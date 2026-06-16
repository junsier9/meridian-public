from __future__ import annotations

import json
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
from enhengclaw.core.enums import ObjectType
from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider, OfflineReplaySafetyProvider
from enhengclaw.providers.providers import ProviderNetworkError, ProviderReplayError, ProviderRequest, ProviderSchemaError
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter, SafetySnapshotAdapter
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path
from tests.test_helpers import enter_runtime_worker


class _FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
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


class RealCEXProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-real-cex-provider")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"

    def _request(self, *, subject: str = "AIX", scenario: str = "live_test") -> ProviderRequest:
        return ProviderRequest(
            object_id=f"real-cex-{scenario}",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp",
            scenario=scenario,
        )

    def test_live_provider_returns_valid_cex_provider_payload(self) -> None:
        provider = RealCEXProvider(
            RealCEXProviderConfig(mode="live", api_base_url="https://api.binance.com"),
            http_getter=_make_http_getter(
                ticker_payload=_good_ticker_payload("AIXUSDT"),
                klines_payload=_good_klines_payload(),
            ),
        )

        payload = provider.fetch(self._request())
        self.assertEqual(payload.metadata.provider_name, "binance-public-cex")
        self.assertEqual(payload.metadata.raw_record_count, 2)
        self.assertEqual(payload.raw_payload["instrument"], "AIXUSDT")
        self.assertEqual(len(payload.raw_payload["events"]), 2)
        self.assertIn("raw_http", payload.raw_payload)

    def test_record_and_replay_roundtrip_is_compatible_with_offline_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request = self._request(scenario="record_roundtrip")
            record_provider = RealCEXProvider(
                RealCEXProviderConfig(mode="record", raw_payload_dir=tmpdir),
                http_getter=_make_http_getter(
                    ticker_payload=_good_ticker_payload("AIXUSDT"),
                    klines_payload=_good_klines_payload(),
                ),
            )
            recorded = record_provider.fetch(request)
            replay_path = subject_key_path(
                Path(tmpdir),
                request.scenario,
                SubjectKey.build(
                    symbol=request.subject,
                    venue="binance-public-cex",
                    instrument_type="cex",
                ),
                "cex_snapshot.json",
            )
            self.assertTrue(replay_path.exists())

            replay_provider = RealCEXProvider(
                RealCEXProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )
            replayed = replay_provider.fetch(request)
            self.assertEqual(recorded.raw_payload, replayed.raw_payload)

            batch = CEXSnapshotAdapter(provider=replay_provider).collect(
                AdapterRequest(
                    object_id=request.object_id,
                    object_type=request.object_type,
                    subject=request.subject,
                    scope=request.scope,
                    scenario=request.scenario,
                    time_horizon=request.time_horizon,
                )
            )
            self.assertEqual(len(batch.signals), 2)

    def test_bad_payload_and_bad_replay_are_rejected_without_polluting_runtime_store(self) -> None:
        store = InMemoryObjectStore()
        orchestrator = RuntimeOrchestrator(store=store)
        bad_provider = RealCEXProvider(
            RealCEXProviderConfig(mode="live"),
            http_getter=_make_http_getter(
                ticker_payload={"symbol": "AIXUSDT", "quoteVolume": "1.0"},
                klines_payload=_good_klines_payload(),
            ),
        )

        with self.assertRaises(ProviderSchemaError):
            orchestrator.run_new_from_adapters(
                object_id="real-provider-bad-payload",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                adapters=[
                    CEXSnapshotAdapter(provider=bad_provider),
                    OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
                    SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
                ],
            )
        self.assertFalse(store.exists("real-provider-bad-payload"))

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = subject_key_path(
                Path(tmpdir),
                "broken_replay",
                SubjectKey.build(
                    symbol="AIX",
                    venue="binance-public-cex",
                    instrument_type="cex",
                ),
                "cex_snapshot.json",
            )
            bad_path.parent.mkdir(parents=True, exist_ok=True)
            bad_path.write_text(json.dumps({"provider": "", "events": []}), encoding="utf-8")
            replay_provider = RealCEXProvider(
                RealCEXProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )
            with self.assertRaises(ProviderReplayError):
                replay_provider.fetch(self._request(scenario="broken_replay"))

    def test_cross_subject_replay_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wrong_request = self._request(subject="BTC", scenario="cross_subject")
            wrong_path = subject_key_path(
                Path(tmpdir),
                wrong_request.scenario,
                SubjectKey.build(
                    symbol=wrong_request.subject,
                    venue="binance-public-cex",
                    instrument_type="cex",
                ),
                "cex_snapshot.json",
            )
            wrong_path.parent.mkdir(parents=True, exist_ok=True)
            wrong_path.write_text(
                json.dumps(
                    {
                        "provider": "binance-public-cex",
                        "retrieved_at": "2026-04-07T00:00:00Z",
                        "scenario_tag": "cross_subject",
                        "instrument": "BTCUSDT",
                        "events": [
                            {
                                "event_id": "btcusdt-spot-24h",
                                "event_name": "spot_24h_momentum",
                                "payload": {"asset": "AIX", "summary": "foreign subject", "metrics": {}},
                                "mapping": {
                                    "claimKind": "measurement",
                                    "bias": "bullish",
                                    "evidence": "E4",
                                    "confidenceScore": 80,
                                    "horizon": "intraday",
                                },
                                "extra": {"venue": "Binance", "market_type": "spot"},
                            }
                        ],
                        "raw_http": {},
                    }
                ),
                encoding="utf-8",
            )
            provider = RealCEXProvider(RealCEXProviderConfig(mode="replay", raw_payload_dir=tmpdir))
            with self.assertRaises(ProviderReplayError):
                provider.fetch(wrong_request)

    def test_network_and_empty_response_errors_are_rejected(self) -> None:
        def failing_getter(req, timeout=0):  # noqa: ARG001
            raise OSError("network down")

        provider = RealCEXProvider(RealCEXProviderConfig(mode="live"), http_getter=failing_getter)
        with self.assertRaises(ProviderNetworkError):
            provider.fetch(self._request())

        class _EmptyBodyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def read(self) -> bytes:
                return b""

        def empty_getter(req, timeout=0):  # noqa: ARG001
            return _EmptyBodyResponse()

        empty_provider = RealCEXProvider(RealCEXProviderConfig(mode="live"), http_getter=empty_getter)
        with self.assertRaises(ProviderSchemaError):
            empty_provider.fetch(self._request())

    def test_real_provider_adapter_runtime_smoke_path_with_mocked_http(self) -> None:
        provider = RealCEXProvider(
            RealCEXProviderConfig(mode="live"),
            http_getter=_make_http_getter(
                ticker_payload=_good_ticker_payload("AIXUSDT"),
                klines_payload=_good_klines_payload(),
            ),
        )
        orchestrator = RuntimeOrchestrator(store=InMemoryObjectStore())
        result = orchestrator.run_new_from_adapters(
            object_id="real-provider-smoke",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=[
                CEXSnapshotAdapter(provider=provider),
                OnchainSnapshotAdapter(provider=OfflineReplayOnchainProvider(self.snapshot_root)),
                SafetySnapshotAdapter(provider=OfflineReplaySafetyProvider(self.snapshot_root)),
            ],
        )
        self.assertEqual(result.runtime_result.decision.decision, "publish")
        self.assertEqual(result.runtime_result.research_object.processing_state.value, "published")


if __name__ == "__main__":
    unittest.main()
