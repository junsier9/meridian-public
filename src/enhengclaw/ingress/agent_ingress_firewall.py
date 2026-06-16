from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from enhengclaw.core.signals import Signal
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer, QuarantineRecord
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog, ReplayableInputRecord
from enhengclaw.ingress.schema_validator import AgentIngressContext, AgentSchemaValidator, SchemaValidationError


class AgentIngressValidationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        replay_records: list[ReplayableInputRecord],
        quarantine_records: list[QuarantineRecord],
    ) -> None:
        super().__init__(message)
        self.replay_records = replay_records
        self.quarantine_records = quarantine_records


@dataclass(frozen=True, slots=True)
class AgentIngressResult:
    signals: list[Signal]
    replay_records: list[ReplayableInputRecord]
    quarantine_records: list[QuarantineRecord]


class AgentIngressFirewall:
    def __init__(
        self,
        *,
        schema_validator: AgentSchemaValidator | None = None,
        quarantine_buffer: QuarantineBuffer | None = None,
        replayable_input_log: ReplayableInputLog | None = None,
    ) -> None:
        self.schema_validator = schema_validator or AgentSchemaValidator()
        self.quarantine_buffer = quarantine_buffer or QuarantineBuffer()
        self.replayable_input_log = replayable_input_log or ReplayableInputLog()

    def intake(
        self,
        *,
        context: AgentIngressContext,
        payloads: list[Mapping[str, Any] | Any],
    ) -> AgentIngressResult:
        if not payloads:
            raise ValueError("agent ingress requires at least one payload")

        signals: list[Signal] = []
        replay_records: list[ReplayableInputRecord] = []
        quarantine_records: list[QuarantineRecord] = []

        for index, payload in enumerate(payloads, start=1):
            input_id = self._input_id(payload, index=index)
            try:
                validated = self.schema_validator.validate(payload, context=context)
            except SchemaValidationError as exc:
                replay_records.append(
                    self.replayable_input_log.write(
                        context=context,
                        input_id=input_id,
                        payload=payload,
                        verdict="quarantined",
                        reason=str(exc),
                    )
                )
                quarantine_records.append(
                    self.quarantine_buffer.write(
                        context=context,
                        input_id=input_id,
                        payload=payload,
                        reason=str(exc),
                    )
                )
                continue

            replay_records.append(
                self.replayable_input_log.write(
                    context=context,
                    input_id=validated.input_id,
                    payload=payload,
                    verdict="accepted",
                )
            )
            signals.append(
                Signal(
                    signal_id=f"agent_ingress:{validated.subject_key.as_path_fragment()}:{validated.input_id}",
                    object_type=context.object_type,
                    subject=validated.subject,
                    predicate=validated.predicate,
                    value=validated.value,
                    claim_type=validated.claim_type,
                    direction=validated.direction,
                    source_family=validated.source_family,
                    evidence_level=validated.evidence_level,
                    confidence_hint=validated.confidence_hint,
                    scope=validated.scope,
                    time_horizon=validated.time_horizon,
                )
            )

        if quarantine_records:
            raise AgentIngressValidationError(
                f"agent ingress rejected {len(quarantine_records)} payload(s); all payloads were blocked from runtime",
                replay_records=replay_records,
                quarantine_records=quarantine_records,
            )
        return AgentIngressResult(
            signals=signals,
            replay_records=replay_records,
            quarantine_records=quarantine_records,
        )

    def _input_id(self, payload: Any, *, index: int) -> str:
        if isinstance(payload, Mapping):
            raw = payload.get("input_id")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        return f"payload_{index}"
