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

from scripts.governance.run_stage4_transition_reattestation_gate import (  # noqa: E402
    APPROVE_TRANSITION_REATTESTATION,
    NEXT_GATE,
    STAGE3,
    STAGE4,
    build_stage4_transition_reattestation_gate,
)


_NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


class Stage4TransitionReattestationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="stage4-transition-reattest-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reattests_without_touching_profile(self) -> None:
        paths = self._write_ready_inputs()
        profile_before = _load_json(paths["project_profile"])

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "ready"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["stage4_transition_reattestation_gate_ready"])
        # Carries exactly the keys the restricted gate consumes from a transition summary.
        self.assertTrue(summary["stage_advance_applied"])
        self.assertTrue(summary["stage_advance_reattested"])
        self.assertFalse(summary["stage_advance_mutation_performed"])
        self.assertEqual(summary["generated_at_utc"], "2026-06-12T12:00:00Z")  # fresh stamp
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)
        # Profile file byte-identical: no mutation, no re-apply.
        self.assertEqual(_load_json(paths["project_profile"]), profile_before)

    def test_blocks_when_code_gate_stale(self) -> None:
        paths = self._write_ready_inputs(code_gate_overrides={"generated_at_utc": "2020-01-01T00:00:00Z"})

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "stale"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("code_gate_summary_fresh", summary["blockers"])
        self.assertFalse(summary["stage_advance_applied"])

    def test_blocks_when_code_gate_not_ready(self) -> None:
        paths = self._write_ready_inputs(code_gate_overrides={"status": "blocked"})

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "code-blocked"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("code_gate_summary_ready", summary["blockers"])

    def test_blocks_when_prior_transition_not_applied(self) -> None:
        paths = self._write_ready_inputs(prior_overrides={"stage_advance_applied": False})

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "prior-not-applied"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("prior_transition_summary_attests_applied", summary["blockers"])

    def test_blocks_when_prior_transition_landed_off_stage4(self) -> None:
        paths = self._write_ready_inputs(prior_overrides={"post_transition_stage": STAGE3})

        summary, _ = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "prior-off-stage4"),
            now_fn=lambda: _NOW,
        )

        self.assertIn("prior_transition_summary_attests_applied", summary["blockers"])

    def test_blocks_when_current_stage_not_stage4(self) -> None:
        paths = self._write_ready_inputs(current_stage=STAGE3)

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "not-stage4"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("current_stage_is_stage4", summary["blockers"])

    def test_blocks_when_prior_transition_beyond_reattestation_window(self) -> None:
        # The original transition is >30 days old: re-attestation must refuse to refresh it,
        # so a stale stage_4 cannot be laundered into "fresh" off code-gate evidence forever.
        paths = self._write_ready_inputs(prior_overrides={"generated_at_utc": "2026-01-01T00:00:00Z"})

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "beyond-window"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("prior_transition_summary_within_reattestation_window", summary["blockers"])
        self.assertFalse(summary["stage_advance_applied"])

    def test_blocks_when_broad_agent_layer_enabled(self) -> None:
        paths = self._write_ready_inputs(agent_overrides={"broad_agent_layer_enabled": True})

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "broad-enabled"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("broad_agent_layer_remains_disabled", summary["blockers"])

    def test_ready_state_has_no_blockers(self) -> None:
        paths = self._write_ready_inputs()
        summary, _ = build_stage4_transition_reattestation_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "ready-empty"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(all(summary["checks"].values()))

    def test_wrong_owner_decision_blocks(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_stage4_transition_reattestation_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "out" / "wrong-owner",
                owner_decision="approve_everything_now",
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_transition_reattestation_recorded", summary["blockers"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_TRANSITION_REATTESTATION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            stage_contract=str(paths["stage_contract"]),
            agent_layer_manifest=str(paths["agent_layer_manifest"]),
            prior_transition_summary=str(paths["prior_transition_summary"]),
            code_gate_summary=str(paths["code_gate_summary"]),
            max_evidence_age_seconds=86400.0,
            max_prior_transition_age_seconds=2592000.0,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        current_stage: str = STAGE4,
        code_gate_overrides: dict | None = None,
        prior_overrides: dict | None = None,
        agent_overrides: dict | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        stage_contract = self.temp_dir / "stage_contract.json"
        agent_manifest = self.temp_dir / "agent_layer_manifest.json"
        code_gate_summary = self.temp_dir / "code_gate_summary.json"
        prior_transition = self.temp_dir / "prior_transition_summary.json"

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
                "stages": [{"stage_id": STAGE3}, {"stage_id": STAGE4}],
                "unlock_minimum_stages": {"automated_execution_unlock": STAGE4},
            },
        )
        agent = {"contract_version": "agent_layer_governance.v2", "broad_agent_layer_enabled": False}
        agent.update(agent_overrides or {})
        _write_json(agent_manifest, agent)
        code_gate = {
            "contract_version": "project_governance_code_gate_verification_gate.v1",
            "status": "ready",
            "code_gate_verification_gate_ready": True,
            "generated_at_utc": "2026-06-12T11:59:00Z",
        }
        code_gate.update(code_gate_overrides or {})
        _write_json(code_gate_summary, code_gate)
        prior = {
            "contract_version": "project_governance_stage4_profile_transition_and_manifest_unlock_gate.v1",
            "status": "ready",
            "stage_advance_applied": True,
            "post_transition_stage": STAGE4,
            "generated_at_utc": "2026-06-10T09:07:10Z",  # the one-shot original, now stale
        }
        prior.update(prior_overrides or {})
        _write_json(prior_transition, prior)

        return {
            "project_profile": project_profile,
            "stage_contract": stage_contract,
            "agent_layer_manifest": agent_manifest,
            "code_gate_summary": code_gate_summary,
            "prior_transition_summary": prior_transition,
        }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
