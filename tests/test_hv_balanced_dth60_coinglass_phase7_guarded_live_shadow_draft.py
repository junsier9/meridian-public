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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase7_guarded_live_shadow_draft import (  # noqa: E402
    APPROVE_P7_DECISION,
    build_phase7_draft,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import TARGET_CONTRIBUTION  # noqa: E402


class HvBalancedDth60CoinglassPhase7GuardedLiveShadowDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase7-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_build_phase7_draft_ready_without_order_authority(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p7"

        summary, exit_code = build_phase7_draft(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 6, 16, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["eligible_for_p7_guarded_live_shadow_draft"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertEqual(summary["exchange_order_submission"], "disabled")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P7_DECISION)
        self.assertFalse(summary["owner_decision"]["live_order_submission_approved"])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((output_root / "guarded_live_shadow_integration_draft.json").exists())

    def test_build_phase7_draft_blocks_without_owner_approval(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p7-blocked"
        args = self._args(paths, output_root=output_root)
        args.owner_decision = "defer_for_more_no_order_observation"

        summary, exit_code = build_phase7_draft(
            args,
            now_fn=lambda: datetime(2026, 6, 6, 16, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_approved_p7_guarded_shadow_only", summary["blockers"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            owner_review_pack=str(paths["owner_review_pack"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P7_DECISION,
            owner_decision_source="test:approved_p7",
            phase2_summary=str(paths["phase2"]),
            phase2b_summary=str(paths["phase2b"]),
            phase3_summary=str(paths["phase3"]),
            phase4_summary=str(paths["phase4"]),
            live_config_path=str(paths["live_config"]),
            max_rebuild_age_seconds=3600,
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        paths = {
            "owner_review_pack": self.temp_dir / "owner_review_pack.json",
            "phase2": self.temp_dir / "phase2.json",
            "phase2b": self.temp_dir / "phase2b.json",
            "phase3": self.temp_dir / "phase3.json",
            "phase4": self.temp_dir / "phase4.json",
            "live_config": self.temp_dir / "live_config.yaml",
        }
        paths["live_config"].write_text("mode: plan_only\n", encoding="utf-8")
        self._write_json(
            paths["owner_review_pack"],
            {"status": "ready", "eligible_for_owner_promotion_review": True},
        )
        no_mutation = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "exchange_order_submission": "disabled",
        }
        self._write_json(
            paths["phase2"],
            {
                **no_mutation,
                "status": "ready",
                "generated_at_utc": "2026-06-06T16:00:00Z",
                "decision_time_utc": "2026-06-06T16:00:00Z",
                "freshness_seconds": 129600,
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
            },
        )
        self._write_json(
            paths["phase2b"],
            {
                **no_mutation,
                "status": "ready",
                "generated_at_utc": "2026-06-06T16:01:00Z",
                "decision_time_utc": "2026-06-06T16:01:00Z",
                "selected_provider_timestamp_utc": "2026-06-06T00:00:00Z",
                "freshness_seconds": 129600,
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
            },
        )
        self._write_json(
            paths["phase3"],
            {
                **no_mutation,
                "status": "ready",
                "combined_candidate_trigger_proven": True,
                "disabled_wrapper_score_matches_core": True,
                "changed_contribution_columns": [TARGET_CONTRIBUTION],
                "changed_non_target_contribution_columns": [],
                "non_target_contribution_max_abs_diff_enabled_vs_disabled": 0.0,
            },
        )
        self._write_json(
            paths["phase4"],
            {
                **no_mutation,
                "status": "ready",
                "run_id": "phase4-ready",
                "generated_at_utc": "2026-06-06T16:05:00Z",
                "same_timestamp_context_proven": True,
                "same_risk_inputs_proven": True,
                "same_symbol_set_proven": True,
                "same_portfolio_engine_proven": True,
                "baseline_plan_only_risk_gate_status": "passed",
                "candidate_plan_only_risk_gate_status": "passed",
                "deterministic_target_difference_proven": True,
                "orders_submitted": 0,
                "fill_count": 0,
                "mainnet_order_submission_authorized": False,
                "target_weight_delta_symbol_count": 12,
                "absolute_target_weight_delta_sum": 0.2,
            },
        )
        return paths

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
