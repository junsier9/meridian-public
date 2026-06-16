from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest, AdapterValidationError
from enhengclaw.core.enums import ObjectType, ProcessingState, RiskState
from enhengclaw.providers.offline_providers import (
    OfflineReplayCEXProvider,
    OfflineReplayOnchainProvider,
    OfflineReplaySafetyProvider,
)
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
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from tests.test_helpers import enter_runtime_worker


class ProviderLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-provider-layer")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"

    def _provider_request(self, scenario: str, subject: str = "AIX") -> ProviderRequest:
        return ProviderRequest(
            object_id=f"provider-{scenario}",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp" if scenario != "restricted_monitoring" else "bridge",
            scenario=scenario,
        )

    def _adapter_request(self, scenario: str, subject: str = "AIX") -> AdapterRequest:
        return AdapterRequest(
            object_id=f"adapter-{scenario}",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp" if scenario != "restricted_monitoring" else "bridge",
            scenario=scenario,
        )

    def test_offline_provider_contract_outputs_expected_shapes(self) -> None:
        cex = OfflineReplayCEXProvider(self.snapshot_root).fetch(self._provider_request("bullish_publish"))
        onchain = OfflineReplayOnchainProvider(self.snapshot_root).fetch(self._provider_request("bullish_publish"))
        safety = OfflineReplaySafetyProvider(self.snapshot_root).fetch(self._provider_request("bullish_publish"))

        self.assertEqual(cex.metadata.provider_name, "snapshot-cex-lab")
        self.assertEqual(cex.metadata.scenario, "bullish_publish")
        self.assertEqual(cex.metadata.raw_record_count, 2)
        self.assertIsInstance(cex.raw_payload, dict)
        self.assertIn("events", cex.raw_payload)

        self.assertEqual(onchain.metadata.provider_name, "snapshot-onchain-lab")
        self.assertEqual(onchain.metadata.raw_record_count, 1)
        self.assertIsInstance(onchain.raw_payload, list)
        self.assertTrue(onchain.raw_payload)

        self.assertEqual(safety.metadata.provider_name, "snapshot-safety-lab")
        self.assertEqual(safety.metadata.raw_record_count, 1)
        self.assertIsInstance(safety.raw_payload, list)
        self.assertTrue(safety.raw_payload)

    def test_adapter_consumes_provider_payload_without_caring_about_file_io(self) -> None:
        base_payload = OfflineReplayCEXProvider(self.snapshot_root).fetch(self._provider_request("bullish_publish"))

        class InMemoryCEXProvider(CEXProvider):
            def __init__(self, payload: CEXProviderPayload) -> None:
                self.payload = deepcopy(payload)

            def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
                return deepcopy(self.payload)

        request = self._adapter_request("bullish_publish")
        via_file = CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)).collect(request)
        via_memory = CEXSnapshotAdapter(provider=InMemoryCEXProvider(base_payload)).collect(request)

        self.assertEqual(via_file.source_metadata["provider"], via_memory.source_metadata["provider"])
        self.assertEqual(via_file.retrieval_timestamp, via_memory.retrieval_timestamp)
        self.assertEqual(
            [(signal.predicate, signal.claim_type.value, signal.direction.value, signal.evidence_level.value) for signal in via_file.signals],
            [(signal.predicate, signal.claim_type.value, signal.direction.value, signal.evidence_level.value) for signal in via_memory.signals],
        )

    def test_bad_provider_payload_is_rejected_by_adapter_normalization(self) -> None:
        class BadCEXProvider(CEXProvider):
            def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
                return CEXProviderPayload(
                    metadata=ProviderMetadata(
                        provider_name="bad-cex-provider",
                        retrieved_at=OfflineReplayCEXProvider.fallback_timestamp.replace(hour=9),
                        scenario=request.scenario,
                        raw_record_count=1,
                    ),
                    raw_payload={
                        "provider": "bad-cex-provider",
                        "retrieved_at": "2026-04-07T09:00:00Z",
                        "scenario_tag": request.scenario,
                        "instrument": "BADUSDT",
                        "events": [
                            {
                                "event_id": "bad-1",
                                "event_name": "spot_breakout",
                                "payload": {"asset": "BAD", "summary": "missing mapping confidence"},
                                "mapping": {
                                    "claimKind": "measurement",
                                    "bias": "bullish",
                                    "evidence": "E4",
                                    "horizon": "intraday",
                                },
                            }
                        ],
                    },
                )

        class BadOnchainProvider(OnchainProvider):
            def fetch(self, request: ProviderRequest) -> OnchainProviderPayload:
                return OnchainProviderPayload(
                    metadata=ProviderMetadata(
                        provider_name="bad-onchain-provider",
                        retrieved_at=OfflineReplayOnchainProvider.fallback_timestamp,
                        scenario=request.scenario,
                        raw_record_count=1,
                    ),
                    raw_payload=[
                        {
                            "record_id": "bad-chain-1",
                            "retrieved_at": "2026-04-07T00:00:00Z",
                            "provider": "bad-onchain-provider",
                            "asset_symbol": "BAD",
                            "event_type": "wallet_buy",
                            "interpretation": "confidence is not numeric",
                            "claim_kind": "flow",
                            "signal_side": "bullish",
                            "evidence_grade": "E4",
                            "confidence_score": "strong",
                            "horizon_label": "intraday",
                            "scope_name": "global",
                        }
                    ],
                )

        with self.assertRaisesRegex(AdapterValidationError, r"confidenceScore"):
            CEXSnapshotAdapter(provider=BadCEXProvider()).collect(self._adapter_request("bad", "BAD"))

        with self.assertRaisesRegex(AdapterValidationError, r"confidence_score"):
            OnchainSnapshotAdapter(provider=BadOnchainProvider()).collect(self._adapter_request("bad", "BAD"))

    def test_provider_backed_runtime_matches_snapshot_adapter_runtime(self) -> None:
        explicit_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        default_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())

        explicit_adapters = [
            CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
            OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
            SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
        ]
        default_adapters = [
            CEXSnapshotAdapter(snapshot_root=self.snapshot_root),
            OnchainSnapshotAdapter(snapshot_root=self.snapshot_root),
            SafetySnapshotAdapter(snapshot_root=self.snapshot_root),
        ]

        explicit = explicit_runtime.run_new_from_adapters(
            object_id="provider-explicit-bullish",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=explicit_adapters,
        )
        default = default_runtime.run_new_from_adapters(
            object_id="provider-default-bullish",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=default_adapters,
        )
        self.assertEqual(explicit.runtime_result.decision.decision, default.runtime_result.decision.decision)
        self.assertEqual(explicit.runtime_result.research_object.processing_state, default.runtime_result.research_object.processing_state)

        explicit_restricted = explicit_runtime.run_new_from_adapters(
            object_id="provider-explicit-restricted",
            object_type=ObjectType.ASSET,
            subject="ORBX",
            scope="bridge",
            scenario="restricted_monitoring",
            adapters=explicit_adapters,
        )
        default_restricted = default_runtime.run_new_from_adapters(
            object_id="provider-default-restricted",
            object_type=ObjectType.ASSET,
            subject="ORBX",
            scope="bridge",
            scenario="restricted_monitoring",
            adapters=default_adapters,
        )
        self.assertEqual(explicit_restricted.runtime_result.decision.decision, default_restricted.runtime_result.decision.decision)
        self.assertEqual(explicit_restricted.runtime_result.research_object.risk_state, RiskState.RESTRICTED)

        explicit_seed = explicit_runtime.run_new_from_adapters(
            object_id="provider-explicit-blocked",
            object_type=ObjectType.ASSET,
            subject="VRTX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=explicit_adapters,
        )
        default_seed = default_runtime.run_new_from_adapters(
            object_id="provider-default-blocked",
            object_type=ObjectType.ASSET,
            subject="VRTX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=default_adapters,
        )
        self.assertEqual(explicit_seed.runtime_result.decision.decision, default_seed.runtime_result.decision.decision)

        explicit_blocked = explicit_runtime.continue_existing_from_adapters(
            object_id="provider-explicit-blocked",
            subject="VRTX",
            scenario="blocked_risk",
            adapters=explicit_adapters,
        )
        default_blocked = default_runtime.continue_existing_from_adapters(
            object_id="provider-default-blocked",
            subject="VRTX",
            scenario="blocked_risk",
            adapters=default_adapters,
        )
        self.assertEqual(explicit_blocked.runtime_result.decision.decision, default_blocked.runtime_result.decision.decision)
        self.assertEqual(explicit_blocked.runtime_result.research_object.processing_state, ProcessingState.BLOCKED)


if __name__ == "__main__":
    unittest.main()
