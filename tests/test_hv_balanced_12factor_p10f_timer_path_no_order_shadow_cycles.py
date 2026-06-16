from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
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

from scripts.live_trading.run_hv_balanced_12factor_p10f_timer_path_no_order_shadow_cycles import (  # noqa: E402
    file_sha256,
    run_p10f_timer_path_no_order_shadow_cycles,
)


class FakeSupervisorRunner:
    def __init__(self, *, orders_submitted: int = 0, blockers: list[str] | None = None) -> None:
        self.calls: list[Namespace] = []
        self.kwargs: list[dict[str, object]] = []
        self.orders_submitted = int(orders_submitted)
        self.blockers = list(blockers or [])

    def __call__(self, args: Namespace, **kwargs: object) -> tuple[dict[str, object], int]:
        self.calls.append(args)
        self.kwargs.append(dict(kwargs))
        cycle_index = len(self.calls)
        core_blockers = list(self.blockers)
        orders = self.orders_submitted
        core_loop_runner = kwargs.get("core_loop_runner")
        if callable(core_loop_runner):
            core, _core_exit = core_loop_runner(Namespace())
            core = dict(core)
        else:
            core = {
                "run_id": f"fake-core-{cycle_index:03d}",
                "status": "mainnet_core_loop_completed" if not core_blockers else "mainnet_core_loop_blocked",
                "blockers": core_blockers,
                "execution_requested": False,
                "live_delta_authorized": False,
                "orders_submitted": orders,
                "fill_count": 0,
                "cycles": [
                    {
                        "status": "cycle_plan_only_ready" if not core_blockers else "cycle_blocked",
                        "blockers": core_blockers,
                        "orders_submitted": orders,
                        "fill_count": 0,
                    }
                ],
            }
        supervisor_cycle = {
            "cycle_index": 1,
            "status": "cycle_observed_no_order" if not core_blockers and orders == 0 else "cycle_blocked",
            "blockers": core_blockers,
            "execute_live_delta_requested": False,
            "live_delta_authorized": False,
            "orders_submitted": orders,
            "fill_count": 0,
            "core_loop_summary": core,
        }
        summary = {
            "run_id": f"fake-supervisor-{cycle_index:03d}",
            "status": "mainnet_live_supervisor_completed"
            if not core_blockers and orders == 0
            else "mainnet_live_supervisor_blocked",
            "blockers": core_blockers,
            "artifact_root": str(Path(args.config).parent / f"fake-supervisor-{cycle_index:03d}"),
            "completed_cycle_count": 1,
            "orders_submitted": orders,
            "fill_count": 0,
            "live_delta_authorized": False,
            "cycles": [supervisor_cycle],
        }
        return summary, 0 if summary["status"] == "mainnet_live_supervisor_completed" else 2


class HvBalanced12FactorP10fTimerPathNoOrderShadowCyclesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10f-timer-shadow-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p10f_ready_runs_three_real_supervisor_entrypoint_shadow_cycles_no_order(self) -> None:
        p10e_summary = self._write_p10e_artifacts()
        base_config = self._write_base_config()
        runner = FakeSupervisorRunner()

        summary, exit_code = run_p10f_timer_path_no_order_shadow_cycles(
            Namespace(
                p10e_summary=p10e_summary,
                base_config=base_config,
                output_root=self.temp_dir / "proof_artifacts" / "p10f",
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="BTCUSDT",
                fixture_panel="",
                public_market_data=False,
                target_engine="multiphase_equal_sleeve",
                position_tolerance=1e-9,
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 0, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p10f_timer_path_no_order_shadow_cycles_ready"])
        self.assertEqual(summary["completed_shadow_cycles"], 3)
        self.assertTrue(summary["fresh_proof_each_cycle"])
        self.assertTrue(summary["baseline_only_executor"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["candidate_scorer_loaded_into_executor"])
        self.assertFalse(summary["candidate_scorer_loaded_into_timer"])
        self.assertFalse(summary["candidate_scorer_loaded_into_supervisor"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["no_anomalies"])
        generated_config = _load_json(Path(summary["output_files"]["generated_no_order_config"]))
        self.assertFalse(generated_config["risk"]["trading_enabled"])
        self.assertFalse(generated_config["core_loop"]["live_delta_enabled"])
        self.assertFalse(generated_config["core_loop"]["submit_orders"])
        self.assertFalse(generated_config["mainnet_live_supervisor"]["allow_live_delta_when_armed"])

    def test_p10f_blocks_when_p10e_is_not_ready_and_does_not_run_supervisor(self) -> None:
        p10e_summary = self._write_p10e_artifacts({"disabled_baseline_scores_byte_for_byte_unchanged": False})
        base_config = self._write_base_config()
        runner = FakeSupervisorRunner()

        summary, exit_code = run_p10f_timer_path_no_order_shadow_cycles(
            Namespace(
                p10e_summary=p10e_summary,
                base_config=base_config,
                output_root=self.temp_dir / "proof_artifacts" / "blocked",
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="",
                fixture_panel="",
                public_market_data=False,
                target_engine="",
                position_tolerance=1e-9,
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 5, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(runner.calls, [])
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10e_ready", summary["blockers"])
        self.assertFalse(summary["p10f_timer_path_no_order_shadow_cycles_ready"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p10f_blocks_on_any_order_delta_and_keeps_live_order_unauthorized(self) -> None:
        p10e_summary = self._write_p10e_artifacts()
        base_config = self._write_base_config()
        runner = FakeSupervisorRunner(orders_submitted=1)

        summary, exit_code = run_p10f_timer_path_no_order_shadow_cycles(
            Namespace(
                p10e_summary=p10e_summary,
                base_config=base_config,
                output_root=self.temp_dir / "proof_artifacts" / "order-delta",
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="",
                fixture_panel="",
                public_market_data=False,
                target_engine="",
                position_tolerance=1e-9,
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 10, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("ran_requested_cycle_count", summary["blockers"])
        self.assertIn("all_supervisor_no_order_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 1)

    def test_p10f_retained_fixture_uses_reference_run_and_keeps_candidate_shadow_only(self) -> None:
        p10e_summary = self._write_p10e_artifacts()
        base_config = self._write_base_config()
        retained_sources = self._write_retained_fixture_sources()
        runner = FakeSupervisorRunner()

        summary, exit_code = run_p10f_timer_path_no_order_shadow_cycles(
            Namespace(
                p10e_summary=p10e_summary,
                base_config=base_config,
                output_root=self.temp_dir / "proof_artifacts" / "retained-fixture",
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="BTCUSDT",
                fixture_panel="",
                public_market_data=False,
                target_engine="multiphase_equal_sleeve",
                account_proof_source=retained_sources["account_proof"],
                position_reference_source=retained_sources["position_reference"],
                retained_p9aa_summary=retained_sources["p9aa_summary"],
                position_tolerance=1e-9,
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 20, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["retained_fixture_requested"])
        self.assertTrue(summary["gates"]["pit_safe_position_reference_fixture_ready"])
        self.assertTrue(summary["gates"]["retained_account_plan_fixture_ready"])
        self.assertEqual(len(runner.calls), 3)
        self.assertTrue(all(Path(call.reference_run).exists() for call in runner.calls))
        self.assertTrue(all(call.reference_run == runner.calls[0].reference_run for call in runner.calls))
        self.assertTrue(all(callable(kwargs.get("core_loop_runner")) for kwargs in runner.kwargs))
        self.assertTrue(summary["baseline_only_executor"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["target_plan_replaced"])

    def _write_p10e_artifacts(self, overrides: dict | None = None) -> Path:
        root = self.temp_dir / "p10e"
        root.mkdir(parents=True, exist_ok=True)
        baseline = root / "baseline.csv"
        shadow = root / "shadow.csv"
        ctx = root / "ctx.json"
        pd.DataFrame(
            [
                {"symbol": "BTCUSDT", "subject": "BTC", "score": 0.0, "score_source": "baseline"},
                {"symbol": "ETHUSDT", "subject": "ETH", "score": 0.0, "score_source": "baseline"},
            ]
        ).to_csv(baseline, index=False)
        pd.DataFrame(
            [
                {"symbol": "BTCUSDT", "subject": "BTC", "shadow_score": 0.25, "score_source": "shadow"},
                {"symbol": "ETHUSDT", "subject": "ETH", "shadow_score": -0.15, "score_source": "shadow"},
            ]
        ).to_csv(shadow, index=False)
        _write_json(
            ctx,
            {
                "baseline_scores_copy": {"path": str(baseline), "exists": True, "sha256": file_sha256(baseline)},
                "shadow_scores_copy": {"path": str(shadow), "exists": True, "sha256": file_sha256(shadow)},
            },
        )
        summary = {
            "status": "ready",
            "blockers": [],
            "p10d_ready": True,
            "disabled_baseline_scores_byte_for_byte_unchanged": True,
            "disabled_executor_consumes_baseline_only": True,
            "disabled_shadow_artifacts_written_count": 0,
            "enabled_executor_consumes_baseline_only": True,
            "enabled_shadow_artifacts_under_proof_artifacts_only": True,
            "enabled_shadow_scorer_referenced_by_executor": False,
            "candidate_scorer_loaded_into_live_scorer_entry": False,
            "executor_invoked": False,
            "timer_path_invoked": False,
            "supervisor_invoked": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "artifacts": {"context": str(ctx)},
        }
        summary.update(overrides or {})
        summary_path = root / "summary.json"
        _write_json(summary_path, summary)
        return summary_path

    def _write_base_config(self) -> Path:
        path = self.temp_dir / "base.json"
        _write_json(
            path,
            {
                "binance": {"venue": "usdm_futures"},
                "risk": {"trading_enabled": False},
                "core_loop": {
                    "target_engine": "multiphase_equal_sleeve",
                    "live_delta_enabled": False,
                    "submit_orders": False,
                    "auto_confirm_delta_after_preflight": False,
                    "max_cycles_per_invocation": 1,
                },
                "mainnet_live_supervisor": {
                    "target_engine": "multiphase_equal_sleeve",
                    "allow_live_delta_when_armed": False,
                    "max_cycles_per_invocation": 1,
                    "interval_seconds": 0,
                },
                "mainnet_health_monitor": {
                    "no_order_expected": True,
                    "require_systemd_timer_active": False,
                },
                "state": {
                    "sqlite_path": str(self.temp_dir / "state.sqlite3"),
                    "artifact_root": str(self.temp_dir / "runs"),
                },
            },
        )
        return path

    def _write_retained_fixture_sources(self) -> dict[str, Path]:
        root = self.temp_dir / "retained_sources"
        root.mkdir(parents=True, exist_ok=True)
        finished_at = "2026-06-07T00:00:00Z"
        account_proof = root / "fresh_remote_account_read_pre.json"
        position_reference = root / "position_fingerprint_pre.json"
        p9aa_summary = root / "p9aa_summary.json"
        current_positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.001",
                "positionSide": "BOTH",
                "entryPrice": "60000",
                "breakEvenPrice": "60000",
                "isolated": "false",
                "isolatedWallet": "0",
            }
        ]
        side_effects = {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        }
        _write_json(
            account_proof,
            {
                "account_readable": True,
                "can_trade": True,
                "position_mode": "one_way",
                "egress_ip": "203.0.113.10",
                "expected_egress_ip": "203.0.113.10",
                "open_order_count": 0,
                "open_position_count": 1,
                "finished_at_utc": finished_at,
                "blockers": ["mainnet_open_positions_exist:1"],
                "side_effects": side_effects,
                "endpoint_results": {
                    name: {"status": "ok"}
                    for name in (
                        "account_config",
                        "account_information_v3",
                        "api_key_permissions",
                        "exchange_info",
                        "open_orders",
                        "position_mode",
                    )
                },
            },
        )
        _write_json(
            position_reference,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ag_position_fingerprint.v1",
                "status": "ready",
                "blockers": [],
                "finished_at_utc": finished_at,
                "open_order_count": 0,
                "open_position_count": 1,
                "side_effects": side_effects,
                "position_fingerprint": {"stable_hash": "stable-position-hash", "stable_rows": current_positions},
            },
        )
        core_cycle = {
            "status": "cycle_plan_only_ready",
            "blockers": [],
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "target_engine": "multiphase_equal_sleeve",
            "plan_artifact_root": str(root / "retained_plan"),
            "account_reconcile_artifacts": {
                "account": {
                    "available_balance_usdt": 100.0,
                    "total_wallet_balance_usdt": 100.0,
                    "total_margin_balance_usdt": 100.0,
                },
                "monitor_report": {"status": "passed_live_position_monitor", "blockers": []},
            },
            "strategy_plan_artifacts": {
                "current_positions": current_positions,
                "target_portfolio": {"weights": {"BTCUSDT": 0.0}},
                "target_positions": [{"symbol": "BTCUSDT", "target_position_amt": "0"}],
                "execution_plan": {"orders": []},
                "order_sizing_report": [],
                "delta_orders": [],
                "risk_gate": {"status": "passed"},
                "run_summary": {"status": "ready"},
            },
        }
        _write_json(
            p9aa_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1",
                "status": "ready",
                "blockers": [],
                "completed_shadow_cycles": 1,
                "fresh_proof_each_cycle": True,
                "same_risk_no_order_config_each_cycle": True,
                "position_reference_fixture_ready": True,
                "position_reference_fixture_requested": True,
                "account_read_blockers": [],
                "orders_submitted": 0,
                "fill_count": 0,
                "cycle_rows": [
                    {
                        "cycle_index": 1,
                        "cycle_ready": True,
                        "hook_summary": {
                            "executor_consumes_baseline_only": True,
                            "candidate_plan_referenced_by_executor": False,
                            "candidate_artifacts_under_proof_artifacts_only": True,
                            "orders_submitted": 0,
                            "fill_count": 0,
                        },
                        "supervisor_summary": {
                            "cycles": [{"core_loop_summary": {"cycles": [core_cycle]}}],
                        },
                    }
                ],
            },
        )
        return {
            "account_proof": account_proof,
            "position_reference": position_reference,
            "p9aa_summary": p9aa_summary,
        }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
