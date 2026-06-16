from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.adapters.adapters import AdapterRequest, AdapterValidationError
from enhengclaw.core.enums import ObjectType
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderNetworkError, ProviderReplayError, ProviderRequest, ProviderSchemaError
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path
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


def _good_search_payload() -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "pairs": [
            {
                "chainId": "base",
                "dexId": "uniswap",
                "pairAddress": "0xa1",
                "url": "https://dexscreener.com/base/0xa1",
                "baseToken": {"symbol": "AIX", "name": "AIX", "address": "0xaix"},
                "quoteToken": {"symbol": "USDT", "name": "Tether", "address": "0xusdt"},
                "txns": {"h1": {"buys": 120, "sells": 80}},
                "volume": {"h24": 1540000},
                "liquidity": {"usd": 920000},
                "pairCreatedAt": 1775555400000,
            }
        ],
    }


def _make_http_getter(*, search_payload: object):
    def _getter(req, timeout=0):  # noqa: ARG001
        if "/latest/dex/search" not in req.full_url:
            raise AssertionError(f"unexpected URL requested: {req.full_url}")
        return _FakeHTTPResponse(search_payload)

    return _getter


class RealOnchainProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-real-onchain-provider")
        self.snapshot_root = ROOT / "fixtures" / "snapshots"

    def _provider_request(self, *, subject: str = "AIX", scenario: str = "bullish_publish") -> ProviderRequest:
        return ProviderRequest(
            object_id=f"real-onchain-{scenario}",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp",
            scenario=scenario,
        )

    def test_live_provider_returns_valid_onchain_provider_payload(self) -> None:
        provider = RealOnchainProvider(
            RealOnchainProviderConfig(mode="live"),
            http_getter=_make_http_getter(search_payload=_good_search_payload()),
        )
        payload = provider.fetch(self._provider_request())
        self.assertEqual(payload.metadata.provider_name, "dexscreener-public-onchain")
        self.assertEqual(payload.metadata.raw_record_count, 1)
        self.assertEqual(len(payload.raw_payload), 1)
        self.assertEqual(payload.raw_payload[0]["asset_symbol"], "AIX")
        self.assertIn("raw_http_pair_address", payload.raw_payload[0])

    def test_record_and_replay_roundtrip_is_compatible_with_onchain_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request = self._provider_request(scenario="bullish_publish")
            record_provider = RealOnchainProvider(
                RealOnchainProviderConfig(mode="record", raw_payload_dir=tmpdir),
                http_getter=_make_http_getter(search_payload=_good_search_payload()),
            )
            recorded = record_provider.fetch(request)
            replay_provider = RealOnchainProvider(
                RealOnchainProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )
            replayed = replay_provider.fetch(request)
            self.assertEqual(recorded.raw_payload, replayed.raw_payload)

            batch = OnchainSnapshotAdapter(provider=replay_provider).collect(
                AdapterRequest(
                    object_id=request.object_id,
                    object_type=request.object_type,
                    subject=request.subject,
                    scope=request.scope,
                    scenario=request.scenario,
                    time_horizon=request.time_horizon,
                )
            )
            self.assertEqual(len(batch.signals), 1)

    def test_bad_payload_and_bad_replay_are_rejected_without_polluting_store(self) -> None:
        store = InMemoryObjectStore()
        orchestrator = RuntimeOrchestrator(store=store)
        bad_provider = RealOnchainProvider(
            RealOnchainProviderConfig(mode="live"),
            http_getter=_make_http_getter(
                search_payload={
                    "schemaVersion": "1.0.0",
                    "pairs": [
                        {
                            "chainId": "base",
                            "baseToken": {"symbol": "AIX"},
                        }
                    ],
                },
            ),
        )
        with self.assertRaises(ProviderSchemaError):
            orchestrator.run_new_from_adapters(
                object_id="real-onchain-bad",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                adapters=[
                    CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
                    OnchainSnapshotAdapter(provider=bad_provider),
                ],
            )
        self.assertFalse(store.exists("real-onchain-bad"))

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = subject_key_path(
                Path(tmpdir),
                "broken",
                SubjectKey.build(
                    symbol="AIX",
                    venue="dexscreener-public-onchain",
                    instrument_type="onchain",
                ),
                "onchain_snapshot.csv",
            )
            bad_path.parent.mkdir(parents=True, exist_ok=True)
            bad_path.write_text("record_id,retrieved_at,provider\nbad-1,2026-04-07T10:00:00Z,\n", encoding="utf-8")
            replay_provider = RealOnchainProvider(
                RealOnchainProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )
            with self.assertRaises(ProviderReplayError):
                replay_provider.fetch(self._provider_request(scenario="broken"))

    def test_record_and_replay_use_subject_namespaced_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request = self._provider_request(scenario="namespaced_roundtrip")
            provider = RealOnchainProvider(
                RealOnchainProviderConfig(mode="record", raw_payload_dir=tmpdir),
                http_getter=_make_http_getter(search_payload=_good_search_payload()),
            )
            provider.fetch(request)
            replay_path = subject_key_path(
                Path(tmpdir),
                request.scenario,
                SubjectKey.build(
                    symbol=request.subject,
                    venue="dexscreener-public-onchain",
                    instrument_type="onchain",
                ),
                "onchain_snapshot.csv",
            )
            self.assertTrue(replay_path.exists())

    def test_cross_subject_replay_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request = self._provider_request(subject="BTC", scenario="cross_subject")
            replay_path = subject_key_path(
                Path(tmpdir),
                request.scenario,
                SubjectKey.build(
                    symbol=request.subject,
                    venue="dexscreener-public-onchain",
                    instrument_type="onchain",
                ),
                "onchain_snapshot.csv",
            )
            replay_path.parent.mkdir(parents=True, exist_ok=True)
            replay_path.write_text(
                "\n".join(
                    [
                        "record_id,retrieved_at,provider,asset_symbol,event_type,interpretation,claim_kind,signal_side,evidence_grade,confidence_score,horizon_label,scope_name,wallet_cluster,extra_note",
                        "row-1,2026-04-07T10:00:00Z,dexscreener-public-onchain,AIX,wallet_buy,foreign subject,flow,bullish,E4,80,intraday,spot+perp,dex_pair_flow,note",
                    ]
                ),
                encoding="utf-8",
            )
            replay_provider = RealOnchainProvider(
                RealOnchainProviderConfig(mode="replay", raw_payload_dir=tmpdir),
            )
            with self.assertRaises(ProviderReplayError):
                replay_provider.fetch(request)

    def test_network_errors_are_rejected(self) -> None:
        def failing_getter(req, timeout=0):  # noqa: ARG001
            raise OSError("network down")

        provider = RealOnchainProvider(RealOnchainProviderConfig(mode="live"), http_getter=failing_getter)
        with self.assertRaises(ProviderNetworkError):
            provider.fetch(self._provider_request())

    def test_real_onchain_provider_can_participate_in_runtime_when_enabled(self) -> None:
        provider = RealOnchainProvider(
            RealOnchainProviderConfig(mode="live"),
            http_getter=_make_http_getter(search_payload=_good_search_payload()),
        )
        runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        result = runtime.run_new_from_adapters(
            object_id="real-onchain-smoke",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
            adapters=[
                CEXSnapshotAdapter(provider=OfflineReplayCEXProvider(self.snapshot_root)),
                OnchainSnapshotAdapter(provider=provider),
            ],
        )
        self.assertEqual(result.runtime_result.decision.decision, "monitoring")
        self.assertGreaterEqual(result.runtime_result.research_object.attention_score, 69)


if __name__ == "__main__":
    unittest.main()
