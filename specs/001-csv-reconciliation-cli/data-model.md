# Data Model: Universal CSV Reconciliation and Merge CLI

**Feature**: `001-csv-reconciliation-cli`
**Date**: 2026-11-23
**Module Mapping**: `src/csv_merge/` (strict Python 3.13 typed frozen dataclasses)

## Overview

All configuration, inspection, lookup, reconciliation, and reporting state is represented by
explicitly typed dataclasses with strict load-time validation and zero hardcoded domain columns.

## 1. Configuration Entities (`src/csv_merge/config.py`)

### `TargetType`, `SystemId`, `JoinMode`, `NumberFormat` (Literal Type Aliases)
- `SystemId = Literal["A", "B"]`
- `JoinMode = Literal["outer", "left", "inner"]`
- `TargetType = Literal["str", "int", "float", "date", "bool"]`
- `NumberFormat = Literal["auto", "eu", "us"]`

### `SourceFileConfig`
Describes ingestion and regional parsing settings for one input CSV (`source_a` or `source_b`).

| Field | Type | Default | Validation Rules |
|-------|------|---------|------------------|
| `encoding` | `str` | `"utf-8"` | Non-empty valid Python codec name (`codecs.lookup`) |
| `delimiter` | `str` | `","` | Exactly 1 character |
| `number_format` | `NumberFormat` | `"auto"` | One of `"auto"`, `"eu"`, `"us"` |
| `date_format` | `str` | `"auto"` | `"auto"`, `"iso"`, `"eu"`, `"us"`, or a strftime pattern containing `"%"` |
| `null_values` | `tuple[str, ...]` | `()` | Optional additional case-insensitive null markers; empty/whitespace always null |

### `JoinConfig`
Defines record matching and join behavior across System A and System B.

| Field | Type | Default | Validation Rules |
|-------|------|---------|------------------|
| `column_a` | `str` | *(required)* | Non-empty source header name in File A |
| `column_b` | `str` | *(required)* | Non-empty source header name in File B |
| `mode` | `JoinMode` | `"outer"` | One of `"outer"`, `"left"`, `"inner"` |

### `OutputConfig`
Controls serialization format for `merged.csv`.

| Field | Type | Default | Validation Rules |
|-------|------|---------|------------------|
| `encoding` | `str` | `"utf-8"` | Non-empty valid Python codec name |
| `delimiter` | `str` | `","` | Exactly 1 character |

### `ColumnRule`
Defines one output column in exact output order, its source mappings, precedence, target type, and
optional lookup/format overrides.

| Field | Type | Default | Validation Rules |
|-------|------|---------|------------------|
| `name` | `str` | *(required)* | Non-empty; unique across `MappingConfig.columns` |
| `source_a` | `str \| None` | `None` | Required (non-empty) when `leading == "A"`; optional when `leading == "B"` |
| `source_b` | `str \| None` | `None` | Required (non-empty) when `leading == "B"`; optional when `leading == "A"` |
| `leading` | `SystemId` | `"A"` | Must be `"A"` or `"B"` |
| `type` | `TargetType` | `"str"` | Must be one of `"str"`, `"int"`, `"float"`, `"date"`, `"bool"` |
| `normalize` | `bool` | `False` | Marks column for template lookup CSV generation during `init` |
| `lookup` | `str \| None` | `None` | Optional path to 3-column lookup CSV (relative to `mapping.yaml` dir); required at `run` if `normalize` is `True` |
| `number_format_a` | `NumberFormat \| None` | `None` | Optional override for System A (`"auto"`, `"eu"`, `"us"`) |
| `number_format_b` | `NumberFormat \| None` | `None` | Optional override for System B (`"auto"`, `"eu"`, `"us"`) |
| `date_format_a` | `str \| None` | `None` | Optional override for System A date format |
| `date_format_b` | `str \| None` | `None` | Optional override for System B date format |

### `MappingConfig`
Root configuration object persisted as `mapping.yaml`.

| Field | Type | Default | Validation Rules |
|-------|------|---------|------------------|
| `version` | `int` | `1` | Must equal `1` |
| `source_a` | `SourceFileConfig` | *(required)* | Valid `SourceFileConfig` |
| `source_b` | `SourceFileConfig` | *(required)* | Valid `SourceFileConfig` |
| `join` | `JoinConfig` | *(required)* | Valid `JoinConfig` |
| `columns` | `tuple[ColumnRule, ...]` | *(required)* | Non-empty tuple; all `ColumnRule.name` unique |
| `output` | `OutputConfig` | `OutputConfig()` | Valid `OutputConfig` |

**Relationships**:
- `MappingConfig` has one `source_a: SourceFileConfig`, one `source_b: SourceFileConfig`, one
  `join: JoinConfig`, one `output: OutputConfig`, and an ordered sequence `columns` of `1..N`
  `ColumnRule` entries.
- Each `ColumnRule` optionally references one `LookupTable` via `lookup`.

---

## 2. Inspection Entities (`src/csv_merge/inspector.py`)

### `FileInspectionResult`
Captures auto-detected properties of an input CSV file during `csv-merge init`.

| Field | Type | Description |
|-------|------|-------------|
| `path` | `Path` | Input CSV path |
| `encoding` | `str` | Detected encoding (`utf-8-sig`, `utf-8`, `cp1252`, `latin-1`, `utf-16`) |
| `delimiter` | `str` | Detected single-character delimiter (`,`, `;`, `\t`, `|`) |
| `headers` | `tuple[str, ...]` | Ordered header names read from row 1 |
| `inferred_types` | `dict[str, TargetType]` | Inferred target type per header from sampled rows |
| `inferred_number_format` | `NumberFormat` | Inferred file-level numeric format (`eu`, `us`, `auto`) |
| `inferred_date_format` | `str` | Inferred file-level date format (`iso`, `eu`, `us`, `auto`) |
| `row_count_sampled` | `int` | Number of data rows inspected for type/format inference |

### `InitResult`
Summarizes files generated by `csv-merge init`.

| Field | Type | Description |
|-------|------|-------------|
| `config_path` | `Path` | Path to generated or read `mapping.yaml` |
| `config_written` | `bool` | `True` when `mapping.yaml` was created, overwritten, or updated with newly populated default `lookup` paths in `--update-lookups` mode; `False` when left untouched |
| `lookup_paths` | `tuple[Path, ...]` | Paths of generated 3-column template lookup CSVs |
| `inspection_a` | `FileInspectionResult` | Inspection metadata for File A |
| `inspection_b` | `FileInspectionResult` | Inspection metadata for File B |

---

## 3. Coercion & Lookup Entities (`src/csv_merge/coercion.py`)

### `LookupTable`
In-memory case-insensitive lookup index loaded from a 3-column CSV.

| Field | Type | Description |
|-------|------|-------------|
| `path` | `Path` | Resolved filesystem path of the lookup CSV |
| `map_a` | `dict[str, str]` | Mapping `source_a_value.strip().casefold() -> unified_value.strip()` |
| `map_b` | `dict[str, str]` | Mapping `source_b_value.strip().casefold() -> unified_value.strip()` |

**Validation Invariants**:
- Required header columns: `source_a_value`, `source_b_value`, `unified_value`.
- Within `map_a` (and independently within `map_b`), the same case-insensitive key MUST NOT map to
  two different non-empty `unified_value` values (raises `ConfigError`).
- An entry with a non-empty source key and empty `unified_value` is stored as `""`, signaling an
  unmapped value at runtime.

### `LookupResolution`
Result of resolving a single non-empty cell through a `LookupTable`.

| Field | Type | Description |
|-------|------|-------------|
| `value` | `str` | Unified value if mapped, or trimmed original raw value if unmapped |
| `mapped` | `bool` | `True` when mapped to a non-empty `unified_value`; `False` when unmapped |

### `CoercionResult`
Typed outcome of normalizing and coercing one system's cell for a `ColumnRule`.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `Literal["ok", "empty", "error"]` | Cell state after empty check, lookup, and type coercion |
| `value` | `str` | Canonical serialized output string when `status == "ok"`, else `""` |
| `error_message` | `str \| None` | Human-readable failure reason when `status == "error"` |

---

## 4. Merge & Reporting Entities (`src/csv_merge/merger.py`, `src/csv_merge/reporter.py`)

### `IndexedRow`
One deduplicated source CSV row retained in memory for joining.

| Field | Type | Description |
|-------|------|-------------|
| `row_number` | `int` | 1-based CSV record number (header = 1, first data row = 2) |
| `raw_id` | `str` | Original unmodified ID cell value |
| `normalized_id` | `str` | `raw_id.strip().upper()` |
| `values` | `dict[str, str]` | Referenced source column values only (unmapped columns pruned) |

### `ErrorCategory` (Literal Type Alias)
`ErrorCategory = Literal["duplicate_id", "missing_id", "type_conversion"]`

### `MergeError`
One row in `errors.csv`.

| Field | Type | Description |
|-------|------|-------------|
| `error_category` | `ErrorCategory` | `"duplicate_id"`, `"missing_id"`, or `"type_conversion"` |
| `system` | `SystemId` | `"A"` or `"B"` |
| `row_number` | `int` | 1-based CSV record number in the source file |
| `record_id` | `str` | Normalized record ID (empty string for `missing_id`) |
| `column` | `str` | Output column name (or configured ID column name for ID errors) |
| `raw_value` | `str` | Raw offending cell value |
| `target_type` | `str` | Target data type for `type_conversion`, else `""` |
| `message` | `str` | Clear diagnostic explanation |

### `UnmappedValueRecord`
One aggregated row in `unmapped_values.csv`.

| Field | Type | Description |
|-------|------|-------------|
| `system` | `SystemId` | `"A"` or `"B"` |
| `column` | `str` | Output column name |
| `raw_value` | `str` | Trimmed unrecognized raw value |
| `occurrence_count` | `int` | Number of times this `(system, column, raw_value)` occurred |
| `sample_record_id` | `str` | First normalized record ID where this unmapped value appeared |

### `ReconciliationSummary`
High-level run statistics displayed to stdout.

| Field | Type | Description |
|-------|------|-------------|
| `rows_read_a` | `int` | Total data rows read from File A (including missing/duplicate IDs) |
| `rows_read_b` | `int` | Total data rows read from File B (including missing/duplicate IDs) |
| `matched_count` | `int` | Count of unique normalized IDs present in both A and B |
| `only_a_count` | `int` | Count of unique normalized IDs present only in A |
| `only_b_count` | `int` | Count of unique normalized IDs present only in B |
| `output_row_count` | `int` | Total data rows written to `merged.csv` |
| `duplicate_id_count` | `int` | Total intra-file duplicate ID rows logged to `errors.csv` |
| `missing_id_count` | `int` | Total missing/blank ID rows logged to `errors.csv` |
| `unmapped_value_occurrences` | `int` | Total unmapped value occurrences across all cells |
| `unmapped_distinct_count` | `int` | Distinct `(system, column, raw_value)` rows written to `unmapped_values.csv` |
| `type_conversion_error_count` | `int` | Total failed type conversions logged to `errors.csv` |

### `MergeResult`
Complete output object produced by `merger.reconcile(...)` and consumed by `reporter`.

| Field | Type | Description |
|-------|------|-------------|
| `headers` | `tuple[str, ...]` | Exact ordered output headers from `MappingConfig.columns` |
| `rows` | `list[list[str]]` | Ordered merged output rows aligned with `headers` |
| `unmapped_values` | `list[UnmappedValueRecord]` | Sorted list of aggregated unmapped lookup values |
| `errors` | `list[MergeError]` | Ordered list of duplicate ID, missing ID, and type conversion errors |
| `summary` | `ReconciliationSummary` | Run counts and reconciliation totals |

## State Transitions (Per-Cell Resolution Pipeline)

```text
Source Cell (raw string)
  ├── [Empty / Whitespace / Configured Null Marker] ──► CoercionResult(status="empty", value="")
  └── [Non-Empty]
        │
        ▼ (if ColumnRule.lookup configured)
      Lookup Resolution (trimmed, case-insensitive)
        ├── [Mapped to non-empty unified_value] ──► candidate = unified_value
        └── [Not found or blank unified_value]  ──► record UnmappedValueRecord; candidate = raw.strip()
        │
        ▼
      Locale-Aware Type Coercion (str | int | float | date | bool)
        ├── [Valid]   ──► CoercionResult(status="ok", value=canonical_str)
        └── [Invalid] ──► record MergeError("type_conversion"); CoercionResult(status="error", value="")

Matched Record Resolution (Leading vs Secondary):
  - Leading == "ok"    ──► emit Leading.value
  - Leading == "error" ──► emit "" (no fallback to secondary; FR-018)
  - Leading == "empty" ──► emit Secondary.value if Secondary == "ok" else "" (FR-017)
```
