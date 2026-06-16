from __future__ import annotations

import csv
import gzip
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MASK_RUNNER = (
    REPO_ROOT
    / "scripts"
    / "quant_research"
    / "parallel_1h"
    / "build_tardis_intraday_rolling_pit_monthly_masks.py"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv_gz(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_partition(raw_root: Path, *, data_type: str, symbol: str, current_date: date, rank: int) -> Path:
    exchange = "binance-futures"
    path = (
        raw_root
        / "raw"
        / exchange
        / data_type
        / f"{current_date:%Y}"
        / f"{current_date:%m}"
        / f"{current_date:%d}"
        / f"{symbol}.csv.gz"
    )
    base = datetime(current_date.year, current_date.month, current_date.day, tzinfo=timezone.utc)
    timestamps = [int((base + timedelta(minutes=idx)).timestamp() * 1000) for idx in range(4)]
    price = 1000.0 + rank * 100.0
    scale = float(10 - rank)
    if data_type == "trades":
        _write_csv_gz(
            path,
            ["timestamp", "price", "amount", "side"],
            [
                {
                    "timestamp": timestamp,
                    "price": price + idx,
                    "amount": scale + idx,
                    "side": "buy" if idx % 2 == 0 else "sell",
                }
                for idx, timestamp in enumerate(timestamps)
            ],
        )
    elif data_type == "book_ticker":
        _write_csv_gz(
            path,
            ["timestamp", "bid_price", "ask_price", "bid_amount", "ask_amount"],
            [
                {
                    "timestamp": timestamp,
                    "bid_price": price - 1.0 - idx * 0.1,
                    "ask_price": price + 1.0 + idx * 0.1,
                    "bid_amount": scale + idx,
                    "ask_amount": scale + idx + 0.5,
                }
                for idx, timestamp in enumerate(timestamps)
            ],
        )
    elif data_type == "book_snapshot_5":
        rows = []
        for idx, timestamp in enumerate(timestamps):
            row: dict[str, object] = {"timestamp": timestamp}
            for level in range(5):
                row[f"bid_{level}_price"] = price - 1.0 - level
                row[f"bid_{level}_amount"] = scale + level + idx
                row[f"ask_{level}_price"] = price + 1.0 + level
                row[f"ask_{level}_amount"] = scale + level + idx
            rows.append(row)
        _write_csv_gz(
            path,
            ["timestamp"]
            + [
                f"{side}_{level}_{field}"
                for level in range(5)
                for side in ("bid", "ask")
                for field in ("price", "amount")
            ],
            rows,
        )
    elif data_type == "derivative_ticker":
        _write_csv_gz(
            path,
            ["timestamp", "mark_price", "index_price", "open_interest", "funding_rate"],
            [
                {
                    "timestamp": timestamp,
                    "mark_price": price + idx,
                    "index_price": price + idx - 1.0,
                    "open_interest": 1000.0 + scale * 100.0 + idx,
                    "funding_rate": 0.0001,
                }
                for idx, timestamp in enumerate(timestamps)
            ],
        )
    elif data_type == "liquidations":
        _write_csv_gz(
            path,
            ["timestamp", "price", "amount", "side"],
            [
                {
                    "timestamp": timestamp,
                    "price": price + idx,
                    "amount": 0.01,
                    "side": "sell",
                }
                for idx, timestamp in enumerate(timestamps)
            ],
        )
    else:
        raise AssertionError(data_type)
    return path


def test_monthly_mask_runner_builds_stage_a_eligible_masks_from_pre_freeze_raw_metrics(tmp_path: Path) -> None:
    dry_run_root = tmp_path / "dry_run"
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "masks"
    manifest_dir = tmp_path / "manifests"
    dry_run_root.mkdir(parents=True)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    months = [
        {
            "evaluation_month": "2025-01",
            "freeze_date": "2024-12-31",
            "selection_lookback_start": "2024-12-30",
            "selection_lookback_end": "2024-12-31",
            "selection_lookback_day_count": 2,
            "evaluation_start": "2025-01-01",
            "evaluation_end": "2025-01-02",
            "evaluation_day_count": 2,
        },
        {
            "evaluation_month": "2025-02",
            "freeze_date": "2025-01-31",
            "selection_lookback_start": "2025-01-30",
            "selection_lookback_end": "2025-01-31",
            "selection_lookback_day_count": 2,
            "evaluation_start": "2025-02-01",
            "evaluation_end": "2025-02-02",
            "evaluation_day_count": 2,
        },
    ]
    (dry_run_root / "rolling_pit_core_monthly_freeze_plan.json").write_text(
        json.dumps({"months": months}, indent=2),
        encoding="utf-8",
    )
    (dry_run_root / "rolling_pit_core_candidate_pool_audit.json").write_text(
        json.dumps({"candidate_seed_symbols": symbols}, indent=2),
        encoding="utf-8",
    )
    (dry_run_root / "rolling_pit_core_raw_staging_manifest.json").write_text(
        json.dumps({"candidate_seed_symbols": symbols}, indent=2),
        encoding="utf-8",
    )

    partitions = []
    ranks = {symbol: idx + 1 for idx, symbol in enumerate(symbols)}
    for month in months:
        selection_dates = [
            date.fromisoformat(month["selection_lookback_start"]),
            date.fromisoformat(month["selection_lookback_end"]),
        ]
        evaluation_dates = [
            date.fromisoformat(month["evaluation_start"]),
            date.fromisoformat(month["evaluation_end"]),
        ]
        for symbol in symbols:
            for current_date in selection_dates:
                for data_type in ("trades", "book_ticker", "book_snapshot_5", "derivative_ticker"):
                    path = _write_partition(raw_root, data_type=data_type, symbol=symbol, current_date=current_date, rank=ranks[symbol])
                    partitions.append(
                        {
                            "date": current_date.isoformat(),
                            "symbol": symbol,
                            "data_type": data_type,
                            "url_path": f"binance-futures/{data_type}/{current_date:%Y/%m/%d}/{symbol}.csv.gz",
                            "path": str(path),
                            "action": "downloaded",
                            "completed": True,
                            "downloaded": True,
                            "size_bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                    )
            for current_date in evaluation_dates:
                for data_type in ("trades", "liquidations", "book_ticker", "book_snapshot_5", "derivative_ticker"):
                    path = _write_partition(raw_root, data_type=data_type, symbol=symbol, current_date=current_date, rank=ranks[symbol])
                    partitions.append(
                        {
                            "date": current_date.isoformat(),
                            "symbol": symbol,
                            "data_type": data_type,
                            "url_path": f"binance-futures/{data_type}/{current_date:%Y/%m/%d}/{symbol}.csv.gz",
                            "path": str(path),
                            "action": "downloaded",
                            "completed": True,
                            "downloaded": True,
                            "size_bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                    )
    raw_manifest = manifest_dir / "raw.json"
    raw_manifest.parent.mkdir(parents=True)
    raw_manifest.write_text(
        json.dumps(
            {
                "exchange": "binance-futures",
                "candidate_seed_symbols": symbols,
                "partitions": partitions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(MASK_RUNNER),
            "--as-of",
            "unit-test-monthly-masks",
            "--dry-run-root",
            str(dry_run_root),
            "--raw-root",
            str(raw_root),
            "--raw-staging-manifest",
            str(raw_manifest),
            "--target-symbols",
            "3",
            "--min-symbols",
            "3",
            "--min-non-btc-eth-symbols",
            "1",
            "--min-liquidity-buckets",
            "3",
            "--distinct-months-min",
            "2",
            "--selection-lookback-min-days",
            "2",
            "--chunksize",
            "2",
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    summary = json.loads((output_root / "rolling_pit_core_stage_a_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "stage_a_monthly_universe_masks_ready"
    assert summary["stage_a_monthly_universe_masks_ready"] is True
    assert summary["stage_a_proof_computed"] is False
    assert summary["strategy_pnl_computed"] is False
    assert summary["trading_action_authorized"] is False
    assert summary["raw_scan_executed_by_runner"] is True
    assert summary["downloads_executed_by_runner"] is False

    jan_mask = json.loads(
        (output_root / "monthly_freezes" / "2025-01" / "monthly_universe_mask.json").read_text(encoding="utf-8")
    )
    assert jan_mask["stage_a_monthly_universe_mask_ready"] is True
    assert jan_mask["future_data_used_for_selection"] is False
    assert jan_mask["label_free_selection_assertion"] is True
    assert set(["BTCUSDT", "ETHUSDT"]).issubset(jan_mask["selected_symbols"])
    assert len(set(jan_mask["liquidity_buckets_by_symbol"].values())) == 3

    masks = json.loads((output_root / "rolling_pit_core_monthly_universe_masks.json").read_text(encoding="utf-8"))
    assert len(masks["monthly_masks"]) == 2
    assert masks["stage_a_monthly_universe_masks_ready"] is True
