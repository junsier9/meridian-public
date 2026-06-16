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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    CONTRACT_VERSION as P9BS_SCOPE_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bt_stage3_profile_transition import (  # noqa: E402
    CONTRACT_VERSION as P9BT_CONTRACT,
    STAGE3,
    STAGE4,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    APPROVE_P9BU_DECISION,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_RISK_CEILING_USDT,
    P9BV_GATE,
    build_p9bu_executor_target_plan_preapproval_terms_review,
)


class Phase9BUPreapprovalTermsReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bu-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_preapproval_terms_review_does_not_authorize_execution(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bu_executor_target_plan_preapproval_terms_review(
            self._args(paths, output_root=self.temp_dir / "p9bu"),
            now_fn=lambda: datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bu_preapproval_terms_review_ready"])
        self.assertTrue(summary["candidate_executor_target_path_preapproval_exists"])
        self.assertTrue(summary["requested_live_order_terms_complete"])
        self.assertEqual(summary["risk_ceiling_usdt"], DEFAULT_RISK_CEILING_USDT)
        self.assertEqual(summary["max_notional_usdt"], DEFAULT_MAX_NOTIONAL_USDT)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")
        self.assertEqual(summary["allowed_next_gate"], P9BV_GATE)
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        preapproval = _load_json(Path(outputs["candidate_executor_target_plan_preapproval"]))
        terms = _load_json(Path(outputs["risk_order_terms"]))
        matrix = _load_json(Path(outputs["non_authorization_matrix"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertTrue(preapproval["candidate_executor_target_path_preapproval_exists"])
        self.assertFalse(preapproval["candidate_enter_executor_target_plan_path_authorized_now"])
        self.assertEqual(terms["candidate_delta_source"], "distance_to_high_60_contribution_only")
        self.assertFalse(terms["market_orders_allowed"])
        self.assertTrue(matrix["authorizations"]["define_concrete_risk_order_terms"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["candidate_entered_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_stage3_review_is_not_ready(self) -> None:
        paths = self._write_ready_inputs(p9bt_overrides={"current_stage": "stage_1_research_readiness_only"})

        summary, exit_code = build_p9bu_executor_target_plan_preapproval_terms_review(
            self._args(paths, output_root=self.temp_dir / "bad-stage"),
            now_fn=lambda: datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bt_stage3_ready", summary["blockers"])
        self.assertFalse(summary["candidate_executor_target_path_preapproval_exists"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_blocks_when_terms_exceed_canary_caps(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bu_executor_target_plan_preapproval_terms_review(
            self._args(
                paths,
                output_root=self.temp_dir / "bad-terms",
                risk_ceiling_usdt=100.0,
                max_notional_usdt=50.0,
                order_type="market",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 9, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("risk_ceiling_within_canary_cap", summary["blockers"])
        self.assertIn("max_notional_within_canary_cap", summary["blockers"])
        self.assertIn("order_type_supported_and_explicit", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bu_executor_target_plan_preapproval_terms_review(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 9, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bu_preapproval_terms_recorded", summary["blockers"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BU_DECISION,
        risk_ceiling_usdt: float = DEFAULT_RISK_CEILING_USDT,
        max_notional_usdt: float = DEFAULT_MAX_NOTIONAL_USDT,
        order_type: str = "post_only_limit",
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bs_scope_summary=str(paths["p9bs_scope_summary"]),
            phase9bt_summary=str(paths["p9bt_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
            risk_ceiling_usdt=risk_ceiling_usdt,
            max_notional_usdt=max_notional_usdt,
            max_orders_per_cycle=1,
            max_symbols_per_cycle=1,
            order_type=order_type,
            time_in_force="GTX",
            kill_switch="disable candidate and revert executor to baseline-only",
            rollback_condition=[
                "candidate proof missing",
                "executor hash mismatch",
                "unexplained order delta",
            ],
        )

    def _write_ready_inputs(
        self,
        *,
        p9bt_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bs_scope_summary = self.temp_dir / "p9bs_scope" / "summary.json"
        p9bt_summary = self.temp_dir / "p9bt" / "summary.json"
        _write_json(project_profile, {"current_stage": STAGE3, "target_stage": STAGE4})
        _write_json(
            p9bs_scope_summary,
            {
                "contract_version": P9BS_SCOPE_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p9bs_execution_path_scope_definition_ready": True,
                "p9br_scope_blocker_resolved": True,
                "p9bs_execution_path_change_discussion_scope_defined": True,
                "eligible_for_future_execution_path_change_proposal": True,
                "eligible_for_future_live_order_gate_terms_discussion": True,
                "execution_path_change_implementation_authorized": False,
                "execution_path_change_execution_authorized": False,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
            },
        )
        p9bt = {
            "contract_version": P9BT_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bt_stage3_profile_transition_ready": True,
            "current_stage": STAGE3,
            "project_stage_allows_live_order_gate_review": True,
            "execution_manifest_stage_minimum_satisfied": True,
            "automated_execution_unlocked": False,
            "stage4_automated_execution_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        p9bt.update(p9bt_overrides or {})
        _write_json(p9bt_summary, p9bt)
        return {
            "project_profile": project_profile,
            "p9bs_scope_summary": p9bs_scope_summary,
            "p9bt_summary": p9bt_summary,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
