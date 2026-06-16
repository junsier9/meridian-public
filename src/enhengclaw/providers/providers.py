from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from enhengclaw.core.execution_control import (
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    RUNTIME_WORKER_ENTRYPOINT,
    require_active_worker_lease,
)
from enhengclaw.core.enums import ObjectType, TimeHorizon


@dataclass(slots=True)
class ProviderRequest:
    object_id: str
    object_type: ObjectType
    subject: str
    scope: str
    scenario: str
    venue: str | None = None
    instrument_type: str | None = None
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY


@dataclass(slots=True)
class ProviderMetadata:
    provider_name: str
    retrieved_at: datetime
    scenario: str
    raw_record_count: int


@dataclass(slots=True)
class CEXProviderPayload:
    metadata: ProviderMetadata
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class OnchainProviderPayload:
    metadata: ProviderMetadata
    raw_payload: list[dict[str, Any]]


@dataclass(slots=True)
class SafetyProviderPayload:
    metadata: ProviderMetadata
    raw_payload: list[dict[str, Any]]


class PermitEnforcedProvider:
    def _require_fetch_execution(self, request: ProviderRequest, *, operation: str) -> None:
        require_active_worker_lease(
            operation=operation,
            required_capabilities={CAP_PROVIDER_FETCH},
            requested_scope=request.scope,
            allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
        )

    def _require_transport_execution(self, *, operation: str, requested_scope: str | None = None) -> None:
        require_active_worker_lease(
            operation=operation,
            required_capabilities={CAP_PROVIDER_TRANSPORT},
            requested_scope=requested_scope,
            allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
        )

    def _require_stream_execution(self, *, operation: str, requested_scope: str | None = None) -> None:
        require_active_worker_lease(
            operation=operation,
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=requested_scope,
            allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
        )


class CEXProvider(PermitEnforcedProvider, ABC):
    @abstractmethod
    def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
        raise NotImplementedError


class OnchainProvider(PermitEnforcedProvider, ABC):
    @abstractmethod
    def fetch(self, request: ProviderRequest) -> OnchainProviderPayload:
        raise NotImplementedError


class SafetyProvider(PermitEnforcedProvider, ABC):
    @abstractmethod
    def fetch(self, request: ProviderRequest) -> SafetyProviderPayload:
        raise NotImplementedError


class ProviderError(RuntimeError):
    pass


class ProviderNetworkError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderReplayError(ProviderError):
    pass


class ProviderSchemaError(ProviderError, ValueError):
    pass


def validate_provider_metadata(metadata: ProviderMetadata) -> None:
    if not metadata.provider_name or not metadata.provider_name.strip():
        raise ProviderSchemaError("provider metadata is missing provider_name")
    if not isinstance(metadata.retrieved_at, datetime):
        raise ProviderSchemaError("provider metadata retrieved_at must be a datetime")
    if not metadata.scenario or not metadata.scenario.strip():
        raise ProviderSchemaError("provider metadata is missing scenario")
    if not isinstance(metadata.raw_record_count, int) or metadata.raw_record_count < 0:
        raise ProviderSchemaError("provider metadata raw_record_count must be a non-negative int")


def validate_cex_provider_payload(payload: CEXProviderPayload) -> None:
    validate_provider_metadata(payload.metadata)
    if not isinstance(payload.raw_payload, dict):
        raise ProviderSchemaError("cex provider raw_payload must be an object")
    raw = payload.raw_payload
    if not raw.get("provider"):
        raise ProviderSchemaError("cex provider raw_payload is missing provider")
    if not raw.get("retrieved_at"):
        raise ProviderSchemaError("cex provider raw_payload is missing retrieved_at")
    if not raw.get("scenario_tag"):
        raise ProviderSchemaError("cex provider raw_payload is missing scenario_tag")
    events = raw.get("events")
    if not isinstance(events, list):
        raise ProviderSchemaError("cex provider raw_payload field 'events' must be a list")


def validate_onchain_provider_payload(payload: OnchainProviderPayload) -> None:
    validate_provider_metadata(payload.metadata)
    if not isinstance(payload.raw_payload, list):
        raise ProviderSchemaError("onchain provider raw_payload must be a list")
