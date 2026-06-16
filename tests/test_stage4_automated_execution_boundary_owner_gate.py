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

from scripts.governance.run_stage4_automated_execution_boundary_owner_gate import (  # noqa: E402
    APPROVE_STAGE4_BOUNDARY_DECISION,
    NEXT_GATE,
    STAGE3,
    STAGE4,
    build_stage4_automated_execution_boundary_owner_gate,
)


class Stage4AutomatedExecutionBoundaryOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="stage4-boundary-gate-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_records_stage4_boundary_approval_without_unlocking_runtime(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_automated_execution_boundary_owner_gate(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "ready"),
            now_fn=lambda: datetime(2026, 6, 9, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["stage4_automated_execution_boundary_owner_gate_ready"])
        self.assertTrue(
            summary["stage4_automated_execution_boundary_owner_approval_collected"]
        )
        self.assertEqual(summary["current_stage"], STAGE3)
        self.assertEqual(summary["target_stage"], STAGE4)
        self.assertTrue(summary["execution_manifest_stage_minimum_satisfied"])
        self.assertFalse(summary["automated_execution_unlocked_now"])
        self.assertFalse(summary["stage4_automated_execution_authorized_now"])
        self.assertTrue(summary["future_stage4_profile_transition_request_allowed"])
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)
        self.assertFalse(summary["project_profile_mutation_performed"])
        self.assertFalse(summary["automated_execution_manifest_unlock_performed"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        readback = _load_json(Path(outputs["stage4_boundary_readback"]))
        non_auth = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        owner_record = _load_json(Path(outputs["owner_decision_record"]))
        self.assertTrue(
            readback["stage4_automated_execution_boundary_owner_approval_collected"]
        )
        self.assertFalse(readback["automated_execution_unlocked_now"])
        self.assertTrue(
            non_auth["authorizations"][
                "stage4_automated_execution_boundary_owner_approval_recorded"
            ]
        )
        self.assertFalse(non_auth["authorizations"]["project_profile_mutation_in_this_gate"])
        self.assertFalse(non_auth["authorizations"]["continuous_automated_order_flow"])
        self.assertFalse(control["project_profile_changed"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertTrue(
            owner_record[
                "stage4_automated_execution_boundary_owner_approval_collected"
            ]
        )
        self.assertFalse(owner_record["automated_execution_runtime_enablement_approved_now"])

    def test_wrong_owner_decision_blocks_boundary_approval(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_automated_execution_boundary_owner_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "proof_artifacts" / "wrong-owner",
                owner_decision="approve_stage4_runtime_enablement_now",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_stage4_boundary_recorded", summary["blockers"])
        self.assertFalse(summary["stage4_automated_execution_boundary_owner_gate_ready"])
        self.assertFalse(summary["future_stage4_profile_transition_request_allowed"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_blocks_if_current_stage_is_not_stage3(self) -> None:
        paths = self._write_ready_inputs(current_stage="stage_2_manual_export_human_review")

        summary, exit_code = build_stage4_automated_execution_boundary_owner_gate(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "stage2"),
            now_fn=lambda: datetime(2026, 6, 9, 16, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "current_stage_is_stage3_human_approved_execution", summary["blockers"]
        )
        self.assertFalse(summary["stage4_automated_execution_authorized_now"])

    def test_blocks_if_owner_verification_or_broad_lock_is_missing(self) -> None:
        paths = self._write_ready_inputs(
            runtime_overrides={"owner_verification_enforced_in_boundary_gates": False},
            manifest_overrides={"broad_agent_layer_enabled": True},
        )

        summary, exit_code = build_stage4_automated_execution_boundary_owner_gate(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "unsafe"),
            now_fn=lambda: datetime(2026, 6, 9, 16, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "owner_verification_enforced_in_boundary_gates", summary["blockers"]
        )
        self.assertIn("broad_agent_layer_remains_disabled", summary["blockers"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_STAGE4_BOUNDARY_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            stage_contract=str(paths["stage_contract"]),
            runtime_ownership_contract=str(paths["runtime_ownership_contract"]),
            agent_layer_manifest=str(paths["agent_layer_manifest"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        current_stage: str = STAGE3,
        runtime_overrides: dict[str, object] | None = None,
        manifest_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        stage_contract = self.temp_dir / "stage_contract.json"
        runtime_contract = self.temp_dir / "runtime_ownership_contract.json"
        agent_manifest = self.temp_dir / "agent_layer_manifest.json"
        _write_json(
            project_profile,
            {
                "contract_version": "project_profile.v1",
                "current_stage": current_stage,
                "target_stage": STAGE4,
            },
        )
        _write_json(
            stage_contract,
            {
                "contract_version": "project_stage_contract.v1",
                "stages": [
                    {"stage_id": "stage_1_research_readiness_only"},
                    {"stage_id": "stage_2_manual_export_human_review"},
                    {"stage_id": STAGE3},
                    {"stage_id": STAGE4},
                ],
                "unlock_minimum_stages": {
                    "execution_manifest_unlock": STAGE3,
                    "automated_execution_unlock": STAGE4,
                },
            },
        )
        runtime_payload = {
            "contract_version": "runtime_ownership_contract.v1",
            "owner_verification_required": True,
            "owner_verification_enforced_in_boundary_gates": True,
        }
        runtime_payload.update(runtime_overrides or {})
        _write_json(runtime_contract, runtime_payload)
        manifest_payload = {
            "contract_version": "agent_layer_governance.v2",
            "agent_layer_governance_enabled": True,
            "broad_agent_layer_enabled": False,
        }
        manifest_payload.update(manifest_overrides or {})
        _write_json(agent_manifest, manifest_payload)
        return {
            "project_profile": project_profile,
            "stage_contract": stage_contract,
            "runtime_ownership_contract": runtime_contract,
            "agent_layer_manifest": agent_manifest,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
