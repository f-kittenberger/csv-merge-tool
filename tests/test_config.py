"""Unit tests for configuration models, YAML persistence, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from csv_merge.config import (
    ColumnRule,
    ConfigError,
    JoinConfig,
    MappingConfig,
    OutputConfig,
    SourceFileConfig,
    load_config,
    resolve_lookup_path,
    save_config,
)


def _sample_config() -> MappingConfig:
    return MappingConfig(
        version=1,
        source_a=SourceFileConfig(
            encoding="utf-8-sig",
            delimiter=";",
            number_format="eu",
            date_format="eu",
            null_values=("N/A", "-"),
        ),
        source_b=SourceFileConfig(
            encoding="cp1252",
            delimiter=",",
            number_format="us",
            date_format="iso",
        ),
        join=JoinConfig(column_a="id_a", column_b="id_b", mode="left"),
        output=OutputConfig(encoding="utf-8", delimiter=","),
        columns=(
            ColumnRule(
                name="record_id",
                source_a="id_a",
                source_b="id_b",
                leading="A",
                type="str",
            ),
            ColumnRule(
                name="category",
                source_a="cat_a",
                source_b="cat_b",
                leading="B",
                type="str",
                normalize=True,
                lookup="lookups/category.csv",
            ),
            ColumnRule(
                name="amount",
                source_a="amt_a",
                source_b="amt_b",
                leading="A",
                type="float",
                number_format_a="eu",
                number_format_b="us",
            ),
            ColumnRule(
                name="only_a_note",
                source_a="note_a",
                source_b=None,
                leading="A",
                type="str",
                date_format_a="%d.%m.%Y",
            ),
        ),
    )


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "nested" / "mapping.yaml"
    original = _sample_config()

    save_config(original, cfg_path)
    loaded = load_config(cfg_path)

    assert loaded == original


def test_load_defaults_for_optional_fields(tmp_path: Path) -> None:
    cfg_path = tmp_path / "mapping.yaml"
    cfg_path.write_text(
        """
source_a: {}
source_b: {}
join:
  column_a: key_a
  column_b: key_b
columns:
  - name: key
    source_a: key_a
    source_b: key_b
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(cfg_path)

    assert loaded.version == 1
    assert loaded.join.mode == "outer"
    assert loaded.output == OutputConfig(encoding="utf-8", delimiter=",")
    assert loaded.source_a == SourceFileConfig()
    assert loaded.columns[0] == ColumnRule(
        name="key",
        source_a="key_a",
        source_b="key_b",
        leading="A",
        type="str",
    )


def test_resolve_lookup_path_relative_and_absolute(tmp_path: Path) -> None:
    cfg_path = tmp_path / "configs" / "mapping.yaml"
    rel = resolve_lookup_path(cfg_path, "lookups/codes.csv")
    assert rel == cfg_path.resolve().parent / "lookups" / "codes.csv"

    abs_target = (tmp_path / "shared" / "codes.csv").resolve()
    assert resolve_lookup_path(cfg_path, str(abs_target)) == abs_target


def test_load_missing_and_invalid_yaml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("source_a: [unterminated", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(bad_yaml)


@pytest.mark.parametrize(
    ("yaml_text", "match"),
    [
        (
            "version: 2\nsource_a: {}\nsource_b: {}\njoin: {column_a: a, column_b: b}\n"
            "columns: [{name: c, source_a: a}]",
            "version",
        ),
        (
            "version: true\nsource_a: {}\nsource_b: {}\njoin: {column_a: a, column_b: b}\n"
            "columns: [{name: c, source_a: a}]",
            "version",
        ),
        (
            "source_a: {encoding: no-such-codec-xyz}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a}]",
            "unknown codec",
        ),
        (
            "source_a: {delimiter: ';;'}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a}]",
            "single character",
        ),
        (
            "source_a: {date_format: badfmt}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a}]",
            "date_format",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b, mode: right}\ncolumns: [{name: c, source_a: a}]",
            "join.mode",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a, type: decimal}]",
            "type must be one of",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a, leading: C}]",
            "leading system",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: [{name: c, source_a: a, leading: B}]",
            "source_b",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\n"
            "columns: [{name: dup, source_a: a}, {name: dup, source_a: a2}]",
            "Duplicate output column",
        ),
        (
            "source_a: {}\nsource_b: {}\n"
            "join: {column_a: a, column_b: b}\ncolumns: []",
            "non-empty list",
        ),
    ],
)
def test_validation_errors(tmp_path: Path, yaml_text: str, match: str) -> None:
    cfg_path = tmp_path / "invalid.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigError, match=match):
        load_config(cfg_path)


def test_normalize_without_lookup_toggle(tmp_path: Path) -> None:
    cfg_path = tmp_path / "norm.yaml"
    cfg_path.write_text(
        """
source_a: {}
source_b: {}
join:
  column_a: a
  column_b: b
columns:
  - name: status
    source_a: st_a
    source_b: st_b
    normalize: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="no 'lookup' path"):
        load_config(cfg_path, require_lookup_for_normalized=True)

    cfg = load_config(cfg_path, require_lookup_for_normalized=False)
    assert cfg.columns[0].normalize is True
    assert cfg.columns[0].lookup is None
