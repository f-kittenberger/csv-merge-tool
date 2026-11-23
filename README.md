# csv-merge

Universal, configuration-driven CSV reconciliation and merge CLI built with Python 3.13 (`csv`, `argparse`, `datetime`, `decimal`, `PyYAML`). Zero domain-specific column names, types, or precedence rules are hardcoded—everything is governed by `mapping.yaml` and optional 3-column lookup CSVs.

## Setup (`uv`)

Requires Python 3.13 managed exclusively by [`uv`](https://docs.astral.sh/uv/):

```powershell
uv sync
```

Verify the CLI is installed:

```powershell
uv run csv-merge --help
```

## Usage

### 1. Bootstrap configuration & lookup templates (`init`)

Inspects two heterogeneous CSV files, auto-detects character encodings (`utf-8`, `utf-8-sig`, `cp1252`, `latin-1`) and delimiters (`,`, `;`, `\t`, `|`), infers column types and regional formats, and writes a starter `mapping.yaml` plus 3-column lookup template CSVs (`source_a_value,source_b_value,unified_value`) for any columns marked for normalization:

```powershell
uv run csv-merge init --file-a system_a.csv --file-b system_b.csv --config mapping.yaml --normalize status
```

To add lookup templates later after editing `mapping.yaml` (e.g., setting `normalize: true` on another column):

```powershell
uv run csv-merge init --file-a system_a.csv --file-b system_b.csv --config mapping.yaml --update-lookups
```

Use `--force` to allow overwriting an existing `mapping.yaml` or existing lookup CSVs.

### 2. Reconcile & merge (`run`)

```powershell
uv run csv-merge run --file-a system_a.csv --file-b system_b.csv --config mapping.yaml --output merged.csv
```

Optional overrides:
- `--join {outer,left,inner}`: Override join mode (defaults to `mapping.yaml`, which defaults to `outer`).
- `--unmapped-output <path>`: Custom path for `unmapped_values.csv` (defaults to `<output_dir>/unmapped_values.csv`).
- `--errors-output <path>`: Custom path for `errors.csv` (defaults to `<output_dir>/errors.csv`).

### Behavior Summary

- **Record matching**: Joins on the configured ID column pair normalized as trimmed uppercase strings; retains first occurrence on intra-file duplicate IDs and logs subsequent duplicates and blank IDs to `errors.csv`.
- **Lookup normalization**: Applies case-insensitive, trimmed 3-column lookup CSVs (`source_a_value,source_b_value,unified_value`) before merging and type coercion. Unrecognized values are logged to `unmapped_values.csv` and retained as trimmed raw values.
- **Type coercion & precedence**: Enforces exact output column order and target types (`str`, `int`, `float`, `date`, `bool`), converting European (`1.250,50`, `23.11.2026`, `Ja`/`Nein`) and US/ISO (`1,250.50`, `11/23/2026`, `2026-11-23`, `true`/`false`) inputs to canonical outputs. Matched cells take the leading system (`A` or `B`) and fill only empty/null cells from the secondary system.

## Quality Gates

```powershell
uv run ruff check .
uv run pytest
```
