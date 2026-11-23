"""Unit tests for merged/diagnostic CSV writers and reconciliation summary formatting."""

from __future__ import annotations

import csv
from pathlib import Path

from csv_merge.config import OutputConfig
from csv_merge.merger import (
    MergeError,
    MergeResult,
    ReconciliationSummary,
    UnmappedValueRecord,
)
from csv_merge.reporter import (
    ERROR_HEADERS,
    UNMAPPED_HEADERS,
    format_reconciliation_summary,
    write_all_reports,
)


def test_write_all_reports_clean_writes_header_only_diagnostics(tmp_path: Path) -> None:
    result = MergeResult(
        headers=("rec_id", "amount"),
        rows=[["R1", "10.5"]],
        unmapped_values=[],
        errors=[],
        summary=ReconciliationSummary(
            rows_read_a=1,
            rows_read_b=1,
            matched_count=1,
            only_a_count=0,
            only_b_count=0,
            output_row_count=1,
            duplicate_id_count=0,
            missing_id_count=0,
            unmapped_value_occurrences=0,
            unmapped_distinct_count=0,
            type_conversion_error_count=0,
        ),
    )

    out_file = tmp_path / "nested" / "out" / "merged.csv"
    merged_p, unmapped_p, errors_p = write_all_reports(
        result, out_file, OutputConfig(encoding="utf-8", delimiter=",")
    )

    assert merged_p == out_file
    assert unmapped_p == out_file.parent / "unmapped_values.csv"
    assert errors_p == out_file.parent / "errors.csv"

    with merged_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh)) == [["rec_id", "amount"], ["R1", "10.5"]]
    with unmapped_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh)) == [list(UNMAPPED_HEADERS)]
    with errors_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh)) == [list(ERROR_HEADERS)]


def test_write_all_reports_populated_sorted_and_summary(tmp_path: Path) -> None:
    result = MergeResult(
        headers=("rec_id", "status"),
        rows=[["R1", "RAW_Z"], ["R2", "ACTIVE"]],
        unmapped_values=[
            UnmappedValueRecord("B", "status", "zeta", 2, "R1"),
            UnmappedValueRecord("A", "status", "alpha", 1, "R2"),
        ],
        errors=[
            MergeError("duplicate_id", "A", 4, "R1", "id_a", " r1 ", "", "Duplicate ID"),
            MergeError("missing_id", "B", 3, "", "id_b", "", "", "Blank ID"),
            MergeError("type_conversion", "A", 2, "R2", "qty", "oops", "int", "Bad int"),
        ],
        summary=ReconciliationSummary(
            rows_read_a=4,
            rows_read_b=3,
            matched_count=1,
            only_a_count=1,
            only_b_count=1,
            output_row_count=2,
            duplicate_id_count=1,
            missing_id_count=1,
            unmapped_value_occurrences=3,
            unmapped_distinct_count=2,
            type_conversion_error_count=1,
        ),
    )

    out_file = tmp_path / "merged.csv"
    custom_unmapped = tmp_path / "diag" / "unmapped.csv"
    custom_errors = tmp_path / "diag" / "errs.csv"
    merged_p, unmapped_p, errors_p = write_all_reports(
        result,
        out_file,
        OutputConfig(encoding="utf-8", delimiter=";"),
        unmapped_path=custom_unmapped,
        errors_path=custom_errors,
    )

    with merged_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh, delimiter=";")) == [
            ["rec_id", "status"],
            ["R1", "RAW_Z"],
            ["R2", "ACTIVE"],
        ]
    with unmapped_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh)) == [
            list(UNMAPPED_HEADERS),
            ["A", "status", "alpha", "1", "R2"],
            ["B", "status", "zeta", "2", "R1"],
        ]
    with errors_p.open("r", encoding="utf-8", newline="") as fh:
        assert list(csv.reader(fh)) == [
            list(ERROR_HEADERS),
            ["duplicate_id", "A", "4", "R1", "id_a", " r1 ", "", "Duplicate ID"],
            ["missing_id", "B", "3", "", "id_b", "", "", "Blank ID"],
            ["type_conversion", "A", "2", "R2", "qty", "oops", "int", "Bad int"],
        ]

    summary_text = format_reconciliation_summary(
        result,
        join_mode="outer",
        merged_path=merged_p,
        unmapped_path=unmapped_p,
        errors_path=errors_p,
    )
    assert "Join mode:                outer" in summary_text
    assert "Rows read (System A):     4" in summary_text
    assert "Rows read (System B):     3" in summary_text
    assert "Matched records:          1" in summary_text
    assert "Output rows written:      2" in summary_text
    assert "Intra-file duplicate IDs: 1" in summary_text
    assert "Missing/blank IDs:        1" in summary_text
    assert "Unmapped lookup values:   3 (2 distinct)" in summary_text
    assert "Type conversion errors:   1" in summary_text
