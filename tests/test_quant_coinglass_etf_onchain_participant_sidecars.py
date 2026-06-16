from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pandas as pd

from scripts.quant_research.sync_coinglass_etf_onchain_participant_sidecars import (
    build_etf_daily_state,
    build_exchange_transfers_daily,
    build_participant_context,
    build_whale_transfers_daily,
    fetch_whale_transfer_rows,
)


def _ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)


def _sec(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def test_etf_daily_state_applies_one_day_pit_lag_and_ticker_flows() -> None:
    frame = build_etf_daily_state(
        bitcoin_flow_rows=[
            {
                "timestamp": _ms(2026, 1, 1),
                "flow_usd": 100.0,
                "price_usd": 50_000.0,
                "etf_flows": [{"etf_ticker": "IBIT", "flow_usd": 80.0}],
            }
        ],
        ethereum_flow_rows=[
            {
                "timestamp": _ms(2026, 1, 1),
                "flow_usd": -20.0,
                "price_usd": 3_000.0,
                "etf_flows": [{"etf_ticker": "ETHA", "flow_usd": -10.0}],
            }
        ],
        bitcoin_ibit_rows=[
            {
                "market_date": _ms(2026, 1, 1),
                "market_price": 55.0,
                "nav": 54.0,
                "net_assets": 123.0,
                "premium_discount": 0.2,
                "btc_holdings": 1.5,
            }
        ],
        pit_lag_days=1,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["date_utc"] == "2026-01-02"
    assert row["btc_etf_source_date_utc"] == "2026-01-01"
    assert float(row["btc_etf_flow_usd_ibit"]) == 80.0
    assert float(row["eth_etf_flow_usd_etha"]) == -10.0
    assert float(row["ibit_net_assets"]) == 123.0
    assert float(row["total_btc_eth_etf_flow_usd"]) == 80.0


def test_exchange_transfers_daily_keeps_raw_type_codes_and_pit_lag() -> None:
    frame = build_exchange_transfers_daily(
        [
            {
                "transaction_time": _sec(2026, 1, 1),
                "amount_usd": 100.0,
                "asset_symbol": "USDT",
                "exchange_name": "Binance",
                "transfer_type": 2,
            },
            {
                "transaction_time": _sec(2026, 1, 1),
                "amount_usd": 40.0,
                "asset_symbol": "USDC",
                "exchange_name": "Coinbase",
                "transfer_type": 1,
            },
        ],
        pit_lag_days=1,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["date_utc"] == "2026-01-02"
    assert int(row["exchange_transfer_count"]) == 2
    assert float(row["exchange_transfer_stablecoin_total_usd"]) == 140.0
    assert float(row["exchange_transfer_type2_usd"]) == 100.0
    assert float(row["exchange_netflow_type2_minus_type1_usd"]) == 60.0
    assert row["exchange_transfer_direction_semantics"] == "raw_transfer_type_unverified"


def test_whale_transfers_daily_infers_exchange_direction_and_lags() -> None:
    frame = build_whale_transfers_daily(
        [
            {
                "block_timestamp": _sec(2026, 1, 1),
                "amount_usd": "90",
                "asset_symbol": "BTC",
                "from": "Coinbase Institutional",
                "to": "unknown wallet",
            },
            {
                "block_timestamp": _sec(2026, 1, 1),
                "amount_usd": "120",
                "asset_symbol": "USDT",
                "from": "unknown wallet",
                "to": "Binance",
            },
            {
                "block_timestamp": _sec(2026, 1, 1),
                "amount_usd": "5",
                "asset_symbol": "ETH",
                "from": "unknown wallet",
                "to": "unknown wallet",
            },
        ],
        pit_lag_days=1,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["date_utc"] == "2026-01-02"
    assert int(row["whale_transfer_count"]) == 3
    assert float(row["whale_from_exchange_usd"]) == 90.0
    assert float(row["whale_to_exchange_usd"]) == 120.0
    assert float(row["whale_unknown_direction_usd"]) == 5.0
    assert float(row["whale_net_to_exchange_usd"]) == 30.0


def test_participant_context_merges_sources_on_same_decision_date() -> None:
    etf = pd.DataFrame(
        [
            {
                "date_utc": "2026-01-02",
                "timestamp_ms": _ms(2026, 1, 2),
                "pit_lag_days": 1,
                "pit_policy": "daily_source_date_plus_lag",
                "source": "etf",
                "btc_etf_flow_usd": 1.0,
            }
        ]
    )
    exchange = pd.DataFrame(
        [
            {
                "date_utc": "2026-01-02",
                "timestamp_ms": _ms(2026, 1, 2),
                "pit_lag_days": 1,
                "pit_policy": "event_date_plus_lag",
                "source": "exchange",
                "exchange_transfer_total_usd": 2.0,
            }
        ]
    )
    whale = pd.DataFrame(
        [
            {
                "date_utc": "2026-01-02",
                "timestamp_ms": _ms(2026, 1, 2),
                "pit_lag_days": 1,
                "pit_policy": "event_date_plus_lag",
                "source": "whale",
                "whale_transfer_total_usd": 3.0,
            }
        ]
    )

    merged = build_participant_context(etf_daily=etf, exchange_daily=exchange, whale_daily=whale)

    assert len(merged) == 1
    assert float(merged.iloc[0]["btc_etf_flow_usd"]) == 1.0
    assert float(merged.iloc[0]["exchange_transfer_total_usd"]) == 2.0
    assert float(merged.iloc[0]["whale_transfer_total_usd"]) == 3.0
    assert merged.iloc[0]["participant_context_sources"] == "etf|exchange|whale"


def test_whale_fetch_splits_windows_that_hit_vendor_row_cap() -> None:
    start_ms = _ms(2026, 1, 1)
    end_ms = start_ms + 24 * 3_600_000 - 1
    calls: list[tuple[int, int]] = []

    def fake_http(url: str) -> dict[str, object]:
        params = parse_qs(urlparse(url).query)
        window_start = int(params["start_time"][0])
        window_end = int(params["end_time"][0])
        calls.append((window_start, window_end))
        if window_end - window_start > 6 * 3_600_000:
            return {
                "data": [
                    {
                        "block_timestamp": window_start // 1000,
                        "amount_usd": "1",
                        "transaction_hash": f"cap-{index}",
                    }
                    for index in range(1000)
                ]
            }
        return {
            "data": [
                {
                    "block_timestamp": window_start // 1000,
                    "amount_usd": "1",
                    "transaction_hash": f"leaf-{window_start}",
                }
            ]
        }

    rows, warnings = fetch_whale_transfer_rows(
        symbols=["BTC"],
        start_ms=start_ms,
        end_ms=end_ms,
        window_days=1,
        http_get_json_fn=fake_http,
    )

    assert warnings == []
    assert len(rows) == 4
    assert len(calls) > 4
