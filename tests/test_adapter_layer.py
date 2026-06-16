from __future__ import annotations

import unittest
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterBatch, AdapterRequest, AdapterValidationError, SignalAdapter
from enhengclaw.core.enums import (
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    ProcessingState,
    RiskState,
    SourceFamily,
)
from enhengclaw.adapters.mock_adapters import (
    MockCEXMarketAdapter,
    MockInfoflowAdapter,
    MockOnchainFlowAdapter,
    MockSafetyRiskAdapter,
)
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.core.signals import Signal
from enhengclaw.utils.subject_keys import SubjectKey
from tests.test_helpers import enter_runtime_worker


class AdapterLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-adapter-layer")
        self.store = InMemoryObjectStore()
        self.orchestrator = RuntimeOrchestrator(store=self.store)
        self.adapters = [
            MockCEXMarketAdapter(),
            MockOnchainFlowAdapter(),
            MockSafetyRiskAdapter(),
            MockInfoflowAdapter(),
        ]

    def _request(self, object_id: str, scenario: str) -> AdapterRequest:
        return AdapterRequest(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )

    def test_adapter_outputs_have_expected_schema(self) -> None:
        request = self._request("adapter-schema", "bullish_publish")

        for adapter in self.adapters:
            with self.subTest(adapter=adapter.adapter_name):
                batch = adapter.collect(request)
                self.assertIsInstance(batch, AdapterBatch)
                self.assertEqual(batch.adapter_name, adapter.adapter_name)
                self.assertEqual(batch.source_family, adapter.source_family)
                self.assertIn("provider", batch.source_metadata)
                self.assertIn("scenario", batch.source_metadata)
                self.assertIn("subject_key", batch.source_metadata)
                self.assertEqual(batch.source_metadata["scenario"], "bullish_publish")
                self.assertIsInstance(batch.retrieval_timestamp, datetime)
                for signal in batch.signals:
                    self.assertIsInstance(signal, Signal)
                    self.assertEqual(signal.object_type, request.object_type)
                    self.assertEqual(signal.subject, request.subject)
                    self.assertEqual(signal.scope, request.scope)
                    self.assertEqual(signal.source_family, adapter.source_family)

    def test_adapter_outputs_merge_into_single_runtime_object(self) -> None:
        adapter_result = self.orchestrator.run_new_from_adapters(
            object_id="adapter-merge",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.adapters,
        )

        self.assertEqual(len(adapter_result.adapter_batches), 4)
        merged_signals = [signal for batch in adapter_result.adapter_batches for signal in batch.signals]
        self.assertGreaterEqual(len(merged_signals), 4)
        source_families = {signal.source_family for signal in merged_signals}
        self.assertGreaterEqual(len(source_families), 3)
        self.assertEqual(adapter_result.runtime_result.research_object.object_id, "adapter-merge")
        self.assertEqual(len(adapter_result.runtime_result.claims), len(merged_signals))

    def test_bad_adapter_data_is_rejected_before_runtime_pollution(self) -> None:
        class EmptyFieldAdapter(SignalAdapter):
            adapter_name = "bad_empty"
            source_family = SourceFamily.CEX

            def collect(self, request: AdapterRequest) -> AdapterBatch:
                subject_key = SubjectKey.build(symbol=request.subject, venue="bad-empty", instrument_type="cex").as_path_fragment()
                return AdapterBatch(
                    adapter_name=self.adapter_name,
                    source_family=self.source_family,
                    source_metadata={"provider": "bad-empty", "scenario": request.scenario, "subject_key": subject_key},
                    retrieval_timestamp=datetime.now(timezone.utc),
                    signals=[
                        Signal(
                            signal_id=f"bad-empty:{subject_key}:1",
                            object_type=request.object_type,
                            subject="",
                            predicate="spot_breakout",
                            value="bad empty subject",
                            claim_type=ClaimType.MEASUREMENT,
                            direction=Direction.BULLISH,
                            source_family=self.source_family,
                            evidence_level=EvidenceLevel.E4,
                            confidence_hint=80,
                            scope=request.scope,
                        )
                    ],
                )

        class InvalidDirectionAdapter(SignalAdapter):
            adapter_name = "bad_direction"
            source_family = SourceFamily.ONCHAIN

            def collect(self, request: AdapterRequest) -> AdapterBatch:
                subject_key = SubjectKey.build(symbol=request.subject, venue="bad-direction", instrument_type="onchain").as_path_fragment()
                return AdapterBatch(
                    adapter_name=self.adapter_name,
                    source_family=self.source_family,
                    source_metadata={"provider": "bad-direction", "scenario": request.scenario, "subject_key": subject_key},
                    retrieval_timestamp=datetime.now(timezone.utc),
                    signals=[
                        Signal(
                            signal_id=f"bad-direction:{subject_key}:1",
                            object_type=request.object_type,
                            subject=request.subject,
                            predicate="wallet_buy",
                            value="invalid direction",
                            claim_type=ClaimType.FLOW,
                            direction="up-only",  # type: ignore[arg-type]
                            source_family=self.source_family,
                            evidence_level=EvidenceLevel.E4,
                            confidence_hint=80,
                            scope=request.scope,
                        )
                    ],
                )

        class InvalidEvidenceAdapter(SignalAdapter):
            adapter_name = "bad_evidence"
            source_family = SourceFamily.SAFETY

            def collect(self, request: AdapterRequest) -> AdapterBatch:
                subject_key = SubjectKey.build(symbol=request.subject, venue="bad-evidence", instrument_type="safety").as_path_fragment()
                return AdapterBatch(
                    adapter_name=self.adapter_name,
                    source_family=self.source_family,
                    source_metadata={"provider": "bad-evidence", "scenario": request.scenario, "subject_key": subject_key},
                    retrieval_timestamp=datetime.now(timezone.utc),
                    signals=[
                        Signal(
                            signal_id=f"bad-evidence:{subject_key}:1",
                            object_type=request.object_type,
                            subject=request.subject,
                            predicate="bridge_risk",
                            value="invalid evidence level",
                            claim_type=ClaimType.RISK_FLAG,
                            direction=Direction.RISK,
                            source_family=self.source_family,
                            evidence_level="E9",  # type: ignore[arg-type]
                            confidence_hint=80,
                            scope=request.scope,
                        )
                    ],
                )

        for bad_adapter in (EmptyFieldAdapter(), InvalidDirectionAdapter(), InvalidEvidenceAdapter()):
            with self.subTest(adapter=bad_adapter.adapter_name):
                with self.assertRaises(AdapterValidationError):
                    self.orchestrator.run_new_from_adapters(
                        object_id=f"bad-{bad_adapter.adapter_name}",
                        object_type=ObjectType.ASSET,
                        subject="AIX",
                        scope="spot+perp",
                        scenario="bullish_publish",
                        adapters=[MockCEXMarketAdapter(), bad_adapter],
                    )
                self.assertFalse(self.store.exists(f"bad-{bad_adapter.adapter_name}"))

    def test_cross_subject_signal_is_rejected_as_hard_error(self) -> None:
        class CrossSubjectAdapter(SignalAdapter):
            adapter_name = "cross_subject"
            source_family = SourceFamily.CEX

            def collect(self, request: AdapterRequest) -> AdapterBatch:
                subject_key = SubjectKey.build(symbol=request.subject, venue="cross-subject", instrument_type="cex").as_path_fragment()
                return AdapterBatch(
                    adapter_name=self.adapter_name,
                    source_family=self.source_family,
                    source_metadata={"provider": "cross-subject", "scenario": request.scenario, "subject_key": subject_key},
                    retrieval_timestamp=datetime.now(timezone.utc),
                    signals=[
                        Signal(
                            signal_id=f"cross-subject:{subject_key}:1",
                            object_type=request.object_type,
                            subject="BTC",
                            predicate="spot_breakout",
                            value="foreign subject leaked into batch",
                            claim_type=ClaimType.MEASUREMENT,
                            direction=Direction.BULLISH,
                            source_family=self.source_family,
                            evidence_level=EvidenceLevel.E4,
                            confidence_hint=80,
                            scope=request.scope,
                        )
                    ],
                )

        with self.assertRaises(AdapterValidationError):
            self.orchestrator.run_new_from_adapters(
                object_id="bad-cross-subject",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                adapters=[CrossSubjectAdapter()],
            )
        self.assertFalse(self.store.exists("bad-cross-subject"))

    def test_mock_adapter_scenarios_drive_expected_runtime_decisions(self) -> None:
        bullish = self.orchestrator.run_new_from_adapters(
            object_id="adapter-bullish",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.adapters,
        )
        self.assertEqual(bullish.runtime_result.decision.decision, "publish")
        self.assertEqual(bullish.runtime_result.research_object.processing_state, ProcessingState.PUBLISHED)

        restricted = self.orchestrator.run_new_from_adapters(
            object_id="adapter-restricted",
            object_type=ObjectType.ASSET,
            subject="ORBX",
            scope="bridge",
            scenario="restricted_monitoring",
            adapters=self.adapters,
        )
        self.assertEqual(restricted.runtime_result.decision.decision, "monitoring")
        self.assertEqual(restricted.runtime_result.research_object.processing_state, ProcessingState.MONITORING)
        self.assertEqual(restricted.runtime_result.research_object.risk_state, RiskState.RESTRICTED)

        seeded = self.orchestrator.run_new_from_adapters(
            object_id="adapter-blocked",
            object_type=ObjectType.ASSET,
            subject="VRTX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=self.adapters,
        )
        self.assertEqual(seeded.runtime_result.research_object.processing_state, ProcessingState.PUBLISHED)

        blocked = self.orchestrator.continue_existing_from_adapters(
            object_id="adapter-blocked",
            subject="VRTX",
            scenario="blocked_risk",
            adapters=self.adapters,
        )
        self.assertEqual(blocked.runtime_result.decision.decision, "blocked")
        self.assertEqual(blocked.runtime_result.research_object.processing_state, ProcessingState.BLOCKED)
        self.assertEqual(blocked.runtime_result.research_object.risk_state, RiskState.BLOCKED)


if __name__ == "__main__":
    unittest.main()
