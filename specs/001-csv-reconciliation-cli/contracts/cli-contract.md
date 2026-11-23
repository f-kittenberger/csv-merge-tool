# CLI Contract: `csv-merge`

**Feature**: `001-csv-reconciliation-cli`
**Entry Point**: `csv-merge = "csv_merge.cli:main"` in `pyproject.toml`

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Command succeeded. For `run`, data-level issues recorded in `unmapped_values.csv` / `errors.csv` still exit `0`. |
| `1` | Fatal runtime, filesystem, CSV header/encoding, configuration validation, or overwrite-protection error (message printed to `stderr`). |
| `2` | CLI syntax / argument parsing error (handled by `argparse`). |

---

## Command 1: `csv-merge init`

Inspects two input CSV files, detects encodings, delimiters, headers, and sample formats, and
generates a starter `mapping.yaml` plus 3-column template lookup CSVs for columns marked for value
normalization.

### Synopsis

```text
csv-merge init --file-a <PATH> --file-b <PATH>
               [--config <PATH>]
               [--lookups-dir <PATH>]
               [--normalize <COLUMN> ...]
               [--update-lookups]
               [--force]
```

### Arguments

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--file-a` | Yes | — | Path to System A input CSV file. |
| `--file-b` | Yes | — | Path to System B input CSV file. |
| `--config` | No | `mapping.yaml` | Output path for starter `mapping.yaml` (or existing config path when `--update-lookups` is set). |
| `--lookups-dir` | No | `lookups` | Directory (relative to `--config` parent if relative) where generated 3-column template lookup CSVs are written. |
| `--normalize` | No | `[]` | Repeatable (and comma-separated supported) column names to mark with `normalize: true` and generate template lookup CSVs for. |
| `--update-lookups` | No | `False` | Read existing `--config` and generate missing template lookup CSVs for all columns marked `normalize: true` or having a `lookup` path. Preserves all user edits in `--config`, writing back only newly defaulted `lookup` paths for columns where `normalize: true` had no `lookup` set. |
| `--force` | No | `False` | Allow overwriting existing `mapping.yaml` and/or existing template lookup CSV files. |

### Behavior & Output

- Validates `--file-a` and `--file-b` exist, are non-empty, and parse with valid headers.
- Refuses to overwrite existing `mapping.yaml` (without `--force` and without `--update-lookups`)
  or existing lookup CSVs (without `--force`), exiting with status `1` and an actionable message.
- Writes `mapping.yaml` with `version: 1`, detected `source_a`/`source_b` profiles, starter `join`,
  `output`, and `columns`.
- For each marked normalization column, writes `<lookup_path>` in UTF-8 with exact header:
  ```csv
  source_a_value,source_b_value,unified_value
  ```
- Prints a concise summary to `stdout` listing detected encodings/delimiters and paths of created
  files.

---

## Command 2: `csv-merge run`

Executes validated reconciliation, lookup normalization, type coercion, joining, precedence merging,
and diagnostic reporting.

### Synopsis

```text
csv-merge run --file-a <PATH> --file-b <PATH>
              --config <PATH>
              --output <PATH>
              [--join {outer,left,inner}]
              [--unmapped-output <PATH>]
              [--errors-output <PATH>]
```

### Arguments

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--file-a` | Yes | — | Path to System A input CSV file. |
| `--file-b` | Yes | — | Path to System B input CSV file. |
| `--config` | Yes | — | Path to `mapping.yaml`. |
| `--output` | Yes | — | Destination path for `merged.csv`. Parent directories are created automatically. |
| `--join` | No | *(from config, default `outer`)* | Optional CLI override for join mode (`outer`, `left`, `inner`). |
| `--unmapped-output` | No | `<output_dir>/unmapped_values.csv` | Destination path for unrecognized lookup values report. |
| `--errors-output` | No | `<output_dir>/errors.csv` | Destination path for row/field error report. |

### Output Artifacts

1. **`merged.csv`** (`--output`):
   - Encoding & delimiter from `config.output` (default UTF-8 without BOM, comma delimiter, `\n`
     line endings).
   - Header row equals exact `[col.name for col in config.columns]` in exact config order.
   - Canonical cell values: `str` (leading/trailing whitespace trimmed, original letter casing preserved), `int` (base-10 digits), `float` (period
     decimal, no thousands separators, no scientific notation), `date` (`YYYY-MM-DD`), `bool`
     (`true`/`false`), empty (`""`).
2. **`unmapped_values.csv`** (`--unmapped-output`, always written even when empty):
   - Exact header: `system,column,raw_value,occurrence_count,sample_record_id`
   - Rows sorted deterministically by `(system, column, raw_value)`.
3. **`errors.csv`** (`--errors-output`, always written even when empty):
   - Exact header: `error_category,system,row_number,record_id,column,raw_value,target_type,message`
   - `error_category` values: `duplicate_id`, `missing_id`, `type_conversion`.
4. **Reconciliation Summary** (`stdout`):
   - Human-readable summary printing:
     - Join mode
     - Input rows read (System A, System B)
     - Matched, A-only, B-only, and Output rows written
     - Duplicate IDs, Missing IDs, Unmapped lookup occurrences (and distinct count), Type
       conversion errors
     - Output file paths (`merged.csv`, `unmapped_values.csv`, `errors.csv`)
