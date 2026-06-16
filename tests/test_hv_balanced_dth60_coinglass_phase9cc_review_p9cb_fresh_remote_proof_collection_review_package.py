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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CONTRACT_VERSION as P9CB_CONTRACT,
    P9CC_GATE,
    P9CC_SCOPE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cc_review_p9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    APPROVE_P9CC_DECISION,
    P9CD_GATE,
    build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package,
)


class Phase9CCReviewP9CBFreshRemoteProofCollectionPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cc-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9cb_package_only_without_remote_reads_or_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = (
            build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
                self._args(paths, output_root=self.temp_dir / "p9cc"),
                now_fn=lambda: datetime(2026, 6, 10, 17, 0, tzinfo=UTC),
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready"
            ]
        )
        self.assertTrue(
            summary[
                "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate"
            ]
        )
        self.assertTrue(summary["eligible_for_future_p9cd_owner_gate"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["fresh_remote_proof_collection_owner_gate_approved_in_p9cc"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cc"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertEqual(summary["target_runner_identity_hint"], TARGET_RUNNER_IDENTITY_HINT)
        self.assertFalse(summary["target_runner_identity_proven_in_p9cc"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9CD_GATE)
        self.assertEqual(summary["required_fresh_proof_count"], 12)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)

        outputs = summary["output_files"]
        review = _load_json(Path(outputs["sufficiency_review"]))
        prereq = _load_json(Path(outputs["future_gate_prerequisites"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))

        self.assertTrue(
            review[
                "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate"
            ]
        )
        self.assertFalse(review["fresh_remote_proof_collection_owner_gate_approved_in_p9cc"])
        self.assertFalse(review["fresh_remote_proof_collection_performed"])
        self.assertEqual(prereq["allowed_next_gate"], P9CD_GATE)
        self.assertIn(
            "separately requested P9CD owner gate",
            prereq["required_before_any_fresh_remote_proof_collection"],
        )
        self.assertTrue(
            matrix["authorizations"][
                "review_p9cb_fresh_remote_proof_collection_review_package"
            ]
        )
        self.assertFalse(matrix["authorizations"]["allow_fresh_remote_proof_collection_owner_gate"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_account_read"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["remote_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["fresh_proofs_collected"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cb_allowed_next_gate_is_not_p9cc(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={
                "allowed_next_gate": "P9CD_skip_review_collect_remote_proofs"
            }
        )

        summary, exit_code = (
            build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
                self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
                now_fn=lambda: datetime(2026, 6, 10, 17, 5, tzinfo=UTC),
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cb_summary_ready_for_package_review", summary["blockers"])
        self.assertFalse(
            summary[
                "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready"
            ]
        )
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9cb_package_claims_proof_collection_happened(self) -> None:
        package = _p9cb_package_payload()
        package["fresh_remote_proof_collection_performed_in_p9cb"] = True
        package["proof_collection_plan"][0]["collection_status_in_p9cb"] = "collected"
        paths = self._write_ready_inputs(package_payload=package)

        summary, exit_code = (
            build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
                self._args(paths, output_root=self.temp_dir / "bad-package"),
                now_fn=lambda: datetime(2026, 6, 10, 17, 10, tzinfo=UTC),
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cb_review_package_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cc"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = (
            build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
                self._args(
                    paths,
                    output_root=self.temp_dir / "wrong-owner",
                    owner_decision="approve_collect_fresh_remote_proofs_now",
                ),
                now_fn=lambda: datetime(2026, 6, 10, 17, 15, tzinfo=UTC),
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cc_review_only_recorded", summary["blockers"])
        self.assertFalse(
            summary[
                "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready"
            ]
        )
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CC_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cb_summary=str(paths["p9cb_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        package_payload: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cb_root = self.temp_dir / "p9cb"
        proof_root = p9cb_root / "proof_artifacts" / "p9cb"
        p9cb_summary = p9cb_root / "summary.json"
        package_path = proof_root / "fresh_remote_proof_collection_review_package.json"
        manifest_path = proof_root / "collection_manifest_template.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = {
            "contract_version": P9CB_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9cb_fresh_remote_proof_collection_review_package_prepared": True,
            "p9ca_sufficient_for_review_package": True,
            "read_only_collection_plan_packaged": True,
            "acceptance_contract_packaged": True,
            "eligible_for_future_p9cc_package_review": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "fresh_remote_proof_collection_performed_in_p9cb": False,
            "fresh_proofs_collected_in_p9cb": False,
            "fresh_remote_account_read_performed": False,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
            "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
            "target_runner_identity_proven_in_p9cb": False,
            "target_deploy_root_proven_in_p9cb": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "allowed_next_gate": P9CC_GATE,
            "allowed_next_gate_scope": P9CC_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "canary_symbol": "BTCUSDT",
            "canary_side": "BUY",
            "risk_ceiling_usdt": 25.0,
            "max_notional_usdt": 10.0,
            "max_orders_per_cycle": 1,
            "max_symbols_per_cycle": 1,
            "order_type": "post_only_limit",
            "time_in_force": "GTX",
            "market_orders_allowed": False,
            "required_fresh_proof_count": 12,
            "only_distance_to_high_60_contribution_changed": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "output_files": {
                "fresh_remote_proof_collection_review_package": str(package_path),
                "collection_manifest_template": str(manifest_path),
                "non_authorization": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(package_path, package_payload or _p9cb_package_payload())
        _write_json(manifest_path, _p9cb_manifest_payload())
        _write_json(matrix_path, _p9cb_matrix_payload())
        _write_json(control_path, _p9cb_control_payload())
        _write_json(p9cb_summary, summary)
        return {"project_profile": project_profile, "p9cb_summary": p9cb_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _proof_plan_rows() -> list[dict[str, object]]:
    proof_specs = [
        ("fresh_remote_account_read", 60),
        ("pre_position_fingerprint", 60),
        ("pre_open_order_fingerprint", 60),
        ("pre_fill_trade_fingerprint", 60),
        ("fresh_order_book", 10),
        ("exchange_filter_readback", 60),
        ("p9bu_terms_operator_acceptance", 300),
        ("candidate_target_plan_hash_binding", 60),
        ("baseline_candidate_plan_diff", 60),
        ("kill_switch_readback", 60),
        ("rollback_command_readback", 60),
        ("final_owner_live_order_gate_approval", 300),
    ]
    return [
        {
            "proof_id": proof_id,
            "required": True,
            "max_age_seconds": max_age,
            "point_in_time_safe_required": True,
            "collection_status_in_p9cb": "not_collected",
            "future_collection_status": "pending_separate_owner_gate",
            "future_collection_channel": "remote_read_only",
            "purpose": f"unit test {proof_id}",
        }
        for proof_id, max_age in proof_specs
    ]


def _p9cb_package_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_review_package.v1",
        "package_only": True,
        "future_gate_name": "fresh_remote_proof_collection_gate",
        "package_decision": "prepared_for_future_review_only",
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cb": False,
        "target_deploy_root_proven_in_p9cb": False,
        "read_only_collection_only": True,
        "fresh_remote_proof_collection_performed_in_p9cb": False,
        "proof_collection_plan": _proof_plan_rows(),
        "read_only_command_boundary": {
            "allowed_future_read_categories": [
                "account_state_read",
                "position_state_read",
                "open_order_state_read",
                "fills_and_trades_read",
                "order_book_read",
                "exchange_info_and_symbol_filter_read",
                "operator_config_and_state_readback",
                "candidate_and_baseline_artifact_hash_readback",
                "kill_switch_and_rollback_readback",
            ],
            "forbidden_future_actions_during_proof_collection": [
                "place_order",
                "cancel_order",
                "modify_order",
                "transfer_assets",
                "change_leverage",
                "change_margin_mode",
                "run_live_supervisor",
                "run_timer_path",
                "enable_or_start_production_timer_service",
                "mutate_live_config",
                "mutate_operator_state",
                "replace_executor_input",
                "replace_target_plan",
                "execute_candidate",
                "remote_sync_or_deploy_code",
                "write_files_outside_future_proof_artifact_root",
            ],
        },
        "acceptance_contract": {
            "delta_acceptance": {
                "order_delta_must_equal": 0,
                "cancel_delta_must_equal": 0,
                "fill_delta_must_equal": 0,
                "trade_delta_must_equal": 0,
                "position_delta_must_equal": 0,
                "balance_delta_must_equal": 0,
            },
            "staleness_policy": {
                "missing_proof_fails_closed": True,
                "stale_proof_fails_closed": True,
                "future_timestamp_fails_closed": True,
                "clock_skew_must_be_reported": True,
                "future_fill_or_stale_fill_evidence_must_fail_closed": True,
            },
            "hash_binding_required": {
                "candidate_target_plan_hash": True,
                "baseline_target_plan_hash": True,
                "baseline_candidate_distance_to_high_60_only_diff": True,
                "proof_artifact_manifest_hash": True,
            },
            "pre_post_fingerprints_required_for_future_collection": [
                "position_fingerprint",
                "open_order_fingerprint",
                "fills_and_trades_fingerprint",
                "account_balance_fingerprint",
            ],
            "no_order_collection_phase_must_prove": [
                "baseline-only executor remains unchanged",
                "candidate remains shadow-only until a later gate explicitly changes path authority",
                "zero order submissions",
                "zero cancels",
                "zero fills",
                "zero trades",
                "no live config mutation",
                "no operator state mutation",
                "no timer or service mutation",
            ],
        },
        "future_gate_may_discuss": [
            "whether to execute a separately owner-approved read-only fresh proof collection run",
            "target runner identity readback requirements",
            "fresh account, position, open-order, fill/trade, order-book, and exchange-filter proof collection",
            "pre/post fingerprint delta acceptance for a no-order collection run",
        ],
        "future_gate_may_not_discuss": [
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor input mutation",
            "supervisor or timer invocation",
            "remote sync or deployment",
        ],
        "baseline_target_plan_sha256": BASELINE_SHA,
        "candidate_target_plan_sha256": CANDIDATE_SHA,
        "only_distance_to_high_60_contribution_changed": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _p9cb_manifest_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_collection_manifest_template.v1",
        "package_only": True,
        "template_only_not_executed": True,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "future_collection_requires_separate_owner_gate": True,
        "required_output_artifacts": [
            "remote_runner_identity_readback.json",
            "fresh_remote_account_read.json",
            "pre_position_fingerprint.json",
            "pre_open_order_fingerprint.json",
            "pre_fill_trade_fingerprint.json",
            "fresh_order_book.json",
            "exchange_filter_readback.json",
            "p9bu_terms_operator_acceptance.json",
            "candidate_target_plan_hash_binding.json",
            "baseline_candidate_plan_diff.json",
            "kill_switch_readback.json",
            "rollback_command_readback.json",
            "post_position_fingerprint.json",
            "post_open_order_fingerprint.json",
            "post_fill_trade_fingerprint.json",
            "proof_collection_delta_acceptance.json",
            "proof_artifact_manifest.json",
        ],
        "proof_ids": [item["proof_id"] for item in _proof_plan_rows()],
        "commands_executed_in_p9cb": [],
        "fresh_proofs_collected_in_p9cb": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _p9cb_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_non_authorization.v1",
        "authorizations": {
            "prepare_fresh_remote_proof_collection_review_package": True,
            "review_fresh_remote_proof_collection_review_package": True,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }


def _p9cb_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_control_boundary.v1",
        "scope": "fresh_remote_proof_collection_review_package_preparation_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
