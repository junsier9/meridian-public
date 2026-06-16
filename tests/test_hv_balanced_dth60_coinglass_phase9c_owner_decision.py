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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9c_owner_decision import (  # noqa: E402
    APPROVE_P9C_IMPLEMENTATION_DECISION,
    build_owner_decision,
)


class HvBalancedDth60CoinglassPhase9cOwnerDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9c-decision-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_records_approval_for_default_off_observe_only_implementation_only(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "decision"

        record, exit_code = build_owner_decision(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 11, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "approved")
        self.assertEqual(record["decision"], APPROVE_P9C_IMPLEMENTATION_DECISION)
        self.assertEqual(
            record["decision_effect"],
            "authorize_default_off_observe_only_hook_implementation_only",
        )
        self.assertTrue(record["authorized_scope"]["observe_only_hook_implementation"])
        self.assertTrue(record["authorized_scope"]["default_off_required"])
        self.assertTrue(record["authorized_scope"]["proof_artifacts_only_required"])
        self.assertTrue(record["authorized_scope"]["executor_input_must_remain_baseline_only"])
        self.assertTrue(record["not_authorized"]["hook_deployment"])
        self.assertTrue(record["not_authorized"]["timer_path_load"])
        self.assertTrue(record["not_authorized"]["live_order_submission"])
        self.assertTrue(record["not_authorized"]["target_plan_replacement"])
        self.assertTrue(record["scorer_reproduction_assessment"]["research_baseline_reproduced_in_p9r_harness"])
        self.assertFalse(record["scorer_reproduction_assessment"]["candidate_scorer_loaded_into_timer"])
        self.assertFalse(record["scorer_reproduction_assessment"]["candidate_scorer_loaded_into_executor"])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((output_root / "owner_decision_report.md").exists())

    def test_blocks_when_p9c_review_is_not_ready(self) -> None:
        paths = self._write_ready_inputs(
            p9c_overrides={
                "status": "blocked",
                "blockers": ["phase9r_ready"],
                "eligible_for_owner_p9c_review": False,
            }
        )

        record, exit_code = build_owner_decision(
            self._args(paths, output_root=self.temp_dir / "decision-block-p9c"),
            now_fn=lambda: datetime(2026, 6, 7, 11, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(record["status"], "blocked")
        self.assertIn("phase9c_ready", record["blockers"])
        self.assertIn("phase9c_owner_review_eligible", record["blockers"])
        self.assertFalse(record["authorized_scope"]["observe_only_hook_implementation"])
        self.assertTrue(record["not_authorized"]["live_order_submission"])

    def test_blocks_when_p9r_scorer_would_load_into_execution_or_drift(self) -> None:
        paths = self._write_ready_inputs(
            p9r_overrides={
                "candidate_scorer_loaded_into_timer": True,
                "row_parity": {
                    "trigger_mismatch_count": 1,
                    "multiplier_mismatch_count": 0,
                    "target_contribution_mismatch_count": 0,
                    "score_mismatch_count": 0,
                },
            }
        )

        record, exit_code = build_owner_decision(
            self._args(paths, output_root=self.temp_dir / "decision-block-p9r"),
            now_fn=lambda: datetime(2026, 6, 7, 11, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(record["status"], "blocked")
        self.assertIn("phase9r_research_parity_ready", record["blockers"])
        self.assertFalse(record["scorer_reproduction_assessment"]["research_baseline_reproduced_in_p9r_harness"])
        self.assertTrue(record["scorer_reproduction_assessment"]["candidate_scorer_loaded_into_timer"])
        self.assertFalse(record["authorized_scope"]["observe_only_hook_implementation"])
        self.assertTrue(record["not_authorized"]["timer_path_load"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            phase9c_summary=str(paths["phase9c"]),
            phase9r_summary=str(paths["phase9r"]),
            owner="rulebook_owner",
            decision=APPROVE_P9C_IMPLEMENTATION_DECISION,
            decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9c_overrides: dict | None = None,
        p9r_overrides: dict | None = None,
    ) -> dict[str, Path]:
        paths = {
            "phase9c": self.temp_dir / "phase9c.json",
            "phase9r": self.temp_dir / "phase9r.json",
        }
        p9c_hard_guards = {
            "candidate_artifact_sink_proof_only": True,
            "candidate_live_order_submission_authorized_false": True,
            "candidate_order_authority_disabled": True,
            "candidate_overlay_execution_path_excluded": True,
            "candidate_plan_not_referenced_by_executor": True,
            "execution_target_source_baseline_only": True,
            "executor_consumes_baseline_only": True,
            "fresh_phase2_no_future_stale_zero_fill": True,
            "fresh_phase2b_no_future_stale_zero_fill": True,
            "no_live_mutation_all_inputs": True,
            "no_timer_or_executor_load": True,
            "research_to_live_parity_ready": True,
            "same_portfolio_engine": True,
            "same_risk_inputs": True,
            "same_symbol_set": True,
            "same_timestamp_context": True,
            "zero_orders_fills_all_inputs": True,
        }
        p9c = {
            "status": "ready",
            "blockers": [],
            "eligible_for_owner_p9c_review": True,
            "allowed_owner_decisions": [APPROVE_P9C_IMPLEMENTATION_DECISION],
            "p9c_hard_guards": p9c_hard_guards,
            "proof_gates": {
                "phase9a_ready": True,
                "phase9b_ready": True,
                "phase9r_ready": True,
                "project_stage_boundary_preserved": True,
                "proposal_doc_exists": True,
                "no_timer_or_executor_load": True,
                "zero_orders_fills_all_inputs": True,
            },
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
        p9c.update(p9c_overrides or {})
        p9r.update(p9r_overrides or {})
        self._write_json(paths["phase9c"], p9c)
        self._write_json(paths["phase9r"], p9r)
        return paths

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
