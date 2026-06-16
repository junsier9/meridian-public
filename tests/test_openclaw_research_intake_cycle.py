from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.utils.research_workbench_queues import (
    QUANT_QUEUE,
    STRUCTURAL_QUEUE,
    consumed_archive_root,
    incoming_queue_root,
)
from scripts.openclaw import run_openclaw_research_intake_cycle as intake_cycle


class OpenClawResearchIntakeCycleTests(unittest.TestCase):
    def _write_snapshot(self, root: Path, *, source: str, cycle_id: str, object_id: str, subject: str) -> Path:
        queue_root = incoming_queue_root(workbench_root=root, source=source)
        queue_root.mkdir(parents=True, exist_ok=True)
        snapshot_path = queue_root / f"{cycle_id}.snapshot.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "cycle_id": cycle_id,
                    "cycle_date": "2026-04-20",
                    "object_id": object_id,
                    "subject": subject,
                    "scope": "spot+perp",
                    "strategy_profile": "balanced",
                    "asset_bucket": "mid_cap",
                    "observation": "Observation",
                    "evidence": "Evidence",
                    "risk": "Risk",
                    "next_step": "Next step",
                    "source": source,
                    "published_to_intake": True,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return snapshot_path

    def test_intake_cycle_consumes_one_structural_and_one_quant_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_intake_") as tmpdir:
            workbench_root = Path(tmpdir) / "workbench"
            structural_snapshot = self._write_snapshot(
                workbench_root,
                source=STRUCTURAL_QUEUE,
                cycle_id="structural-cycle-001",
                object_id="eth-structural-20260420",
                subject="ETH",
            )
            quant_snapshot = self._write_snapshot(
                workbench_root,
                source=QUANT_QUEUE,
                cycle_id="quant-cycle-001",
                object_id="eth-quant-20260420",
                subject="ETH",
            )

            def fake_worker(*, snapshot_path: Path, workbench_root: Path, compiler_backend: str, **_: object) -> dict[str, object]:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                cycle_summary_path = workbench_root / payload["object_id"] / "cycles" / payload["cycle_id"] / "cycle_summary.json"
                cycle_summary_path.parent.mkdir(parents=True, exist_ok=True)
                cycle_summary_path.write_text(json.dumps({"status": "success", "cycle_id": payload["cycle_id"]}), encoding="utf-8")
                return {
                    "status": "success",
                    "cycle_summary_path": str(cycle_summary_path),
                }

            with patch.object(intake_cycle, "run_openclaw_research_cycle", side_effect=fake_worker):
                summary = intake_cycle.run_openclaw_research_intake_cycle(
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["processed_snapshot_count"], 2)
            self.assertFalse(structural_snapshot.exists())
            self.assertFalse(quant_snapshot.exists())
            self.assertTrue((consumed_archive_root(workbench_root=workbench_root, source=STRUCTURAL_QUEUE) / structural_snapshot.name).exists())
            self.assertTrue((consumed_archive_root(workbench_root=workbench_root, source=QUANT_QUEUE) / quant_snapshot.name).exists())
            processed_sources = {item["source"] for item in summary["processed"]}
            self.assertEqual(processed_sources, {STRUCTURAL_QUEUE, QUANT_QUEUE})
            dashboard_path = workbench_root / "operations" / "queue_dashboard" / "queue_dashboard.json"
            self.assertTrue(dashboard_path.exists())
            dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
            self.assertEqual(dashboard["intake_status"]["latest_run"]["processed_snapshot_count"], 2)
            self.assertEqual(dashboard["intake_status"]["recent_processed_by_source"][STRUCTURAL_QUEUE], 1)
            self.assertEqual(dashboard["intake_status"]["recent_processed_by_source"][QUANT_QUEUE], 1)


if __name__ == "__main__":
    unittest.main()
