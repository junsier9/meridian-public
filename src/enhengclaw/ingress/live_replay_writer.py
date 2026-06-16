from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.ingress.shadow_schema import ValidatedShadowEvent
from enhengclaw.providers.shadow_common import isoformat_utc, utc_now
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_hourly_jsonl_path


@dataclass(frozen=True, slots=True)
class LiveReplayWriteResult:
    path: str
    event_id: str


@dataclass(frozen=True, slots=True)
class QuarantineWriteResult:
    path: str
    reason: str


class _JsonlFileAppender:
    def __init__(self) -> None:
        self._locks: dict[Path, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def append(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self._lock_for(path):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")

    def _lock_for(self, path: Path) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(path)
            if lock is None:
                lock = threading.Lock()
                self._locks[path] = lock
            return lock


class LiveReplayWriter:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        health_monitor: DataHealthMonitor | None = None,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "live_replay"
        )
        self._appender = _JsonlFileAppender()
        self.health_monitor = health_monitor

    def write(self, *, event: ValidatedShadowEvent) -> LiveReplayWriteResult:
        ingest_at = utc_now()
        path = subject_key_hourly_jsonl_path(self.root, event.subject_key, ingest_at)
        try:
            self._appender.append(
                path,
                {
                    "subject_key": event.subject_key.as_stable_string(),
                    "provider_id": event.provider_id,
                    "event_type": event.event_type,
                    "ingest_timestamp_utc": isoformat_utc(ingest_at),
                    "source_timestamp": event.source_timestamp,
                    "raw_payload": event.raw_payload,
                    "schema_version": event.schema_version,
                    "event_id": event.event_id,
                },
            )
        except Exception as exc:
            if self.health_monitor is not None:
                self.health_monitor.note_replay_write_failure(
                    event.subject_key,
                    f"live replay write failed: {exc}",
                )
            raise
        if self.health_monitor is not None:
            self.health_monitor.on_ingest_event(
                event.subject_key,
                ingest_at,
                source_ts=event.source_timestamp,
            )
        return LiveReplayWriteResult(path=str(path), event_id=event.event_id)


class LiveQuarantineWriter:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "live_quarantine"
        )
        self._appender = _JsonlFileAppender()

    def write(
        self,
        *,
        subject_key: SubjectKey,
        provider_id: str,
        event_type: str,
        raw_payload: Any,
        reason: str,
        schema_version: str,
    ) -> QuarantineWriteResult:
        ingest_at = utc_now()
        path = subject_key_hourly_jsonl_path(self.root, subject_key, ingest_at)
        self._appender.append(
            path,
            {
                "subject_key": subject_key.as_stable_string(),
                "provider_id": provider_id,
                "event_type": event_type,
                "ingest_timestamp_utc": isoformat_utc(ingest_at),
                "reason": reason,
                "schema_version": schema_version,
                "raw_payload": raw_payload,
            },
        )
        return QuarantineWriteResult(path=str(path), reason=reason)
