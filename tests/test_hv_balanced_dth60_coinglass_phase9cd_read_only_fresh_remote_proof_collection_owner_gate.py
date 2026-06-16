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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cc_review_p9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CONTRACT_VERSION as P9CC_CONTRACT,
    P9CD_GATE,
    P9CD_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cd_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    APPROVE_P9CD_DECISION,
    P9CE_GATE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
    build_p9cd_read_only_fresh_remote_proof_collection_owner_gate,
)


class Phase9CDReadOnlyFreshRemoteProofCollectionOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cd-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_allows_future_p9ce_gate_but_does_not_collect_or_order(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(
            self._args(paths, output_root=self.temp_dir / "p9cd"),
            now_fn=lambda: datetime(2026, 6, 10, 18, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready"
            ]
        )
        self.assertTrue(
            summary[
                "read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd"
            ]
        )
        self.assertTrue(
            summary[
                "eligible_for_future_p9ce_read_only_collection_execution_gate"
            ]
        )
        self.assertFalse(
            summary[
                "eligible_for_future_fresh_remote_proof_collection_without_separate_request"
            ]
        )
        self.assertFalse(summary["fresh_remote_proof_collection_execution_approved_in_p9cd"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cd"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertEqual(summary["target_runner_identity_hint"], TARGET_RUNNER_IDENTITY_HINT)
        self.assertFalse(summary["target_runner_identity_proven_in_p9cd"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9CE_GATE)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)

        outputs = summary["output_files"]
        owner = _load_json(Path(outputs["owner_decision_record"]))
        terms = _load_json(Path(outputs["read_only_collection_gate_terms"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))

        self.assertTrue(
            owner["read_only_fresh_remote_proof_collection_owner_gate_approved"]
        )
        self.assertFalse(owner["fresh_remote_proof_collection_execution_approved_in_p9cd"])
        self.assertEqual(terms["allowed_next_gate"], P9CE_GATE)
        self.assertTrue(terms["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(terms["read_only_fresh_remote_proof_collection_may_be_requested_next"])
        self.assertFalse(terms["read_only_collection_execution_performed_in_p9cd"])
        self.assertEqual(len(terms["required_proofs"]), 12)
        self.assertIn(
            "place_order",
            terms["forbidden_future_actions_during_proof_collection"],
        )
        self.assertTrue(
            matrix["authorizations"][
                "allow_future_p9ce_read_only_collection_gate_request"
            ]
        )
        self.assertFalse(
            matrix["authorizations"][
                "execute_read_only_fresh_remote_proof_collection_in_p9cd"
            ]
        )
        self.assertFalse(matrix["authorizations"]["fresh_remote_account_read"])
        self.assertFalse(matrix["authorizations"]["fresh_order_book_read"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["remote_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["fresh_proofs_collected"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cc_allowed_next_gate_is_not_p9cd(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={
                "allowed_next_gate": "P9CE_skip_owner_gate_collect_now"
            }
        )

        summary, exit_code = build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(
            self._args(paths, output_root=self.temp_dir / "wrong-next"),
            now_fn=lambda: datetime(2026, 6, 10, 18, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cc_summary_ready_for_owner_gate", summary["blockers"])
        self.assertFalse(
            summary[
                "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready"
            ]
        )
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9cc_claims_collection_or_account_read(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={
                "fresh_remote_proof_collection_performed_in_p9cc": True,
                "fresh_remote_account_read_performed": True,
            },
            control_overrides={
                "fresh_remote_account_read_performed": True,
            },
        )

        summary, exit_code = build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(
            self._args(paths, output_root=self.temp_dir / "collected"),
            now_fn=lambda: datetime(2026, 6, 10, 18, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cc_summary_ready_for_owner_gate", summary["blockers"])
        self.assertIn("p9cc_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cd"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_remote_proofs_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 18, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cd_owner_gate_recorded", summary["blockers"])
        self.assertFalse(
            summary[
                "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready"
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
        owner_decision: str = APPROVE_P9CD_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cc_summary=str(paths["p9cc_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        control_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cc_root = self.temp_dir / "p9cc"
        proof_root = p9cc_root / "proof_artifacts" / "p9cc"
        p9cc_summary = p9cc_root / "summary.json"
        sufficiency_path = proof_root / "sufficiency_review.json"
        prereq_path = proof_root / "future_gate_prerequisites.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = _p9cc_summary_payload(
            sufficiency_path,
            prereq_path,
            matrix_path,
            control_path,
        )
        summary.update(summary_overrides or {})
        control = _p9cc_control_payload()
        control.update(control_overrides or {})
        _write_json(sufficiency_path, _p9cc_sufficiency_payload())
        _write_json(prereq_path, _p9cc_prereq_payload())
        _write_json(matrix_path, _p9cc_matrix_payload())
        _write_json(control_path, control)
        _write_json(p9cc_summary, summary)
        return {"project_profile": project_profile, "p9cc_summary": p9cc_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _p9cc_summary_payload(
    sufficiency_path: Path,
    prereq_path: Path,
    matrix_path: Path,
    control_path: Path,
) -> dict[str, object]:
    return {
        "contract_version": P9CC_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready": True,
        "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate": True,
        "eligible_for_future_p9cd_owner_gate": True,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_owner_gate_approved_in_p9cc": False,
        "fresh_remote_proof_collection_performed_in_p9cc": False,
        "fresh_proofs_collected_in_p9cc": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cc": False,
        "target_deploy_root_proven_in_p9cc": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "allowed_next_gate": P9CD_GATE,
        "allowed_next_gate_scope": P9CD_SCOPE,
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
            "sufficiency_review": str(sufficiency_path),
            "future_gate_prerequisites": str(prereq_path),
            "non_authorization": str(matrix_path),
            "control_boundary_readback": str(control_path),
        },
    }


def _p9cc_sufficiency_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_sufficiency_review.v1",
        "status": "ready",
        "checks": {
            "owner_decision_p9cc_review_only_recorded": True,
            "project_profile_exists": True,
            "current_stage_is_stage3": True,
            "p9cb_summary_exists": True,
            "p9cb_summary_ready_for_package_review": True,
            "p9cb_review_package_ready": True,
            "p9cb_manifest_template_ready": True,
            "p9cb_non_authorization_ready": True,
            "p9cb_control_boundary_ready": True,
        },
        "blockers": [],
        "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate": True,
        "fresh_remote_proof_collection_owner_gate_approved_in_p9cc": False,
        "fresh_remote_proof_collection_performed": False,
        "live_order_gate_approved": False,
    }


def _p9cc_prereq_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_future_gate_prerequisites.v1",
        "allowed_next_gate": P9CD_GATE,
        "allowed_next_gate_scope": P9CD_SCOPE,
        "required_before_any_fresh_remote_proof_collection": [
            "separately requested P9CD owner gate",
            "explicit owner approval for read-only proof collection only",
            "target runner identity and deploy-root readback plan",
            "strict read-only command manifest using retained P9CB package",
            "pre/post account, position, open-order, fill/trade fingerprints",
            "zero order/cancel/fill/trade/position/balance delta acceptance contract",
            "fresh proof artifacts retained under a dedicated proof root",
        ],
        "still_required_before_any_future_live_order_submission": [
            "fresh proofs collected and reviewed in later gates",
            "fresh no-order candidate executor input hash binding",
            "post-only order price proof from fresh order book",
            "kill switch and rollback readback",
            "final owner live-order gate approval",
        ],
    }


def _p9cc_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_non_authorization.v1",
        "authorizations": {
            "review_p9cb_fresh_remote_proof_collection_review_package": True,
            "allow_fresh_remote_proof_collection_owner_gate": False,
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


def _p9cc_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_control_boundary.v1",
        "scope": "p9cb_package_review_only",
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
