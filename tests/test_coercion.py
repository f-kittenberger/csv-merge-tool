"""Unit tests for locale-aware coercion across str, int, float, date, and bool."""

from __future__ import annotations

from pathlib import Path

import pytest

from csv_merge.coercion import coerce_value, load_lookup_table, resolve_lookup
from csv_merge.config import ConfigError, NumberFormat


def test_coerce_str_trims_and_preserves_casing() -> None:
    res = coerce_value("  Mixed Case Text  ", "str")
    assert res.status == "ok"
    assert res.value == "Mixed Case Text"

    empty_res = coerce_value("   ", "str")
    assert empty_res.status == "empty"
    assert empty_res.value == ""

    marker_res = coerce_value(" N/A ", "str", null_markers=frozenset({"n/a"}))
    assert marker_res.status == "empty"


@pytest.mark.parametrize(
    ("raw", "fmt", "expected"),
    [
        ("42", "auto", "42"),
        (" -15 ", "auto", "-15"),
        ("42.0", "us", "42"),
        ("42,00", "eu", "42"),
        ("1.000", "eu", "1000"),
        ("1,000", "us", "1000"),
        ("1 000", "eu", "1000"),
        ("1,000,000", "auto", "1000000"),
    ],
)
def test_coerce_int_valid(raw: str, fmt: NumberFormat, expected: str) -> None:
    res = coerce_value(raw, "int", number_format=fmt)
    assert res.status == "ok"
    assert res.value == expected


@pytest.mark.parametrize(
    ("raw", "fmt"),
    [
        ("12.34", "us"),
        ("12,34", "eu"),
        ("abc", "auto"),
        ("$100", "us"),
        ("NaN", "auto"),
    ],
)
def test_coerce_int_invalid(raw: str, fmt: NumberFormat) -> None:
    res = coerce_value(raw, "int", number_format=fmt)
    assert res.status == "error"
    assert res.error_message


@pytest.mark.parametrize(
    ("raw", "fmt", "expected"),
    [
        ("1.250,50", "eu", "1250.5"),
        ("1.250,50", "auto", "1250.5"),
        ("1 250,50", "eu", "1250.5"),
        ("1 250,50", "auto", "1250.5"),
        ("1,250.50", "us", "1250.5"),
        ("1,250.50", "auto", "1250.5"),
        ("1250.50", "auto", "1250.5"),
        ("1.234,56", "eu", "1234.56"),
        ("2,345.67", "us", "2345.67"),
        ("1000.00", "us", "1000"),
        ("-0.00", "auto", "0"),
        ("1000000.25", "us", "1000000.25"),
        ("0,123", "auto", "0.123"),
        ("1,234", "auto", "1234"),
        ("1,234", "eu", "1.234"),
        ("12,5", "auto", "12.5"),
    ],
)
def test_coerce_float_valid(raw: str, fmt: NumberFormat, expected: str) -> None:
    res = coerce_value(raw, "float", number_format=fmt)
    assert res.status == "ok"
    assert res.value == expected


@pytest.mark.parametrize(
    ("raw", "fmt"),
    [
        ("1,250.50", "eu"),
        ("1.250,50", "us"),
        ("12.3.4", "auto"),
        ("Infinity", "auto"),
        ("not-a-number", "auto"),
    ],
)
def test_coerce_float_invalid(raw: str, fmt: NumberFormat) -> None:
    res = coerce_value(raw, "float", number_format=fmt)
    assert res.status == "error"


@pytest.mark.parametrize(
    ("raw", "fmt", "expected"),
    [
        ("2026-11-23", "auto", "2026-11-23"),
        ("2026-11-23", "iso", "2026-11-23"),
        ("23.11.2026", "auto", "2026-11-23"),
        ("5.1.2026", "eu", "2026-01-05"),
        ("23/11/2026", "auto", "2026-11-23"),
        ("23-11-2026", "eu", "2026-11-23"),
        ("11/23/2026", "auto", "2026-11-23"),
        ("11-23-2026", "us", "2026-11-23"),
        ("03/04/2026", "auto", "2026-03-04"),
        ("03/04/2026", "us", "2026-03-04"),
        ("03/04/2026", "eu", "2026-04-03"),
        ("2026/11/23", "%Y/%m/%d", "2026-11-23"),
    ],
)
def test_coerce_date_valid(raw: str, fmt: str, expected: str) -> None:
    res = coerce_value(raw, "date", date_format=fmt)
    assert res.status == "ok"
    assert res.value == expected


@pytest.mark.parametrize(
    ("raw", "fmt"),
    [
        ("23.11.2026", "iso"),
        ("2026-02-30", "iso"),
        ("not-a-date", "auto"),
        ("23/11/2026", "us"),
        ("11/23/2026", "eu"),
        ("23.11.2026", "%Y/%m/%d"),
    ],
)
def test_coerce_date_invalid(raw: str, fmt: str) -> None:
    res = coerce_value(raw, "date", date_format=fmt)
    assert res.status == "error"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", "true"),
        (" TRUE ", "true"),
        ("t", "true"),
        ("Yes", "true"),
        ("y", "true"),
        ("1", "true"),
        ("Ja", "true"),
        ("j", "true"),
        ("wahr", "true"),
        ("false", "false"),
        ("F", "false"),
        ("no", "false"),
        ("N", "false"),
        ("0", "false"),
        ("Nein", "false"),
        ("falsch", "false"),
    ],
)
def test_coerce_bool_valid(raw: str, expected: str) -> None:
    res = coerce_value(raw, "bool")
    assert res.status == "ok"
    assert res.value == expected


def test_coerce_bool_invalid() -> None:
    res = coerce_value("maybe", "bool")
    assert res.status == "error"
    assert res.error_message


def test_load_lookup_table_and_resolve_case_insensitive(tmp_path: Path) -> None:
    lookup = tmp_path / "status.csv"
    lookup.write_text(
        "source_a_value,source_b_value,unified_value\n"
        "ACT,Active,ACTIVE\n"
        "INA,,INACTIVE\n"
        "TBD,Pending,\n",
        encoding="utf-8",
    )

    table = load_lookup_table(lookup)
    res_a = resolve_lookup(table, "A", "  act  ")
    assert res_a.mapped is True
    assert res_a.value == "ACTIVE"

    res_b = resolve_lookup(table, "B", "ACTIVE")
    assert res_b.mapped is True
    assert res_b.value == "ACTIVE"

    blank_target = resolve_lookup(table, "B", " pending ")
    assert blank_target.mapped is False
    assert blank_target.value == "pending"

    unknown = resolve_lookup(table, "A", "  UNKNOWN_CODE ")
    assert unknown.mapped is False
    assert unknown.value == "UNKNOWN_CODE"


def test_lookup_table_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_lookup_table(tmp_path / "missing.csv")

    bad_headers = tmp_path / "bad_headers.csv"
    bad_headers.write_text("a,b,out\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required header"):
        load_lookup_table(bad_headers)

    conflict = tmp_path / "conflict.csv"
    conflict.write_text(
        "source_a_value,source_b_value,unified_value\n"
        "ACT,Active,ACTIVE\n"
        "act,Inactive,ENABLED\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Conflicting System A"):
        load_lookup_table(conflict)
