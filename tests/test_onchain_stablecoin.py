from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path
import tempfile
import unittest

from enhengclaw.quant_research.onchain_address_labels import (
    load_address_label_snapshot,
)
from enhengclaw.quant_research.onchain_stablecoin import (
    StablecoinTokenSpec,
    ZERO_ADDRESS,
    _aggregate_window_row,
    _build_sync_plan,
    _decode_erc20_transfer_log,
    _transfer_identity,
)
from enhengclaw.quant_research.stablecoin_regime import (
    _overlay_state_and_multiplier_exchange_absorption_v1,
    _overlay_state_and_multiplier_v2,
    _overlay_state_and_multiplier_whale_stress_v1,
)
import pandas as pd


class OnchainStablecoinTests(unittest.TestCase):
    def test_decode_erc20_transfer_log_decodes_addresses_and_value(self) -> None:
        token = StablecoinTokenSpec("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6)
        decoded = _decode_erc20_transfer_log(
            token=token,
            raw_log={
                "transactionHash": "0xabc",
                "logIndex": "0x2",
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                    "0x0000000000000000000000001111111111111111111111111111111111111111",
                    "0x0000000000000000000000002222222222222222222222222222222222222222",
                ],
                "data": hex(1_250_000),
            },
        )
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["from"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(decoded["to"], "0x2222222222222222222222222222222222222222")
        self.assertEqual(decoded["value"], 1.25)

    def test_aggregate_window_row_accepts_provider_rows_without_timestamps(self) -> None:
        token = StablecoinTokenSpec("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6)
        start_dt = datetime(2026, 4, 28, tzinfo=UTC)
        end_dt = datetime(2026, 4, 29, tzinfo=UTC)
        row = _aggregate_window_row(
            token=token,
            transfers=[
                {"from": "0x0000000000000000000000000000000000000000", "to": "0xabc", "value": 2_000_000.0},
                {"from": "0xabc", "to": "0x0000000000000000000000000000000000000000", "value": 500_000.0},
            ],
            start_dt=start_dt,
            end_dt=end_dt,
            whale_threshold=1_000_000.0,
            address_labels=None,
            is_full_day=True,
            fetch_status="complete",
            source="eth_getLogs",
        )
        self.assertEqual(row["transfer_count"], 2)
        self.assertEqual(row["mint_count"], 1)
        self.assertEqual(row["burn_count"], 1)
        self.assertEqual(row["net_issuance_amount"], 1_500_000.0)
        self.assertEqual(row["whale_transfer_count"], 1)
        self.assertEqual(row["source"], "eth_getLogs")

    def test_aggregate_window_row_computes_labeled_directional_amounts(self) -> None:
        token = StablecoinTokenSpec("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6)
        start_dt = datetime(2026, 4, 28, tzinfo=UTC)
        end_dt = datetime(2026, 4, 29, tzinfo=UTC)
        row = _aggregate_window_row(
            token=token,
            transfers=[
                {"from": ZERO_ADDRESS, "to": "0x77696bb39917c91a0c3908d577d5e322095425ca", "value": 2_000_000.0},
                {"from": "0x28c6c06298d514db089934071355e5743bf21d60", "to": "0xabc", "value": 1_500_000.0},
                {"from": "0xabc", "to": "0xdef", "value": 50.0},
                {"from": "0xabc", "to": "0x1111111111111111111111111111111111111111", "value": 250_000.0},
                {"from": "0x1111111111111111111111111111111111111111", "to": "0xdef", "value": 100_000.0},
            ],
            start_dt=start_dt,
            end_dt=end_dt,
            whale_threshold=1_000_000.0,
            address_labels={
                "0x77696bb39917c91a0c3908d577d5e322095425ca": {
                    "entity_type": "exchange",
                    "entity_name": "Coinbase 3",
                },
                "0x28c6c06298d514db089934071355e5743bf21d60": {
                    "entity_type": "exchange",
                    "entity_name": "Binance 14",
                },
                "0x1111111111111111111111111111111111111111": {
                    "entity_type": "bridge",
                    "entity_name": "Test Bridge",
                },
            },
            is_full_day=True,
            fetch_status="complete",
            source="eth_getLogs",
        )
        self.assertEqual(row["exchange_inflow_amount"], 2_000_000.0)
        self.assertEqual(row["exchange_outflow_amount"], 1_500_000.0)
        self.assertEqual(row["exchange_netflow_amount"], 500_000.0)
        self.assertEqual(row["whale_to_exchange_amount"], 2_000_000.0)
        self.assertEqual(row["exchange_to_whale_amount"], 1_500_000.0)
        self.assertEqual(row["issuer_to_exchange_amount"], 2_000_000.0)
        self.assertEqual(row["bridge_inflow_amount"], 250_000.0)
        self.assertEqual(row["bridge_outflow_amount"], 100_000.0)
        self.assertEqual(row["labeled_transfer_share_amount"], 3_850_000.0)
        self.assertEqual(row["unknown_transfer_share_amount"], 50.0)

    def test_build_sync_plan_honors_explicit_date_range(self) -> None:
        token = StablecoinTokenSpec("DAI", "0x6B175474E89094C44Da98b954EedeAC495271d0F", 18)
        end_dt = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        plan = _build_sync_plan(
            selected_tokens=(token,),
            existing_rows=[],
            requested_mode="bootstrap",
            lookback_days=14,
            refresh_overlap_days=3,
            end_dt=end_dt,
            start_date_override=datetime(2026, 4, 20, tzinfo=UTC).date(),
            end_date_override=datetime(2026, 4, 22, tzinfo=UTC).date(),
        )
        self.assertEqual(plan["effective_mode"], "explicit_range")
        self.assertEqual(plan["start_date"].isoformat(), "2026-04-20")
        self.assertEqual(plan["end_date"].isoformat(), "2026-04-22")
        self.assertEqual(plan["end_dt"].isoformat(), "2026-04-23T00:00:00+00:00")

    def test_transfer_identity_uses_transaction_hash_fallback(self) -> None:
        identity = _transfer_identity(
            {
                "transactionHash": "0xdeadbeef",
                "logIndex": "0x4",
                "category": "erc20",
                "asset": "USDC",
            }
        )
        self.assertEqual(identity, "0xdeadbeef:0x4:erc20:USDC")

    def test_load_address_label_snapshot_uses_latest_snapshot_not_after_as_of_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshots / "address_labels_2026-04-29.csv"
            with snapshot_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "address",
                        "chain",
                        "entity_type",
                        "entity_name",
                        "label_source",
                        "label_confidence",
                        "as_of_date_utc",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "address": "0x77696bb39917c91a0c3908d577d5e322095425ca",
                        "chain": "ethereum",
                        "entity_type": "exchange",
                        "entity_name": "Coinbase 3",
                        "label_source": "test_seed",
                        "label_confidence": "0.95",
                        "as_of_date_utc": "2026-04-29",
                    }
                )
            snapshot, metadata = load_address_label_snapshot(
                as_of_date=date(2026, 4, 30),
                external_root=root,
            )
        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["record_count"], 1)
        self.assertEqual(metadata["snapshot_path"], str(snapshot_path))
        self.assertEqual(snapshot["0x77696bb39917c91a0c3908d577d5e322095425ca"]["entity_type"], "exchange")

    def test_overlay_v2_leaves_open_regime_unthrottled(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_v2(
            pd.Series(
                {
                    "score_v1": 0.4,
                    "issuance_ratio_z14": 0.2,
                    "velocity_ratio_7d": 1.1,
                    "issuance_breadth": 0.67,
                }
            )
        )
        self.assertEqual(state, "open")
        self.assertEqual(multiplier, 1.0)

    def test_overlay_v2_uses_soft_contraction_before_hard_floor(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_v2(
            pd.Series(
                {
                    "score_v1": -0.9,
                    "issuance_ratio_z14": -0.6,
                    "velocity_ratio_7d": 0.9,
                    "issuance_breadth": 0.33,
                }
            )
        )
        self.assertEqual(state, "soft_contraction")
        self.assertGreaterEqual(multiplier, 0.88)
        self.assertLess(multiplier, 1.0)

    def test_overlay_v2_only_hard_throttles_confirmed_stress(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_v2(
            pd.Series(
                {
                    "score_v1": -1.5,
                    "issuance_ratio_z14": -1.2,
                    "velocity_ratio_7d": 0.8,
                    "issuance_breadth": 0.0,
                }
            )
        )
        self.assertEqual(state, "hard_contraction")
        self.assertEqual(multiplier, 0.8)

    def test_exchange_absorption_overlay_requires_coverage_and_throttles_drain(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_exchange_absorption_v1(
            pd.Series(
                {
                    "labeled_coverage_ratio": 0.08,
                    "exchange_absorption_score_v1": -1.1,
                    "exchange_netflow_ratio": -0.02,
                    "issuance_ratio": -0.001,
                }
            )
        )
        self.assertEqual(state, "drain")
        self.assertEqual(multiplier, 0.85)

    def test_whale_stress_overlay_fails_open_when_coverage_is_too_low(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_whale_stress_v1(
            pd.Series(
                {
                    "labeled_coverage_ratio": 0.01,
                    "whale_exchange_stress_score_v1": 2.0,
                    "exchange_netflow_ratio": -0.01,
                    "issuance_ratio": -0.001,
                }
            )
        )
        self.assertEqual(state, "coverage_insufficient")
        self.assertEqual(multiplier, 1.0)

    def test_whale_stress_overlay_hard_throttles_confirmed_stress(self) -> None:
        state, multiplier = _overlay_state_and_multiplier_whale_stress_v1(
            pd.Series(
                {
                    "labeled_coverage_ratio": 0.07,
                    "whale_exchange_stress_score_v1": 1.3,
                    "exchange_netflow_ratio": -0.015,
                    "issuance_ratio": -0.0008,
                }
            )
        )
        self.assertEqual(state, "hard_stress")
        self.assertEqual(multiplier, 0.8)


if __name__ == "__main__":
    unittest.main()
