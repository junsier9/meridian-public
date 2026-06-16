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
from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256  # noqa: E402
from enhengclaw.live_trading.mainnet_single_run_runner import (  # noqa: E402
    MAINNET_SINGLE_RUN_CONFIRMATION,
    run_mainnet_single_run_pilot,
)


class HvBalancedMainnetSingleRunRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-single-run-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_generates_plan_without_signed_order_client(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        def forbidden_order_client(**_kwargs):
            raise AssertionError("dry-run must not build a signed mainnet order client")

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(config_path=config_path, panel_path=panel_path),
            order_client_factory=forbidden_order_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_single_run_plan_ready")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["required_confirmation"], MAINNET_SINGLE_RUN_CONFIRMATION)
        artifact_root = Path(summary["artifact_root"])
        runtime_gate = json.loads((artifact_root / "runtime_gate_context.json").read_text(encoding="utf-8"))
        self.assertFalse(runtime_gate["config_trading_enabled"])
        self.assertFalse(runtime_gate["runtime_trading_enabled_override"])
        self.assertNotIn("max_daily_realized_loss_enforcement", runtime_gate)
        self.assertNotIn("daily_realized_pnl_gate_active", runtime_gate)

    def test_execute_requires_explicit_mainnet_flags(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        def forbidden_order_client(**_kwargs):
            raise AssertionError("missing confirmation must block before signed order client construction")

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(config_path=config_path, panel_path=panel_path, execute=True),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=forbidden_order_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_operator_enable_live_for_this_run", summary["blockers"])
        self.assertIn("missing_mainnet_strategy_order_understanding_flag", summary["blockers"])
        self.assertIn("missing_exact_mainnet_single_run_confirmation", summary["blockers"])

    def test_execute_submits_once_after_preflight_and_reconciles(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeMainnetOrderClient] = []

        def order_client_factory(**kwargs):
            self.assertEqual(kwargs["base_url"], BINANCE_USDM_MAINNET_BASE_URL)
            client = _FakeMainnetOrderClient()
            created_clients.append(client)
            return client

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=MAINNET_SINGLE_RUN_CONFIRMATION,
            ),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=order_client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_single_run_orders_submitted")
        self.assertEqual(summary["preflight_status"], "passed")
        self.assertEqual(summary["reconciliation_status"], "reconciled")
        self.assertEqual(summary["submitted_order_count"], 6)
        self.assertEqual(summary["fill_count"], 6)
        client = created_clients[0]
        self.assertEqual(len(client.submitted), 6)
        self.assertTrue(all(order["newOrderRespType"] == "RESULT" for order in client.submitted))
        artifact_root = Path(summary["artifact_root"])
        submitted = pd.read_csv(artifact_root / "submitted_orders.csv")
        fills = pd.read_csv(artifact_root / "fills.csv")
        reconciliation = json.loads((artifact_root / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(len(submitted), 6)
        self.assertEqual(len(fills), 6)
        self.assertEqual(reconciliation["open_order_count"], 0)
        self.assertEqual(reconciliation["open_position_count"], 6)

    def test_execute_blocks_when_mainnet_account_has_existing_position(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeMainnetOrderClient] = []

        def order_client_factory(**_kwargs):
            client = _FakeMainnetOrderClient(initial_positions={"BTCUSDT": 0.001})
            created_clients.append(client)
            return client

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=MAINNET_SINGLE_RUN_CONFIRMATION,
            ),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=order_client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("mainnet_open_positions_exist:1", summary["blockers"])
        self.assertEqual(created_clients[0].submitted, [])

    def test_execute_blocks_when_margin_or_leverage_exceeds_config(self) -> None:
        config_path = self._config_path(margin_type="cross", max_leverage=2)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeMainnetOrderClient] = []

        def order_client_factory(**_kwargs):
            client = _FakeMainnetOrderClient(margin_type="cross", leverage=20)
            created_clients.append(client)
            return client

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=MAINNET_SINGLE_RUN_CONFIRMATION,
            ),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=order_client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("leverage_above_max:L1USDT:max=2:actual=20", summary["blockers"])
        self.assertEqual(created_clients[0].submitted, [])

    def test_execute_accepts_cross_when_leverage_is_within_max(self) -> None:
        config_path = self._config_path(margin_type="cross", max_leverage=2)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        def order_client_factory(**_kwargs):
            return _FakeMainnetOrderClient(margin_type="cross", leverage=2)

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=MAINNET_SINGLE_RUN_CONFIRMATION,
            ),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=order_client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_single_run_orders_submitted")
        self.assertEqual(summary["preflight_status"], "passed")

    def test_config_blocks_when_max_leverage_exceeds_pilot_cap(self) -> None:
        config_path = self._config_path(max_leverage=3)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(config_path=config_path, panel_path=panel_path),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_single_run_max_leverage_above_pilot_cap:3>2", summary["blockers"])

    def test_unknown_status_recovery_stops_for_reconcile_without_duplicate_submit(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeUnknownStatusMainnetClient] = []

        def order_client_factory(**_kwargs):
            client = _FakeUnknownStatusMainnetClient()
            created_clients.append(client)
            return client

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=MAINNET_SINGLE_RUN_CONFIRMATION,
            ),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            order_client_factory=order_client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_single_run_reconcile_required")
        self.assertEqual(len(created_clients[0].submitted), 1)
        self.assertEqual(created_clients[0].query_count, 1)
        execution = json.loads((Path(summary["artifact_root"]) / "mainnet_order_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(execution["recoveries"][0]["status"], "resolved")
        self.assertTrue(
            execution["blockers"][0].startswith("unknown_order_status_recovered_stop_for_reconcile:")
        )

    def test_runner_requires_mainnet_venue_config(self) -> None:
        config_path = self._config_path(venue="usdm_futures_testnet")
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_single_run_pilot(
            _args(config_path=config_path, panel_path=panel_path),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("mainnet_single_run_requires_mainnet_venue:actual=usdm_futures_testnet", summary["blockers"])

    def _config_path(self, *, venue: str = "usdm_futures", margin_type: str = "isolated", max_leverage: int = 1) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_mainnet.yaml"
        sqlite_path = (self.temp_dir / "state.sqlite3").as_posix()
        artifact_root = (self.temp_dir / "runs").as_posix()
        frozen_config = self.temp_dir / "frozen_hv_balanced.json"
        payload = json.loads(
            (ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json").read_text(
                encoding="utf-8-sig"
            )
        )
        payload["pit_data_eligibility_policy"] = {"mode": "disabled"}
        frozen_config.write_text(json.dumps(payload), encoding="utf-8")
        frozen_hash = file_sha256(frozen_config)
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    f"  frozen_config_path: {frozen_config.as_posix()}",
                    f"  frozen_config_sha256: {frozen_hash}",
                    "  rebalance_interval_days: 10",
                    "binance:",
                    f"  venue: {venue}",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    f"  margin_type: {margin_type}",
                    f"  max_leverage: {max_leverage}",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "  max_order_notional_usdt: 100.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  require_manual_live_confirm: true",
                    "  max_allocated_capital_usdt: 500.0",
                    "  max_gross_notional_usdt: 500.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "  max_order_notional_usdt: 100.0",
                    "market_data:",
                    "  public_data_enabled: false",
                    "state:",
                    f"  sqlite_path: {sqlite_path}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _args(
    *,
    config_path: Path,
    panel_path: Path,
    execute: bool = False,
    enable: bool = False,
    understand: bool = False,
    daily_review_ack: bool = False,
    confirmation: str = "",
) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel=str(panel_path),
        symbols="",
        public_market_data=False,
        execute_mainnet_strategy_orders=execute,
        operator_enable_live_for_this_run=enable,
        i_understand_this_places_real_mainnet_strategy_orders=understand,
        i_understand_daily_loss_budget_is_review_only=daily_review_ack,
        confirm_mainnet_single_run=confirmation,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 11, 30, 0, tzinfo=UTC)


def _fixture_panel() -> pd.DataFrame:
    rows = []
    for index, subject in enumerate(["L1", "L2", "L3", "S1", "S2", "S3"]):
        base = 0.10 + index * 0.01
        rows.append(
            {
                "timestamp_ms": 0,
                "subject": subject,
                "usdm_symbol": f"{subject}USDT",
                "perp_close": 100.0,
                "perp_quote_volume_usd": 10_000_000.0,
                "universe_active": True,
                "universe_rank": index + 1,
                "liquidity_bucket": "top_liquidity" if subject.startswith("L") else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                "intraday_realized_vol_4h_to_1d_smooth_60": base,
                "realized_volatility_5": base + 0.01,
                "distance_to_high_60": base + 0.02,
                "distance_to_high_5": -0.01 if subject.startswith("S") else -0.20,
                "downside_upside_vol_ratio_30": base + 0.03,
                "momentum_20": 0.05,
            }
        )
    return pd.DataFrame(rows)


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


class _FakeMainnetOrderClient:
    def __init__(
        self,
        *,
        initial_positions: dict[str, float] | None = None,
        margin_type: str = "isolated",
        leverage: int = 1,
    ) -> None:
        self.positions = dict(initial_positions or {})
        self.margin_type = margin_type
        self.leverage = int(leverage)
        self.submitted: list[dict] = []

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "availableBalance": "1000",
                "totalWalletBalance": "1000",
                "positions": [
                    {
                        "symbol": symbol,
                        "positionSide": "BOTH",
                        "positionAmt": str(amount),
                        "notional": str(amount * 100),
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
        return BinanceUsdmResponse(status_code=200, headers={}, payload=[])

    def position_information_v2(self):
        symbols = ["L1USDT", "L2USDT", "L3USDT", "S1USDT", "S2USDT", "S3USDT", *self.positions.keys()]
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload=[
                {
                    "symbol": symbol,
                    "positionSide": "BOTH",
                    "positionAmt": str(self.positions.get(symbol, 0.0)),
                    "notional": str(self.positions.get(symbol, 0.0) * 100.0),
                    "leverage": str(self.leverage),
                    "marginType": self.margin_type,
                    "isolated": self.margin_type == "isolated",
                }
                for symbol in sorted(set(symbols))
            ],
        )

    def submit_mainnet_strategy_single_run_order(self, **params):
        self.submitted.append(dict(params))
        quantity = float(params["quantity"])
        signed = quantity if str(params["side"]).upper() == "BUY" else -quantity
        symbol = str(params["symbol"])
        self.positions[symbol] = round(self.positions.get(symbol, 0.0) + signed, 12)
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": params["newClientOrderId"],
                "orderId": 50_000 + len(self.submitted),
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

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        params = next(item for item in self.submitted if item["newClientOrderId"] == orig_client_order_id)
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 60_001,
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


class _FakeUnknownStatusMainnetClient(_FakeMainnetOrderClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    def submit_mainnet_strategy_single_run_order(self, **params):
        self.submitted.append(dict(params))
        raise BinanceUsdmUnknownExecutionStatus(
            method="POST",
            path="/fapi/v1/order",
            detail='{"code":-1000,"msg":"Unknown error, please check your request or try again later."}',
        )

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        self.query_count += 1
        return super().query_order(symbol=symbol, orig_client_order_id=orig_client_order_id)
