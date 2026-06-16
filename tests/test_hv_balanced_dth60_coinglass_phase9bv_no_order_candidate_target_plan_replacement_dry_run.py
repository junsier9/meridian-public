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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    CONTRACT_VERSION as P9BU_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_RISK_CEILING_USDT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    APPROVE_P9BV_DECISION,
    P9BW_GATE,
    build_p9bv_no_order_candidate_target_plan_replacement_dry_run,
)


class Phase9BVNoOrderReplacementDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bv-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_replacement_dry_run_proves_shadow_semantics_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "p9bv"),
            now_fn=lambda: datetime(2026, 6, 10, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bv_no_order_replacement_dry_run_ready"])
        self.assertTrue(summary["candidate_target_plan_replacement_semantics_proven"])
        self.assertTrue(summary["exact_p9bu_terms_applied"])
        self.assertTrue(summary["same_timestamp_context"])
        self.assertTrue(summary["same_risk_inputs"])
        self.assertTrue(summary["candidate_plan_differs_from_baseline"])
        self.assertTrue(summary["simulated_executor_input_replacement_matches_candidate"])
        self.assertFalse(summary["actual_executor_input_changed"])
        self.assertFalse(summary["actual_target_plan_replaced"])
        self.assertTrue(summary["only_distance_to_high_60_contribution_changed"])
        self.assertEqual(summary["changed_symbol_count"], 1)
        self.assertEqual(summary["order_intent_preview_count"], 1)
        self.assertEqual(summary["risk_ceiling_usdt"], DEFAULT_RISK_CEILING_USDT)
        self.assertEqual(summary["max_notional_usdt"], DEFAULT_MAX_NOTIONAL_USDT)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")
        self.assertEqual(summary["allowed_next_gate"], P9BW_GATE)
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        baseline = _load_json(Path(outputs["baseline_target_plan"]))
        candidate = _load_json(Path(outputs["candidate_target_plan"]))
        diff = _load_json(Path(outputs["target_plan_diff"]))
        preview = _load_json(Path(outputs["order_intent_preview"]))
        replacement = _load_json(Path(outputs["replacement_dry_run"]))
        matrix = _load_json(Path(outputs["non_authorization_matrix"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertEqual(baseline["as_of_utc"], candidate["as_of_utc"])
        self.assertEqual(baseline["risk_inputs"], candidate["risk_inputs"])
        self.assertEqual(diff["changed_symbols"], ["BTCUSDT"])
        self.assertTrue(diff["only_distance_to_high_60_contribution_changed"])
        self.assertTrue(preview["preview_only"])
        self.assertEqual(preview["orders_submitted"], 0)
        self.assertEqual(
            replacement["simulated_executor_input_plan_sha256_after_dry_run"],
            summary["candidate_target_plan_sha256"],
        )
        self.assertEqual(
            replacement["actual_executor_input_plan_sha256_after_dry_run"],
            summary["baseline_target_plan_sha256"],
        )
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["actual_executor_input_mutation"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])

    def test_blocks_when_p9bu_summary_is_not_ready(self) -> None:
        paths = self._write_ready_inputs(summary_overrides={"status": "blocked"})

        summary, exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "blocked-p9bu"),
            now_fn=lambda: datetime(2026, 6, 10, 10, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bu_ready_for_replacement_dry_run", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_terms_do_not_match_p9bu_exact_contract(self) -> None:
        paths = self._write_ready_inputs(terms_overrides={"max_notional_usdt": 11.0})

        summary, exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "bad-terms"),
            now_fn=lambda: datetime(2026, 6, 10, 10, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bu_terms_exact", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_execution(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 10, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bv_recorded", summary["blockers"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BV_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bu_summary=str(paths["p9bu_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        terms_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bu_root = self.temp_dir / "p9bu"
        p9bu_summary = p9bu_root / "summary.json"
        terms_path = p9bu_root / "proof_artifacts" / "p9bu" / "terms.json"
        preapproval_path = p9bu_root / "proof_artifacts" / "p9bu" / "preapproval.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        terms = _p9bu_terms()
        terms.update(terms_overrides or {})
        preapproval = _p9bu_preapproval()
        summary = {
            "contract_version": P9BU_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bu_preapproval_terms_review_ready": True,
            "candidate_executor_target_path_preapproval_exists": True,
            "candidate_executor_target_path_preapproval_review_passed": True,
            "requested_live_order_terms_complete": True,
            "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_orders_per_cycle": 1,
            "max_symbols_per_cycle": 1,
            "order_type": "post_only_limit",
            "time_in_force": "GTX",
            "candidate_enter_executor_target_plan_path_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "output_files": {
                "risk_order_terms": str(terms_path),
                "candidate_executor_target_plan_preapproval": str(preapproval_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(terms_path, terms)
        _write_json(preapproval_path, preapproval)
        _write_json(p9bu_summary, summary)
        return {
            "project_profile": project_profile,
            "p9bu_summary": p9bu_summary,
        }


def _p9bu_terms() -> dict[str, object]:
    return {
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "reduce_only_required_for_rollback_exits": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "candidate_overlay_components": [
            "coinglass_top_trader_crowded_branch",
            "binance_shock_branch",
        ],
        "fresh_account_read_max_age_seconds": 60,
        "fresh_position_fingerprint_max_age_seconds": 60,
        "fresh_open_order_fingerprint_max_age_seconds": 60,
        "fresh_fill_trade_fingerprint_max_age_seconds": 60,
        "fresh_order_book_max_age_seconds": 10,
        "candidate_artifact_stale_after_seconds": 60,
        "limit_price_must_not_cross_spread": True,
        "max_limit_price_distance_bps_from_mid": 5,
        "max_mark_price_deviation_bps": 10,
        "order_lifetime_seconds": 60,
        "kill_switch": "disable candidate and revert executor to baseline-only",
        "rollback_conditions": [
            "candidate proof missing",
            "executor hash mismatch",
            "unexplained order delta",
        ],
    }


def _p9bu_preapproval() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval.v1",
        "run_id": "unit-test",
        "status": "ready",
        "candidate_executor_target_path_preapproval_exists": True,
        "candidate_executor_target_path_preapproval_review_passed": True,
        "candidate_enter_executor_target_plan_path_authorized_now": False,
        "candidate_execution_authorized_now": False,
        "live_order_submission_authorized_now": False,
        "integration_contract": {
            "baseline_plan_must_be_generated_first": True,
            "candidate_plan_must_be_paired_with_baseline_same_timestamp": True,
            "candidate_plan_must_use_same_risk_inputs_as_baseline": True,
            "candidate_target_plan_replacement_requires_future_no_order_dry_run": True,
            "executor_input_replacement_requires_future_live_order_gate": True,
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
