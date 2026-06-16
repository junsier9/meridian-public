from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.health.health_event_log import HealthEventLog
from enhengclaw.health.health_rules import HealthRules
from enhengclaw.providers.shadow_common import utc_now
from enhengclaw.utils.subject_keys import SubjectKey


@dataclass(frozen=True, slots=True)
class DownstreamBlockResult:
    subject_key: SubjectKey
    status: str
    reason: str
    blocked_at_utc: datetime
    latest_ingest_timestamp_utc: datetime | None
    consumer: str


class DownstreamBlockedError(RuntimeError):
    def __init__(self, block_result: DownstreamBlockResult) -> None:
        self.block_result = block_result
        self.subject_key = block_result.subject_key
        self.status = block_result.status
        self.reason = block_result.reason
        self.blocked_at_utc = block_result.blocked_at_utc
        self.latest_ingest_timestamp_utc = block_result.latest_ingest_timestamp_utc
        self.consumer = block_result.consumer
        super().__init__(
            "downstream blocked for "
            f"{self.subject_key.as_stable_string()} "
            f"[{self.status}] consumer={self.consumer}: {self.reason}"
        )


class DownstreamGate:
    def __init__(
        self,
        *,
        monitor: DataHealthMonitor,
        rules: HealthRules,
        event_log: HealthEventLog | None = None,
    ) -> None:
        self.monitor = monitor
        self.rules = rules
        self.event_log = event_log

    def check(self, subject_key: SubjectKey, *, consumer: str = "unknown") -> None:
        state = self.monitor.get_state(subject_key)
        decision = self.rules.evaluate(state)
        if self.event_log is not None:
            self.event_log.record(subject_key=subject_key, decision=decision)
        if decision.action == "block_downstream":
            raise DownstreamBlockedError(
                DownstreamBlockResult(
                    subject_key=subject_key,
                    status=decision.status,
                    reason=decision.reason,
                    blocked_at_utc=utc_now(),
                    latest_ingest_timestamp_utc=state.latest_ingest_timestamp_utc,
                    consumer=consumer,
                )
            )
