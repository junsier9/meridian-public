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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bz_review_p9by_live_order_gate_package import (  # noqa: E402
    CONTRACT_VERSION as P9BZ_CONTRACT,
    P9CA_GATE,
    P9CA_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ca_fresh_remote_proof_collection_scope import (  # noqa: E402
    APPROVE_P9CA_DECISION,
    P9CB_GATE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
    build_p9ca_fresh_remote_proof_collection_scope,
)


class Phase9CAFreshRemoteProofCollectionScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ca-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_scope_only_without_remote_reads_or_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9ca_fresh_remote_proof_collection_scope(
            self._args(paths, output_root=self.temp_dir / "p9ca"),
            now_fn=lambda: datetime(2026, 6, 10, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9ca_fresh_remote_proof_collection_scope_defined"])
        self.assertTrue(summary["eligible_for_future_p9cb_package_preparation"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9ca"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["target_runner_identity_hint"], TARGET_RUNNER_IDENTITY_HINT)
        self.assertEqual(summary["target_deploy_root_hint"], TARGET_DEPLOY_ROOT_HINT)
        self.assertFalse(summary["target_runner_identity_proven_in_p9ca"])
        self.assertEqual(summary["allowed_next_gate"], P9CB_GATE)
        self.assertEqual(summary["required_fresh_proof_count"], 12)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)

        outputs = summary["output_files"]
        scope = _load_json(Path(outputs["fresh_remote_proof_collection_scope"]))
        boundary = _load_json(Path(outputs["read_only_command_boundary"]))
        acceptance = _load_json(Path(outputs["proof_collection_acceptance_contract"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))

        self.assertTrue(scope["scope_definition_only"])
        self.assertEqual(scope["target_runner_identity_hint"], TARGET_RUNNER_IDENTITY_HINT)
        self.assertFalse(scope["target_runner_identity_proven_in_p9ca"])
        self.assertFalse(scope["fresh_remote_proof_collection_performed_in_p9ca"])
        self.assertEqual(len(scope["required_fresh_proofs"]), 12)
        self.assertTrue(
            all(
                item["collection_status_in_p9ca"] == "not_collected"
                for item in scope["required_fresh_proofs"]
            )
        )

        self.assertEqual(boundary["commands_executed_in_p9ca"], [])
        self.assertFalse(boundary["ssh_invoked_in_p9ca"])
        self.assertFalse(boundary["remote_network_connection_performed_in_p9ca"])
        self.assertIn("account_state_read", boundary["allowed_future_read_categories"])
        self.assertIn(
            "place_order",
            boundary["forbidden_future_actions_during_proof_collection"],
        )
        self.assertIn(
            "remote_sync_or_deploy_code",
            boundary["forbidden_future_actions_during_proof_collection"],
        )

        deltas = acceptance["delta_acceptance"]
        self.assertEqual(deltas["order_delta_must_equal"], 0)
        self.assertEqual(deltas["cancel_delta_must_equal"], 0)
        self.assertEqual(deltas["fill_delta_must_equal"], 0)
        self.assertEqual(deltas["trade_delta_must_equal"], 0)
        self.assertEqual(deltas["position_delta_must_equal"], 0)
        self.assertTrue(
            acceptance["staleness_policy"][
                "future_fill_or_stale_fill_evidence_must_fail_closed"
            ]
        )

        self.assertTrue(matrix["authorizations"]["define_fresh_remote_proof_collection_scope"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["remote_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9bz_allowed_next_gate_is_not_p9ca(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9CB_skip_scope_collect_remote_proofs"}
        )

        summary, exit_code = build_p9ca_fresh_remote_proof_collection_scope(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 15, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bz_summary_ready_for_p9ca_scope_definition", summary["blockers"])
        self.assertFalse(summary["p9ca_fresh_remote_proof_collection_scope_defined"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9bz_non_authorization_allows_fresh_collection(self) -> None:
        matrix = _p9bz_matrix_payload()
        matrix["authorizations"]["fresh_remote_proof_collection"] = True
        paths = self._write_ready_inputs(matrix_payload=matrix)

        summary, exit_code = build_p9ca_fresh_remote_proof_collection_scope(
            self._args(paths, output_root=self.temp_dir / "bad-matrix"),
            now_fn=lambda: datetime(2026, 6, 10, 15, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bz_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["p9ca_fresh_remote_proof_collection_scope_defined"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9ca_fresh_remote_proof_collection_scope(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_remote_proofs_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 15, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ca_scope_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9ca_fresh_remote_proof_collection_scope_defined"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CA_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bz_summary=str(paths["p9bz_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        matrix_payload: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bz_root = self.temp_dir / "p9bz"
        proof_root = p9bz_root / "proof_artifacts" / "p9bz"
        p9bz_summary = p9bz_root / "summary.json"
        prereq_path = proof_root / "future_gate_prerequisites.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = {
            "contract_version": P9BZ_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bz_review_p9by_live_order_gate_package_ready": True,
            "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition": True,
            "eligible_for_future_p9ca_scope_definition": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "fresh_remote_proof_collection_scope_defined_in_p9bz": False,
            "fresh_proofs_collected_in_p9bz": False,
            "fresh_remote_account_read_performed": False,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "allowed_next_gate": P9CA_GATE,
            "allowed_next_gate_scope": P9CA_SCOPE,
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
                "future_gate_prerequisites": str(prereq_path),
                "non_authorization": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(prereq_path, _p9bz_prereq_payload())
        _write_json(matrix_path, matrix_payload or _p9bz_matrix_payload())
        _write_json(control_path, _p9bz_control_payload())
        _write_json(p9bz_summary, summary)
        return {"project_profile": project_profile, "p9bz_summary": p9bz_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _p9bz_prereq_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_future_gate_prerequisites.v1",
        "allowed_next_gate": P9CA_GATE,
        "allowed_next_gate_scope": P9CA_SCOPE,
        "required_before_any_fresh_remote_proof_collection": [
            "separately requested P9CA scope definition",
            "target runner identity and read-only command boundary",
            "account-read, position, open-order, fill/trade, order-book, and exchange-filter proof collection plan",
            "no-order/no-cancel/no-trade delta acceptance contract",
            "explicit owner approval for proof collection only",
        ],
        "required_before_any_future_live_order_submission": [
            "fresh proofs collected and retained",
            "fresh no-order candidate executor input hash binding",
            "post-only order price proof from fresh order book",
            "kill switch and rollback readback",
            "final owner live-order gate approval",
        ],
    }


def _p9bz_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_non_authorization.v1",
        "authorizations": {
            "review_p9by_live_order_gate_review_package": True,
            "define_fresh_remote_proof_collection_scope": False,
            "fresh_remote_proof_collection": False,
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


def _p9bz_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_control_boundary.v1",
        "scope": "p9by_package_review_only",
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
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
