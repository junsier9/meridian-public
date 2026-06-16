from __future__ import annotations

import asyncio
import json
import logging
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
from enhengclaw.health.health_event_log import HealthEventLog
from enhengclaw.health.health_rules import HealthRules
from enhengclaw.ingress.live_replay_writer import LiveReplayWriter
from enhengclaw.ingress.shadow_schema import SHADOW_SCHEMA_VERSION, ValidatedShadowEvent
from enhengclaw.orchestration.ingestion_worker import health_check_loop
from enhengclaw.utils.subject_keys import SubjectKey


class _MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, *, minutes: int = 0, seconds: int = 0) -> None:
        self.now += timedelta(minutes=minutes, seconds=seconds)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class DataHealthGateTests(unittest.TestCase):
    def test_recent_ingest_allows_and_ten_minutes_without_data_blocks_via_health_loop(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as health_dir:
            monitor = DataHealthMonitor()
            rules = HealthRules(now_fn=lambda: clock.now)
            event_log = HealthEventLog(health_dir)
            gate = DownstreamGate(
                monitor=monitor,
                rules=rules,
                event_log=event_log,
            )
            writer = LiveReplayWriter(replay_dir, health_monitor=monitor)
            event = ValidatedShadowEvent(
                subject_key=subject_key,
                provider_id="binance.spot.ws",
                event_type="trade",
                source_timestamp="2026-04-09T00:00:00.000Z",
                raw_payload={"stream": "btcusdt@trade"},
                schema_version=SHADOW_SCHEMA_VERSION,
                event_id="sha256:test-health",
            )

            with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: clock.now):
                writer.write(event=event)

            with patch("enhengclaw.health.health_event_log.utc_now", new=lambda: clock.now):
                gate.check(subject_key)

            clock.advance(minutes=10)
            stop_event = asyncio.Event()

            async def _stop_after_one_interval(
                loop_stop_event: asyncio.Event,
                delay_seconds: float,
            ) -> None:
                self.assertEqual(delay_seconds, 30.0)
                loop_stop_event.set()

            loop_logger = logging.getLogger("test_health_check_loop")
            with patch(
                "enhengclaw.orchestration.ingestion_worker.sleep_or_stop",
                new=_stop_after_one_interval,
            ):
                with patch("enhengclaw.health.health_event_log.utc_now", new=lambda: clock.now):
                    with self.assertLogs("test_health_check_loop", level="WARNING") as captured_logs:
                        asyncio.run(
                            health_check_loop(
                                stop_event,
                                monitor=monitor,
                                gate=gate,
                                logger=loop_logger,
                            )
                        )

            self.assertTrue(
                any(
                    "Health check blocked downstream for BTCUSDT.binance.spot" in message
                    and "latest source age 600s exceeds 300s stale threshold" in message
                    for message in captured_logs.output
                )
            )

            rows = _read_jsonl(Path(health_dir) / "2026-04-09.jsonl")
            self.assertEqual(
                rows,
                [
                    {
                        "from_status": "unknown",
                        "reason": "latest ingest age 0s within 300s Binance threshold",
                        "subject_key": "BTCUSDT.binance.spot",
                        "timestamp": "2026-04-09T00:00:00.000Z",
                        "to_status": "healthy",
                    },
                    {
                        "from_status": "healthy",
                        "reason": "latest source age 600s exceeds 300s stale threshold",
                        "subject_key": "BTCUSDT.binance.spot",
                        "timestamp": "2026-04-09T00:10:00.000Z",
                        "to_status": "stale",
                    },
                ],
            )

    def test_recent_gap_replaces_previous_large_gap_after_recovery(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 1, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as health_dir:
            monitor = DataHealthMonitor()
            rules = HealthRules(now_fn=lambda: clock.now)
            event_log = HealthEventLog(health_dir)
            gate = DownstreamGate(
                monitor=monitor,
                rules=rules,
                event_log=event_log,
            )
            writer = LiveReplayWriter(replay_dir, health_monitor=monitor)

            def _event(event_id: str) -> ValidatedShadowEvent:
                return ValidatedShadowEvent(
                    subject_key=subject_key,
                    provider_id="binance.spot.ws",
                    event_type="trade",
                    source_timestamp=clock.now.isoformat().replace("+00:00", "Z"),
                    raw_payload={"stream": "btcusdt@trade", "event_id": event_id},
                    schema_version=SHADOW_SCHEMA_VERSION,
                    event_id=event_id,
                )

            with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: clock.now):
                writer.write(event=_event("sha256:gap-1"))

            clock.advance(seconds=4000)
            with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: clock.now):
                writer.write(event=_event("sha256:gap-2"))

            blocked_state = monitor.get_state(subject_key)
            self.assertEqual(blocked_state.last_gap_seconds, 4000.0)
            with patch("enhengclaw.health.health_event_log.utc_now", new=lambda: clock.now):
                with self.assertRaises(DownstreamBlockedError):
                    gate.check(subject_key)

            clock.advance(seconds=10)
            with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: clock.now):
                writer.write(event=_event("sha256:gap-3"))

            recovered_state = monitor.get_state(subject_key)
            self.assertEqual(recovered_state.last_gap_seconds, 10.0)
            with patch("enhengclaw.health.health_event_log.utc_now", new=lambda: clock.now):
                gate.check(subject_key)

    def test_old_source_timestamp_blocks_even_when_ingest_is_recent(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        clock = _MutableClock(datetime(2026, 4, 9, 2, 0, 0, tzinfo=timezone.utc))

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as health_dir:
            monitor = DataHealthMonitor()
            rules = HealthRules(now_fn=lambda: clock.now)
            event_log = HealthEventLog(health_dir)
            gate = DownstreamGate(
                monitor=monitor,
                rules=rules,
                event_log=event_log,
            )
            writer = LiveReplayWriter(replay_dir, health_monitor=monitor)
            event = ValidatedShadowEvent(
                subject_key=subject_key,
                provider_id="binance.spot.ws",
                event_type="trade",
                source_timestamp="2026-04-09T01:30:00.000Z",
                raw_payload={"stream": "btcusdt@trade"},
                schema_version=SHADOW_SCHEMA_VERSION,
                event_id="sha256:source-lag",
            )

            with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: clock.now):
                writer.write(event=event)

            with patch("enhengclaw.health.health_event_log.utc_now", new=lambda: clock.now):
                with self.assertRaises(DownstreamBlockedError):
                    gate.check(subject_key)

            rows = _read_jsonl(Path(health_dir) / "2026-04-09.jsonl")
            self.assertEqual(
                rows,
                [
                    {
                        "from_status": "unknown",
                        "reason": "latest source age 1800s exceeds 300s stale threshold",
                        "subject_key": "BTCUSDT.binance.spot",
                        "timestamp": "2026-04-09T02:00:00.000Z",
                        "to_status": "stale",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
