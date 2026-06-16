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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    CONTRACT_VERSION as P9BV_CONTRACT,
    P9BW_GATE,
    P9BW_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bw_review_after_p9bv import (  # noqa: E402
    APPROVE_P9BW_DECISION,
    P9BX_GATE,
    build_p9bw_review_after_p9bv,
)


class Phase9BWReviewAfterP9BVTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bw-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_review_allows_live_order_gate_discussion_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bw_review_after_p9bv(
            self._args(paths, output_root=self.temp_dir / "p9bw"),
            now_fn=lambda: datetime(2026, 6, 10, 11, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bw_review_after_p9bv_ready"])
        self.assertTrue(summary["p9bv_retained_evidence_sufficient_for_live_order_gate_discussion"])
        self.assertTrue(summary["eligible_for_future_live_order_gate_discussion"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertEqual(summary["allowed_next_gate"], P9BX_GATE)
        self.assertTrue(summary["simulated_executor_input_replacement_matches_candidate"])
        self.assertFalse(summary["actual_executor_input_changed"])
        self.assertFalse(summary["actual_target_plan_replaced"])
        self.assertTrue(summary["only_distance_to_high_60_contribution_changed"])
        self.assertEqual(summary["changed_symbol_count"], 1)
        self.assertEqual(summary["order_intent_preview_count"], 1)
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        checklist = _load_json(Path(outputs["sufficiency_checklist"]))
        matrix = _load_json(Path(outputs["non_authorization_matrix"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertTrue(
            checklist["p9bv_retained_evidence_sufficient_for_live_order_gate_discussion"]
        )
        self.assertTrue(matrix["authorizations"]["enter_live_order_gate_discussion"])
        self.assertFalse(matrix["authorizations"]["live_order_gate_approval"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9bv_summary_not_ready(self) -> None:
        paths = self._write_ready_inputs(summary_overrides={"status": "blocked"})

        summary, exit_code = build_p9bw_review_after_p9bv(
            self._args(paths, output_root=self.temp_dir / "blocked-p9bv"),
            now_fn=lambda: datetime(2026, 6, 10, 11, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bv_summary_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_replacement_dry_run_no_longer_matches_candidate(self) -> None:
        paths = self._write_ready_inputs(
            replacement_overrides={
                "simulated_executor_input_plan_sha256_after_dry_run": BASELINE_SHA,
                "simulated_executor_input_replacement_matches_candidate": False,
            }
        )

        summary, exit_code = build_p9bw_review_after_p9bv(
            self._args(paths, output_root=self.temp_dir / "bad-replacement"),
            now_fn=lambda: datetime(2026, 6, 10, 11, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("replacement_dry_run_ready", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_authorizing_live_order(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bw_review_after_p9bv(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 11, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bw_review_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BW_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bv_summary=str(paths["p9bv_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        replacement_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bv_root = self.temp_dir / "p9bv"
        proof_root = p9bv_root / "proof_artifacts" / "p9bv"
        p9bv_summary = p9bv_root / "summary.json"
        replacement_path = proof_root / "replacement_dry_run.json"
        diff_path = proof_root / "plan_diff.json"
        preview_path = proof_root / "order_preview.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        replacement = _replacement_payload()
        replacement.update(replacement_overrides or {})
        summary = {
            "contract_version": P9BV_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bv_no_order_replacement_dry_run_ready": True,
            "candidate_target_plan_replacement_semantics_proven": True,
            "exact_p9bu_terms_applied": True,
            "same_timestamp_context": True,
            "same_risk_inputs": True,
            "candidate_plan_differs_from_baseline": True,
            "simulated_executor_input_replacement_matches_candidate": True,
            "actual_executor_input_changed": False,
            "actual_target_plan_replaced": False,
            "only_distance_to_high_60_contribution_changed": True,
            "changed_symbol_count": 1,
            "order_intent_preview_count": 1,
            "risk_ceiling_usdt": 25.0,
            "max_notional_usdt": 10.0,
            "order_type": "post_only_limit",
            "time_in_force": "GTX",
            "candidate_enter_executor_target_plan_path_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "allowed_next_gate": P9BW_GATE,
            "allowed_next_gate_scope": P9BW_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "output_files": {
                "replacement_dry_run": str(replacement_path),
                "target_plan_diff": str(diff_path),
                "order_intent_preview": str(preview_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(replacement_path, replacement)
        _write_json(diff_path, _diff_payload())
        _write_json(preview_path, _preview_payload())
        _write_json(matrix_path, _matrix_payload())
        _write_json(control_path, _control_payload())
        _write_json(p9bv_summary, summary)
        return {"project_profile": project_profile, "p9bv_summary": p9bv_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _replacement_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_replacement_dry_run.v1",
        "dry_run_mode": "shadow_executor_reference_only",
        "baseline_generated_first": True,
        "candidate_generated_after_baseline": True,
        "same_timestamp_context": True,
        "same_risk_inputs": True,
        "baseline_target_plan_sha256": BASELINE_SHA,
        "candidate_target_plan_sha256": CANDIDATE_SHA,
        "candidate_plan_differs_from_baseline": True,
        "simulated_executor_input_plan_sha256_before_dry_run": BASELINE_SHA,
        "simulated_executor_input_plan_sha256_after_dry_run": CANDIDATE_SHA,
        "simulated_executor_input_replacement_matches_candidate": True,
        "actual_executor_input_plan_sha256_before_dry_run": BASELINE_SHA,
        "actual_executor_input_plan_sha256_after_dry_run": BASELINE_SHA,
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "candidate_replacement_semantics_proven_in_shadow": True,
        "candidate_artifacts_under_proof_artifacts_only": True,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def _diff_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_target_plan_diff.v1",
        "changed_symbols": ["BTCUSDT"],
        "changed_symbol_count": 1,
        "distance_to_high_60_contribution_delta_abs_sum": 1.0,
        "non_target_contribution_delta_abs_sum": 0.0,
        "only_distance_to_high_60_contribution_changed": True,
    }


def _preview_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_order_intent_preview.v1",
        "preview_only": True,
        "order_intent_count": 1,
        "orders": [
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "notional_usdt": 10.0,
                "order_type": "post_only_limit",
                "time_in_force": "GTX",
                "preview_only": True,
                "would_submit_order": False,
            }
        ],
        "within_max_orders_per_cycle": True,
        "within_max_symbols_per_cycle": True,
        "within_max_notional": True,
        "market_orders_forbidden": True,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def _matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_non_authorization_matrix.v1",
        "authorizations": {
            "no_order_shadow_replacement_dry_run": True,
            "candidate_replacement_semantics_shadow_proof": True,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }


def _control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_control_boundary_readback.v1",
        "scope": "no_order_shadow_executor_replacement_dry_run_only",
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
