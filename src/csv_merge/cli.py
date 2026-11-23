"""Command-line interface entry point for csv-merge."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from csv_merge.config import CsvMergeError, JoinMode, load_config
from csv_merge.inspector import run_init
from csv_merge.merger import reconcile
from csv_merge.reporter import format_reconciliation_summary, write_all_reports


def build_parser() -> argparse.ArgumentParser:
    """Construct the root argparse CLI parser with init and run subcommands."""
    parser = argparse.ArgumentParser(
        prog="csv-merge",
        description="Universal configuration-driven CSV reconciliation and merge CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Inspect two CSV files and generate starter mapping.yaml and lookup templates.",
    )
    init_parser.add_argument(
        "--file-a",
        type=Path,
        required=True,
        help="Path to System A input CSV file.",
    )
    init_parser.add_argument(
        "--file-b",
        type=Path,
        required=True,
        help="Path to System B input CSV file.",
    )
    init_parser.add_argument(
        "--config",
        type=Path,
        default=Path("mapping.yaml"),
        help="Output path for starter mapping.yaml (default: mapping.yaml).",
    )
    init_parser.add_argument(
        "--lookups-dir",
        type=Path,
        default=Path("lookups"),
        help="Directory for generated 3-column lookup CSV templates (default: lookups).",
    )
    init_parser.add_argument(
        "--normalize",
        action="append",
        default=[],
        help="Column name(s) to mark for value normalization (repeatable or comma-separated).",
    )
    init_parser.add_argument(
        "--update-lookups",
        action="store_true",
        help="Read existing --config and generate missing lookup CSV templates.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing mapping.yaml and/or lookup CSV files.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Reconcile and merge two CSV files using a mapping.yaml configuration.",
    )
    run_parser.add_argument(
        "--file-a",
        type=Path,
        required=True,
        help="Path to System A input CSV file.",
    )
    run_parser.add_argument(
        "--file-b",
        type=Path,
        required=True,
        help="Path to System B input CSV file.",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to mapping.yaml configuration file.",
    )
    run_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path for merged.csv.",
    )
    run_parser.add_argument(
        "--join",
        choices=("outer", "left", "inner"),
        default=None,
        help="Optional override for configured join mode (outer, left, inner).",
    )
    run_parser.add_argument(
        "--unmapped-output",
        type=Path,
        default=None,
        help="Destination path for unmapped_values.csv (default: beside --output).",
    )
    run_parser.add_argument(
        "--errors-output",
        type=Path,
        default=None,
        help="Destination path for errors.csv (default: beside --output).",
    )

    return parser


def _handle_init(args: argparse.Namespace) -> int:
    result = run_init(
        args.file_a,
        args.file_b,
        config_path=args.config,
        lookups_dir=args.lookups_dir,
        normalize_columns=args.normalize,
        update_lookups=args.update_lookups,
        force=args.force,
    )
    print(
        f"File A: encoding={result.inspection_a.encoding}, "
        f"delimiter={result.inspection_a.delimiter!r}, "
        f"columns={len(result.inspection_a.headers)}"
    )
    print(
        f"File B: encoding={result.inspection_b.encoding}, "
        f"delimiter={result.inspection_b.delimiter!r}, "
        f"columns={len(result.inspection_b.headers)}"
    )
    status = "Wrote" if result.config_written else "Preserved"
    print(f"{status} config: {result.config_path}")
    for lookup_path in result.lookup_paths:
        print(f"Generated lookup template: {lookup_path}")
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    join_override: JoinMode | None = args.join
    effective_join = join_override if join_override is not None else config.join.mode
    result = reconcile(
        args.file_a,
        args.file_b,
        config,
        config_path=args.config,
        join_mode_override=join_override,
    )
    merged_path, unmapped_path, errors_path = write_all_reports(
        result,
        args.output,
        config.output,
        unmapped_path=args.unmapped_output,
        errors_path=args.errors_output,
    )
    print(
        format_reconciliation_summary(
            result,
            join_mode=effective_join,
            merged_path=merged_path,
            unmapped_path=unmapped_path,
            errors_path=errors_path,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main entry point returning POSIX exit status codes."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "init":
            return _handle_init(args)
        if args.command == "run":
            return _handle_run(args)
        raise CsvMergeError(f"Unsupported command: {args.command}")
    except (CsvMergeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
