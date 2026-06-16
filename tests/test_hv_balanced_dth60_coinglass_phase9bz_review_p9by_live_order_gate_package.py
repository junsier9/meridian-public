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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9by_live_order_gate_review_package import (  # noqa: E402
    CONTRACT_VERSION as P9BY_CONTRACT,
    P9BZ_GATE,
    P9BZ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bz_review_p9by_live_order_gate_package import (  # noqa: E402
    APPROVE_P9BZ_DECISION,
    P9CA_GATE,
    build_p9bz_review_p9by_live_order_gate_package,
)


class Phase9BZReviewP9BYLiveOrderGatePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bz-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9by_package_only_without_collecting_proofs_or_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bz_review_p9by_live_order_gate_package(
            self._args(paths, output_root=self.temp_dir / "p9bz"),
            now_fn=lambda: datetime(2026, 6, 10, 14, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bz_review_p9by_live_order_gate_package_ready"])
        self.assertTrue(
            summary[
                "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition"
            ]
        )
        self.assertTrue(summary["eligible_for_future_p9ca_scope_definition"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["fresh_remote_proof_collection_scope_defined_in_p9bz"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9bz"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9CA_GATE)
        self.assertEqual(summary["required_fresh_proof_count"], 12)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        review = _load_json(Path(outputs["sufficiency_review"]))
        prereq = _load_json(Path(outputs["future_gate_prerequisites"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertTrue(
            review[
                "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition"
            ]
        )
        self.assertFalse(review["fresh_remote_proof_collection_scope_defined_in_p9bz"])
        self.assertFalse(review["fresh_remote_proof_collection_performed"])
        self.assertEqual(prereq["allowed_next_gate"], P9CA_GATE)
        self.assertTrue(matrix["authorizations"]["review_p9by_live_order_gate_review_package"])
        self.assertFalse(matrix["authorizations"]["define_fresh_remote_proof_collection_scope"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9by_allowed_next_gate_is_not_p9bz(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9CA_skip_review_collect_remote_proofs"}
        )

        summary, exit_code = build_p9bz_review_p9by_live_order_gate_package(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 14, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9by_summary_ready_for_package_review", summary["blockers"])
        self.assertFalse(summary["p9bz_review_p9by_live_order_gate_package_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9by_package_claims_fresh_proofs_were_collected(self) -> None:
        package = _review_package_payload()
        package["fresh_proofs_collected_in_p9by"] = True
        package["fresh_proof_collection_plan"]["fresh_proofs_collected_in_p9by"] = True
        paths = self._write_ready_inputs(package_payload=package)

        summary, exit_code = build_p9bz_review_p9by_live_order_gate_package(
            self._args(paths, output_root=self.temp_dir / "bad-package"),
            now_fn=lambda: datetime(2026, 6, 10, 14, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("review_package_ready", summary["blockers"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9bz"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bz_review_p9by_live_order_gate_package(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_remote_proofs_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bz_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9bz_review_p9by_live_order_gate_package_ready"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BZ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9by_summary=str(paths["p9by_summary"]),
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
        p9by_root = self.temp_dir / "p9by"
        proof_root = p9by_root / "proof_artifacts" / "p9by"
        p9by_summary = p9by_root / "summary.json"
        package_path = proof_root / "live_order_gate_review_package.json"
        canary_path = proof_root / "canary_order_terms.json"
        fresh_plan_path = proof_root / "fresh_proof_collection_plan.json"
        approval_path = proof_root / "approval_checklist.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        package = package_payload or _review_package_payload()
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = {
            "contract_version": P9BY_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9by_live_order_gate_review_package_prepared": True,
            "p9bx_sufficient_for_review_package": True,
            "eligible_for_future_p9bz_package_review": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "fresh_proofs_collected_in_p9by": False,
            "fresh_remote_account_read_performed": False,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "allowed_next_gate": P9BZ_GATE,
            "allowed_next_gate_scope": P9BZ_SCOPE,
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
            "fill_count": 0,
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "output_files": {
                "live_order_gate_review_package": str(package_path),
                "canary_order_terms": str(canary_path),
                "fresh_proof_collection_plan": str(fresh_plan_path),
                "approval_checklist": str(approval_path),
                "non_authorization": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(package_path, package)
        _write_json(canary_path, _canary_payload())
        _write_json(fresh_plan_path, _fresh_plan_payload())
        _write_json(approval_path, _approval_payload())
        _write_json(matrix_path, _p9by_matrix_payload())
        _write_json(control_path, _p9by_control_payload())
        _write_json(p9by_summary, summary)
        return {"project_profile": project_profile, "p9by_summary": p9by_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _canary_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_canary_order_terms.v1",
        "package_only": True,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "risk_ceiling_usdt": 25.0,
        "max_notional_usdt": 10.0,
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "would_submit_order": False,
    }


def _fresh_plan_payload() -> dict[str, object]:
    proof_rows = [
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
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_fresh_proof_collection_plan.v1",
        "package_only": True,
        "fresh_proofs_collected_in_p9by": False,
        "remote_account_read_performed": False,
        "order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "proofs": [
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": max_age,
                "collection_status_in_p9by": "not_collected",
                "required_before": "future_live_order_gate_approval",
                "purpose": f"unit test {proof_id}",
            }
            for proof_id, max_age in proof_rows
        ],
    }


def _approval_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_approval_checklist.v1",
        "package_only": True,
        "approval_items": [
            {"item": "all_required_fresh_proofs_present_and_unexpired", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
            {"item": "candidate_target_plan_hash_bound_to_executor_input", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
            {"item": "baseline_candidate_diff_dth60_only", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
            {"item": "post_only_limit_price_does_not_cross_spread", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
            {"item": "kill_switch_and_rollback_readback_available", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
            {"item": "final_owner_live_order_gate_approval", "required_for_live_order_gate": True, "satisfied_in_p9by": False},
        ],
        "rollback_conditions": [
            "any required fresh proof is missing, stale, or hash-mismatched",
            "candidate target-plan hash differs from no-order approved hash",
            "executor input is not explicitly bound to the candidate target-plan hash in the final gate",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "open-order, fill, trade, or position delta is unexplained",
            "order book no longer supports maker-only post-only execution",
            "supervisor, timer, operator, exchange, or provider health readback reports an exception",
            "kill switch readback is unavailable",
        ],
    }


def _review_package_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_review_package.v1",
        "run_id": "unit",
        "package_only": True,
        "future_gate_name": "candidate_live_order_gate",
        "package_decision": "prepared_for_future_review_only",
        "canary_order_terms": _canary_payload(),
        "fresh_proof_collection_plan": _fresh_plan_payload(),
        "approval_checklist": _approval_payload(),
        "future_gate_may_discuss": [
            "single canary order submission under exact P9BU terms",
            "candidate target-plan replacement semantics if fresh no-order binding still passes",
            "post-order observation and rollback obligations",
        ],
        "future_gate_may_not_skip": [
            "fresh remote account read",
            "pre/post position fingerprint",
            "pre/post open-order fingerprint",
            "pre/post fill and trade fingerprint",
            "fresh order book",
            "exchange filters and post-only support",
            "final owner live-order gate approval",
        ],
        "baseline_target_plan_sha256": BASELINE_SHA,
        "candidate_target_plan_sha256": CANDIDATE_SHA,
        "only_distance_to_high_60_contribution_changed": True,
        "fresh_proofs_collected_in_p9by": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def _p9by_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_non_authorization.v1",
        "authorizations": {
            "prepare_live_order_gate_review_package": True,
            "review_live_order_gate_review_package": True,
            "fresh_remote_proof_collection": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }


def _p9by_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_control_boundary.v1",
        "scope": "live_order_gate_review_package_preparation_only",
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
        "orders_submitted": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
