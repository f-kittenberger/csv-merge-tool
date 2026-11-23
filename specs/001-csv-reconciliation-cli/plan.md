# Implementation Plan: Universal CSV Reconciliation and Merge CLI

**Branch**: `001-csv-reconciliation-cli` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-csv-reconciliation-cli/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Build the domain-agnostic `csv-merge` CLI in Python 3.13 using the standard library (`csv`,
`argparse`, `datetime`, `decimal`, `codecs`, `dataclasses`, `pathlib`) plus `PyYAML` (with no
heavy `pandas` dependency). The package under `src/csv_merge/` is structured into six focused
modules—`config.py`, `inspector.py`, `coercion.py`, `merger.py`, `reporter.py`, and `cli.py`—to
deliver `csv-merge init` (encoding/delimiter detection, header/type inference, starter
`mapping.yaml`, and 3-column lookup template CSV generation) and `csv-merge run` (trimmed
case-insensitive ID matching, `outer`/`left`/`inner` joins, case-insensitive lookup normalization,
European/US locale-aware type coercion, leading-system precedence with empty-field fallback, and
structured `merged.csv` / `unmapped_values.csv` / `errors.csv` / summary reporting).

## Technical Context

**Language/Version**: Python 3.13 (`>=3.13`, pinned via `.python-version`, managed exclusively by `uv`)

**Primary Dependencies**: Python 3.13 standard library (`csv`, `argparse`, `datetime`, `decimal`, `codecs`, `dataclasses`, `pathlib`, `re`) + `PyYAML>=6.0` (runtime); `pytest`, `ruff` (dev dependency group)

**Storage**: Local filesystem delimited CSV files and YAML configuration (`mapping.yaml`, 3-column lookup CSVs, `merged.csv`, `unmapped_values.csv`, `errors.csv`)

**Testing**: `uv run pytest` (unit tests per module + end-to-end CLI integration tests across multiple synthetic domains) and `uv run ruff check .`

**Target Platform**: Cross-platform CLI (Windows, Linux, macOS)

**Project Type**: CLI application & reusable Python package (`csv-merge = "csv_merge.cli:main"`)

**Performance Goals**: `csv-merge init` < 5s and `csv-merge run` < 15s for two 50,000-row CSV files on a standard workstation (`SC-001`, `SC-002`)

**Constraints**: Zero hardcoded domain column names/schemas/precedence rules; no heavy `pandas`/`numpy` dependencies; strict Python 3.13 type hints and dataclass models; deterministic UTF-8 canonical outputs; fail-fast validation before writing outputs

**Scale/Scope**: Batch reconciliation of two local CSV files up to ~50k–250k rows per file, 6 single-responsibility modules under `src/csv_merge/` and mirrored tests under `tests/`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design Status | Post-Design Status | Verification Notes |
|-----------|-------------------|--------------------|--------------------|
| **I. Configuration-Driven Domain Logic (NON-NEGOTIABLE)** | PASS | PASS | All column names, output ordering, target types, join keys, regional formats, lookup tables, and leading-system rules are driven strictly by `mapping.yaml` and referenced 3-column CSVs (`config.py`, [config-schema.md](contracts/config-schema.md)). Zero domain strings in `src/csv_merge/`. |
| **II. Strict Static Typing & Structured Models** | PASS | PASS | Frozen dataclasses (`MappingConfig`, `SourceFileConfig`, `JoinConfig`, `OutputConfig`, `ColumnRule`, `LookupTable`, `MergeError`, `UnmappedValueRecord`, `ReconciliationSummary`, `MergeResult`, `FileInspectionResult`) with strict type annotations across all modules and tests ([data-model.md](data-model.md)). |
| **III. Python 3.13 & Exclusive uv Toolchain** | PASS | PASS | Targets Python 3.13 (`requires-python = ">=3.13"`); `PyYAML` added via `uv add`; all lint/test/CLI invocations run via `uv run`. |
| **IV. Standardized Source & Test Layout** | PASS (scaffold alignment planned) | PASS | Replaces initial placeholder `src/csv_merge_tool/` with `src/csv_merge/`, sets `[tool.uv.build-backend] module-name = "csv_merge"` and `csv-merge = "csv_merge.cli:main"` in `pyproject.toml`, and establishes `tests/` mirroring `src/csv_merge/`. |
| **V. Mandatory Verification Gates (NON-NEGOTIABLE)** | PASS | PASS | Every implementation task verified with `uv run ruff check .` and `uv run pytest`, including unit coverage per module and multi-domain end-to-end CLI tests. |

**Gate Evaluation**: PASSED (both pre-design and post-design). Zero unjustified violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-csv-reconciliation-cli/
├── plan.md                      # This file (/speckit-plan command output)
├── research.md                  # Phase 0 output (/speckit-plan command)
├── data-model.md                # Phase 1 output (/speckit-plan command)
├── quickstart.md                # Phase 1 output (/speckit-plan command)
├── contracts/                   # Phase 1 output (/speckit-plan command)
│   ├── cli-contract.md          # CLI commands, flags, exit codes, output schemas
│   └── config-schema.md         # mapping.yaml & 3-column lookup CSV contracts
├── checklists/
│   └── requirements.md          # Specification quality checklist
└── tasks.md                     # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
pyproject.toml                   # Add PyYAML, [tool.uv.build-backend] module-name="csv_merge", csv-merge script
src/
└── csv_merge/
    ├── __init__.py              # Package metadata and public exports
    ├── config.py                # MappingConfig, SourceFileConfig, JoinConfig, OutputConfig, ColumnRule + YAML I/O & validation
    ├── inspector.py             # Encoding/delimiter sniffer, header/type inference, starter mapping.yaml & lookup CSV generator
    ├── coercion.py              # Locale-aware str/int/float/date/bool converters + case-insensitive 3-column lookup resolver
    ├── merger.py                # Trimmed uppercase ID normalization, duplicate/missing-ID detection, outer/left/inner join & precedence engine
    ├── reporter.py              # merged.csv, unmapped_values.csv, errors.csv writers & stdout reconciliation summary formatter
    └── cli.py                   # argparse CLI wiring `csv-merge init` and `csv-merge run` (entry point `main`)

tests/
├── __init__.py
├── test_config.py               # YAML load/save round-trip & strict schema validation error cases
├── test_inspector.py            # UTF-8-sig/UTF-8/cp1252 + delimiter sniffing, type inference, init & overwrite protection
├── test_coercion.py             # EU/US float & int, EU/US/ISO date, multilingual bool, case-insensitive lookup resolution
├── test_merger.py               # ID normalization, intra-file duplicates, blank IDs, outer/left/inner joins, leading/fallback rules
├── test_reporter.py             # Output CSV formatting, diagnostic headers/sorting, summary formatting
└── test_cli_e2e.py              # End-to-end `init` -> `run` workflows across two distinct synthetic domains
```

**Structure Decision**: Single-package Python `src/` layout strictly following Constitution
Principle IV (`src/csv_merge/` and `tests/`). Each module owns one clearly bounded stage of the
reconciliation pipeline (`config` -> `inspector` / `coercion` -> `merger` -> `reporter` -> `cli`),
keeping business logic testable in isolation without CLI subprocess overhead while `test_cli_e2e.py`
verifies the full `csv-merge` command contract end-to-end.

## Complexity Tracking

No constitution violations; no complexity exceptions required.
