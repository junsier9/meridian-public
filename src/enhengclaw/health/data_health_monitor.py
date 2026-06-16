from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from enhengclaw.domain.identity.subject_key import SubjectKey


@dataclass(frozen=True, slots=True)
class DataHealthState:
    subject_key: SubjectKey
    latest_ingest_timestamp_utc: datetime | None = None
    last_gap_seconds: float = 0.0
    latest_source_timestamp_utc: datetime | None = None
    contamination: bool = False
    contamination_reason: str | None = None
    replay_write_failure: bool = False
    replay_write_failure_reason: str | None = None


class DataHealthMonitor:
    def __init__(self) -> None:
        self._states: dict[str, DataHealthState] = {}
        self._lock = threading.Lock()

    def on_ingest_event(
        self,
        subject_key: SubjectKey,
        ingest_ts: datetime,
        source_ts: object | None = None,
    ) -> DataHealthState:
        ingest_timestamp_utc = _ensure_utc_datetime(ingest_ts)
        source_timestamp_utc = _coerce_optional_utc_datetime(source_ts)
        key = subject_key.as_stable_string()
        with self._lock:
            current = self._states.get(key, DataHealthState(subject_key=subject_key))
            gap_seconds = 0.0
            if current.latest_ingest_timestamp_utc is not None:
                gap_seconds = max(
                    0.0,
                    (ingest_timestamp_utc - current.latest_ingest_timestamp_utc).total_seconds(),
                )
            if (
                current.latest_source_timestamp_utc is not None
                and source_timestamp_utc is not None
            ):
                source_timestamp_utc = max(
                    current.latest_source_timestamp_utc,
                    source_timestamp_utc,
                )
            updated = replace(
                current,
                latest_ingest_timestamp_utc=ingest_timestamp_utc,
                last_gap_seconds=gap_seconds,
                latest_source_timestamp_utc=source_timestamp_utc,
            )
            self._states[key] = updated
            return updated

    def note_contamination(
        self,
        subject_key: SubjectKey,
        reason: str,
    ) -> DataHealthState:
        key = subject_key.as_stable_string()
        with self._lock:
            current = self._states.get(key, DataHealthState(subject_key=subject_key))
            updated = replace(
                current,
                contamination=True,
                contamination_reason=reason.strip() or "contamination detected",
            )
            self._states[key] = updated
            return updated

    def note_replay_write_failure(
        self,
        subject_key: SubjectKey,
        reason: str,
    ) -> DataHealthState:
        key = subject_key.as_stable_string()
        with self._lock:
            current = self._states.get(key, DataHealthState(subject_key=subject_key))
            updated = replace(
                current,
                replay_write_failure=True,
                replay_write_failure_reason=reason.strip() or "replay write failure",
            )
            self._states[key] = updated
            return updated

    def get_state(self, subject_key: SubjectKey) -> DataHealthState:
        key = subject_key.as_stable_string()
        with self._lock:
            current = self._states.get(key)
            if current is None:
                return DataHealthState(subject_key=subject_key)
            return replace(current)

    def get_all_subject_keys(self) -> list[SubjectKey]:
        with self._lock:
            return [
                state.subject_key
                for _, state in sorted(self._states.items(), key=lambda item: item[0])
            ]


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_optional_utc_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc_datetime(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return _ensure_utc_datetime(parsed)
    return None
