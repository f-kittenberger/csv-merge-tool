"""Configuration models, validation, and YAML persistence for csv-merge."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

SystemId = Literal["A", "B"]
JoinMode = Literal["outer", "left", "inner"]
TargetType = Literal["str", "int", "float", "date", "bool"]
NumberFormat = Literal["auto", "eu", "us"]

VALID_SYSTEMS: tuple[SystemId, ...] = ("A", "B")
VALID_JOIN_MODES: tuple[JoinMode, ...] = ("outer", "left", "inner")
VALID_TARGET_TYPES: tuple[TargetType, ...] = ("str", "int", "float", "date", "bool")
VALID_NUMBER_FORMATS: tuple[NumberFormat, ...] = ("auto", "eu", "us")
VALID_NAMED_DATE_FORMATS: frozenset[str] = frozenset({"auto", "iso", "eu", "us"})


class CsvMergeError(Exception):
    """Base error for fatal csv-merge failures."""


class ConfigError(CsvMergeError):
    """Raised when configuration or lookup definitions fail validation."""


class InputFileError(CsvMergeError):
    """Raised when an input or output file operation cannot proceed safely."""


def validate_encoding_name(encoding: str, context: str) -> str:
    """Validate that encoding is a non-empty registered Python codec name."""
    if not isinstance(encoding, str) or not encoding.strip():
        raise ConfigError(f"{context}.encoding must be a non-empty string.")
    try:
        codecs.lookup(encoding)
    except LookupError as exc:
        raise ConfigError(f"{context}.encoding has unknown codec '{encoding}'.") from exc
    return encoding


def validate_delimiter(delimiter: str, context: str) -> str:
    """Validate that delimiter is a single character."""
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ConfigError(
            f"{context}.delimiter must be a single character, got {delimiter!r}."
        )
    return delimiter


def validate_number_format(value: str, context: str) -> NumberFormat:
    """Validate numeric regional format hint."""
    if value not in VALID_NUMBER_FORMATS:
        raise ConfigError(
            f"{context} must be one of {VALID_NUMBER_FORMATS}, got {value!r}."
        )
    return cast(NumberFormat, value)


def validate_date_format(value: str, context: str) -> str:
    """Validate date format keyword or strftime pattern."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must be a non-empty string.")
    if value in VALID_NAMED_DATE_FORMATS or "%" in value:
        return value
    raise ConfigError(
        f"{context} must be one of ('auto', 'iso', 'eu', 'us') or a strftime pattern "
        f"containing '%', got {value!r}."
    )


@dataclass(frozen=True, slots=True)
class SourceFileConfig:
    """Ingestion and regional parsing settings for one source CSV file."""

    encoding: str = "utf-8"
    delimiter: str = ","
    number_format: NumberFormat = "auto"
    date_format: str = "auto"
    null_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_encoding_name(self.encoding, "source")
        validate_delimiter(self.delimiter, "source")
        validate_number_format(self.number_format, "source.number_format")
        validate_date_format(self.date_format, "source.date_format")
        for marker in self.null_values:
            if not isinstance(marker, str):
                raise ConfigError("source.null_values entries must all be strings.")


@dataclass(frozen=True, slots=True)
class JoinConfig:
    """Unique ID matching and join configuration."""

    column_a: str
    column_b: str
    mode: JoinMode = "outer"

    def __post_init__(self) -> None:
        if not isinstance(self.column_a, str) or not self.column_a.strip():
            raise ConfigError("join.column_a must be a non-empty string.")
        if not isinstance(self.column_b, str) or not self.column_b.strip():
            raise ConfigError("join.column_b must be a non-empty string.")
        if self.mode not in VALID_JOIN_MODES:
            raise ConfigError(
                f"join.mode must be one of {VALID_JOIN_MODES}, got {self.mode!r}."
            )


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Output serialization settings for merged.csv."""

    encoding: str = "utf-8"
    delimiter: str = ","

    def __post_init__(self) -> None:
        validate_encoding_name(self.encoding, "output")
        validate_delimiter(self.delimiter, "output")


@dataclass(frozen=True, slots=True)
class ColumnRule:
    """Output column definition, source mapping, precedence, type, and lookup rule."""

    name: str
    source_a: str | None = None
    source_b: str | None = None
    leading: SystemId = "A"
    type: TargetType = "str"
    normalize: bool = False
    lookup: str | None = None
    number_format_a: NumberFormat | None = None
    number_format_b: NumberFormat | None = None
    date_format_a: str | None = None
    date_format_b: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigError("Column rule 'name' must be a non-empty string.")
        if self.leading not in VALID_SYSTEMS:
            raise ConfigError(
                f"Column '{self.name}' leading system must be 'A' or 'B', got {self.leading!r}."
            )
        if self.type not in VALID_TARGET_TYPES:
            raise ConfigError(
                f"Column '{self.name}' type must be one of {VALID_TARGET_TYPES}, got {self.type!r}."
            )
        if self.source_a is not None and (
            not isinstance(self.source_a, str) or not self.source_a.strip()
        ):
            raise ConfigError(
                f"Column '{self.name}' source_a must be a non-empty string or null."
            )
        if self.source_b is not None and (
            not isinstance(self.source_b, str) or not self.source_b.strip()
        ):
            raise ConfigError(
                f"Column '{self.name}' source_b must be a non-empty string or null."
            )
        if self.leading == "A" and self.source_a is None:
            raise ConfigError(
                f"Column '{self.name}' sets leading='A' and must define a non-empty source_a."
            )
        if self.leading == "B" and self.source_b is None:
            raise ConfigError(
                f"Column '{self.name}' sets leading='B' and must define a non-empty source_b."
            )
        if not isinstance(self.normalize, bool):
            raise ConfigError(f"Column '{self.name}' normalize must be a boolean.")
        if self.lookup is not None and (
            not isinstance(self.lookup, str) or not self.lookup.strip()
        ):
            raise ConfigError(
                f"Column '{self.name}' lookup must be a non-empty path or null."
            )
        if self.number_format_a is not None:
            validate_number_format(
                self.number_format_a, f"columns[{self.name}].number_format_a"
            )
        if self.number_format_b is not None:
            validate_number_format(
                self.number_format_b, f"columns[{self.name}].number_format_b"
            )
        if self.date_format_a is not None:
            validate_date_format(
                self.date_format_a, f"columns[{self.name}].date_format_a"
            )
        if self.date_format_b is not None:
            validate_date_format(
                self.date_format_b, f"columns[{self.name}].date_format_b"
            )


@dataclass(frozen=True, slots=True)
class MappingConfig:
    """Root mapping.yaml configuration model."""

    source_a: SourceFileConfig
    source_b: SourceFileConfig
    join: JoinConfig
    columns: tuple[ColumnRule, ...]
    version: int = 1
    output: OutputConfig = OutputConfig()

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version != 1:
            raise ConfigError(f"Unsupported config version: {self.version!r}. Expected 1.")
        if not self.columns:
            raise ConfigError("Configuration 'columns' must define at least one output column.")
        seen_names: set[str] = set()
        for col in self.columns:
            if col.name in seen_names:
                raise ConfigError(f"Duplicate output column name in configuration: '{col.name}'.")
            seen_names.add(col.name)


def _as_mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"Expected mapping for '{context}'.")
    result: dict[str, object] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            raise ConfigError(f"All keys in '{context}' must be strings, got {k!r}.")
        result[k] = v
    return result


def _req_str(mapping: dict[str, object], key: str, context: str) -> str:
    if key not in mapping or mapping[key] is None:
        raise ConfigError(f"Missing required field '{context}.{key}'.")
    val = mapping[key]
    if not isinstance(val, str):
        raise ConfigError(f"Field '{context}.{key}' must be a string.")
    return val


def _opt_str(mapping: dict[str, object], key: str, default: str, context: str) -> str:
    if key not in mapping or mapping[key] is None:
        return default
    val = mapping[key]
    if not isinstance(val, str):
        raise ConfigError(f"Field '{context}.{key}' must be a string.")
    return val


def _opt_nullable_str(mapping: dict[str, object], key: str, context: str) -> str | None:
    if key not in mapping or mapping[key] is None:
        return None
    val = mapping[key]
    if not isinstance(val, str):
        raise ConfigError(f"Field '{context}.{key}' must be a string or null.")
    return val


def _opt_bool(mapping: dict[str, object], key: str, default: bool, context: str) -> bool:
    if key not in mapping or mapping[key] is None:
        return default
    val = mapping[key]
    if not isinstance(val, bool):
        raise ConfigError(f"Field '{context}.{key}' must be a boolean.")
    return val


def _parse_source_config(raw: object, context: str) -> SourceFileConfig:
    mapping = _as_mapping(raw, context)
    encoding = _opt_str(mapping, "encoding", "utf-8", context)
    delimiter = _opt_str(mapping, "delimiter", ",", context)
    num_fmt_raw = _opt_str(mapping, "number_format", "auto", context)
    number_format = validate_number_format(num_fmt_raw, f"{context}.number_format")
    date_format = _opt_str(mapping, "date_format", "auto", context)

    null_values: tuple[str, ...] = ()
    if "null_values" in mapping and mapping["null_values"] is not None:
        raw_nulls = mapping["null_values"]
        if not isinstance(raw_nulls, list):
            raise ConfigError(f"Field '{context}.null_values' must be a list of strings.")
        parsed_nulls: list[str] = []
        for item in raw_nulls:
            if not isinstance(item, str):
                raise ConfigError(f"Entries in '{context}.null_values' must be strings.")
            parsed_nulls.append(item)
        null_values = tuple(parsed_nulls)

    return SourceFileConfig(
        encoding=encoding,
        delimiter=delimiter,
        number_format=number_format,
        date_format=date_format,
        null_values=null_values,
    )


def _parse_join_config(raw: object) -> JoinConfig:
    mapping = _as_mapping(raw, "join")
    column_a = _req_str(mapping, "column_a", "join")
    column_b = _req_str(mapping, "column_b", "join")
    mode_raw = _opt_str(mapping, "mode", "outer", "join")
    if mode_raw not in VALID_JOIN_MODES:
        raise ConfigError(
            f"join.mode must be one of {VALID_JOIN_MODES}, got {mode_raw!r}."
        )
    return JoinConfig(
        column_a=column_a,
        column_b=column_b,
        mode=cast(JoinMode, mode_raw),
    )


def _parse_output_config(raw: object) -> OutputConfig:
    mapping = _as_mapping(raw, "output")
    encoding = _opt_str(mapping, "encoding", "utf-8", "output")
    delimiter = _opt_str(mapping, "delimiter", ",", "output")
    return OutputConfig(encoding=encoding, delimiter=delimiter)


def _parse_column_rule(
    raw: object, index: int, *, require_lookup_for_normalized: bool
) -> ColumnRule:
    ctx = f"columns[{index}]"
    mapping = _as_mapping(raw, ctx)
    name = _req_str(mapping, "name", ctx)
    source_a = _opt_nullable_str(mapping, "source_a", ctx)
    source_b = _opt_nullable_str(mapping, "source_b", ctx)
    leading_raw = _opt_str(mapping, "leading", "A", ctx)
    if leading_raw not in VALID_SYSTEMS:
        raise ConfigError(
            f"Column '{name}' leading system must be 'A' or 'B', got {leading_raw!r}."
        )
    type_raw = _opt_str(mapping, "type", "str", ctx)
    if type_raw not in VALID_TARGET_TYPES:
        raise ConfigError(
            f"Column '{name}' type must be one of {VALID_TARGET_TYPES}, got {type_raw!r}."
        )
    normalize = _opt_bool(mapping, "normalize", False, ctx)
    lookup = _opt_nullable_str(mapping, "lookup", ctx)

    nf_a_raw = _opt_nullable_str(mapping, "number_format_a", ctx)
    nf_b_raw = _opt_nullable_str(mapping, "number_format_b", ctx)
    nf_a = validate_number_format(nf_a_raw, f"{ctx}.number_format_a") if nf_a_raw else None
    nf_b = validate_number_format(nf_b_raw, f"{ctx}.number_format_b") if nf_b_raw else None

    df_a = _opt_nullable_str(mapping, "date_format_a", ctx)
    df_b = _opt_nullable_str(mapping, "date_format_b", ctx)

    rule = ColumnRule(
        name=name,
        source_a=source_a,
        source_b=source_b,
        leading=cast(SystemId, leading_raw),
        type=cast(TargetType, type_raw),
        normalize=normalize,
        lookup=lookup,
        number_format_a=nf_a,
        number_format_b=nf_b,
        date_format_a=df_a,
        date_format_b=df_b,
    )
    if require_lookup_for_normalized and rule.normalize and rule.lookup is None:
        raise ConfigError(
            f"Column '{rule.name}' has normalize=true but no 'lookup' path configured."
        )
    return rule


def resolve_lookup_path(config_path: Path, lookup_ref: str) -> Path:
    """Resolve a lookup CSV path relative to the directory containing mapping.yaml."""
    candidate = Path(lookup_ref)
    if candidate.is_absolute():
        return candidate
    return config_path.resolve().parent / candidate


def load_config(
    path: Path, *, require_lookup_for_normalized: bool = True
) -> MappingConfig:
    """Load and strictly validate mapping.yaml from disk."""
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
        raw_data: object = yaml.safe_load(text)
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file '{path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML syntax in '{path}': {exc}") from exc

    root = _as_mapping(raw_data, "root")

    raw_version = root.get("version", 1)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise ConfigError(f"Field 'version' must be integer 1, got {raw_version!r}.")

    if "source_a" not in root or root["source_a"] is None:
        raise ConfigError("Missing required section 'source_a'.")
    if "source_b" not in root or root["source_b"] is None:
        raise ConfigError("Missing required section 'source_b'.")
    if "join" not in root or root["join"] is None:
        raise ConfigError("Missing required section 'join'.")
    if "columns" not in root or root["columns"] is None:
        raise ConfigError("Missing required section 'columns'.")

    source_a = _parse_source_config(root["source_a"], "source_a")
    source_b = _parse_source_config(root["source_b"], "source_b")
    join = _parse_join_config(root["join"])
    output = (
        _parse_output_config(root["output"])
        if root.get("output") is not None
        else OutputConfig()
    )

    raw_columns = root["columns"]
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ConfigError("Field 'columns' must be a non-empty list of column rules.")

    columns = tuple(
        _parse_column_rule(
            item,
            idx,
            require_lookup_for_normalized=require_lookup_for_normalized,
        )
        for idx, item in enumerate(raw_columns)
    )

    return MappingConfig(
        version=raw_version,
        source_a=source_a,
        source_b=source_b,
        join=join,
        columns=columns,
        output=output,
    )


def _source_to_dict(src: SourceFileConfig) -> dict[str, object]:
    return {
        "encoding": src.encoding,
        "delimiter": src.delimiter,
        "number_format": src.number_format,
        "date_format": src.date_format,
        "null_values": list(src.null_values),
    }


def _column_to_dict(col: ColumnRule) -> dict[str, object]:
    data: dict[str, object] = {
        "name": col.name,
        "source_a": col.source_a,
        "source_b": col.source_b,
        "leading": col.leading,
        "type": col.type,
    }
    if col.normalize:
        data["normalize"] = True
    if col.lookup is not None:
        data["lookup"] = col.lookup
    if col.number_format_a is not None:
        data["number_format_a"] = col.number_format_a
    if col.number_format_b is not None:
        data["number_format_b"] = col.number_format_b
    if col.date_format_a is not None:
        data["date_format_a"] = col.date_format_a
    if col.date_format_b is not None:
        data["date_format_b"] = col.date_format_b
    return data


def save_config(config: MappingConfig, path: Path) -> None:
    """Serialize a validated MappingConfig to YAML on disk."""
    payload: dict[str, object] = {
        "version": config.version,
        "source_a": _source_to_dict(config.source_a),
        "source_b": _source_to_dict(config.source_b),
        "join": {
            "column_a": config.join.column_a,
            "column_b": config.join.column_b,
            "mode": config.join.mode,
        },
        "output": {
            "encoding": config.output.encoding,
            "delimiter": config.output.delimiter,
        },
        "columns": [_column_to_dict(col) for col in config.columns],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(rendered, encoding="utf-8")
