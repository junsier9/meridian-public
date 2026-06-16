from __future__ import annotations

import csv
import gzip
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = (
    REPO_ROOT
    / "scripts"
    / "quant_research"
    / "parallel_1h"
    / "normalize_tardis_intraday_liquidity_shock_raw_to_parquet.py"
)
STAGE_A_RUNNER = (
    REPO_ROOT
    / "scripts"
    / "quant_research"
    / "parallel_1h"
    / "run_tardis_intraday_liquidity_shock_impulse_stage_a.py"
)


def _write_csv_gz(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_raw_fixture(raw_root: Path, *, symbol: str = "BTCUSDT", day: str = "2026-06-13") -> None:
    exchange = "binance-futures"
    base_date = datetime.fromisoformat(day)
    base = datetime(base_date.year, base_date.month, base_date.day, tzinfo=timezone.utc)
    timestamps = [int((base + timedelta(minutes=5 * idx)).timestamp() * 1000) for idx in range(120)]

    trades = []
    liquidations = []
    book_ticker = []
    derivative_ticker = []
    book_snapshot = []
    for idx, timestamp in enumerate(timestamps):
        price = 100_000.0 + idx * 5.0
        amount = 1.0 + (idx % 7) * 0.1
        trades.append(
            {
                "timestamp": timestamp,
                "price": price,
                "amount": amount,
                "side": "buy" if idx % 2 == 0 else "sell",
            }
        )
        liquidations.append(
            {
                "timestamp": timestamp,
                "price": price,
                "amount": amount * (6.0 if idx % 9 == 0 else 0.05),
                "side": "sell" if idx % 9 == 0 else "buy",
            }
        )
        book_ticker.append(
            {
                "timestamp": timestamp,
                "bid_price": price - 1.0,
                "ask_price": price + 1.0,
                "bid_amount": 5.0 + idx % 3,
                "ask_amount": 4.0 + idx % 4,
            }
        )
        derivative_ticker.append(
            {
                "timestamp": timestamp,
                "mark_price": price,
                "index_price": price - 2.0,
                "open_interest": 10_000.0 + idx * 10.0,
                "funding_rate": 0.0001,
            }
        )
        snapshot_row: dict[str, object] = {"timestamp": timestamp}
        for level in range(5):
            snapshot_row[f"bid_{level}_price"] = price - 1.0 - level
            snapshot_row[f"bid_{level}_amount"] = 10.0 + level
            snapshot_row[f"ask_{level}_price"] = price + 1.0 + level
            snapshot_row[f"ask_{level}_amount"] = 9.0 + level
        book_snapshot.append(snapshot_row)

    rows_by_type = {
        "trades": (["timestamp", "price", "amount", "side"], trades),
        "liquidations": (["timestamp", "price", "amount", "side"], liquidations),
        "book_ticker": (
            ["timestamp", "bid_price", "ask_price", "bid_amount", "ask_amount"],
            book_ticker,
        ),
        "derivative_ticker": (
            ["timestamp", "mark_price", "index_price", "open_interest", "funding_rate"],
            derivative_ticker,
        ),
        "book_snapshot_5": (
            ["timestamp"]
            + [
                f"{side}_{level}_{field}"
                for level in range(5)
                for side in ("bid", "ask")
                for field in ("price", "amount")
            ],
            book_snapshot,
        ),
    }
    for data_type, (fieldnames, rows) in rows_by_type.items():
        path = (
            raw_root
            / "raw"
            / exchange
            / data_type
            / f"{base:%Y}"
            / f"{base:%m}"
            / f"{base:%d}"
            / f"{symbol}.csv.gz"
        )
        _write_csv_gz(path, fieldnames, rows)


def test_tardis_intraday_stage_a_requires_columnar_staging(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw_store"
    normalized_root = tmp_path / "columnar_store"
    output_root = tmp_path / "stage_a"
    _write_raw_fixture(raw_root)

    normalizer_result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER),
            "--as-of",
            "columnar-test",
            "--from-date",
            "2026-06-13",
            "--to-date",
            "2026-06-13",
            "--symbols",
            "BTCUSDT",
            "--raw-root",
            str(raw_root),
            "--normalized-root",
            str(normalized_root),
            "--event-bar-minutes",
            "5",
            "--chunksize",
            "50",
            "--compression",
            "snappy",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert normalizer_result.returncode == 0, normalizer_result.stderr
    manifest_path = normalized_root / "manifests" / "columnar-test.json"
    assert manifest_path.exists()

    rejected_raw_result = subprocess.run(
        [
            sys.executable,
            str(STAGE_A_RUNNER),
            "--as-of",
            "raw-rejected-test",
            "--from-date",
            "2026-06-13",
            "--to-date",
            "2026-06-13",
            "--symbols",
            "BTCUSDT",
            "--raw-root",
            str(raw_root),
            "--output-root",
            str(tmp_path / "rejected"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected_raw_result.returncode != 0
    assert "--raw-root is no longer accepted" in rejected_raw_result.stderr

    stage_a_result = subprocess.run(
        [
            sys.executable,
            str(STAGE_A_RUNNER),
            "--as-of",
            "columnar-test",
            "--from-date",
            "2026-06-13",
            "--to-date",
            "2026-06-13",
            "--symbols",
            "BTCUSDT",
            "--normalized-root",
            str(normalized_root),
            "--normalized-manifest",
            str(manifest_path),
            "--output-root",
            str(output_root),
            "--lookback-bars",
            "3",
            "--min-lookback-bars",
            "1",
            "--shuffle-iterations",
            "2",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stage_a_result.returncode == 0, stage_a_result.stderr
    summary = json.loads((output_root / "intraday_liquidity_shock_summary.json").read_text())
    assert summary["input_mode"] == "normalized_parquet_only"
    assert summary["downloads_executed_by_runner"] is False
    assert summary["raw_scan_executed_by_runner"] is False
    assert "raw_input_paths" not in summary
    assert summary["event_counts"]["bars"] == 120
    assert (output_root / "intraday_liquidity_shock_profile.json").exists()


def test_tardis_intraday_columnar_pipeline_respects_monthly_universe_masks(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw_store"
    normalized_root = tmp_path / "columnar_store"
    output_root = tmp_path / "stage_a_masked"
    _write_raw_fixture(raw_root, symbol="BTCUSDT", day="2026-06-13")
    _write_raw_fixture(raw_root, symbol="ETHUSDT", day="2026-07-01")

    masks_path = tmp_path / "monthly_masks.json"
    masks_path.write_text(
        json.dumps(
            {
                "contract_version": "quant_tardis_intraday_rolling_pit_monthly_masks.v1",
                "artifact_kind": "rolling_pit_core_monthly_universe_masks",
                "stage_a_monthly_universe_masks_ready": True,
                "monthly_masks": [
                    {
                        "evaluation_month": "2026-06",
                        "freeze_date": "2026-05-31",
                        "evaluation_start": "2026-06-13",
                        "evaluation_end": "2026-06-13",
                        "selected_symbols": ["BTCUSDT"],
                        "stage_a_monthly_universe_mask_ready": True,
                        "future_data_used_for_selection": False,
                        "label_free_selection_assertion": True,
                    },
                    {
                        "evaluation_month": "2026-07",
                        "freeze_date": "2026-06-30",
                        "evaluation_start": "2026-07-01",
                        "evaluation_end": "2026-07-01",
                        "selected_symbols": ["ETHUSDT"],
                        "stage_a_monthly_universe_mask_ready": True,
                        "future_data_used_for_selection": False,
                        "label_free_selection_assertion": True,
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    normalizer_result = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER),
            "--as-of",
            "columnar-monthly-mask-test",
            "--from-date",
            "2026-06-13",
            "--to-date",
            "2026-07-01",
            "--symbols",
            "BTCUSDT,ETHUSDT",
            "--monthly-universe-masks",
            str(masks_path),
            "--raw-root",
            str(raw_root),
            "--normalized-root",
            str(normalized_root),
            "--event-bar-minutes",
            "5",
            "--chunksize",
            "50",
            "--compression",
            "snappy",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert normalizer_result.returncode == 0, normalizer_result.stderr
    manifest_path = normalized_root / "manifests" / "columnar-monthly-mask-test.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["expected_normalized_partition_count"] == 2
    assert manifest["normalized_partition_count"] == 2
    assert manifest["required_symbol_date_count"] == 2
    assert manifest["monthly_mask_context"]["evaluation_month_count"] == 2
    normalized_pairs = {
        (item["symbol"], item["date"])
        for item in manifest["normalized_partitions"]
    }
    assert normalized_pairs == {("BTCUSDT", "2026-06-13"), ("ETHUSDT", "2026-07-01")}

    stage_a_result = subprocess.run(
        [
            sys.executable,
            str(STAGE_A_RUNNER),
            "--as-of",
            "columnar-monthly-mask-test",
            "--from-date",
            "2026-06-13",
            "--to-date",
            "2026-07-01",
            "--symbols",
            "BTCUSDT,ETHUSDT",
            "--monthly-universe-masks",
            str(masks_path),
            "--normalized-root",
            str(normalized_root),
            "--normalized-manifest",
            str(manifest_path),
            "--output-root",
            str(output_root),
            "--lookback-bars",
            "3",
            "--min-lookback-bars",
            "1",
            "--shuffle-iterations",
            "2",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stage_a_result.returncode == 0, stage_a_result.stderr
    summary = json.loads((output_root / "intraday_liquidity_shock_summary.json").read_text())
    assert summary["input_mode"] == "normalized_parquet_only"
    assert summary["raw_scan_executed_by_runner"] is False
    assert summary["downloads_executed_by_runner"] is False
    assert summary["profile"]["input_counts"]["expected_columnar_partitions"] == 2
    assert summary["profile"]["input_counts"]["found_columnar_partitions"] == 2
    assert summary["monthly_mask_context"]["required_symbol_date_count"] == 2
