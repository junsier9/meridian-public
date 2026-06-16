from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.utils.research_workbench_queue_dashboard import generate_research_workbench_queue_dashboard
from enhengclaw.utils.research_workbench_queues import LEGACY_QUEUE, QUANT_QUEUE, STRUCTURAL_QUEUE, incoming_queue_root


class ResearchWorkbenchQueueDashboardTests(unittest.TestCase):
    def _write_snapshot(
        self,
        *,
        workbench_root: Path,
        source: str,
        cycle_id: str,
        object_id: str,
        subject: str,
        age_minutes: int,
    ) -> Path:
        queue_root = incoming_queue_root(workbench_root=workbench_root, source=source)
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
        self._set_age(snapshot_path, age_minutes)
        return snapshot_path

    def _write_cycle_summary(self, *, workbench_root: Path, object_id: str, cycle_id: str) -> Path:
        cycle_root = workbench_root / object_id / "cycles" / cycle_id
        cycle_root.mkdir(parents=True, exist_ok=True)
        summary_path = cycle_root / "cycle_summary.json"
        summary_path.write_text(json.dumps({"status": "success", "cycle_id": cycle_id}), encoding="utf-8")
        return summary_path

    def _write_scan_summary(
        self,
        *,
        workbench_root: Path,
        generated_at: datetime | None = None,
        snapshot_path: Path | None = None,
        cycle_id: str = "structural-cycle-001",
        object_id: str = "eth-structural-20260420",
    ) -> Path:
        scan_root = workbench_root / "_scan_runs" / "scan-001"
        scan_root.mkdir(parents=True, exist_ok=True)
        summary_path = scan_root / "scan_summary.json"
        payload = {
            "status": "success",
            "scan_id": "scan-001",
            "scan_date": "2026-04-20",
            "generated_at_utc": (generated_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
            "incoming_root": str((snapshot_path.parent if snapshot_path is not None else incoming_queue_root(workbench_root=workbench_root, source=STRUCTURAL_QUEUE)).resolve()),
            "source": STRUCTURAL_QUEUE,
            "selected_snapshot_count": 1,
            "selected_snapshots": [
                {
                    "cycle_id": cycle_id,
                    "object_id": object_id,
                    "subject": "ETH",
                    "snapshot_path": None if snapshot_path is None else str(snapshot_path.resolve()),
                }
            ],
        }
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return summary_path

    def _write_bridge_summary(
        self,
        *,
        quant_artifacts_root: Path,
        workbench_root: Path,
        published_snapshot_path: Path | None,
        generated_at: datetime | None = None,
        published_to_intake: bool = True,
    ) -> Path:
        export_root = quant_artifacts_root / "bridge_exports" / "2026-04-20"
        export_root.mkdir(parents=True, exist_ok=True)
        published_archive = export_root / "quant-cycle-001.snapshot.json"
        staged_archive = export_root / "quant-cycle-002.snapshot.json"
        published_archive.write_text("{}", encoding="utf-8")
        staged_archive.write_text("{}", encoding="utf-8")
        summary_path = export_root / "bridge_summary.json"
        payload = {
            "generated_at_utc": (generated_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
            "as_of": "2026-04-20",
            "queue": QUANT_QUEUE,
            "queue_root": str((published_snapshot_path.parent if published_snapshot_path is not None else incoming_queue_root(workbench_root=workbench_root, source=QUANT_QUEUE)).resolve()),
            "export_root": str(export_root.resolve()),
            "exported_snapshot_count": 2,
            "published_snapshot_count": 1 if published_to_intake else 0,
            "staged_only_snapshot_count": 1 if published_to_intake else 2,
            "exports": [
                {
                    "experiment_id": "exp-001",
                    "queue": QUANT_QUEUE,
                    "subject": "ETH",
                    "object_id": "eth-quant-20260420",
                    "cycle_id": "quant-cycle-001",
                    "source": QUANT_QUEUE,
                    "published_to_intake": published_to_intake,
                    "archive_path": str(published_archive.resolve()),
                    "queue_path": None if published_snapshot_path is None or not published_to_intake else str(published_snapshot_path.resolve()),
                }
            ],
            "suppressed_exports": [
                {
                    "experiment_id": "exp-002",
                    "queue": QUANT_QUEUE,
                    "subject": "SUI",
                    "object_id": "sui-quant-20260420",
                    "cycle_id": "quant-cycle-002",
                    "source": QUANT_QUEUE,
                    "published_to_intake": False,
                    "archive_path": str(staged_archive.resolve()),
                    "queue_path": None,
                }
            ] if published_to_intake else [
                {
                    "experiment_id": "exp-001",
                    "queue": QUANT_QUEUE,
                    "subject": "ETH",
                    "object_id": "eth-quant-20260420",
                    "cycle_id": "quant-cycle-001",
                    "source": QUANT_QUEUE,
                    "published_to_intake": False,
                    "archive_path": str(published_archive.resolve()),
                    "queue_path": None,
                },
                {
                    "experiment_id": "exp-002",
                    "queue": QUANT_QUEUE,
                    "subject": "SUI",
                    "object_id": "sui-quant-20260420",
                    "cycle_id": "quant-cycle-002",
                    "source": QUANT_QUEUE,
                    "published_to_intake": False,
                    "archive_path": str(staged_archive.resolve()),
                    "queue_path": None,
                },
            ],
        }
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return summary_path

    def _write_intake_summary(
        self,
        *,
        workbench_root: Path,
        run_id: str,
        generated_at: datetime,
        processed_sources: list[str],
    ) -> Path:
        run_root = workbench_root / "_intake_runs" / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        summary_path = run_root / "intake_summary.json"
        payload = {
            "status": "success",
            "run_id": run_id,
            "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
            "processed_snapshot_count": len(processed_sources),
            "processed": [
                {
                    "source": source,
                    "cycle_id": f"{source}-cycle-{index}",
                    "object_id": f"{source}-object-{index}",
                    "status": "success",
                }
                for index, source in enumerate(processed_sources, start=1)
            ],
        }
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return summary_path

    def _set_age(self, path: Path, age_minutes: int) -> None:
        timestamp = (datetime.now(UTC) - timedelta(minutes=age_minutes)).timestamp()
        os.utime(path, (timestamp, timestamp))

    def test_dashboard_reports_queue_producer_and_intake_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="research_queue_dashboard_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "artifacts" / "research_workbench"
            quant_artifacts_root = root / "artifacts" / "quant_research"
            workbench_root.mkdir(parents=True, exist_ok=True)
            quant_artifacts_root.mkdir(parents=True, exist_ok=True)

            incoming_queue_root(workbench_root=workbench_root, source=LEGACY_QUEUE).mkdir(parents=True, exist_ok=True)
            structural_snapshot = self._write_snapshot(
                workbench_root=workbench_root,
                source=STRUCTURAL_QUEUE,
                cycle_id="structural-cycle-001",
                object_id="eth-structural-20260420",
                subject="ETH",
                age_minutes=25,
            )
            quant_snapshot = self._write_snapshot(
                workbench_root=workbench_root,
                source=QUANT_QUEUE,
                cycle_id="quant-cycle-001",
                object_id="eth-quant-20260420",
                subject="ETH",
                age_minutes=10,
            )
            self._write_scan_summary(workbench_root=workbench_root, snapshot_path=structural_snapshot)
            self._write_bridge_summary(
                quant_artifacts_root=quant_artifacts_root,
                workbench_root=workbench_root,
                published_snapshot_path=quant_snapshot,
            )
            self._write_intake_summary(
                workbench_root=workbench_root,
                run_id="20260420T120000Z",
                generated_at=datetime.now(UTC) - timedelta(minutes=5),
                processed_sources=[STRUCTURAL_QUEUE, QUANT_QUEUE],
            )

            dashboard = generate_research_workbench_queue_dashboard(
                workbench_root=workbench_root,
                quant_artifacts_root=quant_artifacts_root,
                window_hours=24,
            )

            self.assertTrue(Path(dashboard["queue_dashboard_json_path"]).exists())
            self.assertTrue(Path(dashboard["queue_dashboard_markdown_path"]).exists())
            self.assertEqual(dashboard["queue_status"][STRUCTURAL_QUEUE]["pending_snapshot_count"], 1)
            self.assertEqual(dashboard["queue_status"][QUANT_QUEUE]["pending_snapshot_count"], 1)
            self.assertEqual(dashboard["queue_status"][LEGACY_QUEUE]["pending_snapshot_count"], 0)
            self.assertEqual(dashboard["producer_status"]["structural"]["scan_id"], "scan-001")
            self.assertEqual(dashboard["producer_status"]["quant"]["published_snapshot_count"], 1)
            self.assertEqual(dashboard["producer_status"]["quant"]["staged_only_snapshot_count"], 1)
            self.assertEqual(dashboard["intake_status"]["recent_processed_by_source"][STRUCTURAL_QUEUE], 1)
            self.assertEqual(dashboard["intake_status"]["recent_processed_by_source"][QUANT_QUEUE], 1)
            self.assertFalse(any(alert["code"] == "missing_queue_dir" for alert in dashboard["alerts"]))
            markdown = Path(dashboard["queue_dashboard_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("research-only / archive-only", markdown)

    def test_dashboard_flags_missing_new_queues_and_legacy_rollout_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="research_queue_rollout_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "artifacts" / "research_workbench"
            quant_artifacts_root = root / "artifacts" / "quant_research"
            workbench_root.mkdir(parents=True, exist_ok=True)
            quant_artifacts_root.mkdir(parents=True, exist_ok=True)

            for index in range(13):
                self._write_snapshot(
                    workbench_root=workbench_root,
                    source=LEGACY_QUEUE,
                    cycle_id=f"legacy-eth-{index:02d}",
                    object_id=f"eth-object-{index:02d}",
                    subject="ETH",
                    age_minutes=180 if index == 0 else 15,
                )
            for index in range(6):
                self._write_snapshot(
                    workbench_root=workbench_root,
                    source=LEGACY_QUEUE,
                    cycle_id=f"legacy-sui-{index:02d}",
                    object_id=f"sui-object-{index:02d}",
                    subject="SUI",
                    age_minutes=30,
                )
            self._write_intake_summary(
                workbench_root=workbench_root,
                run_id="20260420T110000Z",
                generated_at=datetime.now(UTC) - timedelta(minutes=10),
                processed_sources=[LEGACY_QUEUE, LEGACY_QUEUE],
            )

            dashboard = generate_research_workbench_queue_dashboard(
                workbench_root=workbench_root,
                quant_artifacts_root=quant_artifacts_root,
                window_hours=24,
            )

            self.assertEqual(dashboard["queue_status"][LEGACY_QUEUE]["pending_snapshot_count"], 19)
            self.assertFalse(dashboard["queue_status"][QUANT_QUEUE]["exists"])
            self.assertFalse(dashboard["queue_status"][STRUCTURAL_QUEUE]["exists"])
            top_subjects = dashboard["queue_status"][LEGACY_QUEUE]["top_subjects"]
            self.assertEqual(top_subjects[0], {"subject": "ETH", "count": 13})
            self.assertEqual(top_subjects[1], {"subject": "SUI", "count": 6})
            alert_codes = {alert["code"] for alert in dashboard["alerts"]}
            self.assertIn("missing_queue_dir", alert_codes)
            self.assertIn("legacy_backlog_present", alert_codes)
            self.assertIn("rollout_mismatch", alert_codes)
            self.assertIn("stale_pending", alert_codes)

    def test_dashboard_ignores_missing_or_stale_producers_for_cross_system_warnings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="research_queue_neutral_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "artifacts" / "research_workbench"
            quant_artifacts_root = root / "artifacts" / "quant_research"
            workbench_root.mkdir(parents=True, exist_ok=True)
            quant_artifacts_root.mkdir(parents=True, exist_ok=True)
            incoming_queue_root(workbench_root=workbench_root, source=LEGACY_QUEUE).mkdir(parents=True, exist_ok=True)
            self._write_intake_summary(
                workbench_root=workbench_root,
                run_id="20260420T110000Z",
                generated_at=datetime.now(UTC) - timedelta(minutes=10),
                processed_sources=[LEGACY_QUEUE],
            )

            dashboard = generate_research_workbench_queue_dashboard(
                workbench_root=workbench_root,
                quant_artifacts_root=quant_artifacts_root,
                window_hours=24,
            )

            alert_codes = {alert["code"] for alert in dashboard["alerts"]}
            self.assertNotIn("structural_no_recent_intake", alert_codes)
            self.assertNotIn("quant_no_recent_intake", alert_codes)
            self.assertNotIn("legacy_only_intake", alert_codes)

            self._write_cycle_summary(
                workbench_root=workbench_root,
                object_id="eth-structural-20260420",
                cycle_id="structural-cycle-001",
            )
            self._write_scan_summary(
                workbench_root=workbench_root,
                generated_at=datetime.now(UTC) - timedelta(hours=30),
                snapshot_path=None,
            )
            self._write_bridge_summary(
                quant_artifacts_root=quant_artifacts_root,
                workbench_root=workbench_root,
                published_snapshot_path=None,
                generated_at=datetime.now(UTC) - timedelta(hours=30),
                published_to_intake=False,
            )

            stale_dashboard = generate_research_workbench_queue_dashboard(
                workbench_root=workbench_root,
                quant_artifacts_root=quant_artifacts_root,
                window_hours=24,
            )

            stale_alert_codes = {alert["code"] for alert in stale_dashboard["alerts"]}
            self.assertNotIn("structural_no_recent_intake", stale_alert_codes)
            self.assertNotIn("quant_no_recent_intake", stale_alert_codes)
            self.assertNotIn("legacy_only_intake", stale_alert_codes)

    def test_dashboard_warns_when_recent_producer_output_has_no_recent_intake(self) -> None:
        with tempfile.TemporaryDirectory(prefix="research_queue_recent_producers_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "artifacts" / "research_workbench"
            quant_artifacts_root = root / "artifacts" / "quant_research"
            workbench_root.mkdir(parents=True, exist_ok=True)
            quant_artifacts_root.mkdir(parents=True, exist_ok=True)
            incoming_queue_root(workbench_root=workbench_root, source=LEGACY_QUEUE).mkdir(parents=True, exist_ok=True)
            self._write_cycle_summary(
                workbench_root=workbench_root,
                object_id="eth-structural-20260420",
                cycle_id="structural-cycle-001",
            )
            self._write_scan_summary(
                workbench_root=workbench_root,
                generated_at=datetime.now(UTC) - timedelta(minutes=20),
                snapshot_path=None,
            )
            self._write_bridge_summary(
                quant_artifacts_root=quant_artifacts_root,
                workbench_root=workbench_root,
                published_snapshot_path=None,
                generated_at=datetime.now(UTC) - timedelta(minutes=15),
                published_to_intake=True,
            )
            self._write_intake_summary(
                workbench_root=workbench_root,
                run_id="20260420T120000Z",
                generated_at=datetime.now(UTC) - timedelta(minutes=5),
                processed_sources=[LEGACY_QUEUE],
            )

            dashboard = generate_research_workbench_queue_dashboard(
                workbench_root=workbench_root,
                quant_artifacts_root=quant_artifacts_root,
                window_hours=24,
            )

            alert_codes = {alert["code"] for alert in dashboard["alerts"]}
            self.assertIn("structural_no_recent_intake", alert_codes)
            self.assertIn("quant_no_recent_intake", alert_codes)
            self.assertIn("legacy_only_intake", alert_codes)


if __name__ == "__main__":
    unittest.main()
