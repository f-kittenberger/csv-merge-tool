# Quickstart & Validation Guide: `csv-merge`

**Feature**: `001-csv-reconciliation-cli`
**Contracts**: [CLI Contract](contracts/cli-contract.md) | [Config Schema](contracts/config-schema.md) | [Data Model](data-model.md)

## Prerequisites

- Python 3.13 managed via `uv` (`uv --version`, `uv run python --version`).
- Dependencies installed via `uv sync` (after `src/csv_merge/` and `PyYAML` are configured in
  `pyproject.toml`).

## Quality Gates

Every change during implementation must pass:

```powershell
uv run ruff check .
uv run pytest
```

## End-to-End Validation Walkthrough

### Scenario 1: Bootstrap Starter Config & Lookup Template (`init`)

Given two heterogeneous synthetic CSV exports:
- `file_a.csv`: Windows-1252 or UTF-8-BOM, semicolon-delimited (`;`), European numbers (`1.250,50`),
  European dates (`23.11.2026`), German booleans (`Ja`/`Nein`), and categorical codes (`ACT`, `INA`).
- `file_b.csv`: UTF-8, comma-delimited (`,`), US numbers (`1250.50`), ISO dates (`2026-11-23`),
  English booleans (`true`/`false`), and categorical labels (`Active`, `Closed`).

Run:

```powershell
uv run csv-merge init --file-a file_a.csv --file-b file_b.csv --config work/mapping.yaml --normalize status
```

**Expected outcomes**:
- `work/mapping.yaml` is created with detected encodings, delimiters, regional format hints,
  starter `join`, and ordered `columns`.
- `work/lookups/status.csv` is created with exact headers
  `source_a_value,source_b_value,unified_value` containing all unique non-empty values from both
  files.
- Re-running the same command without `--force` exits `1` without overwriting user edits.

### Scenario 2: Reconcile, Normalize, Coerce & Merge (`run`)

After filling `unified_value` entries in `work/lookups/status.csv` and reviewing `work/mapping.yaml`
(column order, leading systems `A`/`B`, target types, join mode):

```powershell
uv run csv-merge run --file-a file_a.csv --file-b file_b.csv --config work/mapping.yaml --output out/merged.csv
```

**Expected outcomes**:
- `out/merged.csv` is created with exact column headers and ordering from `work/mapping.yaml`.
- IDs differing only in whitespace or letter casing match into a single output row.
- Matched rows take leading-system values and fill only empty/null leading cells from the secondary
  system.
- European and US numbers, dates, and booleans serialize in canonical target formats (`1250.5`,
  `2026-11-23`, `true`/`false`).
- `out/unmapped_values.csv` and `out/errors.csv` are written alongside `out/merged.csv` (headers
  only when clean, populated with full diagnostics when anomalies exist).
- `stdout` prints the reconciliation summary with input, match, output, duplicate, missing-ID,
  unmapped, and conversion-error counts.

### Scenario 3: Join Mode & Exception Verification

1. Re-run with `--join left` and `--join inner` and confirm row counts match `matched + only_a`
   (`left`) and `matched` (`inner`).
2. Introduce an intra-file duplicate normalized ID, a blank ID row, an unrecognized lookup value,
   and an invalid date cell; re-run `csv-merge run` and confirm:
   - First occurrence of the duplicate ID remains in `merged.csv`; duplicate row is logged in
     `errors.csv` (`duplicate_id`).
   - Blank ID row is excluded from `merged.csv` and logged in `errors.csv` (`missing_id`).
   - Unrecognized lookup value appears in `unmapped_values.csv` with occurrence count and sample
     record ID.
   - Failed date conversion is logged in `errors.csv` (`type_conversion`) and does not fall back to
     secondary data when on the leading system.
   - Reconciliation summary counts match diagnostic CSV totals exactly.
