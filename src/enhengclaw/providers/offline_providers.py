from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.core.execution_control import CAP_PROVIDER_FETCH, RUNTIME_WORKER_ENTRYPOINT, require_active_worker_lease
from enhengclaw.providers.providers import (
    CEXProvider,
    CEXProviderPayload,
    OnchainProvider,
    OnchainProviderPayload,
    ProviderMetadata,
    ProviderRequest,
    SafetyProvider,
    SafetyProviderPayload,
)
from enhengclaw.utils.subject_keys import (
    SubjectKey,
    ensure_subject_symbol_matches,
    iter_subject_key_paths,
    subject_key_path,
)


class _OfflineReplayProviderBase:
    file_name: str
    fallback_timestamp = datetime.fromisoformat("2026-04-07T00:00:00+00:00")
    default_venue = "offline-replay"
    default_instrument_type = "snapshot"

    def __init__(
        self,
        snapshot_root: str | Path | None = None,
        *,
        default_venue: str | None = None,
        default_instrument_type: str | None = None,
    ) -> None:
        self.snapshot_root = (
            Path(snapshot_root)
            if snapshot_root is not None
            else Path(__file__).resolve().parents[3] / "fixtures" / "snapshots"
        )
        if default_venue is not None:
            self.default_venue = str(default_venue)
        if default_instrument_type is not None:
            self.default_instrument_type = str(default_instrument_type)

    def subject_key_for_request(self, request: ProviderRequest) -> SubjectKey:
        return SubjectKey.from_request(
            request,
            default_venue=self.default_venue,
            default_instrument_type=self.default_instrument_type,
        )

    def snapshot_path_for(self, request: ProviderRequest) -> Path:
        return subject_key_path(
            self.snapshot_root,
            request.scenario,
            self.subject_key_for_request(request),
            self.file_name,
        )

    def _resolve_snapshot_path(self, request: ProviderRequest) -> Path:
        exact_path = self.snapshot_path_for(request)
        if exact_path.exists():
            return exact_path

        expected_subject_key = self.subject_key_for_request(request)
        matches = [
            path
            for subject_key, path in iter_subject_key_paths(self.snapshot_root, request.scenario, self.file_name)
            if subject_key == expected_subject_key
        ]
        if len(matches) > 1:
            raise AdapterValidationError(
                f"multiple replay payloads matched subject_key '{expected_subject_key.as_path_fragment()}'"
            )
        if len(matches) == 1:
            return matches[0]
        return exact_path

    def _load_snapshot(self, request: ProviderRequest) -> Any:
        require_active_worker_lease(
            operation=f"provider.{type(self).__name__}.snapshot_io",
            required_capabilities={CAP_PROVIDER_FETCH},
            requested_scope=request.scope,
            allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
        )
        path = self._resolve_snapshot_path(request)
        if not path.exists():
            raise AdapterValidationError(f"snapshot file does not exist: {path}")

        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        if suffix == ".csv":
            with path.open("r", encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))
        if suffix == ".ndjson":
            rows: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rows.append(json.loads(stripped))
                    except json.JSONDecodeError as exc:
                        raise AdapterValidationError(f"invalid NDJSON in {path} at line {line_no}: {exc.msg}") from exc
            return rows
        raise AdapterValidationError(f"unsupported snapshot file type: {path.suffix}")

    def preview(self, request: ProviderRequest) -> dict[str, object]:
        payload = self.fetch(request)
        return {
            "provider_name": payload.metadata.provider_name,
            "scenario": payload.metadata.scenario,
            "retrieved_at": payload.metadata.retrieved_at.isoformat(),
            "raw_record_count": payload.metadata.raw_record_count,
            "snapshot_path": str(self._resolve_snapshot_path(request)),
            "payload_type": type(payload).__name__,
            "sample_keys": self._sample_keys(payload),
        }

    def _sample_keys(self, payload: CEXProviderPayload | OnchainProviderPayload | SafetyProviderPayload) -> list[str]:
        raw = payload.raw_payload
        if isinstance(raw, dict):
            return sorted(str(key) for key in raw.keys())
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            return sorted(str(key) for key in raw[0].keys())
        return []

    def _parse_datetime(self, value: Any, *, context: str) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise AdapterValidationError(f"{type(self).__name__} timestamp must be a non-empty string in {context}")
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise AdapterValidationError(f"{type(self).__name__} invalid timestamp '{value}' in {context}") from exc


class OfflineReplayCEXProvider(_OfflineReplayProviderBase, CEXProvider):
    file_name = "cex_snapshot.json"
    default_venue = "snapshot-cex-lab"
    default_instrument_type = "cex"

    def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
        self._require_fetch_execution(request, operation="provider.offline_replay_cex.fetch")
        raw = self._load_snapshot(request)
        if not isinstance(raw, dict):
            raise AdapterValidationError("OfflineReplayCEXProvider expected JSON object payload")
        observed_subject = self._cex_subject(raw)
        ensure_subject_symbol_matches(request.subject, observed_subject, context="OfflineReplayCEXProvider")
        events = raw.get("events")
        raw_record_count = len(events) if isinstance(events, list) else 0
        metadata = ProviderMetadata(
            provider_name=str(raw.get("provider", "offline-cex-replay")),
            retrieved_at=self._parse_datetime(raw.get("retrieved_at"), context="cex snapshot root"),
            scenario=str(raw.get("scenario_tag", request.scenario)),
            raw_record_count=raw_record_count,
        )
        return CEXProviderPayload(metadata=metadata, raw_payload=raw)

    def _cex_subject(self, raw: dict[str, Any]) -> str:
        events = raw.get("events")
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                payload = event.get("payload")
                if isinstance(payload, dict) and payload.get("asset"):
                    return str(payload["asset"])
        instrument = raw.get("instrument")
        if isinstance(instrument, str) and instrument.strip():
            upper = instrument.strip().upper()
            for suffix in ("USDT", "USDC", "USD", "BTC", "ETH"):
                if upper.endswith(suffix) and len(upper) > len(suffix):
                    return upper[: -len(suffix)]
            return upper
        raise AdapterValidationError("OfflineReplayCEXProvider could not infer snapshot subject")


class OfflineReplayOnchainProvider(_OfflineReplayProviderBase, OnchainProvider):
    file_name = "onchain_snapshot.csv"
    default_venue = "snapshot-onchain-lab"
    default_instrument_type = "onchain"

    def fetch(self, request: ProviderRequest) -> OnchainProviderPayload:
        self._require_fetch_execution(request, operation="provider.offline_replay_onchain.fetch")
        raw = self._load_snapshot(request)
        if not isinstance(raw, list):
            raise AdapterValidationError("OfflineReplayOnchainProvider expected CSV row list payload")
        observed_subject = request.subject if not raw else raw[0].get("asset_symbol")
        ensure_subject_symbol_matches(request.subject, observed_subject, context="OfflineReplayOnchainProvider")
        retrieved_at = self.fallback_timestamp if not raw else self._parse_datetime(raw[0].get("retrieved_at"), context="onchain row #1")
        provider_name = "offline-onchain-replay" if not raw else str(raw[0].get("provider", "offline-onchain-replay"))
        metadata = ProviderMetadata(
            provider_name=provider_name,
            retrieved_at=retrieved_at,
            scenario=request.scenario,
            raw_record_count=len(raw),
        )
        return OnchainProviderPayload(metadata=metadata, raw_payload=raw)


class OfflineReplaySafetyProvider(_OfflineReplayProviderBase, SafetyProvider):
    file_name = "safety_snapshot.ndjson"
    default_venue = "snapshot-safety-lab"
    default_instrument_type = "safety"

    def fetch(self, request: ProviderRequest) -> SafetyProviderPayload:
        self._require_fetch_execution(request, operation="provider.offline_replay_safety.fetch")
        raw = self._load_snapshot(request)
        if not isinstance(raw, list):
            raise AdapterValidationError("OfflineReplaySafetyProvider expected NDJSON record list payload")
        observed_subject = request.subject
        if raw:
            incident = raw[0].get("incident")
            if isinstance(incident, dict):
                observed_subject = incident.get("asset", request.subject)
        ensure_subject_symbol_matches(request.subject, observed_subject, context="OfflineReplaySafetyProvider")
        retrieved_at = self.fallback_timestamp if not raw else self._parse_datetime(raw[0].get("retrieved_at"), context="safety record #1")
        provider_name = "offline-safety-replay" if not raw else str(raw[0].get("provider", "offline-safety-replay"))
        metadata = ProviderMetadata(
            provider_name=provider_name,
            retrieved_at=retrieved_at,
            scenario=request.scenario,
            raw_record_count=len(raw),
        )
        return SafetyProviderPayload(metadata=metadata, raw_payload=raw)
