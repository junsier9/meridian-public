from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9de_review_p9dd_limited_live_delta_executor_path_discussion import (
    APPROVE_P9DE_DECISION,
    P9DF_GATE,
    build_phase9de,
)


class Phase9DEReviewP9DDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9de-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_review_allows_only_limited_discussion_scope(self) -> None:
        paths = self._write_ready_p9dd_inputs()

        summary, exit_code = build_phase9de(
            self._args(paths, output_root=self.temp_dir / "p9de"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion"
            ]
        )
        self.assertFalse(summary["p9dd_sufficient_for_live_order_submission_without_new_gate"])
        self.assertFalse(
            summary["p9dd_sufficient_for_candidate_executor_path_execution_without_new_gate"]
        )
        self.assertFalse(summary["p9dd_sufficient_for_continuous_automated_order_flow"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9DF_GATE)

        review = _load_json(
            Path(summary["output_files"]["p9dd_limited_executor_path_discussion_review"])
        )
        self.assertEqual(review["required_next_discussion_constraints"]["max_cycles_to_discuss"], 1)
        self.assertEqual(
            review["required_next_discussion_constraints"]["default_order_state"],
            "disabled_until_separate_execution_gate",
        )

    def test_blocks_if_p9dd_claims_candidate_execution(self) -> None:
        paths = self._write_ready_p9dd_inputs()
        p9dd = _load_json(paths["p9dd_summary"])
        p9dd["candidate_execution_performed"] = True
        _write_json(paths["p9dd_summary"], p9dd)

        summary, exit_code = build_phase9de(
            self._args(paths, output_root=self.temp_dir / "bad-p9de"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9dd_summary_ready_for_review", summary["blockers"])
        self.assertFalse(
            summary[
                "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion"
            ]
        )
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9dd_summary=str(paths["p9dd_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DE_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9dd_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9dd"
        proof = root / "proof_artifacts" / "p9dd" / "run"
        p9dc_proof = self.temp_dir / "p9dc" / "proof_artifacts" / "p9dc" / "run"
        project_profile = self.temp_dir / "project_profile.json"
        p9dd_summary = root / "summary.json"
        control = proof / "control_boundary_readback.json"
        submission = root / "remote_round_trip_canary_order_submission.json"
        command_records = root / "command_records.json"
        terms = p9dc_proof / "approved_round_trip_terms.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            terms,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dc_0_001_btcusdt_round_trip_canary_terms.v1",
                "allowed_next_gate": "P9DD_execute_0_001_btcusdt_buy_then_reduce_only_sell_canary",
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dd_control_boundary.v1",
                "scope": "0_001_btcusdt_limit_ioc_round_trip_canary_only",
                "ssh_invoked": True,
                "remote_network_connection_performed": True,
                "fresh_remote_account_read_performed": True,
                "fresh_order_book_read_performed": True,
                "exchange_filter_read_performed": True,
                "order_test_endpoint_called": False,
                "live_order_submission_performed": True,
                "orders_submitted": 2,
                "orders_canceled": 0,
                "fill_count": 2,
                "trade_count": 2,
                "entered_timer_path": False,
                "ran_supervisor": False,
                "timer_path_loaded": False,
                "candidate_execution_performed": False,
                "target_plan_replaced": False,
                "executor_input_changed": False,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "remote_files_written": 0,
                "remote_sync_performed": False,
            },
        )
        _write_json(
            submission,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dd_remote_round_trip_canary_submitter.v1",
                "status": "ready",
                "blockers": [],
                "symbol": "BTCUSDT",
                "quantity_btc": "0.001",
                "orders_submitted": 2,
                "orders_canceled": 0,
                "fill_count": 2,
                "trade_count": 2,
                "buy_executed_qty": "0.001",
                "sell_executed_qty": "0.001",
                "gross_turnover_usdt": "126.3007",
                "post_position_equals_pre": True,
                "buy_order_query": {
                    "payload": {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "LIMIT",
                        "timeInForce": "IOC",
                        "reduceOnly": False,
                        "status": "FILLED",
                        "origQty": "0.001",
                        "executedQty": "0.001",
                    }
                },
                "sell_order_query": {
                    "payload": {
                        "symbol": "BTCUSDT",
                        "side": "SELL",
                        "type": "LIMIT",
                        "timeInForce": "IOC",
                        "reduceOnly": True,
                        "status": "FILLED",
                        "origQty": "0.001",
                        "executedQty": "0.001",
                    }
                },
                "side_effects": {
                    "http_methods_used": ["GET", "POST"],
                    "remote_files_written": 0,
                    "remote_sync_performed": False,
                    "supervisor_invoked": False,
                    "timer_path_invoked": False,
                    "candidate_executed": False,
                    "executor_input_mutated": False,
                    "target_plan_replaced": False,
                    "order_test_endpoint_called": False,
                },
            },
        )
        _write_json(
            command_records,
            {
                "commands": [
                    {"label": "pre_control_snapshot"},
                    {"label": "remote_round_trip_canary_order_submitter"},
                    {"label": "post_control_snapshot"},
                ]
            },
        )
        _write_json(
            p9dd_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dd_execute_0_001_btcusdt_round_trip_canary.v1",
                "status": "ready",
                "blockers": [],
                "p9dd_0_001_btcusdt_round_trip_canary_ready": True,
                "p9dc_sufficient_for_p9dd_execution": True,
                "fresh_pre_submit_readback_performed": True,
                "fresh_remote_account_read_performed": True,
                "fresh_order_book_read_performed": True,
                "exchange_filter_read_performed": True,
                "can_trade_decision_source": "/fapi/v2/account.canTrade",
                "live_order_submission_authorized": True,
                "live_order_submission_performed": True,
                "actual_live_order_submission_performed": True,
                "orders_submitted": 2,
                "orders_canceled": 0,
                "fill_count": 2,
                "trade_count": 2,
                "buy_executed_qty": "0.001",
                "sell_executed_qty": "0.001",
                "post_position_equals_pre": True,
                "gross_turnover_usdt": "126.3007",
                "max_notional_per_leg_usdt": 75.0,
                "max_gross_turnover_usdt": 150.0,
                "quantity_btc": 0.001,
                "symbol": "BTCUSDT",
                "order_type": "limit_ioc_round_trip",
                "time_in_force": "IOC",
                "market_orders_allowed": False,
                "sell_leg_reduce_only_required": True,
                "remote_control_boundary_unchanged": True,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "order_test_endpoint_called": False,
                "candidate_execution_performed": False,
                "target_plan_replaced": False,
                "executor_input_mutated": False,
                "timer_path_loaded": False,
                "supervisor_invoked": False,
                "pre_btcusdt_position_amt": "0.014",
                "post_btcusdt_position_amt": "0.014",
                "output_files": {
                    "control_boundary_readback": str(control),
                    "remote_round_trip_canary_order_submission": str(submission),
                    "command_records": str(command_records),
                    "approved_round_trip_terms": str(terms),
                },
            },
        )
        return {"project_profile": project_profile, "p9dd_summary": p9dd_summary}


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
