from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.hv_balanced_live_signal import build_live_hv_balanced_snapshot
from enhengclaw.quant_research.contracts import read_json


FROZEN_CONFIG = ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"


class HvBalancedLiveSignalTests(unittest.TestCase):
    def test_live_signal_is_label_free_and_scores_closed_decision_rows(self) -> None:
        config = _test_strategy_config()
        snapshot = build_live_hv_balanced_snapshot(
            _feature_panel(),
            config=config,
            config_sha256="fixture-sha",
            decision_time_ms=0,
            rebalance_interval_days=10,
        )

        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.blockers, [])
        self.assertEqual(len(snapshot.scores), 6)
        self.assertIn("score", snapshot.scores.columns)
        self.assertTrue(snapshot.scores["binance_decision_eligible"].all())
        self.assertTrue(snapshot.scores["binance_pit_top_long_eligible"].head(3).all())
        self.assertTrue(snapshot.scores["binance_pit_mid_short_eligible"].tail(3).all())

    def test_live_signal_rejects_future_label_columns(self) -> None:
        config = _test_strategy_config()
        frame = _feature_panel()
        frame["target_execution_forward_return"] = 0.01
        frame["target_forward_return"] = 0.02

        snapshot = build_live_hv_balanced_snapshot(
            frame,
            config=config,
            config_sha256="fixture-sha",
            decision_time_ms=0,
            rebalance_interval_days=10,
        )

        self.assertEqual(snapshot.status, "blocked")
        self.assertIn(
            "future_label_columns_present:target_execution_forward_return,target_forward_return",
            snapshot.blockers,
        )

    def test_live_signal_blocks_non_rebalance_slot(self) -> None:
        config = _test_strategy_config()

        snapshot = build_live_hv_balanced_snapshot(
            _feature_panel(timestamp_ms=86_400_000),
            config=config,
            config_sha256="fixture-sha",
            decision_time_ms=86_400_000,
            rebalance_interval_days=10,
        )

        self.assertEqual(snapshot.status, "blocked")
        self.assertIn("non_rebalance_slot", snapshot.blockers)


def _test_strategy_config() -> dict:
    config = dict(read_json(FROZEN_CONFIG))
    config["pit_data_eligibility_policy"] = {"mode": "disabled"}
    return config


def _feature_panel(timestamp_ms: int = 0) -> pd.DataFrame:
    rows = []
    subjects = ["L1", "L2", "L3", "S1", "S2", "S3"]
    for index, subject in enumerate(subjects):
        base = 0.10 + index * 0.01
        rows.append(
            {
                "timestamp_ms": timestamp_ms,
                "subject": subject,
                "usdm_symbol": f"{subject}USDT",
                "perp_close": 100.0 + index,
                "perp_quote_volume_usd": 10_000_000.0,
                "universe_active": True,
                "universe_rank": index + 1,
                "liquidity_bucket": "top_liquidity" if subject.startswith("L") else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                "intraday_realized_vol_4h_to_1d_smooth_60": base,
                "realized_volatility_5": base + 0.01,
                "distance_to_high_60": base + 0.02,
                "distance_to_high_5": -0.01 if subject.startswith("S") else -0.20,
                "downside_upside_vol_ratio_30": base + 0.03,
                "momentum_20": 0.05,
            }
        )
    return pd.DataFrame(rows)
