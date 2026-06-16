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
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmResponse,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402
from enhengclaw.live_trading.testnet_strategy_runner import (  # noqa: E402
    TESTNET_STRATEGY_CONFIRMATION,
    run_testnet_strategy_auto_order,
)


class HvBalancedTestnetStrategyRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-testnet-runner-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_generates_strategy_plan_without_signed_order_client(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        def forbidden_order_client(**_kwargs):
            raise AssertionError("dry-run must not build a signed testnet order client")

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(config_path=config_path, panel_path=panel_path),
            order_client_factory=forbidden_order_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "testnet_strategy_plan_ready")
        self.assertTrue(summary["testnet_only"])
        self.assertEqual(summary["submitted_order_count"], 0)
        artifact_root = Path(summary["artifact_root"])
        risk_gate = json.loads((artifact_root / "risk_gate.json").read_text(encoding="utf-8"))
        execution_plan = pd.read_csv(artifact_root / "execution_plan.csv")
        target_positions = pd.read_csv(artifact_root / "target_positions.csv")
        sizing_summary = json.loads((artifact_root / "min_executable_capital_report.json").read_text(encoding="utf-8"))

        self.assertTrue(risk_gate["passed"])
        self.assertEqual(risk_gate["mode"], "testnet")
        self.assertGreater(len(target_positions), 0)
        self.assertGreater(len(execution_plan), 0)
        self.assertEqual(sizing_summary["status"], "passed")
        self.assertFalse((artifact_root / "testnet_order_execution.json").exists())

    def test_execute_requires_explicit_testnet_flags_and_does_not_submit_when_missing(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        args = _args(
            config_path=config_path,
            panel_path=panel_path,
            execute=True,
            understand=False,
            confirmation="",
        )

        def forbidden_order_client(**_kwargs):
            raise AssertionError("missing confirmation must block before signed order client construction")

        summary, exit_code = run_testnet_strategy_auto_order(
            args,
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=forbidden_order_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_testnet_understanding_flag", summary["blockers"])
        self.assertIn("missing_exact_testnet_strategy_confirmation", summary["blockers"])
        self.assertEqual(summary["submitted_order_count"], 0)

    def test_operator_pause_blocks_testnet_strategy_auto_order_runner(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-kill",
            action_type="kill-switch",
            reason="unit test kill switch",
            created_at_utc="2026-05-17T02:59:00Z",
        )

        def forbidden_order_client(**_kwargs):
            raise AssertionError("operator pause must block before signed order client construction")

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                understand=True,
                confirmation=TESTNET_STRATEGY_CONFIRMATION,
            ),
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=forbidden_order_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("operator_paused", summary["blockers"])
        operator_state = json.loads((Path(summary["artifact_root"]) / "operator_state.json").read_text(encoding="utf-8"))
        self.assertTrue(operator_state["paused"])

    def test_execute_submits_all_strategy_intents_to_testnet_after_preflight(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeTestnetOrderClient] = []

        def order_client_factory(**kwargs):
            self.assertEqual(kwargs["base_url"], BINANCE_USDM_TESTNET_BASE_URL)
            client = _FakeTestnetOrderClient()
            created_clients.append(client)
            return client

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                understand=True,
                confirmation=TESTNET_STRATEGY_CONFIRMATION,
            ),
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=order_client_factory,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "testnet_strategy_orders_submitted")
        artifact_root = Path(summary["artifact_root"])
        plan = pd.read_csv(artifact_root / "execution_plan.csv")
        submitted = pd.read_csv(artifact_root / "submitted_orders.csv")
        fills = pd.read_csv(artifact_root / "fills.csv")
        preflight = json.loads((artifact_root / "testnet_preflight.json").read_text(encoding="utf-8"))
        execution = json.loads((artifact_root / "testnet_order_execution.json").read_text(encoding="utf-8"))

        self.assertEqual(preflight["status"], "passed")
        self.assertEqual(len(created_clients), 1)
        self.assertEqual(summary["submitted_order_count"], len(plan))
        self.assertEqual(summary["fill_count"], len(plan))
        self.assertEqual(len(created_clients[0].submitted), len(plan))
        self.assertEqual(len(submitted), len(plan))
        self.assertEqual(len(fills), len(plan))
        self.assertEqual(execution["status"], "submitted")
        self.assertTrue(all(order["newOrderRespType"] == "RESULT" for order in created_clients[0].submitted))

    def test_unknown_status_is_recovered_and_stops_without_duplicate_strategy_submit(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeUnknownStatusStrategyClient] = []

        def order_client_factory(**kwargs):
            self.assertEqual(kwargs["base_url"], BINANCE_USDM_TESTNET_BASE_URL)
            client = _FakeUnknownStatusStrategyClient()
            created_clients.append(client)
            return client

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                understand=True,
                confirmation=TESTNET_STRATEGY_CONFIRMATION,
            ),
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=order_client_factory,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "testnet_strategy_reconcile_required")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(len(created_clients[0].submitted), 1)
        self.assertEqual(created_clients[0].query_count, 1)
        artifact_root = Path(summary["artifact_root"])
        execution = json.loads((artifact_root / "testnet_order_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(execution["status"], "reconcile_required")
        self.assertEqual(execution["recoveries"][0]["status"], "resolved")
        self.assertEqual(execution["recoveries"][0]["source"], "rest_query")
        self.assertEqual(execution["recoveries"][0]["order_status"], "FILLED")
        self.assertTrue(
            execution["blockers"][0].startswith("unknown_order_status_recovered_stop_for_reconcile:")
        )
        self.assertEqual(execution["rejections"], [])

    def test_execute_blocks_when_testnet_account_cannot_trade(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeTestnetOrderClient] = []

        def order_client_factory(**_kwargs):
            client = _FakeTestnetOrderClient(can_trade=False)
            created_clients.append(client)
            return client

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                understand=True,
                confirmation=TESTNET_STRATEGY_CONFIRMATION,
            ),
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=order_client_factory,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("testnet_account_cannot_trade", summary["blockers"])
        self.assertEqual(created_clients[0].submitted, [])

    def test_execute_blocks_when_testnet_available_balance_is_zero(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created_clients: list[_FakeTestnetOrderClient] = []

        def order_client_factory(**_kwargs):
            client = _FakeTestnetOrderClient(available_balance=0.0)
            created_clients.append(client)
            return client

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(
                config_path=config_path,
                panel_path=panel_path,
                execute=True,
                understand=True,
                confirmation=TESTNET_STRATEGY_CONFIRMATION,
            ),
            env={"TESTNET_KEY": "key", "TESTNET_SECRET": "secret"},
            order_client_factory=order_client_factory,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("testnet_available_balance_not_positive", summary["blockers"])
        self.assertEqual(created_clients[0].submitted, [])

    def test_runner_requires_testnet_venue_config(self) -> None:
        config_path = self._config_path(venue="usdm_futures")
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_testnet_strategy_auto_order(
            _args(config_path=config_path, panel_path=panel_path),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("testnet_strategy_requires_testnet_venue:actual=usdm_futures", summary["blockers"])

    def _config_path(self, *, venue: str = "usdm_futures_testnet") -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_testnet.yaml"
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
                    "  api_key_env: TESTNET_KEY",
                    "  api_secret_env: TESTNET_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "risk:",
                    "  trading_enabled: false",
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


class _FakeTestnetOrderClient:
    def __init__(self, *, can_trade: bool = True, available_balance: float = 1000.0) -> None:
        self.can_trade = can_trade
        self.available_balance = float(available_balance)
        self.submitted: list[dict] = []

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "availableBalance": str(self.available_balance),
                "totalWalletBalance": str(self.available_balance),
                "positions": [
                    {"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"},
                    {"symbol": "ETHUSDT", "positionSide": "BOTH", "positionAmt": "0"},
                ],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"canTrade": self.can_trade})

    def position_mode(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": False})

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=[])

    def submit_testnet_strategy_order(self, **params):
        self.submitted.append(dict(params))
        order_id = 10_000 + len(self.submitted)
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": params["symbol"],
                "clientOrderId": params["newClientOrderId"],
                "orderId": order_id,
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


class _FakeUnknownStatusStrategyClient(_FakeTestnetOrderClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    def submit_testnet_strategy_order(self, **params):
        self.submitted.append(dict(params))
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
                "orderId": 20_001,
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


def _args(
    *,
    config_path: Path,
    panel_path: Path,
    execute: bool = False,
    understand: bool = False,
    confirmation: str = "",
) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel=str(panel_path),
        symbols="",
        public_market_data=False,
        execute_testnet_strategy_orders=execute,
        i_understand_this_uses_binance_usdm_testnet=understand,
        confirm_testnet_risk=confirmation,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 3, 0, 0, tzinfo=UTC)


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
