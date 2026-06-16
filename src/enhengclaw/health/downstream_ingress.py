from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TypeVar

from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.health.downstream_gate import (
    DownstreamBlockResult,
    DownstreamBlockedError,
    DownstreamGate,
)
from enhengclaw.domain.identity.subject_key import SubjectKey
from enhengclaw.infra.shared.time import isoformat_utc


T = TypeVar("T")


class DownstreamBlockAuditLog:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "downstream_blocks"
        )
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._lock = threading.Lock()

    def record(self, block_result: DownstreamBlockResult) -> None:
        path = self.root / f"{block_result.blocked_at_utc.strftime('%Y-%m-%d')}.jsonl"
        record = {
            "event_type": "downstream_blocked",
            "subject_key": block_result.subject_key.as_stable_string(),
            "status": block_result.status,
            "reason": block_result.reason,
            "consumer": block_result.consumer,
            "timestamp": isoformat_utc(block_result.blocked_at_utc),
            "latest_ingest_timestamp_utc": None
            if block_result.latest_ingest_timestamp_utc is None
            else isoformat_utc(block_result.latest_ingest_timestamp_utc),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        self.logger.warning(
            "Recorded downstream block for %s consumer=%s status=%s reason=%s",
            block_result.subject_key.as_stable_string(),
            block_result.consumer,
            block_result.status,
            block_result.reason,
        )


class DownstreamIngressGuard:
    def __init__(
        self,
        *,
        monitor: DataHealthMonitor,
        gate: DownstreamGate,
        audit_log: DownstreamBlockAuditLog | None = None,
    ) -> None:
        self.monitor = monitor
        self.gate = gate
        self.audit_log = audit_log

    def guard_downstream_input(
        self,
        *,
        subject_key: SubjectKey,
        consumer: str,
        payload: T,
    ) -> T:
        try:
            self.gate.check(subject_key, consumer=consumer)
        except DownstreamBlockedError as exc:
            if self.audit_log is not None:
                self.audit_log.record(exc.block_result)
            raise
        return payload
