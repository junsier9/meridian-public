from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.health.downstream_gate import DownstreamBlockedError, DownstreamGate
from enhengclaw.health.downstream_ingress import DownstreamBlockAuditLog, DownstreamIngressGuard
from enhengclaw.health.health_event_log import HealthEventLog
from enhengclaw.health.health_rules import HealthRules
from enhengclaw.utils.subject_keys import SubjectKey


class _MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, *, minutes: int = 0, seconds: int = 0) -> None:
        self.now += timedelta(minutes=minutes, seconds=seconds)


def _read_all_jsonl(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


class DownstreamRuntimeGateTests(unittest.TestCase):
    def _guard(
        self,
        *,
        monitor: DataHealthMonitor,
        clock: _MutableClock,
        artifact_root: Path,
    ) -> DownstreamIngressGuard:
        gate = DownstreamGate(
            monitor=monitor,
            rules=HealthRules(now_fn=lambda: clock.now),
            event_log=HealthEventLog(artifact_root / "health_events"),
        )
        return DownstreamIngressGuard(
            monitor=monitor,
            gate=gate,
            audit_log=DownstreamBlockAuditLog(artifact_root / "downstream_blocks"),
        )

    def test_healthy_subject_passes_runtime_downstream_ingress(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 2, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            monitor = DataHealthMonitor()
            monitor.on_ingest_event(subject_key, clock.now)
            guard = self._guard(monitor=monitor, clock=clock, artifact_root=artifact_root)

            guard.guard_downstream_input(
                subject_key=subject_key,
                consumer="runtime.provider_snapshot.create",
                payload=None,
            )

            self.assertEqual(_read_all_jsonl(artifact_root / "downstream_blocks"), [])

    def test_stale_subject_blocks_runtime_with_structured_error(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 3, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            monitor = DataHealthMonitor()
            monitor.on_ingest_event(subject_key, clock.now)
            guard = self._guard(monitor=monitor, clock=clock, artifact_root=artifact_root)

            clock.advance(minutes=10)
            with patch("enhengclaw.health.downstream_gate.utc_now", new=lambda: clock.now):
                with self.assertRaises(DownstreamBlockedError) as exc_info:
                    guard.guard_downstream_input(
                        subject_key=subject_key,
                        consumer="runtime.provider_snapshot.create",
                        payload=None,
                    )

            error = exc_info.exception
            self.assertEqual(error.status, "stale")
            self.assertEqual(error.consumer, "runtime.provider_snapshot.create")
            self.assertEqual(error.subject_key.as_stable_string(), "BTCUSDT.binance.spot")
            self.assertEqual(error.latest_ingest_timestamp_utc, datetime(2026, 4, 9, 3, 0, 0, tzinfo=timezone.utc))
            self.assertEqual(error.blocked_at_utc, datetime(2026, 4, 9, 3, 10, 0, tzinfo=timezone.utc))
            self.assertIn("latest ingest age 600s exceeds 300s stale threshold", error.reason)

    def test_blocked_subject_writes_downstream_block_audit_log(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 4, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            monitor = DataHealthMonitor()
            monitor.note_contamination(subject_key, "cross-subject contamination detected")
            guard = self._guard(monitor=monitor, clock=clock, artifact_root=artifact_root)

            with patch("enhengclaw.health.downstream_gate.utc_now", new=lambda: clock.now):
                with self.assertRaises(DownstreamBlockedError) as exc_info:
                    guard.guard_downstream_input(
                        subject_key=subject_key,
                        consumer="runtime.provider_snapshot.create",
                        payload=None,
                    )

            self.assertEqual(exc_info.exception.status, "blocked")
            rows = _read_all_jsonl(artifact_root / "downstream_blocks")
            self.assertEqual(
                rows,
                [
                    {
                        "consumer": "runtime.provider_snapshot.create",
                        "event_type": "downstream_blocked",
                        "latest_ingest_timestamp_utc": None,
                        "reason": "cross-subject contamination detected",
                        "status": "blocked",
                        "subject_key": "BTCUSDT.binance.spot",
                        "timestamp": "2026-04-09T04:00:00.000Z",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
