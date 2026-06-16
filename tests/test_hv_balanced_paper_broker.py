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

from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent
from enhengclaw.live_trading.paper_broker import simulate_paper_execution


class HvBalancedPaperBrokerTests(unittest.TestCase):
    def test_simulate_paper_execution_fills_intents_without_exchange_submission(self) -> None:
        plan = ExecutionPlan(
            plan_id="portfolio:plan:paper",
            portfolio_id="portfolio",
            mode="paper",
            status="ok",
            intents=[
                _intent(symbol="BTCUSDT", side="BUY", quantity=0.01, seq=1),
                _intent(symbol="ETHUSDT", side="SELL", quantity=0.20, seq=2),
            ],
        )

        result = simulate_paper_execution(
            plan,
            mark_prices={"BTCUSDT": 100_000.0, "ETHUSDT": 5_000.0},
            run_id="run",
            created_at_utc="2026-05-16T00:00:00Z",
            current_positions={"BNBUSDT": 1.0},
            fee_rate=0.0004,
        )

        self.assertEqual(result.status, "filled")
        self.assertEqual(result.blockers, [])
        self.assertEqual(len(result.submitted_orders), 2)
        self.assertEqual(len(result.fills), 2)
        self.assertEqual(result.account_before["positions"], {"BNBUSDT": 1.0})
        self.assertEqual(result.account_after["positions"]["BNBUSDT"], 1.0)
        self.assertAlmostEqual(result.account_after["positions"]["BTCUSDT"], 0.01)
        self.assertAlmostEqual(result.account_after["positions"]["ETHUSDT"], -0.20)
        self.assertAlmostEqual(float(result.account_after["simulated_gross_notional_usdt"]), 2_000.0)
        self.assertAlmostEqual(float(result.account_after["simulated_fee_usdt"]), 0.8)


def _intent(*, symbol: str, side: str, quantity: float, seq: int) -> OrderIntent:
    signed = quantity if side == "BUY" else -quantity
    return OrderIntent(
        intent_id=f"intent-{seq}",
        portfolio_id="portfolio",
        symbol=symbol,
        side=side,
        position_side="BOTH",
        order_type="MARKET",
        quantity=quantity,
        reduce_only=False,
        target_position_amt=signed,
        current_position_amt=0.0,
        delta_position_amt=signed,
        max_slippage_bps=20.0,
        client_order_id=f"client-{seq}",
    )
