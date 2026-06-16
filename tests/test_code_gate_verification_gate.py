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

from scripts.governance.run_code_gate_verification_gate import (  # noqa: E402
    APPROVE_CODE_GATE_VERIFICATION,
    NEXT_GATE,
    REQUIRED_TEST_FILES,
    build_code_gate_verification_gate,
)


class CodeGateVerificationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="code-gate-verification-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_when_markers_present_and_evidence_green(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_code_gate_verification_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "ready"),
            now_fn=lambda: datetime(2026, 6, 9, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["code_gate_verification_gate_ready"])
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)
        self.assertFalse(summary["tests_executed_by_this_gate"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_missing_source_marker_blocks(self) -> None:
        paths = self._write_ready_inputs()
        # Wipe the Fix 4 marker out of the core-loop runner stub.
        Path(paths["core_loop_runner"]).write_text("# no marker here\n", encoding="utf-8")

        summary, exit_code = build_code_gate_verification_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "missing-marker"),
            now_fn=lambda: datetime(2026, 6, 9, 17, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("fix4_entry_second_reconcile_symmetry", summary["blockers"])

    def test_failing_test_evidence_blocks(self) -> None:
        paths = self._write_ready_inputs(evidence_overrides={"failed": 2, "exit_code": 1})

        summary, exit_code = build_code_gate_verification_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "failing-evidence"),
            now_fn=lambda: datetime(2026, 6, 9, 17, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("test_evidence_no_failures", summary["blockers"])
        self.assertIn("test_evidence_exit_code_zero", summary["blockers"])

    def test_incomplete_test_file_coverage_blocks(self) -> None:
        paths = self._write_ready_inputs(
            evidence_overrides={"targeted_test_files": [REQUIRED_TEST_FILES[0]]}
        )

        summary, exit_code = build_code_gate_verification_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "incomplete-coverage"),
            now_fn=lambda: datetime(2026, 6, 9, 17, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("test_evidence_covers_required_files", summary["blockers"])

    def test_missing_evidence_blocks(self) -> None:
        paths = self._write_ready_inputs()
        paths["test_evidence"] = self.temp_dir / "does_not_exist.json"

        summary, exit_code = build_code_gate_verification_gate(
            self._args(paths, output_root=self.temp_dir / "out" / "no-evidence"),
            now_fn=lambda: datetime(2026, 6, 9, 17, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("test_evidence_present", summary["blockers"])

    def test_wrong_owner_decision_blocks(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_code_gate_verification_gate(
            self._args(
                paths,
                output_root=self.temp_dir / "out" / "wrong-owner",
                owner_decision="approve_runtime_now",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 17, 25, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_code_gate_verification_recorded", summary["blockers"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_CODE_GATE_VERIFICATION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            test_evidence=str(paths["test_evidence"]),
            delta_runner=str(paths["delta_runner"]),
            core_loop_runner=str(paths["core_loop_runner"]),
            live_risk_controls=str(paths["live_risk_controls"]),
            live_timer_config=str(paths["live_timer_config"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self, *, evidence_overrides: dict | None = None) -> dict[str, Path]:
        delta_runner = self.temp_dir / "delta_runner.py"
        core_loop_runner = self.temp_dir / "core_loop_runner.py"
        live_risk_controls = self.temp_dir / "live_risk_controls.py"
        live_timer_config = self.temp_dir / "live_timer.yaml"
        test_evidence = self.temp_dir / "test_evidence.json"

        delta_runner.write_text(
            "Fail-closed: when no plan-stage source margin gate\n"
            "evaluate_account_snapshot_age_gate(\n"
            '"fetched_at_ms": fetched_at_ms\n',
            encoding="utf-8",
        )
        core_loop_runner.write_text(
            "Prior-submission integrity applies to BOTH stages\n", encoding="utf-8"
        )
        live_risk_controls.write_text(
            "def evaluate_account_snapshot_age_gate(\n", encoding="utf-8"
        )
        live_timer_config.write_text(
            "max_spread_bps: 20  # OUT-OF-SCOPE by owner decision\n", encoding="utf-8"
        )

        evidence = {
            "contract_version": "code_gate_test_evidence.v1",
            "exit_code": 0,
            "passed": 71,
            "failed": 0,
            "errors": 0,
            "targeted_test_files": list(REQUIRED_TEST_FILES),
        }
        evidence.update(evidence_overrides or {})
        test_evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

        return {
            "delta_runner": delta_runner,
            "core_loop_runner": core_loop_runner,
            "live_risk_controls": live_risk_controls,
            "live_timer_config": live_timer_config,
            "test_evidence": test_evidence,
        }


if __name__ == "__main__":
    unittest.main()
