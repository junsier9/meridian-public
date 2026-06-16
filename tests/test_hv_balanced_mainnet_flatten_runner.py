from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import pandas as pd


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
)
from enhengclaw.live_trading.mainnet_flatten_runner import (  # noqa: E402
    MAINNET_FLATTEN_CONFIRMATION,
    run_mainnet_reduce_only_flatten,
)


class HvBalancedMainnetFlattenRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-flatten-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_generates_reduce_only_plan_without_submitting_orders(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(config_path=self._config_path()),
            env=_env(),
            mainnet_client_factory=_factory(created, positions={"BTCUSDT": 0.001, "AAVEUSDT": -0.9}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_flatten_plan_ready")
        self.assertEqual(summary["planned_order_count"], 2)
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["required_confirmation"], MAINNET_FLATTEN_CONFIRMATION)
        self.assertFalse(summary["recurring_mainnet_enabled"])
        self.assertEqual(created[0].submitted, [])
        plan = pd.read_csv(Path(summary["artifact_root"]) / "flatten_plan.csv")
        by_symbol = {row["symbol"]: row for row in plan.to_dict(orient="records")}
        self.assertEqual(by_symbol["BTCUSDT"]["side"], "SELL")
        self.assertEqual(by_symbol["AAVEUSDT"]["side"], "BUY")
        self.assertTrue(plan["reduce_only"].all())

    def test_execute_requires_explicit_confirmation_before_building_client(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(config_path=self._config_path(), execute=True),
            env=_env(),
            mainnet_client_factory=_factory(created, positions={"BTCUSDT": 0.001}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_operator_enable_mainnet_flatten_for_this_run", summary["blockers"])
        self.assertIn("missing_mainnet_reduce_only_order_understanding_flag", summary["blockers"])
        self.assertIn("missing_exact_mainnet_flatten_confirmation", summary["blockers"])
        self.assertEqual(created, [])

    def test_execute_reduce_only_flatten_reconciles_to_flat(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(
                config_path=self._config_path(),
                execute=True,
                enable=True,
                understand=True,
                confirmation=MAINNET_FLATTEN_CONFIRMATION,
            ),
            env=_env(),
            mainnet_client_factory=_factory(created, positions={"BTCUSDT": 0.001, "AAVEUSDT": -0.9}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_reduce_only_flatten_executed")
        self.assertEqual(summary["open_position_count_before"], 2)
        self.assertEqual(summary["open_position_count_after"], 0)
        self.assertEqual(summary["submitted_order_count"], 2)
        self.assertEqual(summary["fill_count"], 2)
        self.assertEqual(created[0].kwargs["base_url"], BINANCE_USDM_MAINNET_BASE_URL)
        self.assertEqual(len(created[0].submitted), 2)
        self.assertTrue(all(item["reduceOnly"] == "true" for item in created[0].submitted))
        self.assertTrue(all(item["type"] == "MARKET" for item in created[0].submitted))
        reconciliation = json.loads((Path(summary["artifact_root"]) / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(reconciliation["status"], "passed")
        self.assertTrue(reconciliation["all_submitted_orders_reduce_only"])

    def test_unknown_status_recovery_stops_without_duplicate_submit(self) -> None:
        created: list[_UnknownStatusMainnetFlattenClient] = []

        def build(**kwargs) -> _UnknownStatusMainnetFlattenClient:
            client = _UnknownStatusMainnetFlattenClient(positions={"BTCUSDT": 0.001}, **kwargs)
            created.append(client)
            return client

        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(
                config_path=self._config_path(),
                execute=True,
                enable=True,
                understand=True,
                confirmation=MAINNET_FLATTEN_CONFIRMATION,
            ),
            env=_env(),
            mainnet_client_factory=build,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_flatten_reconcile_required")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["open_position_count_after"], 0)
        self.assertEqual(len(created[0].submitted), 1)
        self.assertEqual(created[0].query_count, 1)
        execution = json.loads((Path(summary["artifact_root"]) / "mainnet_flatten_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(execution["recoveries"][0]["status"], "resolved")
        self.assertEqual(execution["recoveries"][0]["order_status"], "FILLED")
        self.assertTrue(execution["blockers"][0].startswith("unknown_order_status_recovered_stop_for_reconcile:"))

    def test_execute_blocks_when_open_orders_exist(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(
                config_path=self._config_path(),
                execute=True,
                enable=True,
                understand=True,
                confirmation=MAINNET_FLATTEN_CONFIRMATION,
            ),
            env=_env(),
            mainnet_client_factory=_factory(
                created,
                positions={"BTCUSDT": 0.001},
                open_orders=[{"symbol": "BTCUSDT", "orderId": 1}],
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("mainnet_open_orders_exist:1", summary["blockers"])
        self.assertEqual(created[0].submitted, [])

    def test_missing_credentials_never_builds_client(self) -> None:
        def forbidden_client(**_kwargs):
            raise AssertionError("missing credentials should block before client construction")

        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(config_path=self._config_path()),
            env={},
            mainnet_client_factory=forbidden_client,
            permission_client_factory=forbidden_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("missing_api_key_env:LIVE_KEY", summary["blockers"])
        self.assertIn("missing_api_secret_env:LIVE_SECRET", summary["blockers"])
        self.assertEqual(summary["submitted_order_count"], 0)

    def test_already_flat_is_noop(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(config_path=self._config_path()),
            env=_env(),
            mainnet_client_factory=_factory(created, positions={}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_already_flat")
        self.assertEqual(summary["planned_order_count"], 0)
        self.assertEqual(summary["submitted_order_count"], 0)

    def test_leverage_warning_does_not_block_reduce_only_plan(self) -> None:
        created: list[_FakeMainnetFlattenClient] = []
        summary, exit_code = run_mainnet_reduce_only_flatten(
            _args(config_path=self._config_path(max_leverage=2)),
            env=_env(),
            mainnet_client_factory=_factory(created, positions={"BTCUSDT": 0.001}, leverage=20),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_flatten_plan_ready")
        self.assertIn("leverage_above_config_but_reduce_only_exit_allowed:BTCUSDT:max=2:actual=20", summary["warnings"])

    def _config_path(self, *, venue: str = "usdm_futures", max_leverage: int = 2) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_mainnet.yaml"
        artifact_root = (self.temp_dir / "runs").as_posix()
        config_path.write_text(
            "\n".join(
                [
                    "binance:",
                    f"  venue: {venue}",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    f"  max_leverage: {max_leverage}",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


class _FakePermissionClient:
    def api_key_restrictions(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "ipRestrict": True,
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "enableMargin": True,
                "enableSpotAndMarginTrading": True,
                "permitsUniversalTransfer": True,
            },
        )


class _FakeMainnetFlattenClient:
    def __init__(
        self,
        *,
        positions: dict[str, float],
        open_orders: list[dict] | None = None,
        margin_type: str = "cross",
        leverage: int = 2,
        **kwargs,
    ) -> None:
        self.positions = {symbol: float(amount) for symbol, amount in positions.items()}
        self.open_orders = list(open_orders or [])
        self.margin_type = margin_type
        self.leverage = int(leverage)
        self.kwargs = kwargs
        self.submitted: list[dict] = []

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "canTrade": True,
                "availableBalance": "1000",
                "totalWalletBalance": "1000",
                "positions": [
                    {
                        "symbol": symbol,
                        "positionSide": "BOTH",
                        "positionAmt": str(amount),
                        "entryPrice": "100",
                        "unrealizedProfit": "0",
                    }
                    for symbol, amount in sorted(self.positions.items())
                ],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"canTrade": True})

    def position_mode(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": False})

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.open_orders))

    def position_information_v2(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload=[
                {
                    "symbol": symbol,
                    "positionSide": "BOTH",
                    "positionAmt": str(amount),
                    "notional": str(amount * 100.0),
                    "entryPrice": "100",
                    "markPrice": "100",
                    "unRealizedProfit": "0",
                    "marginType": self.margin_type,
                    "leverage": str(self.leverage),
                    "isolated": self.margin_type == "isolated",
                }
                for symbol, amount in sorted(self.positions.items())
            ],
        )

    def submit_mainnet_reduce_only_order(self, **params):
        self.submitted.append(dict(params))
        symbol = str(params["symbol"])
        amount = float(self.positions.get(symbol, 0.0))
        if params.get("reduceOnly") == "true":
            if amount > 0.0 and params["side"] == "SELL":
                self.positions[symbol] = 0.0
            elif amount < 0.0 and params["side"] == "BUY":
                self.positions[symbol] = 0.0
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": params["newClientOrderId"],
                "orderId": 3000 + len(self.submitted),
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100",
                "updateTime": 1770000000000,
            },
        )


class _UnknownStatusMainnetFlattenClient(_FakeMainnetFlattenClient):
    def __init__(self, *, positions: dict[str, float], **kwargs) -> None:
        super().__init__(positions=positions, **kwargs)
        self.query_count = 0

    def submit_mainnet_reduce_only_order(self, **params):
        self.submitted.append(dict(params))
        symbol = str(params["symbol"])
        self.positions[symbol] = 0.0
        raise BinanceUsdmUnknownExecutionStatus(
            method="POST",
            path="/fapi/v1/order",
            detail='{"code":-1000,"msg":"Unknown error, please check your request or try again later."}',
        )

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        self.query_count += 1
        params = self.submitted[-1]
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 4001,
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100",
                "updateTime": 1770000000000,
            },
        )


def _factory(
    created: list[_FakeMainnetFlattenClient],
    *,
    positions: dict[str, float],
    open_orders: list[dict] | None = None,
    margin_type: str = "cross",
    leverage: int = 2,
):
    def build(**kwargs) -> _FakeMainnetFlattenClient:
        client = _FakeMainnetFlattenClient(
            positions=positions,
            open_orders=open_orders,
            margin_type=margin_type,
            leverage=leverage,
            **kwargs,
        )
        created.append(client)
        return client

    return build


def _args(
    *,
    config_path: Path,
    execute: bool = False,
    enable: bool = False,
    understand: bool = False,
    confirmation: str = "",
) -> Namespace:
    return Namespace(
        config=str(config_path),
        execute_mainnet_flatten=execute,
        operator_enable_mainnet_flatten_for_this_run=enable,
        i_understand_this_places_real_mainnet_reduce_only_orders=understand,
        confirm_mainnet_flatten=confirmation,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 14, 0, 0, tzinfo=UTC)
