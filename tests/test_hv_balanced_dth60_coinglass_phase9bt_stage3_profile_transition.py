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
    APPROVE_P9BT_STAGE3_DECISION,
    STAGE3,
    STAGE4,
    build_p9bt_stage3_profile_transition,
)


class Phase9BTStage3ProfileTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bt-stage3-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_stage3_transition_ready_without_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bt_stage3_profile_transition(
            self._args(paths, output_root=self.temp_dir / "p9bt"),
            now_fn=lambda: datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bt_stage3_profile_transition_ready"])
        self.assertTrue(summary["stage_profile_transition_applied"])
        self.assertEqual(summary["current_stage"], STAGE3)
        self.assertTrue(summary["project_stage_allows_live_order_gate_review"])
        self.assertTrue(summary["execution_manifest_stage_minimum_satisfied"])
        self.assertFalse(summary["automated_execution_unlocked"])
        self.assertFalse(summary["stage4_automated_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = (
            self.temp_dir
            / "p9bt"
            / "proof_artifacts"
            / "p9bt_stage3_profile_transition"
            / "20260610T080000Z"
        )
        readback = _load_json(proof_root / "stage3_profile_transition_readback.json")
        matrix = _load_json(proof_root / "non_authorization_matrix.json")
        control = _load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(readback["stage3_transition_applied"])
        self.assertFalse(readback["automated_execution_unlocked"])
        self.assertTrue(matrix["authorizations"]["stage3_profile_transition"])
        self.assertFalse(matrix["authorizations"]["stage4_automated_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_if_project_profile_still_stage1(self) -> None:
        paths = self._write_ready_inputs(current_stage="stage_1_research_readiness_only")

        summary, exit_code = build_p9bt_stage3_profile_transition(
            self._args(paths, output_root=self.temp_dir / "stage1"),
            now_fn=lambda: datetime(2026, 6, 10, 8, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_stage_is_stage3", summary["blockers"])
        self.assertFalse(summary["stage_profile_transition_applied"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_wrong_owner_decision_blocks_stage_transition_readback(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bt_stage3_profile_transition(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_stage4_automation",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 8, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_stage3_transition_recorded", summary["blockers"])
        self.assertFalse(summary["stage4_automated_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BT_STAGE3_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            stage_contract=str(paths["stage_contract"]),
            phase9bs_scope_summary=str(paths["p9bs_scope_summary"]),
            readme=str(paths["readme"]),
            agents=str(paths["agents"]),
            readme_for_agent=str(paths["readme_for_agent"]),
            project_state=str(paths["project_state"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self, *, current_stage: str = STAGE3) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        stage_contract = self.temp_dir / "stage_contract.json"
        p9bs_scope_summary = self.temp_dir / "p9bs_scope" / "summary.json"
        readme = self.temp_dir / "README.md"
        agents = self.temp_dir / "AGENTS.md"
        readme_for_agent = self.temp_dir / "docs" / "README_FOR_AGENT.md"
        project_state = self.temp_dir / "PROJECT_STATE.md"
        _write_json(
            project_profile,
            {"current_stage": current_stage, "target_stage": STAGE4},
        )
        _write_json(
            stage_contract,
            {
                "stages": [
                    {"stage_id": "stage_1_research_readiness_only"},
                    {"stage_id": STAGE3},
                    {"stage_id": STAGE4},
                ],
                "unlock_minimum_stages": {
                    "execution_manifest_unlock": STAGE3,
                    "automated_execution_unlock": STAGE4,
                },
            },
        )
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
        readme.write_text(
            "Current checked-in stage is `Stage 3: Human-Approved Execution`.\n",
            encoding="utf-8",
        )
        agents.write_text(
            "The checked-in repo is now at `Stage 3: Human-Approved Execution`.\n",
            encoding="utf-8",
        )
        readme_for_agent.parent.mkdir(parents=True, exist_ok=True)
        readme_for_agent.write_text(
            "Current checked-in state is `Stage 3: Human-Approved Execution`.\n",
            encoding="utf-8",
        )
        project_state.write_text(
            "Current checked-in stage is `stage_3_human_approved_execution`.\n",
            encoding="utf-8",
        )
        return {
            "project_profile": project_profile,
            "stage_contract": stage_contract,
            "p9bs_scope_summary": p9bs_scope_summary,
            "readme": readme,
            "agents": agents,
            "readme_for_agent": readme_for_agent,
            "project_state": project_state,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
