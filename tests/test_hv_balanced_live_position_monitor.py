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

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmResponse  # noqa: E402
from enhengclaw.live_trading.live_position_monitor import run_live_position_monitor  # noqa: E402


class HvBalancedLivePositionMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-live-position-monitor-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_monitor_recommends_hold_when_positions_match_reference(self) -> None:
        config_path = self._config_path()
        reference_run = self._reference_run()
        client = _FakeMonitorClient(
            positions={
                "BTCUSDT": 0.001,
                "SOLUSDT": 0.94,
                "AAVEUSDT": -0.9,
            }
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=reference_run),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_live_position_monitor")
        self.assertEqual(summary["operator_recommendation"], "HOLD_MANUAL_MONITOR")
        self.assertEqual(summary["open_order_count"], 0)
        self.assertEqual(summary["open_position_count"], 3)
        self.assertFalse(summary["recurring_mainnet_enabled"])
        artifact_root = Path(summary["artifact_root"])
        decision = json.loads((artifact_root / "operator_decision_matrix.json").read_text(encoding="utf-8"))
        self.assertIn("hold_and_monitor", decision["allowed_next_actions"])
        self.assertIn("recurring_mainnet_loop", decision["disallowed_next_actions"])

    def test_monitor_auto_resolves_latest_reconciled_delta_execution_reference(self) -> None:
        config_path = self._config_path()
        self._delta_execution_reference_run()
        client = _FakeMonitorClient(
            positions={
                "BTCUSDT": 0.006,
                "SOLUSDT": 5.57,
                "AAVEUSDT": -5.3,
            }
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=""),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_live_position_monitor")
        artifact_root = Path(summary["artifact_root"])
        request_context = json.loads((artifact_root / "request_context.json").read_text(encoding="utf-8"))
        self.assertEqual(request_context["reference"]["reference_type"], "mainnet_delta_execution")

    def test_monitor_prefers_newer_reconciled_delta_over_lexically_later_genesis(self) -> None:
        config_path = self._config_path()
        stale_genesis = self._genesis_reference_run(
            name="zzzz-20260517T-stale-post-management-genesis-snapshot",
            created_at_utc="2026-05-17T14:00:00Z",
            expected_positions={"BTCUSDT": 0.001, "SOLUSDT": 0.94, "AAVEUSDT": -0.9},
        )
        latest_delta = self._delta_execution_reference_run(
            finished_at_utc="2026-05-17T15:00:00Z",
            expected_positions={"BTCUSDT": 0.006, "SOLUSDT": 5.57, "AAVEUSDT": -5.3},
        )
        self.assertGreater(stale_genesis.name, latest_delta.name)
        client = _FakeMonitorClient(
            positions={
                "BTCUSDT": 0.006,
                "SOLUSDT": 5.57,
                "AAVEUSDT": -5.3,
            }
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=""),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_live_position_monitor")
        artifact_root = Path(summary["artifact_root"])
        request_context = json.loads((artifact_root / "request_context.json").read_text(encoding="utf-8"))
        self.assertEqual(request_context["reference"]["reference_type"], "mainnet_delta_execution")
        self.assertEqual(request_context["reference"]["reference_run"], str(latest_delta))

    def test_monitor_accepts_flat_expected_symbols_missing_from_position_risk(self) -> None:
        config_path = self._config_path()
        self._delta_execution_reference_run(expected_positions={"BTCUSDT": 0.006, "SOLUSDT": 0.0, "AAVEUSDT": 0.0})
        client = _FakeMonitorClient(positions={"BTCUSDT": 0.006})

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=""),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_live_position_monitor")

    def test_monitor_accepts_genesis_snapshot_reference(self) -> None:
        config_path = self._config_path()
        genesis = self._genesis_reference_run()
        client = _FakeMonitorClient(positions={"BTCUSDT": 0.006, "SOLUSDT": 5.57})

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=genesis),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_live_position_monitor")

    def test_monitor_blocks_when_open_orders_exist(self) -> None:
        config_path = self._config_path()
        reference_run = self._reference_run()
        client = _FakeMonitorClient(
            positions={"BTCUSDT": 0.001, "SOLUSDT": 0.94, "AAVEUSDT": -0.9},
            open_orders=[{"symbol": "BTCUSDT", "orderId": 1, "clientOrderId": "x"}],
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=reference_run),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked_live_position_monitor")
        self.assertIn("mainnet_open_orders_exist:1", summary["blockers"])
        self.assertEqual(summary["operator_recommendation"], "STOP_NEW_ENTRIES_FORCED_RECONCILE_REVIEW")

    def test_monitor_blocks_on_unexpected_position_and_drift(self) -> None:
        config_path = self._config_path()
        reference_run = self._reference_run()
        client = _FakeMonitorClient(
            positions={
                "BTCUSDT": 0.002,
                "SOLUSDT": 0.94,
                "AAVEUSDT": -0.9,
                "ETHUSDT": 0.01,
            }
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=reference_run),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertTrue(any(item.startswith("position_mismatch:BTCUSDT") for item in summary["blockers"]))
        self.assertIn("unexpected_live_position:ETHUSDT:0.01", summary["blockers"])

    def test_monitor_blocks_when_leverage_exceeds_config(self) -> None:
        config_path = self._config_path(max_leverage=2)
        reference_run = self._reference_run()
        client = _FakeMonitorClient(
            positions={"BTCUSDT": 0.001, "SOLUSDT": 0.94, "AAVEUSDT": -0.9},
            leverage=20,
        )

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=reference_run),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            mainnet_client_factory=lambda **_kwargs: client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("leverage_above_max:BTCUSDT:max=2:actual=20", summary["blockers"])

    def test_monitor_missing_credentials_never_calls_clients(self) -> None:
        config_path = self._config_path()
        reference_run = self._reference_run()

        def forbidden_client(**_kwargs):
            raise AssertionError("missing credentials should block before client construction")

        summary, exit_code = run_live_position_monitor(
            _args(config_path=config_path, reference_run=reference_run),
            env={},
            mainnet_client_factory=forbidden_client,
            permission_client_factory=forbidden_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("missing_api_key_env:LIVE_KEY", summary["blockers"])
        self.assertIn("missing_api_secret_env:LIVE_SECRET", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _config_path(self, *, max_leverage: int = 2) -> Path:
        config_path = self.temp_dir / "hv_balanced_mainnet_monitor.yaml"
        artifact_root = self.temp_dir / "runs"
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    f"  max_leverage: {max_leverage}",
                    "state:",
                    f"  artifact_root: {artifact_root.as_posix()}",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _reference_run(self) -> Path:
        run = self.temp_dir / "runs" / "20260517T125840117850Z-mainnet-single-run"
        run.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "price": 78000.0, "notional_usdt": 78.0},
                {"symbol": "SOLUSDT", "side": "BUY", "quantity": 0.94, "price": 86.0, "notional_usdt": 80.84},
                {"symbol": "AAVEUSDT", "side": "SELL", "quantity": 0.9, "price": 90.0, "notional_usdt": 81.0},
            ]
        ).to_csv(run / "fills.csv", index=False)
        pd.DataFrame(
            [
                {"usdm_symbol": "BTCUSDT", "side": "long", "target_notional_usdt": 83.33, "target_weight": 0.1667},
                {"usdm_symbol": "SOLUSDT", "side": "long", "target_notional_usdt": 83.33, "target_weight": 0.1667},
                {"usdm_symbol": "AAVEUSDT", "side": "short", "target_notional_usdt": 83.33, "target_weight": -0.1667},
            ]
        ).to_csv(run / "target_positions.csv", index=False)
        (run / "run_summary.json").write_text(
            json.dumps({"status": "mainnet_single_run_orders_submitted"}),
            encoding="utf-8",
        )
        return run

    def _delta_execution_reference_run(
        self,
        *,
        expected_positions: dict[str, float] | None = None,
        finished_at_utc: str | None = None,
    ) -> Path:
        run = self.temp_dir / "mainnet_delta_execution" / "20260517T145005387167Z-mainnet-delta-execution"
        run.mkdir(parents=True, exist_ok=True)
        expected_positions = expected_positions or {
            "BTCUSDT": 0.006,
            "SOLUSDT": 5.57,
            "AAVEUSDT": -5.3,
        }
        (run / "run_summary.json").write_text(
            json.dumps(
                {
                    "status": "mainnet_delta_orders_submitted",
                    "reconciliation_status": "reconciled",
                    "finished_at_utc": finished_at_utc or "2026-05-17T14:50:05Z",
                }
            ),
            encoding="utf-8",
        )
        (run / "reconciliation.json").write_text(
            json.dumps(
                {
                    "status": "reconciled",
                    "expected_positions": expected_positions,
                    "open_positions_redacted": [],
                }
            ),
            encoding="utf-8",
        )
        return run

    def _genesis_reference_run(
        self,
        *,
        name: str = "20260517T150000000000Z-genesis-snapshot",
        created_at_utc: str = "2026-05-17T15:00:00Z",
        expected_positions: dict[str, float] | None = None,
    ) -> Path:
        run = self.temp_dir / "position_reference" / name
        run.mkdir(parents=True, exist_ok=True)
        (run / "run_summary.json").write_text(
            json.dumps({"status": "mainnet_position_genesis_snapshot", "created_at_utc": created_at_utc}),
            encoding="utf-8",
        )
        expected_positions = expected_positions or {"BTCUSDT": 0.006, "SOLUSDT": 5.57}
        pd.DataFrame(
            [
                {"symbol": symbol, "expected_position_amt": amount}
                for symbol, amount in expected_positions.items()
            ]
        ).to_csv(run / "reference_positions.csv", index=False)
        return run


def _args(*, config_path: Path, reference_run: Path | str) -> Namespace:
    return Namespace(
        config=str(config_path),
        reference_run=str(reference_run) if reference_run else "",
        api_key_env="",
        api_secret_env="",
        max_abs_position_drift_qty=1e-9,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 14, 30, 0, tzinfo=UTC)


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


class _FakeMonitorClient:
    def __init__(
        self,
        *,
        positions: dict[str, float],
        open_orders: list[dict] | None = None,
        margin_type: str = "cross",
        leverage: int = 2,
    ) -> None:
        self.positions = dict(positions)
        self.open_orders = list(open_orders or [])
        self.margin_type = margin_type
        self.leverage = leverage

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "canTrade": True,
                "availableBalance": "1000",
                "totalWalletBalance": "1000",
                "totalMarginBalance": "1000",
                "positions": [
                    {
                        "symbol": symbol,
                        "positionSide": "BOTH",
                        "positionAmt": str(amount),
                        "notional": str(amount * 100.0),
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
