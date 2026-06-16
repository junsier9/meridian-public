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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import (  # noqa: E402
    PENDING_DECISION_STATUS,
    TARGET_CONTRIBUTION,
    build_owner_review_pack,
)


class HvBalancedDth60CoinglassPhase6OwnerReviewPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase6-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_build_pack_ready_for_owner_review_without_live_approval(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase6"

        summary, exit_code = build_owner_review_pack(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 6, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["eligible_for_owner_promotion_review"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["owner_decision_record"]["decision_status"], PENDING_DECISION_STATUS)
        self.assertEqual(summary["project_stage"]["current_stage"], "stage_1_research_readiness_only")
        self.assertEqual(summary["target_contribution_boundary"], TARGET_CONTRIBUTION)
        self.assertTrue(summary["proof_gates"]["p5b_zero_orders_fills_each_cycle"])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_review_pack.json").exists())
        self.assertTrue((output_root / "owner_review_pack.md").exists())

    def test_build_pack_blocks_when_p5b_zero_order_gate_fails(self) -> None:
        paths = self._write_ready_inputs(p5b_zero_count=2)
        output_root = self.temp_dir / "phase6-blocked"

        summary, exit_code = build_owner_review_pack(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 6, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertFalse(summary["eligible_for_owner_promotion_review"])
        self.assertIn("p5b_zero_orders_fills_each_cycle", summary["blockers"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            step1_summary=str(paths["step1"]),
            phase2_summary=str(paths["phase2"]),
            phase2b_summary=str(paths["phase2b"]),
            phase3_summary=str(paths["phase3"]),
            phase4_summary=str(paths["phase4"]),
            p5a_phase3_summary=str(paths["p5a_phase3"]),
            p5a_phase4_summary=str(paths["p5a_phase4"]),
            p5b_summary=str(paths["p5b"]),
        )

    def _write_ready_inputs(self, *, p5b_zero_count: int = 3) -> dict[str, Path]:
        paths = {
            "project_profile": self.temp_dir / "project_profile.json",
            "step1": self.temp_dir / "step1.json",
            "phase2": self.temp_dir / "phase2.json",
            "phase2b": self.temp_dir / "phase2b.json",
            "phase3": self.temp_dir / "phase3.json",
            "phase4": self.temp_dir / "phase4.json",
            "p5a_phase3": self.temp_dir / "p5a_phase3.json",
            "p5a_phase4": self.temp_dir / "p5a_phase4.json",
            "p5b": self.temp_dir / "p5b.json",
        }
        self._write_json(
            paths["project_profile"],
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        no_mutation = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "exchange_order_submission": "disabled",
        }
        self._write_json(
            paths["step1"],
            {
                **no_mutation,
                "status": "ready",
                "api_key_present": True,
                "ready_symbol_count": 20,
                "requested_symbol_count": 20,
                "generated_at_utc": "2026-06-06T13:13:28Z",
                "required_endpoint_id": "futures_top_long_short_position_ratio",
            },
        )
        self._write_json(
            paths["phase2"],
            {
                **no_mutation,
                "status": "ready",
                "joined_symbol_count": 20,
                "requested_symbol_count": 20,
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
                "decision_time_utc": "2026-06-06T13:19:51Z",
                "freshness_seconds": 129600,
            },
        )
        self._write_json(
            paths["phase2b"],
            {
                **no_mutation,
                "status": "ready",
                "joined_symbol_count": 20,
                "requested_symbol_count": 20,
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
                "train_includes_decision_row": False,
                "decision_time_utc": "2026-06-06T14:23:50Z",
                "selected_provider_timestamp_utc": "2026-06-06T00:00:00Z",
                "shock_branch_triggered": True,
            },
        )
        self._write_json(
            paths["phase3"],
            {
                **no_mutation,
                "status": "ready",
                "run_id": "phase3",
                "generated_at_utc": "2026-06-06T14:40:05Z",
                "combined_candidate_trigger_proven": True,
                "disabled_wrapper_score_matches_core": True,
                "changed_contribution_columns": [TARGET_CONTRIBUTION],
                "non_target_contribution_max_abs_diff_enabled_vs_disabled": 0.0,
                "overlay_triggered_row_count": 20,
            },
        )
        phase4 = {
            **no_mutation,
            "status": "ready",
            "run_id": "phase4",
            "generated_at_utc": "2026-06-06T14:42:34Z",
            "same_timestamp_context_proven": True,
            "same_risk_inputs_proven": True,
            "deterministic_target_difference_proven": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "mainnet_order_submission_authorized": False,
            "target_weight_delta_symbol_count": 12,
            "absolute_target_weight_delta_sum": 0.2,
        }
        self._write_json(paths["phase4"], phase4)
        self._write_json(paths["p5a_phase3"], {**phase4, "run_id": "p5a-phase3", "combined_candidate_trigger_proven": True})
        self._write_json(
            paths["p5a_phase4"],
            {**phase4, "run_id": "p5a-phase4", "combined_candidate_trigger_proven": True},
        )
        self._write_json(
            paths["p5b"],
            {
                "status": "ready",
                "remote_clean_root": "/remote/p5b",
                "generated_at_utc": "2026-06-06T15:13:57Z",
                "cycle_count_observed": 3,
                "ready_cycle_count": 3,
                "fresh_proof_cycle_count": 3,
                "same_risk_paired_plan_cycle_count": 3,
                "zero_orders_fills_cycle_count": p5b_zero_count,
                "target_contribution_boundary_cycle_count": 3,
                "control_plane_snapshot": {
                    "db_window_counts": {
                        "counts": {
                            "execution_plans": 0,
                            "paper_orders": 0,
                            "paper_fills": 0,
                        }
                    }
                },
                "cycles": [
                    {"no_live_mutation_flags_proven": True},
                    {"no_live_mutation_flags_proven": True},
                    {"no_live_mutation_flags_proven": True},
                ],
            },
        )
        return paths

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
