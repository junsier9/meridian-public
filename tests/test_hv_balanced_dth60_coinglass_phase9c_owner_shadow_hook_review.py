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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9c_owner_shadow_hook_review import (  # noqa: E402
    PENDING_OWNER_DECISION,
    READY_DECISION_STATUS,
    build_p9c_review,
)


class HvBalancedDth60CoinglassPhase9cOwnerShadowHookReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9c-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9c_ready_for_owner_review_without_authorizing_hook_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9c"

        summary, exit_code = build_p9c_review(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["eligible_for_owner_p9c_review"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["timer_hook_deployment_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["candidate_order_authority"], "disabled")
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertEqual(summary["candidate_artifact_sink"], "proof_artifacts_only")
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["fills_observed"], 0)
        self.assertEqual(
            summary["owner_decision_record"]["review_status"],
            READY_DECISION_STATUS,
        )
        self.assertEqual(
            summary["owner_decision_record"]["timer_hook_implementation_decision"],
            PENDING_OWNER_DECISION,
        )
        self.assertTrue(summary["proof_gates"]["phase9r_ready"])
        self.assertTrue(summary["p9c_hard_guards"]["research_to_live_parity_ready"])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "p9c_owner_shadow_hook_review.json").exists())
        self.assertTrue((output_root / "p9c_owner_shadow_hook_review.md").exists())

    def test_phase9c_blocks_when_research_contract_scorer_would_load_into_timer(self) -> None:
        paths = self._write_ready_inputs(
            p9r_overrides={
                "candidate_scorer_loaded_into_timer": True,
                "live_supervisor_timer_loaded_candidate_overlay": True,
            }
        )

        summary, exit_code = build_p9c_review(
            self._args(paths, output_root=self.temp_dir / "phase9c-block-p9r"),
            now_fn=lambda: datetime(2026, 6, 7, 10, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertFalse(summary["eligible_for_owner_p9c_review"])
        self.assertIn("phase9r_ready", summary["blockers"])
        self.assertIn("no_timer_or_executor_load", summary["blockers"])
        self.assertFalse(summary["phase9r_gates"]["scorer_not_loaded_into_timer"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9c_blocks_when_remote_wrapper_points_executor_at_candidate_or_timer_path(self) -> None:
        paths = self._write_ready_inputs(
            p9b_overrides={
                "candidate_plan_referenced_by_executor": True,
                "timer_path_invoked": True,
            }
        )

        summary, exit_code = build_p9c_review(
            self._args(paths, output_root=self.temp_dir / "phase9c-block-p9b"),
            now_fn=lambda: datetime(2026, 6, 7, 10, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase9b_ready", summary["blockers"])
        self.assertIn("no_timer_or_executor_load", summary["blockers"])
        self.assertFalse(summary["phase9b_gates"]["candidate_plan_not_referenced_by_executor"])
        self.assertFalse(summary["phase9b_gates"]["timer_path_invoked_false"])
        self.assertFalse(summary["p9c_hard_guards"]["candidate_plan_not_referenced_by_executor"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            proposal_doc=str(paths["proposal_doc"]),
            phase9a_summary=str(paths["phase9a"]),
            phase9b_summary=str(paths["phase9b"]),
            phase9r_summary=str(paths["phase9r"]),
            owner="rulebook_owner",
            review_request_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9a_overrides: dict | None = None,
        p9b_overrides: dict | None = None,
        p9r_overrides: dict | None = None,
    ) -> dict[str, Path]:
        paths = {
            "project_profile": self.temp_dir / "project_profile.json",
            "proposal_doc": self.temp_dir / "proposal.md",
            "phase9a": self.temp_dir / "phase9a.json",
            "phase9b": self.temp_dir / "phase9b.json",
            "phase9r": self.temp_dir / "phase9r.json",
        }
        self._write_json(
            paths["project_profile"],
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        paths["proposal_doc"].write_text("# P9 proposal\n", encoding="utf-8")

        no_live = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        zero_order = {
            "orders_submitted": 0,
            "fill_count": 0,
            "mainnet_order_submission_authorized": False,
            "exchange_order_submission": "disabled",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
        }
        p9a = {
            **no_live,
            **zero_order,
            "status": "ready",
            "blockers": [],
            "disabled_hook_baseline_output_unchanged": True,
            "enabled_hook_execution_target_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_plan_referenced_by_executor": False,
            "same_timestamp_context_proven": True,
            "same_risk_inputs_proven": True,
            "same_symbol_set_proven": True,
            "same_portfolio_engine_proven": True,
            "fresh_phase2_no_future_stale_zero_fill": True,
            "fresh_phase2b_no_future_stale_zero_fill": True,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
        }
        p9b = {
            **no_live,
            **zero_order,
            "status": "ready",
            "blockers": [],
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_equals_baseline": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_shadow_plan_generated": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "read_only_supervisor_artifacts": True,
            "control_plane": {"unchanged": True},
            "wrapper_output_under_proof_artifacts": True,
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
        }
        p9r = {
            "status": "ready",
            "blockers": [],
            "candidate_scorer_mode": "research_h10d_contract",
            "candidate_scorer_mode_scope": "proof_harness_only",
            "candidate_scorer_loaded_into_live_wrapper": False,
            "candidate_scorer_loaded_into_timer": False,
            "candidate_scorer_loaded_into_executor": False,
            "row_parity": {
                "trigger_mismatch_count": 0,
                "multiplier_mismatch_count": 0,
                "target_contribution_mismatch_count": 0,
                "score_mismatch_count": 0,
            },
            "target_weight_parity": {"mismatch_count": 0},
            "slice_metric_parity": {"mismatch_count": 0},
            "retained_forward_artifact_compare": {"status": "ready"},
            "orders_submitted": 0,
            "fills_observed": 0,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "live_supervisor_timer_loaded_candidate_overlay": False,
        }
        p9a.update(p9a_overrides or {})
        p9b.update(p9b_overrides or {})
        p9r.update(p9r_overrides or {})
        self._write_json(paths["phase9a"], p9a)
        self._write_json(paths["phase9b"], p9b)
        self._write_json(paths["phase9r"], p9r)
        return paths

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
