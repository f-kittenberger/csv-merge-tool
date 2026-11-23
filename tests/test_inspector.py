"""Unit and CLI tests for CSV inspection, format inference, and init generation."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from csv_merge.cli import main
from csv_merge.config import ConfigError, InputFileError, load_config
from csv_merge.inspector import detect_delimiter, detect_encoding, inspect_csv_file, run_init


def test_detect_encoding_bom_utf8_and_cp1252(tmp_path: Path) -> None:
    utf8_bom = tmp_path / "bom.csv"
    utf8_bom.write_bytes(b"\xef\xbb\xbfid,name\n1,M\xc3\xbcller\n")
    assert detect_encoding(utf8_bom) == "utf-8-sig"

    utf8_plain = tmp_path / "utf8.csv"
    utf8_plain.write_text("id,name\n1,Zürich\n", encoding="utf-8")
    assert detect_encoding(utf8_plain) == "utf-8"

    cp1252_file = tmp_path / "cp1252.csv"
    cp1252_file.write_bytes("id;city\n1;München €\n".encode("cp1252"))
    assert detect_encoding(cp1252_file) == "cp1252"


@pytest.mark.parametrize("delim", [",", ";", "\t", "|"])
def test_detect_delimiter_variants(tmp_path: Path, delim: str) -> None:
    csv_file = tmp_path / "sample.csv"
    lines = [
        f"col_1{delim}col_2{delim}col_3",
        f"a{delim}10{delim}x",
        f"b{delim}20{delim}y",
    ]
    csv_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert detect_delimiter(csv_file, "utf-8") == delim


def test_inspect_csv_infers_types_and_regional_formats(tmp_path: Path) -> None:
    eu_file = tmp_path / "eu.csv"
    eu_file.write_bytes(
        (
            "rec_id;count;amount;active;created_on;note\n"
            "1;100;1.250,50;Ja;23.11.2026;München\n"
            "2;200;42,00;Nein;05.01.2026;Größe\n"
        ).encode("cp1252")
    )

    info = inspect_csv_file(eu_file)
    assert info.encoding == "cp1252"
    assert info.delimiter == ";"
    assert info.inferred_number_format == "eu"
    assert info.inferred_date_format == "eu"
    assert info.inferred_types == {
        "rec_id": "int",
        "count": "int",
        "amount": "float",
        "active": "bool",
        "created_on": "date",
        "note": "str",
    }


def test_run_init_generates_config_and_paired_lookup_csv(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_a.write_bytes(
        b"\xef\xbb\xbfemp_id;status;amount;only_a\n"
        b"E1; ACT ;1.250,50;alpha\n"
        b"E2;INA;50,00;\n"
    )
    file_b = tmp_path / "b.csv"
    file_b.write_text(
        "emp_id,status,amount,only_b\n"
        "E1,act,1250.50,beta\n"
        "E3,Closed,99.95,gamma\n",
        encoding="utf-8",
    )

    cfg_path = tmp_path / "work" / "mapping.yaml"
    res = run_init(file_a, file_b, config_path=cfg_path, normalize_columns=["status"])

    assert res.config_written is True
    assert cfg_path.is_file()
    cfg = load_config(cfg_path)
    assert cfg.source_a.encoding == "utf-8-sig"
    assert cfg.source_a.delimiter == ";"
    assert cfg.source_b.encoding == "utf-8"
    assert cfg.source_b.delimiter == ","
    assert cfg.join.column_a == "emp_id"
    assert cfg.join.column_b == "emp_id"
    assert cfg.join.mode == "outer"
    assert [c.name for c in cfg.columns] == ["emp_id", "status", "amount", "only_a", "only_b"]

    status_rule = cfg.columns[1]
    assert status_rule.normalize is True
    assert status_rule.lookup == "lookups/status.csv"

    lookup_file = tmp_path / "work" / "lookups" / "status.csv"
    assert lookup_file.is_file()
    with lookup_file.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))

    assert rows == [
        ["source_a_value", "source_b_value", "unified_value"],
        ["ACT", "act", "ACT"],
        ["", "Closed", ""],
        ["INA", "", ""],
    ]


def test_init_overwrite_protection_and_update_lookups(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_a.write_text("id,dept,grade\n1,ENG,A\n", encoding="utf-8")
    file_b = tmp_path / "b.csv"
    file_b.write_text("id,dept,grade\n1,Engineering,A\n", encoding="utf-8")
    cfg_path = tmp_path / "mapping.yaml"

    run_init(file_a, file_b, config_path=cfg_path, normalize_columns=["dept"])

    # Re-running without --force or --update-lookups fails safely
    with pytest.raises(InputFileError, match="already exists"):
        run_init(file_a, file_b, config_path=cfg_path)

    # User edits dept lookup and marks grade normalize: true without lookup path
    dept_lookup = tmp_path / "lookups" / "dept.csv"
    dept_lookup.write_text(
        "source_a_value,source_b_value,unified_value\nENG,Engineering,ENGINEERING\n",
        encoding="utf-8",
    )
    yaml_text = cfg_path.read_text(encoding="utf-8")
    assert "- name: grade\n" in yaml_text
    yaml_text = yaml_text.replace("- name: grade\n", "- name: grade\n  normalize: true\n")
    cfg_path.write_text(yaml_text, encoding="utf-8")

    res = run_init(file_a, file_b, config_path=cfg_path, update_lookups=True)
    assert res.config_written is True
    assert dept_lookup.read_text(encoding="utf-8").endswith("ENGINEERING\n")
    grade_lookup = tmp_path / "lookups" / "grade.csv"
    assert grade_lookup.is_file()
    updated_cfg = load_config(cfg_path)
    assert updated_cfg.columns[2].lookup == "lookups/grade.csv"

    # Re-running with --force overwrites config and lookup templates cleanly
    forced = run_init(file_a, file_b, config_path=cfg_path, normalize_columns=["dept"], force=True)
    assert forced.config_written is True
    assert "ENGINEERING" not in dept_lookup.read_text(encoding="utf-8")


def test_init_errors_and_cli_integration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_file = tmp_path / "empty.csv"
    empty_file.write_bytes(b"")
    valid_file = tmp_path / "valid.csv"
    valid_file.write_text("id,name\n1,A\n", encoding="utf-8")

    with pytest.raises(InputFileError, match="empty"):
        run_init(empty_file, valid_file, config_path=tmp_path / "m.yaml")

    with pytest.raises(ConfigError, match="does not match"):
        run_init(
            valid_file,
            valid_file,
            config_path=tmp_path / "m.yaml",
            normalize_columns=["nonexistent_col"],
        )

    exit_code = main(
        [
            "init",
            "--file-a",
            str(valid_file),
            "--file-b",
            str(valid_file),
            "--config",
            str(tmp_path / "cli_mapping.yaml"),
            "--normalize",
            "name",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Wrote config:" in out
    assert "Generated lookup template:" in out

    bad_exit = main(
        [
            "init",
            "--file-a",
            str(tmp_path / "missing.csv"),
            "--file-b",
            str(valid_file),
        ]
    )
    assert bad_exit == 1
