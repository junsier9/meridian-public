from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.refactor_freeze.common import write_json
from scripts.refactor_freeze.diff_snapshots import build_diff_report
from scripts.refactor_freeze.generation import generate_snapshots


class RefactorFreezeToolchainTests(unittest.TestCase):
    def test_diff_report_triggers_stopline_for_unapproved_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            freeze_root = Path(tmpdir)
            baseline_root = freeze_root / "baselines" / "phase_01"
            candidate_root = freeze_root / "candidates" / "phase_01"
            baseline_root.mkdir(parents=True)
            candidate_root.mkdir(parents=True)

            baseline = {
                "snapshot_meta": {
                    "snapshot_type": "runtime_decision",
                    "case_id": "case_a",
                    "phase": "phase_01",
                    "generated_at_utc": "2026-04-09T00:00:00Z",
                    "source_commit_or_worktree_ref": "abc",
                    "generator_version": "refactor_freeze.v1",
                },
                "snapshot": {"decision": "publish"},
            }
            candidate = {
                **baseline,
                "snapshot": {"decision": "monitoring"},
            }
            write_json(baseline_root / "runtime_decision.case_a.snapshot.json", baseline)
            write_json(candidate_root / "runtime_decision.case_a.snapshot.json", candidate)

            report = build_diff_report(phase="phase_01", freeze_root=freeze_root)
            self.assertTrue(report["summary"]["stopline_triggered"])
            self.assertFalse(report["summary"]["can_continue"])
            self.assertEqual(report["summary"]["unapproved_diff_count"], 1)
            self.assertEqual(report["snapshots"][0]["diffs"][0]["field"], "$.decision")

    def test_missing_snapshot_triggers_stopline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            freeze_root = Path(tmpdir)
            baseline_root = freeze_root / "baselines" / "phase_01"
            baseline_root.mkdir(parents=True)
            write_json(
                baseline_root / "runtime_decision.case_a.snapshot.json",
                {
                    "snapshot_meta": {
                        "snapshot_type": "runtime_decision",
                        "case_id": "case_a",
                        "phase": "phase_01",
                        "generated_at_utc": "2026-04-09T00:00:00Z",
                        "source_commit_or_worktree_ref": "abc",
                        "generator_version": "refactor_freeze.v1",
                    },
                    "snapshot": {"decision": "publish"},
                },
            )

            report = build_diff_report(phase="phase_01", freeze_root=freeze_root)
            self.assertTrue(report["summary"]["stopline_triggered"])
            self.assertEqual(report["summary"]["missing_snapshot_count"], 1)
            self.assertEqual(report["snapshots"][0]["diffs"][0]["field"], "$.__presence__")

    def test_generation_creates_manifest_and_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            freeze_root = Path(tmpdir)
            result = generate_snapshots(
                kind="baselines",
                phase="phase_01",
                snapshot_types={"runtime_decision", "health_decision"},
                freeze_root=freeze_root,
            )
            self.assertGreaterEqual(result["snapshot_count"], 2)
            self.assertTrue(Path(result["manifest_path"]).exists())
            generated = list((freeze_root / "baselines" / "phase_01").glob("*.snapshot.json"))
            self.assertTrue(generated)


if __name__ == "__main__":
    unittest.main()
