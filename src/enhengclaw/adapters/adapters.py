from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from enhengclaw.core.enums import (
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    SourceFamily,
    TimeHorizon,
)
from enhengclaw.core.signals import Signal


class AdapterValidationError(ValueError):
    pass


@dataclass(slots=True)
class AdapterRequest:
    object_id: str
    object_type: ObjectType
    subject: str
    scope: str
    scenario: str
    venue: str | None = None
    instrument_type: str | None = None
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY


@dataclass(slots=True)
class AdapterBatch:
    adapter_name: str
    source_family: SourceFamily
    source_metadata: dict[str, str] = field(default_factory=dict)
    retrieval_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signals: list[Signal] = field(default_factory=list)


class SignalAdapter(ABC):
    adapter_name: str
    source_family: SourceFamily

    @abstractmethod
    def collect(self, request: AdapterRequest) -> AdapterBatch:
        raise NotImplementedError


def validate_adapter_batch(batch: AdapterBatch, request: AdapterRequest) -> None:
    if not batch.adapter_name or not batch.adapter_name.strip():
        raise AdapterValidationError("adapter batch is missing adapter_name")
    if not isinstance(batch.source_family, SourceFamily):
        raise AdapterValidationError("adapter batch source_family must be a SourceFamily enum")
    if not isinstance(batch.retrieval_timestamp, datetime):
        raise AdapterValidationError("adapter batch retrieval_timestamp must be a datetime")
    if not isinstance(batch.source_metadata, dict):
        raise AdapterValidationError("adapter batch source_metadata must be a dictionary")
    if "provider" not in batch.source_metadata or not str(batch.source_metadata["provider"]).strip():
        raise AdapterValidationError("adapter batch source_metadata must include a non-empty provider")
    if "scenario" not in batch.source_metadata or not str(batch.source_metadata["scenario"]).strip():
        raise AdapterValidationError("adapter batch source_metadata must include a non-empty scenario")
    if "subject_key" not in batch.source_metadata or not str(batch.source_metadata["subject_key"]).strip():
        raise AdapterValidationError("adapter batch source_metadata must include a non-empty subject_key")

    for signal in batch.signals:
        validate_signal(signal, batch, request)


def validate_signal(signal: Signal, batch: AdapterBatch, request: AdapterRequest) -> None:
    if not isinstance(signal, Signal):
        raise AdapterValidationError("adapter output contains a non-Signal item")
    if not signal.signal_id or not signal.signal_id.strip():
        raise AdapterValidationError("signal_id must be non-empty")
    if not isinstance(signal.object_type, ObjectType):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid object_type")
    if signal.object_type != request.object_type:
        raise AdapterValidationError(
            f"signal {signal.signal_id} object_type {signal.object_type!s} does not match adapter request {request.object_type!s}"
        )
    if not signal.subject or not signal.subject.strip():
        raise AdapterValidationError(f"signal {signal.signal_id} subject must be non-empty")
    if signal.subject.strip().upper() != request.subject.strip().upper():
        raise AdapterValidationError(
            f"signal {signal.signal_id} subject '{signal.subject}' does not match adapter request '{request.subject}'"
        )
    if not signal.predicate or not signal.predicate.strip():
        raise AdapterValidationError(f"signal {signal.signal_id} predicate must be non-empty")
    if not signal.value or not signal.value.strip():
        raise AdapterValidationError(f"signal {signal.signal_id} value must be non-empty")
    if not isinstance(signal.claim_type, ClaimType):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid claim_type")
    if not isinstance(signal.direction, Direction):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid direction")
    if not isinstance(signal.source_family, SourceFamily):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid source_family")
    if signal.source_family != batch.source_family:
        raise AdapterValidationError(
            f"signal {signal.signal_id} source_family {signal.source_family!s} does not match adapter batch {batch.source_family!s}"
        )
    if not isinstance(signal.evidence_level, EvidenceLevel):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid evidence_level")
    if not isinstance(signal.time_horizon, TimeHorizon):
        raise AdapterValidationError(f"signal {signal.signal_id} has invalid time_horizon")
    if not signal.scope or not signal.scope.strip():
        raise AdapterValidationError(f"signal {signal.signal_id} scope must be non-empty")
    if not isinstance(signal.confidence_hint, int) or not 0 <= signal.confidence_hint <= 100:
        raise AdapterValidationError(f"signal {signal.signal_id} confidence_hint must be an int between 0 and 100")
    if not isinstance(signal.fresh, bool):
        raise AdapterValidationError(f"signal {signal.signal_id} fresh must be a bool")
    subject_key = str(batch.source_metadata.get("subject_key", "")).strip()
    if subject_key and subject_key not in signal.signal_id:
        raise AdapterValidationError(
            f"signal {signal.signal_id} is missing subject_key namespace '{subject_key}'"
        )


def collect_and_validate_batches(
    adapters: list[SignalAdapter],
    request: AdapterRequest,
) -> list[AdapterBatch]:
    batches: list[AdapterBatch] = []
    for adapter in adapters:
        batch = adapter.collect(request)
        validate_adapter_batch(batch, request)
        batches.append(batch)
    return batches


def merge_adapter_batches(batches: list[AdapterBatch]) -> list[Signal]:
    signals: list[Signal] = []
    for batch in batches:
        signals.extend(batch.signals)
    return signals
