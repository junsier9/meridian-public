from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterBatch, AdapterRequest
from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.providers import CEXProviderPayload, ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from enhengclaw.core.enums import ObjectType


class _StaticCEXProvider:
    def __init__(self, payload: CEXProviderPayload) -> None:
        self.payload = payload

    def fetch(self, request: ProviderRequest) -> CEXProviderPayload:  # noqa: ARG002
        return self.payload


def _provider_summary(payload: CEXProviderPayload) -> dict[str, object]:
    return {
        "provider_name": payload.metadata.provider_name,
        "scenario": payload.metadata.scenario,
        "retrieved_at": payload.metadata.retrieved_at.isoformat(),
        "raw_record_count": payload.metadata.raw_record_count,
        "instrument": payload.raw_payload.get("instrument"),
        "sample_keys": sorted(str(key) for key in payload.raw_payload.keys()),
        "event_names": [str(event.get("event_name")) for event in payload.raw_payload.get("events", [])],
    }


def _normalized_summary(batch: AdapterBatch) -> dict[str, object]:
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


def _runtime_summary(runtime_result) -> dict[str, object]:
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


def _build_live_provider() -> tuple[RealCEXProvider, str, str, str, str]:
    symbol = os.getenv("REAL_CEX_SYMBOL", "BTC")
    scope = "spot"
    scenario = os.getenv("REAL_CEX_SCENARIO", "live_cex_demo")
    provider = RealCEXProvider(
        RealCEXProviderConfig(
            api_base_url=os.getenv("REAL_CEX_API_BASE_URL", "https://api.binance.com"),
            timeout_seconds=float(os.getenv("REAL_CEX_TIMEOUT", "5")),
            api_key_env_var="REAL_CEX_API_KEY",
            mode="record",
            raw_payload_dir=ROOT / "fixtures" / "replays",
        )
    )
    return provider, symbol, scope, scenario, "live_record"


def _build_replay_provider() -> tuple[RealCEXProvider, str, str, str, str]:
    provider = RealCEXProvider(
        RealCEXProviderConfig(
            mode="replay",
            raw_payload_dir=ROOT / "fixtures" / "snapshots",
        )
    )
    return provider, "AIX", "spot+perp", "bullish_publish", "replay_fallback"


def main() -> None:
    real_enabled = os.getenv("ENABLE_REAL_CEX_PROVIDER") == "1"
    provider, subject, scope, scenario, mode = _build_live_provider() if real_enabled else _build_replay_provider()

    provider_request = ProviderRequest(
        object_id="real-cex-demo",
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
    )
    adapter_request = AdapterRequest(
        object_id=provider_request.object_id,
        object_type=provider_request.object_type,
        subject=provider_request.subject,
        scope=provider_request.scope,
        scenario=provider_request.scenario,
    )

    fallback_reason: str | None = None
    try:
        payload = provider.fetch(provider_request)
    except Exception as exc:
        fallback_reason = str(exc)
        provider, subject, scope, scenario, mode = _build_replay_provider()
        provider_request = ProviderRequest(
            object_id="real-cex-demo",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope=scope,
            scenario=scenario,
        )
        adapter_request = AdapterRequest(
            object_id=provider_request.object_id,
            object_type=provider_request.object_type,
            subject=provider_request.subject,
            scope=provider_request.scope,
            scenario=provider_request.scenario,
        )
        payload = provider.fetch(provider_request)
        mode = "replay_fallback_after_live_error"

    cex_adapter = CEXSnapshotAdapter(provider=_StaticCEXProvider(payload))
    adapter_batches = [cex_adapter.collect(adapter_request)]
    adapters = [cex_adapter]

    # Live mode intentionally runs only the real CEX source. Replay fallback adds
    # offline onchain/safety so the demo still shows a full publish-capable path.
    if mode != "live_record":
        adapters.extend(
            [
                OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(ROOT / "fixtures" / "snapshots")),
                SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(ROOT / "fixtures" / "snapshots")),
            ]
        )
        adapter_batches.extend(
            [
                adapters[1].collect(adapter_request),
                adapters[2].collect(adapter_request),
            ]
        )

    orchestrator = RuntimeOrchestrator()
    runtime_result = orchestrator.run_new_from_adapters(
        object_id=provider_request.object_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
        adapters=adapters,
    )

    print(
        json.dumps(
            {
                "mode": mode,
                "fallback_reason": fallback_reason,
                "provider_payload_summary": _provider_summary(payload),
                "normalized_signal_summary": [_normalized_summary(batch) for batch in adapter_batches],
                "runtime_result": _runtime_summary(runtime_result.runtime_result),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="real-cex-provider-demo"):
        main()

