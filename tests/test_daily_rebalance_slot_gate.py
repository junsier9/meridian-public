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

from enhengclaw.live_trading.daily_rebalance_slot_gate import completed_slot_execution_gate  # noqa: E402
from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent  # noqa: E402


class DailyRebalanceSlotGateTests(unittest.TestCase):
    def test_completed_slot_requires_slot_and_hash_bound_manual_reexecution_authorization(self) -> None:
        record = {"status": "completed", "slot_id": "slot-1", "target_hash": "hash-1"}

        unbound = completed_slot_execution_gate(
            slot_record=record,
            plan=_plan(reduce_only=False),
            reexecution_authorization={"status": "applied"},
        )
        self.assertEqual(unbound["status"], "hold_until_next_rebalance_slot")
        self.assertTrue(unbound["hold_until_next_rebalance_slot"])

        mismatched = completed_slot_execution_gate(
            slot_record=record,
            plan=_plan(reduce_only=False),
            reexecution_authorization={"status": "applied", "slot_id": "slot-1", "target_hash": "other-hash"},
        )
        self.assertEqual(mismatched["status"], "hold_until_next_rebalance_slot")

        matched = completed_slot_execution_gate(
            slot_record=record,
            plan=_plan(reduce_only=False),
            reexecution_authorization={"status": "applied", "slot_id": "slot-1", "target_hash": "hash-1"},
        )
        self.assertEqual(matched["status"], "manual_owner_reexecution_allowed")
        self.assertFalse(matched["hold_until_next_rebalance_slot"])

    def test_completed_slot_reduce_only_cleanup_requires_owner_budget_canary(self) -> None:
        gate = completed_slot_execution_gate(
            slot_record={"status": "completed", "slot_id": "slot-1", "target_hash": "hash-1"},
            plan=_plan(reduce_only=True),
            current_budget_epoch_id="epoch-1",
        )
        self.assertEqual(gate["status"], "risk_only_reduce_cleanup_requires_owner_budget_canary")
        self.assertTrue(gate["hold_until_next_rebalance_slot"])
        self.assertIn("risk_only_reduce_cleanup_owner_authorization_missing", gate["blockers"])

    def test_completed_slot_allows_single_use_risk_only_cleanup_after_canary_and_budget_binding(self) -> None:
        gate = completed_slot_execution_gate(
            slot_record={"status": "completed", "slot_id": "slot-1", "target_hash": "hash-1"},
            plan=_plan(reduce_only=True),
            risk_only_reduce_cleanup_authorization=_risk_only_auth(),
            current_budget_epoch_id="epoch-1",
        )
        self.assertEqual(gate["status"], "risk_only_reduce_cleanup_allowed")
        self.assertFalse(gate["hold_until_next_rebalance_slot"])
        self.assertEqual(gate["budget_epoch_id"], "epoch-1")
        self.assertEqual(gate["no_order_canary"]["artifact_root"], "artifact-root")

    def test_completed_slot_blocks_risk_only_cleanup_on_budget_mismatch(self) -> None:
        gate = completed_slot_execution_gate(
            slot_record={"status": "completed", "slot_id": "slot-1", "target_hash": "hash-1"},
            plan=_plan(reduce_only=True),
            risk_only_reduce_cleanup_authorization=_risk_only_auth(),
            current_budget_epoch_id="other-epoch",
        )
        self.assertEqual(gate["status"], "risk_only_reduce_cleanup_requires_owner_budget_canary")
        self.assertIn(
            "risk_only_reduce_cleanup_budget_epoch_mismatch:expected=epoch-1:actual=other-epoch",
            gate["blockers"],
        )

    def test_completed_slot_blocks_risk_only_cleanup_after_consumption(self) -> None:
        gate = completed_slot_execution_gate(
            slot_record={"status": "completed", "slot_id": "slot-1", "target_hash": "hash-1"},
            plan=_plan(reduce_only=True),
            risk_only_reduce_cleanup_authorization=_risk_only_auth(),
            risk_only_reduce_cleanup_consumed={
                "status": "applied",
                "slot_id": "slot-1",
                "target_hash": "hash-1",
                "action_id": "consume-1",
            },
            current_budget_epoch_id="epoch-1",
        )
        self.assertEqual(gate["status"], "risk_only_reduce_cleanup_requires_owner_budget_canary")
        self.assertIn("risk_only_reduce_cleanup_authorization_already_consumed", gate["blockers"])


def _plan(*, reduce_only: bool) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        portfolio_id="portfolio-1",
        mode="plan_only",
        status="ok",
        intents=[
            OrderIntent(
                intent_id="intent-1",
                portfolio_id="portfolio-1",
                symbol="L1USDT",
                side="SELL" if reduce_only else "BUY",
                position_side="BOTH",
                order_type="MARKET",
                quantity=1.0,
                reduce_only=reduce_only,
                target_position_amt=0.0 if reduce_only else 2.0,
                current_position_amt=1.0,
                delta_position_amt=-1.0 if reduce_only else 1.0,
                max_slippage_bps=20.0,
                client_order_id="intent-1",
                execution_phase="reduce_first" if reduce_only else "entry_second",
            )
        ],
        active_execution_phase="reduce_first" if reduce_only else "entry_second",
        phase_counts={"reduce_first" if reduce_only else "entry_second": 1},
    )


def _risk_only_auth() -> dict:
    return {
        "status": "applied",
        "slot_id": "slot-1",
        "target_hash": "hash-1",
        "action_id": "auth-1",
        "budget_epoch_id": "epoch-1",
        "single_use": True,
        "no_order_canary": {
            "status": "passed",
            "artifact_root": "artifact-root",
            "orders_submitted": 0,
            "mainnet_order_submission_authorized": False,
        },
    }


if __name__ == "__main__":
    unittest.main()
