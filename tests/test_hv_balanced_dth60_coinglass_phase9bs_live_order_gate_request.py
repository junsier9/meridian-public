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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9br_review_after_p9bq import (  # noqa: E402
    CONTRACT_VERSION as P9BR_CONTRACT,
    P9BS_GATE,
    P9BS_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_live_order_gate_request import (  # noqa: E402
    APPROVE_P9BS_LIVE_ORDER_DECISION,
    build_p9bs_live_order_gate_request,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    CONTRACT_VERSION as P9BS_SCOPE_CONTRACT,
)


class Phase9BSLiveOrderGateRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bs-live-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_stage1_live_order_gate_request_blocks_fail_closed(self) -> None:
        paths = self._write_ready_p9br_bundle(stage="stage_1_research_readiness_only")

        summary, exit_code = build_p9bs_live_order_gate_request(
            self._args(paths, output_root=self.temp_dir / "p9bs-live"),
            now_fn=lambda: datetime(2026, 6, 10, 6, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertTrue(summary["live_order_gate_requested"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_executor_target_path_approved"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertIn("project_stage_allows_live_order", summary["blockers"])
        self.assertIn("p9bs_scope_summary_exists", summary["blockers"])
        self.assertIn("p9bs_scope_ready_for_live_order_gate_review", summary["blockers"])
        self.assertIn("p9br_authorizes_live_order_gate", summary["blockers"])
        self.assertIn("scope_definition_gate_executed_before_live_order_gate", summary["blockers"])

        proof_root = (
            self.temp_dir
            / "p9bs-live"
            / "proof_artifacts"
            / "p9bs_live_order_request"
            / "20260610T060000Z"
        )
        review = _load_json(proof_root / "live_order_gate_request_review.json")
        matrix = _load_json(proof_root / "non_authorization_matrix.json")
        control = _load_json(proof_root / "control_boundary_readback.json")
        self.assertEqual(review["status"], "blocked")
        self.assertFalse(review["live_order_gate_approved"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_executor_target_path_entry"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_even_complete_terms_block_until_p9bs_scope_gate_executes(self) -> None:
        paths = self._write_ready_p9br_bundle(stage="stage_3_human_approved_execution")

        summary, exit_code = build_p9bs_live_order_gate_request(
            self._args(
                paths,
                output_root=self.temp_dir / "complete-terms",
                risk_ceiling_usdt="25",
                max_notional_usdt="10",
                order_type="post_only_limit",
                kill_switch="disable_candidate_overlay_and_revert_to_baseline_plan",
                rollback_condition=["any order/fill anomaly"],
            ),
            now_fn=lambda: datetime(2026, 6, 10, 6, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertNotIn("project_stage_allows_live_order", summary["blockers"])
        self.assertNotIn("requested_live_order_terms_complete", summary["blockers"])
        self.assertIn("p9bs_scope_summary_exists", summary["blockers"])
        self.assertIn("p9bs_scope_ready_for_live_order_gate_review", summary["blockers"])
        self.assertIn("p9br_authorizes_live_order_gate", summary["blockers"])
        self.assertIn("scope_definition_gate_executed_before_live_order_gate", summary["blockers"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_stage3_with_p9bs_scope_removes_stage_and_p9br_scope_blockers(self) -> None:
        paths = self._write_ready_p9br_bundle(
            stage="stage_3_human_approved_execution",
            include_p9bs_scope=True,
        )

        summary, exit_code = build_p9bs_live_order_gate_request(
            self._args(
                paths,
                output_root=self.temp_dir / "scope-fixed",
                risk_ceiling_usdt="25",
                max_notional_usdt="10",
                order_type="post_only_limit",
                kill_switch="disable_candidate_overlay_and_revert_to_baseline_plan",
                rollback_condition=["any order/fill anomaly"],
            ),
            now_fn=lambda: datetime(2026, 6, 10, 6, 7, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertNotIn("project_stage_allows_live_order", summary["blockers"])
        self.assertNotIn("p9bs_scope_summary_exists", summary["blockers"])
        self.assertNotIn("p9bs_scope_ready_for_live_order_gate_review", summary["blockers"])
        self.assertNotIn("p9br_authorizes_live_order_gate", summary["blockers"])
        self.assertNotIn("scope_definition_gate_executed_before_live_order_gate", summary["blockers"])
        self.assertNotIn("requested_live_order_terms_complete", summary["blockers"])
        self.assertEqual(summary["blockers"], ["candidate_executor_target_path_preapproval_exists"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_and_does_not_authorize_anything(self) -> None:
        paths = self._write_ready_p9br_bundle(stage="stage_1_research_readiness_only")

        summary, exit_code = build_p9bs_live_order_gate_request(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 6, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_live_order_request_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["repo_stage_change_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BS_LIVE_ORDER_DECISION,
        risk_ceiling_usdt: str = "",
        max_notional_usdt: str = "",
        order_type: str = "",
        kill_switch: str = "",
        rollback_condition: list[str] | None = None,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9br_summary=str(paths["p9br_summary"]),
            phase9bs_scope_summary=str(
                paths.get("p9bs_scope_summary", self.temp_dir / "missing_p9bs_scope_summary.json")
            ),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
            risk_ceiling_usdt=risk_ceiling_usdt,
            max_notional_usdt=max_notional_usdt,
            order_type=order_type,
            kill_switch=kill_switch,
            rollback_condition=list(rollback_condition or []),
        )

    def _write_ready_p9br_bundle(
        self,
        *,
        stage: str,
        include_p9bs_scope: bool = False,
    ) -> dict[str, Path]:
        p9br_root = self.temp_dir / "p9br"
        p9br_summary = p9br_root / "summary.json"
        p9bs_scope_summary = self.temp_dir / "p9bs_scope" / "summary.json"
        project_profile = self.temp_dir / "project_profile.json"
        _write_json(project_profile, {"current_stage": stage})
        _write_json(
            p9br_summary,
            {
                "contract_version": P9BR_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p9br_retained_evidence_review_ready": True,
                "p9bq_retained_shadow_cycles_sufficient": True,
                "sufficient_for_execution_path_change_discussion": True,
                "allowed_next_gate": P9BS_GATE,
                "allowed_next_gate_scope": P9BS_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
                "execution_path_change_discussion_scope_definition_authorized": False,
                "execution_path_change_implementation_authorized": False,
                "execution_path_change_execution_authorized": False,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
            },
        )
        paths = {"project_profile": project_profile, "p9br_summary": p9br_summary}
        if include_p9bs_scope:
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
            paths["p9bs_scope_summary"] = p9bs_scope_summary
        return paths


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
