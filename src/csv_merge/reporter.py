"""Output CSV writers and reconciliation summary formatting."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from csv_merge.config import JoinMode, OutputConfig
from csv_merge.merger import MergeError, MergeResult, UnmappedValueRecord

UNMAPPED_HEADERS: tuple[str, ...] = (
    "system",
    "column",
    "raw_value",
    "occurrence_count",
    "sample_record_id",
)
ERROR_HEADERS: tuple[str, ...] = (
    "error_category",
    "system",
    "row_number",
    "record_id",
    "column",
    "raw_value",
    "target_type",
    "message",
)


def write_merged_csv(
    result: MergeResult,
    output_path: Path,
    output_config: OutputConfig,
) -> None:
    """Write merged.csv using configured encoding, delimiter, and exact header order."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding=output_config.encoding, newline="") as fh:
        writer = csv.writer(fh, delimiter=output_config.delimiter, lineterminator="\n")
        writer.writerow(result.headers)
        writer.writerows(result.rows)


def write_unmapped_values_csv(
    records: Sequence[UnmappedValueRecord],
    output_path: Path,
) -> None:
    """Write unmapped_values.csv sorted deterministically by (system, column, raw_value)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: (r.system, r.column, r.raw_value))
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=",", lineterminator="\n")
        writer.writerow(UNMAPPED_HEADERS)
        for rec in ordered:
            writer.writerow(
                (
                    rec.system,
                    rec.column,
                    rec.raw_value,
                    rec.occurrence_count,
                    rec.sample_record_id,
                )
            )


def write_errors_csv(
    errors: Sequence[MergeError],
    output_path: Path,
) -> None:
    """Write errors.csv with consistent headers even when zero errors occur."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=",", lineterminator="\n")
        writer.writerow(ERROR_HEADERS)
        for err in errors:
            writer.writerow(
                (
                    err.error_category,
                    err.system,
                    err.row_number,
                    err.record_id,
                    err.column,
                    err.raw_value,
                    err.target_type,
                    err.message,
                )
            )


def write_all_reports(
    result: MergeResult,
    output_path: Path,
    output_config: OutputConfig,
    *,
    unmapped_path: Path | None = None,
    errors_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Write merged.csv, unmapped_values.csv, and errors.csv and return their paths."""
    resolved_unmapped = (
        unmapped_path if unmapped_path is not None else output_path.parent / "unmapped_values.csv"
    )
    resolved_errors = (
        errors_path if errors_path is not None else output_path.parent / "errors.csv"
    )
    write_merged_csv(result, output_path, output_config)
    write_unmapped_values_csv(result.unmapped_values, resolved_unmapped)
    write_errors_csv(result.errors, resolved_errors)
    return output_path, resolved_unmapped, resolved_errors


def format_reconciliation_summary(
    result: MergeResult,
    *,
    join_mode: JoinMode,
    merged_path: Path,
    unmapped_path: Path,
    errors_path: Path,
) -> str:
    """Format a human-readable reconciliation summary matching diagnostic outputs."""
    s = result.summary
    lines = [
        "Reconciliation Summary",
        "----------------------",
        f"Join mode:                {join_mode}",
        f"Rows read (System A):     {s.rows_read_a}",
        f"Rows read (System B):     {s.rows_read_b}",
        f"Matched records:          {s.matched_count}",
        f"System A only records:    {s.only_a_count}",
        f"System B only records:    {s.only_b_count}",
        f"Output rows written:      {s.output_row_count}",
        f"Intra-file duplicate IDs: {s.duplicate_id_count}",
        f"Missing/blank IDs:        {s.missing_id_count}",
        (
            f"Unmapped lookup values:   {s.unmapped_value_occurrences} "
            f"({s.unmapped_distinct_count} distinct)"
        ),
        f"Type conversion errors:   {s.type_conversion_error_count}",
        f"Merged CSV:               {merged_path}",
        f"Unmapped values CSV:      {unmapped_path}",
        f"Errors CSV:               {errors_path}",
    ]
    return "\n".join(lines)
