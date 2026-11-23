# Phase 0 Research & Architectural Decisions: Universal CSV Reconciliation and Merge CLI

**Feature**: `001-csv-reconciliation-cli`
**Date**: 2026-11-23
**Inputs**: [spec.md](spec.md), [constitution.md](../../.specify/memory/constitution.md)

## 1. Python 3.13 Standard Library + PyYAML Stack

- **Decision**: Implement the entire CLI using Python 3.13 standard library modules (`csv`,
  `argparse`, `datetime`, `decimal`, `codecs`, `dataclasses`, `pathlib`, `re`, `sys`, `typing`)
  plus `PyYAML` (`>=6.0`) as the sole runtime dependency.
- **Rationale**: Eliminates heavy native dependencies (`pandas`, `numpy`, `chardet`) that inflate
  install times, introduce implicit type guessing on CSV ingest (such as stripping leading zeros on
  string IDs or silently coercing floats), and complicate cross-platform Windows/Linux builds.
  Standard library `csv` preserves raw cell text identically so lookup normalization and
  locale-aware type coercion run deterministically in the exact order required by the spec.
- **Alternatives considered**:
  - `pandas`: Rejected by user technical constraint and because automatic type inference during
    `read_csv` conflicts with raw-value preservation before lookup resolution.
  - `typer` / `click`: Rejected in favor of stdlib `argparse` to minimize dependency footprint as
    requested while still providing clean `init` and `run` subcommands and `--help` output.
  - `pydantic`: Permitted by the constitution, but stdlib frozen `@dataclass(frozen=True, slots=True)`
    models with explicit validation functions keep runtime dependencies limited to `PyYAML` and
    align directly with the user's architecture specification (`MappingConfig`, `ColumnRule`,
    `JoinConfig`).

## 2. `uv_build` Packaging & `src/csv_merge/` Layout Alignment

- **Decision**: Configure `[tool.uv.build-backend]` in `pyproject.toml` with
  `module-name = "csv_merge"` and `module-root = "src"`, register
  `csv-merge = "csv_merge.cli:main"` under `[project.scripts]`, add `PyYAML>=6.0` via `uv add`,
  and replace the initial placeholder directory `src/csv_merge_tool/` with `src/csv_merge/`.
- **Rationale**: `pyproject.toml` declares `name = "csv-merge-tool"` with `build-backend = "uv_build"`.
  By default `uv_build` looks for `src/csv_merge_tool/`; setting `module-name = "csv_merge"`
  explicitly satisfies Constitution Principle IV (`src/csv_merge/`) without renaming the project
  distribution.
- **Alternatives considered**:
  - Renaming `[project] name` to `csv-merge`: Unnecessary when `uv_build` natively supports
    `module-name = "csv_merge"`.
  - Keeping `src/csv_merge_tool/`: Violates Constitution Principle IV and user architecture rules.

## 3. Encoding & Delimiter Detection (`inspector.py`)

- **Decision**:
  - **Encoding**: Inspect raw bytes first for UTF-8 BOM (`\xef\xbb\xbf` -> `utf-8-sig`) and UTF-16
    BOM (`\xff\xfe` / `\xfe\xff` -> `utf-16`). Next, attempt strict UTF-8 decoding on a sample up
    to 64 KiB using `codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)` (avoiding
    false failures if the 64 KiB slice bisects a multi-byte UTF-8 character; use `final=True` when
    the entire file fits within the sample). If UTF-8 raises `UnicodeDecodeError`, try `cp1252`
    strictly; fall back to `latin-1` only if bytes undefined in `cp1252` (`0x81`, `0x8D`, `0x8F`,
    `0x90`, `0x9D`) occur.
  - **Delimiter**: Decode up to 20 non-empty sample lines (within the 64 KiB sample) and try
    `csv.Sniffer().sniff(sample_text, delimiters=",;\t|")`. Validate the sniffed delimiter by
    parsing the sample lines with `csv.reader` and checking that the column count is consistent and
    `> 1`. If `csv.Sniffer` raises `csv.Error` or produces inconsistent column counts (common on
    header-only files or text containing commas), score each candidate in `(",", ";", "\t", "|")`
    by consistent column count (`min_cols == max_cols > 1`, preferring higher column count and
    tie-breaking in candidate order); default to `,` for single-column files.
- **Rationale**: Combines `csv.Sniffer` with deterministic validation and `utf-8-sig`/`cp1252`
  fallback using pure Python 3.13 stdlib, accurately handling UTF-8, UTF-8-BOM, Windows-1252, and
  European semicolon/tab/pipe exports.
- **Alternatives considered**:
  - `chardet` / `charset-normalizer`: Rejected to avoid extra runtime dependencies and probabilistic
    misclassification on short ASCII/Western European CSV samples.

## 4. Header Pairing, Type Inference & Starter Template Generation (`inspector.py`)

- **Decision**:
  - **Type inference**: Sample up to 1,000 non-empty values per column. Evaluate in order:
    1. `int` (valid integer under the file's inferred number format, checked before `bool` so
       numeric columns containing `0`/`1` are not misclassified as booleans unless textual boolean
       tokens appear).
    2. `bool` (all values match textual/mixed boolean tokens such as `true/false`, `yes/no`,
       `ja/nein`, `wahr/falsch`, `y/n`, optionally combined with `0/1` if at least one non-digit
       boolean token is present).
    3. `float` (valid decimal under inferred number format).
    4. `date` (valid date under inferred ISO/EU/US date formats).
    5. `str` (fallback for mixed or textual values).
    - Empty columns (no non-empty sample values) default to `str`.
  - **Regional format inference**: Scan sample values across the file for unambiguous numeric
    markers (e.g., `1.250,50` or `12,50` -> `eu`; `1,250.50` -> `us`; otherwise `auto`) and
    unambiguous date markers (`DD.MM.YYYY` or `DD/MM/YYYY` with first field > 12 -> `eu`;
    `MM/DD/YYYY` with second field > 12 -> `us`; `YYYY-MM-DD` -> `iso`; otherwise `auto`).
  - **Header pairing**: Match headers between File A and File B using normalized key
    `re.sub(r"[\s\-_]+", "", header.strip().casefold())`. Paired columns emit a single `ColumnRule`
    (leading `A` by default, target type inferred from leading system); unmatched System A headers
    emit A-only rules (leading `A`); unmatched System B headers emit B-only rules (leading `B`).
    The first paired column (or first header of each file if none match) populates starter
    `JoinConfig`.
  - **Value normalization & 3-column lookup templates**:
    - Columns marked via `--normalize <col>` (repeatable/comma-separated on `init`) or via
      `normalize: true` / `lookup: <path>` in an existing `mapping.yaml` (when running `init` with
      `--update-lookups`) receive a 3-column UTF-8 CSV (`source_a_value,source_b_value,unified_value`).
    - All unique trimmed non-empty values from System A and System B are collected (preserving
      first-seen display casing). Values matching case-insensitively across both files are paired on
      the same row with `unified_value` pre-filled from the leading system's value for convenient
      review; A-only and B-only values appear on separate rows with the opposite source column blank
      and `unified_value` blank for explicit human curation.
    - Existing `mapping.yaml` or lookup CSVs are never silently overwritten unless `--force` is
      passed (`FR-007`).
- **Rationale**: Produces an immediately runnable or minimally editable `mapping.yaml` while
  keeping human review explicit for unmatched categorical values and preventing accidental data
  loss on re-runs.
- **Alternatives considered**:
  - Auto-generating lookup CSVs for every low-cardinality text column without marking: Rejected
    because the spec explicitly scopes lookup CSV generation to columns marked for value
    normalization.

## 5. Locale-Aware Coercion & Case-Insensitive Lookup Resolver (`coercion.py`)

- **Decision**:
  - **Numbers (`int`, `float`) via `decimal.Decimal`**:
    - Strip surrounding whitespace; accept optional leading `+`/`-`. Reject empty strings, NaN/Inf,
      currency symbols, or malformed grouping.
    - `eu` mode: thousands separator `.` or space (` ` / `\u00a0`) in 3-digit groups; decimal
      separator `,` (also accepts plain ungrouped digits `1234` or `1234,50`).
    - `us` mode: thousands separator `,` in 3-digit groups; decimal separator `.` (also accepts
      plain ungrouped digits `1234` or `1234.50`).
    - `auto` mode:
      - Both `.` and `,` present -> last separator is decimal; preceding separator must form valid
        3-digit thousands groups (`1.250,50` -> `1250.50`, `1,250.50` -> `1250.50`).
      - Space + `,` -> `eu`.
      - Only `,`: multiple valid 3-digit groups (`1,000,000`) -> US thousands; single comma with
        != 3 trailing digits (`12,5`, `12,50`) -> EU decimal; single comma with exactly 3 trailing
        digits (`1,234`) -> US thousands tie-breaker per spec Assumptions.
      - Only `.`: multiple valid 3-digit groups (`1.000.000`) -> EU thousands; single dot ->
        standard/US decimal (`1250.50`, `1.234`).
    - `int` target: parse via decimal parser, verify `d == d.to_integral_value()`, return `int(d)`
      serialized as plain base-10 digits (rejects non-zero fractional values such as `12.34`, while
      accepting whole values such as `42.0`, `42,00`, `1.000` in EU, `1,000` in US).
    - `float` target: parse into `Decimal`, normalize `-0` to `0`, and format as fixed-point
      without scientific notation or thousands separators (stripping redundant trailing fractional
      zeros after `.` via normalized `Decimal` so `1.250,50` and `1250.5` both serialize canonically
      as `1250.5`, `1.234,56` as `1234.56`, and `1000.00` as `1000`).
  - **Dates (`date`) via `datetime.date`**:
    - Always accept unambiguous ISO `YYYY-MM-DD` and European dot `DD.MM.YYYY` (except when
      `date_format` is explicitly set to `iso` or a custom `%` strftime pattern).
    - Slash/hyphen dates (`XX/YY/YYYY`, `XX-YY-YYYY`):
      - `eu`: `%d/%m/%Y`, `%d-%m-%Y`, `%d.%m.%Y`, `%Y-%m-%d`.
      - `us`: `%m/%d/%Y`, `%m-%d-%Y`, `%Y-%m-%d`, `%d.%m.%Y`.
      - `iso`: `%Y-%m-%d` only.
      - `auto`: ISO `%Y-%m-%d` and dot `%d.%m.%Y` first; for `A/B/YYYY` or `A-B-YYYY`, if `A > 12`
        parse as EU (`%d/%m/%Y`), else if `B > 12` parse as US (`%m/%d/%Y`), else use US
        tie-breaker (`%m/%d/%Y`) per spec Assumptions.
      - Custom `strptime` pattern (any `date_format` containing `%`): parse strictly with that
        pattern.
    - Serialize canonically via `date.isoformat()` (`YYYY-MM-DD`).
  - **Booleans (`bool`)**:
    - Match `raw.strip().casefold()` against truthy `{"true", "t", "yes", "y", "1", "ja", "j", "wahr"}`
      and falsy `{"false", "f", "no", "n", "0", "nein", "falsch"}`. Serialize canonically as
      `"true"` or `"false"`.
  - **Strings (`str`)**:
    - Trim leading and trailing whitespace on all non-empty `str` values (including join ID
      columns) while preserving original letter casing (after lookup normalization when
      configured); treat whitespace-only strings and configured `null_values` as empty (`""`).
  - **Lookup Table Resolver**:
    - Load 3-column CSV with required header names `source_a_value`, `source_b_value`,
      `unified_value` (resolved relative to `mapping.yaml`'s parent directory).
    - Index trimmed `casefold()` keys separately for System A and System B.
    - Fail fast at config load if file is missing, headers are invalid, or a single system maps the
      same case-insensitive key to two different non-empty `unified_value` entries.
    - At runtime, if a non-empty cell has no key match OR maps to a blank `unified_value`, record an
      unmapped occurrence and return the original trimmed string for downstream type coercion.
- **Rationale**: `Decimal` prevents binary floating-point rounding drift and cleanly validates
  integer wholeness; explicit locale modes eliminate silent date/decimal misinterpretation while
  `auto` handles mixed unambiguous inputs seamlessly.
- **Alternatives considered**:
  - Python `float()` directly: Rejected due to binary representation artifacts and imprecise
    `is_integer()` behavior on large values.
  - `python-dateutil`: Rejected to avoid extra dependencies and opaque heuristic date parsing.

## 6. Join Engine, Duplicate Handling & Resolution Order (`merger.py`)

- **Decision**:
  - **ID normalization**: `raw_id.strip().upper()`. Empty/whitespace-only (or configured null
    marker) IDs are excluded from indexing and recorded in `errors.csv` (`error_category = "missing_id"`).
  - **Row numbering**: 1-based CSV record numbers where the header is row `1` and the first data
    row is row `2`, matching spreadsheet and text-editor line expectations.
  - **Intra-file duplicates**: Store indexed rows in Python `dict[str, IndexedRow]` (insertion
    ordered). On encountering an already-seen normalized ID within the same file, keep the first
    occurrence and append a `MergeError` (`error_category = "duplicate_id"`) referencing both the
    duplicate row number and the first-seen row number.
  - **Join iteration order**:
    - `outer`: System A keys in input order (matched or A-only), then System B keys absent from A
      in input order (B-only).
    - `left`: System A keys in input order (matched or A-only); B-only rows excluded and counted in
      summary.
    - `inner`: System A keys also present in B in input order; A-only and B-only rows excluded and
      counted in summary.
  - **Cell pipeline per included row & column**:
    1. Apply lookup normalization (if `ColumnRule.lookup` is set) to each present source side
       independently, recording any unmapped non-empty values in the unmapped aggregator.
    2. Apply target type coercion (`str`, `int`, `float`, `date`, `bool`) to each present non-empty
       source side independently, recording any conversion failures in `errors.csv`.
    3. Resolve output cell:
       - Single-side row (A-only or B-only): emit that side's coerced value (or `""` if empty/error).
       - Matched row: take the leading system's result if `"ok"`; emit `""` without fallback if
         leading status is `"error"` (`FR-018`); fall back to secondary system's `"ok"` value only
         when leading status is `"empty"` (`FR-017`).
- **Rationale**: Running lookup and type validation on both sides of every included record ensures
  100% diagnostic visibility (`SC-004`) while strictly enforcing leading-system precedence and
  non-masking of leading-system conversion errors (`FR-018`).
- **Alternatives considered**:
  - Lazy evaluation of secondary side only when leading is empty: Rejected because unmapped values
    or corrupt dates/numbers in the secondary system on matched rows would go unreported, violating
    `FR-012`, `FR-015`, and `SC-004`.

## 7. Performance & Scale Profile

- **Decision**: Stream CSV ingestion with `csv.reader`, store indexed rows as compact dicts keyed
  by normalized ID (retaining only the columns referenced by `JoinConfig` and `ColumnRule`s rather
  than unmapped source columns), and stream output rows directly to `merged.csv`.
- **Rationale**: Pruning unmapped source columns during ingest keeps memory footprint modest and
  easily meets the 50,000-row-per-file targets (`<5s` for `init`, `<15s` for `run`) using pure
  Python 3.13 without external C-extension DataFrame libraries.
- **Alternatives considered**:
  - External disk-backed sort/merge: Unnecessary complexity for the target batch scale (up to tens
    or hundreds of thousands of rows on a standard workstation).
