from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10j_review_p10i_single_cycle_live_delta_canary import (  # noqa: E402
    APPROVE_P10J_DECISION,
    P10K_GATE,
    build_p10j,
)


class HvBalanced12FactorP10jReviewP10iTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10j-review-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_review_allows_only_next_discussion_scope_gate(self) -> None:
        paths = self._write_ready_p10i_bundle()

        summary, exit_code = build_p10j(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10j-ready"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p10j_review_p10i_single_cycle_live_delta_canary_ready"])
        self.assertTrue(summary["p10i_retained_evidence_sufficient_for_p10j_review"])
        self.assertTrue(summary["p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion"])
        self.assertFalse(summary["p10i_sufficient_for_live_order_submission_without_new_gate"])
        self.assertFalse(summary["p10i_sufficient_for_candidate_executor_path_execution_without_new_gate"])
        self.assertFalse(summary["p10i_sufficient_for_continuous_automated_order_flow"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["p10i_orders_submitted"], 1)
        self.assertEqual(summary["p10i_orders_canceled"], 1)
        self.assertEqual(summary["p10i_fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P10K_GATE)

        review = _load_json(Path(summary["output_files"]["p10i_retained_evidence_review"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(review["p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion"])
        self.assertFalse(review["p10i_sufficient_for_live_order_submission_without_new_gate"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p10j"])
        self.assertFalse(non_auth["authorizations"]["continuous_automated_order_flow"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_blocks_when_remote_submission_did_not_cancel(self) -> None:
        paths = self._write_ready_p10i_bundle()
        submission = _load_json(paths["submission"])
        submission["orders_canceled"] = 0
        submission["order_cancel"]["status"] = "not_attempted"
        submission["order_cancel"]["payload"]["status"] = "NEW"
        _write_json(paths["submission"], submission)

        summary, exit_code = build_p10j(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10j-bad-submit"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10i_remote_submission_ready", summary["blockers"])
        self.assertFalse(summary["p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p10i_summary_not_ready(self) -> None:
        paths = self._write_ready_p10i_bundle()
        p10i = _load_json(paths["p10i_summary"])
        p10i["status"] = "blocked"
        p10i["blockers"] = ["unit_test_blocker"]
        _write_json(paths["p10i_summary"], p10i)

        summary, exit_code = build_p10j(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10j-bad-summary"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p10i_summary_ready_for_review", summary["blockers"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            p10i_summary=str(paths["p10i_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P10J_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_p10i_bundle(self) -> dict[str, Path]:
        root = self.temp_dir / "p10i"
        proof = root / "proof"
        project_profile = self.temp_dir / "project_profile.json"
        p10i_summary = root / "summary.json"
        candidate_delta = proof / "candidate_delta_binding.json"
        plan = proof / "canary_order_plan.json"
        submission = proof / "remote_single_cycle_live_delta_canary_order_submission.json"
        control = proof / "control_boundary_readback.json"
        account_delta = proof / "account_delta_acceptance.json"
        account_history = proof / "account_history_delta_acceptance.json"
        market_delta = proof / "market_proof_collection_delta_acceptance.json"
        identity = proof / "remote_runner_identity_readback.json"
        command_records = root / "command_records.json"
        manifest = proof / "proof_artifact_manifest.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            candidate_delta,
            {
                "contract_version": "hv_balanced_12factor_p10i_candidate_delta_binding.v1",
                "status": "ready",
                "blockers": [],
                "symbol": "BTCUSDT",
                "side": "SELL",
                "side_source": "P10G.target_plan_diff.target_notional_delta_usdt",
                "target_notional_delta_usdt": "-1497.7849977386668",
                "canary_notional_usdt": "75",
            },
        )
        _write_json(
            plan,
            {
                "contract_version": "hv_balanced_12factor_p10i_canary_order_plan.v1",
                "status": "ready",
                "blockers": [],
                "symbol": "BTCUSDT",
                "side": "SELL",
                "price": "63219.6",
                "quantity": "0.001",
                "notional_usdt": "63.2196",
                "minimum_executable_notional_usdt": "63.2196",
                "order_type": "post_only_limit",
                "time_in_force": "GTX",
                "market_orders_allowed": False,
                "post_only_required": True,
                "maker_only_required": True,
                "limit_order_must_not_cross_spread": True,
            },
        )
        _write_json(
            submission,
            {
                "contract_version": "hv_balanced_12factor_p10i_remote_single_cycle_live_delta_canary_submitter.v1",
                "status": "ready",
                "blockers": [],
                "orders_submitted": 1,
                "orders_canceled": 1,
                "fill_count": 0,
                "trade_count": 0,
                "order_submission": {
                    "status": "ok",
                    "payload": {
                        "symbol": "BTCUSDT",
                        "side": "SELL",
                        "type": "LIMIT",
                        "timeInForce": "GTX",
                        "origQty": "0.001",
                        "executedQty": "0.000",
                        "status": "NEW",
                    },
                },
                "order_query": {"status": "ok", "payload": {"status": "NEW", "executedQty": "0.000"}},
                "order_cancel": {"status": "ok", "payload": {"status": "CANCELED", "executedQty": "0.000"}},
                "post_submit_readback": {"open_orders": {"status": "ok", "payload": []}},
                "side_effects": {
                    "http_methods_used": ["GET", "POST", "DELETE"],
                    "remote_files_written": 0,
                    "remote_sync_performed": False,
                    "supervisor_invoked": False,
                    "timer_path_invoked": False,
                    "candidate_executed": False,
                    "executor_input_mutated": False,
                    "target_plan_replaced": False,
                    "continuous_automation_enabled": False,
                },
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_12factor_p10i_control_boundary.v1",
                "scope": "single_cycle_live_delta_canary_only",
                "ssh_invoked": True,
                "remote_network_connection_performed": True,
                "fresh_remote_account_read_performed": True,
                "fresh_order_book_read_performed": True,
                "exchange_filter_read_performed": True,
                "live_order_submission_performed": True,
                "orders_submitted": 1,
                "orders_canceled": 1,
                "fill_count": 0,
                "trade_count": 0,
                "entered_timer_path": False,
                "ran_supervisor": False,
                "timer_path_loaded": False,
                "target_plan_replaced": False,
                "executor_input_changed": False,
                "continuous_automation_enabled": False,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "remote_files_written": 0,
                "remote_sync_performed": False,
            },
        )
        _write_json(
            account_delta,
            {
                "position_fingerprint_stable": True,
                "open_order_fingerprint_stable": True,
                "balance_fingerprint_stable": True,
                "open_order_count_zero_pre_post": True,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
            },
        )
        _write_json(account_history, {"order_cancel_fill_trade_delta_zero": True})
        _write_json(
            market_delta,
            {
                "position_fingerprint_stable": True,
                "open_order_fingerprint_stable": True,
                "balance_fingerprint_stable": True,
                "fill_trade_fingerprint_stable": True,
                "order_cancel_fill_trade_delta_zero": True,
            },
        )
        _write_json(
            identity,
            {
                "account_collector_identity_ready": True,
                "market_collector_identity_ready": True,
            },
        )
        _write_json(
            command_records,
            {
                "commands": [
                    {"label": "pre_control_snapshot"},
                    {"label": "remote_stdout_pit_safe_v2v3_account_collector"},
                    {"label": "remote_stdout_market_and_fingerprint_collector"},
                    {"label": "remote_single_cycle_live_delta_canary_order_submitter"},
                    {"label": "post_control_snapshot"},
                ]
            },
        )
        _write_json(manifest, {"artifact_count": 13, "self": {"sha256": "manifest-sha"}})
        _write_json(
            p10i_summary,
            {
                "contract_version": "hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary.v1",
                "status": "ready",
                "blockers": [],
                "p10i_single_cycle_live_delta_canary_ready": True,
                "p10h_sufficient_for_p10i_execution": True,
                "p10g_hash_bound_to_p10h": True,
                "candidate_delta_binding_ready": True,
                "candidate_delta_side": "SELL",
                "candidate_delta_notional_usdt": "-1497.7849977386668",
                "canary_symbol": "BTCUSDT",
                "canary_side": "SELL",
                "canary_capped_notional_usdt": "75",
                "canary_notional_usdt": "63.2196",
                "canary_quantity": "0.001",
                "fresh_pre_submit_readback_performed": True,
                "fresh_remote_account_read_performed": True,
                "fresh_order_book_read_performed": True,
                "exchange_filter_read_performed": True,
                "pit_safe_v2v3_account_proof_ready": True,
                "can_trade_decision_source": "/fapi/v2/account.canTrade",
                "can_trade_pre": True,
                "can_trade_post": True,
                "canary_order_plan_ready": True,
                "order_type": "post_only_limit",
                "time_in_force": "GTX",
                "market_orders_allowed": False,
                "post_only_required": True,
                "maker_only_required": True,
                "limit_order_must_not_cross_spread": True,
                "live_order_submission_authorized": True,
                "live_order_submission_performed": True,
                "actual_live_order_submission_performed": True,
                "orders_submitted": 1,
                "orders_canceled": 1,
                "fill_count": 0,
                "trade_count": 0,
                "remote_control_boundary_unchanged": True,
                "actual_target_plan_replacement_performed": False,
                "actual_executor_input_mutation_performed": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "continuous_automation_enabled": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "allowed_next_gate": "P10J_review_p10i_single_cycle_live_delta_canary_only_if_separately_requested",
                "allowed_next_gate_scope": "review_p10i_retained_evidence_before_any_limited_live_delta_or_continuous_candidate_execution_discussion",
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "candidate_delta_binding": str(candidate_delta),
                    "canary_order_plan": str(plan),
                    "remote_single_cycle_live_delta_canary_order_submission": str(submission),
                    "control_boundary_readback": str(control),
                    "account_delta_acceptance": str(account_delta),
                    "account_history_delta_acceptance": str(account_history),
                    "market_proof_collection_delta_acceptance": str(market_delta),
                    "remote_runner_identity_readback": str(identity),
                    "command_records": str(command_records),
                    "proof_artifact_manifest": str(manifest),
                },
            },
        )
        return {
            "project_profile": project_profile,
            "p10i_summary": p10i_summary,
            "submission": submission,
        }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
