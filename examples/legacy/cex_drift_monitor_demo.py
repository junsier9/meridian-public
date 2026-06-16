from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest
from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.enums import ObjectType
from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter


def _discover_entries(root: Path) -> list[tuple[Path, str, str]]:
    if (root / "cex_snapshot.json").exists():
        return [(root.parent, root.name, str(root))]

    entries: list[tuple[Path, str, str]] = []
    for path in sorted(root.rglob("cex_snapshot.json")):
        scenario_dir = path.parent
        entries.append((scenario_dir.parent, scenario_dir.name, str(scenario_dir)))
    return entries


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


def _runtime_summary(runtime_result) -> dict[str, object]:
    return {
        "processing_state": runtime_result.research_object.processing_state.value,
        "risk_state": runtime_result.research_object.risk_state.value,
        "market_state": runtime_result.research_object.market_state.value,
        "attention_score": runtime_result.research_object.attention_score,
        "working_primary_thesis_id": runtime_result.research_object.working_primary_thesis_id,
        "working_opposing_thesis_id": runtime_result.research_object.working_opposing_thesis_id,
        "decision": runtime_result.decision.decision,
        "decision_reasons": runtime_result.decision.reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "replay_dir",
        nargs="?",
        default=str(ROOT / "fixtures" / "golden_corpus" / "cex"),
        help="Path to a replay directory, category directory, or single scenario directory",
    )
    args = parser.parse_args()

    replay_root = Path(args.replay_dir)
    inspector = CEXDriftInspector()
    snapshot_root = ROOT / "fixtures" / "snapshots"
    runs: list[dict[str, object]] = []

    for category_root, scenario, scenario_dir in _discover_entries(replay_root):
        provider = RealCEXProvider(
            RealCEXProviderConfig(
                mode="replay",
                raw_payload_dir=category_root,
            )
        )
        provider_request = ProviderRequest(
            object_id=f"demo-{scenario}",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )
        payload = provider.fetch(provider_request)
        drift_report = inspector.inspect(payload)

        cex_adapter = CEXSnapshotAdapter(provider=provider)
        normalized_signal_summary = []
        runtime_summary: dict[str, object] | None = None
        adapter_error: str | None = None
        runtime_error: str | None = None

        try:
            adapter_request = AdapterRequest(
                object_id=provider_request.object_id,
                object_type=provider_request.object_type,
                subject=provider_request.subject,
                scope=provider_request.scope,
                scenario=provider_request.scenario,
            )
            cex_batch = cex_adapter.collect(adapter_request)
            normalized_signal_summary.append(_normalized_summary(cex_batch))

            adapters = [cex_adapter]
            if (snapshot_root / scenario).exists():
                onchain = OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(snapshot_root))
                safety = SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(snapshot_root))
                adapters.extend([onchain, safety])
                normalized_signal_summary.append(_normalized_summary(onchain.collect(adapter_request)))
                normalized_signal_summary.append(_normalized_summary(safety.collect(adapter_request)))

            try:
                runtime_result = RuntimeOrchestrator().run_new_from_adapters(
                    object_id=provider_request.object_id,
                    object_type=ObjectType.ASSET,
                    subject=provider_request.subject,
                    scope=provider_request.scope,
                    scenario=provider_request.scenario,
                    adapters=adapters,
                )
                runtime_summary = _runtime_summary(runtime_result.runtime_result)
            except ValueError as exc:
                runtime_error = str(exc)
        except AdapterValidationError as exc:
            adapter_error = str(exc)

        runs.append(
            {
                "scenario_dir": scenario_dir,
                "category_root": str(category_root),
                "scenario": scenario,
                "payload_summary": {
                    "provider_name": payload.metadata.provider_name,
                    "retrieved_at": payload.metadata.retrieved_at.isoformat(),
                    "raw_record_count": payload.metadata.raw_record_count,
                    "top_level_keys": sorted(str(key) for key in payload.raw_payload.keys()),
                },
                "drift_summary": {
                    "status": drift_report.status,
                    "summary": {
                        "top_level_keys": drift_report.summary.top_level_keys,
                        "events_count": drift_report.summary.events_count,
                        "raw_http_present": drift_report.summary.raw_http_present,
                        "metadata_provider_matches": drift_report.summary.metadata_provider_matches,
                        "metadata_scenario_matches": drift_report.summary.metadata_scenario_matches,
                        "metadata_record_count_matches": drift_report.summary.metadata_record_count_matches,
                        "metadata_timestamp_matches": drift_report.summary.metadata_timestamp_matches,
                        "latest_kline_close": drift_report.summary.latest_kline_close,
                        "latest_kline_lag_minutes": drift_report.summary.latest_kline_lag_minutes,
                    },
                    "findings": [
                        {"severity": finding.severity, "code": finding.code, "message": finding.message}
                        for finding in drift_report.findings
                    ],
                },
                "normalized_signal_summary": normalized_signal_summary,
                "runtime_result": runtime_summary,
                "adapter_error": adapter_error,
                "runtime_error": runtime_error,
            }
        )

    print(json.dumps({"runs": runs}, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="cex-drift-monitor-demo"):
        main()

