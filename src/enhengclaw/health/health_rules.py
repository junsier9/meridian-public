from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from enhengclaw.health.data_health_monitor import DataHealthState
from enhengclaw.providers.shadow_common import utc_now


@dataclass(frozen=True, slots=True)
class HealthDecision:
    action: str
    status: str
    reason: str


class HealthRules:
    def __init__(self, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self._now_fn = now_fn or utc_now

    def evaluate(self, state: DataHealthState) -> HealthDecision:
        if state.replay_write_failure:
            return HealthDecision(
                action="block_downstream",
                status="blocked",
                reason=state.replay_write_failure_reason or "replay write failure",
            )

        if state.contamination:
            return HealthDecision(
                action="block_downstream",
                status="blocked",
                reason=state.contamination_reason or "contamination detected",
            )

        if state.latest_ingest_timestamp_utc is None:
            return HealthDecision(
                action="block_downstream",
                status="blocked",
                reason="no ingest observed yet",
            )

        latest_ingest = _ensure_utc_datetime(state.latest_ingest_timestamp_utc)
        now = _ensure_utc_datetime(self._now_fn())
        ingest_age_seconds = max(0.0, (now - latest_ingest).total_seconds())
        source_age_seconds = _source_age_seconds(state, now)

        if state.subject_key.venue == "binance":
            if state.last_gap_seconds > 900.0:
                return HealthDecision(
                    action="block_downstream",
                    status="blocked",
                    reason=(
                        "observed recent ingest gap "
                        f"{_format_seconds(state.last_gap_seconds)} exceeds 900s block threshold"
                    ),
                )
            if source_age_seconds is not None and source_age_seconds > 300.0:
                return HealthDecision(
                    action="block_downstream",
                    status="stale",
                    reason=(
                        "latest source age "
                        f"{_format_seconds(source_age_seconds)} exceeds 300s stale threshold"
                    ),
                )
            if ingest_age_seconds > 300.0:
                return HealthDecision(
                    action="block_downstream",
                    status="stale",
                    reason=(
                        "latest ingest age "
                        f"{_format_seconds(ingest_age_seconds)} exceeds 300s stale threshold"
                    ),
                )
            return HealthDecision(
                action="allow_downstream",
                status="healthy",
                reason=(
                    "latest ingest age "
                    f"{_format_seconds(ingest_age_seconds)} within 300s Binance threshold"
                ),
            )

        if state.subject_key.venue == "alchemy":
            if source_age_seconds is not None and source_age_seconds > 900.0:
                return HealthDecision(
                    action="block_downstream",
                    status="stale",
                    reason=(
                        "latest source age "
                        f"{_format_seconds(source_age_seconds)} exceeds 900s stale threshold"
                    ),
                )
            if ingest_age_seconds > 900.0:
                return HealthDecision(
                    action="block_downstream",
                    status="stale",
                    reason=(
                        "latest ingest age "
                        f"{_format_seconds(ingest_age_seconds)} exceeds 900s stale threshold"
                    ),
                )
            return HealthDecision(
                action="allow_downstream",
                status="healthy",
                reason=(
                    "latest ingest age "
                    f"{_format_seconds(ingest_age_seconds)} within 900s Alchemy threshold"
                ),
            )

        if source_age_seconds is not None and source_age_seconds > 900.0:
            return HealthDecision(
                action="block_downstream",
                status="stale",
                reason=(
                    "latest source age "
                    f"{_format_seconds(source_age_seconds)} exceeds default 900s stale threshold"
                ),
            )
        if ingest_age_seconds > 900.0:
            return HealthDecision(
                action="block_downstream",
                status="stale",
                reason=(
                    "latest ingest age "
                    f"{_format_seconds(ingest_age_seconds)} exceeds default 900s stale threshold"
                ),
            )
        return HealthDecision(
            action="allow_downstream",
            status="healthy",
            reason=(
                "latest ingest age "
                f"{_format_seconds(ingest_age_seconds)} within default 900s threshold"
            ),
        )


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _source_age_seconds(state: DataHealthState, now: datetime) -> float | None:
    if state.latest_source_timestamp_utc is None:
        return None
    latest_source = _ensure_utc_datetime(state.latest_source_timestamp_utc)
    return max(0.0, (now - latest_source).total_seconds())


def _format_seconds(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}s"
    return f"{value:.1f}s"
