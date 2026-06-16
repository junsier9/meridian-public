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

from enhengclaw.live_trading.dth60_observe_only_shadow_hook import (  # noqa: E402
    ObserveOnlyShadowHookConfig,
    file_sha256,
    run_observe_only_shadow_hook,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9d_default_off_observe_only_hook import (  # noqa: E402
    APPROVE_P9C_IMPLEMENTATION_DECISION,
    build_phase9d,
)


class HvBalancedDth60CoinglassPhase9dDefaultOffObserveOnlyHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9d-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_hook_disabled_preserves_baseline_and_writes_no_candidate_artifacts(self) -> None:
        paths = self._write_plan_files()

        summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(enabled=False),
            baseline_target_plan_path=paths["baseline"],
            executor_input_plan_path=paths["executor"],
            candidate_shadow_plan_path=paths["candidate"],
            run_id="disabled",
            now=datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["status"], "ready")
        self.assertFalse(summary["hook_enabled"])
        self.assertTrue(summary["baseline_target_plan_byte_for_byte_unchanged"])
        self.assertTrue(summary["executor_input_plan_hash_equals_baseline"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertEqual(summary["candidate_artifacts_written_count"], 0)
        self.assertEqual(summary["candidate_artifact_paths"], [])
        self.assertFalse(summary["candidate_live_order_submission_authorized"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["deployed_hook"])

    def test_hook_enabled_writes_only_proof_artifacts_and_keeps_executor_baseline(self) -> None:
        paths = self._write_plan_files()
        proof_root = self.temp_dir / "proof_artifacts" / "p9d" / "enabled"

        summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(enabled=True, output_root=proof_root),
            baseline_target_plan_path=paths["baseline"],
            executor_input_plan_path=paths["executor"],
            candidate_shadow_plan_path=paths["candidate"],
            run_id="enabled",
            now=datetime(2026, 6, 7, 12, 5, tzinfo=UTC),
        )

        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["hook_enabled"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertGreater(summary["candidate_artifacts_written_count"], 0)
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertEqual(summary["executor_input_plan_sha256_after_hook"], file_sha256(paths["baseline"]))
        self.assertNotEqual(summary["candidate_shadow_plan_sha256"], summary["executor_input_plan_sha256_after_hook"])
        self.assertTrue(all("proof_artifacts" in Path(path).parts for path in summary["candidate_artifact_paths"]))
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_hook_enabled_blocks_when_output_root_is_not_proof_artifacts(self) -> None:
        paths = self._write_plan_files()

        summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(enabled=True, output_root=self.temp_dir / "not_proof"),
            baseline_target_plan_path=paths["baseline"],
            executor_input_plan_path=paths["executor"],
            candidate_shadow_plan_path=paths["candidate"],
            run_id="blocked",
            now=datetime(2026, 6, 7, 12, 10, tzinfo=UTC),
        )

        self.assertEqual(summary["status"], "blocked")
        self.assertIn("enabled_hook_output_root_not_under_proof_artifacts", summary["blockers"])
        self.assertFalse(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertEqual(summary["candidate_artifacts_written_count"], 0)

    def test_phase9d_runner_builds_ready_default_off_implementation_proof(self) -> None:
        paths = self._write_phase9d_inputs()
        output_root = self.temp_dir / "phase9d"

        summary, exit_code = build_phase9d(
            Namespace(
                output_root=str(output_root),
                phase9c_owner_decision_summary=str(paths["owner_decision"]),
                phase4_summary=str(paths["phase4_summary"]),
            ),
            now_fn=lambda: datetime(2026, 6, 7, 12, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9c_owner_decision_approved"])
        self.assertFalse(summary["default_off_hook_enabled"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertTrue(summary["disabled_hook_baseline_output_unchanged"])
        self.assertEqual(summary["disabled_hook_candidate_artifacts_written_count"], 0)
        self.assertTrue(summary["enabled_fixture_execution_target_unchanged"])
        self.assertTrue(summary["enabled_fixture_candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertTrue((output_root / "default_off_hook_contract.json").exists())
        self.assertTrue((output_root / "disabled_hook_summary.json").exists())
        self.assertTrue((output_root / "enabled_hook_summary.json").exists())
        self.assertTrue((output_root / "summary.json").exists())

    def _write_plan_files(self) -> dict[str, Path]:
        baseline = self.temp_dir / "baseline_target_plan.json"
        executor = self.temp_dir / "executor" / "target_plan.json"
        candidate = self.temp_dir / "candidate_target_plan.json"
        baseline_payload = {"positions": [{"symbol": "BTCUSDT", "target_weight": 0.1}], "version": "baseline"}
        candidate_payload = {"positions": [{"symbol": "ETHUSDT", "target_weight": 0.1}], "version": "candidate"}
        self._write_json(baseline, baseline_payload)
        self._write_json(executor, baseline_payload)
        self._write_json(candidate, candidate_payload)
        return {"baseline": baseline, "executor": executor, "candidate": candidate}

    def _write_phase9d_inputs(self) -> dict[str, Path]:
        plan_paths = self._write_plan_files()
        phase4_root = self.temp_dir / "phase4"
        phase4_root.mkdir()
        baseline = phase4_root / "baseline_target_portfolio.json"
        candidate = phase4_root / "candidate_target_portfolio.json"
        target_diff = phase4_root / "target_plan_diff.csv"
        shared_context = phase4_root / "shared_input_context.json"
        shutil.copyfile(plan_paths["baseline"], baseline)
        shutil.copyfile(plan_paths["candidate"], candidate)
        target_diff.write_text("symbol,baseline,candidate\nBTCUSDT,0.1,0\n", encoding="utf-8")
        self._write_json(shared_context, {"as_of": "2026-06-07T00:00:00Z"})
        phase4_summary = phase4_root / "summary.json"
        self._write_json(
            phase4_summary,
            {
                "status": "ready",
                "blockers": [],
                "run_id": "phase4",
                "generated_at_utc": "2026-06-07T00:00:00Z",
                "same_timestamp_context_proven": True,
                "same_risk_inputs_proven": True,
                "same_symbol_set_proven": True,
                "same_portfolio_engine_proven": True,
                "phase2_pit_proof_checks": {
                    "no_future_fill_proven": True,
                    "no_stale_fill_proven": True,
                    "no_zero_fill_proven": True,
                },
                "phase2b_pit_proof_checks": {
                    "no_future_fill_proven": True,
                    "no_stale_fill_proven": True,
                    "no_zero_fill_proven": True,
                },
                "phase3_parity_proof_checks": {
                    "overlay_enabled_only_target_contribution_changed": True,
                },
                "orders_submitted": 0,
                "fill_count": 0,
                "mainnet_order_submission_authorized": False,
                "applied_to_live": False,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "output_files": {
                    "baseline_target_portfolio": str(baseline),
                    "candidate_target_portfolio": str(candidate),
                    "target_plan_diff": str(target_diff),
                    "shared_input_context": str(shared_context),
                },
            },
        )
        owner_decision = self.temp_dir / "owner_decision.json"
        self._write_json(
            owner_decision,
            {
                "status": "approved",
                "blockers": [],
                "decision": APPROVE_P9C_IMPLEMENTATION_DECISION,
                "decision_effect": "authorize_default_off_observe_only_hook_implementation_only",
                "authorized_scope": {
                    "observe_only_hook_implementation": True,
                    "default_off_required": True,
                    "proof_artifacts_only_required": True,
                    "executor_input_must_remain_baseline_only": True,
                    "candidate_order_authority": "disabled",
                },
                "not_authorized": {
                    "hook_deployment": True,
                    "timer_path_load": True,
                    "live_order_submission": True,
                    "target_plan_replacement": True,
                    "executor_input_mutation": True,
                },
                "scorer_reproduction_assessment": {
                    "research_baseline_reproduced_in_p9r_harness": True,
                    "candidate_scorer_loaded_into_timer": False,
                    "candidate_scorer_loaded_into_executor": False,
                },
            },
        )
        return {"owner_decision": owner_decision, "phase4_summary": phase4_summary}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
