"""Record indexing, duplicate/missing-ID detection, join engine, and precedence resolution."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from csv_merge.coercion import (
    CoercionResult,
    LookupTable,
    coerce_value,
    is_empty_value,
    load_lookup_table,
    resolve_lookup,
)
from csv_merge.config import (
    ColumnRule,
    ConfigError,
    InputFileError,
    JoinMode,
    MappingConfig,
    NumberFormat,
    SourceFileConfig,
    SystemId,
    resolve_lookup_path,
)

ErrorCategory = Literal["duplicate_id", "missing_id", "type_conversion"]


@dataclass(frozen=True, slots=True)
class IndexedRow:
    """One deduplicated source CSV row retained in memory for joining."""

    row_number: int
    raw_id: str
    normalized_id: str
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class MergeError:
    """One diagnostic row recorded for errors.csv."""

    error_category: ErrorCategory
    system: SystemId
    row_number: int
    record_id: str
    column: str
    raw_value: str
    target_type: str
    message: str


@dataclass(frozen=True, slots=True)
class UnmappedValueRecord:
    """Aggregated unmapped lookup value record for unmapped_values.csv."""

    system: SystemId
    column: str
    raw_value: str
    occurrence_count: int
    sample_record_id: str


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """High-level counts and diagnostic totals for a reconciliation run."""

    rows_read_a: int
    rows_read_b: int
    matched_count: int
    only_a_count: int
    only_b_count: int
    output_row_count: int
    duplicate_id_count: int
    missing_id_count: int
    unmapped_value_occurrences: int
    unmapped_distinct_count: int
    type_conversion_error_count: int


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Complete output of merger.reconcile consumed by reporter."""

    headers: tuple[str, ...]
    rows: list[list[str]]
    unmapped_values: list[UnmappedValueRecord]
    errors: list[MergeError]
    summary: ReconciliationSummary


def normalize_id(raw: str) -> str:
    """Normalize a record ID as a trimmed uppercase string for matching."""
    return raw.strip().upper()


def _null_markers(source_cfg: SourceFileConfig) -> frozenset[str]:
    return frozenset(m.strip().casefold() for m in source_cfg.null_values if m.strip())


def _required_columns(config: MappingConfig, system: SystemId) -> set[str]:
    cols: set[str] = {config.join.column_a if system == "A" else config.join.column_b}
    for rule in config.columns:
        src_col = rule.source_a if system == "A" else rule.source_b
        if src_col is not None:
            cols.add(src_col)
    return cols


def _load_indexed_rows(
    path: Path,
    source_cfg: SourceFileConfig,
    id_column: str,
    required_cols: set[str],
    system: SystemId,
    errors: list[MergeError],
) -> tuple[dict[str, IndexedRow], int, int, int]:
    """Validate headers and stream-index deduplicated rows from a source CSV."""
    if not path.is_file():
        raise InputFileError(f"Input CSV file for System {system} not found: {path}")
    if path.stat().st_size == 0:
        raise InputFileError(f"Input CSV file for System {system} is empty (0 bytes): {path}")

    null_markers = _null_markers(source_cfg)
    indexed: dict[str, IndexedRow] = {}
    rows_read = 0
    duplicate_count = 0
    missing_count = 0

    try:
        with path.open("r", encoding=source_cfg.encoding, newline="") as fh:
            reader = csv.reader(fh, delimiter=source_cfg.delimiter)
            raw_headers = next(reader, None)
            if raw_headers is None or not raw_headers or all(not h.strip() for h in raw_headers):
                raise InputFileError(
                    f"Input CSV file for System {system} ('{path}') contains no valid header row."
                )

            stripped_headers = [h.strip() for h in raw_headers]
            col_indices: dict[str, int] = {}
            for req in sorted(required_cols):
                matches = [idx for idx, h in enumerate(stripped_headers) if h == req]
                if not matches:
                    raise InputFileError(
                        f"Configured column '{req}' not found in System {system} file '{path}'."
                    )
                if len(matches) > 1:
                    raise InputFileError(
                        f"Duplicate header '{req}' referenced in System {system} file '{path}'."
                    )
                col_indices[req] = matches[0]

            id_idx = col_indices[id_column]
            value_cols = {c: idx for c, idx in col_indices.items() if c != id_column}

            for row_number, row in enumerate(reader, start=2):
                if not row:
                    continue
                rows_read += 1
                raw_id = row[id_idx] if id_idx < len(row) else ""
                if is_empty_value(raw_id, null_markers):
                    missing_count += 1
                    errors.append(
                        MergeError(
                            error_category="missing_id",
                            system=system,
                            row_number=row_number,
                            record_id="",
                            column=id_column,
                            raw_value=raw_id,
                            target_type="",
                            message=(
                                f"Missing or blank ID in System {system} row {row_number}."
                            ),
                        )
                    )
                    continue

                norm_id = normalize_id(raw_id)
                if norm_id in indexed:
                    duplicate_count += 1
                    first_row = indexed[norm_id].row_number
                    errors.append(
                        MergeError(
                            error_category="duplicate_id",
                            system=system,
                            row_number=row_number,
                            record_id=norm_id,
                            column=id_column,
                            raw_value=raw_id,
                            target_type="",
                            message=(
                                f"Duplicate normalized ID '{norm_id}' in System {system} "
                                f"row {row_number}; retaining first occurrence at row {first_row}."
                            ),
                        )
                    )
                    continue

                extracted = {
                    col_name: (row[idx] if idx < len(row) else "")
                    for col_name, idx in value_cols.items()
                }
                extracted[id_column] = raw_id
                indexed[norm_id] = IndexedRow(
                    row_number=row_number,
                    raw_id=raw_id,
                    normalized_id=norm_id,
                    values=extracted,
                )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise InputFileError(
            f"Failed to read System {system} file '{path}': {exc}"
        ) from exc

    return indexed, rows_read, duplicate_count, missing_count


@dataclass(slots=True)
class _UnmappedAccumulator:
    occurrence_count: int
    sample_record_id: str


def _preload_lookups(
    config: MappingConfig,
    config_path: Path | None,
) -> dict[str, LookupTable]:
    tables: dict[str, LookupTable] = {}
    for rule in config.columns:
        if rule.normalize and rule.lookup is None:
            raise ConfigError(
                f"Column '{rule.name}' has normalize=true but no 'lookup' path configured."
            )
        if rule.lookup is not None:
            resolved = (
                resolve_lookup_path(config_path, rule.lookup)
                if config_path is not None
                else Path(rule.lookup)
            )
            tables[rule.name] = load_lookup_table(resolved)
    return tables


def _evaluate_cell(
    row: IndexedRow | None,
    source_col: str | None,
    rule: ColumnRule,
    system: SystemId,
    record_id: str,
    null_markers: frozenset[str],
    number_format: NumberFormat,
    date_format: str,
    lookup_table: LookupTable | None,
    unmapped: dict[tuple[SystemId, str, str], _UnmappedAccumulator],
    errors: list[MergeError],
) -> tuple[CoercionResult, int, int]:
    if row is None or source_col is None:
        return CoercionResult(status="empty", value=""), 0, 0
    raw = row.values[source_col]
    if is_empty_value(raw, null_markers):
        return CoercionResult(status="empty", value=""), 0, 0

    candidate = raw
    unmapped_hit = 0
    if lookup_table is not None:
        lookup_res = resolve_lookup(lookup_table, system, raw)
        if not lookup_res.mapped:
            unmapped_hit = 1
            key = (system, rule.name, lookup_res.value)
            acc = unmapped.get(key)
            if acc is None:
                unmapped[key] = _UnmappedAccumulator(
                    occurrence_count=1,
                    sample_record_id=record_id,
                )
            else:
                acc.occurrence_count += 1
        candidate = lookup_res.value

    result = coerce_value(
        candidate,
        rule.type,
        number_format=number_format,
        date_format=date_format,
        null_markers=null_markers,
    )
    if result.status == "error":
        errors.append(
            MergeError(
                error_category="type_conversion",
                system=system,
                row_number=row.row_number,
                record_id=record_id,
                column=rule.name,
                raw_value=raw,
                target_type=rule.type,
                message=result.error_message
                or f"Failed converting {raw!r} to {rule.type}.",
            )
        )
        return result, 1, unmapped_hit
    return result, 0, unmapped_hit


def _select_cell_value(
    rule: ColumnRule,
    res_a: CoercionResult,
    res_b: CoercionResult,
    has_a: bool,
    has_b: bool,
) -> str:
    if has_a and not has_b:
        return res_a.value if res_a.status == "ok" else ""
    if has_b and not has_a:
        return res_b.value if res_b.status == "ok" else ""

    leading_res, secondary_res = (res_a, res_b) if rule.leading == "A" else (res_b, res_a)
    if leading_res.status == "ok":
        return leading_res.value
    if leading_res.status == "error":
        return ""
    return secondary_res.value if secondary_res.status == "ok" else ""


def reconcile(
    file_a: Path,
    file_b: Path,
    config: MappingConfig,
    *,
    config_path: Path | None = None,
    join_mode_override: JoinMode | None = None,
) -> MergeResult:
    """Reconcile and merge System A and System B CSV files under MappingConfig rules."""
    lookup_tables = _preload_lookups(config, config_path)
    errors: list[MergeError] = []
    unmapped_acc: dict[tuple[SystemId, str, str], _UnmappedAccumulator] = {}

    req_a = _required_columns(config, "A")
    req_b = _required_columns(config, "B")

    indexed_a, rows_read_a, dup_a, miss_a = _load_indexed_rows(
        file_a, config.source_a, config.join.column_a, req_a, "A", errors
    )
    indexed_b, rows_read_b, dup_b, miss_b = _load_indexed_rows(
        file_b, config.source_b, config.join.column_b, req_b, "B", errors
    )

    matched_keys = [k for k in indexed_a if k in indexed_b]
    only_a_keys = [k for k in indexed_a if k not in indexed_b]
    only_b_keys = [k for k in indexed_b if k not in indexed_a]

    join_mode = join_mode_override if join_mode_override is not None else config.join.mode
    if join_mode == "outer":
        ordered_keys = [*indexed_a.keys(), *only_b_keys]
    elif join_mode == "left":
        ordered_keys = list(indexed_a.keys())
    else:
        ordered_keys = matched_keys

    null_a = _null_markers(config.source_a)
    null_b = _null_markers(config.source_b)
    headers = tuple(col.name for col in config.columns)
    output_rows: list[list[str]] = []
    type_error_count = 0
    unmapped_occurrences = 0

    for key in ordered_keys:
        row_a = indexed_a.get(key)
        row_b = indexed_b.get(key)
        has_a = row_a is not None
        has_b = row_b is not None
        merged_row: list[str] = []
        for rule in config.columns:
            num_fmt_a = rule.number_format_a or config.source_a.number_format
            num_fmt_b = rule.number_format_b or config.source_b.number_format
            date_fmt_a = rule.date_format_a or config.source_a.date_format
            date_fmt_b = rule.date_format_b or config.source_b.date_format
            table = lookup_tables.get(rule.name)

            res_a, err_a, unm_a = _evaluate_cell(
                row_a,
                rule.source_a,
                rule,
                "A",
                key,
                null_a,
                num_fmt_a,
                date_fmt_a,
                table,
                unmapped_acc,
                errors,
            )
            res_b, err_b, unm_b = _evaluate_cell(
                row_b,
                rule.source_b,
                rule,
                "B",
                key,
                null_b,
                num_fmt_b,
                date_fmt_b,
                table,
                unmapped_acc,
                errors,
            )
            type_error_count += err_a + err_b
            unmapped_occurrences += unm_a + unm_b
            merged_row.append(_select_cell_value(rule, res_a, res_b, has_a, has_b))
        output_rows.append(merged_row)

    unmapped_records = [
        UnmappedValueRecord(
            system=sys_id,
            column=col_name,
            raw_value=raw_val,
            occurrence_count=acc.occurrence_count,
            sample_record_id=acc.sample_record_id,
        )
        for (sys_id, col_name, raw_val), acc in sorted(unmapped_acc.items())
    ]

    summary = ReconciliationSummary(
        rows_read_a=rows_read_a,
        rows_read_b=rows_read_b,
        matched_count=len(matched_keys),
        only_a_count=len(only_a_keys),
        only_b_count=len(only_b_keys),
        output_row_count=len(output_rows),
        duplicate_id_count=dup_a + dup_b,
        missing_id_count=miss_a + miss_b,
        unmapped_value_occurrences=unmapped_occurrences,
        unmapped_distinct_count=len(unmapped_records),
        type_conversion_error_count=type_error_count,
    )

    return MergeResult(
        headers=headers,
        rows=output_rows,
        unmapped_values=unmapped_records,
        errors=errors,
        summary=summary,
    )
