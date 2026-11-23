# Feature Specification: Universal CSV Reconciliation and Merge CLI

**Feature Branch**: `001-csv-reconciliation-cli`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Build a universal CSV reconciliation and merge CLI `csv-merge` with two commands: `init` and `run`. 1. `csv-merge init --file-a <path> --file-b <path>`: Auto-detects CSV delimiters and encodings, inspects headers and sample values, and generates a starter `mapping.yaml` plus template 3-column lookup CSVs (`source_a_value,source_b_value,unified_value`) containing all unique values for any columns marked for value normalization. 2. `csv-merge run --file-a <path> --file-b <path> --config mapping.yaml --output merged.csv`: Matches records across systems using a configured unique ID column pair (normalized as trimmed, case-insensitive strings; supports `outer`, `left`, and `inner` joins, defaulting to `outer`). Enforces the exact output column list and order defined in `mapping.yaml`. For each column, designates one leading system (`A` or `B`) that defines the target data type (`str`, `int`, `float`, `date`, `bool`) and coerces the secondary system's values to match (supporting European/US number and date formats). Applies case-insensitive value-lookup tables before merging. Resolves matched rows by taking values from the leading system and filling only empty/null fields from the secondary system. Outputs `merged.csv` alongside a reconciliation summary and `unmapped_values.csv` / `errors.csv` for any unrecognized lookup values, intra-file duplicate IDs, or failed type conversions."

## Clarifications

### Session 2026-11-23

- Q: When a single input CSV file contains multiple rows with the same normalized unique ID, how should those duplicate rows be handled in `merged.csv`? → A: Keep the first occurrence in `merged.csv` and log each subsequent duplicate row to `errors.csv`.
- Q: When a non-empty cell has no matching entry in its configured lookup table (or its lookup row has a blank `unified_value`), what should be written to `merged.csv` for that field? → A: Keep the original trimmed raw value in `merged.csv` and log it to `unmapped_values.csv`.
- Q: What exit code should `csv-merge run` return when the merge completes but `errors.csv` or `unmapped_values.csv` contains data-level issues? → A: Exit `0` whenever the merge completes (even if diagnostic CSVs contain rows); exit non-zero only on fatal input, schema, or configuration errors.
- Q: How should leading and trailing whitespace be handled when writing `str` columns (including the join ID column) to `merged.csv`? → A: Trim leading and trailing whitespace on all `str` output values (including join ID columns), while preserving the leading system's letter casing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap Configuration and Lookup Templates (`init`) (Priority: P1)

A data analyst receives two CSV exports from different source systems (System A and System B) that
may differ in character encoding, field delimiter, header naming, and categorical value labels.
They run `csv-merge init --file-a <path> --file-b <path>` to inspect both files and generate a
ready-to-edit starter `mapping.yaml` configuration file along with template 3-column lookup CSVs
(`source_a_value,source_b_value,unified_value`) populated with all unique values for any columns
marked for value normalization.

**Why this priority**: Rapid, accurate discovery of file encodings, delimiters, headers, inferred
types, and distinct categorical values removes error-prone manual inspection and makes the tool
immediately usable on any unfamiliar dataset without modifying code.

**Independent Test**: Run `csv-merge init --file-a <file_a> --file-b <file_b>` (with normalization
columns marked) against two fixture CSV files having different delimiters and encodings; confirm
the generated `mapping.yaml` records detected delimiters, encodings, headers, and inferred target
types, and confirm each generated lookup CSV uses the exact header
`source_a_value,source_b_value,unified_value` and lists every unique non-empty value from both
source files.

**Acceptance Scenarios**:

1. **Given** File A is UTF-8 comma-delimited and File B is Windows-1252 semicolon-delimited,
   **When** the user runs `csv-merge init --file-a file_a.csv --file-b file_b.csv`,
   **Then** the tool detects each file's encoding and delimiter, inspects headers and sample
   values, and writes a valid starter `mapping.yaml` pre-populated with detected file settings,
   column entries, and inferred types.
2. **Given** the user marks one or more columns for value normalization (either via command options
   on `init` or by marking columns in an existing `mapping.yaml` and re-running `init`),
   **When** `csv-merge init` completes,
   **Then** the tool generates one 3-column template CSV (`source_a_value,source_b_value,unified_value`)
   per marked column containing all unique non-empty values observed in File A and File B, and links
   each lookup file from `mapping.yaml`.
3. **Given** a marked normalization column has values that match case-insensitively across both
   files as well as values unique to File A or File B,
   **When** the template lookup CSV is generated,
   **Then** matching values are paired on the same row and file-exclusive values appear in their
   respective source column with the opposing source column blank, ready for user review and
   `unified_value` assignment.
4. **Given** an input file path passed to `init` does not exist or cannot be read as a delimited
   table with headers,
   **When** the user runs `csv-merge init`,
   **Then** the command fails with a non-zero exit status and a clear, actionable error message
   without creating partial or corrupted configuration files.

---

### User Story 2 - Record Matching, Join Modes, and Precedence Merge (`run`) (Priority: P1)

A data operator with a reviewed `mapping.yaml` runs
`csv-merge run --file-a <path> --file-b <path> --config mapping.yaml --output merged.csv` to
reconcile and merge records from System A and System B. Records are matched using the configured
unique ID column pair (normalized as trimmed, case-insensitive strings) under the configured join
mode (`outer`, `left`, or `inner`, defaulting to `outer`). The resulting `merged.csv` contains the
exact column list and column order defined in `mapping.yaml`, taking each column's value from its
designated leading system (`A` or `B`) and falling back to the secondary system only when the
leading system's field is empty or null.

**Why this priority**: Record matching, join selection, exact schema ordering, and field-level
leading-system precedence are the core business capabilities of the reconciliation tool.

**Independent Test**: Run `csv-merge run` against two fixture CSVs containing matched IDs (with
casing and leading/trailing whitespace differences), A-only IDs, and B-only IDs across `outer`,
`left`, and `inner` configurations with mixed leading systems (`A` on some columns, `B` on others)
and sparse empty cells; verify exact row membership, exact output header order, and precedence
resolution.

**Acceptance Scenarios**:

1. **Given** File A has record ID `"  USR-001 "` and File B has record ID `"usr-001"`, and
   `mapping.yaml` defines `join` as omitted (defaulting to `outer`),
   **When** the user runs `csv-merge run --file-a a.csv --file-b b.csv --config mapping.yaml --output merged.csv`,
   **Then** the two rows are matched as a single output record, alongside all A-only and B-only
   records.
2. **Given** `mapping.yaml` sets the join mode to `left` or `inner`,
   **When** the user runs `csv-merge run`,
   **Then** `left` outputs matched records plus A-only records (excluding B-only records), and
   `inner` outputs only records whose normalized ID exists in both File A and File B.
3. **Given** a matched record where Column 1 has leading system `A` and Column 2 has leading system
   `B`, and both systems provide non-empty values for Column 1 while System B's value for Column 2
   is empty and System A has a value for Column 2,
   **When** `csv-merge run` resolves the record,
   **Then** Column 1 receives System A's value and Column 2 is filled with System A's value as a
   fallback for System B's empty field.
4. **Given** `mapping.yaml` specifies an ordered list of output columns that omits some source
   columns and reorders or renames others,
   **When** `csv-merge run` writes `merged.csv`,
   **Then** `merged.csv` contains strictly the configured output columns in the exact configured
   order.

---

### User Story 3 - Target Type Enforcement and European/US Format Coercion (Priority: P2)

When System A and System B export numbers, dates, or booleans in conflicting regional or textual
formats, `mapping.yaml` designates one leading system (`A` or `B`) and target data type (`str`,
`int`, `float`, `date`, or `bool`) per output column. During `csv-merge run`, values from both the
leading and secondary systems are parsed according to their regional formats (supporting European
and US numeric and date conventions) and serialized into a uniform canonical representation for the
column's target type.

**Why this priority**: Cross-system exports frequently mix European (`1.234,56`, `23.11.2026`,
`23/11/2026`) and US (`1,234.56`, `11/23/2026`) conventions; harmonizing them during merge prevents
downstream parsing failures and silent numeric/date corruption.

**Independent Test**: Run `csv-merge run` on fixture files where System A uses European numbers and
dates and System B uses US numbers and dates across `str`, `int`, `float`, `date`, and `bool`
columns; verify all merged and fallback values are coerced into uniform canonical formats in
`merged.csv`.

**Acceptance Scenarios**:

1. **Given** an output column has target type `float` with System A leading (`"1.234,56"` in
   European format) and System B secondary (`"2,345.67"` in US format),
   **When** `csv-merge run` coerces values for matched, A-only, and B-only records,
   **Then** both values are normalized to canonical decimal values (`1234.56` and `2345.67`).
2. **Given** an output column has target type `date` where System A uses `DD.MM.YYYY` or
   `DD/MM/YYYY` and System B uses `MM/DD/YYYY` or `YYYY-MM-DD`,
   **When** `csv-merge run` processes both files,
   **Then** all valid dates from either system are coerced to canonical `YYYY-MM-DD` format.
3. **Given** an output column has target type `int` or `bool` and the secondary system supplies
   equivalent values in different representations (such as `"42.0"` or `"1.000"` for integer, or
   `"YES"`, `"1"`, `"Ja"`, `"false"`, `"0"` for boolean),
   **When** `csv-merge run` processes those values,
   **Then** valid values are coerced to canonical integers (`42`, `1000`) and booleans (`true`,
   `false`).

---

### User Story 4 - Case-Insensitive Value Normalization via Lookup Tables (Priority: P2)

Before merging and type coercion, `csv-merge run` translates categorical values using any
column-specific 3-column lookup CSV (`source_a_value,source_b_value,unified_value`) configured in
`mapping.yaml`. Lookups match trimmed source values case-insensitively so inconsistent casing or
system-specific codes resolve to a single unified vocabulary before leading-system precedence and
type coercion occur.

**Why this priority**: Different enterprise systems encode the same business concepts with
incompatible codes or labels (for example, `"DE"` vs `"Germany"` or `"ACT"` vs `"Active"`). Value
normalization before merging ensures consistent output regardless of whether the leading or
secondary system supplies a field.

**Independent Test**: Configure a lookup CSV mapping distinct System A and System B codes to
unified values, supply inputs with mixed casing and extra surrounding spaces, run `csv-merge run`,
and verify unified values appear in `merged.csv` (and can subsequently be coerced if the target
type is non-string).

**Acceptance Scenarios**:

1. **Given** a lookup CSV maps `source_a_value = "ACT"` and `source_b_value = "Active"` to
   `unified_value = "ACTIVE"`, and File A contains `" act "` while File B contains `"ACTIVE"`,
   **When** `csv-merge run` executes,
   **Then** both values normalize to `"ACTIVE"` prior to precedence resolution.
2. **Given** a lookup CSV maps categorical text codes to typed unified values (for example, `"YES"`
   / `"J"` to `"true"` for a `bool` column or `"HIGH"` to `"1"` for an `int` column),
   **When** `csv-merge run` executes,
   **Then** lookup normalization runs before type coercion so the resulting unified value is parsed
   and validated against the column's target type.
3. **Given** a source cell is empty or null on a column with a lookup CSV,
   **When** `csv-merge run` executes,
   **Then** the cell is treated as empty/null (eligible for secondary-system fallback if on the
   leading system) and is not reported as an unmapped lookup value.

---

### User Story 5 - Reconciliation Summary and Diagnostic Reporting (Priority: P3)

After every `csv-merge run` execution, the operator receives a reconciliation summary detailing row
counts, match statistics, and data-quality issue counts, alongside structured diagnostic CSV files
(`unmapped_values.csv` and `errors.csv`) enumerating every unrecognized lookup value, intra-file
duplicate ID, missing ID, and failed type conversion.

**Why this priority**: Auditable exception reporting enables operators to iteratively refine lookup
tables, correct source anomalies, and sign off on data migrations with full confidence that no
errors were silently ignored.

**Independent Test**: Run `csv-merge run` on fixture files containing at least one unrecognized
lookup value, one intra-file duplicate ID, one blank ID row, and one invalid date/number value;
verify the reconciliation summary totals match the exact row counts in `unmapped_values.csv` and
`errors.csv`.

**Acceptance Scenarios**:

1. **Given** File A or File B contains a non-empty value not found in the column's lookup table (or
   mapped to a blank `unified_value`),
   **When** `csv-merge run` completes,
   **Then** `unmapped_values.csv` records the source system, column name, unmapped raw value,
   occurrence count, and sample record ID, and the reconciliation summary reflects the total
   unmapped value occurrences.
2. **Given** File A or File B contains intra-file duplicate normalized IDs or a row with an empty
   ID,
   **When** `csv-merge run` completes,
   **Then** `errors.csv` logs each duplicate or missing-ID incident with source system, source row
   number, raw/normalized ID, and error category, while keeping the first occurrence of a duplicate
   ID in the merge and excluding rows with blank IDs.
3. **Given** a value fails type conversion for a column's target type (such as `"not-a-date"` for a
   `date` column or `"abc"` for a `float` column),
   **When** `csv-merge run` completes,
   **Then** `errors.csv` logs the record ID, source system, source row number, column name, raw
   value, target type, and error reason, and the reconciliation summary reports the exact error
   count.
4. **Given** both input files merge cleanly with zero unmapped values and zero errors,
   **When** `csv-merge run` completes,
   **Then** `merged.csv` is written, the reconciliation summary reports `0` unmapped values and `0`
   errors, and `unmapped_values.csv` and `errors.csv` are written cleanly with header rows only.

---

### Edge Cases

- **Mixed file formats and quoted fields**: File A and File B use different encodings (such as
  UTF-8 with BOM vs Windows-1252) and different delimiters (such as `,`, `;`, `\t`, or `|`), and
  contain quoted fields with embedded delimiters, quotes, or line breaks.
- **Empty or header-only files**: A header-only file (0 data rows) reconciles validly (producing
  only rows from the non-empty side under `outer`/`left`, or 0 rows under `inner`), whereas a
  0-byte file or file without headers fails fast with a clear configuration/input error.
- **Missing or duplicate headers**: If a column referenced in `mapping.yaml` does not exist in its
  source CSV, or if a source CSV contains duplicate header names referenced by the mapping, `run`
  fails before writing output with a clear error naming the offending file and column.
- **Intra-file duplicate IDs differing by whitespace or case**: `" AB-10 "` and `"ab-10"` in the
  same file normalize to the same ID; the first occurrence is retained for merging and every
  subsequent duplicate row is recorded in `errors.csv`.
- **Blank ID rows**: Rows whose configured ID column is empty or whitespace-only cannot be joined;
  they are excluded from `merged.csv` and recorded in `errors.csv` with source file and row number.
- **Leading-system type conversion failure on a matched row**: If the leading system has a
  non-empty value that fails target type coercion while the secondary system has a valid value,
  the conversion failure is logged in `errors.csv` and the merged cell is left empty rather than
  silently substituting the secondary system's value.
- **Ambiguous regional formats**: Values such as `03/04/2026` (March 4 vs April 3) or `1,234`
  (integer 1234 vs decimal 1.234) are resolved deterministically using per-system or per-column
  format settings in `mapping.yaml`, with documented defaults when set to automatic detection.
- **Single-system output columns**: An output column defined in `mapping.yaml` may map from only
  System A or only System B (with the other source column omitted); rows lacking the mapped system
  produce an empty cell for that column.
- **Relative lookup CSV paths**: Relative paths to lookup CSVs declared inside `mapping.yaml` are
  resolved relative to the directory containing `mapping.yaml`, regardless of the current working
  directory when `csv-merge run` is invoked.
- **Existing files during `init`**: Re-running `csv-merge init` when `mapping.yaml` or lookup CSVs
  already exist MUST avoid silently destroying user edits unless overwrite is explicitly requested,
  and when pointed at an existing `mapping.yaml` MUST generate or update template lookup CSVs for
  columns marked for normalization.
- **Malformed lookup CSVs**: If a referenced lookup CSV is missing, lacks the required
  `source_a_value,source_b_value,unified_value` header columns, or defines conflicting
  `unified_value` mappings for the same case-insensitive source key within a system, `csv-merge run`
  fails fast with a clear validation error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST expose the command name `csv-merge` with two primary subcommands: `init`
  and `run`.
- **FR-002**: The tool MUST remain completely domain-agnostic: it MUST NOT hardcode any
  domain-specific column names, schemas, data types, lookup mappings, or precedence rules. All
  reconciliation behavior MUST be driven exclusively by configuration files (`mapping.yaml` and its
  referenced lookup CSVs).
- **FR-003**: `csv-merge init --file-a <path> --file-b <path>` MUST automatically detect each
  input CSV file's character encoding (including UTF-8, UTF-8 with BOM, and common Western European
  encodings such as Windows-1252/Latin-1) and field delimiter (such as comma, semicolon, tab, or
  pipe).
- **FR-004**: `csv-merge init` MUST inspect headers and sample data values from both input files
  and generate a starter `mapping.yaml` containing detected file settings (encoding, delimiter,
  detected regional number/date format hints), ID key mapping configuration, default join mode
  (`outer`), and an ordered output column list with source column mappings, leading-system
  designations (`A` or `B`), and inferred target data types (`str`, `int`, `float`, `date`, `bool`).
- **FR-005**: `csv-merge init` MUST support marking columns for value normalization (via explicit
  command-line options on `init` and/or by reading normalization flags from an existing
  `mapping.yaml`) and MUST generate one 3-column template lookup CSV per marked column with exact
  headers `source_a_value,source_b_value,unified_value` containing all unique non-empty values from
  File A and File B.
- **FR-006**: When populating template 3-column lookup CSVs, `csv-merge init` MUST pair values
  that match case-insensitively (after trimming) between System A and System B on the same row and
  list system-exclusive values in their respective source column (`source_a_value` or
  `source_b_value`), leaving the opposite column empty and allowing user review of `unified_value`.
- **FR-007**: `csv-merge init` MUST protect existing `mapping.yaml` and lookup CSV files from
  unintended silent overwrite unless explicit overwrite or existing-config template-generation mode
  is specified.
- **FR-008**: `csv-merge run --file-a <path> --file-b <path> --config <mapping.yaml> --output <merged.csv>`
  MUST load and strictly validate `mapping.yaml` and all referenced lookup CSVs before processing
  records, failing fast with clear error messages and a non-zero exit code on missing files,
  invalid syntax, invalid join mode, unsupported target types, invalid leading system values,
  missing source headers, or conflicting lookup definitions.
- **FR-009**: `csv-merge run` MUST match records between File A and File B using the configured
  unique ID column pair normalized as trimmed, case-insensitive strings.
- **FR-010**: `csv-merge run` MUST support `outer`, `left`, and `inner` join modes configured in
  `mapping.yaml` (defaulting to `outer` when omitted) and produce deterministic row ordering
  (System A rows in input order first, followed by System B–only rows in input order for `outer`
  joins).
- **FR-011**: `csv-merge run` MUST enforce the exact output column names and column ordering
  declared in `mapping.yaml`, ignoring unmapped source columns and supporting columns mapped from
  both systems or from a single system.
- **FR-012**: For every configured output column, `mapping.yaml` MUST designate a leading system
  (`A` or `B`) and a target data type (`str`, `int`, `float`, `date`, or `bool`). Values from both
  the leading and secondary systems MUST be coerced to match the column's target data type.
- **FR-013**: Type coercion MUST support both European and US number formats (including comma vs
  period decimal separators and period, comma, or space thousands separators) and European, US, and
  ISO date formats (`DD.MM.YYYY`, `DD/MM/YYYY`, `DD-MM-YYYY`, `MM/DD/YYYY`, `MM-DD-YYYY`,
  `YYYY-MM-DD`), honoring per-system or per-column regional format hints configured in
  `mapping.yaml` to disambiguate otherwise ambiguous inputs.
- **FR-014**: Type coercion MUST support boolean parsing from common case-insensitive text
  representations (including `true`/`false`, `yes`/`no`, `y`/`n`, `1`/`0`, `ja`/`nein`,
  `wahr`/`falsch`) and integer parsing including clean whole-number representations with regional
  thousands separators, while rejecting fractional values for `int` columns.
- **FR-015**: Before merging and type coercion, `csv-merge run` MUST apply any configured
  3-column lookup CSV (`source_a_value,source_b_value,unified_value`) using trimmed,
  case-insensitive matching against `source_a_value` for System A rows and `source_b_value` for
  System B rows, replacing matched values with `unified_value`.
- **FR-016**: Relative paths to lookup CSVs declared in `mapping.yaml` MUST resolve relative to
  the directory containing `mapping.yaml`.
- **FR-017**: For matched records, `csv-merge run` MUST resolve every output column by taking the
  value from the column's designated leading system (`A` or `B`) and filling from the secondary
  system ONLY when the leading system's raw/normalized field is empty or null (including empty
  strings, whitespace-only strings, and any configured null markers).
- **FR-018**: If a leading system supplies a non-empty value that fails target type conversion,
  `csv-merge run` MUST log the failure to `errors.csv` and leave that output cell empty rather than
  substituting the secondary system's value.
- **FR-019**: When a non-empty value in a column with a configured lookup table does not match any
  entry for its system (or matches an entry with an empty `unified_value`), `csv-merge run` MUST
  record it in `unmapped_values.csv` (capturing source system, column name, raw value, occurrence
  count, and sample record ID) and retain the original trimmed value for downstream processing.
- **FR-020**: When File A or File B contains multiple rows sharing the same normalized unique ID,
  `csv-merge run` MUST retain the first occurrence for reconciliation and log every subsequent
  duplicate occurrence to `errors.csv` (capturing source system, source row number, raw ID,
  normalized ID, and duplicate-ID error category).
- **FR-021**: When File A or File B contains a row with an empty or whitespace-only ID value,
  `csv-merge run` MUST exclude that row from `merged.csv` and log it to `errors.csv` with source
  system, source row number, and missing-ID error category.
- **FR-022**: `csv-merge run` MUST serialize `merged.csv` in canonical typed output formats
  (leading and trailing whitespace trimmed while preserving original letter casing for `str`
  values including join ID columns, ISO-8601 `YYYY-MM-DD` for `date`, period decimal without
  thousands separators for `float`, plain base-10 digits for `int`, lowercase `true`/`false` for
  `bool`, empty string for null, and UTF-8 encoding with configurable output delimiter defaulting
  to comma).
- **FR-023**: `csv-merge run` MUST write `unmapped_values.csv` and `errors.csv` alongside
  `merged.csv` (in the same output directory, creating parent directories if needed) with
  consistent header rows on every successful run, even when zero issues are detected.
- **FR-024**: `csv-merge run` MUST display a clear reconciliation summary upon completion reporting
  input row counts for System A and System B, matched row count, A-only row count, B-only row
  count, total output rows written, intra-file duplicate ID count, missing ID count, unmapped
  lookup value count, type conversion error count, and output file paths.
- **FR-025**: `csv-merge run` MUST exit with status code `0` whenever reconciliation completes
  and outputs are written (even when data-level anomalies are logged in `unmapped_values.csv`
  or `errors.csv`), and MUST exit with a non-zero status code on fatal input, schema, or
  configuration validation errors.

### Key Entities

- **Source File Profile**: Metadata describing an input CSV file (System A or System B), including
  detected or configured encoding, field delimiter, header names, regional number/date format
  preferences, and optional null-value markers.
- **Mapping Configuration (`mapping.yaml`)**: The single user-editable governance file defining
  source profiles for System A and System B, the unique ID column pair, join mode (`outer`, `left`,
  `inner`), output CSV settings, and the ordered list of output column definitions.
- **Output Column Definition**: An entry in `mapping.yaml` specifying the output column name,
  corresponding source column name in System A and/or System B, leading system (`A` or `B`), target
  data type (`str`, `int`, `float`, `date`, `bool`), optional lookup CSV reference, and optional
  column-level regional format overrides.
- **Value Lookup Table**: A 3-column CSV (`source_a_value,source_b_value,unified_value`) associated
  with an output column that maps system-specific raw values (matched trimmed and
  case-insensitively) to unified canonical values prior to merging and type coercion.
- **Reconciliation Record**: An aligned logical record keyed by a normalized unique ID representing
  either a matched pair (System A + System B), an A-only record, or a B-only record, resolved into
  a typed output row adhering to the configured schema and precedence rules.
- **Diagnostic Reports (`unmapped_values.csv`, `errors.csv`, and Reconciliation Summary)**:
  Structured audit outputs detailing unrecognized lookup values (aggregated with occurrence counts
  and sample IDs), row-level data errors (intra-file duplicate IDs, missing IDs, and failed type
  conversions), and high-level reconciliation metrics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can bootstrap a complete, valid starter `mapping.yaml` and template lookup
  CSVs from two unfamiliar CSV files in a single `csv-merge init` command taking under 5 seconds
  for typical datasets up to 50,000 rows per file.
- **SC-002**: `csv-merge run` reconciles and merges two 50,000-row CSV files with lookup
  normalization and mixed European/US type coercion in under 15 seconds on a standard workstation.
- **SC-003**: 100% of output columns in `merged.csv` match the exact names, ordering, leading-system
  precedence rules, and canonical target data types defined in `mapping.yaml`, verified across at
  least two completely distinct domains (with zero source-code changes between domains).
- **SC-004**: 100% of unrecognized lookup values, intra-file duplicate IDs, missing IDs, and failed
  type conversions introduced into test datasets are accurately captured in `unmapped_values.csv`,
  `errors.csv`, and the reconciliation summary with zero silent data drops.
- **SC-005**: File delimiter and encoding auto-detection in `csv-merge init` correctly identifies
  standard delimited CSV inputs across UTF-8, UTF-8 with BOM, and Windows-1252/Latin-1 encodings
  and comma, semicolon, tab, and pipe delimiters without manual pre-processing.

## Assumptions

- **Starter configuration output location**: By default, `csv-merge init` writes `mapping.yaml` and
  template lookup CSVs (for example under a `lookups/` subdirectory or current directory) in the
  current working directory unless the user provides an optional output path or configuration path.
- **Marking columns for value normalization during `init`**: Users can mark normalization columns
  either directly via an optional CLI flag on `csv-merge init` (for example, specifying column
  names) or through a two-step workflow where they mark columns in the generated `mapping.yaml`
  and re-run `csv-merge init --file-a <path> --file-b <path> --config mapping.yaml --update-lookups`.
- **Ambiguous regional format tie-breaking**: When regional format hints are set to automatic
  detection, unambiguous European/US values are parsed automatically; ambiguous slash dates (such
  as `03/04/2026`) and ambiguous single-separator numbers default to US/ISO conventions unless the
  user configures `eu` at the system or column level in `mapping.yaml`.
- **Null/empty value definition**: Empty strings and whitespace-only cells are always treated as
  empty/null; additional sentinel strings (such as `NULL`, `N/A`, or `-`) are treated as literal
  values unless explicitly listed as null markers in `mapping.yaml`.
- **Diagnostic file presence**: `unmapped_values.csv` and `errors.csv` are always created
  alongside `merged.csv` (header-only when clean) so automated pipelines have predictable
  outputs.
- **Scope boundary**: The CLI operates on local delimited text files (CSV/TSV/etc.) in batch mode;
  direct database connectors, interactive GUI editors, and multi-way (>2 files) merges are out of
  scope for this feature.
