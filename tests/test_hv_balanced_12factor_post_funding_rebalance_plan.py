from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_12factor_post_funding_rebalance_plan import (  # noqa: E402
    run_post_funding_rebalance_plan,
)


class HvBalanced12FactorPostFundingRebalancePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv12-post-funding-plan-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_mixed_material_reduces_and_bch_dust_residual_is_ready_no_order_plan(self) -> None:
        account_proof = self.temp_dir / "fresh_read_only_account_proof.json"
        target_plan = self.temp_dir / "latest_counterfactual_target_plan.json"
        account_proof.write_text(json.dumps(_account_proof_fixture()), encoding="utf-8")
        target_plan.write_text(json.dumps(_target_plan_fixture()), encoding="utf-8")

        summary = run_post_funding_rebalance_plan(
            account_proof_path=account_proof,
            target_plan_path=target_plan,
            output_root=self.temp_dir / "out",
            run_label="fixture",
            now=datetime(2026, 6, 8, 17, 40, tzinfo=UTC),
        )

        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["raw_blocked_order_row_count"], 1)
        self.assertEqual(summary["blocked_order_row_count"], 0)
        self.assertEqual(summary["material_blocked_order_row_count"], 0)
        self.assertEqual(summary["dust_noop_row_count"], 1)
        self.assertEqual(summary["dust_noop_symbols"], ["BCHUSDT"])
        self.assertEqual(summary["dust_noop_blockers"], ["notional_below_min:BCHUSDT"])
        self.assertEqual(summary["execution_plan_status"], "ok")
        self.assertEqual(summary["active_execution_phase"], "reduce_first")
        self.assertEqual(summary["deferred_phase_counts"], {"entry_second": 1})
        self.assertEqual([intent["symbol"] for intent in summary["intents_this_cycle"]], ["DOGEUSDT", "XRPUSDT"])
        self.assertTrue(all(intent["reduce_only"] for intent in summary["intents_this_cycle"]))
        self.assertFalse(summary["timer_invoked"])
        self.assertFalse(summary["supervisor_invoked"])
        self.assertFalse(summary["executor_invoked"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fills_observed"], 0)

        sizing = pd.read_csv(summary["output_files"]["sizing_report"])
        bch = sizing.loc[sizing["symbol"].eq("BCHUSDT")].iloc[0]
        self.assertEqual(bch["delta_classification"], "dust_residual")
        self.assertEqual(bch["execution_phase"], "dust_noop")
        self.assertEqual(bch["recommended_stage"], "noop")
        self.assertEqual(bch["blockers"], "notional_below_min:BCHUSDT")


def _account_proof_fixture() -> dict:
    return {
        "status": "ready",
        "position_hash": "fixture-position-hash",
        "can_trade_v2": True,
        "open_order_count": 0,
        "open_position_count": 3,
        "account_totals": {
            "totalWalletBalance": "10801.65306773",
            "availableBalance": "8097.02120615",
        },
        "remote_runner_identity_readback": {"egress_ip": "203.0.113.10"},
        "nonzero_positions": [
            {"symbol": "BCHUSDT", "positionAmt": "-1.729", "markPrice": "207.81", "notional": "-359.30349"},
            {"symbol": "DOGEUSDT", "positionAmt": "3328", "markPrice": "0.08664", "notional": "288.33792"},
            {"symbol": "XRPUSDT", "positionAmt": "648.7", "markPrice": "1.16604744", "notional": "756.414974328"},
        ],
        "mark_prices": {
            "BCHUSDT": "207.81",
            "DOGEUSDT": "0.08664",
            "XRPUSDT": "1.16604744",
            "TRXUSDT": "0.32572",
        },
        "exchange_filters": {
            "BCHUSDT": {"step_size": "0.001", "min_qty": "0.001", "min_notional": "20"},
            "DOGEUSDT": {"step_size": "1", "min_qty": "1", "min_notional": "5"},
            "XRPUSDT": {"step_size": "0.1", "min_qty": "0.1", "min_notional": "5"},
            "TRXUSDT": {"step_size": "1", "min_qty": "1", "min_notional": "5"},
        },
    }


def _target_plan_fixture() -> dict:
    return {
        "contract_version": "fixture",
        "decision_date_utc": "2026-06-08",
        "decision_time_utc": "2026-06-08T00:01:00Z",
        "positions": [
            {"symbol": "BCHUSDT", "target_weight": -0.016666666666666666},
            {"symbol": "TRXUSDT", "target_weight": 0.16666666666666666},
            {"symbol": "DOGEUSDT", "target_weight": 0.0},
            {"symbol": "XRPUSDT", "target_weight": 0.0},
        ],
    }

