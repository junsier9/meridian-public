from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Iterable

from datetime import timedelta

from enhengclaw.providers.providers import CEXProvider, CEXProviderPayload, OnchainProvider, OnchainProviderPayload, ProviderRequest


class ChaosProviderWrapper(CEXProvider):
    def __init__(
        self,
        provider: CEXProvider,
        scenario: str | Iterable[str],
    ) -> None:
        self.provider = provider
        if isinstance(scenario, str):
            self._scenarios = [scenario]
        else:
            self._scenarios = list(scenario)
        self._call_count = 0

    def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
        self._require_fetch_execution(request, operation="provider.chaos_cex.fetch")
        payload = deepcopy(self.provider.fetch(request))
        scenario = self._current_scenario()
        self._call_count += 1
        if scenario in {"none", "pass_through"}:
            return payload
        return self._apply(payload, scenario)

    def _current_scenario(self) -> str:
        if not self._scenarios:
            return "pass_through"
        index = min(self._call_count, len(self._scenarios) - 1)
        return self._scenarios[index]

    def _apply(self, payload: CEXProviderPayload, scenario: str) -> CEXProviderPayload:
        raw = payload.raw_payload
        events = raw.get("events", [])

        if scenario == "missing_field" and events:
            events[0]["mapping"].pop("confidenceScore", None)
        elif scenario == "wrong_type" and events:
            events[0]["mapping"]["confidenceScore"] = "strong"
        elif scenario == "future_timestamp":
            payload.metadata.retrieved_at = payload.metadata.retrieved_at + timedelta(days=2)
        elif scenario == "retrograde_timestamp":
            raw["retrieved_at"] = (payload.metadata.retrieved_at - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        elif scenario == "empty_events":
            raw["events"] = []
            payload.metadata.raw_record_count = 0
        elif scenario == "metadata_mismatch":
            payload.metadata.provider_name = f"{payload.metadata.provider_name}-mismatch"
            payload.metadata.raw_record_count = payload.metadata.raw_record_count + 2
        elif scenario == "partial_truncation":
            raw["events"] = events[:1]
            payload.metadata.raw_record_count = 1
        elif scenario == "delayed_data":
            raw_http = raw.get("raw_http")
            if isinstance(raw_http, dict) and isinstance(raw_http.get("klines"), list) and raw_http["klines"]:
                latest = raw_http["klines"][-1]
                if isinstance(latest, list) and len(latest) > 6:
                    latest[6] = int((payload.metadata.retrieved_at - timedelta(hours=12)).timestamp() * 1000)
        elif scenario == "schema_flip":
            raw["events"] = {"not": "a list"}
        elif scenario == "null_metadata":
            raw.pop("provider", None)
        else:
            raise ValueError(f"Unsupported chaos scenario: {scenario}")
        return payload


class OnchainChaosProviderWrapper(OnchainProvider):
    def __init__(
        self,
        provider: OnchainProvider,
        scenario: str | Iterable[str],
    ) -> None:
        self.provider = provider
        if isinstance(scenario, str):
            self._scenarios = [scenario]
        else:
            self._scenarios = list(scenario)
        self._call_count = 0

    def fetch(self, request: ProviderRequest) -> OnchainProviderPayload:
        self._require_fetch_execution(request, operation="provider.chaos_onchain.fetch")
        payload = deepcopy(self.provider.fetch(request))
        scenario = self._current_scenario()
        self._call_count += 1
        if scenario in {"none", "pass_through"}:
            return payload
        return self._apply(payload, scenario)

    def _current_scenario(self) -> str:
        if not self._scenarios:
            return "pass_through"
        index = min(self._call_count, len(self._scenarios) - 1)
        return self._scenarios[index]

    def _apply(self, payload: OnchainProviderPayload, scenario: str) -> OnchainProviderPayload:
        rows = payload.raw_payload
        if scenario == "missing_field" and rows:
            rows[0].pop("confidence_score", None)
        elif scenario == "wrong_type" and rows:
            rows[0]["confidence_score"] = "strong"
        elif scenario == "future_timestamp" and rows:
            rows[0]["retrieved_at"] = (payload.metadata.retrieved_at + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        elif scenario == "metadata_mismatch" and rows:
            payload.metadata.provider_name = f"{payload.metadata.provider_name}-mismatch"
            payload.metadata.raw_record_count = payload.metadata.raw_record_count + 2
        elif scenario == "empty_rows":
            payload.raw_payload = []
            payload.metadata.raw_record_count = 0
        elif scenario == "partial_truncation":
            payload.raw_payload = rows[:1]
            payload.metadata.raw_record_count = len(payload.raw_payload)
        elif scenario == "delayed_data" and rows:
            rows[0]["retrieved_at"] = (payload.metadata.retrieved_at - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        elif scenario == "schema_flip":
            payload.raw_payload = [{"unexpected": "shape"}]
            payload.metadata.raw_record_count = 1
        else:
            raise ValueError(f"Unsupported chaos scenario: {scenario}")
        return payload
