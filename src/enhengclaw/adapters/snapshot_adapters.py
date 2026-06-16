from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from enhengclaw.adapters.adapters import AdapterBatch, AdapterRequest, AdapterValidationError, SignalAdapter
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, SourceFamily, TimeHorizon
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider, OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.providers import (
    CEXProvider,
    CEXProviderPayload,
    OnchainProvider,
    OnchainProviderPayload,
    ProviderRequest,
    SafetyProvider,
    SafetyProviderPayload,
    ProviderSchemaError,
    validate_cex_provider_payload,
    validate_onchain_provider_payload,
)
from enhengclaw.core.signals import Signal
from enhengclaw.domain.identity.subject_key import SubjectKey, ensure_subject_symbol_matches


class SnapshotSignalAdapter(SignalAdapter):
    subject_instrument_type: str = "snapshot"

    def _provider_request(self, request: AdapterRequest) -> ProviderRequest:
        return ProviderRequest(
            object_id=request.object_id,
            object_type=request.object_type,
            subject=request.subject,
            scope=request.scope,
            scenario=request.scenario,
            venue=request.venue,
            instrument_type=request.instrument_type,
            time_horizon=request.time_horizon,
        )

    def _subject_key(self, request: AdapterRequest, *, provider_name: str) -> SubjectKey:
        return SubjectKey.from_request(
            request,
            default_venue=provider_name,
            default_instrument_type=self.subject_instrument_type,
        )

    def _signal_id(
        self,
        request: AdapterRequest,
        *,
        provider_name: str,
        suffix: str,
    ) -> str:
        subject_key = self._subject_key(request, provider_name=provider_name)
        return f"{request.object_id}:{subject_key.as_path_fragment()}:{self.adapter_name}:{suffix}"

    def _required(self, mapping: dict[str, Any], key: str, *, context: str) -> Any:
        if key not in mapping:
            raise AdapterValidationError(f"{self.adapter_name} missing required field '{key}' in {context}")
        value = mapping[key]
        if value is None:
            raise AdapterValidationError(f"{self.adapter_name} field '{key}' is null in {context}")
        return value

    def _parse_datetime(self, value: Any, *, context: str) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise AdapterValidationError(f"{self.adapter_name} timestamp must be a non-empty string in {context}")
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise AdapterValidationError(f"{self.adapter_name} invalid timestamp '{value}' in {context}") from exc

    def _as_int(self, value: Any, *, field_name: str, context: str) -> int:
        if isinstance(value, bool):
            raise AdapterValidationError(f"{self.adapter_name} field '{field_name}' must be an int in {context}")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return int(value)
            except ValueError as exc:
                raise AdapterValidationError(f"{self.adapter_name} field '{field_name}' must be an int in {context}") from exc
        raise AdapterValidationError(f"{self.adapter_name} field '{field_name}' must be an int in {context}")

    def _as_enum(self, enum_cls: type, value: Any, *, field_name: str, context: str):
        if isinstance(value, enum_cls):
            return value
        if not isinstance(value, str) or not value.strip():
            raise AdapterValidationError(f"{self.adapter_name} field '{field_name}' must be a non-empty string in {context}")
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise AdapterValidationError(f"{self.adapter_name} field '{field_name}' has unsupported value '{value}' in {context}") from exc

    @abstractmethod
    def preview_provider_payload(self, request: AdapterRequest) -> dict[str, object]:
        raise NotImplementedError


class CEXSnapshotAdapter(SnapshotSignalAdapter):
    adapter_name = "cex_snapshot_adapter"
    source_family = SourceFamily.CEX
    subject_instrument_type = "cex"
    metadata_time_skew_tolerance = timedelta(minutes=5)
    max_kline_lag = timedelta(hours=2)

    def __init__(self, provider: CEXProvider | str | Path | None = None, snapshot_root: str | Path | None = None) -> None:
        if isinstance(provider, (str, Path)) and snapshot_root is None:
            snapshot_root = provider
            provider = None
        self.provider = provider or OfflineReplayCEXProvider(snapshot_root)

    def preview_provider_payload(self, request: AdapterRequest) -> dict[str, object]:
        provider_request = self._provider_request(request)
        if hasattr(self.provider, "preview"):
            return self.provider.preview(provider_request)  # type: ignore[no-any-return]
        payload = self.provider.fetch(provider_request)
        return {
            "provider_name": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "retrieved_at": payload.metadata.retrieved_at.isoformat(),
            "raw_record_count": payload.metadata.raw_record_count,
            "payload_type": type(payload).__name__,
            "sample_keys": sorted(str(key) for key in payload.raw_payload.keys()),
        }

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        payload = self.provider.fetch(self._provider_request(request))
        self._validate_payload_consistency(payload)
        records = self.extract_records(payload)
        metadata = {
            "provider": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "format": "provider_contract",
            "raw_record_count": payload.metadata.raw_record_count,
            "subject_key": self._subject_key(request, provider_name=payload.metadata.provider_name).as_path_fragment(),
        }
        instrument = payload.raw_payload.get("instrument")
        if instrument is not None:
            metadata["instrument"] = instrument
        signals = [
            self.record_to_signal(
                request,
                record,
                idx,
                provider_name=payload.metadata.provider_name,
            )
            for idx, record in enumerate(records, start=1)
        ]
        return AdapterBatch(
            adapter_name=self.adapter_name,
            source_family=self.source_family,
            source_metadata={key: str(value) for key, value in metadata.items()},
            retrieval_timestamp=payload.metadata.retrieved_at,
            signals=signals,
        )

    def _validate_payload_consistency(self, payload: CEXProviderPayload) -> None:
        try:
            validate_cex_provider_payload(payload)
        except ProviderSchemaError as exc:
            raise AdapterValidationError(f"{self.adapter_name} provider payload failed schema validation: {exc}") from exc

        raw = payload.raw_payload
        events = raw["events"]
        if payload.metadata.provider_name != str(raw.get("provider")):
            raise AdapterValidationError(f"{self.adapter_name} provider metadata does not match raw payload provider")
        if payload.metadata.scenario != str(raw.get("scenario_tag")):
            raise AdapterValidationError(f"{self.adapter_name} provider metadata does not match raw payload scenario_tag")
        if payload.metadata.raw_record_count != len(events):
            raise AdapterValidationError(f"{self.adapter_name} provider metadata raw_record_count does not match events length")

        raw_retrieved_at = self._parse_datetime(raw.get("retrieved_at"), context="cex provider payload root")
        skew = abs(payload.metadata.retrieved_at - raw_retrieved_at)
        if skew > self.metadata_time_skew_tolerance:
            raise AdapterValidationError(
                f"{self.adapter_name} provider metadata timestamp skew exceeds tolerance"
            )

        raw_http = raw.get("raw_http")
        if isinstance(raw_http, dict):
            klines = raw_http.get("klines")
            if isinstance(klines, list) and klines:
                latest_close_time = self._extract_latest_kline_close(klines)
                if latest_close_time is not None:
                    lag = payload.metadata.retrieved_at - latest_close_time
                    if lag > self.max_kline_lag:
                        raise AdapterValidationError(
                            f"{self.adapter_name} provider payload appears stale relative to latest kline close"
                        )
                    if latest_close_time - payload.metadata.retrieved_at > self.metadata_time_skew_tolerance:
                        raise AdapterValidationError(
                            f"{self.adapter_name} latest kline close is ahead of provider retrieval timestamp"
                        )

    def _extract_latest_kline_close(self, klines: list[Any]) -> datetime | None:
        latest = klines[-1]
        if not isinstance(latest, list) or len(latest) <= 6:
            return None
        close_time = latest[6]
        try:
            close_time_ms = int(close_time)
        except (TypeError, ValueError) as exc:
            raise AdapterValidationError(f"{self.adapter_name} latest kline close_time must be an int-like value") from exc
        return datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)

    def extract_records(self, payload: CEXProviderPayload) -> list[dict[str, Any]]:
        raw = payload.raw_payload
        if not isinstance(raw, dict):
            raise AdapterValidationError(f"{self.adapter_name} expected provider payload.raw_payload to be an object")
        records = self._required(raw, "events", context="cex provider payload")
        if not isinstance(records, list):
            raise AdapterValidationError(f"{self.adapter_name} field 'events' must be a list")
        return records

    def record_to_signal(
        self,
        request: AdapterRequest,
        record: dict[str, Any],
        idx: int,
        *,
        provider_name: str,
    ) -> Signal:
        context = f"cex record #{idx}"
        event_id = self._required(record, "event_id", context=context)
        event_name = self._required(record, "event_name", context=context)
        payload = self._required(record, "payload", context=context)
        mapping = self._required(record, "mapping", context=context)
        if not isinstance(payload, dict) or not isinstance(mapping, dict):
            raise AdapterValidationError(f"{self.adapter_name} payload and mapping must be objects in {context}")
        subject = self._required(payload, "asset", context=context)
        ensure_subject_symbol_matches(request.subject, subject, context=context)
        value = self._required(payload, "summary", context=context)
        return Signal(
            signal_id=self._signal_id(
                request,
                provider_name=provider_name,
                suffix=str(event_id),
            ),
            object_type=request.object_type,
            subject=str(subject),
            predicate=str(event_name),
            value=str(value),
            claim_type=self._as_enum(ClaimType, self._required(mapping, "claimKind", context=context), field_name="claimKind", context=context),
            direction=self._as_enum(Direction, self._required(mapping, "bias", context=context), field_name="bias", context=context),
            source_family=self.source_family,
            evidence_level=self._as_enum(EvidenceLevel, self._required(mapping, "evidence", context=context), field_name="evidence", context=context),
            confidence_hint=self._as_int(self._required(mapping, "confidenceScore", context=context), field_name="confidenceScore", context=context),
            scope=request.scope,
            time_horizon=self._as_enum(TimeHorizon, self._required(mapping, "horizon", context=context), field_name="horizon", context=context),
            fresh=True,
        )


class OnchainSnapshotAdapter(SnapshotSignalAdapter):
    adapter_name = "onchain_snapshot_adapter"
    source_family = SourceFamily.ONCHAIN
    subject_instrument_type = "onchain"
    metadata_time_skew_tolerance = timedelta(minutes=5)

    def __init__(self, provider: OnchainProvider | str | Path | None = None, snapshot_root: str | Path | None = None) -> None:
        if isinstance(provider, (str, Path)) and snapshot_root is None:
            snapshot_root = provider
            provider = None
        self.provider = provider or OfflineReplayOnchainProvider(snapshot_root)

    def preview_provider_payload(self, request: AdapterRequest) -> dict[str, object]:
        provider_request = self._provider_request(request)
        if hasattr(self.provider, "preview"):
            return self.provider.preview(provider_request)  # type: ignore[no-any-return]
        payload = self.provider.fetch(provider_request)
        sample_keys = sorted(str(key) for key in payload.raw_payload[0].keys()) if payload.raw_payload else []
        return {
            "provider_name": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "retrieved_at": payload.metadata.retrieved_at.isoformat(),
            "raw_record_count": payload.metadata.raw_record_count,
            "payload_type": type(payload).__name__,
            "sample_keys": sample_keys,
        }

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        payload = self.provider.fetch(self._provider_request(request))
        self._validate_payload_consistency(payload)
        metadata = {
            "provider": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "format": "provider_contract",
            "raw_record_count": payload.metadata.raw_record_count,
            "subject_key": self._subject_key(request, provider_name=payload.metadata.provider_name).as_path_fragment(),
        }
        signals = [
            self.record_to_signal(
                request,
                record,
                idx,
                provider_name=payload.metadata.provider_name,
            )
            for idx, record in enumerate(payload.raw_payload, start=1)
        ]
        return AdapterBatch(
            adapter_name=self.adapter_name,
            source_family=self.source_family,
            source_metadata={key: str(value) for key, value in metadata.items()},
            retrieval_timestamp=payload.metadata.retrieved_at,
            signals=signals,
        )

    def _validate_payload_consistency(self, payload: OnchainProviderPayload) -> None:
        try:
            validate_onchain_provider_payload(payload)
        except ProviderSchemaError as exc:
            raise AdapterValidationError(f"{self.adapter_name} provider payload failed schema validation: {exc}") from exc

        rows = payload.raw_payload
        if payload.metadata.raw_record_count != len(rows):
            raise AdapterValidationError(f"{self.adapter_name} provider metadata raw_record_count does not match row count")
        for idx, row in enumerate(rows, start=1):
            context = f"onchain row #{idx}"
            if not isinstance(row, dict):
                raise AdapterValidationError(f"{self.adapter_name} {context} must be an object")
            row_provider = self._required(row, "provider", context=context)
            if str(row_provider) != payload.metadata.provider_name:
                raise AdapterValidationError(f"{self.adapter_name} provider metadata does not match row provider in {context}")
            row_retrieved_at = self._parse_datetime(self._required(row, "retrieved_at", context=context), context=context)
            if abs(payload.metadata.retrieved_at - row_retrieved_at) > self.metadata_time_skew_tolerance:
                raise AdapterValidationError(f"{self.adapter_name} provider metadata timestamp skew exceeds tolerance in {context}")

    def record_to_signal(
        self,
        request: AdapterRequest,
        record: dict[str, Any],
        idx: int,
        *,
        provider_name: str,
    ) -> Signal:
        context = f"onchain row #{idx}"
        record_id = self._required(record, "record_id", context=context)
        subject = self._required(record, "asset_symbol", context=context)
        ensure_subject_symbol_matches(request.subject, subject, context=context)
        return Signal(
            signal_id=self._signal_id(
                request,
                provider_name=provider_name,
                suffix=str(record_id),
            ),
            object_type=request.object_type,
            subject=str(subject),
            predicate=str(self._required(record, "event_type", context=context)),
            value=str(self._required(record, "interpretation", context=context)),
            claim_type=self._as_enum(ClaimType, self._required(record, "claim_kind", context=context), field_name="claim_kind", context=context),
            direction=self._as_enum(Direction, self._required(record, "signal_side", context=context), field_name="signal_side", context=context),
            source_family=self.source_family,
            evidence_level=self._as_enum(EvidenceLevel, self._required(record, "evidence_grade", context=context), field_name="evidence_grade", context=context),
            confidence_hint=self._as_int(self._required(record, "confidence_score", context=context), field_name="confidence_score", context=context),
            scope=str(self._required(record, "scope_name", context=context)),
            time_horizon=self._as_enum(TimeHorizon, self._required(record, "horizon_label", context=context), field_name="horizon_label", context=context),
            fresh=True,
        )


class SafetySnapshotAdapter(SnapshotSignalAdapter):
    adapter_name = "safety_snapshot_adapter"
    source_family = SourceFamily.SAFETY
    subject_instrument_type = "safety"

    def __init__(self, provider: SafetyProvider | str | Path | None = None, snapshot_root: str | Path | None = None) -> None:
        if isinstance(provider, (str, Path)) and snapshot_root is None:
            snapshot_root = provider
            provider = None
        self.provider = provider or OfflineReplaySafetyProvider(snapshot_root)

    def preview_provider_payload(self, request: AdapterRequest) -> dict[str, object]:
        provider_request = self._provider_request(request)
        if hasattr(self.provider, "preview"):
            return self.provider.preview(provider_request)  # type: ignore[no-any-return]
        payload = self.provider.fetch(provider_request)
        sample_keys = sorted(str(key) for key in payload.raw_payload[0].keys()) if payload.raw_payload else []
        return {
            "provider_name": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "retrieved_at": payload.metadata.retrieved_at.isoformat(),
            "raw_record_count": payload.metadata.raw_record_count,
            "payload_type": type(payload).__name__,
            "sample_keys": sample_keys,
        }

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        payload = self.provider.fetch(self._provider_request(request))
        metadata = {
            "provider": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "format": "provider_contract",
            "raw_record_count": payload.metadata.raw_record_count,
            "subject_key": self._subject_key(request, provider_name=payload.metadata.provider_name).as_path_fragment(),
        }
        signals = [
            self.record_to_signal(
                request,
                record,
                idx,
                provider_name=payload.metadata.provider_name,
            )
            for idx, record in enumerate(payload.raw_payload, start=1)
        ]
        return AdapterBatch(
            adapter_name=self.adapter_name,
            source_family=self.source_family,
            source_metadata={key: str(value) for key, value in metadata.items()},
            retrieval_timestamp=payload.metadata.retrieved_at,
            signals=signals,
        )

    def record_to_signal(
        self,
        request: AdapterRequest,
        record: dict[str, Any],
        idx: int,
        *,
        provider_name: str,
    ) -> Signal:
        context = f"safety record #{idx}"
        incident = self._required(record, "incident", context=context)
        classification = self._required(record, "classification", context=context)
        if not isinstance(incident, dict) or not isinstance(classification, dict):
            raise AdapterValidationError(f"{self.adapter_name} incident and classification must be objects in {context}")
        code = self._required(incident, "code", context=context)
        subject = self._required(incident, "asset", context=context)
        ensure_subject_symbol_matches(request.subject, subject, context=context)
        return Signal(
            signal_id=self._signal_id(
                request,
                provider_name=provider_name,
                suffix=f"{code}:{idx}",
            ),
            object_type=request.object_type,
            subject=str(subject),
            predicate=str(code),
            value=str(self._required(incident, "summary", context=context)),
            claim_type=self._as_enum(ClaimType, self._required(classification, "claim", context=context), field_name="claim", context=context),
            direction=self._as_enum(Direction, self._required(classification, "direction", context=context), field_name="direction", context=context),
            source_family=self.source_family,
            evidence_level=self._as_enum(EvidenceLevel, self._required(classification, "evidence_level", context=context), field_name="evidence_level", context=context),
            confidence_hint=self._as_int(self._required(classification, "confidence", context=context), field_name="confidence", context=context),
            scope=request.scope,
            time_horizon=self._as_enum(TimeHorizon, self._required(classification, "horizon", context=context), field_name="horizon", context=context),
            fresh=True,
        )
