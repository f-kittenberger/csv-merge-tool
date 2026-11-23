"""Unit tests for ID matching, joins, duplicate/blank IDs, and precedence resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from csv_merge.config import (
    ColumnRule,
    InputFileError,
    JoinConfig,
    JoinMode,
    MappingConfig,
    SourceFileConfig,
)
from csv_merge.merger import normalize_id, reconcile


def _base_config(mode: JoinMode = "outer") -> MappingConfig:
    return MappingConfig(
        source_a=SourceFileConfig(encoding="utf-8", delimiter=",", null_values=("NULL",)),
        source_b=SourceFileConfig(encoding="utf-8", delimiter=",", null_values=("N/A",)),
        join=JoinConfig(column_a="id_a", column_b="id_b", mode=mode),
        columns=(
            ColumnRule(name="out_id", source_a="id_a", source_b="id_b", leading="A", type="str"),
            ColumnRule(
                name="col_a_lead", source_a="f1_a", source_b="f1_b", leading="A", type="str"
            ),
            ColumnRule(
                name="col_b_lead", source_a="f2_a", source_b="f2_b", leading="B", type="str"
            ),
            ColumnRule(name="only_from_a", source_a="extra_a", source_b=None, leading="A"),
            ColumnRule(name="only_from_b", source_a=None, source_b="extra_b", leading="B"),
        ),
    )


def test_normalize_id() -> None:
    assert normalize_id("  ab-001 ") == "AB-001"
    assert normalize_id("\tUsr_9\n") == "USR_9"


def test_join_modes_ordering_and_precedence(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_a.write_text(
        "id_a,f1_a,f2_a,extra_a,ignored_a\n"
        "  Usr-001 ,  AlphaLead ,A_fallback,exA1,skip1\n"
        "usr-002,,A_only_f2,exA2,skip2\n",
        encoding="utf-8",
    )
    file_b = tmp_path / "b.csv"
    file_b.write_text(
        "id_b,f1_b,f2_b,extra_b,ignored_b\n"
        "USR-001,BetaSec,N/A,exB1,skipB1\n"
        "usr-003,BetaOnly,B_f2,exB3,skipB3\n",
        encoding="utf-8",
    )

    outer = reconcile(file_a, file_b, _base_config("outer"))
    assert outer.headers == ("out_id", "col_a_lead", "col_b_lead", "only_from_a", "only_from_b")
    assert outer.rows == [
        ["Usr-001", "AlphaLead", "A_fallback", "exA1", "exB1"],
        ["usr-002", "", "A_only_f2", "exA2", ""],
        ["usr-003", "BetaOnly", "B_f2", "", "exB3"],
    ]
    assert outer.summary.matched_count == 1
    assert outer.summary.only_a_count == 1
    assert outer.summary.only_b_count == 1
    assert outer.summary.output_row_count == 3

    left = reconcile(file_a, file_b, _base_config("left"))
    assert [r[0] for r in left.rows] == ["Usr-001", "usr-002"]
    assert left.summary.only_b_count == 1
    assert left.summary.output_row_count == 2

    inner = reconcile(file_a, file_b, _base_config("inner"))
    assert [r[0] for r in inner.rows] == ["Usr-001"]
    assert inner.summary.output_row_count == 1


def test_duplicate_and_missing_id_detection(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_a.write_text(
        "id_a,f1_a,f2_a,extra_a\n"
        "K-1,First,A1,E1\n"
        " ,BlankRow,A2,E2\n"
        " k-1 ,Duplicate,A3,E3\n"
        "NULL,MarkerBlank,A4,E4\n",
        encoding="utf-8",
    )
    file_b = tmp_path / "b.csv"
    file_b.write_text(
        "id_b,f1_b,f2_b,extra_b\n"
        "K-1,B_val,B1,EB1\n"
        "k-1,B_dup,B2,EB2\n",
        encoding="utf-8",
    )

    res = reconcile(file_a, file_b, _base_config("outer"))
    assert res.rows == [["K-1", "First", "B1", "E1", "EB1"]]
    assert res.summary.rows_read_a == 4
    assert res.summary.rows_read_b == 2
    assert res.summary.duplicate_id_count == 2
    assert res.summary.missing_id_count == 2
    assert [e.error_category for e in res.errors] == [
        "missing_id",
        "duplicate_id",
        "missing_id",
        "duplicate_id",
    ]
    assert res.errors[0].row_number == 3
    assert res.errors[1].row_number == 4
    assert res.errors[2].row_number == 5
    assert res.errors[3].row_number == 3


def test_header_only_and_header_validation_errors(tmp_path: Path) -> None:
    header_only_a = tmp_path / "empty_rows_a.csv"
    header_only_a.write_text("id_a,f1_a,f2_a,extra_a\n", encoding="utf-8")
    file_b = tmp_path / "b.csv"
    file_b.write_text("id_b,f1_b,f2_b,extra_b\nR1,B1,B2,EB\n", encoding="utf-8")

    res_outer = reconcile(header_only_a, file_b, _base_config("outer"))
    assert res_outer.rows == [["R1", "B1", "B2", "", "EB"]]

    res_inner = reconcile(header_only_a, file_b, _base_config("inner"))
    assert res_inner.rows == []

    missing_col = tmp_path / "missing_col.csv"
    missing_col.write_text("id_a,f1_a\n1,X\n", encoding="utf-8")
    with pytest.raises(InputFileError, match="not found"):
        reconcile(missing_col, file_b, _base_config("outer"))

    dup_header = tmp_path / "dup_header.csv"
    dup_header.write_text("id_a,f1_a,f1_a,f2_a,extra_a\n1,X,Y,Z,W\n", encoding="utf-8")
    with pytest.raises(InputFileError, match="Duplicate header"):
        reconcile(dup_header, file_b, _base_config("outer"))

    zero_byte = tmp_path / "zero.csv"
    zero_byte.write_bytes(b"")
    with pytest.raises(InputFileError, match="empty"):
        reconcile(zero_byte, file_b, _base_config("outer"))


def test_type_coercion_and_leading_error_non_fallback(tmp_path: Path) -> None:
    cfg = MappingConfig(
        source_a=SourceFileConfig(number_format="eu", date_format="eu"),
        source_b=SourceFileConfig(number_format="us", date_format="iso"),
        join=JoinConfig(column_a="id", column_b="id", mode="outer"),
        columns=(
            ColumnRule(name="id", source_a="id", source_b="id", leading="A", type="str"),
            ColumnRule(name="qty", source_a="qty", source_b="qty", leading="A", type="int"),
            ColumnRule(
                name="amount", source_a="amount", source_b="amount", leading="A", type="float"
            ),
            ColumnRule(name="dt", source_a="dt", source_b="dt", leading="B", type="date"),
            ColumnRule(name="flag", source_a="flag", source_b="flag", leading="A", type="bool"),
        ),
    )

    file_a = tmp_path / "a.csv"
    file_a.write_text(
        "id,qty,amount,dt,flag\n"
        'R1,1.000,"1.250,50",23.11.2026,Ja\n'
        'R2,bad-int,"12,50",01.02.2026,true\n',
        encoding="utf-8",
    )
    file_b = tmp_path / "b.csv"
    file_b.write_text(
        'id,qty,amount,dt,flag\n'
        'R1,999,"2,345.67",2026-11-23,false\n'
        'R2,42,"99.99",bad-date,false\n',
        encoding="utf-8",
    )

    res = reconcile(file_a, file_b, cfg)
    assert res.rows == [
        ["R1", "1000", "1250.5", "2026-11-23", "true"],
        ["R2", "", "12.5", "", "true"],
    ]
    assert res.summary.type_conversion_error_count == 2
    assert [(e.error_category, e.system, e.column, e.target_type) for e in res.errors] == [
        ("type_conversion", "A", "qty", "int"),
        ("type_conversion", "B", "dt", "date"),
    ]


def test_lookup_before_coercion_and_unmapped_aggregation(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "cfg"
    lookups_dir = cfg_dir / "lookups"
    lookups_dir.mkdir(parents=True)
    cfg_path = cfg_dir / "mapping.yaml"

    (lookups_dir / "bool_codes.csv").write_text(
        "source_a_value,source_b_value,unified_value\n"
        "Y_CODE,Yes,true\n"
        "N_CODE,No,false\n",
        encoding="utf-8",
    )
    (lookups_dir / "status.csv").write_text(
        "source_a_value,source_b_value,unified_value\n"
        "ACT,Active,ACTIVE\n"
        "WAIT,Pending,\n",
        encoding="utf-8",
    )

    cfg = MappingConfig(
        source_a=SourceFileConfig(),
        source_b=SourceFileConfig(),
        join=JoinConfig(column_a="id", column_b="id", mode="outer"),
        columns=(
            ColumnRule(name="id", source_a="id", source_b="id", leading="A", type="str"),
            ColumnRule(
                name="status",
                source_a="st_a",
                source_b="st_b",
                leading="A",
                type="str",
                normalize=True,
                lookup="lookups/status.csv",
            ),
            ColumnRule(
                name="enabled",
                source_a="en_a",
                source_b="en_b",
                leading="B",
                type="bool",
                normalize=True,
                lookup="lookups/bool_codes.csv",
            ),
        ),
    )

    file_a = tmp_path / "a.csv"
    file_a.write_text(
        "id,st_a,en_a\n"
        "R1, act ,Y_CODE\n"
        "R2,,N_CODE\n"
        "R3,  CustomRaw ,Y_CODE\n"
        "R4,WAIT,N_CODE\n",
        encoding="utf-8",
    )
    file_b = tmp_path / "b.csv"
    file_b.write_text(
        "id,st_b,en_b\n"
        "R1,Active,Yes\n"
        "R2,ACTIVE,\n"
        "R3,pending,No\n"
        "R4,Active,Yes\n",
        encoding="utf-8",
    )

    res = reconcile(file_a, file_b, cfg, config_path=cfg_path)
    assert res.rows == [
        ["R1", "ACTIVE", "true"],
        ["R2", "ACTIVE", "false"],
        ["R3", "CustomRaw", "false"],
        ["R4", "WAIT", "true"],
    ]
    assert res.summary.unmapped_value_occurrences == 3
    assert res.summary.unmapped_distinct_count == 3
    observed_unmapped = [
        (u.system, u.column, u.raw_value, u.occurrence_count, u.sample_record_id)
        for u in res.unmapped_values
    ]
    assert observed_unmapped == [
        ("A", "status", "CustomRaw", 1, "R3"),
        ("A", "status", "WAIT", 1, "R4"),
        ("B", "status", "pending", 1, "R3"),
    ]
