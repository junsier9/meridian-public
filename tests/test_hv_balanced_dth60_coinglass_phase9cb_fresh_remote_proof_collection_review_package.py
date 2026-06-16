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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ca_fresh_remote_proof_collection_scope import (  # noqa: E402
    CONTRACT_VERSION as P9CA_CONTRACT,
    P9CB_GATE,
    P9CB_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    APPROVE_P9CB_DECISION,
    P9CC_GATE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
    build_p9cb_fresh_remote_proof_collection_review_package,
)


class Phase9CBFreshRemoteProofCollectionReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cb-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_package_only_without_remote_reads_or_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9cb_fresh_remote_proof_collection_review_package(
            self._args(paths, output_root=self.temp_dir / "p9cb"),
            now_fn=lambda: datetime(2026, 6, 10, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cb_fresh_remote_proof_collection_review_package_prepared"])
        self.assertTrue(summary["p9ca_sufficient_for_review_package"])
        self.assertTrue(summary["read_only_collection_plan_packaged"])
        self.assertTrue(summary["acceptance_contract_packaged"])
        self.assertTrue(summary["eligible_for_future_p9cc_package_review"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cb"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertEqual(summary["target_runner_identity_hint"], TARGET_RUNNER_IDENTITY_HINT)
        self.assertEqual(summary["target_deploy_root_hint"], TARGET_DEPLOY_ROOT_HINT)
        self.assertFalse(summary["target_runner_identity_proven_in_p9cb"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9CC_GATE)
        self.assertEqual(summary["required_fresh_proof_count"], 12)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)

        outputs = summary["output_files"]
        package = _load_json(Path(outputs["fresh_remote_proof_collection_review_package"]))
        manifest = _load_json(Path(outputs["collection_manifest_template"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))

        self.assertTrue(package["package_only"])
        self.assertEqual(package["future_gate_name"], "fresh_remote_proof_collection_gate")
        self.assertFalse(package["fresh_remote_proof_collection_performed_in_p9cb"])
        self.assertEqual(len(package["proof_collection_plan"]), 12)
        self.assertTrue(
            all(
                item["collection_status_in_p9cb"] == "not_collected"
                and item["future_collection_status"] == "pending_separate_owner_gate"
                for item in package["proof_collection_plan"]
            )
        )
        self.assertIn(
            "place_order",
            package["read_only_command_boundary"][
                "forbidden_future_actions_during_proof_collection"
            ],
        )
        self.assertEqual(
            package["acceptance_contract"]["delta_acceptance"]["order_delta_must_equal"],
            0,
        )
        self.assertTrue(
            package["acceptance_contract"]["staleness_policy"][
                "future_fill_or_stale_fill_evidence_must_fail_closed"
            ]
        )

        self.assertTrue(manifest["package_only"])
        self.assertTrue(manifest["template_only_not_executed"])
        self.assertEqual(manifest["commands_executed_in_p9cb"], [])
        self.assertFalse(manifest["fresh_proofs_collected_in_p9cb"])
        self.assertEqual(len(manifest["proof_ids"]), 12)
        self.assertIn("proof_artifact_manifest.json", manifest["required_output_artifacts"])

        self.assertTrue(
            matrix["authorizations"][
                "prepare_fresh_remote_proof_collection_review_package"
            ]
        )
        self.assertFalse(matrix["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_account_read"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["remote_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["fresh_proofs_collected"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9ca_allowed_next_gate_is_not_p9cb(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={
                "allowed_next_gate": "P9CC_skip_package_collect_remote_proofs"
            }
        )

        summary, exit_code = build_p9cb_fresh_remote_proof_collection_review_package(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ca_summary_ready_for_review_package", summary["blockers"])
        self.assertFalse(summary["p9cb_fresh_remote_proof_collection_review_package_prepared"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9ca_scope_claims_proof_collection_happened(self) -> None:
        scope = _p9ca_scope_payload()
        scope["fresh_remote_proof_collection_performed_in_p9ca"] = True
        scope["required_fresh_proofs"][0]["collection_status_in_p9ca"] = "collected"
        paths = self._write_ready_inputs(scope_payload=scope)

        summary, exit_code = build_p9cb_fresh_remote_proof_collection_review_package(
            self._args(paths, output_root=self.temp_dir / "bad-scope"),
            now_fn=lambda: datetime(2026, 6, 10, 16, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ca_scope_ready", summary["blockers"])
        self.assertFalse(summary["p9cb_fresh_remote_proof_collection_review_package_prepared"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9cb_fresh_remote_proof_collection_review_package(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_fresh_remote_proofs_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 16, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cb_package_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9cb_fresh_remote_proof_collection_review_package_prepared"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CB_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ca_summary=str(paths["p9ca_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        scope_payload: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9ca_root = self.temp_dir / "p9ca"
        proof_root = p9ca_root / "proof_artifacts" / "p9ca"
        p9ca_summary = p9ca_root / "summary.json"
        scope_path = proof_root / "fresh_remote_proof_collection_scope.json"
        boundary_path = proof_root / "read_only_command_boundary.json"
        acceptance_path = proof_root / "proof_collection_acceptance_contract.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = {
            "contract_version": P9CA_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9ca_fresh_remote_proof_collection_scope_defined": True,
            "p9bz_sufficient_for_scope_definition": True,
            "read_only_command_boundary_defined": True,
            "proof_collection_acceptance_contract_defined": True,
            "eligible_for_future_p9cb_package_preparation": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "fresh_remote_proof_collection_performed_in_p9ca": False,
            "fresh_proofs_collected_in_p9ca": False,
            "fresh_remote_account_read_performed": False,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
            "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
            "target_runner_identity_proven_in_p9ca": False,
            "target_deploy_root_proven_in_p9ca": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "allowed_next_gate": P9CB_GATE,
            "allowed_next_gate_scope": P9CB_SCOPE,
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
                "fresh_remote_proof_collection_scope": str(scope_path),
                "read_only_command_boundary": str(boundary_path),
                "proof_collection_acceptance_contract": str(acceptance_path),
                "non_authorization": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(scope_path, scope_payload or _p9ca_scope_payload())
        _write_json(boundary_path, _p9ca_boundary_payload())
        _write_json(acceptance_path, _p9ca_acceptance_payload())
        _write_json(matrix_path, _p9ca_matrix_payload())
        _write_json(control_path, _p9ca_control_payload())
        _write_json(p9ca_summary, summary)
        return {"project_profile": project_profile, "p9ca_summary": p9ca_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _proof_rows() -> list[dict[str, object]]:
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
            "collection_status_in_p9ca": "not_collected",
            "future_collection_requires_separate_owner_gate": True,
            "must_be_point_in_time_safe": True,
            "purpose": f"unit test {proof_id}",
        }
        for proof_id, max_age in proof_specs
    ]


def _p9ca_scope_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_scope.v1",
        "scope_definition_only": True,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9ca": False,
        "target_deploy_root_proven_in_p9ca": False,
        "read_only_collection_only": True,
        "fresh_remote_proof_collection_performed_in_p9ca": False,
        "future_collection_requires_separate_owner_gate": True,
        "required_fresh_proofs": _proof_rows(),
        "canary_terms_carried_forward_for_future_review": {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "risk_ceiling_usdt": 25.0,
            "max_notional_usdt": 10.0,
            "max_orders_per_cycle": 1,
            "max_symbols_per_cycle": 1,
            "order_type": "post_only_limit",
            "time_in_force": "GTX",
            "market_orders_allowed": False,
            "would_submit_order_in_p9ca": False,
        },
    }


def _p9ca_boundary_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_read_only_command_boundary.v1",
        "scope_definition_only": True,
        "commands_executed_in_p9ca": [],
        "ssh_invoked_in_p9ca": False,
        "remote_network_connection_performed_in_p9ca": False,
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
    }


def _p9ca_acceptance_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_acceptance_contract.v1",
        "scope_definition_only": True,
        "fresh_proofs_collected_in_p9ca": False,
        "future_collection_requires_separate_owner_gate": True,
        "max_age_contract_by_proof_id": {
            "fresh_remote_account_read": 60,
            "pre_position_fingerprint": 60,
            "pre_open_order_fingerprint": 60,
            "pre_fill_trade_fingerprint": 60,
            "fresh_order_book": 10,
            "exchange_filter_readback": 60,
            "p9bu_terms_operator_acceptance": 300,
            "candidate_target_plan_hash_binding": 60,
            "baseline_candidate_plan_diff": 60,
            "kill_switch_readback": 60,
            "rollback_command_readback": 60,
            "final_owner_live_order_gate_approval": 300,
        },
        "delta_acceptance": {
            "order_delta_must_equal": 0,
            "cancel_delta_must_equal": 0,
            "fill_delta_must_equal": 0,
            "trade_delta_must_equal": 0,
            "position_delta_must_equal": 0,
            "balance_delta_must_equal": 0,
        },
        "pre_post_fingerprints_required_for_future_collection": [
            "position_fingerprint",
            "open_order_fingerprint",
            "fills_and_trades_fingerprint",
            "account_balance_fingerprint",
        ],
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
    }


def _p9ca_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_non_authorization.v1",
        "authorizations": {
            "define_fresh_remote_proof_collection_scope": True,
            "prepare_future_fresh_remote_proof_collection_package": True,
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


def _p9ca_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_control_boundary.v1",
        "scope": "fresh_remote_proof_collection_scope_definition_only",
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
