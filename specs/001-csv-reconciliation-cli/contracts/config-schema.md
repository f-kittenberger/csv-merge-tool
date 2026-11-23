# Configuration & Lookup File Schema Contract

**Feature**: `001-csv-reconciliation-cli`

## 1. `mapping.yaml` Schema

All column names shown below are illustrative examples only; the tool enforces zero hardcoded
domain column names.

```yaml
version: 1
source_a:
  encoding: utf-8-sig
  delimiter: ";"
  number_format: eu        # auto | eu | us
  date_format: eu          # auto | iso | eu | us | <strftime pattern>
  null_values: []          # optional list of extra null markers
source_b:
  encoding: utf-8
  delimiter: ","
  number_format: us        # auto | eu | us
  date_format: iso         # auto | iso | eu | us | <strftime pattern>
  null_values: []
join:
  column_a: key_a          # header name in File A
  column_b: key_b          # header name in File B
  mode: outer              # outer | left | inner (default: outer)
output:
  encoding: utf-8
  delimiter: ","
columns:
  - name: record_key
    source_a: key_a
    source_b: key_b
    leading: A             # A | B
    type: str              # str | int | float | date | bool
  - name: status
    source_a: status_a
    source_b: status_b
    leading: A
    type: str
    normalize: true
    lookup: lookups/status.csv
  - name: metric_amount
    source_a: amount_a
    source_b: amount_b
    leading: A
    type: float
    number_format_a: eu    # optional per-column override
    number_format_b: us    # optional per-column override
  - name: effective_date
    source_a: date_a
    source_b: date_b
    leading: B
    type: date
    date_format_a: eu      # optional per-column override
    date_format_b: iso     # optional per-column override
  - name: active_flag
    source_a: flag_a
    source_b: flag_b
    leading: A
    type: bool
```

### Validation Rules (Fail-Fast on Load)

1. Root YAML document MUST be a mapping; `version` (if present) MUST equal `1`.
2. `source_a` and `source_b` encodings MUST be valid codec names; delimiters MUST be single
   characters; `number_format` MUST be in `{"auto", "eu", "us"}`; `date_format` MUST be in
   `{"auto", "iso", "eu", "us"}` or contain `"%"`.
3. `join.column_a` and `join.column_b` MUST be non-empty strings; `join.mode` (default `"outer"`)
   MUST be in `{"outer", "left", "inner"}`.
4. `columns` MUST be a non-empty list of mappings with unique, non-empty `name` values.
5. Each column's `leading` MUST be `"A"` or `"B"` and `type` MUST be in
   `{"str", "int", "float", "date", "bool"}`.
6. The leading system's source column (`source_a` when `leading == "A"`, `source_b` when
   `leading == "B"`) MUST be non-empty. The secondary source column may be omitted or `null` for
   single-system columns.
7. If `normalize: true` is set on a column during `run`, `lookup` MUST specify a non-empty path.
8. Relative `lookup` paths MUST resolve relative to the directory containing `mapping.yaml`.
9. Before reading data rows during `run`, all referenced `join` and `columns` source headers MUST
   exist in their respective CSV files and MUST NOT be ambiguous duplicate headers in those files.

## 2. 3-Column Value Lookup CSV Contract

### Header (Required Exact Names)

```csv
source_a_value,source_b_value,unified_value
```

### Semantics

- Matching uses `value.strip().casefold()` against `source_a_value` for System A cells and against
  `source_b_value` for System B cells.
- A row may populate both `source_a_value` and `source_b_value` (shared mapping to `unified_value`),
  or only one of them (system-specific mapping).
- Conflicting non-empty `unified_value` assignments for the same case-insensitive source key within
  the same system cause a fatal config validation error before merge execution.
- A row with a non-empty source key and an empty `unified_value` is allowed in template files; if
  encountered during `run`, that value is reported in `unmapped_values.csv` and the trimmed raw
  value is retained.
