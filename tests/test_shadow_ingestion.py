from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
from enhengclaw.ingress.shadow_schema import (
    CrossSubjectViolationError,
    SHADOW_SCHEMA_VERSION,
    ValidatedShadowEvent,
)
from enhengclaw.orchestration import ingestion_worker as ingestion_worker_module
from enhengclaw.orchestration.ingestion_worker import ShadowIngestionEnvironment, ShadowIngestionRequest
from enhengclaw.orchestration.shadow_ingestion_providers import build_legacy_provider_payloads
from enhengclaw.orchestration.shadow_ingestion_runner import main as shadow_ingestion_main
from enhengclaw.orchestration.worker_operations import SubprocessAuditResult
from enhengclaw.orchestration.worker_operations import StreamCaptureMetrics
from enhengclaw.orchestration.worker_operations import heartbeat_task_lock
from enhengclaw.providers.alchemy_bitcoin_shadow_provider import AlchemyBitcoinShadowConfig, AlchemyBitcoinShadowProvider
from enhengclaw.providers.alchemy_shadow_provider import AlchemyEthShadowConfig, AlchemyEthShadowProvider
from enhengclaw.providers.alchemy_solana_shadow_provider import AlchemySolanaShadowConfig, AlchemySolanaShadowProvider
from enhengclaw.providers.binance_shadow_provider import BinanceTradeShadowConfig, BinanceTradeShadowProvider
from enhengclaw.providers.shadow_common import ExponentialBackoffConfig, FatalTransportError, MissingEnvironmentVariableError, RetryableTransportError
from enhengclaw.utils.subject_keys import SubjectKey


def _read_all_jsonl(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


class _FakeWebSocket:
    def __init__(
        self,
        payloads: list[dict[str, object]],
        *,
        block_when_empty: bool = False,
    ) -> None:
        self._messages = [
            json.dumps(payload, separators=(",", ":"), sort_keys=True)
            for payload in payloads
        ]
        self.sent_payloads: list[dict[str, object]] = []
        self._block_when_empty = block_when_empty

    async def __aenter__(self) -> "_FakeWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def send(self, payload: str) -> None:
        self.sent_payloads.append(json.loads(payload))

    async def recv(self) -> str:
        if not self._messages:
            if self._block_when_empty:
                while True:
                    await asyncio.sleep(3600)
            raise AssertionError("unexpected websocket recv after scripted payloads were exhausted")
        return self._messages.pop(0)


class ShadowIngestionTests(unittest.TestCase):
    def test_controller_only_serializes_request_and_dispatches_ingestion_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            fake_permit = Path(tmpdir) / "missing_permit.json"
            captured: dict[str, object] = {}

            def _fake_run(command: list[str], *, env: dict[str, str], run_root: Path):
                request_path = Path(command[command.index("--request") + 1])
                captured["command"] = list(command)
                captured["env"] = dict(env)
                captured["request_path"] = request_path
                captured["payload"] = json.loads(request_path.read_text(encoding="utf-8"))
                captured["run_root"] = run_root
                return SubprocessAuditResult(
                    returncode=0,
                    worker_pid=4242,
                    stdout=StreamCaptureMetrics("stdout", 0, 0, False, 0),
                    stderr=StreamCaptureMetrics("stderr", 0, 0, False, 0),
                )

            exit_code = None
            with patch(
                "enhengclaw.orchestration.shadow_ingestion_runner.audited_subprocess_run",
                new=_fake_run,
            ):
                exit_code = shadow_ingestion_main(
                    [
                        "--artifacts-root",
                        str(artifacts_root),
                        "--execution-permit",
                        str(fake_permit),
                        "--run-seconds",
                        "15",
                        "--log-level",
                        "DEBUG",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                captured["command"][1:4],
                ["-m", "enhengclaw.orchestration.ingestion_worker", "--request"],
            )
            self.assertTrue(str(Path(captured["command"][4])).endswith("request.json"))
            self.assertEqual(
                captured["command"][5:],
                ["--permit", str(fake_permit.resolve())],
            )
            self.assertEqual(
                captured["payload"]["payload"],
                {
                    "artifacts_root": str(artifacts_root.resolve()),
                    "provider_config_path": None,
                    "providers": build_legacy_provider_payloads(
                        binance_websocket_url="wss://stream.binance.com:9443/ws",
                        binance_receive_timeout_seconds=20.0,
                        binance_initial_backoff_seconds=1.0,
                        binance_max_backoff_seconds=5.0,
                        binance_max_reconnect_attempts=None,
                        alchemy_poll_interval_seconds=5.0,
                        alchemy_request_timeout_seconds=10.0,
                        alchemy_initial_backoff_seconds=1.0,
                        alchemy_max_backoff_seconds=20.0,
                        alchemy_max_retry_attempts=5,
                        alchemy_degraded_after_failures=3,
                        disable_eth_get_block_by_number=False,
                        alchemy_endpoint_url=None,
                    ),
                    "run_seconds": 15.0,
                    "log_level": "DEBUG",
                    "simulation_profile": "real",
                    "synthetic_event_interval_seconds": 1.0,
                    "synthetic_quarantine_every": 10,
                    "binance_receive_timeout_seconds": 20.0,
                    "binance_initial_backoff_seconds": 1.0,
                    "binance_max_backoff_seconds": 5.0,
                    "binance_max_reconnect_attempts": None,
                    "binance_websocket_url": "wss://stream.binance.com:9443/ws",
                    "alchemy_poll_interval_seconds": 5.0,
                    "alchemy_request_timeout_seconds": 10.0,
                    "alchemy_initial_backoff_seconds": 1.0,
                    "alchemy_max_backoff_seconds": 20.0,
                    "alchemy_max_retry_attempts": 5,
                    "alchemy_degraded_after_failures": 3,
                    "disable_eth_get_block_by_number": False,
                    "alchemy_endpoint_url": None,
                },
            )
            self.assertEqual(captured["payload"]["request_kind"], "ingestion")
            self.assertEqual(captured["payload"]["schema_version"], "worker-request.v1")
            self.assertFalse((artifacts_root / "live_replay").exists())
            self.assertFalse((artifacts_root / "live_quarantine").exists())
            self.assertFalse(Path(captured["request_path"]).exists())

    def test_controller_loads_explicit_provider_config_and_embeds_expanded_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            fake_permit = Path(tmpdir) / "missing_permit.json"
            provider_config = Path(tmpdir) / "providers.json"
            provider_config.write_text(
                json.dumps(
                    {
                        "providers": [
                            {
                                "kind": "binance_trade",
                                "provider_id": "binance.spot.ws",
                                "subject_key": "BTCUSDT.binance.spot",
                                "symbol": "BTCUSDT",
                                "websocket_url": "wss://stream.binance.com:9443/ws",
                                "receive_timeout_seconds": 20.0,
                                "initial_backoff_seconds": 1.0,
                                "max_backoff_seconds": 5.0,
                                "max_reconnect_attempts": None,
                            },
                            {
                                "kind": "alchemy_solana_block",
                                "provider_id": "alchemy.sol.rpc",
                                "subject_key": "SOL.alchemy.onchain",
                                "symbol": "SOL",
                                "network": "solana-mainnet",
                                "endpoint_url": None,
                                "poll_interval_seconds": 5.0,
                                "request_timeout_seconds": 10.0,
                                "initial_backoff_seconds": 1.0,
                                "max_backoff_seconds": 20.0,
                                "max_retry_attempts": 5,
                                "degraded_after_failures": 3,
                                "include_block_details": True,
                                "commitment": "finalized",
                                "encoding": "json",
                                "transaction_details": "none",
                            },
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            def _fake_run(command: list[str], *, env: dict[str, str], run_root: Path):
                request_path = Path(command[command.index("--request") + 1])
                captured["payload"] = json.loads(request_path.read_text(encoding="utf-8"))
                return SubprocessAuditResult(
                    returncode=0,
                    worker_pid=4242,
                    stdout=StreamCaptureMetrics("stdout", 0, 0, False, 0),
                    stderr=StreamCaptureMetrics("stderr", 0, 0, False, 0),
                )

            with patch(
                "enhengclaw.orchestration.shadow_ingestion_runner.audited_subprocess_run",
                new=_fake_run,
            ):
                exit_code = shadow_ingestion_main(
                    [
                        "--artifacts-root",
                        str(artifacts_root),
                        "--execution-permit",
                        str(fake_permit),
                        "--provider-config",
                        str(provider_config),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = captured["payload"]["payload"]
            self.assertEqual(payload["provider_config_path"], str(provider_config.resolve()))
            self.assertEqual(
                [provider["subject_key"] for provider in payload["providers"]],
                ["BTCUSDT.binance.spot", "SOL.alchemy.onchain"],
            )

    def test_subject_key_stable_string_and_live_replay_layout(self) -> None:
        subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
        self.assertEqual(subject_key.as_stable_string(), "BTCUSDT.binance.spot")

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = LiveReplayWriter(tmpdir)
            event = ValidatedShadowEvent(
                subject_key=subject_key,
                provider_id="binance.spot.ws",
                event_type="trade",
                source_timestamp="2026-04-08T00:00:00.000Z",
                raw_payload={"stream": "btcusdt@trade"},
                schema_version=SHADOW_SCHEMA_VERSION,
                event_id="sha256:test",
            )
            result = writer.write(event=event)
            replay_path = Path(result.path)
            self.assertTrue(replay_path.exists())
            self.assertEqual(replay_path.parent.parent.name, "BTCUSDT.binance.spot")
            lines = replay_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["subject_key"], "BTCUSDT.binance.spot")
            self.assertEqual(record["provider_id"], "binance.spot.ws")
            self.assertEqual(record["event_id"], "sha256:test")

    def test_binance_provider_writes_replay_and_quarantines_invalid_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                    )
                    provider.process_message(
                        {
                            "stream": "btcusdt@trade",
                            "data": {
                                "e": "trade",
                                "E": 1712534400000,
                                "s": "BTCUSDT",
                                "t": 123456,
                                "p": "68750.10",
                                "q": "0.005",
                                "T": 1712534400001,
                            },
                        }
                    )
                    provider.process_message(
                        {
                            "stream": "ethusdt@trade",
                            "data": {
                                "e": "trade",
                                "E": 1712534400002,
                                "s": "ETHUSDT",
                                "t": 999,
                                "p": "3520.10",
                            },
                        }
                    )

            replay_rows = _read_all_jsonl(Path(replay_dir))
            quarantine_rows = _read_all_jsonl(Path(quarantine_dir))
            self.assertEqual(len(replay_rows), 1)
            self.assertEqual(replay_rows[0]["subject_key"], "BTCUSDT.binance.spot")
            self.assertEqual(replay_rows[0]["event_type"], "trade")

            self.assertEqual(len(quarantine_rows), 1)
            self.assertEqual(quarantine_rows[0]["subject_key"], "ETHUSDT.binance.spot")
            self.assertIn("data.q", quarantine_rows[0]["reason"])

    def test_binance_provider_hard_fails_on_cross_subject_payload(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                    )
                    with self.assertRaises(CrossSubjectViolationError):
                        provider.process_message(
                            {
                                "stream": "solusdt@trade",
                                "data": {
                                    "e": "trade",
                                    "E": 1712534400000,
                                    "s": "SOLUSDT",
                                    "t": 1,
                                    "p": "120.1",
                                    "q": "2.5",
                                },
                            }
                        )

            replay_rows = _read_all_jsonl(Path(replay_dir))
            quarantine_rows = _read_all_jsonl(Path(quarantine_dir))
            self.assertEqual(replay_rows, [])
            self.assertEqual(len(quarantine_rows), 1)
            self.assertEqual(quarantine_rows[0]["subject_key"], "SOLUSDT.binance.spot")

    def test_binance_provider_recovers_from_checkpoint_and_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            checkpoint_path = Path(state_dir) / "binance_trade_checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "binance.spot.ws",
                        "last_trade_ids": {"BTCUSDT": 100},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            def fetch_historical(symbol: str, from_trade_id: int) -> list[dict[str, object]]:
                self.assertEqual(symbol, "BTCUSDT")
                if from_trade_id == 101:
                    return [
                        {
                            "id": 101,
                            "price": "71545.44",
                            "qty": "0.001",
                            "time": 1775987588152,
                            "isBuyerMaker": True,
                            "isBestMatch": True,
                        },
                        {
                            "id": 102,
                            "price": "71545.45",
                            "qty": "0.002",
                            "time": 1775987588395,
                            "isBuyerMaker": False,
                            "isBestMatch": True,
                        },
                    ]
                return []

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )
                    provider._fetch_historical_trades = fetch_historical  # type: ignore[method-assign]
                    asyncio.run(provider._recover_gap_best_effort(asyncio.Event()))
                    provider.process_message(
                        {
                            "stream": "btcusdt@trade",
                            "data": {
                                "e": "trade",
                                "E": 1775987588395,
                                "s": "BTCUSDT",
                                "t": 102,
                                "p": "71545.45",
                                "q": "0.002",
                                "T": 1775987588395,
                            },
                        }
                    )

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual(len(replay_rows), 2)
            self.assertEqual([row["raw_payload"]["data"]["t"] for row in replay_rows], [101, 102])
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_trade_ids"]["BTCUSDT"], 102)

    def test_binance_provider_warns_when_catch_up_hits_page_cap(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            checkpoint_path = Path(state_dir) / "binance_trade_checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "binance.spot.ws",
                        "last_trade_ids": {"BTCUSDT": 100},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            def fetch_historical(symbol: str, from_trade_id: int) -> list[dict[str, object]]:
                self.assertEqual(symbol, "BTCUSDT")
                return [
                    {
                        "id": from_trade_id,
                        "price": "71545.44",
                        "qty": "0.001",
                        "time": 1775987588152,
                        "isBuyerMaker": True,
                        "isBestMatch": True,
                    },
                    {
                        "id": from_trade_id + 1,
                        "price": "71545.45",
                        "qty": "0.002",
                        "time": 1775987588395,
                        "isBuyerMaker": False,
                        "isBestMatch": True,
                    },
                ]

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            historical_trade_limit=2,
                            historical_trade_max_pages=2,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )
                    provider._fetch_historical_trades = fetch_historical  # type: ignore[method-assign]
                    with self.assertLogs("BinanceTradeShadowProvider", level="WARNING") as captured_logs:
                        asyncio.run(provider._recover_gap_best_effort(asyncio.Event()))

            self.assertTrue(
                any("hit the configured page cap" in message for message in captured_logs.output)
            )

    def test_binance_provider_splits_checkpoint_paths_by_socket_label(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    btc_provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("BTCUSDT",),
                            socket_label="BTCUSDT",
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )
                    eth_provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("ETHUSDT",),
                            socket_label="ETHUSDT",
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )

            self.assertEqual(
                btc_provider.checkpoint_path,
                Path(state_dir).resolve() / "binance" / "BTCUSDT" / "binance_trade_checkpoint.json",
            )
            self.assertEqual(
                eth_provider.checkpoint_path,
                Path(state_dir).resolve() / "binance" / "ETHUSDT" / "binance_trade_checkpoint.json",
            )
            self.assertNotEqual(btc_provider.checkpoint_path, eth_provider.checkpoint_path)

    def test_ingestion_worker_builds_split_socket_binance_providers_for_real_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            request = ShadowIngestionRequest.from_payload(
                {
                    "artifacts_root": replay_dir,
                    "run_seconds": 15.0,
                    "log_level": "INFO",
                    "simulation_profile": "real",
                    "synthetic_event_interval_seconds": 1.0,
                    "synthetic_quarantine_every": 10,
                    "binance_receive_timeout_seconds": 20.0,
                    "binance_initial_backoff_seconds": 1.0,
                    "binance_max_backoff_seconds": 5.0,
                    "binance_max_reconnect_attempts": None,
                    "binance_websocket_url": "wss://stream.binance.com:9443/ws",
                    "alchemy_poll_interval_seconds": 5.0,
                    "alchemy_request_timeout_seconds": 10.0,
                    "alchemy_initial_backoff_seconds": 1.0,
                    "alchemy_max_backoff_seconds": 20.0,
                    "alchemy_max_retry_attempts": 5,
                    "alchemy_degraded_after_failures": 3,
                    "disable_eth_get_block_by_number": False,
                    "alchemy_endpoint_url": None,
                }
            )
            replay_writer = LiveReplayWriter(replay_dir)
            quarantine_writer = LiveQuarantineWriter(quarantine_dir)
            binance_calls: list[dict[str, object]] = []
            alchemy_calls: list[dict[str, object]] = []

            class _FakeBinanceProvider:
                def __init__(self, **kwargs: object) -> None:
                    binance_calls.append(kwargs)

            class _FakeAlchemyProvider:
                def __init__(self, **kwargs: object) -> None:
                    alchemy_calls.append(kwargs)

            with patch.object(ingestion_worker_module, "BinanceTradeShadowProvider", _FakeBinanceProvider):
                with patch.object(ingestion_worker_module, "AlchemyEthShadowProvider", _FakeAlchemyProvider):
                    providers = ingestion_worker_module._build_real_shadow_providers(
                        request=request,
                        replay_writer=replay_writer,
                        quarantine_writer=quarantine_writer,
                        health_monitor=ingestion_worker_module.DataHealthMonitor(),
                        provider_state_root=Path(state_dir),
                    )

            self.assertEqual(len(providers), 3)
            self.assertEqual(len(binance_calls), 2)
            self.assertEqual(len(alchemy_calls), 1)
            self.assertEqual(
                [call["config"].symbols for call in binance_calls],
                [("BTCUSDT",), ("ETHUSDT",)],
            )
            self.assertEqual(
                [call["config"].socket_label for call in binance_calls],
                ["BTCUSDT", "ETHUSDT"],
            )
            self.assertTrue(all(call["state_root"] == Path(state_dir) for call in binance_calls))

    def test_ingestion_worker_builds_multi_chain_providers_from_explicit_provider_list(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            request = ShadowIngestionRequest.from_payload(
                {
                    "artifacts_root": replay_dir,
                    "providers": [
                        {
                            "kind": "binance_trade",
                            "provider_id": "binance.spot.ws",
                            "subject_key": "BTCUSDT.binance.spot",
                            "symbol": "BTCUSDT",
                            "websocket_url": "wss://stream.binance.com:9443/ws",
                            "receive_timeout_seconds": 20.0,
                            "initial_backoff_seconds": 1.0,
                            "max_backoff_seconds": 5.0,
                            "max_reconnect_attempts": None,
                        },
                        {
                            "kind": "alchemy_evm_block",
                            "provider_id": "alchemy.bnb.rpc",
                            "subject_key": "BNB.alchemy.onchain",
                            "symbol": "BNB",
                            "network": "bnb-mainnet",
                            "endpoint_url": None,
                            "poll_interval_seconds": 5.0,
                            "request_timeout_seconds": 10.0,
                            "initial_backoff_seconds": 1.0,
                            "max_backoff_seconds": 20.0,
                            "max_retry_attempts": 5,
                            "degraded_after_failures": 3,
                            "include_block_details": True,
                        },
                        {
                            "kind": "alchemy_bitcoin_block",
                            "provider_id": "alchemy.btc.rpc",
                            "subject_key": "BTC.alchemy.onchain",
                            "symbol": "BTC",
                            "network": "bitcoin-mainnet",
                            "endpoint_url": None,
                            "poll_interval_seconds": 5.0,
                            "request_timeout_seconds": 10.0,
                            "initial_backoff_seconds": 1.0,
                            "max_backoff_seconds": 20.0,
                            "max_retry_attempts": 5,
                            "degraded_after_failures": 3,
                            "include_block_details": True,
                        },
                        {
                            "kind": "alchemy_solana_block",
                            "provider_id": "alchemy.sol.rpc",
                            "subject_key": "SOL.alchemy.onchain",
                            "symbol": "SOL",
                            "network": "solana-mainnet",
                            "endpoint_url": None,
                            "poll_interval_seconds": 5.0,
                            "request_timeout_seconds": 10.0,
                            "initial_backoff_seconds": 1.0,
                            "max_backoff_seconds": 20.0,
                            "max_retry_attempts": 5,
                            "degraded_after_failures": 3,
                            "include_block_details": True,
                            "commitment": "finalized",
                            "encoding": "json",
                            "transaction_details": "none",
                        },
                    ],
                    "run_seconds": 15.0,
                    "log_level": "INFO",
                    "simulation_profile": "real",
                    "synthetic_event_interval_seconds": 1.0,
                    "synthetic_quarantine_every": 10,
                    "binance_receive_timeout_seconds": 20.0,
                    "binance_initial_backoff_seconds": 1.0,
                    "binance_max_backoff_seconds": 5.0,
                    "binance_max_reconnect_attempts": None,
                    "binance_websocket_url": "wss://stream.binance.com:9443/ws",
                    "alchemy_poll_interval_seconds": 5.0,
                    "alchemy_request_timeout_seconds": 10.0,
                    "alchemy_initial_backoff_seconds": 1.0,
                    "alchemy_max_backoff_seconds": 20.0,
                    "alchemy_max_retry_attempts": 5,
                    "alchemy_degraded_after_failures": 3,
                    "disable_eth_get_block_by_number": False,
                    "alchemy_endpoint_url": None,
                }
            )
            replay_writer = LiveReplayWriter(replay_dir)
            quarantine_writer = LiveQuarantineWriter(quarantine_dir)
            binance_calls: list[dict[str, object]] = []
            evm_calls: list[dict[str, object]] = []
            bitcoin_calls: list[dict[str, object]] = []
            solana_calls: list[dict[str, object]] = []

            class _FakeBinanceProvider:
                def __init__(self, **kwargs: object) -> None:
                    binance_calls.append(kwargs)

            class _FakeAlchemyProvider:
                def __init__(self, **kwargs: object) -> None:
                    evm_calls.append(kwargs)

            class _FakeBitcoinProvider:
                def __init__(self, **kwargs: object) -> None:
                    bitcoin_calls.append(kwargs)

            class _FakeSolanaProvider:
                def __init__(self, **kwargs: object) -> None:
                    solana_calls.append(kwargs)

            with patch.object(ingestion_worker_module, "BinanceTradeShadowProvider", _FakeBinanceProvider):
                with patch.object(ingestion_worker_module, "AlchemyEthShadowProvider", _FakeAlchemyProvider):
                    with patch.object(ingestion_worker_module, "AlchemyBitcoinShadowProvider", _FakeBitcoinProvider):
                        with patch.object(ingestion_worker_module, "AlchemySolanaShadowProvider", _FakeSolanaProvider):
                            providers = ingestion_worker_module._build_real_shadow_providers(
                                request=request,
                                replay_writer=replay_writer,
                                quarantine_writer=quarantine_writer,
                                health_monitor=ingestion_worker_module.DataHealthMonitor(),
                                provider_state_root=Path(state_dir),
                            )

            self.assertEqual(len(providers), 4)
            self.assertEqual(len(binance_calls), 1)
            self.assertEqual(len(evm_calls), 1)
            self.assertEqual(len(bitcoin_calls), 1)
            self.assertEqual(len(solana_calls), 1)
            self.assertEqual(evm_calls[0]["config"].provider_id, "alchemy.bnb.rpc")
            self.assertEqual(evm_calls[0]["config"].subject_key, "BNB.alchemy.onchain")
            self.assertEqual(
                evm_calls[0]["state_root"],
                Path(state_dir) / "alchemy" / "bnb",
            )
            self.assertEqual(bitcoin_calls[0]["config"].provider_id, "alchemy.btc.rpc")
            self.assertEqual(bitcoin_calls[0]["config"].subject_key, "BTC.alchemy.onchain")
            self.assertEqual(
                bitcoin_calls[0]["state_root"],
                Path(state_dir) / "alchemy" / "btc",
            )
            self.assertEqual(solana_calls[0]["config"].provider_id, "alchemy.sol.rpc")
            self.assertEqual(solana_calls[0]["config"].subject_key, "SOL.alchemy.onchain")
            self.assertEqual(
                solana_calls[0]["state_root"],
                Path(state_dir) / "alchemy" / "sol",
            )

    def test_binance_runtime_session_disables_client_ping_and_sets_transport_timeouts(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            fake_websocket = _FakeWebSocket(
                [
                    {"id": 1, "result": None},
                    {
                        "stream": "btcusdt@trade",
                        "data": {
                            "e": "trade",
                            "E": 1775987589000,
                            "s": "BTCUSDT",
                            "t": 500,
                            "p": "71546.00",
                            "q": "0.003",
                            "T": 1775987589000,
                        },
                    },
                ]
            )
            captured_connect: dict[str, object] = {}

            def fake_connect(url: str, **kwargs: object) -> _FakeWebSocket:
                captured_connect["url"] = url
                captured_connect["kwargs"] = dict(kwargs)
                return fake_websocket

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(receive_timeout_seconds=7.5),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                        websocket_connect=fake_connect,
                    )
                    stop_event = asyncio.Event()
                    original_process_message = provider.process_message

                    def wrapped_process_message(payload: object, *, origin: str = "live") -> bool:
                        ack_received = original_process_message(payload, origin=origin)
                        symbol, trade_id = provider._extract_trade_identity(payload)
                        if symbol == "BTCUSDT" and trade_id == 500:
                            stop_event.set()
                        return ack_received

                    provider.process_message = wrapped_process_message  # type: ignore[method-assign]
                    asyncio.run(
                        asyncio.wait_for(
                            provider._run_session(stop_event),
                            timeout=0.5,
                        )
                    )

            self.assertEqual(captured_connect["url"], "wss://stream.binance.com:9443/ws")
            self.assertEqual(
                captured_connect["kwargs"],
                {
                    "ping_interval": None,
                    "ping_timeout": None,
                    "open_timeout": 7.5,
                    "close_timeout": 5.0,
                },
            )

    def test_binance_run_reconnects_after_receive_timeout_and_resumes_live_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            session_one = _FakeWebSocket(
                [{"id": 1, "result": None}],
                block_when_empty=True,
            )
            session_two = _FakeWebSocket(
                [
                    {"id": 1, "result": None},
                    {
                        "stream": "btcusdt@trade",
                        "data": {
                            "e": "trade",
                            "E": 1775987589000,
                            "s": "BTCUSDT",
                            "t": 500,
                            "p": "71546.00",
                            "q": "0.003",
                            "T": 1775987589000,
                        },
                    },
                ]
            )
            sessions = [session_one, session_two]
            connect_kwargs: list[dict[str, object]] = []

            def fake_connect(*args: object, **kwargs: object) -> _FakeWebSocket:
                connect_kwargs.append(dict(kwargs))
                if not sessions:
                    raise AssertionError("unexpected websocket reconnect after scripted sessions were exhausted")
                return sessions.pop(0)

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            receive_timeout_seconds=0.01,
                            reconnect_backoff=ExponentialBackoffConfig(
                                initial_delay_seconds=0.0,
                                max_delay_seconds=0.0,
                                multiplier=2.0,
                                max_attempts=1,
                            ),
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                        websocket_connect=fake_connect,
                    )
                    stop_event = asyncio.Event()
                    original_process_message = provider.process_message

                    def wrapped_process_message(payload: object, *, origin: str = "live") -> bool:
                        ack_received = original_process_message(payload, origin=origin)
                        symbol, trade_id = provider._extract_trade_identity(payload)
                        if symbol == "BTCUSDT" and trade_id == 500:
                            stop_event.set()
                        return ack_received

                    provider.process_message = wrapped_process_message  # type: ignore[method-assign]
                    with self.assertLogs("BinanceTradeShadowProvider", level="INFO") as captured_logs:
                        asyncio.run(
                            asyncio.wait_for(
                                provider.run(stop_event),
                                timeout=1.0,
                            )
                        )

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual([row["raw_payload"]["data"]["t"] for row in replay_rows], [500])
            self.assertEqual(len(connect_kwargs), 2)
            self.assertTrue(
                all(
                    kwargs["ping_interval"] is None and kwargs["ping_timeout"] is None
                    for kwargs in connect_kwargs
                )
            )
            self.assertTrue(
                any("reconnect attempt" in message for message in captured_logs.output)
            )
            self.assertTrue(
                any(
                    "subscription ack received after reconnect" in message
                    for message in captured_logs.output
                )
            )

    def test_binance_symbol_live_gap_watchdog_forces_reconnect_for_missing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("BTCUSDT", "ETHUSDT"),
                            symbol_live_gap_threshold_seconds=0.05,
                            symbol_live_gap_check_interval_seconds=0.01,
                            post_ack_symbol_grace_seconds=0.0,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )

                    async def run_watchdog() -> str:
                        stop_event = asyncio.Event()
                        reconnect_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                        provider._subscription_ack_monotonic = time.monotonic()
                        watchdog_task = asyncio.create_task(
                            provider._watch_live_symbol_gaps(
                                stop_event=stop_event,
                                reconnect_signal=reconnect_signal,
                            )
                        )
                        try:
                            for trade_id in range(1, 4):
                                now_ms = int(time.time() * 1000)
                                provider.process_message(
                                    {
                                        "stream": "btcusdt@trade",
                                        "data": {
                                            "e": "trade",
                                            "E": now_ms,
                                            "s": "BTCUSDT",
                                            "t": trade_id,
                                            "p": "71546.00",
                                            "q": "0.003",
                                            "T": now_ms,
                                        },
                                    },
                                    origin="live",
                                )
                                await asyncio.sleep(0.02)
                            return await asyncio.wait_for(reconnect_signal, timeout=0.2)
                        finally:
                            stop_event.set()
                            watchdog_task.cancel()
                            try:
                                await watchdog_task
                            except asyncio.CancelledError:
                                pass

                    reason = asyncio.run(run_watchdog())

            self.assertIn("ETHUSDT live receive gap exceeded", reason)

    def test_binance_historical_catch_up_does_not_feed_live_gap_watchdog(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("ETHUSDT",),
                            symbol_live_gap_threshold_seconds=0.05,
                            symbol_live_gap_check_interval_seconds=0.01,
                            post_ack_symbol_grace_seconds=0.0,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )

                    async def run_watchdog() -> str:
                        stop_event = asyncio.Event()
                        reconnect_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                        provider._subscription_ack_monotonic = time.monotonic()
                        watchdog_task = asyncio.create_task(
                            provider._watch_live_symbol_gaps(
                                stop_event=stop_event,
                                reconnect_signal=reconnect_signal,
                            )
                        )
                        try:
                            now_ms = int(time.time() * 1000)
                            provider.process_message(
                                {
                                    "stream": "ethusdt@trade",
                                    "data": {
                                        "e": "trade",
                                        "E": now_ms,
                                        "s": "ETHUSDT",
                                        "t": 10,
                                        "p": "3520.10",
                                        "q": "0.5",
                                        "T": now_ms,
                                    },
                                },
                                origin="historical",
                            )
                            return await asyncio.wait_for(reconnect_signal, timeout=0.2)
                        finally:
                            stop_event.set()
                            watchdog_task.cancel()
                            try:
                                await watchdog_task
                            except asyncio.CancelledError:
                                pass

                    reason = asyncio.run(run_watchdog())

            self.assertIn("ETHUSDT live receive gap exceeded", reason)

    def test_split_socket_watchdogs_do_not_cross_trip_other_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    btc_provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("BTCUSDT",),
                            socket_label="BTCUSDT",
                            symbol_live_gap_threshold_seconds=0.05,
                            symbol_live_gap_check_interval_seconds=0.01,
                            post_ack_symbol_grace_seconds=0.0,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )
                    eth_provider = BinanceTradeShadowProvider(
                        config=BinanceTradeShadowConfig(
                            symbols=("ETHUSDT",),
                            socket_label="ETHUSDT",
                            symbol_live_gap_threshold_seconds=0.05,
                            symbol_live_gap_check_interval_seconds=0.01,
                            post_ack_symbol_grace_seconds=0.0,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )

                    async def run_watchdogs() -> tuple[str, bool]:
                        stop_event = asyncio.Event()
                        btc_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                        eth_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                        btc_provider._subscription_ack_monotonic = time.monotonic()
                        eth_provider._subscription_ack_monotonic = time.monotonic()
                        btc_task = asyncio.create_task(
                            btc_provider._watch_live_symbol_gaps(
                                stop_event=stop_event,
                                reconnect_signal=btc_signal,
                            )
                        )
                        eth_task = asyncio.create_task(
                            eth_provider._watch_live_symbol_gaps(
                                stop_event=stop_event,
                                reconnect_signal=eth_signal,
                            )
                        )
                        try:
                            for trade_id in range(1, 4):
                                now_ms = int(time.time() * 1000)
                                eth_provider.process_message(
                                    {
                                        "stream": "ethusdt@trade",
                                        "data": {
                                            "e": "trade",
                                            "E": now_ms,
                                            "s": "ETHUSDT",
                                            "t": trade_id,
                                            "p": "3520.10",
                                            "q": "0.5",
                                            "T": now_ms,
                                        },
                                    },
                                    origin="live",
                                )
                                await asyncio.sleep(0.02)
                            btc_reason = await asyncio.wait_for(btc_signal, timeout=0.2)
                            await asyncio.sleep(0.02)
                            return btc_reason, eth_signal.done()
                        finally:
                            stop_event.set()
                            for task in (btc_task, eth_task):
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass

                    btc_reason, eth_triggered = asyncio.run(run_watchdogs())

            self.assertIn("BTCUSDT live receive gap exceeded", btc_reason)
            self.assertFalse(eth_triggered)

    def test_binance_reconnect_recovers_live_before_background_catch_up_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            checkpoint_path = Path(state_dir) / "binance_trade_checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "binance.spot.ws",
                        "last_trade_ids": {"BTCUSDT": 100},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            fake_websocket = _FakeWebSocket(
                [
                    {"id": 1, "result": None},
                    {
                        "stream": "btcusdt@trade",
                        "data": {
                            "e": "trade",
                            "E": 1775987589000,
                            "s": "BTCUSDT",
                            "t": 500,
                            "p": "71546.00",
                            "q": "0.003",
                            "T": 1775987589000,
                        },
                    },
                ]
            )

            def fetch_historical(symbol: str, from_trade_id: int) -> list[dict[str, object]]:
                self.assertEqual(symbol, "BTCUSDT")
                self.assertEqual(from_trade_id, 101)
                time.sleep(1.0)
                return [
                    {
                        "id": 101,
                        "price": "71545.44",
                        "qty": "0.001",
                        "time": 1775987588152,
                        "isBuyerMaker": True,
                        "isBestMatch": True,
                    }
                ]

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                        websocket_connect=lambda *args, **kwargs: fake_websocket,
                    )
                    provider._fetch_historical_trades = fetch_historical  # type: ignore[method-assign]
                    stop_event = asyncio.Event()
                    original_process_message = provider.process_message

                    def wrapped_process_message(payload: object, *, origin: str = "live") -> bool:
                        ack_received = original_process_message(payload, origin=origin)
                        symbol, trade_id = provider._extract_trade_identity(payload)
                        if symbol == "BTCUSDT" and trade_id == 500:
                            stop_event.set()
                        return ack_received

                    provider.process_message = wrapped_process_message  # type: ignore[method-assign]
                    with self.assertLogs("BinanceTradeShadowProvider", level="INFO") as captured_logs:
                        asyncio.run(
                            asyncio.wait_for(
                                provider._run_session(stop_event, reconnecting=True),
                                timeout=0.5,
                            )
                        )

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual([row["raw_payload"]["data"]["t"] for row in replay_rows], [500])
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_trade_ids"]["BTCUSDT"], 500)
            self.assertEqual(fake_websocket.sent_payloads[0]["method"], "SUBSCRIBE")
            self.assertTrue(
                any(
                    "subscription ack received after reconnect" in message
                    for message in captured_logs.output
                )
            )

    def test_binance_background_catch_up_aborts_when_live_stream_overtakes_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            checkpoint_path = Path(state_dir) / "binance_trade_checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "binance.spot.ws",
                        "last_trade_ids": {"BTCUSDT": 100},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            fetch_started = threading.Event()
            release_fetch = threading.Event()

            def fetch_historical(symbol: str, from_trade_id: int) -> list[dict[str, object]]:
                self.assertEqual(symbol, "BTCUSDT")
                self.assertEqual(from_trade_id, 101)
                fetch_started.set()
                release_fetch.wait(timeout=1.0)
                return [
                    {
                        "id": 101,
                        "price": "71545.44",
                        "qty": "0.001",
                        "time": 1775987588152,
                        "isBuyerMaker": True,
                        "isBestMatch": True,
                    },
                    {
                        "id": 102,
                        "price": "71545.45",
                        "qty": "0.002",
                        "time": 1775987588395,
                        "isBuyerMaker": False,
                        "isBestMatch": True,
                    },
                ]

            async def run_recovery(provider: BinanceTradeShadowProvider) -> None:
                stop_event = asyncio.Event()
                recovery_task = asyncio.create_task(
                    provider._recover_symbol_gap("BTCUSDT", stop_event=stop_event)
                )
                await asyncio.to_thread(fetch_started.wait, 1.0)
                provider.process_message(
                    {
                        "stream": "btcusdt@trade",
                        "data": {
                            "e": "trade",
                            "E": 1775987589000,
                            "s": "BTCUSDT",
                            "t": 500,
                            "p": "71546.00",
                            "q": "0.003",
                            "T": 1775987589000,
                        },
                    }
                )
                release_fetch.set()
                await recovery_task

            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.binance_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = BinanceTradeShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        state_root=state_dir,
                    )
                    provider._fetch_historical_trades = fetch_historical  # type: ignore[method-assign]
                    with self.assertLogs("BinanceTradeShadowProvider", level="INFO") as captured_logs:
                        asyncio.run(run_recovery(provider))

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual([row["raw_payload"]["data"]["t"] for row in replay_rows], [500])
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_trade_ids"]["BTCUSDT"], 500)
            self.assertTrue(
                any(
                    "catch-up aborted for BTCUSDT because live stream overtook checkpoint" in message
                    for message in captured_logs.output
                )
            )

    def test_check_shadow_run_reports_split_socket_stability_by_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_root = root / "artifacts"
            run_root = root / "run"
            stdout_log = root / "stdout.log"
            stderr_log = root / "stderr.log"
            run_config = root / "run_config.json"
            exit_status = root / "exit_status.json"
            artifacts_root.mkdir()
            run_root.mkdir()
            stdout_log.write_text(
                "\n".join(
                    [
                        "2026-04-18 00:00:00,000 INFO [BinanceTradeShadowProvider.BTCUSDT] Binance subscription acknowledged for streams: btcusdt@trade",
                        "2026-04-18 00:00:01,000 WARNING [BinanceTradeShadowProvider.BTCUSDT] Binance WebSocket disconnected; reconnect attempt 1/unbounded in 1.0s: no Binance messages received within 20.0s",
                        "2026-04-18 00:00:02,000 INFO [BinanceTradeShadowProvider.ETHUSDT] Binance subscription ack received after reconnect for streams: ethusdt@trade",
                        "2026-04-18 00:00:03,000 WARNING [BinanceTradeShadowProvider.ETHUSDT] forcing Binance reconnect because ETHUSDT live source age exceeded 120s",
                        "2026-04-18 00:00:04,000 WARNING [BinanceTradeShadowProvider.ETHUSDT] Binance WebSocket disconnected; reconnect attempt 2/unbounded in 2.0s: forcing Binance reconnect because ETHUSDT live source age exceeded 120s",
                        "2026-04-18 00:00:05,000 WARNING [BinanceTradeShadowProvider.BTCUSDT] forcing Binance reconnect because BTCUSDT live receive gap exceeded 120s",
                    ]
                ),
                encoding="utf-8",
            )
            stderr_log.write_text("", encoding="utf-8")
            run_config.write_text(
                json.dumps({"launched_at_utc": "2026-04-18T00:00:00Z"}, indent=2),
                encoding="utf-8",
            )
            exit_status.write_text(
                json.dumps({"ended_at_utc": "2026-04-18T00:10:00Z", "exit_code": 0}, indent=2),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "check_shadow_run.py"),
                    "--artifacts-root",
                    str(artifacts_root),
                    "--run-root",
                    str(run_root),
                    "--stdout-log",
                    str(stdout_log),
                    "--stderr-log",
                    str(stderr_log),
                    "--run-config",
                    str(run_config),
                    "--exit-status",
                    str(exit_status),
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(result.stdout)

            self.assertEqual(summary["stability"]["binance_reconnect_count"], 2)
            self.assertEqual(summary["stability"]["binance_subscription_ack_count"], 2)
            self.assertEqual(
                summary["stability"]["binance_reconnect_count_by_symbol"],
                {"BTCUSDT": 1, "ETHUSDT": 1},
            )
            self.assertEqual(
                summary["stability"]["binance_subscription_ack_count_by_symbol"],
                {"BTCUSDT": 1, "ETHUSDT": 1},
            )
            self.assertEqual(
                summary["stability"]["binance_receive_timeout_count_by_symbol"],
                {"BTCUSDT": 1, "ETHUSDT": 0},
            )
            self.assertEqual(
                summary["stability"]["binance_watchdog_receive_gap_count_by_symbol"],
                {"BTCUSDT": 1, "ETHUSDT": 0},
            )
            self.assertEqual(
                summary["stability"]["binance_watchdog_source_age_count_by_symbol"],
                {"BTCUSDT": 0, "ETHUSDT": 1},
            )

    def test_check_shadow_run_keeps_legacy_aggregate_counts_without_symbol_breakdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_root = root / "artifacts"
            run_root = root / "run"
            stdout_log = root / "stdout.log"
            stderr_log = root / "stderr.log"
            run_config = root / "run_config.json"
            exit_status = root / "exit_status.json"
            artifacts_root.mkdir()
            run_root.mkdir()
            stdout_log.write_text(
                "\n".join(
                    [
                        "2026-04-18 00:00:00,000 INFO [BinanceTradeShadowProvider] Binance subscription acknowledged for streams: btcusdt@trade, ethusdt@trade",
                        "2026-04-18 00:00:01,000 WARNING [BinanceTradeShadowProvider] Binance WebSocket disconnected; reconnect attempt 1/unbounded in 1.0s: no Binance messages received within 20.0s",
                    ]
                ),
                encoding="utf-8",
            )
            stderr_log.write_text("", encoding="utf-8")
            run_config.write_text(
                json.dumps({"launched_at_utc": "2026-04-18T00:00:00Z"}, indent=2),
                encoding="utf-8",
            )
            exit_status.write_text(
                json.dumps({"ended_at_utc": "2026-04-18T00:10:00Z", "exit_code": 0}, indent=2),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "check_shadow_run.py"),
                    "--artifacts-root",
                    str(artifacts_root),
                    "--run-root",
                    str(run_root),
                    "--stdout-log",
                    str(stdout_log),
                    "--stderr-log",
                    str(stderr_log),
                    "--run-config",
                    str(run_config),
                    "--exit-status",
                    str(exit_status),
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(result.stdout)

            self.assertEqual(summary["stability"]["binance_reconnect_count"], 1)
            self.assertEqual(summary["stability"]["binance_subscription_ack_count"], 1)
            self.assertEqual(
                summary["stability"]["binance_reconnect_count_by_symbol"],
                {"BTCUSDT": 0, "ETHUSDT": 0},
            )
            self.assertEqual(
                summary["stability"]["binance_subscription_ack_count_by_symbol"],
                {"BTCUSDT": 0, "ETHUSDT": 0},
            )

    def test_check_shadow_run_derives_expected_subjects_from_run_config_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_root = root / "artifacts"
            run_root = root / "run"
            stdout_log = root / "stdout.log"
            stderr_log = root / "stderr.log"
            run_config = root / "run_config.json"
            exit_status = root / "exit_status.json"
            sol_path = artifacts_root / "live_replay" / "SOL.alchemy.onchain" / "2026-04-18" / "00.jsonl"
            bnb_path = artifacts_root / "live_replay" / "BNB.alchemy.onchain" / "2026-04-18" / "00.jsonl"
            sol_path.parent.mkdir(parents=True, exist_ok=True)
            bnb_path.parent.mkdir(parents=True, exist_ok=True)
            sol_path.write_text(
                json.dumps(
                    {
                        "subject_key": "SOL.alchemy.onchain",
                        "provider_id": "alchemy.sol.rpc",
                        "event_type": "getSlot",
                        "raw_payload": {"method": "getSlot"},
                        "ingest_timestamp_utc": "2026-04-18T00:00:05Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            bnb_path.write_text(
                json.dumps(
                    {
                        "subject_key": "BNB.alchemy.onchain",
                        "provider_id": "alchemy.bnb.rpc",
                        "event_type": "eth_blockNumber",
                        "raw_payload": {"method": "eth_blockNumber"},
                        "ingest_timestamp_utc": "2026-04-18T00:00:05Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stdout_log.write_text("", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            run_config.write_text(
                json.dumps(
                    {
                        "launched_at_utc": "2026-04-18T00:00:00Z",
                        "providers": [
                            {
                                "kind": "alchemy_evm_block",
                                "provider_id": "alchemy.bnb.rpc",
                                "subject_key": "BNB.alchemy.onchain",
                                "symbol": "BNB",
                            },
                            {
                                "kind": "alchemy_solana_block",
                                "provider_id": "alchemy.sol.rpc",
                                "subject_key": "SOL.alchemy.onchain",
                                "symbol": "SOL",
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            exit_status.write_text(
                json.dumps({"ended_at_utc": "2026-04-18T00:10:00Z", "exit_code": 0}, indent=2),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "check_shadow_run.py"),
                    "--artifacts-root",
                    str(artifacts_root),
                    "--run-root",
                    str(run_root),
                    "--stdout-log",
                    str(stdout_log),
                    "--stderr-log",
                    str(stderr_log),
                    "--run-config",
                    str(run_config),
                    "--exit-status",
                    str(exit_status),
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(result.stdout)

            self.assertEqual(set(summary["subjects"].keys()), {"BNB.alchemy.onchain", "SOL.alchemy.onchain"})
            self.assertEqual(summary["subjects"]["BNB.alchemy.onchain"]["event_count"], 1)
            self.assertEqual(summary["subjects"]["SOL.alchemy.onchain"]["event_count"], 1)

    def test_alchemy_provider_retries_and_writes_block_events(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(method)
            if method == "eth_blockNumber" and calls.count("eth_blockNumber") == 1:
                raise RetryableTransportError("HTTP 429")
            if method == "eth_blockNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": "0x10",
                }
            if method == "eth_getBlockByNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "number": "0x10",
                        "timestamp": "0x6612e080",
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemyEthShadowProvider(
                        config=AlchemyEthShadowConfig(
                            retry_backoff=ExponentialBackoffConfig(
                                initial_delay_seconds=0.0,
                                max_delay_seconds=0.0,
                                multiplier=2.0,
                                max_attempts=2,
                            ),
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            quarantine_rows = _read_all_jsonl(Path(quarantine_dir))
            self.assertEqual(calls, ["eth_blockNumber", "eth_blockNumber", "eth_getBlockByNumber"])
            self.assertEqual(len(replay_rows), 2)
            self.assertEqual({row["event_type"] for row in replay_rows}, {"eth_blockNumber", "eth_getBlockByNumber"})
            self.assertEqual({row["subject_key"] for row in replay_rows}, {"ETH.alchemy.onchain"})
            self.assertEqual(quarantine_rows, [])

    def test_alchemy_provider_backfills_missing_blocks_from_checkpoint(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(f"{method}:{request_payload['params'][0] if request_payload.get('params') else ''}")
            if method == "eth_blockNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": "0x12",
                }
            if method == "eth_getBlockByNumber":
                block_hex = str(request_payload["params"][0])
                timestamp_hex = "0x6612e080" if block_hex == "0x11" else "0x6612e08c"
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "number": block_hex,
                        "timestamp": timestamp_hex,
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            checkpoint_path = Path(state_dir) / "alchemy_block_checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "alchemy.eth.rpc",
                        "last_block_number": "0x10",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemyEthShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                        state_root=state_dir,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual(len(replay_rows), 3)
            self.assertEqual(
                [row["event_type"] for row in replay_rows],
                ["eth_blockNumber", "eth_getBlockByNumber", "eth_getBlockByNumber"],
            )
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_block_number"], "0x12")
            self.assertIn("eth_getBlockByNumber:0x11", calls)
            self.assertIn("eth_getBlockByNumber:0x12", calls)

    def test_alchemy_provider_supports_non_eth_evm_subjects(self) -> None:
        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            if method == "eth_blockNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": "0x20",
                }
            if method == "eth_getBlockByNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "number": "0x20",
                        "timestamp": "0x6612e080",
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemyEthShadowProvider(
                        config=AlchemyEthShadowConfig(
                            provider_id="alchemy.bnb.rpc",
                            symbol="BNB",
                            subject_key="BNB.alchemy.onchain",
                            network="bnb-mainnet",
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual({row["provider_id"] for row in replay_rows}, {"alchemy.bnb.rpc"})
            self.assertEqual({row["subject_key"] for row in replay_rows}, {"BNB.alchemy.onchain"})

    def test_alchemy_provider_reads_legacy_eth_checkpoint_from_new_chain_root(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(f"{method}:{request_payload['params'][0] if request_payload.get('params') else ''}")
            if method == "eth_blockNumber":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": "0x12",
                }
            if method == "eth_getBlockByNumber":
                block_hex = str(request_payload["params"][0])
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "number": block_hex,
                        "timestamp": "0x6612e080",
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            legacy_checkpoint_path = Path(state_dir) / "alchemy_block_checkpoint.json"
            legacy_checkpoint_path.write_text(
                json.dumps(
                    {
                        "provider_id": "alchemy.eth.rpc",
                        "last_block_number": "0x10",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            nested_state_root = Path(state_dir) / "alchemy" / "eth"
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemyEthShadowProvider(
                        config=AlchemyEthShadowConfig(
                            legacy_checkpoint_path=legacy_checkpoint_path,
                        ),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                        state_root=nested_state_root,
                    )
                    asyncio.run(provider.poll_once())

            self.assertIn("eth_getBlockByNumber:0x11", calls)
            self.assertTrue((nested_state_root / "alchemy_block_checkpoint.json").exists())

    def test_alchemy_solana_provider_writes_slot_and_block_events(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(method)
            if method == "getSlot":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": 237158054,
                }
            if method == "getBlock":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "blockhash": "abc",
                        "previousBlockhash": "def",
                        "parentSlot": 237158053,
                        "blockTime": 1712515200,
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_solana_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemySolanaShadowProvider(
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual(calls, ["getSlot", "getBlock"])
            self.assertEqual({row["event_type"] for row in replay_rows}, {"getSlot", "getBlock"})
            self.assertEqual({row["subject_key"] for row in replay_rows}, {"SOL.alchemy.onchain"})

    def test_alchemy_solana_provider_allows_missing_block_time(self) -> None:
        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            if method == "getSlot":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": 237158054,
                }
            if method == "getBlock":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "blockhash": "abc",
                        "previousBlockhash": "def",
                        "parentSlot": 237158053,
                        "blockTime": None,
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_solana_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemySolanaShadowProvider(
                        config=AlchemySolanaShadowConfig(),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            block_row = next(row for row in replay_rows if row["event_type"] == "getBlock")
            self.assertIsNone(block_row["source_timestamp"])

    def test_alchemy_solana_provider_skips_skipped_slot_and_advances_checkpoint(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(method)
            if method == "getSlot":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": 237158054,
                }
            if method == "getBlock":
                raise FatalTransportError(
                    "JSON-RPC error for getBlock: Slot 237158054 was skipped, or missing due to ledger jump to recent snapshot"
                )
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_solana_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemySolanaShadowProvider(
                        config=AlchemySolanaShadowConfig(),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                        state_root=state_dir,
                    )
                    asyncio.run(provider.poll_once())
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            quarantine_rows = _read_all_jsonl(Path(quarantine_dir))
            self.assertEqual(calls, ["getSlot", "getBlock", "getSlot"])
            self.assertEqual([row["event_type"] for row in replay_rows], ["getSlot", "getSlot"])
            self.assertEqual(quarantine_rows, [])
            checkpoint = json.loads((Path(state_dir) / "alchemy_slot_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_slot"], 237158054)
            self.assertFalse(provider.is_degraded)

    def test_alchemy_bitcoin_provider_writes_height_and_block_events(self) -> None:
        calls: list[str] = []

        def rpc_caller(request_payload: dict[str, object]) -> dict[str, object]:
            method = str(request_payload["method"])
            calls.append(method)
            if method == "getblockcount":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": 946436,
                }
            if method == "getblockhash":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": "00000000000000000000abc123",
                }
            if method == "getblock":
                return {
                    "jsonrpc": "2.0",
                    "id": request_payload["id"],
                    "result": {
                        "hash": "00000000000000000000abc123",
                        "height": 946436,
                        "time": 1712515200,
                    },
                }
            raise AssertionError(f"unexpected method: {method}")

        with tempfile.TemporaryDirectory() as replay_dir, tempfile.TemporaryDirectory() as quarantine_dir, tempfile.TemporaryDirectory() as state_dir:
            with patch.dict(
                os.environ,
                {"BINANCE_API_KEY": "dummy-binance-key", "ALCHEMY_API_KEY": "dummy-alchemy-key"},
                clear=False,
            ):
                with patch(
                    "enhengclaw.providers.alchemy_bitcoin_shadow_provider.require_active_worker_lease",
                    return_value=None,
                ):
                    provider = AlchemyBitcoinShadowProvider(
                        config=AlchemyBitcoinShadowConfig(),
                        replay_writer=LiveReplayWriter(replay_dir),
                        quarantine_writer=LiveQuarantineWriter(quarantine_dir),
                        rpc_caller=rpc_caller,
                        state_root=state_dir,
                    )
                    asyncio.run(provider.poll_once())

            replay_rows = _read_all_jsonl(Path(replay_dir))
            self.assertEqual(calls, ["getblockcount", "getblockhash", "getblock"])
            self.assertEqual([row["event_type"] for row in replay_rows], ["getblockcount", "getblock"])
            self.assertEqual({row["subject_key"] for row in replay_rows}, {"BTC.alchemy.onchain"})
            block_row = next(row for row in replay_rows if row["event_type"] == "getblock")
            self.assertEqual(block_row["source_timestamp"], "2024-04-07T18:40:00.000Z")
            checkpoint = json.loads((Path(state_dir) / "alchemy_btc_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_height"], 946436)

    def test_heartbeat_task_lock_retries_transient_winerror_5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "shadow_ingestion.default.json"
            lock_path.write_text(
                json.dumps(
                    {
                        "task_key": "shadow_ingestion.default",
                        "run_id": "run-1",
                        "status": "active",
                        "controller_pid": 1,
                        "worker_pid": 2,
                        "lease_id": "lease-old",
                        "created_at_utc": "2026-04-25T00:00:00Z",
                        "updated_at_utc": "2026-04-25T00:00:00Z",
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            original_replace = Path.replace
            replace_attempts = {"count": 0}

            def flaky_replace(self: Path, target: str | Path) -> Path:
                if self.name.startswith(".tmp-") and Path(target) == lock_path and replace_attempts["count"] < 2:
                    replace_attempts["count"] += 1
                    exc = PermissionError(13, "Access is denied")
                    exc.winerror = 5  # type: ignore[attr-defined]
                    raise exc
                return original_replace(self, target)

            with (
                patch("pathlib.Path.replace", new=flaky_replace),
                patch("enhengclaw.orchestration.worker_operations.time.sleep", return_value=None) as sleep_mock,
            ):
                heartbeat_task_lock(
                    lock_path,
                    controller_pid=11,
                    worker_pid=22,
                    lease_id="lease-new",
                )

            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(replace_attempts["count"], 2)
            self.assertEqual(sleep_mock.call_count, 2)
            self.assertEqual(payload["controller_pid"], 11)
            self.assertEqual(payload["worker_pid"], 22)
            self.assertEqual(payload["lease_id"], "lease-new")
            self.assertEqual(payload["status"], "active")

    def test_missing_environment_variables_fail_fast(self) -> None:
        with patch.dict(
            os.environ,
            {"BINANCE_API_KEY": "", "ALCHEMY_API_KEY": ""},
            clear=False,
        ):
            with self.assertRaises(MissingEnvironmentVariableError):
                ShadowIngestionEnvironment.from_env()


if __name__ == "__main__":
    unittest.main()
