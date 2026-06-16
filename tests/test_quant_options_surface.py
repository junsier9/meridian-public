from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pandas as pd

from enhengclaw.quant_research.options_surface import (
    FACTOR_COLUMNS,
    build_options_surface_feature_panel,
    load_ohlcv_realized_vol_panel,
    summarize_options_surface_feature_panel,
)
from scripts.quant_research.build_tardis_deribit_options_surface_features import (
    main as build_main,
)


FIELDNAMES = [
    "exchange",
    "symbol",
    "timestamp",
    "local_timestamp",
    "type",
    "strike_price",
    "expiration",
    "open_interest",
    "last_price",
    "bid_price",
    "bid_amount",
    "bid_iv",
    "ask_price",
    "ask_amount",
    "ask_iv",
    "mark_price",
    "mark_iv",
    "underlying_index",
    "underlying_price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
]
OHLCV_FIELDNAMES = [
    "exchange",
    "market_type",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "source",
]


def _row(
    *,
    under: str,
    timestamp: int,
    expiration: int,
    option_type: str,
    delta: float,
    strike: float,
    mark_iv: float,
    underlying_price: float,
) -> dict[str, object]:
    return {
        "exchange": "deribit",
        "symbol": f"{under}-28JUN24-{int(strike)}-{option_type[0].upper()}",
        "timestamp": timestamp,
        "local_timestamp": timestamp + 1_000_000,
        "type": option_type,
        "strike_price": strike,
        "expiration": expiration,
        "open_interest": 12.5,
        "last_price": 0.02,
        "bid_price": 0.019,
        "bid_amount": 1.0,
        "bid_iv": mark_iv - 1.0,
        "ask_price": 0.021,
        "ask_amount": 1.5,
        "ask_iv": mark_iv + 1.0,
        "mark_price": 0.02,
        "mark_iv": mark_iv,
        "underlying_index": f"SYN.{under}-28JUN24",
        "underlying_price": underlying_price,
        "delta": delta,
        "gamma": 0.0002,
        "vega": 1.2,
        "theta": -0.4,
        "rho": 0.01,
    }


def _fixture_rows() -> list[dict[str, object]]:
    timestamp_1 = int(pd.Timestamp("2024-06-01T00:00:00Z").timestamp() * 1_000_000)
    timestamp_2 = int(pd.Timestamp("2024-06-01T01:00:00Z").timestamp() * 1_000_000)
    front_expiration = int(pd.Timestamp("2024-06-28T08:00:00Z").timestamp() * 1_000_000)
    mid_expiration = int(pd.Timestamp("2024-07-26T08:00:00Z").timestamp() * 1_000_000)
    rows = []
    for under, spot_1, spot_2, strike in [("BTC", 66000.0, 66660.0, 65000.0), ("ETH", 3600.0, 3636.0, 3500.0)]:
        for timestamp, spot in [(timestamp_1, spot_1), (timestamp_2, spot_2)]:
            rows.extend(
                [
                    _row(
                        under=under,
                        timestamp=timestamp,
                        expiration=front_expiration,
                        option_type="call",
                        delta=0.25,
                        strike=strike * 1.08,
                        mark_iv=58.0,
                        underlying_price=spot,
                    ),
                    _row(
                        under=under,
                        timestamp=timestamp,
                        expiration=front_expiration,
                        option_type="put",
                        delta=-0.25,
                        strike=strike * 0.92,
                        mark_iv=64.0,
                        underlying_price=spot,
                    ),
                    _row(
                        under=under,
                        timestamp=timestamp,
                        expiration=front_expiration,
                        option_type="call",
                        delta=0.50,
                        strike=strike,
                        mark_iv=60.0,
                        underlying_price=spot,
                    ),
                    _row(
                        under=under,
                        timestamp=timestamp,
                        expiration=mid_expiration,
                        option_type="put",
                        delta=-0.50,
                        strike=strike,
                        mark_iv=55.0,
                        underlying_price=spot,
                    ),
                ]
            )
    return rows


def _write_gzip_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_green_probe_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "contract_version": "quant_m3_1_tardis_deribit_options_surface_probe.v1",
                "phase0_decision": {
                    "authenticated_key_accepted": True,
                    "feature_builder_allowed": True,
                    "m3_1_tardis_options_surface_phase0_ready": True,
                    "raw_sample_retained": False,
                    "manifest_mutation_authorized": False,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_ohlcv_cache(root: Path) -> None:
    for under, symbol, base in [("BTC", "BTCUSDT", 66000.0), ("ETH", "ETHUSDT", 3600.0)]:
        del under
        rows = []
        for index, dt in enumerate(pd.date_range("2024-05-01", "2024-06-01", tz="UTC", freq="1D")):
            open_time_ms = int(dt.timestamp() * 1000)
            close = base * (1.0 + index * 0.002)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": "spot",
                    "symbol": symbol,
                    "interval": "1d",
                    "open_time_ms": open_time_ms,
                    "close_time_ms": open_time_ms + 86_399_999,
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 1000.0,
                    "quote_volume": close * 1000.0,
                    "trade_count": 100,
                    "taker_buy_base_volume": 500.0,
                    "taker_buy_quote_volume": close * 500.0,
                    "source": "fixture",
                }
            )
        partition = root / "spot" / symbol / "1d" / "2024-06.csv.gz"
        partition.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(partition, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OHLCV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)


def test_options_surface_panel_builds_f56_to_f60() -> None:
    rows = [{key: str(value) for key, value in row.items()} for row in _fixture_rows()]
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ohlcv_root = Path(tmp) / "ohlcv"
        _write_ohlcv_cache(ohlcv_root)
        rv_panel = load_ohlcv_realized_vol_panel(
            external_root=ohlcv_root,
            required_underlyings=["BTC", "ETH"],
        )

        panel = build_options_surface_feature_panel(
            rows,
            required_underlyings=["BTC", "ETH"],
            realized_vol_panel=rv_panel,
        )
    summary = summarize_options_surface_feature_panel(panel, input_rows_read=len(rows))

    assert list(panel["subject"]) == ["BTC", "ETH"]
    for column in FACTOR_COLUMNS:
        assert column in panel.columns
        assert panel[column].notna().all()
    assert "realized_vol_30d_ohlcv" in panel.columns
    assert "realized_vol_sample_seconds" not in panel.columns
    assert panel["m3_1_options_surface_panel_ready"].all()
    assert summary["feature_readiness"]["all_required_subjects_latest_ready"] is True
    assert summary["raw_sample_retained"] is False


def test_builder_cli_requires_green_probe_and_writes_panel(tmp_path: Path) -> None:
    fixture_path = tmp_path / "OPTIONS.csv.gz"
    _write_gzip_csv(fixture_path, _fixture_rows())
    ohlcv_root = tmp_path / "ohlcv"
    _write_ohlcv_cache(ohlcv_root)
    probe_report = tmp_path / "reports" / "2026-06-13" / "m3_1_tardis_deribit_options_surface_probe.json"
    _write_green_probe_report(probe_report)

    exit_code = build_main(
        [
            "--as-of",
            "2026-06-13",
            "--input-csv-gz",
            str(fixture_path),
            "--ohlcv-external-root",
            str(ohlcv_root),
            "--output-dir",
            str(tmp_path / "options_surface"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    panel_path = tmp_path / "options_surface" / "2026-06-13" / "tardis_deribit_options_surface_features.csv"
    report_path = tmp_path / "reports" / "2026-06-13" / "m3_1_tardis_deribit_options_surface_builder.json"
    audit_path = (
        tmp_path
        / "reports"
        / "2026-06-13"
        / "m3_1_tardis_deribit_options_surface_admission_manifest_audit.json"
    )
    panel = pd.read_csv(panel_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert set(panel["subject"]) == {"BTC", "ETH"}
    assert panel["realized_vol_30d_ohlcv"].notna().all()
    assert report["phase1_decision"]["raw_sample_retained"] is False
    assert report["phase1_decision"]["all_required_subjects_latest_ready"] is True
    assert audit["decision"]["manifest_mutation_authorized"] is False
    assert audit["decision"]["audit_status"] == "blocked_for_manifest_admission"


def test_builder_cli_reads_local_raw_store_date_range(tmp_path: Path) -> None:
    raw_store_root = tmp_path / "tardis_deribit_options_chain"
    partition = raw_store_root / "raw" / "deribit" / "options_chain" / "2024" / "06" / "01" / "OPTIONS.csv.gz"
    _write_gzip_csv(partition, _fixture_rows())
    ohlcv_root = tmp_path / "ohlcv"
    _write_ohlcv_cache(ohlcv_root)
    probe_report = tmp_path / "reports" / "2026-06-13" / "m3_1_tardis_deribit_options_surface_probe.json"
    _write_green_probe_report(probe_report)

    exit_code = build_main(
        [
            "--as-of",
            "2026-06-13",
            "--from-date",
            "2024-06-01",
            "--to-date",
            "2024-06-01",
            "--input-raw-store-root",
            str(raw_store_root),
            "--ohlcv-external-root",
            str(ohlcv_root),
            "--output-dir",
            str(tmp_path / "options_surface"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    panel_path = tmp_path / "options_surface" / "2026-06-13" / "tardis_deribit_options_surface_features.csv"
    report_path = tmp_path / "reports" / "2026-06-13" / "m3_1_tardis_deribit_options_surface_builder.json"
    panel = pd.read_csv(panel_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(panel["subject"]) == {"BTC", "ETH"}
    assert report["builder_mode"] == "local_raw_store"
    assert report["input"]["source"] == "local_raw_store_date_range"
    assert report["input"]["raw_store_root"] == str(raw_store_root.resolve())
    assert report["phase1_decision"]["manifest_mutation_authorized"] is False
    assert report["phase1_decision"]["all_required_subjects_latest_ready"] is True
