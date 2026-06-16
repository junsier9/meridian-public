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

from enhengclaw.live_trading.models import LiveDecisionSnapshot
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio, portfolio_drawdown_multiplier
from enhengclaw.quant_research.contracts import read_json


FROZEN_CONFIG = ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"


class HvBalancedPortfolioTargetTests(unittest.TestCase):
    def test_drawdown_multiplier_matches_balanced_soft_budget(self) -> None:
        constraints = {
            "dd_throttle_start_threshold": 0.10,
            "dd_throttle_full_threshold": 0.25,
            "dd_throttle_min_multiplier": 0.80,
        }

        self.assertEqual(portfolio_drawdown_multiplier(current_drawdown=0.0, constraints=constraints), 1.0)
        self.assertEqual(portfolio_drawdown_multiplier(current_drawdown=0.10, constraints=constraints), 1.0)
        self.assertAlmostEqual(portfolio_drawdown_multiplier(current_drawdown=0.175, constraints=constraints), 0.90)
        self.assertAlmostEqual(portfolio_drawdown_multiplier(current_drawdown=0.30, constraints=constraints), 0.80)

    def test_target_portfolio_applies_top_bottom_selection_and_short_brake(self) -> None:
        portfolio = build_target_portfolio(
            _snapshot(),
            config=dict(read_json(FROZEN_CONFIG)),
            allocated_capital_usdt=100.0,
            current_drawdown=0.175,
        )

        self.assertEqual(portfolio.status, "ok")
        by_subject = {position.subject: position for position in portfolio.positions}
        self.assertAlmostEqual(by_subject["L1"].target_weight, 0.15)
        self.assertAlmostEqual(by_subject["L2"].target_weight, 0.15)
        self.assertAlmostEqual(by_subject["L3"].target_weight, 0.15)
        self.assertAlmostEqual(by_subject["S1"].target_weight, -0.15)
        self.assertAlmostEqual(by_subject["S2"].target_weight, -0.075)
        self.assertAlmostEqual(by_subject["S3"].target_weight, -0.0375)
        self.assertAlmostEqual(portfolio.target_gross_weight, 0.7125)
        self.assertAlmostEqual(by_subject["S2"].target_notional_usdt, 7.5)


def _snapshot() -> LiveDecisionSnapshot:
    scores = pd.DataFrame(
        [
            _row("L1", 3.0, "top_liquidity", True, False, 1.0),
            _row("L2", 2.0, "top_liquidity", True, False, 1.0),
            _row("L3", 1.0, "top_liquidity", True, False, 1.0),
            _row("S1", -1.0, "mid_liquidity", False, True, 1.0),
            _row("S2", -2.0, "mid_liquidity", False, True, 0.5),
            _row("S3", -3.0, "mid_liquidity", False, True, 0.25),
        ]
    )
    return LiveDecisionSnapshot(
        decision_id="fixture-decision",
        strategy_label="fixture-strategy",
        config_sha256="fixture-sha",
        decision_time_ms=0,
        decision_date_utc="1970-01-01",
        rebalance_slot=True,
        input_bar_end_ms=0,
        status="ok",
        scores=scores,
    )


def _row(subject: str, score: float, bucket: str, long_ok: bool, short_ok: bool, short_multiplier: float) -> dict:
    return {
        "timestamp_ms": 0,
        "subject": subject,
        "usdm_symbol": f"{subject}USDT",
        "score": score,
        "liquidity_bucket": bucket,
        "binance_decision_eligible": True,
        "binance_pit_top_long_eligible": long_ok,
        "binance_pit_mid_short_eligible": short_ok,
        "binance_risk_brake_short_multiplier": short_multiplier,
    }
