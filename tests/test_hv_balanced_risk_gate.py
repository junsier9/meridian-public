from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.models import TargetPortfolio, TargetPosition
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate


class HvBalancedRiskGateTests(unittest.TestCase):
    def test_plan_only_can_pass_for_valid_portfolio(self) -> None:
        result = evaluate_risk_gate(_portfolio(), mode="plan_only", config=_live_config())

        self.assertTrue(result.passed)
        self.assertEqual(result.decision, "allow_plan")

    def test_live_is_blocked_without_confirmation_and_config_enable(self) -> None:
        result = evaluate_risk_gate(_portfolio(), mode="live", config=_live_config(), live_confirmed=False)

        self.assertFalse(result.passed)
        self.assertIn("missing_live_confirmation_flag", result.blockers)
        self.assertIn("live_trading_disabled_in_config", result.blockers)

    def test_symbol_notional_cap_blocks_oversized_position(self) -> None:
        config = _live_config()
        config["risk"]["max_symbol_notional_usdt"] = 5.0

        result = evaluate_risk_gate(_portfolio(), mode="plan_only", config=config)

        self.assertFalse(result.passed)
        self.assertIn("symbol_notional_exceeds_cap:BTCUSDT", result.blockers)

    def test_local_state_health_blocks_plan(self) -> None:
        result = evaluate_risk_gate(
            _portfolio(),
            mode="paper",
            config=_live_config(),
            local_state_health={
                "status": "blocked",
                "blockers": ["stale_running_heartbeat:old-run"],
            },
        )

        self.assertFalse(result.passed)
        self.assertIn("local_state_health_not_ok", result.blockers)
        self.assertIn("stale_running_heartbeat:old-run", result.blockers)


def _live_config() -> dict:
    return {
        "capital": {"allocated_capital_usdt": 100.0},
        "risk": {
            "trading_enabled": False,
            "max_allocated_capital_usdt": 100.0,
            "max_gross_notional_usdt": 100.0,
            "max_symbol_notional_usdt": 20.0,
        },
    }


def _portfolio() -> TargetPortfolio:
    return TargetPortfolio(
        portfolio_id="p1",
        decision_id="d1",
        strategy_label="fixture",
        allocated_capital_usdt=100.0,
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=0.1,
        target_net_weight=0.1,
        status="ok",
        positions=[
            TargetPosition(
                subject="BTC",
                usdm_symbol="BTCUSDT",
                side="long",
                score=1.0,
                target_weight=0.1,
                target_notional_usdt=10.0,
                previous_target_weight=0.0,
                delta_target_weight=0.1,
                raw_short_multiplier=1.0,
                portfolio_drawdown_multiplier=1.0,
                selection_reason="top_long",
            )
        ],
    )
