from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from enhengclaw.quant_research.onchain_m3_2_features import (
    build_m3_2_feature_panel,
    build_m3_2_mf14_overlay_component_panel,
    compute_mf14_rebound_release_floor_v1,
    compute_mf14_sell_pressure_overlay_component_v1,
)


class M32FeaturePanelTests(unittest.TestCase):
    def test_build_m3_2_feature_panel_merges_alchemy_and_cryptoquant(self) -> None:
        with (
            tempfile.TemporaryDirectory() as stablecoin_tmp,
            tempfile.TemporaryDirectory() as cq_tmp,
            tempfile.TemporaryDirectory() as tron_tmp,
        ):
            stablecoin_root = Path(stablecoin_tmp)
            cq_root = Path(cq_tmp)
            tron_root = Path(tron_tmp)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "token_symbol": "USDT",
                        "transfer_count": 1,
                        "transfer_amount": 100.0,
                        "net_issuance_amount": 10.0,
                        "mint_amount": 10.0,
                        "burn_amount": 0.0,
                        "whale_transfer_amount": 0.0,
                        "exchange_inflow_amount": 5.0,
                        "exchange_outflow_amount": 1.0,
                        "exchange_netflow_amount": 4.0,
                        "whale_to_exchange_amount": 1.0,
                        "exchange_to_whale_amount": 0.0,
                        "issuer_to_exchange_amount": 1.0,
                        "bridge_inflow_amount": 0.0,
                        "bridge_outflow_amount": 0.0,
                        "labeled_transfer_share_amount": 100.0,
                        "unknown_transfer_share_amount": 0.0,
                        "is_full_day": True,
                        "fetch_status": "complete",
                    },
                    {
                        "date_utc": "2026-01-01",
                        "token_symbol": "USDC",
                        "transfer_count": 1,
                        "transfer_amount": 200.0,
                        "net_issuance_amount": 0.0,
                        "mint_amount": 0.0,
                        "burn_amount": 0.0,
                        "whale_transfer_amount": 0.0,
                        "exchange_inflow_amount": 5.0,
                        "exchange_outflow_amount": 1.0,
                        "exchange_netflow_amount": 4.0,
                        "whale_to_exchange_amount": 1.0,
                        "exchange_to_whale_amount": 0.0,
                        "issuer_to_exchange_amount": 1.0,
                        "bridge_inflow_amount": 0.0,
                        "bridge_outflow_amount": 0.0,
                        "labeled_transfer_share_amount": 200.0,
                        "unknown_transfer_share_amount": 0.0,
                        "is_full_day": True,
                        "fetch_status": "complete",
                    },
                    {
                        "date_utc": "2026-01-01",
                        "token_symbol": "DAI",
                        "transfer_count": 1,
                        "transfer_amount": 300.0,
                        "net_issuance_amount": 5.0,
                        "mint_amount": 5.0,
                        "burn_amount": 0.0,
                        "whale_transfer_amount": 0.0,
                        "exchange_inflow_amount": 5.0,
                        "exchange_outflow_amount": 1.0,
                        "exchange_netflow_amount": 4.0,
                        "whale_to_exchange_amount": 1.0,
                        "exchange_to_whale_amount": 0.0,
                        "issuer_to_exchange_amount": 1.0,
                        "bridge_inflow_amount": 0.0,
                        "bridge_outflow_amount": 0.0,
                        "labeled_transfer_share_amount": 300.0,
                        "unknown_transfer_share_amount": 0.0,
                        "is_full_day": True,
                        "fetch_status": "complete",
                    },
                ]
            ).to_csv(stablecoin_root / "daily_aggregates.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "token_id": "usdt_eth",
                        "window": "day",
                        "supply_total": 1000.0,
                        "supply_circulating": 900.0,
                        "supply_minted": 10.0,
                        "supply_burned": 1.0,
                        "supply_issued": 9.0,
                        "supply_redeemed": 2.0,
                        "tokens_transferred_total": 50.0,
                        "tokens_transferred_mean": 5.0,
                        "addresses_active_count": 10,
                        "addresses_active_sender_count": 6,
                        "addresses_active_receiver_count": 7,
                        "addresses_active_sender_percent": 0.6,
                        "addresses_active_receiver_percent": 0.7,
                        "source": "cryptoquant_api",
                    }
                ]
            ).to_csv(cq_root / "stablecoin_supply_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "token_id": "usdt_eth",
                        "exchange": "spot_exchange",
                        "window": "day",
                        "reserve": 100.0,
                        "inflow_total": 20.0,
                        "inflow_top10": 10.0,
                        "inflow_mean": 2.0,
                        "outflow_total": 15.0,
                        "outflow_top10": 8.0,
                        "outflow_mean": 1.5,
                        "netflow_total": 5.0,
                        "transactions_count_inflow": 4.0,
                        "transactions_count_outflow": 3.0,
                        "addresses_count_inflow": 2.0,
                        "addresses_count_outflow": 2.0,
                        "source": "cryptoquant_api",
                    }
                ]
            ).to_csv(cq_root / "stablecoin_exchange_flows_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "asset_id": "btc",
                        "exchange": "spot_exchange",
                        "window": "day",
                        "reserve": 50.0,
                        "reserve_usd": 5000.0,
                        "inflow_total": 5.0,
                        "inflow_top10": 4.0,
                        "inflow_mean": 1.0,
                        "outflow_total": 3.0,
                        "outflow_top10": 2.0,
                        "outflow_mean": 0.5,
                        "netflow_total": 2.0,
                        "transactions_count_inflow": 3.0,
                        "transactions_count_outflow": 2.0,
                        "addresses_count_inflow": 2.0,
                        "addresses_count_outflow": 1.0,
                        "source": "cryptoquant_api",
                    }
                ]
            ).to_csv(cq_root / "reflexivity_exchange_flows_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "asset_id": "btc",
                        "window": "day",
                        "sopr": 0.98,
                        "a_sopr": 0.99,
                        "sth_sopr": 0.97,
                        "lth_sopr": 0.95,
                        "sopr_ratio": 0.96,
                        "stablecoin_supply_ratio": 11.0,
                        "realized_price": 42000.0,
                        "source": "cryptoquant_api",
                    }
                ]
            ).to_csv(cq_root / "reflexivity_market_indicators_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date_utc": "2026-01-01",
                        "token_symbol": "USDT_TRX",
                        "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                        "decimals": 6,
                        "transfer_count": 100.0,
                        "transfer_amount": 1000.0,
                        "transfer_amount_usd": 1005.0,
                        "from_count": 45.0,
                        "to_count": 55.0,
                        "active_address_count": 70.0,
                        "holders_count": 1000000.0,
                        "stats_usdt_transaction_count": 100.0,
                        "stats_active_account_number": 500.0,
                        "stats_total_transaction_count": 1000.0,
                        "transfer_count_vs_stats_delta": 0.0,
                        "coverage_start_utc": "2026-01-01T00:00:00Z",
                        "coverage_end_utc": "2026-01-01T23:59:59Z",
                        "is_full_day": True,
                        "fetch_status": "complete",
                        "source": "tronscan_public_api",
                    }
                ]
            ).to_csv(tron_root / "daily_aggregates.csv", index=False)

            panel = build_m3_2_feature_panel(
                stablecoin_external_root=stablecoin_root,
                cryptoquant_external_root=cq_root,
                tron_external_root=tron_root,
            )

        self.assertEqual(len(panel), 1)
        self.assertIn("alchemy_exchange_absorption_score_v1", panel.columns)
        self.assertIn("cq_supply_circulating", panel.columns)
        self.assertIn("cq_stable_spot_exchange_reserve_ratio", panel.columns)
        self.assertIn("m3_2_stable_supply_impulse_state", panel.columns)
        self.assertIn("tronscan_transfer_count", panel.columns)
        self.assertIn("m3_2_tron_flow_impulse_state", panel.columns)
        self.assertIn("m3_2_tron_speculative_heat_state", panel.columns)
        self.assertEqual(float(panel.loc[0, "tronscan_transfer_count"]), 100.0)

    def test_build_m3_2_mf14_overlay_component_panel(self) -> None:
        panel = pd.DataFrame(
            [
                {
                    "date_utc": "2026-01-01",
                    "decision_date_utc": "2026-01-02",
                    "m3_2_panel_ready": True,
                    "m3_2_btc_sell_pressure_state": 0.80,
                    "m3_2_reflexive_rebound_state": 0.10,
                },
                {
                    "date_utc": "2026-01-02",
                    "decision_date_utc": "2026-01-03",
                    "m3_2_panel_ready": True,
                    "m3_2_btc_sell_pressure_state": 1.30,
                    "m3_2_reflexive_rebound_state": 0.90,
                },
                {
                    "date_utc": "2026-01-03",
                    "decision_date_utc": "2026-01-04",
                    "m3_2_panel_ready": True,
                    "m3_2_btc_sell_pressure_state": 0.20,
                    "m3_2_reflexive_rebound_state": 1.40,
                },
            ]
        )

        components = build_m3_2_mf14_overlay_component_panel(panel=panel)
        sell_table = compute_mf14_sell_pressure_overlay_component_v1(panel=panel)
        rebound_table = compute_mf14_rebound_release_floor_v1(panel=panel)

        self.assertEqual(
            list(components["mf14_sell_pressure_overlay_component_v1"]),
            [0.90, 0.75, 1.0],
        )
        self.assertEqual(
            list(components["mf14_rebound_release_floor_v1"]),
            [0.0, 0.95, 1.0],
        )
        self.assertEqual(sell_table["2026-01-02"], 0.90)
        self.assertEqual(sell_table["2026-01-03"], 0.75)
        self.assertEqual(rebound_table["2026-01-03"], 0.95)
        self.assertEqual(rebound_table["2026-01-04"], 1.0)


if __name__ == "__main__":
    unittest.main()
