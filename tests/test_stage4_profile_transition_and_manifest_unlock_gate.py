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

from scripts.governance.run_stage4_profile_transition_and_manifest_unlock_gate import (  # noqa: E402
    APPROVE_PROFILE_TRANSITION,
    NEXT_GATE,
    STAGE3,
    STAGE4,
    build_stage4_profile_transition_and_manifest_unlock_gate,
)


_NOW = datetime(2026, 6, 9, 18, 0, tzinfo=UTC)


class Stage4ProfileTransitionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="stage4-profile-transition-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_ready_does_not_mutate_profile(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "dry-run"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["stage4_profile_transition_gate_ready"])
        self.assertFalse(summary["apply_requested"])
        self.assertFalse(summary["stage_advance_applied"])
        self.assertEqual(summary["post_transition_stage"], STAGE3)
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        # Profile file untouched.
        self.assertEqual(_load_json(paths["project_profile"])["current_stage"], STAGE3)

    def test_apply_ready_advances_stage_to_stage4(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "apply", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(summary["stage_advance_applied"])
        self.assertEqual(summary["post_transition_stage"], STAGE4)
        self.assertTrue(summary["automated_execution_stage_unlocked"])
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)
        # Profile file actually advanced; other keys preserved.
        profile = _load_json(paths["project_profile"])
        self.assertEqual(profile["current_stage"], STAGE4)
        self.assertEqual(profile["target_stage"], STAGE4)
        self.assertEqual(profile["slug"], "meridian_alpha")
        # Runtime order flow still NOT authorized here.
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])

    def test_blocks_and_does_not_mutate_when_code_gate_not_ready(self) -> None:
        paths = self._write_ready_inputs(code_gate_overrides={"status": "blocked"})

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "code-gate-blocked", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("code_gate_summary_ready", summary["blockers"])
        self.assertFalse(summary["stage_advance_applied"])
        self.assertEqual(_load_json(paths["project_profile"])["current_stage"], STAGE3)

    def test_blocks_when_evidence_stale(self) -> None:
        paths = self._write_ready_inputs(
            code_gate_overrides={"generated_at_utc": "2020-01-01T00:00:00Z"}
        )

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "stale", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("code_gate_summary_fresh", summary["blockers"])
        self.assertFalse(summary["stage_advance_applied"])

    def test_wrong_owner_decision_blocks_without_mutation(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "out" / "wrong-owner",
                apply=True,
                owner_decision="approve_everything_now",
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_profile_transition_recorded", summary["blockers"])
        self.assertFalse(summary["stage_advance_applied"])
        self.assertEqual(_load_json(paths["project_profile"])["current_stage"], STAGE3)

    def test_blocks_when_current_stage_not_stage3(self) -> None:
        paths = self._write_ready_inputs(current_stage=STAGE4)

        summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "already-stage4", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("current_stage_is_stage3", summary["blockers"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        apply: bool = False,
        owner_decision: str = APPROVE_PROFILE_TRANSITION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            stage_contract=str(paths["stage_contract"]),
            agent_layer_manifest=str(paths["agent_layer_manifest"]),
            code_gate_summary=str(paths["code_gate_summary"]),
            stage4_boundary_summary=str(paths["stage4_boundary_summary"]),
            max_evidence_age_seconds=86400.0,
            apply=apply,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        current_stage: str = STAGE3,
        code_gate_overrides: dict | None = None,
        boundary_overrides: dict | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        stage_contract = self.temp_dir / "stage_contract.json"
        agent_manifest = self.temp_dir / "agent_layer_manifest.json"
        code_gate_summary = self.temp_dir / "code_gate_summary.json"
        boundary_summary = self.temp_dir / "stage4_boundary_summary.json"

        _write_json(
            project_profile,
            {
                "contract_version": "project_profile.v1",
                "slug": "meridian_alpha",
                "current_stage": current_stage,
                "target_stage": STAGE4,
            },
        )
        _write_json(
            stage_contract,
            {
                "contract_version": "project_stage_contract.v1",
                "stages": [
                    {"stage_id": "stage_2_manual_export_human_review"},
                    {"stage_id": STAGE3},
                    {"stage_id": STAGE4},
                ],
                "unlock_minimum_stages": {"automated_execution_unlock": STAGE4},
            },
        )
        _write_json(
            agent_manifest,
            {
                "contract_version": "agent_layer_governance.v2",
                "agent_layer_governance_enabled": True,
                "broad_agent_layer_enabled": False,
            },
        )
        code_gate = {
            "contract_version": "project_governance_code_gate_verification_gate.v1",
            "status": "ready",
            "code_gate_verification_gate_ready": True,
            "generated_at_utc": "2026-06-09T17:59:00Z",
        }
        code_gate.update(code_gate_overrides or {})
        _write_json(code_gate_summary, code_gate)
        boundary = {
            "contract_version": "project_governance_stage4_automated_execution_boundary_owner_gate.v1",
            "status": "ready",
            "stage4_automated_execution_boundary_owner_gate_ready": True,
            "future_stage4_profile_transition_request_allowed": True,
            "generated_at_utc": "2026-06-09T17:59:30Z",
        }
        boundary.update(boundary_overrides or {})
        _write_json(boundary_summary, boundary)

        return {
            "project_profile": project_profile,
            "stage_contract": stage_contract,
            "agent_layer_manifest": agent_manifest,
            "code_gate_summary": code_gate_summary,
            "stage4_boundary_summary": boundary_summary,
        }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
