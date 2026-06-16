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

from enhengclaw.live_trading.account_probe import run_read_only_account_probe  # noqa: E402
from enhengclaw.live_trading.binance_usdm_client import (  # noqa: E402
    BINANCE_USDM_MAINNET_BASE_URL,
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmResponse,
)


class HvBalancedAccountProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-account-probe-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_read_only_probe_checks_account_permissions_position_mode_and_rules(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_read_only_account_probe")
        self.assertTrue(summary["account_readable"])
        self.assertTrue(summary["can_trade"])
        self.assertEqual(summary["position_mode"], "one_way")
        self.assertEqual(summary["open_order_count"], 0)
        self.assertEqual(summary["open_position_count"], 0)
        self.assertTrue(summary["api_key_enable_reading"])
        self.assertTrue(summary["api_key_enable_futures"])
        self.assertFalse(summary["api_key_enable_withdrawals"])
        self.assertTrue(summary["api_key_ip_restrict"])
        self.assertEqual(created[0].kwargs["base_url"], BINANCE_USDM_MAINNET_BASE_URL)
        self.assertEqual(created[0].new_order_calls, 0)
        self.assertEqual(created[0].new_order_test_calls, 0)
        self.assertEqual(created[0].cancel_order_calls, 0)
        artifact_root = Path(summary["artifact_root"])
        result = json.loads((artifact_root / "account_probe_result.json").read_text(encoding="utf-8"))
        request_context = json.loads((artifact_root / "request_context.json").read_text(encoding="utf-8"))
        self.assertEqual(result["side_effects"]["orders_submitted"], 0)
        self.assertEqual(result["open_orders"]["open_order_count"], 0)
        self.assertTrue(result["api_key_permissions"]["enable_futures"])
        self.assertFalse(result["api_key_permissions"]["enable_withdrawals"])
        self.assertTrue(result["api_key_permissions"]["ip_restrict"])
        self.assertEqual(result["min_order_rules"]["BTCUSDT"]["min_notional"], 5.0)
        self.assertEqual(request_context["api_key_length"], 3)
        self.assertNotIn("abc", json.dumps(request_context))
        self.assertNotIn("def", json.dumps(request_context))
        self.assertNotIn("abc", json.dumps(result))
        self.assertNotIn("def", json.dumps(result))

    def test_probe_can_target_testnet_base_url(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="testnet"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["environment"], "testnet")
        self.assertEqual(created[0].kwargs["base_url"], BINANCE_USDM_TESTNET_BASE_URL)

    def test_probe_accepts_meridian_alpha_alias_for_legacy_binance_env_names(self) -> None:
        created: list[_FakeProbeClient] = []
        args = self._args(environment="mainnet")
        args.api_key_env = "ENHENGCLAW_BINANCE_USDM_API_KEY"
        args.api_secret_env = "ENHENGCLAW_BINANCE_USDM_API_SECRET"

        summary, exit_code = run_read_only_account_probe(
            args,
            env={
                "MERIDIAN_ALPHA_BINANCE_USDM_API_KEY": "abc",
                "MERIDIAN_ALPHA_BINANCE_USDM_API_SECRET": "def",
            },
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_read_only_account_probe")
        self.assertEqual(created[0].kwargs["api_key"], "abc")

    def test_probe_blocks_missing_credentials_without_creating_client(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env={},
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_api_key_env:PROBE_KEY", summary["blockers"])
        self.assertIn("missing_api_secret_env:PROBE_SECRET", summary["blockers"])
        self.assertEqual(created, [])

    def test_probe_blocks_when_can_trade_is_false(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env=self._env(),
            client_factory=_factory(created, can_trade=False),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("account_config_canTrade_not_true:False", summary["blockers"])

    def test_probe_blocks_position_mode_mismatch(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env=self._env(),
            client_factory=_factory(created, dual_side_position=True),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("position_mode_mismatch:expected=one_way:actual=hedge", summary["blockers"])

    def test_probe_blocks_existing_open_orders(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env=self._env(),
            client_factory=_factory(created, open_orders=[{"symbol": "BTCUSDT", "orderId": 1, "status": "NEW"}]),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_open_orders_exist:1", summary["blockers"])
        self.assertEqual(summary["open_order_count"], 1)

    def test_probe_blocks_unsafe_api_key_permissions(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet"),
            env=self._env(),
            client_factory=_factory(
                created,
                api_key_permissions={
                    "ipRestrict": False,
                    "enableReading": True,
                    "enableFutures": True,
                    "enableWithdrawals": True,
                },
            ),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("api_key_enableWithdrawals_not_false:True", summary["blockers"])
        self.assertIn("api_key_ipRestrict_not_true:False", summary["blockers"])

    def test_probe_blocks_missing_min_order_rule_symbol(self) -> None:
        created: list[_FakeProbeClient] = []

        summary, exit_code = run_read_only_account_probe(
            self._args(environment="mainnet", symbols="BADUSDT"),
            env=self._env(),
            client_factory=_factory(created),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("symbol_missing_from_exchange_info:BADUSDT", summary["blockers"])

    def _args(self, *, environment: str, symbols: str = "BTCUSDT") -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            environment=environment,
            api_key_env="",
            api_secret_env="",
            symbols=symbols,
            max_symbols=20,
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm.yaml"
        artifact_root = (self.temp_dir / "runs").as_posix()
        config_path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  api_key_env: PROBE_KEY",
                    "  api_secret_env: PROBE_SECRET",
                    "  position_mode: one_way",
                    "  recv_window_ms: 5000",
                    "market_data:",
                    "  symbols: BTCUSDT,ETHUSDT",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    @staticmethod
    def _env() -> dict[str, str]:
        return {"PROBE_KEY": "abc", "PROBE_SECRET": "def"}


class _FakeProbeClient:
    def __init__(
        self,
        *,
        can_trade: bool = True,
        dual_side_position: bool = False,
        open_orders: list[dict] | None = None,
        api_key_permissions: dict | None = None,
        **kwargs,
    ) -> None:
        self.kwargs = kwargs
        self.can_trade = can_trade
        self.dual_side_position = dual_side_position
        self.open_orders = list(open_orders or [])
        self.api_key_permissions_payload = dict(
            api_key_permissions
            or {
                "ipRestrict": True,
                "createTime": 1698645219000,
                "enableReading": True,
                "enableWithdrawals": False,
                "enableInternalTransfer": False,
                "enableMargin": False,
                "enableFutures": True,
                "permitsUniversalTransfer": False,
                "enableSpotAndMarginTrading": False,
            }
        )
        self.new_order_calls = 0
        self.new_order_test_calls = 0
        self.cancel_order_calls = 0

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "availableBalance": "100.0",
                "totalWalletBalance": "100.0",
                "assets": [{"asset": "USDT", "walletBalance": "100.0"}],
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0", "positionSide": "BOTH"}],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "canTrade": self.can_trade,
                "canDeposit": True,
                "canWithdraw": True,
                "dualSidePosition": self.dual_side_position,
                "multiAssetsMargin": False,
                "feeTier": 0,
                "tradeGroupId": -1,
            },
        )

    def position_mode(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={"dualSidePosition": self.dual_side_position},
        )

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=self.open_orders)

    def api_key_restrictions(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=self.api_key_permissions_payload)

    def exchange_info(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=_exchange_info())

    def new_order(self, **kwargs):
        self.new_order_calls += 1
        raise AssertionError(f"account probe must not submit orders: {kwargs}")

    def new_order_test(self, **kwargs):
        self.new_order_test_calls += 1
        raise AssertionError(f"account probe must not call order/test: {kwargs}")

    def cancel_order(self, **kwargs):
        self.cancel_order_calls += 1
        raise AssertionError(f"account probe must not cancel orders: {kwargs}")


def _factory(
    created: list[_FakeProbeClient],
    *,
    can_trade: bool = True,
    dual_side_position: bool = False,
    open_orders: list[dict] | None = None,
    api_key_permissions: dict | None = None,
):
    def build(**kwargs) -> _FakeProbeClient:
        client = _FakeProbeClient(
            can_trade=can_trade,
            dual_side_position=dual_side_position,
            open_orders=open_orders,
            api_key_permissions=api_key_permissions,
            **kwargs,
        )
        created.append(client)
        return client

    return build


def _exchange_info() -> dict:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                ],
            }
        ]
    }


def _fixed_now() -> datetime:
    return datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
