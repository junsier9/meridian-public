from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.quant_research.sync_coinglass_full_stack_foundation import (
    _aggregate_extended_hourly_to_daily,
    _add_extended_derived_columns,
    build_microstructure_and_participant_panels,
    render_foundation_doc,
    summarize_tabular_artifact,
)


def _ms(year: int, month: int, day: int, hour: int = 0) -> int:
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp() * 1000)


def test_extended_derived_columns_preserve_raw_and_add_ratios() -> None:
    frame = pd.DataFrame(
        {
            "long_liquidation_usd": [10.0],
            "short_liquidation_usd": [30.0],
            "orderbook_bids_usd": [60.0],
            "orderbook_asks_usd": [40.0],
            "taker_buy_volume_usd": [70.0],
            "taker_sell_volume_usd": [30.0],
            "global_account_long_pct": [51.0],
            "global_account_short_pct": [49.0],
            "top_trader_long_pct": [60.0],
            "top_trader_short_pct": [40.0],
        }
    )

    out = _add_extended_derived_columns(frame)

    assert float(out.loc[0, "liquidation_total_usd"]) == 40.0
    assert float(out.loc[0, "liquidation_imbalance_ratio"]) == 0.5
    assert float(out.loc[0, "orderbook_imbalance"]) == 0.2
    assert float(out.loc[0, "taker_buy_sell_imbalance"]) == 0.4
    assert float(out.loc[0, "top_global_long_pct_disagreement"]) == 9.0
    assert float(out.loc[0, "top_global_net_long_disagreement"]) == 18.0


def test_aggregate_extended_hourly_to_daily_uses_sum_for_flows_last_for_state() -> None:
    hourly = pd.DataFrame(
        {
            "date_utc": ["2026-01-01", "2026-01-01"],
            "subject": ["BTC", "BTC"],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "liquidity_bucket": ["top_liquidity", "top_liquidity"],
            "timestamp_ms": [_ms(2026, 1, 1, 0), _ms(2026, 1, 1, 1)],
            "close_time_ms": [_ms(2026, 1, 1, 1) - 1, _ms(2026, 1, 1, 2) - 1],
            "long_liquidation_usd": [10.0, 20.0],
            "short_liquidation_usd": [5.0, 15.0],
            "taker_buy_volume_usd": [100.0, 200.0],
            "taker_sell_volume_usd": [80.0, 120.0],
            "global_account_long_pct": [50.0, 55.0],
            "global_account_short_pct": [50.0, 45.0],
            "top_trader_long_pct": [60.0, 65.0],
            "top_trader_short_pct": [40.0, 35.0],
            "source": ["coinglass_extended", "coinglass_extended"],
        }
    )
    hourly = _add_extended_derived_columns(hourly)

    daily = _aggregate_extended_hourly_to_daily(hourly)

    assert len(daily) == 1
    row = daily.iloc[0]
    assert float(row["long_liquidation_usd"]) == 30.0
    assert float(row["taker_buy_volume_usd"]) == 300.0
    assert float(row["global_account_long_pct"]) == 55.0
    assert int(row["hourly_row_count"]) == 2


def test_build_microstructure_panels_accepts_injected_loader(tmp_path: Path) -> None:
    rows = [
        {
            "exchange": "binance",
            "market_type": "usdm_perp",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "open_time_ms": str(_ms(2026, 1, 1, 0)),
            "close_time_ms": str(_ms(2026, 1, 1, 1) - 1),
            "long_liquidation_usd": "10",
            "short_liquidation_usd": "20",
            "global_account_long_pct": "51",
            "global_account_short_pct": "49",
            "global_account_long_short_ratio": "1.04",
            "top_trader_long_pct": "60",
            "top_trader_short_pct": "40",
            "top_trader_long_short_ratio": "1.5",
            "orderbook_bids_usd": "100",
            "orderbook_asks_usd": "80",
            "orderbook_bids_quantity": "1",
            "orderbook_asks_quantity": "2",
            "taker_buy_volume_usd": "70",
            "taker_sell_volume_usd": "30",
            "source": "coinglass_extended",
        }
    ]

    def loader(**_: object) -> list[dict[str, str]]:
        return rows

    summary = build_microstructure_and_participant_panels(
        symbol_records=[
            {
                "subject": "BTC",
                "usdm_symbol": "BTCUSDT",
                "liquidity_bucket": "top_liquidity",
            }
        ],
        output_root=tmp_path,
        external_root=tmp_path / "external",
        rows_loader=loader,
    )

    assert summary["status"] == "success"
    assert summary["artifacts"]["microstructure_panel_1h"]["row_count"] == 1
    assert summary["artifacts"]["participant_panel_1d"]["row_count"] == 1
    participant = pd.read_csv(tmp_path / "participant_panel_1d.csv.gz")
    assert "top_global_long_pct_disagreement" in participant.columns


def test_summarize_tabular_artifact_reports_date_range(tmp_path: Path) -> None:
    path = tmp_path / "toy.csv.gz"
    pd.DataFrame({"date_utc": ["2026-01-01", "2026-01-03"], "symbol": ["A", "B"]}).to_csv(
        path,
        index=False,
        compression="gzip",
    )

    summary = summarize_tabular_artifact(path)

    assert summary["exists"] is True
    assert summary["row_count"] == 2
    assert summary["first_date_utc"] == "2026-01-01"
    assert summary["last_date_utc"] == "2026-01-03"
    assert summary["symbol_count"] == 2


def test_render_foundation_doc_makes_catalog_the_default_entrypoint() -> None:
    doc = render_foundation_doc(
        {
            "generated_at_utc": "2026-05-07T00:00:00Z",
            "contract_version": "x",
            "as_of": "2026-05-04",
            "catalog_only": True,
            "symbol_count": 1,
            "steps": [{"name": "panel", "status": "success", "duration_seconds": 0.1}],
            "decision": {"foundation_catalog_ready": True, "alpha_rerun_allowed": False},
            "catalog": {
                "toy": {
                    "family": "microstructure",
                    "research_status": "sidecar_context_only",
                    "summary": {"row_count": 1, "first_date_utc": "2026-01-01", "last_date_utc": "2026-01-02"},
                    "notes": "note",
                }
            },
        }
    )

    assert "# CoinGlass Full-Stack Foundation Sync" in doc
    assert "Before starting a new CoinGlass-backed research lane" in doc
    assert "alpha_rerun_allowed: `False`" in doc
