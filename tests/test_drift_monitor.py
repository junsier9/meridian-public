from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.adapters.adapters import AdapterRequest
from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from tests.test_helpers import enter_runtime_worker


class DriftMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-drift-monitor")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"
        self.corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
        self.inspector = CEXDriftInspector()

    def _provider(self, category: str) -> RealCEXProvider:
        return RealCEXProvider(
            RealCEXProviderConfig(
                mode="replay",
                raw_payload_dir=self.corpus.category_root(category),
            )
        )

    def _provider_request(self, scenario: str) -> ProviderRequest:
        return ProviderRequest(
            object_id=f"drift-{scenario}",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )

    def _adapter_request(self, scenario: str) -> AdapterRequest:
        return AdapterRequest(
            object_id=f"drift-{scenario}",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )

    def test_golden_corpus_structure_is_discoverable(self) -> None:
        entries = self.corpus.iter_entries()
        categories = {(entry.category, entry.scenario) for entry in entries}
        self.assertIn(("normal", "bullish_publish"), categories)
        self.assertIn(("edge", "empty_events"), categories)
        self.assertIn(("edge", "missing_raw_http"), categories)
        self.assertIn(("known_bad", "missing_field"), categories)
        self.assertIn(("known_bad", "delayed_data"), categories)

    def test_normal_payload_has_clean_drift_report(self) -> None:
        payload = self._provider("normal").fetch(self._provider_request("bullish_publish"))
        report = self.inspector.inspect(payload)
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.is_drifted)
        self.assertEqual(report.summary.events_count, 2)
        self.assertTrue(report.summary.raw_http_present)

    def test_edge_payloads_are_marked_not_silent(self) -> None:
        missing_raw_http = self._provider("edge").fetch(self._provider_request("missing_raw_http"))
        report = self.inspector.inspect(missing_raw_http)
        self.assertEqual(report.status, "warning")
        self.assertTrue(report.is_drifted)
        self.assertFalse(report.should_reject)

        empty_events = self._provider("edge").fetch(self._provider_request("empty_events"))
        report_empty = self.inspector.inspect(empty_events)
        self.assertEqual(report_empty.status, "warning")
        self.assertTrue(any(finding.code == "empty_events" for finding in report_empty.findings))

    def test_known_bad_payloads_are_marked_and_rejected(self) -> None:
        delayed_payload = self._provider("known_bad").fetch(self._provider_request("delayed_data"))
        delayed_report = self.inspector.inspect(delayed_payload)
        self.assertEqual(delayed_report.status, "error")
        self.assertTrue(delayed_report.should_reject)

        with self.assertRaises(AdapterValidationError):
            CEXSnapshotAdapter(provider=self._provider("known_bad")).collect(self._adapter_request("delayed_data"))

        with self.assertRaises(AdapterValidationError):
            CEXSnapshotAdapter(provider=self._provider("known_bad")).collect(self._adapter_request("missing_field"))

    def test_replay_stability_is_identical_for_same_golden_payload(self) -> None:
        provider = self._provider("normal")
        adapters = [
            CEXSnapshotAdapter(provider=provider),
            OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
            SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
        ]

        runtime_a = RuntimeOrchestrator(store=InMemoryObjectStore())
        runtime_b = RuntimeOrchestrator(store=InMemoryObjectStore())

        result_a = runtime_a.run_new_from_adapters(
            object_id="golden-normal-a",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=adapters,
        )
        result_b = runtime_b.run_new_from_adapters(
            object_id="golden-normal-b",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=adapters,
        )

        self.assertEqual(result_a.runtime_result.decision.decision, result_b.runtime_result.decision.decision)
        self.assertEqual(result_a.runtime_result.research_object.processing_state, result_b.runtime_result.research_object.processing_state)
        self.assertEqual(result_a.runtime_result.research_object.risk_state, result_b.runtime_result.research_object.risk_state)
        self.assertEqual(result_a.runtime_result.research_object.market_state, result_b.runtime_result.research_object.market_state)
        self.assertEqual(
            [(thesis.thesis_type.value, thesis.status.value, thesis.confidence, thesis.working_primary_streak) for thesis in result_a.runtime_result.theses],
            [(thesis.thesis_type.value, thesis.status.value, thesis.confidence, thesis.working_primary_streak) for thesis in result_b.runtime_result.theses],
        )

    def test_edge_payload_runtime_is_marked_and_degraded(self) -> None:
        provider = self._provider("edge")
        report = self.inspector.inspect(
            provider.fetch(self._provider_request("missing_raw_http"))
        )
        self.assertTrue(report.is_drifted)

        runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        result = runtime.run_new_from_adapters(
            object_id="edge-runtime",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="missing_raw_http",
            adapters=[CEXSnapshotAdapter(provider=provider)],
        )
        self.assertEqual(result.runtime_result.decision.decision, "monitoring")
        self.assertEqual(result.runtime_result.research_object.processing_state, ProcessingState.MONITORING)


if __name__ == "__main__":
    unittest.main()
