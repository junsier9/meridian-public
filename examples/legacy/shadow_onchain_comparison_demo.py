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
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.governance.shadow_mode import AdapterBinding, PARTICIPATE_IN_RUNTIME, SHADOW_ONLY, collect_bound_batches
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter


def _signal_summary(batch) -> dict[str, object]:
    return {
        "adapter_name": batch.adapter_name,
        "source_family": batch.source_family.value,
        "source_metadata": batch.source_metadata,
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


def _runtime_summary(result) -> dict[str, object]:
    return {
        "processing_state": result.research_object.processing_state.value,
        "risk_state": result.research_object.risk_state.value,
        "market_state": result.research_object.market_state.value,
        "attention_score": result.research_object.attention_score,
        "working_primary_thesis_id": result.research_object.working_primary_thesis_id,
        "working_opposing_thesis_id": result.research_object.working_opposing_thesis_id,
        "decision": result.decision.decision,
        "decision_reasons": result.decision.reasons,
    }


def main() -> None:
    request = AdapterRequest(
        object_id="shadow-compare",
        object_type=ObjectType.ASSET,
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
    )

    cex_provider = RealCEXProvider(
        RealCEXProviderConfig(
            mode="replay",
            raw_payload_dir=ROOT / "fixtures" / "snapshots",
        )
    )
    onchain_provider = RealOnchainProvider(
        RealOnchainProviderConfig(
            mode="replay",
            raw_payload_dir=ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
        )
    )

    cex_adapter = CEXSnapshotAdapter(provider=cex_provider)
    onchain_adapter = OnchainSnapshotAdapter(provider=onchain_provider)

    cex_only_result = RuntimeOrchestrator().run_new_from_adapters(
        object_id="shadow-compare-cex-only",
        object_type=ObjectType.ASSET,
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
        adapters=[cex_adapter],
    )

    shadow_collection = collect_bound_batches(
        [
            AdapterBinding(adapter=cex_adapter, mode=PARTICIPATE_IN_RUNTIME, name="cex"),
            AdapterBinding(adapter=onchain_adapter, mode=SHADOW_ONLY, name="onchain-shadow"),
        ],
        request,
    )
    official_shadow_result = RuntimeOrchestrator().run_new(
        object_id="shadow-compare-official",
        object_type=ObjectType.ASSET,
        scope="spot+perp",
        signals=shadow_collection.runtime_signals,
    )
    hypothetical_enabled_result = RuntimeOrchestrator().run_new(
        object_id="shadow-compare-enabled",
        object_type=ObjectType.ASSET,
        scope="spot+perp",
        signals=shadow_collection.runtime_signals + shadow_collection.shadow_signals,
    )

    print(
        json.dumps(
            {
                "request": {
                    "object_id": request.object_id,
                    "subject": request.subject,
                    "scope": request.scope,
                    "scenario": request.scenario,
                },
                "cex_only": {
                    "normalized_signal_summary": [_signal_summary(batch) for batch in cex_only_result.adapter_batches],
                    "runtime_result": _runtime_summary(cex_only_result.runtime_result),
                },
                "cex_plus_shadow_provider": {
                    "official_runtime_batches": [_signal_summary(batch) for batch in shadow_collection.runtime_batches],
                    "shadow_batches": [_signal_summary(batch) for batch in shadow_collection.shadow_batches],
                    "new_shadow_signals": [
                        {
                            "signal_id": signal.signal_id,
                            "predicate": signal.predicate,
                            "claim_type": signal.claim_type.value,
                            "direction": signal.direction.value,
                            "evidence_level": signal.evidence_level.value,
                            "confidence_hint": signal.confidence_hint,
                        }
                        for signal in shadow_collection.shadow_signals
                    ],
                    "official_decision_unchanged": _runtime_summary(official_shadow_result),
                    "hypothetical_if_enabled": _runtime_summary(hypothetical_enabled_result),
                    "potential_impact": {
                        "decision_changed": official_shadow_result.decision.decision != hypothetical_enabled_result.decision.decision,
                        "risk_state_changed": official_shadow_result.research_object.risk_state.value != hypothetical_enabled_result.research_object.risk_state.value,
                        "working_primary_changed": official_shadow_result.research_object.working_primary_thesis_id != hypothetical_enabled_result.research_object.working_primary_thesis_id,
                    },
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="shadow-onchain-comparison-demo"):
        main()

