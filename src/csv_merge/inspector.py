"""CSV encoding/delimiter inspection, type inference, and init template generation."""

from __future__ import annotations

import codecs
import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from csv_merge.coercion import coerce_bool, coerce_date, coerce_float, coerce_int
from csv_merge.config import (
    ColumnRule,
    ConfigError,
    InputFileError,
    JoinConfig,
    MappingConfig,
    NumberFormat,
    OutputConfig,
    SourceFileConfig,
    TargetType,
    load_config,
    resolve_lookup_path,
    save_config,
)

CANDIDATE_DELIMITERS: tuple[str, ...] = (",", ";", "\t", "|")
LOOKUP_HEADERS: tuple[str, str, str] = ("source_a_value", "source_b_value", "unified_value")

_UNAMBIGUOUS_EU_NUM_RE = re.compile(
    r"^[+-]?(?:"
    r"\d{1,3}(?:[.\s\u00a0]\d{3})+,\d+"
    r"|\d{1,3}(?:\.\d{3}){2,}"
    r"|\d+,(?!\d{3}$)\d+"
    r"|0,\d{3}"
    r")$"
)
_UNAMBIGUOUS_US_NUM_RE = re.compile(
    r"^[+-]?(?:"
    r"\d{1,3}(?:,\d{3})+\.\d+"
    r"|\d{1,3}(?:,\d{3}){2,}"
    r"|\d+\.(?!\d{3}$)\d+"
    r")$"
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DOT_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_SLASH_OR_HYPHEN_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_HEADER_KEY_RE = re.compile(r"[\s\-_]+")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class FileInspectionResult:
    """Auto-detected file metadata and inferred types for one source CSV."""

    path: Path
    encoding: str
    delimiter: str
    headers: tuple[str, ...]
    inferred_types: dict[str, TargetType]
    inferred_number_format: NumberFormat
    inferred_date_format: str
    row_count_sampled: int


@dataclass(frozen=True, slots=True)
class InitResult:
    """Summary of artifacts produced or updated by csv-merge init."""

    config_path: Path
    config_written: bool
    lookup_paths: tuple[Path, ...]
    inspection_a: FileInspectionResult
    inspection_b: FileInspectionResult


def detect_encoding(path: Path, sample_size: int = 65536) -> str:
    """Detect text encoding with BOM checks, UTF-8, cp1252, and latin-1 fallback."""
    if not path.is_file():
        raise InputFileError(f"Input CSV file not found: {path}")

    with path.open("rb") as fh:
        sample = fh.read(sample_size)
        at_eof = fh.read(1) == b""

    if not sample:
        raise InputFileError(f"Input CSV file is empty (0 bytes): {path}")

    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"

    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(sample, final=at_eof)
        return "utf-8"
    except UnicodeDecodeError:
        pass

    try:
        sample.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def _row_lengths_for_delimiter(sample_text: str, delimiter: str) -> list[int]:
    reader = csv.reader(io.StringIO(sample_text), delimiter=delimiter)
    return [len(row) for row in reader if row]


def detect_delimiter(path: Path, encoding: str, max_lines: int = 20) -> str:
    """Detect CSV delimiter using csv.Sniffer with consistent-column-count fallback."""
    if not path.is_file():
        raise InputFileError(f"Input CSV file not found: {path}")

    lines: list[str] = []
    try:
        with path.open("r", encoding=encoding, newline="") as fh:
            for line in fh:
                if line.strip():
                    lines.append(line)
                if len(lines) >= max_lines:
                    break
    except UnicodeDecodeError as exc:
        raise InputFileError(
            f"Cannot decode '{path}' using encoding '{encoding}': {exc}"
        ) from exc

    if not lines:
        raise InputFileError(f"Input CSV file contains no readable lines: {path}")

    sample_text = "".join(lines)

    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters="".join(CANDIDATE_DELIMITERS))
        sniffed = dialect.delimiter
        if sniffed in CANDIDATE_DELIMITERS:
            lengths = _row_lengths_for_delimiter(sample_text, sniffed)
            if lengths and min(lengths) == max(lengths) and min(lengths) > 1:
                return sniffed
    except csv.Error:
        pass

    best_delim = ","
    best_cols = 1
    for candidate in CANDIDATE_DELIMITERS:
        lengths = _row_lengths_for_delimiter(sample_text, candidate)
        if lengths and min(lengths) == max(lengths) and min(lengths) > best_cols:
            best_cols = min(lengths)
            best_delim = candidate
    return best_delim


def _infer_number_format(samples: Sequence[str]) -> NumberFormat:
    saw_eu = False
    saw_us = False
    for raw in samples:
        val = raw.strip()
        if not val:
            continue
        if _UNAMBIGUOUS_EU_NUM_RE.match(val):
            saw_eu = True
        elif _UNAMBIGUOUS_US_NUM_RE.match(val):
            saw_us = True
    if saw_eu and not saw_us:
        return "eu"
    if saw_us and not saw_eu:
        return "us"
    return "auto"


def _is_valid_date_parts(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _infer_date_format(samples: Sequence[str]) -> str:
    saw_eu = False
    saw_us = False
    saw_iso = False
    for raw in samples:
        val = raw.strip()
        if not val:
            continue
        if _ISO_DATE_RE.match(val):
            try:
                datetime.strptime(val, "%Y-%m-%d")
                saw_iso = True
            except ValueError:
                pass
            continue
        dot_match = _DOT_DATE_RE.match(val)
        if dot_match:
            day, month, year = (int(g) for g in dot_match.groups())
            if _is_valid_date_parts(year, month, day):
                saw_eu = True
            continue
        slash_match = _SLASH_OR_HYPHEN_DATE_RE.match(val)
        if slash_match:
            first, second, year = (int(g) for g in slash_match.groups())
            if first > 12 and _is_valid_date_parts(year, second, first):
                saw_eu = True
            elif second > 12 and _is_valid_date_parts(year, first, second):
                saw_us = True

    if saw_eu and not saw_us:
        return "eu"
    if saw_us and not saw_eu:
        return "us"
    if saw_iso and not saw_eu and not saw_us:
        return "iso"
    return "auto"


def _looks_like_bool_column(values: Sequence[str]) -> bool:
    has_word = any(v.strip().casefold() not in {"0", "1"} for v in values)
    return has_word and all(coerce_bool(v).status == "ok" for v in values)


def _infer_column_type(
    values: Sequence[str],
    number_format: NumberFormat,
    date_format: str,
) -> TargetType:
    non_empty = [v.strip() for v in values if v.strip()]
    if not non_empty:
        return "str"
    if all(coerce_int(v, number_format).status == "ok" for v in non_empty):
        return "int"
    if _looks_like_bool_column(non_empty):
        return "bool"
    if all(coerce_float(v, number_format).status == "ok" for v in non_empty):
        return "float"
    if all(coerce_date(v, date_format).status == "ok" for v in non_empty):
        return "date"
    return "str"


def inspect_csv_file(path: Path, max_sample_rows: int = 1000) -> FileInspectionResult:
    """Inspect a CSV file to detect encoding, delimiter, headers, and sample types."""
    encoding = detect_encoding(path)
    delimiter = detect_delimiter(path, encoding)

    try:
        with path.open("r", encoding=encoding, newline="") as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            raw_headers = next(reader, None)
            if raw_headers is None or not raw_headers or all(not h.strip() for h in raw_headers):
                raise InputFileError(f"Input CSV file '{path}' does not contain a valid header.")

            headers = tuple(h.strip() for h in raw_headers)
            per_column_samples: list[list[str]] = [[] for _ in headers]
            all_samples: list[str] = []
            sampled_rows = 0

            for row in reader:
                if not row:
                    continue
                sampled_rows += 1
                for idx in range(len(headers)):
                    cell = row[idx] if idx < len(row) else ""
                    if cell.strip():
                        per_column_samples[idx].append(cell)
                        all_samples.append(cell)
                if sampled_rows >= max_sample_rows:
                    break
    except (UnicodeDecodeError, csv.Error) as exc:
        raise InputFileError(f"Failed to parse CSV '{path}': {exc}") from exc

    number_format = _infer_number_format(all_samples)
    date_format = _infer_date_format(all_samples)
    inferred_types: dict[str, TargetType] = {}
    for idx, header in enumerate(headers):
        if header not in inferred_types:
            inferred_types[header] = _infer_column_type(
                per_column_samples[idx], number_format, date_format
            )

    return FileInspectionResult(
        path=path,
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        inferred_types=inferred_types,
        inferred_number_format=number_format,
        inferred_date_format=date_format,
        row_count_sampled=sampled_rows,
    )


def _normalize_header_key(header: str) -> str:
    return _HEADER_KEY_RE.sub("", header.strip().casefold())


def _unique_output_name(candidate: str, used_names: set[str], suffix: str) -> str:
    if candidate not in used_names:
        return candidate
    with_suffix = f"{candidate}_{suffix}"
    if with_suffix not in used_names:
        return with_suffix
    counter = 2
    while f"{with_suffix}_{counter}" in used_names:
        counter += 1
    return f"{with_suffix}_{counter}"


def _parse_normalize_flags(raw_flags: Sequence[str]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for entry in raw_flags:
        for part in entry.split(","):
            cleaned = part.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                targets.append(cleaned)
    return targets


def _sanitize_lookup_filename(column_name: str) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("_", column_name.strip()).strip("_")
    return f"{cleaned or 'column'}.csv"


def _default_lookup_ref(lookups_dir: Path, column_name: str) -> str:
    return (lookups_dir / _sanitize_lookup_filename(column_name)).as_posix()


def _build_starter_columns(
    inspection_a: FileInspectionResult,
    inspection_b: FileInspectionResult,
) -> tuple[list[ColumnRule], tuple[str, str]]:
    b_by_key: dict[str, list[str]] = {}
    for h_b in inspection_b.headers:
        b_by_key.setdefault(_normalize_header_key(h_b), []).append(h_b)

    used_b: set[str] = set()
    used_names: set[str] = set()
    columns: list[ColumnRule] = []
    first_pair: tuple[str, str] | None = None

    for h_a in inspection_a.headers:
        key = _normalize_header_key(h_a)
        candidates_b = [h for h in b_by_key.get(key, []) if h not in used_b]
        matched_b: str | None = candidates_b[0] if candidates_b else None
        if matched_b is not None:
            used_b.add(matched_b)
            if first_pair is None:
                first_pair = (h_a, matched_b)
        out_name = _unique_output_name(h_a, used_names, "a")
        used_names.add(out_name)
        columns.append(
            ColumnRule(
                name=out_name,
                source_a=h_a,
                source_b=matched_b,
                leading="A",
                type=inspection_a.inferred_types.get(h_a, "str"),
            )
        )

    for h_b in inspection_b.headers:
        if h_b in used_b:
            continue
        out_name = _unique_output_name(h_b, used_names, "b")
        used_names.add(out_name)
        columns.append(
            ColumnRule(
                name=out_name,
                source_a=None,
                source_b=h_b,
                leading="B",
                type=inspection_b.inferred_types.get(h_b, "str"),
            )
        )

    join_pair = first_pair or (inspection_a.headers[0], inspection_b.headers[0])
    return columns, join_pair


def _collect_unique_values(
    path: Path,
    encoding: str,
    delimiter: str,
    column_name: str | None,
    null_values: tuple[str, ...] = (),
) -> dict[str, str]:
    if column_name is None:
        return {}
    null_fold = {m.strip().casefold() for m in null_values if m.strip()}
    unique: dict[str, str] = {}
    with path.open("r", encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        headers = next(reader, None)
        if headers is None:
            return {}
        stripped_headers = [h.strip() for h in headers]
        if column_name not in stripped_headers:
            raise InputFileError(
                f"Configured column '{column_name}' not found in '{path}' headers."
            )
        col_idx = stripped_headers.index(column_name)
        for row in reader:
            if col_idx >= len(row):
                continue
            val = row[col_idx].strip()
            if not val or val.casefold() in null_fold:
                continue
            unique.setdefault(val.casefold(), val)
    return unique


def _write_template_lookup_csv(
    target_path: Path,
    values_a: dict[str, str],
    values_b: dict[str, str],
    rule: ColumnRule,
) -> None:
    all_keys = sorted(set(values_a.keys()) | set(values_b.keys()))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=",", lineterminator="\n")
        writer.writerow(LOOKUP_HEADERS)
        for key in all_keys:
            val_a = values_a.get(key, "")
            val_b = values_b.get(key, "")
            unified = (
                (val_a if rule.leading == "A" else val_b)
                if (val_a and val_b)
                else ""
            )
            writer.writerow((val_a, val_b, unified))


def _matches_rule(rule: ColumnRule, target_fold: str) -> bool:
    candidates = [rule.name, rule.source_a, rule.source_b]
    return any(c is not None and c.strip().casefold() == target_fold for c in candidates)


def _apply_normalize_targets(
    columns: list[ColumnRule],
    normalize_targets: Sequence[str],
    lookups_dir: Path,
) -> tuple[list[ColumnRule], bool]:
    updated = list(columns)
    changed = False
    for target in normalize_targets:
        target_fold = target.casefold()
        matched_idx = [idx for idx, col in enumerate(updated) if _matches_rule(col, target_fold)]
        if not matched_idx:
            raise ConfigError(
                f"Normalized column '{target}' does not match any column in the CSV files."
            )
        for idx in matched_idx:
            col = updated[idx]
            lookup_ref = col.lookup or _default_lookup_ref(lookups_dir, col.name)
            if not col.normalize or col.lookup != lookup_ref:
                updated[idx] = replace(col, normalize=True, lookup=lookup_ref)
                changed = True
    return updated, changed


def run_init(
    file_a: Path,
    file_b: Path,
    *,
    config_path: Path = Path("mapping.yaml"),
    lookups_dir: Path = Path("lookups"),
    normalize_columns: Sequence[str] = (),
    update_lookups: bool = False,
    force: bool = False,
) -> InitResult:
    """Inspect two CSVs and write starter mapping.yaml plus 3-column lookup CSVs."""
    inspection_a = inspect_csv_file(file_a)
    inspection_b = inspect_csv_file(file_b)
    norm_targets = _parse_normalize_flags(normalize_columns)

    if update_lookups:
        existing_cfg = load_config(config_path, require_lookup_for_normalized=False)
        cols = list(existing_cfg.columns)
        cols, norm_changed = _apply_normalize_targets(cols, norm_targets, lookups_dir)

        defaulted_lookup = False
        for idx, col in enumerate(cols):
            if col.normalize and col.lookup is None:
                cols[idx] = replace(
                    col, lookup=_default_lookup_ref(lookups_dir, col.name)
                )
                defaulted_lookup = True

        active_cfg = (
            replace(existing_cfg, columns=tuple(cols))
            if (norm_changed or defaulted_lookup)
            else existing_cfg
        )

        created_lookups: list[Path] = []
        for col in active_cfg.columns:
            if not col.normalize and col.lookup is None:
                continue
            assert col.lookup is not None
            lookup_path = resolve_lookup_path(config_path, col.lookup)
            if lookup_path.exists() and not force:
                continue
            values_a = _collect_unique_values(
                file_a,
                active_cfg.source_a.encoding,
                active_cfg.source_a.delimiter,
                col.source_a,
                active_cfg.source_a.null_values,
            )
            values_b = _collect_unique_values(
                file_b,
                active_cfg.source_b.encoding,
                active_cfg.source_b.delimiter,
                col.source_b,
                active_cfg.source_b.null_values,
            )
            _write_template_lookup_csv(lookup_path, values_a, values_b, col)
            created_lookups.append(lookup_path)

        config_written = norm_changed or defaulted_lookup
        if config_written:
            save_config(active_cfg, config_path)

        return InitResult(
            config_path=config_path,
            config_written=config_written,
            lookup_paths=tuple(created_lookups),
            inspection_a=inspection_a,
            inspection_b=inspection_b,
        )

    if config_path.exists() and not force:
        raise InputFileError(
            f"Configuration file already exists: '{config_path}'. "
            "Use --force to overwrite or --update-lookups to generate missing lookup templates."
        )

    starter_cols, join_pair = _build_starter_columns(inspection_a, inspection_b)
    starter_cols, _ = _apply_normalize_targets(starter_cols, norm_targets, lookups_dir)

    planned_lookups: list[tuple[ColumnRule, Path]] = []
    for col in starter_cols:
        if col.normalize and col.lookup is not None:
            target = resolve_lookup_path(config_path, col.lookup)
            if target.exists() and not force:
                raise InputFileError(
                    f"Lookup file already exists: '{target}'. Use --force to overwrite."
                )
            planned_lookups.append((col, target))

    config = MappingConfig(
        version=1,
        source_a=SourceFileConfig(
            encoding=inspection_a.encoding,
            delimiter=inspection_a.delimiter,
            number_format=inspection_a.inferred_number_format,
            date_format=inspection_a.inferred_date_format,
        ),
        source_b=SourceFileConfig(
            encoding=inspection_b.encoding,
            delimiter=inspection_b.delimiter,
            number_format=inspection_b.inferred_number_format,
            date_format=inspection_b.inferred_date_format,
        ),
        join=JoinConfig(column_a=join_pair[0], column_b=join_pair[1], mode="outer"),
        output=OutputConfig(encoding="utf-8", delimiter=","),
        columns=tuple(starter_cols),
    )

    save_config(config, config_path)

    written_lookups: list[Path] = []
    for col, target in planned_lookups:
        values_a = _collect_unique_values(
            file_a, inspection_a.encoding, inspection_a.delimiter, col.source_a
        )
        values_b = _collect_unique_values(
            file_b, inspection_b.encoding, inspection_b.delimiter, col.source_b
        )
        _write_template_lookup_csv(target, values_a, values_b, col)
        written_lookups.append(target)

    return InitResult(
        config_path=config_path,
        config_written=True,
        lookup_paths=tuple(written_lookups),
        inspection_a=inspection_a,
        inspection_b=inspection_b,
    )
