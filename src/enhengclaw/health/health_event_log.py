from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from enhengclaw.health.health_rules import HealthDecision
from enhengclaw.infra.shared.time import isoformat_utc, utc_now
from enhengclaw.utils.subject_keys import SubjectKey


class HealthEventLog:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "health_events"
        )
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._last_status_by_subject: dict[str, str] = {}
        self._lock = threading.Lock()

    def record(
        self,
        *,
        subject_key: SubjectKey,
        decision: HealthDecision,
        timestamp: datetime | None = None,
    ) -> None:
        event_timestamp = _ensure_utc_datetime(timestamp or utc_now())
        subject_name = subject_key.as_stable_string()

        with self._lock:
            previous_status = self._last_status_by_subject.get(subject_name)
            if previous_status == decision.status:
                return
            self._last_status_by_subject[subject_name] = decision.status
            path = self.root / f"{event_timestamp.strftime('%Y-%m-%d')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "subject_key": subject_name,
                "from_status": previous_status or "unknown",
                "to_status": decision.status,
                "reason": decision.reason,
                "timestamp": isoformat_utc(event_timestamp),
            }
            line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")

        self.logger.info(
            "Health status transition for %s: %s -> %s (%s)",
            subject_name,
            previous_status or "unknown",
            decision.status,
            decision.reason,
        )


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
