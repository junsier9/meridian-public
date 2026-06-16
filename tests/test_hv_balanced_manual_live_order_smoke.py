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
    BinanceUsdmResponse,
    BinanceUsdmUnknownExecutionStatus,
    LiveOrderSubmissionDisabled,
)
from enhengclaw.live_trading.manual_tiny_live_order_smoke import run_manual_tiny_live_order_smoke  # noqa: E402


class HvBalancedManualLiveOrderSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-live-smoke-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_preflight_passes_without_submitting_orders(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(execute=False),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "dry_run_preflight_passed")
        self.assertFalse(summary["executed"])
        self.assertEqual(summary["required_confirmation"], "LIVE_MANUAL_SMOKE:BTCUSDT:BUY:QTY=0.05:MAX_NOTIONAL=6:ONE_WAY")
        self.assertEqual(created[0].submit_calls, [])
        artifact_root = Path(summary["artifact_root"])
        result = json.loads((artifact_root / "manual_live_order_smoke_result.json").read_text(encoding="utf-8"))
        request_context = json.loads((artifact_root / "request_context.json").read_text(encoding="utf-8"))
        self.assertEqual(result["order_plan"]["quantity"], "0.05")
        self.assertEqual(request_context["strategy_order_generation"], "disabled")
        self.assertNotIn("abc", json.dumps(result))
        self.assertNotIn("def", json.dumps(result))

    def test_execute_requires_exact_live_confirmation(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(execute=True, confirm_risk="wrong"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("confirm_risk_mismatch", summary["blockers"])
        self.assertEqual(created[0].submit_calls, [])

    def test_execute_submits_entry_then_reduce_only_close(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(
                execute=True,
                confirm_risk="LIVE_MANUAL_SMOKE:BTCUSDT:BUY:QTY=0.05:MAX_NOTIONAL=6:ONE_WAY",
                understand=True,
            ),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "manual_live_order_smoke_completed")
        self.assertTrue(summary["executed"])
        client = created[0]
        self.assertEqual(len(client.submit_calls), 2)
        self.assertEqual(client.submit_calls[0]["reduceOnly"], "false")
        self.assertEqual(client.submit_calls[0]["newClientOrderId"], "hvlsm-120000-btcusdt-b")
        self.assertEqual(client.submit_calls[1]["side"], "SELL")
        self.assertEqual(client.submit_calls[1]["reduceOnly"], "true")
        self.assertEqual(client.position_amt, 0.0)
        with self.assertRaises(LiveOrderSubmissionDisabled):
            client.new_order(symbol="BTCUSDT")
        result = json.loads((Path(summary["artifact_root"]) / "manual_live_order_smoke_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["side_effects"]["entry_orders_submitted"], 1)
        self.assertEqual(result["side_effects"]["close_orders_submitted"], 1)

    def test_blocks_when_existing_position_or_open_order_exists(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(execute=False),
            env=self._env(),
            client_factory=_factory(created, position_amt=0.01, open_orders=True),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("open_positions_exist:1", summary["blockers"])
        self.assertIn("open_orders_exist:1", summary["blockers"])
        self.assertEqual(created[0].submit_calls, [])

    def test_blocks_when_estimated_notional_exceeds_max(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(execute=False, max_notional_usdt="4.99"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertTrue(any(item.startswith("requested_notional_exceeds_max") for item in summary["blockers"]))
        self.assertTrue(any(item.startswith("estimated_notional_exceeds_max") for item in summary["blockers"]))

    def test_unknown_entry_status_recovers_by_query_and_still_closes_once(self) -> None:
        created: list[_FakeLiveSmokeClient] = []

        summary, exit_code = run_manual_tiny_live_order_smoke(
            self._args(
                execute=True,
                confirm_risk="LIVE_MANUAL_SMOKE:BTCUSDT:BUY:QTY=0.05:MAX_NOTIONAL=6:ONE_WAY",
                understand=True,
            ),
            env=self._env(),
            client_factory=_factory(created, raise_unknown_on_first_submit=True),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "manual_live_order_smoke_completed")
        self.assertEqual(len(created[0].submit_calls), 2)
        result = json.loads((Path(summary["artifact_root"]) / "manual_live_order_smoke_result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["execution"]["entry_order"]["unknown_status_recovered"])

    def _args(
        self,
        *,
        execute: bool,
        confirm_risk: str = "",
        understand: bool = False,
        max_notional_usdt: str = "6",
    ) -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            api_key_env="",
            api_secret_env="",
            symbol="BTCUSDT",
            side="BUY",
            notional_usdt="5",
            max_notional_usdt=max_notional_usdt,
            client_order_id="",
            execute=execute,
            i_understand_this_places_a_real_mainnet_order=understand,
            confirm_risk=confirm_risk,
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm.yaml"
        artifact_root = (self.temp_dir / "runs").as_posix()
        config_path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  position_mode: one_way",
                    "  recv_window_ms: 5000",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    @staticmethod
    def _env() -> dict[str, str]:
        return {"LIVE_KEY": "abc", "LIVE_SECRET": "def"}


class _FakeLiveSmokeClient:
    def __init__(
        self,
        *,
        position_amt: float = 0.0,
        open_orders: bool = False,
        raise_unknown_on_first_submit: bool = False,
        **kwargs,
    ) -> None:
        self.kwargs = kwargs
        self.position_amt = float(position_amt)
        self.include_open_orders = bool(open_orders)
        self.raise_unknown_on_first_submit = raise_unknown_on_first_submit
        self.submit_calls: list[dict] = []
        self.orders: dict[str, dict] = {}

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "assets": [{"asset": "USDT", "walletBalance": "100.0"}],
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": str(self.position_amt),
                        "positionSide": "BOTH",
                        "notional": str(self.position_amt * 100.0),
                    }
                ],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"canTrade": True, "dualSidePosition": False})

    def position_mode(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": False})

    def exchange_info(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {"filterType": "MARKET_LOT_SIZE", "minQty": "0.01", "stepSize": "0.01"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                        ],
                    }
                ]
            },
        )

    def premium_index(self, *, symbol: str):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"symbol": symbol, "markPrice": "100.0"})

    def current_all_open_orders(self):
        payload = []
        if self.include_open_orders:
            payload.append({"symbol": "BTCUSDT", "orderId": 1, "clientOrderId": "existing", "status": "NEW"})
        return BinanceUsdmResponse(status_code=200, headers={}, payload=payload)

    def submit_manual_live_order_smoke(self, **params):
        self.submit_calls.append(dict(params))
        client_order_id = str(params["newClientOrderId"])
        quantity = float(params["quantity"])
        side = str(params["side"])
        reduce_only = str(params.get("reduceOnly", "false")).lower() == "true"
        signed_qty = quantity if side == "BUY" else -quantity
        if reduce_only:
            self.position_amt = round(self.position_amt + signed_qty, 12)
            if abs(self.position_amt) < 1e-12:
                self.position_amt = 0.0
        else:
            self.position_amt = round(self.position_amt + signed_qty, 12)
        payload = {
            "symbol": params["symbol"],
            "clientOrderId": client_order_id,
            "orderId": len(self.orders) + 1,
            "status": "FILLED",
            "side": side,
            "type": "MARKET",
            "positionSide": "BOTH",
            "reduceOnly": reduce_only,
            "origQty": str(quantity),
            "executedQty": str(quantity),
            "avgPrice": "100.0",
            "updateTime": 1770000000000,
        }
        self.orders[client_order_id] = payload
        if self.raise_unknown_on_first_submit and len(self.submit_calls) == 1:
            raise BinanceUsdmUnknownExecutionStatus("POST", "/fapi/v1/order", "fixture unknown")
        return BinanceUsdmResponse(status_code=200, headers={}, payload=payload)

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=self.orders[orig_client_order_id])

    def new_order(self, **_):
        raise LiveOrderSubmissionDisabled("strategy order submission remains disabled")


def _factory(
    created: list[_FakeLiveSmokeClient],
    *,
    position_amt: float = 0.0,
    open_orders: bool = False,
    raise_unknown_on_first_submit: bool = False,
):
    def build(**kwargs) -> _FakeLiveSmokeClient:
        client = _FakeLiveSmokeClient(
            position_amt=position_amt,
            open_orders=open_orders,
            raise_unknown_on_first_submit=raise_unknown_on_first_submit,
            **kwargs,
        )
        created.append(client)
        return client

    return build


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
