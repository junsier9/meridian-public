from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import (
    AdapterRequest,
    AdapterValidationError,
    collect_and_validate_batches,
    merge_adapter_batches,
)
from enhengclaw.ops.drift_inspector import OnchainDriftInspector
from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.provider_chaos import OnchainChaosProviderWrapper
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.governance.shadow_mode import (
    AdapterBinding,
    PARTICIPATE_IN_RUNTIME,
    SHADOW_ONLY,
    collect_bound_batches,
)
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter
from tests.test_helpers import enter_runtime_worker


class OnchainDriftAndShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-onchain-shadow-mode")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"
        self.corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "onchain")
        self.inspector = OnchainDriftInspector()

    def _provider(self, category: str) -> RealOnchainProvider:
        return RealOnchainProvider(
            RealOnchainProviderConfig(mode="replay", raw_payload_dir=self.corpus.category_root(category))
        )

    def _adapter_request(self, scenario: str) -> AdapterRequest:
        return AdapterRequest(
            object_id=f"onchain-{scenario}",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )

    def test_onchain_drift_inspector_marks_normal_edge_and_known_bad(self) -> None:
        normal_report = self.inspector.inspect(self._provider("normal").fetch(self._adapter_request("bullish_publish")))
        self.assertEqual(normal_report.status, "ok")

        edge_report = self.inspector.inspect(self._provider("edge").fetch(self._adapter_request("missing_raw_http")))
        self.assertEqual(edge_report.status, "warning")
        self.assertTrue(edge_report.is_drifted)

        bad_provider = self._provider("known_bad")
        with self.assertRaises(AdapterValidationError):
            OnchainSnapshotAdapter(provider=bad_provider).collect(self._adapter_request("missing_field"))
        with self.assertRaises(AdapterValidationError):
            OnchainSnapshotAdapter(provider=bad_provider).collect(self._adapter_request("wrong_type"))

    def test_onchain_chaos_invalid_payloads_are_rejected(self) -> None:
        base_provider = self._provider("normal")
        invalid_scenarios = ["missing_field", "wrong_type", "future_timestamp", "metadata_mismatch", "delayed_data", "schema_flip"]
        for scenario in invalid_scenarios:
            with self.subTest(scenario=scenario):
                adapter = OnchainSnapshotAdapter(provider=OnchainChaosProviderWrapper(base_provider, scenario))
                with self.assertRaises(AdapterValidationError):
                    adapter.collect(self._adapter_request("bullish_publish"))

    def test_onchain_chaos_empty_and_partial_inputs_degrade_not_publish(self) -> None:
        runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        empty_request = self._adapter_request("bullish_publish")
        empty_batches = collect_and_validate_batches(
            [
                CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
                OnchainSnapshotAdapter(provider=OnchainChaosProviderWrapper(self._provider("normal"), "empty_rows")),
            ],
            empty_request,
        )
        empty_result = runtime.run_new(
            object_id="onchain-chaos-empty",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=merge_adapter_batches(empty_batches),
        )
        self.assertEqual(empty_result.decision.decision, "monitoring")
        self.assertEqual(empty_result.research_object.processing_state, ProcessingState.MONITORING)

        partial_request = self._adapter_request("bullish_publish")
        partial_batches = collect_and_validate_batches(
            [
                CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
                OnchainSnapshotAdapter(provider=OnchainChaosProviderWrapper(self._provider("normal"), "partial_truncation")),
            ],
            partial_request,
        )
        partial_result = runtime.run_new(
            object_id="onchain-chaos-partial",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=merge_adapter_batches(partial_batches),
        )
        self.assertEqual(partial_result.decision.decision, "monitoring")
        self.assertGreaterEqual(partial_result.research_object.attention_score, 69)

    def test_shadow_mode_does_not_change_official_runtime_decision(self) -> None:
        request = self._adapter_request("bullish_publish")
        cex_adapter = CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root))
        onchain_adapter = OnchainSnapshotAdapter(provider=self._provider("normal"))

        direct_batches = collect_and_validate_batches([cex_adapter], request)
        direct_result = RuntimeOrchestrator(store=InMemoryObjectStore()).run_new(
            object_id="shadow-direct",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=merge_adapter_batches(direct_batches),
        )

        shadow_collection = collect_bound_batches(
            [
                AdapterBinding(adapter=cex_adapter, mode=PARTICIPATE_IN_RUNTIME, name="cex"),
                AdapterBinding(adapter=onchain_adapter, mode=SHADOW_ONLY, name="onchain-shadow"),
            ],
            request,
        )
        official_result = RuntimeOrchestrator(store=InMemoryObjectStore()).run_new(
            object_id="shadow-official",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=shadow_collection.runtime_signals,
        )
        hypothetical_enabled = RuntimeOrchestrator(store=InMemoryObjectStore()).run_new(
            object_id="shadow-enabled",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=shadow_collection.runtime_signals + shadow_collection.shadow_signals,
        )

        self.assertEqual(direct_result.decision.decision, official_result.decision.decision)
        self.assertEqual(official_result.decision.decision, "monitoring")
        self.assertEqual(hypothetical_enabled.decision.decision, "monitoring")
        self.assertGreater(hypothetical_enabled.research_object.attention_score, official_result.research_object.attention_score)
        self.assertEqual(len(shadow_collection.shadow_signals), 1)

    def test_enabled_mode_is_the_only_mode_routed_through_runtime_collect_pipeline(self) -> None:
        request = self._adapter_request("bullish_publish")
        bindings = [
            AdapterBinding(
                adapter=CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
                mode=PARTICIPATE_IN_RUNTIME,
                name="cex",
            ),
            AdapterBinding(
                adapter=OnchainSnapshotAdapter(provider=self._provider("normal")),
                mode=SHADOW_ONLY,
                name="onchain-shadow",
            ),
        ]

        with patch("enhengclaw.governance.shadow_mode.collect_and_validate_batches") as mocked_collect:
            mocked_collect.side_effect = lambda adapters, req: [adapter.collect(req) for adapter in adapters]
            result = collect_bound_batches(bindings, request)

        mocked_collect.assert_called_once()
        passed_adapters = mocked_collect.call_args.args[0]
        self.assertEqual(len(passed_adapters), 1)
        self.assertIsInstance(passed_adapters[0], CEXSnapshotAdapter)
        self.assertEqual(len(result.runtime_batches), 1)
        self.assertEqual(len(result.shadow_batches), 1)


if __name__ == "__main__":
    unittest.main()
