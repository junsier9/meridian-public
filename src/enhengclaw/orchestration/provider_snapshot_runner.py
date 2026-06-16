from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from enhengclaw.adapters.adapters import (
    AdapterBatch,
    AdapterRequest,
    SignalAdapter,
    collect_and_validate_batches,
    merge_adapter_batches,
)
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import ExecutionPermit
from enhengclaw.orchestration.runtime_runner import (
    RuntimeExecutionProfile,
    RuntimeOrchestrator,
    RuntimeResult,
    adapter_batch_from_record,
    adapter_batch_to_record,
    adapter_request_from_record,
    adapter_request_to_record,
    runtime_execution_profile_from_record,
    runtime_execution_profile_to_record,
    runtime_result_from_record,
    runtime_result_to_record,
)
from enhengclaw.providers.providers import CEXProviderPayload, OnchainProviderPayload, ProviderMetadata, ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path


@dataclass(frozen=True, slots=True)
class ProviderSourceSpec:
    provider_name: str
    provider_type: str
    adapter_kind: str
    provider_impl_kind: str
    mode: str
    scenario: str | None = None
    raw_payload_root: str | None = None
    api_base_url: str | None = None
    timeout_seconds: float | None = None
    api_key_env_var: str | None = None
    quote_asset: str | None = None
    kline_interval: str | None = None
    kline_limit: int | None = None
    query_quote_symbol: str | None = None
    max_pairs: int | None = None

    @classmethod
    def real_cex(
        cls,
        *,
        provider_name: str = "binance-public-cex",
        mode: str = "replay",
        scenario: str | None = None,
        raw_payload_root: str | Path | None = None,
        api_base_url: str | None = None,
        timeout_seconds: float | None = None,
        api_key_env_var: str | None = None,
        quote_asset: str | None = None,
        kline_interval: str | None = None,
        kline_limit: int | None = None,
    ) -> ProviderSourceSpec:
        return cls(
            provider_name=provider_name,
            provider_type="cex",
            adapter_kind="cex_snapshot_adapter",
            provider_impl_kind="real_cex_provider",
            mode=mode,
            scenario=scenario,
            raw_payload_root=None if raw_payload_root is None else str(Path(raw_payload_root)),
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            api_key_env_var=api_key_env_var,
            quote_asset=quote_asset,
            kline_interval=kline_interval,
            kline_limit=kline_limit,
        )

    @classmethod
    def real_onchain(
        cls,
        *,
        provider_name: str = "real_onchain_provider_shadow",
        mode: str = "replay",
        scenario: str | None = None,
        raw_payload_root: str | Path | None = None,
        api_base_url: str | None = None,
        timeout_seconds: float | None = None,
        api_key_env_var: str | None = None,
        query_quote_symbol: str | None = None,
        max_pairs: int | None = None,
    ) -> ProviderSourceSpec:
        return cls(
            provider_name=provider_name,
            provider_type="onchain",
            adapter_kind="onchain_snapshot_adapter",
            provider_impl_kind="real_onchain_provider",
            mode=mode,
            scenario=scenario,
            raw_payload_root=None if raw_payload_root is None else str(Path(raw_payload_root)),
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            api_key_env_var=api_key_env_var,
            query_quote_symbol=query_quote_symbol,
            max_pairs=max_pairs,
        )


@dataclass(frozen=True, slots=True)
class ProviderSnapshotRunRequest:
    object_id: str
    object_type: ObjectType
    subject: str
    scope: str
    scenario: str
    source_specs: list[ProviderSourceSpec]
    execution_profile: RuntimeExecutionProfile | None = None


@dataclass(slots=True)
class ProviderSnapshotRunResult:
    adapter_request: AdapterRequest
    adapter_batches: list[AdapterBatch]
    runtime_result: RuntimeResult
    source_artifact_paths: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class _MaterializedSource:
    spec: ProviderSourceSpec
    adapter: SignalAdapter
    provider: object


def provider_source_spec_to_record(spec: ProviderSourceSpec) -> dict[str, object]:
    return {
        "provider_name": spec.provider_name,
        "provider_type": spec.provider_type,
        "adapter_kind": spec.adapter_kind,
        "provider_impl_kind": spec.provider_impl_kind,
        "mode": spec.mode,
        "scenario": spec.scenario,
        "raw_payload_root": spec.raw_payload_root,
        "api_base_url": spec.api_base_url,
        "timeout_seconds": spec.timeout_seconds,
        "api_key_env_var": spec.api_key_env_var,
        "quote_asset": spec.quote_asset,
        "kline_interval": spec.kline_interval,
        "kline_limit": spec.kline_limit,
        "query_quote_symbol": spec.query_quote_symbol,
        "max_pairs": spec.max_pairs,
    }


def provider_source_spec_from_record(payload: dict[str, object]) -> ProviderSourceSpec:
    return ProviderSourceSpec(
        provider_name=str(payload["provider_name"]),
        provider_type=str(payload["provider_type"]),
        adapter_kind=str(payload["adapter_kind"]),
        provider_impl_kind=str(payload["provider_impl_kind"]),
        mode=str(payload["mode"]),
        scenario=None if payload.get("scenario") is None else str(payload["scenario"]),
        raw_payload_root=None if payload.get("raw_payload_root") is None else str(payload["raw_payload_root"]),
        api_base_url=None if payload.get("api_base_url") is None else str(payload["api_base_url"]),
        timeout_seconds=None if payload.get("timeout_seconds") is None else float(payload["timeout_seconds"]),
        api_key_env_var=None if payload.get("api_key_env_var") is None else str(payload["api_key_env_var"]),
        quote_asset=None if payload.get("quote_asset") is None else str(payload["quote_asset"]),
        kline_interval=None if payload.get("kline_interval") is None else str(payload["kline_interval"]),
        kline_limit=None if payload.get("kline_limit") is None else int(payload["kline_limit"]),
        query_quote_symbol=None
        if payload.get("query_quote_symbol") is None
        else str(payload["query_quote_symbol"]),
        max_pairs=None if payload.get("max_pairs") is None else int(payload["max_pairs"]),
    )


def provider_snapshot_run_request_to_record(request: ProviderSnapshotRunRequest) -> dict[str, object]:
    return {
        "object_id": request.object_id,
        "object_type": request.object_type.value,
        "subject": request.subject,
        "scope": request.scope,
        "scenario": request.scenario,
        "source_specs": [provider_source_spec_to_record(spec) for spec in request.source_specs],
        "execution_profile": runtime_execution_profile_to_record(request.execution_profile),
    }


def provider_snapshot_run_request_from_record(payload: dict[str, object]) -> ProviderSnapshotRunRequest:
    return ProviderSnapshotRunRequest(
        object_id=str(payload["object_id"]),
        object_type=ObjectType(payload["object_type"]),
        subject=str(payload["subject"]),
        scope=str(payload["scope"]),
        scenario=str(payload["scenario"]),
        source_specs=[provider_source_spec_from_record(dict(item)) for item in payload.get("source_specs", [])],
        execution_profile=runtime_execution_profile_from_record(
            None if payload.get("execution_profile") is None else dict(payload["execution_profile"])
        ),
    )


def provider_snapshot_run_result_to_record(result: ProviderSnapshotRunResult) -> dict[str, object]:
    return {
        "adapter_request": adapter_request_to_record(result.adapter_request),
        "adapter_batches": [adapter_batch_to_record(batch) for batch in result.adapter_batches],
        "runtime_result": runtime_result_to_record(result.runtime_result),
        "source_artifact_paths": dict(result.source_artifact_paths),
    }


def provider_snapshot_run_result_from_record(payload: dict[str, object]) -> ProviderSnapshotRunResult:
    return ProviderSnapshotRunResult(
        adapter_request=adapter_request_from_record(dict(payload["adapter_request"])),
        adapter_batches=[adapter_batch_from_record(dict(item)) for item in payload.get("adapter_batches", [])],
        runtime_result=runtime_result_from_record(dict(payload["runtime_result"])),
        source_artifact_paths={
            str(key): None if value is None else str(value)
            for key, value in dict(payload.get("source_artifact_paths", {})).items()
        },
    )


class ProviderSnapshotRunner:
    def __init__(self, *, runtime: RuntimeOrchestrator | None = None) -> None:
        self.runtime = runtime or RuntimeOrchestrator()

    def run_once(
        self,
        request: ProviderSnapshotRunRequest,
        *,
        execution_permit: ExecutionPermit | None = None,
    ) -> ProviderSnapshotRunResult:
        if not request.source_specs:
            raise ValueError("ProviderSnapshotRunner requires at least one ProviderSourceSpec")
        if self.runtime._is_worker_process():
            return execute_provider_snapshot_request(
                request,
                runtime=self.runtime,
                execution_permit=execution_permit,
            )
        payload = self.runtime._dispatch_worker(
            method="run_provider_snapshot",
            request_payload=provider_snapshot_run_request_to_record(request),
            execution_permit=execution_permit,
        )
        return provider_snapshot_run_result_from_record(dict(payload))


def expected_provider_payload_path(
    spec: ProviderSourceSpec,
    request: ProviderRequest,
) -> str | None:
    source = _materialize_source(spec)
    adapter_request = _source_adapter_request(
        ProviderSnapshotRunRequest(
            object_id=request.object_id,
            object_type=request.object_type,
            subject=request.subject,
            scope=request.scope,
            scenario=request.scenario,
            source_specs=[spec],
        ),
        spec,
    )
    return _resolve_provider_payload_path(source.provider, adapter_request)


def execute_provider_snapshot_request(
    request: ProviderSnapshotRunRequest,
    *,
    runtime: RuntimeOrchestrator | None = None,
    execution_permit: ExecutionPermit | None = None,
) -> ProviderSnapshotRunResult:
    orchestrator = _runtime_for_request(
        runtime=runtime,
        execution_permit=execution_permit,
        execution_profile=request.execution_profile,
    )
    adapter_request = AdapterRequest(
        object_id=request.object_id,
        object_type=request.object_type,
        subject=request.subject,
        scope=request.scope,
        scenario=request.scenario,
    )
    sources = [_materialize_source(spec) for spec in request.source_specs]
    batches: list[AdapterBatch] = []
    source_artifact_paths: dict[str, str | None] = {}
    for source in sources:
        source_request = _source_adapter_request(request, source.spec)
        batches.extend(collect_and_validate_batches([source.adapter], source_request))
        source_artifact_paths[source.spec.provider_name] = _resolve_provider_payload_path(source.provider, source_request)
    orchestrator._guard_downstream_subject_keys(
        subject_keys=orchestrator._subject_keys_from_batches(batches),
        consumer="runtime.provider_snapshot.create",
    )
    runtime_result = orchestrator.run_new(
        object_id=request.object_id,
        object_type=request.object_type,
        scope=request.scope,
        signals=merge_adapter_batches(batches),
    )
    return ProviderSnapshotRunResult(
        adapter_request=adapter_request,
        adapter_batches=batches,
        runtime_result=runtime_result,
        source_artifact_paths=source_artifact_paths,
    )


def load_cex_payload_artifact(path: str | Path) -> CEXProviderPayload:
    artifact_path = Path(path)
    raw_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    retrieved_at = _parse_artifact_timestamp(raw_payload.get("retrieved_at"))
    events = raw_payload.get("events")
    if not isinstance(events, list):
        raise ValueError(f"{artifact_path} does not contain a valid cex events list")
    return CEXProviderPayload(
        metadata=ProviderMetadata(
            provider_name=str(raw_payload.get("provider", "")),
            retrieved_at=retrieved_at,
            scenario=str(raw_payload.get("scenario_tag", artifact_path.parents[1].name)),
            raw_record_count=len(events),
        ),
        raw_payload=raw_payload,
    )


def load_onchain_payload_artifact(path: str | Path) -> OnchainProviderPayload:
    artifact_path = Path(path)
    with artifact_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    provider_name = str(rows[0].get("provider", "")) if rows else "dexscreener-public-onchain"
    retrieved_at = _parse_artifact_timestamp(rows[0].get("retrieved_at") if rows else None)
    return OnchainProviderPayload(
        metadata=ProviderMetadata(
            provider_name=provider_name,
            retrieved_at=retrieved_at,
            scenario=artifact_path.parents[1].name,
            raw_record_count=len(rows),
        ),
        raw_payload=rows,
    )


def _runtime_for_request(
    *,
    runtime: RuntimeOrchestrator | None,
    execution_permit: ExecutionPermit | None,
    execution_profile: RuntimeExecutionProfile | None,
) -> RuntimeOrchestrator:
    if runtime is None:
        return RuntimeOrchestrator(
            execution_permit=execution_permit,
            execution_profile=execution_profile,
        )
    if execution_profile is None or execution_profile == runtime.execution_profile:
        return runtime
    return RuntimeOrchestrator(
        store=runtime.store,
        rule_service=runtime.rule_service,
        resource_allocator=runtime.resource_allocator,
        selection_gateway=runtime.selection_gateway,
        agent_ingress_firewall=runtime.agent_ingress_firewall,
        downstream_ingress_guard=runtime.downstream_ingress_guard,
        execution_permit=execution_permit or runtime.execution_permit,
        execution_profile=execution_profile,
    )


def _materialize_source(spec: ProviderSourceSpec) -> _MaterializedSource:
    if spec.provider_impl_kind == "real_cex_provider":
        if spec.adapter_kind != "cex_snapshot_adapter" or spec.provider_type != "cex":
            raise ValueError(f"{spec.provider_name} has an unsupported cex adapter/provider pairing")
        provider = RealCEXProvider(
            RealCEXProviderConfig(
                api_base_url=spec.api_base_url or "https://api.binance.com",
                timeout_seconds=5.0 if spec.timeout_seconds is None else spec.timeout_seconds,
                api_key_env_var=spec.api_key_env_var,
                mode=spec.mode,
                raw_payload_dir=spec.raw_payload_root,
                quote_asset=spec.quote_asset or "USDT",
                kline_interval=spec.kline_interval or "5m",
                kline_limit=2 if spec.kline_limit is None else spec.kline_limit,
            )
        )
        return _MaterializedSource(
            spec=spec,
            adapter=CEXSnapshotAdapter(provider=provider),
            provider=provider,
        )
    if spec.provider_impl_kind == "real_onchain_provider":
        if spec.adapter_kind != "onchain_snapshot_adapter" or spec.provider_type != "onchain":
            raise ValueError(f"{spec.provider_name} has an unsupported onchain adapter/provider pairing")
        provider = RealOnchainProvider(
            RealOnchainProviderConfig(
                api_base_url=spec.api_base_url or "https://api.dexscreener.com",
                timeout_seconds=5.0 if spec.timeout_seconds is None else spec.timeout_seconds,
                api_key_env_var=spec.api_key_env_var,
                mode=spec.mode,
                raw_payload_dir=spec.raw_payload_root,
                query_quote_symbol=spec.query_quote_symbol or "USDT",
                max_pairs=1 if spec.max_pairs is None else spec.max_pairs,
            )
        )
        return _MaterializedSource(
            spec=spec,
            adapter=OnchainSnapshotAdapter(provider=provider),
            provider=provider,
        )
    raise ValueError(f"unsupported provider_impl_kind: {spec.provider_impl_kind}")


def _resolve_provider_payload_path(provider: object, request: AdapterRequest) -> str | None:
    provider_request = ProviderRequest(
        object_id=request.object_id,
        object_type=request.object_type,
        subject=request.subject,
        scope=request.scope,
        scenario=request.scenario,
        venue=request.venue,
        instrument_type=request.instrument_type,
        time_horizon=request.time_horizon,
    )
    replay_path_fn = getattr(provider, "_replay_path_for", None)
    if callable(replay_path_fn):
        try:
            return str(Path(replay_path_fn(provider_request)))
        except Exception:
            return None
    raw_dir = getattr(provider, "raw_payload_dir", None)
    file_name = getattr(provider, "file_name", None)
    if raw_dir is None or not file_name:
        return None
    default_venue = str(getattr(provider, "provider_name", "unknown-provider"))
    default_instrument_type = str(getattr(provider, "subject_instrument_type", "unknown"))
    subject_key = SubjectKey.from_request(
        provider_request,
        default_venue=default_venue,
        default_instrument_type=default_instrument_type,
    )
    return str(subject_key_path(Path(raw_dir), request.scenario, subject_key, file_name))


def _parse_artifact_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("artifact metadata is missing retrieved_at")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _source_adapter_request(
    request: ProviderSnapshotRunRequest,
    spec: ProviderSourceSpec,
) -> AdapterRequest:
    return AdapterRequest(
        object_id=request.object_id,
        object_type=request.object_type,
        subject=request.subject,
        scope=request.scope,
        scenario=spec.scenario or request.scenario,
    )
