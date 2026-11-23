"""End-to-end CLI tests across distinct domains, anomalies, exit codes, and 50k-row scale."""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from pathlib import Path

import pytest

from csv_merge.cli import main
from csv_merge.config import load_config, save_config


def test_e2e_domain_one_inventory_catalog_with_anomalies_and_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Domain 1: Inventory/Catalog exports with cp1252/semicolon vs UTF-8/comma & anomalies."""
    data_dir = tmp_path / "inputs"
    cfg_dir = tmp_path / "configs"
    out_dir = tmp_path / "outputs"
    other_cwd = tmp_path / "runner_cwd"
    data_dir.mkdir()
    cfg_dir.mkdir()
    other_cwd.mkdir()

    file_a = data_dir / "warehouse_eu.csv"
    file_a.write_bytes(
        (
            "sku_code;item_title;stock_qty;unit_price;restock_date;in_stock;cat_code\n"
            '  SKU-100 ;"Widget; ""Pro""\nLine2";1.000;1.250,50;23.11.2026;Ja;AVAIL\n'
            "sku-100;DuplicateRow;5;10,00;01.01.2026;Nein;AVAIL\n"
            " ;BlankIdRow;1;5,00;02.01.2026;Ja;AVAIL\n"
            "SKU-200;Gadget Köln;25;49,95;bad-date;Ja;DISC\n"
            "SKU-300;A-Only Item;10;15,00;15.05.2026;Nein;UNKNOWN_A\n"
        ).encode("cp1252")
    )

    file_b = data_dir / "erp_us.csv"
    file_b.write_text(
        "sku_code,item_title,stock_qty,unit_price,restock_date,in_stock,cat_code\n"
        "sku-100,Widget US,999,\"2,345.67\",2026-11-23,true,In Stock\n"
        "SKU-200,Gadget Cologne,25,49.95,11/30/2026,true,Discontinued\n"
        "SKU-400,B-Only Sensor,3,\"1,100.00\",12/01/2026,false,PendingNew\n",
        encoding="utf-8",
    )

    cfg_path = cfg_dir / "mapping.yaml"
    assert (
        main(
            [
                "init",
                "--file-a",
                str(file_a),
                "--file-b",
                str(file_b),
                "--config",
                str(cfg_path),
                "--normalize",
                "cat_code",
            ]
        )
        == 0
    )

    # Populate generated 3-column lookup CSV
    lookup_csv = cfg_dir / "lookups" / "cat_code.csv"
    assert lookup_csv.is_file()
    lookup_csv.write_text(
        "source_a_value,source_b_value,unified_value\n"
        "AVAIL,In Stock,AVAILABLE\n"
        "DISC,Discontinued,DISCONTINUED\n"
        ",PendingNew,\n",
        encoding="utf-8",
    )

    # Customize config: reorder columns and enforce target type 'date' on restock_date
    cfg = load_config(cfg_path)
    from dataclasses import replace

    reordered = (
        cfg.columns[0],
        cfg.columns[6],  # cat_code
        replace(cfg.columns[4], type="date"),  # restock_date (leading A)
        cfg.columns[3],  # unit_price
        cfg.columns[2],  # stock_qty
        cfg.columns[5],  # in_stock
        cfg.columns[1],  # item_title
    )

    save_config(replace(cfg, columns=reordered), cfg_path)

    # Execute from an unrelated working directory so relative lookup resolution is exercised
    monkeypatch.chdir(other_cwd)
    capsys.readouterr()

    merged_out = out_dir / "merged.csv"
    rc = main(
        [
            "run",
            "--file-a",
            str(file_a),
            "--file-b",
            str(file_b),
            "--config",
            str(cfg_path),
            "--output",
            str(merged_out),
        ]
    )
    assert rc == 0

    summary_out = capsys.readouterr().out
    assert "Join mode:                outer" in summary_out
    assert "Matched records:          2" in summary_out
    assert "System A only records:    1" in summary_out
    assert "System B only records:    1" in summary_out
    assert "Output rows written:      4" in summary_out
    assert "Intra-file duplicate IDs: 1" in summary_out
    assert "Missing/blank IDs:        1" in summary_out
    assert "Unmapped lookup values:   2 (2 distinct)" in summary_out
    assert "Type conversion errors:   1" in summary_out

    with merged_out.open("r", encoding="utf-8", newline="") as fh:
        merged_rows = list(csv.reader(fh))

    assert merged_rows[0] == [
        "sku_code",
        "cat_code",
        "restock_date",
        "unit_price",
        "stock_qty",
        "in_stock",
        "item_title",
    ]
    assert merged_rows[1] == [
        "SKU-100",
        "AVAILABLE",
        "2026-11-23",
        "1250.5",
        "1000",
        "true",
        'Widget; "Pro"\nLine2',
    ]
    # SKU-200 leading A has bad-date -> empty cell (no fallback to System B's 2026-11-30)
    assert merged_rows[2] == [
        "SKU-200",
        "DISCONTINUED",
        "",
        "49.95",
        "25",
        "true",
        "Gadget Köln",
    ]
    assert merged_rows[3] == [
        "SKU-300",
        "UNKNOWN_A",
        "2026-05-15",
        "15",
        "10",
        "false",
        "A-Only Item",
    ]
    assert merged_rows[4] == [
        "SKU-400",
        "PendingNew",
        "2026-12-01",
        "1100",
        "3",
        "false",
        "B-Only Sensor",
    ]

    with (out_dir / "unmapped_values.csv").open("r", encoding="utf-8", newline="") as fh:
        unmapped_rows = list(csv.reader(fh))
    assert unmapped_rows == [
        ["system", "column", "raw_value", "occurrence_count", "sample_record_id"],
        ["A", "cat_code", "UNKNOWN_A", "1", "SKU-300"],
        ["B", "cat_code", "PendingNew", "1", "SKU-400"],
    ]

    with (out_dir / "errors.csv").open("r", encoding="utf-8", newline="") as fh:
        error_rows = list(csv.reader(fh))
    assert [r[0] for r in error_rows[1:]] == ["duplicate_id", "missing_id", "type_conversion"]

    # Join overrides: left and inner
    left_out = out_dir / "left.csv"
    assert (
        main(
            [
                "run",
                "--file-a",
                str(file_a),
                "--file-b",
                str(file_b),
                "--config",
                str(cfg_path),
                "--output",
                str(left_out),
                "--join",
                "left",
            ]
        )
        == 0
    )
    with left_out.open("r", encoding="utf-8", newline="") as fh:
        assert len(list(csv.reader(fh))) == 4  # header + 3 rows

    inner_out = out_dir / "inner.csv"
    assert (
        main(
            [
                "run",
                "--file-a",
                str(file_a),
                "--file-b",
                str(file_b),
                "--config",
                str(cfg_path),
                "--output",
                str(inner_out),
                "--join",
                "inner",
            ]
        )
        == 0
    )
    with inner_out.open("r", encoding="utf-8", newline="") as fh:
        assert len(list(csv.reader(fh))) == 3  # header + 2 matched rows


def test_e2e_domain_two_ledger_and_exit_codes(tmp_path: Path) -> None:
    """Domain 2: Completely distinct ledger schema proving domain-agnosticism & exit codes."""
    ledger_a = tmp_path / "ledger_a.tsv"
    ledger_a.write_bytes(
        b"\xef\xbb\xbfaccount_ref\tcost_center\tfunding_eur\tclose_day\treconciled\n"
        b" ACC-10 \tCC-ENG\t2.500,00\t15.08.2026\twahr\n"
        b"ACC-20\tCC-OPS\t750,25\t01.09.2026\tfalsch\n"
    )
    ledger_b = tmp_path / "ledger_b.pipe"
    ledger_b.write_text(
        "acct_id|dept_code|funding_usd|close_day|reconciled\n"
        "acc-10|Engineering|9999.00|2026-08-15|false\n"
        "ACC-30|Sales|1200.50|2026-10-05|true\n",
        encoding="utf-8",
    )

    cfg_path = tmp_path / "ledger_mapping.yaml"
    cfg_path.write_text(
        """
version: 1
source_a:
  encoding: utf-8-sig
  delimiter: "\t"
  number_format: eu
  date_format: eu
source_b:
  encoding: utf-8
  delimiter: "|"
  number_format: us
  date_format: iso
join:
  column_a: account_ref
  column_b: acct_id
  mode: outer
columns:
  - name: account_key
    source_a: account_ref
    source_b: acct_id
    leading: A
    type: str
  - name: department
    source_a: cost_center
    source_b: dept_code
    leading: B
    type: str
    normalize: true
    lookup: dept_lookup.csv
  - name: budget_amount
    source_a: funding_eur
    source_b: funding_usd
    leading: A
    type: float
  - name: closing_date
    source_a: close_day
    source_b: close_day
    leading: B
    type: date
  - name: is_reconciled
    source_a: reconciled
    source_b: reconciled
    leading: A
    type: bool
""".strip(),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "init",
                "--file-a",
                str(ledger_a),
                "--file-b",
                str(ledger_b),
                "--config",
                str(cfg_path),
                "--update-lookups",
            ]
        )
        == 0
    )

    lookup_file = tmp_path / "dept_lookup.csv"
    assert lookup_file.is_file()
    lookup_file.write_text(
        "source_a_value,source_b_value,unified_value\n"
        "CC-ENG,Engineering,ENGINEERING\n"
        "CC-OPS,Operations,OPERATIONS\n"
        ",Sales,SALES\n",
        encoding="utf-8",
    )

    out_csv = tmp_path / "ledger_merged.csv"
    assert (
        main(
            [
                "run",
                "--file-a",
                str(ledger_a),
                "--file-b",
                str(ledger_b),
                "--config",
                str(cfg_path),
                "--output",
                str(out_csv),
            ]
        )
        == 0
    )

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["account_key", "department", "budget_amount", "closing_date", "is_reconciled"],
        ["ACC-10", "ENGINEERING", "2500", "2026-08-15", "true"],
        ["ACC-20", "OPERATIONS", "750.25", "2026-09-01", "false"],
        ["ACC-30", "SALES", "1200.5", "2026-10-05", "true"],
    ]

    # Fatal config error returns exit code 1
    assert (
        main(
            [
                "run",
                "--file-a",
                str(ledger_a),
                "--file-b",
                str(ledger_b),
                "--config",
                str(tmp_path / "missing_config.yaml"),
                "--output",
                str(out_csv),
            ]
        )
        == 1
    )

    # Invalid CLI syntax raises SystemExit(2)
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--unknown-flag"])
    assert exc_info.value.code == 2

    # Verify module entry point works cleanly via subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "csv_merge.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "csv-merge" in proc.stdout


def test_scale_50k_rows_performance(tmp_path: Path) -> None:
    """Verify SC-001 (<5s init) and SC-002 (<15s run) on 50,000 rows per file."""
    row_count = 50_000
    file_a = tmp_path / "scale_a.csv"
    file_b = tmp_path / "scale_b.csv"

    with file_a.open("w", encoding="utf-8", newline="") as fh_a:
        fh_a.write("rec_id;tier;qty;amount;dt;active\n")
        for i in range(row_count):
            tier = "GOLD" if i % 2 == 0 else "STD"
            fh_a.write(
                f"ID-{i:06d};{tier};{i};1.250,50;23.11.2026;Ja\n"
            )

    with file_b.open("w", encoding="utf-8", newline="") as fh_b:
        fh_b.write("rec_id,tier,qty,amount,dt,active\n")
        for i in range(row_count):
            tier = "Gold" if i % 2 == 0 else "Standard"
            fh_b.write(
                f"id-{i:06d},{tier},{i},1250.50,2026-11-23,true\n"
            )

    cfg_path = tmp_path / "scale_mapping.yaml"
    t0 = time.perf_counter()
    rc_init = main(
        [
            "init",
            "--file-a",
            str(file_a),
            "--file-b",
            str(file_b),
            "--config",
            str(cfg_path),
            "--normalize",
            "tier",
        ]
    )
    init_elapsed = time.perf_counter() - t0
    assert rc_init == 0
    assert init_elapsed < 5.0, f"init took {init_elapsed:.2f}s (budget <5.0s)"

    lookup_path = tmp_path / "lookups" / "tier.csv"
    lookup_path.write_text(
        "source_a_value,source_b_value,unified_value\n"
        "GOLD,Gold,GOLD\n"
        "STD,Standard,STANDARD\n",
        encoding="utf-8",
    )

    out_path = tmp_path / "scale_merged.csv"
    t1 = time.perf_counter()
    rc_run = main(
        [
            "run",
            "--file-a",
            str(file_a),
            "--file-b",
            str(file_b),
            "--config",
            str(cfg_path),
            "--output",
            str(out_path),
        ]
    )
    run_elapsed = time.perf_counter() - t1
    assert rc_run == 0
    assert run_elapsed < 15.0, f"run took {run_elapsed:.2f}s (budget <15.0s)"

    with out_path.open("r", encoding="utf-8") as fh_out:
        line_total = sum(1 for _ in fh_out)
    assert line_total == row_count + 1
