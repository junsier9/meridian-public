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

from scripts.governance.run_restricted_unattended_gate import (  # noqa: E402
    APPROVE_RESTRICTED_UNATTENDED,
    NEXT_GATE,
    STAGE4,
    build_restricted_unattended_gate,
)


_NOW = datetime(2026, 6, 9, 19, 0, tzinfo=UTC)


class RestrictedUnattendedGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="restricted-unattended-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_ready_does_not_authorize(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_restricted_unattended_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "dry-run"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["restricted_unattended_gate_ready"])
        self.assertFalse(summary["apply_requested"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])

    def test_apply_ready_authorizes_continuous_flow(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_restricted_unattended_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "apply", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(summary["continuous_automated_order_flow_authorized"])
        self.assertTrue(summary["timer_path_load_authorized"])
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)
        # Even authorized, this gate never arms or submits.
        self.assertFalse(summary["live_delta_armed_in_this_gate"])
        self.assertEqual(summary["orders_submitted"], 0)
        auth = _load_json(Path(summary["output_files"]["restricted_unattended_authorization"]))
        self.assertTrue(auth["continuous_automated_order_flow_authorized"])
        self.assertFalse(auth["live_delta_armed_in_this_gate"])

    def test_blocks_when_budget_gate_flag_off(self) -> None:
        paths = self._write_ready_inputs(budget_gate_on=False)

        summary, exit_code = build_restricted_unattended_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "budget-off", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("host_budget_gate_enabled", summary["blockers"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])

    def test_blocks_when_epoch_too_large(self) -> None:
        paths = self._write_ready_inputs(epoch_overrides={"max_live_cycles": 200})

        summary, exit_code = build_restricted_unattended_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "big-epoch", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("epoch_cycles_within_ceiling", summary["blockers"])
        self.assertIn("epoch_cycles_within_human_review_cadence", summary["blockers"])

    def test_blocks_when_host_load_source_unproven(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_restricted_unattended_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "out" / "unproven-host",
                apply=True,
                host_load_source_proven=False,
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("host_load_source_proven", summary["blockers"])

    def test_blocks_when_stage_not_stage4(self) -> None:
        paths = self._write_ready_inputs(current_stage="stage_3_human_approved_execution")

        summary, exit_code = build_restricted_unattended_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "stage3", apply=True),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("stage4_active", summary["blockers"])

    def test_wrong_owner_decision_blocks(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_restricted_unattended_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "out" / "wrong-owner",
                apply=True,
                owner_decision="approve_unbounded_unattended",
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_restricted_unattended_recorded", summary["blockers"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        apply: bool = False,
        host_load_source_proven: bool = True,
        owner_decision: str = APPROVE_RESTRICTED_UNATTENDED,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            host_config=str(paths["host_config"]),
            profile_transition_summary=str(paths["profile_transition_summary"]),
            epoch_summary=str(paths["epoch_summary"]),
            max_live_cycles_ceiling=6,
            max_age_seconds_ceiling=3600.0,
            max_cycles_before_human_review=6,
            max_evidence_age_seconds=86400.0,
            host_load_source_proven=host_load_source_proven,
            terminal_budget_disarm_confirmed=True,
            apply=apply,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        current_stage: str = STAGE4,
        budget_gate_on: bool = True,
        per_order_gate_on: bool = True,
        epoch_overrides: dict | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        host_config = self.temp_dir / "host_config.yaml"
        transition = self.temp_dir / "profile_transition_summary.json"
        epoch_summary = self.temp_dir / "epoch_summary.json"

        _write_json(
            project_profile,
            {"contract_version": "project_profile.v1", "current_stage": current_stage},
        )
        host_config.write_text(
            "core_loop:\n"
            f"  unattended_budget_gate_enabled: {str(budget_gate_on).lower()}\n"
            "risk:\n"
            f"  per_order_notional_gate_enabled: {str(per_order_gate_on).lower()}\n",
            encoding="utf-8",
        )
        _write_json(
            transition,
            {
                "contract_version": "project_governance_stage4_profile_transition_and_manifest_unlock_gate.v1",
                "status": "ready",
                "stage_advance_applied": True,
                "generated_at_utc": "2026-06-09T18:59:00Z",
            },
        )
        epoch = {
            "status": "open",
            "max_live_cycles": 5,
            "max_age_seconds": 3000.0,
            "max_gross_turnover_usdt": 500.0,
        }
        epoch.update(epoch_overrides or {})
        _write_json(epoch_summary, epoch)

        return {
            "project_profile": project_profile,
            "host_config": host_config,
            "profile_transition_summary": transition,
            "epoch_summary": epoch_summary,
        }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
