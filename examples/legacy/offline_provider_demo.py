from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest
from enhengclaw.core.enums import ObjectType
from enhengclaw.providers.offline_providers import (
    OfflineReplayCEXProvider,
    OfflineReplayOnchainProvider,
    OfflineReplaySafetyProvider,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter


def _provider_summary(provider, request: ProviderRequest) -> dict[str, object]:
    payload = provider.fetch(request)
    raw = payload.raw_payload
    if isinstance(raw, dict):
        sample_keys = sorted(str(key) for key in raw.keys())
    elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
        sample_keys = sorted(str(key) for key in raw[0].keys())
    else:
        sample_keys = []
    return {
        "provider_name": payload.metadata.provider_name,
        "scenario": payload.metadata.scenario,
        "retrieved_at": payload.metadata.retrieved_at.isoformat(),
        "raw_record_count": payload.metadata.raw_record_count,
        "payload_type": type(payload).__name__,
        "sample_keys": sample_keys,
    }


def _normalized_summary(batch) -> dict[str, object]:
    return {
        "adapter_name": batch.adapter_name,
        "source_family": batch.source_family.value,
        "source_metadata": batch.source_metadata,
        "retrieval_timestamp": batch.retrieval_timestamp.isoformat(),
        "signal_count": len(batch.signals),
        "signals": [
            {
                "signal_id": signal.signal_id,
                "predicate": signal.predicate,
                "claim_type": signal.claim_type.value,
                "direction": signal.direction.value,
                "evidence_level": signal.evidence_level.value,
                "confidence_hint": signal.confidence_hint,
            }
            for signal in batch.signals
        ],
    }


def _serialize_runtime_result(runtime_result):
    return {
        "object_id": runtime_result.research_object.object_id,
        "processing_state": runtime_result.research_object.processing_state.value,
        "risk_state": runtime_result.research_object.risk_state.value,
        "market_state": runtime_result.research_object.market_state.value,
        "attention_score": runtime_result.research_object.attention_score,
        "working_primary_thesis_id": runtime_result.research_object.working_primary_thesis_id,
        "working_opposing_thesis_id": runtime_result.research_object.working_opposing_thesis_id,
        "decision": runtime_result.decision.decision,
        "decision_reasons": runtime_result.decision.reasons,
        "cadence": {
            "mode": runtime_result.cadence.mode,
            "normal_review_after": None
            if runtime_result.cadence.normal_review_after is None
            else str(runtime_result.cadence.normal_review_after),
            "deep_review_after": None
            if runtime_result.cadence.deep_review_after is None
            else str(runtime_result.cadence.deep_review_after),
        },
        "allocation": None
        if runtime_result.resource_allocation is None
        else {
            "tier": runtime_result.resource_allocation.tier.value,
            "slot_type": runtime_result.resource_allocation.slot_type.value,
        },
    }


def _run_case(orchestrator: RuntimeOrchestrator, *, object_id: str, subject: str, scope: str, scenario: str, snapshot_root: Path):
    providers = {
        "cex": OfflineReplayCEXProvider(snapshot_root),
        "onchain": OfflineReplayOnchainProvider(snapshot_root),
        "safety": OfflineReplaySafetyProvider(snapshot_root),
    }
    adapters = [
        CEXSnapshotAdapter(provider=providers["cex"]),
        OnchainSnapshotAdapter(provider=providers["onchain"]),
        SafetySnapshotAdapter(provider=providers["safety"]),
    ]
    provider_request = ProviderRequest(
        object_id=object_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
    )
    adapter_request = AdapterRequest(
        object_id=object_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
    )
    provider_payloads = [_provider_summary(provider, provider_request) for provider in providers.values()]
    adapter_result = orchestrator.run_new_from_adapters(
        object_id=object_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
        adapters=adapters,
    )
    return {
        "request": {
            "object_id": adapter_request.object_id,
            "subject": adapter_request.subject,
            "scope": adapter_request.scope,
            "scenario": adapter_request.scenario,
        },
        "raw_provider_payload_summary": provider_payloads,
        "normalized_signal_summary": [_normalized_summary(batch) for batch in adapter_result.adapter_batches],
        "runtime_result": _serialize_runtime_result(adapter_result.runtime_result),
    }


def main() -> None:
    snapshot_root = ROOT / "fixtures" / "snapshots"
    orchestrator = RuntimeOrchestrator()

    bullish = _run_case(
        orchestrator,
        object_id="provider-demo-bullish",
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
        snapshot_root=snapshot_root,
    )
    restricted = _run_case(
        orchestrator,
        object_id="provider-demo-restricted",
        subject="ORBX",
        scope="bridge",
        scenario="restricted_monitoring",
        snapshot_root=snapshot_root,
    )

    blocked_seed = _run_case(
        orchestrator,
        object_id="provider-demo-blocked",
        subject="VRTX",
        scope="spot+perp",
        scenario="bullish_publish",
        snapshot_root=snapshot_root,
    )

    blocked_providers = {
        "cex": OfflineReplayCEXProvider(snapshot_root),
        "onchain": OfflineReplayOnchainProvider(snapshot_root),
        "safety": OfflineReplaySafetyProvider(snapshot_root),
    }
    blocked_adapters = [
        CEXSnapshotAdapter(provider=blocked_providers["cex"]),
        OnchainSnapshotAdapter(provider=blocked_providers["onchain"]),
        SafetySnapshotAdapter(provider=blocked_providers["safety"]),
    ]
    blocked_request = ProviderRequest(
        object_id="provider-demo-blocked",
        object_type=ObjectType.ASSET,
        subject="VRTX",
        scope="spot+perp",
        scenario="blocked_risk",
    )
    blocked_payloads = [_provider_summary(provider, blocked_request) for provider in blocked_providers.values()]
    blocked_result = orchestrator.continue_existing_from_adapters(
        object_id="provider-demo-blocked",
        subject="VRTX",
        scenario="blocked_risk",
        adapters=blocked_adapters,
    )

    payload = {
        "runs": [
            bullish,
            restricted,
            {
                "phase": "seed_for_blocked",
                **blocked_seed,
            },
            {
                "phase": "blocked_resume",
                "request": {
                    "object_id": blocked_request.object_id,
                    "subject": blocked_request.subject,
                    "scope": blocked_request.scope,
                    "scenario": blocked_request.scenario,
                },
                "raw_provider_payload_summary": blocked_payloads,
                "normalized_signal_summary": [_normalized_summary(batch) for batch in blocked_result.adapter_batches],
                "runtime_result": _serialize_runtime_result(blocked_result.runtime_result),
            },
        ]
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="offline-provider-demo"):
        main()

