from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.live_risk_controls import (  # noqa: E402
    classify_exception_strategy,
    evaluate_account_snapshot_age_gate,
    evaluate_margin_cushion_gate,
    removed_daily_realized_pnl_gate,
)


class HvBalancedLiveRiskControlsTests(unittest.TestCase):
    def test_removed_daily_realized_pnl_gate_is_non_blocking_marker(self) -> None:
        result = removed_daily_realized_pnl_gate(config=_config(max_loss=10.0, enforcement="active"))

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["enforcement"], "disabled")
        self.assertEqual(result["mechanism"], "daily_realized_pnl_loss_cap_removed")

    def test_margin_cushion_gate_blocks_low_available_balance(self) -> None:
        result = evaluate_margin_cushion_gate(
            {"available_balance_usdt": 40.0, "total_wallet_balance_usdt": 1476.0},
            config=_config(max_loss=10.0, enforcement="active"),
            planned_additional_initial_margin_usdt=0.0,
            require_configured=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("available_balance_below_min_after_plan:") for item in result["blockers"]))
        self.assertTrue(any(item.startswith("available_balance_ratio_below_min_after_plan:") for item in result["blockers"]))

    def test_margin_cushion_gate_require_configured_blocks_when_thresholds_absent(self) -> None:
        result = evaluate_margin_cushion_gate(
            {"available_balance_usdt": 5000.0, "total_wallet_balance_usdt": 10000.0},
            config={"risk": {}},
            planned_additional_initial_margin_usdt=0.0,
            require_configured=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("margin_cushion_gate_not_configured", result["blockers"])

    def test_snapshot_age_gate_fresh_passes(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {"fetched_at_ms": 1_000_000_000_000},
            config=_config(max_loss=10.0, enforcement="active", snapshot_age=30),
            now_ms=1_000_000_005_000,  # 5s later
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["age_seconds"], 5.0)

    def test_snapshot_age_gate_stale_blocks(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {"fetched_at_ms": 1_000_000_000_000},
            config=_config(max_loss=10.0, enforcement="active", snapshot_age=30),
            now_ms=1_000_000_045_000,  # 45s later > 30s
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("account_snapshot_stale:") for item in result["blockers"]))

    def test_snapshot_age_gate_future_timestamp_blocks(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {"fetched_at_ms": 1_000_000_010_000},
            config=_config(max_loss=10.0, enforcement="active", snapshot_age=30),
            now_ms=1_000_000_000_000,  # snapshot stamped in the future
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("account_snapshot_timestamp_in_future:") for item in result["blockers"]))

    def test_snapshot_age_gate_missing_fetched_at_blocks_when_configured(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {},
            config=_config(max_loss=10.0, enforcement="active", snapshot_age=30),
            now_ms=1_000_000_000_000,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("account_snapshot_fetched_at_unreadable", result["blockers"])

    def test_snapshot_age_gate_noop_when_unconfigured(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {},
            config={"risk": {}},
            now_ms=1_000_000_000_000,
        )

        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["passed"])

    def test_snapshot_age_gate_require_configured_blocks_when_unconfigured(self) -> None:
        result = evaluate_account_snapshot_age_gate(
            {"fetched_at_ms": 1_000_000_000_000},
            config={"risk": {}},
            now_ms=1_000_000_000_000,
            require_configured=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("account_snapshot_age_gate_not_configured", result["blockers"])

    def test_exception_policy_maps_pnl_and_unknown_order(self) -> None:
        pnl = classify_exception_strategy(["daily_realized_pnl_below_loss_cap:-12<-10"])
        unknown = classify_exception_strategy(["unknown_order_status_recovered_stop_for_reconcile:BTCUSDT:x"])

        self.assertEqual(pnl["action"], "pause_new_entries_and_review_reduce_only_flatten")
        self.assertEqual(unknown["action"], "stop_new_entries_unknown_order_recovery")


def _config(
    *,
    max_loss: float,
    enforcement: str,
    wallet_ratio: float | None = None,
    snapshot_age: float | None = None,
) -> dict:
    return {
        "risk": {
            "max_daily_realized_loss_usdt": max_loss,
            **({"max_daily_realized_loss_wallet_ratio": wallet_ratio} if wallet_ratio is not None else {}),
            "max_daily_realized_loss_enforcement": enforcement,
            "daily_realized_pnl_income_types": "REALIZED_PNL,COMMISSION",
            "min_available_balance_after_plan_usdt": 100.0,
            "min_available_balance_ratio_after_plan": 0.05,
            "min_margin_cushion_after_plan_usdt": 100.0,
            **({"max_account_snapshot_age_seconds": snapshot_age} if snapshot_age is not None else {}),
        }
    }


if __name__ == "__main__":
    unittest.main()
