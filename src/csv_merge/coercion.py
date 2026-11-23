"""Locale-aware type coercion (str, int, float, date, bool) and lookup resolution."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from csv_merge.config import ConfigError, NumberFormat, SystemId, TargetType

LOOKUP_REQUIRED_HEADERS: tuple[str, str, str] = (
    "source_a_value",
    "source_b_value",
    "unified_value",
)

BOOL_TRUE_TOKENS: frozenset[str] = frozenset(
    {"true", "t", "yes", "y", "1", "ja", "j", "wahr"}
)
BOOL_FALSE_TOKENS: frozenset[str] = frozenset(
    {"false", "f", "no", "n", "0", "nein", "falsch"}
)

_PLAIN_NUM_RE = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)$")
_EU_PLAIN_RE = re.compile(r"^\d+(?:,\d+)?$")
_EU_GROUPED_DOT_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
_EU_GROUPED_SPACE_RE = re.compile(r"^\d{1,3}(?:[ \u00a0]\d{3})+(?:,\d+)?$")
_US_GROUPED_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_SINGLE_COMMA_RE = re.compile(r"^(\d+),(\d+)$")

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DOT_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_SLASH_HYPHEN_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


@dataclass(frozen=True, slots=True)
class CoercionResult:
    """Outcome of coercing one source cell to a target column type."""

    status: Literal["ok", "empty", "error"]
    value: str
    error_message: str | None = None


def is_empty_value(raw: str, null_markers: frozenset[str] = frozenset()) -> bool:
    """Return True when raw is blank, whitespace-only, or matches a configured null marker."""
    stripped = raw.strip()
    return not stripped or stripped.casefold() in null_markers


def _split_sign(text: str) -> tuple[str, str]:
    s = text.strip()
    if s.startswith(("+", "-")):
        return ("-" if s[0] == "-" else ""), s[1:].strip()
    return "", s


def _normalize_eu_body(body: str) -> str:
    if (
        _EU_PLAIN_RE.match(body)
        or _EU_GROUPED_DOT_RE.match(body)
        or _EU_GROUPED_SPACE_RE.match(body)
    ):
        return body.replace(" ", "").replace("\u00a0", "").replace(".", "").replace(",", ".")
    raise ValueError(f"Invalid European numeric literal: {body!r}")


def _normalize_us_body(body: str) -> str:
    if _PLAIN_NUM_RE.match(body) or _US_GROUPED_RE.match(body):
        return body.replace(",", "")
    raise ValueError(f"Invalid US numeric literal: {body!r}")


def _normalize_auto_body(body: str) -> str:
    if _PLAIN_NUM_RE.match(body):
        return body
    if _EU_GROUPED_SPACE_RE.match(body):
        return body.replace(" ", "").replace("\u00a0", "").replace(",", ".")

    has_dot = "." in body
    has_comma = "," in body

    if has_dot and has_comma:
        if body.rfind(",") > body.rfind(".") and _EU_GROUPED_DOT_RE.match(body):
            return body.replace(".", "").replace(",", ".")
        if body.rfind(".") > body.rfind(",") and _US_GROUPED_RE.match(body):
            return body.replace(",", "")
        raise ValueError(f"Invalid mixed-separator numeric literal: {body!r}")

    if has_comma:
        single = _SINGLE_COMMA_RE.match(body)
        if single:
            left, right = single.groups()
            if len(right) == 3 and left != "0" and 1 <= len(left) <= 3:
                return f"{left}{right}"
            return f"{left}.{right}"
        if _US_GROUPED_RE.match(body):
            return body.replace(",", "")
        raise ValueError(f"Invalid comma-separated numeric literal: {body!r}")

    if has_dot and _EU_GROUPED_DOT_RE.match(body):
        return body.replace(".", "")

    raise ValueError(f"Invalid numeric literal: {body!r}")


def parse_decimal(raw: str, number_format: NumberFormat = "auto") -> Decimal:
    """Parse a localized number string into Decimal under eu, us, or auto rules."""
    sign, body = _split_sign(raw)
    if not body:
        raise ValueError("Empty numeric value.")

    if number_format == "eu":
        normalized = _normalize_eu_body(body)
    elif number_format == "us":
        normalized = _normalize_us_body(body)
    else:
        normalized = _normalize_auto_body(body)

    try:
        dec = Decimal(f"{sign}{normalized}")
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric literal: {raw!r}") from exc

    if not dec.is_finite():
        raise ValueError(f"Non-finite numeric value is not supported: {raw!r}")
    return dec


def format_decimal(dec: Decimal) -> str:
    """Format Decimal without scientific notation or redundant trailing decimal zeros."""
    if dec == 0:
        return "0"
    rendered = format(dec, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def coerce_str(raw: str) -> CoercionResult:
    """Trim leading and trailing whitespace while preserving original letter casing."""
    return CoercionResult(status="ok", value=raw.strip())


def coerce_int(raw: str, number_format: NumberFormat = "auto") -> CoercionResult:
    """Parse whole-number integer representations and serialize as plain base-10 digits."""
    try:
        dec = parse_decimal(raw, number_format)
    except ValueError as exc:
        return CoercionResult(status="error", value="", error_message=str(exc))
    if dec != dec.to_integral_value():
        return CoercionResult(
            status="error",
            value="",
            error_message=f"Value {raw!r} has a non-zero fractional part for target type 'int'.",
        )
    return CoercionResult(status="ok", value=str(int(dec)))


def coerce_float(raw: str, number_format: NumberFormat = "auto") -> CoercionResult:
    """Parse localized decimal representations and serialize canonically with '.' decimal."""
    try:
        dec = parse_decimal(raw, number_format)
    except ValueError as exc:
        return CoercionResult(status="error", value="", error_message=str(exc))
    return CoercionResult(status="ok", value=format_decimal(dec))


def _make_date(year: int, month: int, day: int, raw: str) -> CoercionResult:
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        return CoercionResult(
            status="error",
            value="",
            error_message=f"Invalid calendar date {raw!r}: {exc}",
        )
    return CoercionResult(status="ok", value=parsed.isoformat())


def coerce_date(raw: str, date_format: str = "auto") -> CoercionResult:
    """Parse ISO, European, US, or custom strftime date values to canonical YYYY-MM-DD."""
    s = raw.strip()
    if "%" in date_format:
        try:
            parsed = datetime.strptime(s, date_format).date()
            return CoercionResult(status="ok", value=parsed.isoformat())
        except ValueError:
            return CoercionResult(
                status="error",
                value="",
                error_message=f"Value {raw!r} does not match date format {date_format!r}.",
            )

    iso_match = _ISO_DATE_RE.match(s)
    if iso_match:
        year, month, day = (int(g) for g in iso_match.groups())
        return _make_date(year, month, day, raw)

    if date_format == "iso":
        return CoercionResult(
            status="error",
            value="",
            error_message=f"Value {raw!r} is not valid ISO YYYY-MM-DD date.",
        )

    dot_match = _DOT_DATE_RE.match(s)
    if dot_match:
        day, month, year = (int(g) for g in dot_match.groups())
        return _make_date(year, month, day, raw)

    slash_match = _SLASH_HYPHEN_DATE_RE.match(s)
    if slash_match:
        first, second, year = (int(g) for g in slash_match.groups())
        if date_format == "eu":
            return _make_date(year, second, first, raw)
        if date_format == "us":
            return _make_date(year, first, second, raw)
        if first > 12:
            return _make_date(year, second, first, raw)
        if second > 12:
            return _make_date(year, first, second, raw)
        return _make_date(year, first, second, raw)

    return CoercionResult(
        status="error",
        value="",
        error_message=f"Unrecognized date literal {raw!r} for format {date_format!r}.",
    )


def coerce_bool(raw: str) -> CoercionResult:
    """Parse multilingual boolean tokens into canonical 'true' or 'false'."""
    token = raw.strip().casefold()
    if token in BOOL_TRUE_TOKENS:
        return CoercionResult(status="ok", value="true")
    if token in BOOL_FALSE_TOKENS:
        return CoercionResult(status="ok", value="false")
    return CoercionResult(
        status="error",
        value="",
        error_message=f"Invalid boolean value: {raw!r}.",
    )


@dataclass(frozen=True, slots=True)
class LookupTable:
    """Case-insensitive 3-column value lookup table for one output column."""

    path: Path
    map_a: dict[str, str]
    map_b: dict[str, str]


@dataclass(frozen=True, slots=True)
class LookupResolution:
    """Result of resolving one non-empty source value through a LookupTable."""

    value: str
    mapped: bool


def _read_lookup_lines(path: Path) -> tuple[str, list[list[str]]]:
    raw_bytes = path.read_bytes()
    if not raw_bytes:
        raise ConfigError(f"Lookup CSV file is empty: {path}")

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        try:
            raw_bytes.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            try:
                raw_bytes.decode("cp1252")
                encoding = "cp1252"
            except UnicodeDecodeError:
                encoding = "latin-1"

    for delim in (",", ";", "\t"):
        with path.open("r", encoding=encoding, newline="") as fh:
            rows = list(csv.reader(fh, delimiter=delim))
        if rows:
            stripped = [h.strip() for h in rows[0]]
            if all(req in stripped for req in LOOKUP_REQUIRED_HEADERS):
                return delim, rows
            if len(stripped) >= 3 and delim == ",":
                return delim, rows

    with path.open("r", encoding=encoding, newline="") as fh:
        return ",", list(csv.reader(fh, delimiter=","))


def load_lookup_table(path: Path) -> LookupTable:
    """Load and validate a 3-column lookup CSV (source_a_value,source_b_value,unified_value)."""
    if not path.is_file():
        raise ConfigError(f"Lookup CSV file not found: {path}")

    _, rows = _read_lookup_lines(path)
    if not rows:
        raise ConfigError(f"Lookup CSV file has no headers: {path}")

    headers = [h.strip() for h in rows[0]]
    for req in LOOKUP_REQUIRED_HEADERS:
        if req not in headers:
            raise ConfigError(
                f"Lookup CSV '{path}' missing required header column '{req}'. "
                f"Expected {LOOKUP_REQUIRED_HEADERS}, got {tuple(headers)}."
            )

    idx_a = headers.index("source_a_value")
    idx_b = headers.index("source_b_value")
    idx_u = headers.index("unified_value")

    map_a: dict[str, str] = {}
    map_b: dict[str, str] = {}

    for row_num, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        raw_a = row[idx_a].strip() if idx_a < len(row) else ""
        raw_b = row[idx_b].strip() if idx_b < len(row) else ""
        unified = row[idx_u].strip() if idx_u < len(row) else ""

        if raw_a:
            key_a = raw_a.casefold()
            if key_a in map_a and map_a[key_a] != unified:
                raise ConfigError(
                    f"Conflicting System A lookup mapping in '{path}' row {row_num} for "
                    f"{raw_a!r}: {map_a[key_a]!r} vs {unified!r}."
                )
            map_a[key_a] = unified

        if raw_b:
            key_b = raw_b.casefold()
            if key_b in map_b and map_b[key_b] != unified:
                raise ConfigError(
                    f"Conflicting System B lookup mapping in '{path}' row {row_num} for "
                    f"{raw_b!r}: {map_b[key_b]!r} vs {unified!r}."
                )
            map_b[key_b] = unified

    return LookupTable(path=path, map_a=map_a, map_b=map_b)


def resolve_lookup(
    table: LookupTable,
    system: SystemId,
    raw_value: str,
) -> LookupResolution:
    """Resolve one trimmed non-empty value case-insensitively against a LookupTable."""
    trimmed = raw_value.strip()
    mapping = table.map_a if system == "A" else table.map_b
    unified = mapping.get(trimmed.casefold(), "")
    if unified:
        return LookupResolution(value=unified, mapped=True)
    return LookupResolution(value=trimmed, mapped=False)


def coerce_value(
    raw: str,
    target_type: TargetType,
    *,
    number_format: NumberFormat = "auto",
    date_format: str = "auto",
    null_markers: frozenset[str] = frozenset(),
) -> CoercionResult:
    """Coerce a raw or lookup-normalized cell value into the column's canonical target type."""
    if is_empty_value(raw, null_markers):
        return CoercionResult(status="empty", value="")
    if target_type == "str":
        return coerce_str(raw)
    if target_type == "int":
        return coerce_int(raw, number_format)
    if target_type == "float":
        return coerce_float(raw, number_format)
    if target_type == "date":
        return coerce_date(raw, date_format)
    if target_type == "bool":
        return coerce_bool(raw)
    return CoercionResult(
        status="error",
        value="",
        error_message=f"Unsupported target type: {target_type!r}.",
    )
