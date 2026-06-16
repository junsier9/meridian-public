from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.core.enums import ObjectType, ProcessingState, RiskState
from enhengclaw.adapters.mock_adapters import MockCEXMarketAdapter, MockOnchainFlowAdapter, MockSafetyRiskAdapter
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider, OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from tests.test_helpers import enter_runtime_worker


class SnapshotAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-snapshot-adapters")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"
        self.store = InMemoryObjectStore()
        self.orchestrator = RuntimeOrchestrator(store=self.store)
        self.snapshot_adapters = [
            CEXSnapshotAdapter(self.snapshot_root),
            OnchainSnapshotAdapter(self.snapshot_root),
            SafetySnapshotAdapter(self.snapshot_root),
        ]
        self.mock_adapters = [
            MockCEXMarketAdapter(),
            MockOnchainFlowAdapter(),
            MockSafetyRiskAdapter(),
        ]

    def test_snapshot_files_parse_and_normalize_correctly(self) -> None:
        from enhengclaw.adapters.adapters import AdapterRequest

        request_kwargs = {
            "object_id": "snapshot-parse",
            "object_type": ObjectType.ASSET,
            "subject": "AIX",
            "scope": "spot+perp",
            "scenario": "bullish_publish",
        }

        previews = []
        total_signals = 0
        request = AdapterRequest(**request_kwargs)
        for adapter in self.snapshot_adapters:
            preview = adapter.preview_provider_payload(request)
            batch = adapter.collect(request)
            previews.append(preview)
            total_signals += len(batch.signals)
            self.assertGreaterEqual(preview["raw_record_count"], len(batch.signals))
            self.assertTrue(preview["sample_keys"] or preview["raw_record_count"] == 0)
            self.assertEqual(batch.source_metadata["scenario"], "bullish_publish")
        self.assertEqual(total_signals, 4)
        self.assertEqual(previews[0]["raw_record_count"], 2)
        self.assertEqual(previews[1]["raw_record_count"], 1)
        self.assertEqual(previews[2]["raw_record_count"], 1)

    def test_missing_and_type_error_fields_are_rejected(self) -> None:
        class BadCEXReplayProvider(OfflineReplayCEXProvider):
            file_name = "cex_missing_confidence.json"

        class BadOnchainReplayProvider(OfflineReplayOnchainProvider):
            file_name = "onchain_bad_confidence.csv"

        from enhengclaw.adapters.adapters import AdapterRequest

        request = AdapterRequest(
            object_id="bad-snapshot",
            object_type=ObjectType.ASSET,
            subject="BAD",
            scope="global",
            scenario="bad",
        )

        with self.assertRaisesRegex(AdapterValidationError, r"confidenceScore"):
            CEXSnapshotAdapter(provider=BadCEXReplayProvider(self.snapshot_root)).collect(request)

        with self.assertRaisesRegex(AdapterValidationError, r"confidence_score"):
            OnchainSnapshotAdapter(provider=BadOnchainReplayProvider(self.snapshot_root)).collect(request)

    def test_snapshot_decisions_match_mock_decisions(self) -> None:
        snapshot_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        mock_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())

        snapshot_bullish = snapshot_runtime.run_new_from_adapters(
            object_id="snapshot-bullish",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.snapshot_adapters,
        )
        mock_bullish = mock_runtime.run_new_from_adapters(
            object_id="mock-bullish",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.mock_adapters,
        )
        self.assertEqual(snapshot_bullish.runtime_result.decision.decision, mock_bullish.runtime_result.decision.decision)
        self.assertEqual(snapshot_bullish.runtime_result.research_object.processing_state, mock_bullish.runtime_result.research_object.processing_state)

        snapshot_restricted = snapshot_runtime.run_new_from_adapters(
            object_id="snapshot-restricted",
            object_type=ObjectType.ASSET,
            subject="ORBX",
            scope="bridge",
            scenario="restricted_monitoring",
            adapters=self.snapshot_adapters,
        )
        mock_restricted = mock_runtime.run_new_from_adapters(
            object_id="mock-restricted",
            object_type=ObjectType.ASSET,
            subject="ORBX",
            scope="bridge",
            scenario="restricted_monitoring",
            adapters=self.mock_adapters,
        )
        self.assertEqual(snapshot_restricted.runtime_result.decision.decision, mock_restricted.runtime_result.decision.decision)
        self.assertEqual(snapshot_restricted.runtime_result.research_object.risk_state, mock_restricted.runtime_result.research_object.risk_state)

        seeded_snapshot = snapshot_runtime.run_new_from_adapters(
            object_id="snapshot-blocked",
            object_type=ObjectType.ASSET,
            subject="VRTX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.snapshot_adapters,
        )
        seeded_mock = mock_runtime.run_new_from_adapters(
            object_id="mock-blocked",
            object_type=ObjectType.ASSET,
            subject="VRTX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.mock_adapters,
        )
        self.assertEqual(seeded_snapshot.runtime_result.decision.decision, seeded_mock.runtime_result.decision.decision)

        blocked_snapshot = snapshot_runtime.continue_existing_from_adapters(
            object_id="snapshot-blocked",
            subject="VRTX",
            scenario="blocked_risk",
            adapters=self.snapshot_adapters,
        )
        blocked_mock = mock_runtime.continue_existing_from_adapters(
            object_id="mock-blocked",
            subject="VRTX",
            scenario="blocked_risk",
            adapters=self.mock_adapters,
        )
        self.assertEqual(blocked_snapshot.runtime_result.decision.decision, blocked_mock.runtime_result.decision.decision)
        self.assertEqual(blocked_snapshot.runtime_result.research_object.processing_state, ProcessingState.BLOCKED)
        self.assertEqual(blocked_snapshot.runtime_result.research_object.risk_state, RiskState.BLOCKED)

    def test_bad_snapshot_input_does_not_pollute_session_store(self) -> None:
        class BadCEXReplayProvider(OfflineReplayCEXProvider):
            file_name = "cex_missing_confidence.json"

        with self.assertRaises(AdapterValidationError):
            self.orchestrator.run_new_from_adapters(
                object_id="snapshot-store-clean",
                object_type=ObjectType.ASSET,
                subject="BAD",
                scope="global",
                scenario="bad",
                adapters=[
                    CEXSnapshotAdapter(provider=BadCEXReplayProvider(self.snapshot_root)),
                    OnchainSnapshotAdapter(self.snapshot_root),
                    SafetySnapshotAdapter(self.snapshot_root),
                ],
            )

        self.assertFalse(self.store.exists("snapshot-store-clean"))


if __name__ == "__main__":
    unittest.main()
