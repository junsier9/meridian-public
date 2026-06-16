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

from scripts.live_trading.run_hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms import (  # noqa: E402
    APPROVE_P10H_DECISION,
    P10I_GATE,
    run_p10h_owner_gate_single_cycle_live_delta_canary_terms,
    stable_payload_sha256,
)


class HvBalanced12FactorP10hOwnerGateCanaryTermsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10h-canary-terms-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_records_exact_single_cycle_live_delta_canary_terms_without_execution(self) -> None:
        paths = self._write_ready_p10g_bundle()

        summary, exit_code = run_p10h_owner_gate_single_cycle_live_delta_canary_terms(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10h"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p10h_owner_gate_single_cycle_live_delta_canary_terms_ready"])
        self.assertEqual(summary["approved_max_notional_usdt"], 75.0)
        self.assertEqual(summary["approved_symbol"], "BTCUSDT")
        self.assertEqual(summary["approved_order_type"], "post_only_limit")
        self.assertEqual(summary["approved_time_in_force"], "GTX")
        self.assertEqual(summary["approved_cycles"], 1)
        self.assertFalse(summary["continuous_automation"])
        self.assertEqual(summary["candidate_plan_hash"], paths["candidate_plan_sha"])
        self.assertTrue(summary["candidate_plan_hash_binding_ready"])
        self.assertTrue(summary["baseline_fallback_ready"])
        self.assertTrue(summary["kill_switch_ready"])
        self.assertTrue(summary["rollback_ready"])
        self.assertTrue(summary["future_p10i_single_cycle_canary_authorized_if_separately_requested"])
        self.assertTrue(summary["fresh_remote_proof_required_before_execution"])
        self.assertFalse(summary["execute_canary_inside_p10h"])
        self.assertFalse(summary["candidate_execution_authorized_now"])
        self.assertFalse(summary["live_order_submission_authorized_now"])
        self.assertFalse(summary["target_plan_replacement_authorized_now"])
        self.assertFalse(summary["executor_input_mutation_authorized_now"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P10I_GATE)

        outputs = summary["output_files"]
        terms = _load_json(Path(outputs["terms"]))
        binding = _load_json(Path(outputs["candidate_plan_hash_binding"]))
        fallback = _load_json(Path(outputs["baseline_fallback_contract"]))
        kill_switch = _load_json(Path(outputs["kill_switch_contract"]))
        rollback = _load_json(Path(outputs["rollback_contract"]))
        matrix = _load_json(Path(outputs["non_authorization_matrix"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertEqual(terms["max_notional_usdt"], 75.0)
        self.assertEqual(terms["symbol"], "BTCUSDT")
        self.assertFalse(terms["continuous_automation"])
        self.assertEqual(binding["candidate_plan_hash_from_p10g_summary"], paths["candidate_plan_sha"])
        self.assertTrue(binding["candidate_plan_hash_matches_p10g_summary"])
        self.assertTrue(binding["candidate_symbol_in_plan"])
        self.assertEqual(fallback["fallback_action"], "executor_target_source=baseline_only; candidate_live_delta_enabled=false; submit_no_candidate_order")
        self.assertTrue(kill_switch["active_state_selects_baseline"])
        self.assertTrue(rollback["reduce_only_close_only_if_filled"])
        self.assertFalse(matrix["authorizations"]["execute_canary_inside_p10h"])
        self.assertFalse(matrix["authorizations"]["continuous_automation"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p10g_is_not_ready(self) -> None:
        paths = self._write_ready_p10g_bundle(summary_overrides={"status": "blocked"})

        summary, exit_code = run_p10h_owner_gate_single_cycle_live_delta_canary_terms(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "blocked"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10g_replacement_dry_run_ready", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized_now"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_terms_block_and_do_not_authorize_order(self) -> None:
        paths = self._write_ready_p10g_bundle()

        summary, exit_code = run_p10h_owner_gate_single_cycle_live_delta_canary_terms(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "bad-terms", max_notional=50.0),
            now_fn=lambda: datetime(2026, 6, 8, 19, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("max_notional_usdt_is_75", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized_now"])
        self.assertFalse(summary["executor_input_mutation_authorized_now"])

    def test_wrong_owner_decision_blocks_without_execution(self) -> None:
        paths = self._write_ready_p10g_bundle()

        summary, exit_code = run_p10h_owner_gate_single_cycle_live_delta_canary_terms(
            self._args(
                paths,
                output_root=self.temp_dir / "proof_artifacts" / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 19, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p10h_terms_only_recorded", summary["blockers"])
        self.assertFalse(summary["execute_canary_inside_p10h"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path | str],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P10H_DECISION,
        max_notional: float = 75.0,
    ) -> Namespace:
        return Namespace(
            p10g_summary=paths["p10g_summary"],
            output_root=output_root,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
            max_notional_usdt=max_notional,
            symbol="BTCUSDT",
            order_type="post_only_limit",
            time_in_force="GTX",
            cycles=1,
            continuous_automation=False,
        )

    def _write_ready_p10g_bundle(self, summary_overrides: dict[str, object] | None = None) -> dict[str, Path | str]:
        root = self.temp_dir / "p10g"
        candidate = root / "candidate_target_plan.json"
        summary_path = root / "summary.json"
        candidate_plan = {
            "contract_version": "hv_balanced_12factor_p10g_target_plan.v1",
            "positions": [
                {"symbol": "BTCUSDT", "target_weight": 0.1, "target_notional_usdt": 75.0},
                {"symbol": "ETHUSDT", "target_weight": -0.1, "target_notional_usdt": -75.0},
            ],
        }
        candidate_sha = stable_payload_sha256(candidate_plan)
        _write_json(candidate, candidate_plan)
        summary = {
            "status": "ready",
            "p10g_candidate_target_plan_replacement_dry_run_ready": True,
            "candidate_target_plan_replacement_semantics_proven": True,
            "hash_binding_proven": True,
            "baseline_fallback_proven": True,
            "kill_switch_proven": True,
            "actual_executor_input_changed": False,
            "actual_target_plan_replaced": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "candidate_target_plan_sha256": candidate_sha,
            "output_files": {"candidate_target_plan": str(candidate)},
        }
        summary.update(summary_overrides or {})
        _write_json(summary_path, summary)
        return {"p10g_summary": summary_path, "candidate_plan_sha": candidate_sha}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
