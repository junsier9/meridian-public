from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest
from enhengclaw.core.enums import ObjectType
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter


def _raw_preview(adapter, request: AdapterRequest) -> dict[str, object]:
    return adapter.preview_provider_payload(request)


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


def _run_case(orchestrator: RuntimeOrchestrator, adapters, *, object_id: str, subject: str, scope: str, scenario: str):
    request = AdapterRequest(
        object_id=object_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        scope=scope,
        scenario=scenario,
    )
    previews = [_raw_preview(adapter, request) for adapter in adapters]
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
            "object_id": request.object_id,
            "subject": request.subject,
            "scope": request.scope,
            "scenario": request.scenario,
        },
        "raw_snapshot_preview": previews,
        "normalized_batches": [_normalized_summary(batch) for batch in adapter_result.adapter_batches],
        "runtime_result": _serialize_runtime_result(adapter_result.runtime_result),
    }


def main() -> None:
    snapshot_root = ROOT / "fixtures" / "snapshots"
    adapters = [
        CEXSnapshotAdapter(snapshot_root),
        OnchainSnapshotAdapter(snapshot_root),
        SafetySnapshotAdapter(snapshot_root),
    ]
    orchestrator = RuntimeOrchestrator()

    bullish = _run_case(
        orchestrator,
        adapters,
        object_id="snapshot-demo-bullish",
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
    )
    restricted = _run_case(
        orchestrator,
        adapters,
        object_id="snapshot-demo-restricted",
        subject="ORBX",
        scope="bridge",
        scenario="restricted_monitoring",
    )

    seed_request = AdapterRequest(
        object_id="snapshot-demo-blocked",
        object_type=ObjectType.ASSET,
        subject="VRTX",
        scope="spot+perp",
        scenario="bullish_publish",
    )
    seed_previews = [_raw_preview(adapter, seed_request) for adapter in adapters]
    seed_result = orchestrator.run_new_from_adapters(
        object_id="snapshot-demo-blocked",
        object_type=ObjectType.ASSET,
        subject="VRTX",
        scope="spot+perp",
        scenario="bullish_publish",
        adapters=adapters,
    )

    blocked_request = AdapterRequest(
        object_id="snapshot-demo-blocked",
        object_type=ObjectType.ASSET,
        subject="VRTX",
        scope="spot+perp",
        scenario="blocked_risk",
    )
    blocked_previews = [_raw_preview(adapter, blocked_request) for adapter in adapters]
    blocked_result = orchestrator.continue_existing_from_adapters(
        object_id="snapshot-demo-blocked",
        subject="VRTX",
        scenario="blocked_risk",
        adapters=adapters,
    )

    payload = {
        "runs": [
            bullish,
            restricted,
            {
                "phase": "seed_for_blocked",
                "request": {
                    "object_id": seed_request.object_id,
                    "subject": seed_request.subject,
                    "scope": seed_request.scope,
                    "scenario": seed_request.scenario,
                },
                "raw_snapshot_preview": seed_previews,
                "normalized_batches": [_normalized_summary(batch) for batch in seed_result.adapter_batches],
                "runtime_result": _serialize_runtime_result(seed_result.runtime_result),
            },
            {
                "phase": "blocked_resume",
                "request": {
                    "object_id": blocked_request.object_id,
                    "subject": blocked_request.subject,
                    "scope": blocked_request.scope,
                    "scenario": blocked_request.scenario,
                },
                "raw_snapshot_preview": blocked_previews,
                "normalized_batches": [_normalized_summary(batch) for batch in blocked_result.adapter_batches],
                "runtime_result": _serialize_runtime_result(blocked_result.runtime_result),
            },
        ]
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="snapshot-adapter-demo"):
        main()

