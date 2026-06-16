from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.binance_usdm_client import (  # noqa: E402
    BINANCE_USDM_MAINNET_BASE_URL,
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmResponse,
)
from enhengclaw.live_trading.manual_lifecycle_runner import run_manual_lifecycle  # noqa: E402


class HvBalancedManualLifecycleRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-manual-lifecycle-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_manual_query_uses_operator_client_order_id_and_writes_artifacts(self) -> None:
        created: list[_FakeLifecycleClient] = []

        summary, exit_code = run_manual_lifecycle(
            self._args(action="query"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "manual_query_resolved")
        self.assertEqual(summary["base_url"], BINANCE_USDM_TESTNET_BASE_URL)
        self.assertEqual(created[0].query_calls, [("BTCUSDT", "operator-id-1")])
        self.assertEqual(created[0].cancel_calls, [])
        self.assertEqual(created[0].new_order_calls, 0)
        artifact_root = Path(summary["artifact_root"])
        result = json.loads((artifact_root / "lifecycle_result.json").read_text(encoding="utf-8"))
        request_context = json.loads((artifact_root / "request_context.json").read_text(encoding="utf-8"))
        self.assertEqual(result["client_order_id"], "operator-id-1")
        self.assertEqual(request_context["strategy_order_generation"], "disabled")
        self.assertEqual(request_context["new_order_submission"], "not_called")

    def test_manual_cancel_only_calls_cancel_for_operator_client_order_id(self) -> None:
        created: list[_FakeLifecycleClient] = []

        summary, exit_code = run_manual_lifecycle(
            self._args(action="cancel"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "manual_cancel_resolved")
        self.assertEqual(created[0].query_calls, [])
        self.assertEqual(created[0].cancel_calls, [("BTCUSDT", "operator-id-1")])
        self.assertEqual(created[0].new_order_calls, 0)
        result = json.loads((Path(summary["artifact_root"]) / "lifecycle_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "CANCELED")

    def test_manual_recover_can_resolve_from_user_event_without_api_credentials(self) -> None:
        created: list[_FakeLifecycleClient] = []
        event_path = self.temp_dir / "events.jsonl"
        event_path.write_text(json.dumps(_order_trade_update_event(status="FILLED", execution_type="TRADE")), encoding="utf-8")

        summary, exit_code = run_manual_lifecycle(
            self._args(action="recover", user_event_jsonl=str(event_path)),
            env={},
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "manual_recovery_resolved")
        self.assertEqual(summary["result_source"], "user_data_stream")
        self.assertEqual(summary["order_status"], "FILLED")
        self.assertEqual(created, [])

    def test_manual_recover_without_event_or_credentials_requires_reconcile_without_resubmit(self) -> None:
        summary, exit_code = run_manual_lifecycle(
            self._args(action="recover"),
            env={},
            client_factory=_factory([]),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "manual_recovery_reconcile_required")
        self.assertIn("missing_api_key_env:TESTNET_KEY", summary["blockers"])
        result = json.loads((Path(summary["artifact_root"]) / "lifecycle_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["next_action"], "do_not_resubmit")

    def test_manual_lifecycle_blocks_missing_client_order_id(self) -> None:
        summary, exit_code = run_manual_lifecycle(
            self._args(action="query", client_order_id=""),
            env=self._env(),
            client_factory=_factory([]),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("manual_lifecycle_requires_client_order_id", summary["blockers"])

    def test_manual_lifecycle_rejects_non_testnet_base_url_even_in_internal_call(self) -> None:
        args = self._args(action="query")
        args.base_url = BINANCE_USDM_MAINNET_BASE_URL

        summary, exit_code = run_manual_lifecycle(
            args,
            env=self._env(),
            client_factory=_factory([]),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("manual_lifecycle_testnet_only", summary["blockers"])

    def _args(
        self,
        *,
        action: str,
        symbol: str = "BTCUSDT",
        client_order_id: str = "operator-id-1",
        user_event_jsonl: str = "",
    ) -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            action=action,
            symbol=symbol,
            client_order_id=client_order_id,
            user_event_jsonl=user_event_jsonl,
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm.yaml"
        artifact_root = (self.temp_dir / "runs").as_posix()
        config_path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  api_key_env: TESTNET_KEY",
                    "  api_secret_env: TESTNET_SECRET",
                    "  recv_window_ms: 7000",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    @staticmethod
    def _env() -> dict[str, str]:
        return {"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"}


class _FakeLifecycleClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.query_calls: list[tuple[str, str]] = []
        self.cancel_calls: list[tuple[str, str]] = []
        self.new_order_calls = 0

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        self.query_calls.append((symbol, orig_client_order_id))
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 123,
                "status": "NEW",
                "side": "BUY",
                "type": "MARKET",
                "positionSide": "BOTH",
                "reduceOnly": True,
                "origQty": "0.010",
                "executedQty": "0",
                "avgPrice": "0",
                "updateTime": 1770000000000,
            },
        )

    def cancel_order(self, *, symbol: str, orig_client_order_id: str):
        self.cancel_calls.append((symbol, orig_client_order_id))
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 123,
                "status": "CANCELED",
                "side": "BUY",
                "type": "MARKET",
                "positionSide": "BOTH",
                "reduceOnly": True,
                "origQty": "0.010",
                "executedQty": "0",
                "avgPrice": "0",
                "updateTime": 1770000000000,
            },
        )

    def new_order(self, **kwargs):
        self.new_order_calls += 1
        raise AssertionError(f"manual lifecycle runner must not submit new orders: {kwargs}")


def _factory(created: list[_FakeLifecycleClient]):
    def build(**kwargs) -> _FakeLifecycleClient:
        client = _FakeLifecycleClient(**kwargs)
        created.append(client)
        return client

    return build


def _fixed_now() -> datetime:
    return datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


def _order_trade_update_event(*, status: str, execution_type: str) -> dict:
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1770000000001,
        "T": 1770000000000,
        "o": {
            "s": "BTCUSDT",
            "c": "operator-id-1",
            "S": "BUY",
            "o": "MARKET",
            "f": "GTC",
            "q": "0.010",
            "p": "0",
            "ap": "100000",
            "x": execution_type,
            "X": status,
            "i": 123,
            "l": "0.010",
            "z": "0.010",
            "L": "100000",
            "N": "USDT",
            "n": "0.04",
            "T": 1770000000000,
            "t": 456,
            "m": False,
            "R": True,
            "ps": "BOTH",
            "rp": "0",
            "er": "0",
        },
    }
