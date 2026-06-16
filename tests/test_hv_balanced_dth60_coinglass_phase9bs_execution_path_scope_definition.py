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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    APPROVE_P9BS_SCOPE_DECISION,
    P9BT_GATE,
    build_p9bs_execution_path_scope_definition,
    p9bs_scope_ready_for_live_order_gate_review,
)


class Phase9BSExecutionPathScopeDefinitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bs-scope-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_scope_definition_resolves_p9br_scope_blocker_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bs_execution_path_scope_definition(
            self._args(paths, output_root=self.temp_dir / "p9bs-scope"),
            now_fn=lambda: datetime(2026, 6, 10, 7, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bs_execution_path_scope_definition_ready"])
        self.assertTrue(summary["p9br_scope_blocker_resolved"])
        self.assertTrue(summary["eligible_for_future_live_order_gate_terms_discussion"])
        self.assertEqual(summary["allowed_next_gate"], P9BT_GATE)
        self.assertFalse(summary["execution_path_change_implementation_authorized"])
        self.assertFalse(summary["execution_path_change_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["repo_stage_change_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(p9bs_scope_ready_for_live_order_gate_review(summary))

        proof_root = (
            self.temp_dir
            / "p9bs-scope"
            / "proof_artifacts"
            / "p9bs_execution_path_scope_definition"
            / "20260610T070000Z"
        )
        scope_packet = _load_json(proof_root / "execution_path_scope_packet.json")
        matrix = _load_json(proof_root / "non_authorization_matrix.json")
        control = _load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(scope_packet["p9br_scope_blocker_resolved"])
        self.assertTrue(matrix["authorizations"]["define_execution_path_change_discussion_scope"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9br_did_not_allow_scope_definition(self) -> None:
        paths = self._write_ready_inputs(p9br_overrides={"allowed_next_gate": "P9XX_wrong_gate"})

        summary, exit_code = build_p9bs_execution_path_scope_definition(
            self._args(paths, output_root=self.temp_dir / "blocked"),
            now_fn=lambda: datetime(2026, 6, 10, 7, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9br_ready_for_scope_definition", summary["blockers"])
        self.assertFalse(summary["p9bs_execution_path_scope_definition_ready"])
        self.assertFalse(summary["p9br_scope_blocker_resolved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_wrong_owner_decision_blocks_without_authorizing_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bs_execution_path_scope_definition(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 7, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bs_scope_recorded", summary["blockers"])
        self.assertFalse(summary["p9br_scope_blocker_resolved"])
        self.assertFalse(summary["repo_stage_change_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BS_SCOPE_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9br_summary=str(paths["p9br_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9br_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        p9br_summary = self.temp_dir / "p9br" / "summary.json"
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "hook.py"
        supervisor = self.temp_dir / "supervisor.py"
        live_config_dir = self.temp_dir / "live_config"
        live_config_dir.mkdir(parents=True, exist_ok=True)
        _write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        hook_module.write_text("# hook\n", encoding="utf-8")
        supervisor.write_text("# supervisor\n", encoding="utf-8")
        (live_config_dir / "config.yaml").write_text("enabled: false\n", encoding="utf-8")
        p9br = {
            "contract_version": P9BR_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9br_retained_evidence_review_ready": True,
            "p9bq_retained_shadow_cycles_sufficient": True,
            "sufficient_for_execution_path_change_discussion": True,
            "eligible_for_future_p9bs_execution_path_change_discussion_scope_gate_request": True,
            "allowed_next_gate": P9BS_GATE,
            "allowed_next_gate_scope": P9BS_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "execution_path_change_proposal_authorized": False,
            "execution_path_change_implementation_authorized": False,
            "execution_path_change_execution_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        p9br.update(p9br_overrides or {})
        _write_json(p9br_summary, p9br)
        return {
            "project_profile": project_profile,
            "p9br_summary": p9br_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
