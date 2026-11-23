---

description: "Task list for Universal CSV Reconciliation and Merge CLI (001-csv-reconciliation-cli)"
---

# Tasks: Universal CSV Reconciliation and Merge CLI

**Input**: Design documents from `/specs/001-csv-reconciliation-cli/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/cli-contract.md`, `contracts/config-schema.md`, `quickstart.md`

**Tests**: Included per Constitution Principle V (NON-NEGOTIABLE: every new feature, configuration rule, or bug fix MUST include unit tests under `tests/`, and every change MUST pass `uv run ruff check .` and `uv run pytest`).

**Organization**: Tasks are grouped by user story (`US1`–`US5`) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`, `US4`, `US5`)
- Exact file paths are included in every task description
- Field constraints are cited directly to `data-model.md` (`Entity.field`) without duplicating canonical constraint prose

## Path Conventions

- Application source package: `src/csv_merge/`
- Unit and end-to-end tests: `tests/`
- Packaging & tooling config: `pyproject.toml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Align project packaging, `uv_build` module layout, dependencies, and design doc consistency with the ratified constitution.

- [X] T001 Add runtime dependency `PyYAML>=6.0` (via `uv add pyyaml`), configure `[tool.uv.build-backend]` with `module-name = "csv_merge"` and `module-root = "src"`, register `csv-merge = "csv_merge.cli:main"` under `[project.scripts]`, and configure `[tool.ruff]` for Python 3.13 in `pyproject.toml`
- [X] T002 Replace placeholder `src/csv_merge_tool/` with `src/csv_merge/__init__.py` and create `tests/__init__.py`, then sync the editable package via `uv sync`
- [x] T003 [P] Align `Strings (str)` serialization notes with `spec.md` clarification Q4 (`FR-022`: trim leading/trailing whitespace while preserving original letter casing) in `specs/001-csv-reconciliation-cli/research.md` and `specs/001-csv-reconciliation-cli/contracts/cli-contract.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core configuration dataclasses, strict YAML validation, shared error hierarchy, and CLI subcommand routing required before any user story can execute.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Define exception hierarchy (`CsvMergeError`, `ConfigError`, `InputFileError`), literal type aliases (`SystemId`, `JoinMode`, `TargetType`, `NumberFormat`), and frozen dataclasses enforcing canonical field definitions from `specs/001-csv-reconciliation-cli/data-model.md` for `SourceFileConfig` (`SourceFileConfig.encoding`, `SourceFileConfig.delimiter`, `SourceFileConfig.number_format`, `SourceFileConfig.date_format`, `SourceFileConfig.null_values`), `JoinConfig` (`JoinConfig.column_a`, `JoinConfig.column_b`, `JoinConfig.mode`), `OutputConfig` (`OutputConfig.encoding`, `OutputConfig.delimiter`), `ColumnRule` (`ColumnRule.name`, `ColumnRule.source_a`, `ColumnRule.source_b`, `ColumnRule.leading`, `ColumnRule.type`, `ColumnRule.normalize`, `ColumnRule.lookup`, `ColumnRule.number_format_a`, `ColumnRule.number_format_b`, `ColumnRule.date_format_a`, `ColumnRule.date_format_b`), and `MappingConfig` (`MappingConfig.version`, `MappingConfig.source_a`, `MappingConfig.source_b`, `MappingConfig.join`, `MappingConfig.columns`, `MappingConfig.output`) in `src/csv_merge/config.py`
- [X] T005 Implement strictly typed `load_config(...)`, `save_config(...)`, and `resolve_lookup_path(...)` using `yaml.safe_load` / `yaml.safe_dump` enforcing fail-fast schema rules from `specs/001-csv-reconciliation-cli/contracts/config-schema.md` in `src/csv_merge/config.py`
- [X] T006 [P] Implement `argparse` CLI router (`build_parser()`, `main(argv=None) -> int`, subcommand dispatchers, and `CsvMergeError` -> `stderr` exit code `1` handling) per `specs/001-csv-reconciliation-cli/contracts/cli-contract.md` in `src/csv_merge/cli.py` and package exports in `src/csv_merge/__init__.py`
- [X] T007 [P] Write unit tests for `MappingConfig` YAML load/save round-trip, relative lookup path resolution, and fail-fast schema validation error cases in `tests/test_config.py`

**Checkpoint**: Foundation ready — `uv run ruff check .` and `uv run pytest tests/test_config.py` pass; user story phases can now proceed.

---

## Phase 3: User Story 1 - Bootstrap Configuration and Lookup Templates (`init`) (Priority: P1) 🎯 MVP

**Goal**: Enable `csv-merge init --file-a <path> --file-b <path>` to auto-detect encodings and delimiters, inspect headers and sample values, infer formats and target types, and generate starter `mapping.yaml` plus 3-column template lookup CSVs (`source_a_value,source_b_value,unified_value`) with overwrite safety.

**Independent Test**: Run `csv-merge init` against fixture CSVs with differing encodings (`utf-8`, `utf-8-sig`, `cp1252`) and delimiters (`,`, `;`, `\t`, `|`) and marked normalization columns; verify `mapping.yaml` contents, 3-column lookup CSV pairing, `--update-lookups` mode, overwrite protection without `--force`, and failure on missing/0-byte files.

### Implementation for User Story 1

- [X] T008 [US1] Define frozen dataclasses enforcing canonical definitions from `specs/001-csv-reconciliation-cli/data-model.md` for `FileInspectionResult` (`FileInspectionResult.path`, `FileInspectionResult.encoding`, `FileInspectionResult.delimiter`, `FileInspectionResult.headers`, `FileInspectionResult.inferred_types`, `FileInspectionResult.inferred_number_format`, `FileInspectionResult.inferred_date_format`, `FileInspectionResult.row_count_sampled`) and `InitResult` (`InitResult.config_path`, `InitResult.config_written`, `InitResult.lookup_paths`, `InitResult.inspection_a`, `InitResult.inspection_b`) in `src/csv_merge/inspector.py`
- [X] T009 [US1] Implement `detect_encoding(path: Path) -> str` (BOM detection for `utf-8-sig`/`utf-16`, incremental 64 KiB `utf-8` decode, `cp1252`/`latin-1` fallback) and `detect_delimiter(path: Path, encoding: str) -> str` (`csv.Sniffer` validated by consistent column count with fallback across `,`, `;`, `\t`, `|`) in `src/csv_merge/inspector.py`
- [X] T010 [US1] Implement `inspect_csv_file(path: Path, max_sample_rows: int = 1000) -> FileInspectionResult` (validating non-empty files with headers, inferring file-level `number_format` and `date_format`, and inferring column target types in `int -> bool -> float -> date -> str` order) in `src/csv_merge/inspector.py`
- [X] T011 [US1] Implement starter `MappingConfig` generation (normalized header pairing, A-only/B-only ordering, starter `JoinConfig`, `--normalize` marking), 3-column lookup template CSV generation (`source_a_value,source_b_value,unified_value` pairing case-insensitive matches with leading-system `unified_value` pre-fill and leaving unmatched rows blank for review), and `run_init(...) -> InitResult` with overwrite protection (`--force`) and existing-config `--update-lookups` mode (populating missing default `lookup` paths back into `mapping.yaml` while preserving all other user settings) in `src/csv_merge/inspector.py`
- [X] T012 [US1] Wire `csv-merge init` flags (`--file-a`, `--file-b`, `--config`, `--lookups-dir`, `--normalize`, `--update-lookups`, `--force`) to `run_init(...)` and print the concise `init` summary to `stdout` per `specs/001-csv-reconciliation-cli/contracts/cli-contract.md` in `src/csv_merge/cli.py`
- [X] T013 [P] [US1] Write unit and CLI tests covering encoding/delimiter sniffing, header/type/regional inference, starter `mapping.yaml` generation, 3-column lookup template pairing, `--update-lookups`, overwrite protection, and missing/0-byte file failures in `tests/test_inspector.py`

**Checkpoint**: User Story 1 (`csv-merge init`) is independently functional and passes `uv run ruff check .` and `uv run pytest tests/test_config.py tests/test_inspector.py`.

---

## Phase 4: User Story 2 - Record Matching, Join Modes, and Precedence Merge (`run`) (Priority: P1)

**Goal**: Enable `csv-merge run` to validate CSV headers, match records by trimmed uppercase normalized IDs across `outer` (default), `left`, and `inner` joins in deterministic order, detect intra-file duplicate and blank IDs, enforce exact output column order, and apply leading-system precedence with empty-field fallback.

**Independent Test**: Run `csv-merge run` on fixture CSVs containing case/whitespace ID variations, matched/A-only/B-only rows, intra-file duplicate IDs, blank IDs, single-system columns, and mixed `A`/`B` leading columns across `outer`, `left`, and `inner` modes; verify `merged.csv` headers, row ordering, trimmed `str` values with preserved casing, and fallback precedence.

### Implementation for User Story 2

- [X] T014 [US2] Define `ErrorCategory` and frozen dataclasses enforcing canonical definitions from `specs/001-csv-reconciliation-cli/data-model.md` for `IndexedRow` (`IndexedRow.row_number`, `IndexedRow.raw_id`, `IndexedRow.normalized_id`, `IndexedRow.values`), `MergeError` (`MergeError.error_category`, `MergeError.system`, `MergeError.row_number`, `MergeError.record_id`, `MergeError.column`, `MergeError.raw_value`, `MergeError.target_type`, `MergeError.message`), `UnmappedValueRecord` (`UnmappedValueRecord.system`, `UnmappedValueRecord.column`, `UnmappedValueRecord.raw_value`, `UnmappedValueRecord.occurrence_count`, `UnmappedValueRecord.sample_record_id`), `ReconciliationSummary` (`ReconciliationSummary.rows_read_a`, `ReconciliationSummary.rows_read_b`, `ReconciliationSummary.matched_count`, `ReconciliationSummary.only_a_count`, `ReconciliationSummary.only_b_count`, `ReconciliationSummary.output_row_count`, `ReconciliationSummary.duplicate_id_count`, `ReconciliationSummary.missing_id_count`, `ReconciliationSummary.unmapped_value_occurrences`, `ReconciliationSummary.unmapped_distinct_count`, `ReconciliationSummary.type_conversion_error_count`), and `MergeResult` (`MergeResult.headers`, `MergeResult.rows`, `MergeResult.unmapped_values`, `MergeResult.errors`, `MergeResult.summary`) in `src/csv_merge/merger.py`
- [X] T015 [US2] Implement source CSV header validation (fail fast on 0-byte/headerless files, missing configured columns, or duplicate referenced headers), `normalize_id(raw: str) -> str` (`raw.strip().upper()`), and streaming row indexing (pruning unmapped columns, excluding blank/null ID rows with `missing_id` errors, and retaining first occurrence on intra-file duplicate IDs while logging subsequent duplicates as `duplicate_id` errors per `FR-020`/`FR-021`) in `src/csv_merge/merger.py`
- [X] T016 [US2] Implement the `outer`/`left`/`inner` join engine (System A input order followed by B-only input order), empty/null detection (`SourceFileConfig.null_values` + empty/whitespace), exact `MappingConfig.columns` output ordering, single-system column support, trimmed `str` output preserving original casing (`FR-022`), and leading-system precedence with empty-field secondary fallback (`FR-017`) in `src/csv_merge/merger.py`
- [X] T017 [US2] Implement `write_merged_csv(...)` (auto-creating parent directories, UTF-8 / configured `OutputConfig` encoding and delimiter, `\n` line endings) in `src/csv_merge/reporter.py` and wire core `csv-merge run` flags (`--file-a`, `--file-b`, `--config`, `--output`, `--join`) in `src/csv_merge/cli.py`
- [X] T018 [P] [US2] Write unit tests for ID normalization, header validation failures, header-only inputs, intra-file duplicate first-occurrence retention, blank ID exclusion, `outer`/`left`/`inner` join order, exact output column ordering, single-system columns, trimmed `str` casing preservation, and leading/secondary fallback precedence in `tests/test_merger.py`

**Checkpoint**: User Stories 1 and 2 are independently functional and pass `uv run ruff check .` and `uv run pytest`.

---

## Phase 5: User Story 3 - Target Type Enforcement and European/US Format Coercion (Priority: P2)

**Goal**: Parse and coerce both leading and secondary values into canonical `str`, `int`, `float`, `date`, and `bool` output representations supporting European and US number/date conventions via `decimal.Decimal` and `datetime.date`, logging failed conversions without silently substituting secondary data when the leading system fails (`FR-018`).

**Independent Test**: Run `tests/test_coercion.py` and `csv-merge run` against fixture CSVs combining EU (`1.250,50`, `23.11.2026`, `Ja`/`Nein`) and US/ISO (`1,250.50`, `11/23/2026`, `2026-11-23`, `true`/`false`) formats across all 5 target types, ambiguous regional values, and malformed leading-system values.

### Implementation for User Story 3

- [X] T019 [US3] Define `CoercionResult` enforcing canonical definitions from `specs/001-csv-reconciliation-cli/data-model.md` (`CoercionResult.status`, `CoercionResult.value`, `CoercionResult.error_message`) and implement `is_empty_value(...)`, `parse_decimal(...)`, `coerce_int(...)`, `coerce_float(...)`, `coerce_date(...)`, `coerce_bool(...)`, `coerce_str(...)` (trimming leading/trailing whitespace while preserving original letter casing per `FR-022`), and `coerce_value(...) -> CoercionResult` in `src/csv_merge/coercion.py`
- [X] T020 [US3] Integrate `coerce_value(...)` into `src/csv_merge/merger.py` for every included row and `ColumnRule` (resolving column-level `number_format_a`/`number_format_b` and `date_format_a`/`date_format_b` overrides over `SourceFileConfig`, evaluating both present sides to log all `type_conversion` errors, and enforcing `FR-018` so leading `"error"` emits `""` without falling back to secondary)
- [X] T021 [P] [US3] Reuse `coercion.py` locale-aware parsers inside `inspect_csv_file(...)` type and regional format inference in `src/csv_merge/inspector.py` so `init` inference and `run` coercion stay aligned
- [X] T022 [P] [US3] Write comprehensive unit tests in `tests/test_coercion.py` covering `str` trimming/casing, `int` (EU/US thousands, whole decimals, fractional rejection), `float` (`1.250,50`, `1,250.50`, `1250.50`, `1 250,50`, `-0`, large numbers without scientific notation, ambiguous `1,234` under `auto` vs `eu`), `date` (`DD.MM.YYYY`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`, custom `%` patterns, ambiguous `03/04/2026` under `auto`/`eu`/`us`), and `bool` (`true`/`false`/`yes`/`no`/`y`/`n`/`1`/`0`/`ja`/`nein`/`wahr`/`falsch`), and add leading-system conversion-error non-fallback (`FR-018`) tests in `tests/test_merger.py`

**Checkpoint**: User Stories 1–3 pass `uv run ruff check .` and `uv run pytest`.

---

## Phase 6: User Story 4 - Case-Insensitive Value Normalization via Lookup Tables (Priority: P2)

**Goal**: Load and strictly validate 3-column lookup CSVs (`source_a_value,source_b_value,unified_value`) resolved relative to `mapping.yaml`, apply trimmed case-insensitive normalization before merging and type coercion, and retain trimmed raw values while aggregating unmapped occurrences (`FR-015`, `FR-016`, `FR-019`).

**Independent Test**: Configure 3-column lookup CSVs mapping distinct System A and System B codes (including mixed casing, whitespace padding, blank `unified_value` rows, and typed unified outputs such as `"true"` / `"1"`), run `csv-merge run`, and verify lookup translation runs before type coercion while conflicting/malformed lookup files fail fast.

### Implementation for User Story 4

- [X] T023 [US4] Define frozen dataclasses enforcing canonical definitions from `specs/001-csv-reconciliation-cli/data-model.md` for `LookupTable` (`LookupTable.path`, `LookupTable.map_a`, `LookupTable.map_b`) and `LookupResolution` (`LookupResolution.value`, `LookupResolution.mapped`), implement `load_lookup_table(path: Path) -> LookupTable` (validating required headers `source_a_value,source_b_value,unified_value`, encoding fallback, and conflicting non-empty `unified_value` detection raising `ConfigError` per `specs/001-csv-reconciliation-cli/contracts/config-schema.md`), and implement `resolve_lookup(table: LookupTable, system: SystemId, raw_value: str) -> LookupResolution` in `src/csv_merge/coercion.py`
- [X] T024 [US4] Preload all configured lookup tables in `src/csv_merge/merger.py` (resolving relative paths via `resolve_lookup_path(config_path, rule.lookup)` and requiring `rule.lookup` when `rule.normalize` is `True`), apply `resolve_lookup(...)` prior to `coerce_value(...)` on both present sides of every included row, aggregate unmapped occurrences `(system, column, raw_value)` with counts and `sample_record_id`, and retain trimmed raw values (`FR-019`)
- [X] T025 [US4] Add unit tests covering 3-column lookup loading, missing/bad-header/conflicting-mapping validation errors, case-insensitive/trimmed matching, blank `unified_value` unmapped retention, relative lookup path resolution, and lookup-before-coercion pipelines in `tests/test_coercion.py` and `tests/test_merger.py`

**Checkpoint**: User Stories 1–4 pass `uv run ruff check .` and `uv run pytest`.

---

## Phase 7: User Story 5 - Reconciliation Summary and Diagnostic Reporting (Priority: P3)

**Goal**: Write `unmapped_values.csv` and `errors.csv` alongside `merged.csv` on every run (header-only when clean), print the structured reconciliation summary to `stdout`, and enforce CLI exit code contracts (`0` on completed run including data anomalies, `1` on fatal errors).

**Independent Test**: Run `csv-merge run` on both clean fixtures and anomaly-rich fixtures (unmapped lookup values, intra-file duplicate IDs, blank IDs, invalid dates/numbers); verify exact diagnostic headers, deterministic sorting, exact match between reconciliation summary counts and diagnostic CSV totals, and exit codes `0` vs `1`.

### Implementation for User Story 5

- [X] T026 [US5] Implement `write_unmapped_values_csv(...)` (exact header `system,column,raw_value,occurrence_count,sample_record_id`, deterministically sorted), `write_errors_csv(...)` (exact header `error_category,system,row_number,record_id,column,raw_value,target_type,message`), `write_all_reports(...)`, and `format_reconciliation_summary(...)` per `specs/001-csv-reconciliation-cli/contracts/cli-contract.md` in `src/csv_merge/reporter.py`
- [X] T027 [US5] Wire `--unmapped-output` and `--errors-output` flags (defaulting to `<output_dir>/unmapped_values.csv` and `<output_dir>/errors.csv`), call `write_all_reports(...)`, print the reconciliation summary to `stdout`, and return exit code `0` on completed runs (`FR-025`) in `src/csv_merge/cli.py`
- [X] T028 [P] [US5] Write unit tests for `merged.csv` formatting, header-only vs populated `unmapped_values.csv` sorting, `errors.csv` rows across all 3 `ErrorCategory` values, parent directory creation, and reconciliation summary output in `tests/test_reporter.py`

**Checkpoint**: All 5 user stories (`US1`–`US5`) are independently complete and pass `uv run ruff check .` and `uv run pytest`.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Multi-domain end-to-end CLI verification, scale/performance validation, documentation, and final quality gate sign-off.

- [X] T029 Write end-to-end CLI integration tests in `tests/test_cli_e2e.py` covering full `csv-merge init` -> lookup edit -> `csv-merge run` workflows across two completely distinct synthetic domains (`SC-003`), quoted embedded-delimiter/multiline fields, relative lookup paths executed from a different working directory, all join modes (`outer`/`left`/`inner`), anomaly reporting (`SC-004`), and exit codes `0`/`1`/`2` (`FR-025`)
- [X] T030 Add a 50,000-row-per-file scale/performance verification test in `tests/test_cli_e2e.py` confirming `init` (`SC-001` < 5s) and `run` (`SC-002` < 15s) complete within latency budgets
- [X] T031 [P] Document `uv`-only setup, `csv-merge init` / `csv-merge run` CLI usage, `mapping.yaml` overview, and test/lint commands in `README.md`
- [X] T032 Validate end-to-end scenarios from `specs/001-csv-reconciliation-cli/quickstart.md` via `uv run csv-merge`, audit `src/csv_merge/` for zero hardcoded domain column names and strict type hints, and confirm `uv run ruff check .` and `uv run pytest` exit `0`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — starts immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — BLOCKS all user stories (`US1`–`US5`).
- **Phase 3 (US1 - `init`)**: Depends on Phase 2. Independently testable MVP increment.
- **Phase 4 (US2 - Core `run` merge)**: Depends on Phase 2. Independent of US1 (can proceed after Phase 2 or in parallel with US1 except shared `cli.py` wiring).
- **Phase 5 (US3 - Type Coercion)**: Depends on Phase 4 (`merger.py` integration) and optionally updates `inspector.py` (`T021`) after US1 (`T010`).
- **Phase 6 (US4 - Value Lookup Tables)**: Depends on Phase 5 (`coercion.py` + `merger.py` per-cell pipeline order: lookup -> coercion -> precedence).
- **Phase 7 (US5 - Diagnostic Reporting & Summary)**: Depends on Phase 4 (`reporter.py` + `MergeResult`) and integrates all anomaly sources from US2–US4.
- **Phase 8 (Polish)**: Depends on Phases 3–7 completion.

### Parallel Opportunities

- **Phase 1**: `T003` [P] can run in parallel with `T001`–`T002`.
- **Phase 2**: Once `T005` completes, `T006` [P] (`cli.py` + `__init__.py`) and `T007` [P] (`tests/test_config.py`) run in parallel.
- **Phase 3 (US1)**: Once `T011` completes, `T012` (`cli.py`) and `T013` [P] (`tests/test_inspector.py`) run in parallel.
- **Phase 4 (US2)**: Once `T016` completes, `T017` (`reporter.py` + `cli.py`) and `T018` [P] (`tests/test_merger.py`) run in parallel.
- **Phase 5 (US3)**: Once `T020` completes, `T021` [P] (`inspector.py`) and `T022` [P] (`tests/test_coercion.py` + `tests/test_merger.py`) run in parallel.
- **Phase 6 (US4)**: Once `T024` completes, `T025` (`tests/test_coercion.py` + `tests/test_merger.py`) validates lookup behavior immediately.
- **Phase 7 (US5)**: Once `T026` completes, `T027` (`cli.py`) and `T028` [P] (`tests/test_reporter.py`) run in parallel.
- **Phase 8 (Polish)**: `T031` [P] (`README.md`) can run in parallel with `T029`–`T030` (`tests/test_cli_e2e.py`).

---

## Parallel Examples

### Phase 2 (Foundational)

```text
# After T005 finishes in src/csv_merge/config.py:
Task T006 [P]: Implement argparse CLI router in src/csv_merge/cli.py and src/csv_merge/__init__.py
Task T007 [P]: Write config unit tests in tests/test_config.py
```

### Phase 5 (User Story 3)

```text
# After T020 integrates coercion into src/csv_merge/merger.py:
Task T021 [P] [US3]: Reuse coercion.py parsers in src/csv_merge/inspector.py
Task T022 [P] [US3]: Write coercion and non-fallback unit tests in tests/test_coercion.py and tests/test_merger.py
```

---

## Implementation Strategy

### MVP First (Phase 1 + Phase 2 + User Story 1, or Core CLI MVP = US1 + US2)

1. Complete **Phase 1 (Setup)** and **Phase 2 (Foundational)** to align `src/csv_merge/`, `PyYAML`, and typed `MappingConfig` validation.
2. Complete **Phase 3 (US1 - `init`)** — independently usable bootstrap CLI generating `mapping.yaml` and template 3-column lookup CSVs.
3. Complete **Phase 4 (US2 - core `run`)** — end-to-end two-file reconciliation with ID matching, join modes, exact column ordering, and leading-system precedence.
4. Layer on **Phase 5 (US3 - EU/US type coercion)**, **Phase 6 (US4 - lookup tables)**, **Phase 7 (US5 - full diagnostic CSVs & summary)**, and **Phase 8 (Polish & multi-domain E2E + 50k-row validation)**.

### Verification Discipline

- Run `uv run ruff check .` and `uv run pytest` at every phase checkpoint.
- Keep `src/csv_merge/` 100% domain-agnostic (Constitution Principle I) with strict Python 3.13 type hints (Principle II).
