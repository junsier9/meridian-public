from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest
from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.adapters.adapters import collect_and_validate_batches, merge_adapter_batches
from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.provider_chaos import ChaosProviderWrapper
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from tests.test_helpers import enter_runtime_worker


class _FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        import json

        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _good_ticker_payload(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "priceChangePercent": "5.80",
        "quoteVolume": "1543210.50",
        "lastPrice": "1.2570",
        "openPrice": "1.1880",
    }


def _good_klines_payload() -> list[list[object]]:
    now = datetime.now(timezone.utc)
    previous_open = int((now - timedelta(minutes=10)).timestamp() * 1000)
    previous_close = int((now - timedelta(minutes=5)).timestamp() * 1000)
    latest_open = int((now - timedelta(minutes=5)).timestamp() * 1000)
    latest_close = int(now.timestamp() * 1000)
    return [
        [previous_open, "1.1900", "1.2100", "1.1800", "1.2050", "1200", previous_close, "150000.0", 120, "82000.0", "102000.0", "0"],
        [latest_open, "1.2050", "1.2650", "1.2000", "1.2570", "1800", latest_close, "230000.0", 200, "150000.0", "150000.0", "0"],
    ]


def _make_http_getter(*, ticker_payload: object, klines_payload: object):
    def _getter(req, timeout=0):  # noqa: ARG001
        url = req.full_url
        if "/api/v3/ticker/24hr" in url:
            return _FakeHTTPResponse(ticker_payload)
        if "/api/v3/klines" in url:
            return _FakeHTTPResponse(klines_payload)
        raise AssertionError(f"unexpected URL requested: {url}")

    return _getter


class ProviderChaosRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-provider-chaos-regression")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"
        self.store = InMemoryObjectStore()
        self.orchestrator = RuntimeOrchestrator(store=self.store)

    def _request(self, *, object_id: str = "chaos-object", subject: str = "AIX", scenario: str = "bullish_publish") -> ProviderRequest:
        return ProviderRequest(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp",
            scenario=scenario,
        )

    def _base_real_provider(self) -> RealCEXProvider:
        return RealCEXProvider(
            RealCEXProviderConfig(mode="live"),
            http_getter=_make_http_getter(
                ticker_payload=_good_ticker_payload("AIXUSDT"),
                klines_payload=_good_klines_payload(),
            ),
        )

    def _full_adapters(self, cex_provider) -> list:
        return [
            CEXSnapshotAdapter(provider=cex_provider),
            OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
            SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
        ]

    def _run_new_from_adapters(
        self,
        *,
        object_id: str,
        subject: str,
        scenario: str,
        adapters: list,
        orchestrator: RuntimeOrchestrator | None = None,
    ):
        runtime = self.orchestrator if orchestrator is None else orchestrator
        request = AdapterRequest(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp",
            scenario=scenario,
        )
        batches = collect_and_validate_batches(adapters, request)
        return runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=merge_adapter_batches(batches),
        )

    def _continue_existing_from_adapters(
        self,
        *,
        object_id: str,
        subject: str,
        scenario: str,
        adapters: list,
    ):
        session = self.store.load(object_id)
        request = AdapterRequest(
            object_id=object_id,
            object_type=session.research_object.object_type,
            subject=subject,
            scope=session.research_object.scope,
            scenario=scenario,
        )
        batches = collect_and_validate_batches(adapters, request)
        return self.orchestrator.continue_existing(
            object_id=object_id,
            signals=merge_adapter_batches(batches),
        )

    def test_invalid_chaos_payloads_are_rejected_by_adapter_boundary(self) -> None:
        invalid_scenarios = [
            "missing_field",
            "wrong_type",
            "future_timestamp",
            "retrograde_timestamp",
            "metadata_mismatch",
            "delayed_data",
            "schema_flip",
        ]
        for scenario in invalid_scenarios:
            with self.subTest(scenario=scenario):
                adapter = CEXSnapshotAdapter(provider=ChaosProviderWrapper(self._base_real_provider(), scenario))
                with self.assertRaises(AdapterValidationError):
                    adapter.collect(
                        AdapterRequest(
                            object_id="adapter-chaos",
                            object_type=ObjectType.ASSET,
                            subject="AIX",
                            scope="spot+perp",
                            scenario="bullish_publish",
                            time_horizon=self._request().time_horizon,
                        )
                    )

    def test_invalid_chaos_payloads_do_not_create_runtime_sessions(self) -> None:
        invalid_scenarios = [
            "missing_field",
            "wrong_type",
            "future_timestamp",
            "retrograde_timestamp",
            "metadata_mismatch",
            "delayed_data",
            "schema_flip",
        ]
        for scenario in invalid_scenarios:
            object_id = f"runtime-chaos-{scenario}"
            with self.subTest(scenario=scenario):
                with self.assertRaises(AdapterValidationError):
                    self._run_new_from_adapters(
                        object_id=object_id,
                        subject="AIX",
                        scenario="bullish_publish",
                        adapters=self._full_adapters(ChaosProviderWrapper(self._base_real_provider(), scenario)),
                    )
                self.assertFalse(self.store.exists(object_id))

    def test_empty_events_and_partial_truncation_degrade_without_publish(self) -> None:
        empty_result = self._run_new_from_adapters(
            object_id="chaos-empty-events",
            subject="AIX",
            scenario="bullish_publish",
            adapters=self._full_adapters(ChaosProviderWrapper(self._base_real_provider(), "empty_events")),
        )
        self.assertEqual(empty_result.decision.decision, "monitoring")
        self.assertEqual(empty_result.research_object.processing_state, ProcessingState.MONITORING)
        self.assertNotEqual(empty_result.research_object.processing_state, ProcessingState.PUBLISHED)

        truncated_result = self._run_new_from_adapters(
            object_id="chaos-truncated",
            subject="AIX",
            scenario="bullish_publish",
            adapters=self._full_adapters(ChaosProviderWrapper(self._base_real_provider(), "partial_truncation")),
        )
        self.assertEqual(truncated_result.decision.decision, "monitoring")
        self.assertEqual(truncated_result.research_object.processing_state, ProcessingState.MONITORING)
        self.assertNotEqual(truncated_result.research_object.processing_state, ProcessingState.PUBLISHED)

    def test_invalid_provider_input_does_not_pollute_existing_session(self) -> None:
        seed = self._run_new_from_adapters(
            object_id="chaos-existing-session",
            subject="AIX",
            scenario="bullish_publish",
            adapters=self._full_adapters(self._base_real_provider()),
        )
        before = self.store.load("chaos-existing-session")
        self.assertEqual(seed.decision.decision, "publish")

        with self.assertRaises(AdapterValidationError):
            self._continue_existing_from_adapters(
                object_id="chaos-existing-session",
                subject="AIX",
                scenario="bullish_publish",
                adapters=self._full_adapters(ChaosProviderWrapper(self._base_real_provider(), "missing_field")),
            )

        after = self.store.load("chaos-existing-session")
        self.assertEqual(after.research_object.processing_state, before.research_object.processing_state)
        self.assertEqual(after.research_object.risk_state, before.research_object.risk_state)
        self.assertEqual(len(after.claims), len(before.claims))
        self.assertEqual(after.latest_decision.decision, before.latest_decision.decision)

    def test_same_request_different_schema_second_call_is_rejected_and_session_stable(self) -> None:
        wrapper = ChaosProviderWrapper(self._base_real_provider(), ["pass_through", "schema_flip"])
        seed = self._run_new_from_adapters(
            object_id="chaos-schema-flip",
            subject="AIX",
            scenario="bullish_publish",
            adapters=self._full_adapters(wrapper),
        )
        self.assertEqual(seed.decision.decision, "publish")
        before = self.store.load("chaos-schema-flip")

        with self.assertRaises(AdapterValidationError):
            self._continue_existing_from_adapters(
                object_id="chaos-schema-flip",
                subject="AIX",
                scenario="bullish_publish",
                adapters=self._full_adapters(wrapper),
            )

        after = self.store.load("chaos-schema-flip")
        self.assertEqual(after.research_object.processing_state, before.research_object.processing_state)
        self.assertEqual(after.latest_decision.decision, before.latest_decision.decision)
        self.assertEqual(len(after.claims), len(before.claims))

    def test_recorded_real_payload_replays_to_identical_runtime_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_provider = RealCEXProvider(
                RealCEXProviderConfig(mode="record", raw_payload_dir=tmpdir),
                http_getter=_make_http_getter(
                    ticker_payload=_good_ticker_payload("AIXUSDT"),
                    klines_payload=_good_klines_payload(),
                ),
            )
            replay_provider = RealCEXProvider(
                RealCEXProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )

            record_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
            replay_runtime = RuntimeOrchestrator(store=InMemoryObjectStore())

            recorded = self._run_new_from_adapters(
                object_id="chaos-recorded",
                subject="AIX",
                scenario="bullish_publish",
                adapters=[
                    CEXSnapshotAdapter(provider=record_provider),
                    OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
                    SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
                ],
                orchestrator=record_runtime,
            )
            replayed = self._run_new_from_adapters(
                object_id="chaos-replayed",
                subject="AIX",
                scenario="bullish_publish",
                adapters=[
                    CEXSnapshotAdapter(provider=replay_provider),
                    OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
                    SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
                ],
                orchestrator=replay_runtime,
            )

            self.assertEqual(recorded.decision.decision, replayed.decision.decision)
            self.assertEqual(recorded.research_object.processing_state, replayed.research_object.processing_state)
            self.assertEqual(recorded.research_object.risk_state, replayed.research_object.risk_state)
            self.assertEqual(recorded.research_object.market_state, replayed.research_object.market_state)
            self.assertEqual(
                [(t.thesis_type.value, t.status.value, t.confidence, t.working_primary_streak) for t in recorded.theses],
                [(t.thesis_type.value, t.status.value, t.confidence, t.working_primary_streak) for t in replayed.theses],
            )


if __name__ == "__main__":
    unittest.main()
