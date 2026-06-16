from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (
    CommandResult,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision_gate import (
    P9DA_GATE,
    P9DA_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9da_execute_single_post_only_canary_live_order import (
    APPROVE_P9DA_DECISION,
    build_canary_order_plan,
    build_phase9da,
)


class Phase9DASinglePostOnlyCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9da-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_blocks_when_btcusdt_minimum_notional_exceeds_approved_max_without_submit(self) -> None:
        paths = self._write_ready_p9cz_inputs()
        runner = SequenceCommandRunner(
            [
                _snapshot(),
                _account_collector(),
                _market_collector(min_notional="50", min_qty="0.001", best_bid="62841.90", best_ask="62842.00"),
                _snapshot(),
            ]
        )

        summary, exit_code = build_phase9da(
            self._args(paths, output_root=self.temp_dir / "p9da-blocked"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 0, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertFalse(summary["canary_order_plan_ready"])
        self.assertIn("canary_order_plan_not_ready", summary["blockers"])
        self.assertTrue(
            any(str(item).startswith("canary_minimum_notional_exceeds_authorized_max") for item in summary["blockers"])
        )
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertNotIn("remote_single_post_only_canary_order_submitter", runner.labels_seen)
        plan = _load_json(Path(summary["output_files"]["canary_order_plan"]))
        self.assertEqual(plan["minimum_executable_notional_usdt"], "62.8419")

    def test_ready_path_submits_exactly_one_fake_post_only_canary(self) -> None:
        paths = self._write_ready_p9cz_inputs()
        runner = SequenceCommandRunner(
            [
                _snapshot(),
                _account_collector(),
                _market_collector(min_notional="5", min_qty="0.001", best_bid="10000.00", best_ask="10000.10"),
                {
                    "contract_version": "hv_balanced_dth60_coinglass_phase9da_remote_single_post_only_canary_submitter.v1",
                    "status": "ready",
                    "blockers": [],
                    "client_order_id": "p9da-test",
                    "orders_submitted": 1,
                    "orders_canceled": 1,
                    "fill_count": 0,
                    "trade_count": 0,
                    "side_effects": {
                        "orders_submitted": 1,
                        "orders_canceled": 1,
                        "fill_count": 0,
                        "trade_count": 0,
                        "remote_files_written": 0,
                        "remote_sync_performed": False,
                        "supervisor_invoked": False,
                        "timer_path_invoked": False,
                        "candidate_executed": False,
                        "executor_input_mutated": False,
                        "target_plan_replaced": False,
                    },
                },
                _snapshot(),
            ]
        )

        summary, exit_code = build_phase9da(
            self._args(paths, output_root=self.temp_dir / "p9da-ready"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 5, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["canary_order_plan_ready"])
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["orders_canceled"], 1)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertIn("remote_single_post_only_canary_order_submitter", runner.labels_seen)

    def test_bad_p9cz_blocks_before_remote_commands(self) -> None:
        paths = self._write_ready_p9cz_inputs()
        p9cz = _load_json(paths["p9cz_summary"])
        p9cz["allowed_next_gate"] = "P9DA_wrong_gate"
        _write_json(paths["p9cz_summary"], p9cz)
        runner = SequenceCommandRunner([])

        summary, exit_code = build_phase9da(
            self._args(paths, output_root=self.temp_dir / "p9da-bad-p9cz"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 10, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cz_summary_ready_for_p9da", summary["blockers"])
        self.assertEqual(runner.labels_seen, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_canary_plan_rejects_crossing_buy_price(self) -> None:
        plan = build_canary_order_plan(
            {
                "status": "ready",
                "book": {"best_bid": ["100.00", "1"], "best_ask": ["100.00", "1"]},
            },
            _exchange_filters(min_notional="5", min_qty="0.001"),
            _terms(),
        )

        self.assertEqual(plan.status, "blocked")
        self.assertIn("invalid_or_locked_spread:bid=100.00:ask=100.00", plan.blockers)

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cz_summary=str(paths["p9cz_summary"]),
            remote_host="root@203.0.113.10",
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            expected_egress_ip="203.0.113.10",
            canary_symbol="BTCUSDT",
            canary_side="BUY",
            max_history_symbols=20,
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DA_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cz_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9cz"
        proof_root = root / "proof_artifacts" / "p9cz" / "run"
        project_profile = self.temp_dir / "project_profile.json"
        terms = proof_root / "approved_single_canary_terms.json"
        pre_submit = proof_root / "pre_submit_requirements_for_p9da.json"
        decision = proof_root / "final_owner_live_order_decision.json"
        summary = root / "summary.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(terms, _terms())
        _write_json(
            pre_submit,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9cz_pre_submit_requirements_for_p9da.v1",
                "fresh_pre_submit_readback_max_age_seconds": 30,
                "order_lifetime_seconds": 60,
                "candidate_artifact_stale_after_seconds": 60,
                "cancel_if_not_maker_or_unexpected_delta": True,
                "required_before_any_future_order_submission": [
                    "fresh pre-submit account read using /fapi/v2/account.canTrade",
                    "fresh pre-submit position and open-order fingerprint",
                    "fresh pre-submit order/fill/trade delta fingerprint",
                    "fresh order book and exchange filter readback",
                    "post-only GTX limit price must not cross spread",
                    "kill switch readable and rollback path documented",
                    "candidate target plan hash must match approved P9CZ candidate hash",
                    "executor input replacement must be scoped to one canary cycle only",
                ],
            },
        )
        _write_json(decision, {"decision_status": "approved"})
        payload = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9cz_final_owner_live_order_decision_gate_ready": True,
            "p9cz_satisfies_final_owner_live_order_decision_gate": True,
            "final_owner_live_order_gate_approval_collected": True,
            "explicit_final_owner_live_order_decision_collected": True,
            "live_order_submission_authorized": True,
            "candidate_enter_executor_target_plan_path_authorized": True,
            "target_plan_replacement_authorized": True,
            "candidate_execution_authorized": True,
            "authorization_scope": "future_p9da_single_post_only_canary_only",
            "eligible_for_future_p9da_single_post_only_canary_execution": True,
            "fresh_pre_submit_readback_required_before_p9da": True,
            "allowed_next_gate": P9DA_GATE,
            "allowed_next_gate_scope": P9DA_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "canary_symbol": "BTCUSDT",
            "canary_side": "BUY",
            "max_notional_usdt": 10.0,
            "risk_ceiling_usdt": 25.0,
            "max_orders_per_cycle": 1,
            "max_symbols_per_cycle": 1,
            "order_type": "post_only_limit",
            "time_in_force": "GTX",
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
            "limit_order_must_not_cross_spread": True,
            "only_distance_to_high_60_contribution_changed": True,
            "actual_live_order_submission_performed": False,
            "remote_execution_performed": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "baseline_target_plan_sha256": "baseline-sha",
            "candidate_target_plan_sha256": "candidate-sha",
            "output_files": {
                "approved_single_canary_terms": str(terms),
                "pre_submit_requirements_for_p9da": str(pre_submit),
                "final_owner_live_order_decision": str(decision),
            },
        }
        _write_json(summary, payload)
        return {"project_profile": project_profile, "p9cz_summary": summary}


class SequenceCommandRunner:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.labels_seen: list[str] = []

    def __call__(self, args: list[str]) -> CommandResult:
        command = " ".join(str(item) for item in args)
        if "remote_stdout_v2v3_account_collector" in command:
            self.labels_seen.append("remote_stdout_pit_safe_v2v3_account_collector")
        elif "remote_stdout_collector.v1" in command:
            self.labels_seen.append("remote_stdout_market_and_fingerprint_collector")
        elif "phase9da_remote_single_post_only_canary_submitter" in command:
            self.labels_seen.append("remote_single_post_only_canary_order_submitter")
        elif "systemctl" in command or "remote_live_config_sha256" in command:
            label = "pre_control_snapshot" if "pre_control_snapshot" not in self.labels_seen else "post_control_snapshot"
            self.labels_seen.append(label)
        else:
            self.labels_seen.append("unknown")
        if not self.payloads:
            raise AssertionError(f"unexpected command: {command[:200]}")
        payload = self.payloads.pop(0)
        return CommandResult(args=list(args), returncode=0, stdout=json.dumps(payload), stderr="")


def _snapshot() -> dict[str, object]:
    return {
        "status": "ready",
        "remote_live_config_sha256": "config-sha",
        "live_supervisor_sha256": "supervisor-sha",
        "operator_state": {"paused": False, "live_delta_armed": True},
        "systemd_units": {
            "meridian-alpha.timer": {
                "LoadState": "loaded",
                "UnitFileState": "enabled",
                "ActiveState": "active",
                "SubState": "waiting",
                "FragmentPath": "/etc/systemd/system/meridian-alpha.timer",
            }
        },
    }


def _identity() -> dict[str, object]:
    return {
        "whoami": "root",
        "repo_path": "/root/meridian_alpha_live_runner/repo",
        "config_path": "/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
        "egress_ip": "203.0.113.10",
        "config_sha256": "config-sha",
        "live_supervisor_sha256": "supervisor-sha",
    }


def _endpoint(path: str, payload: object) -> dict[str, object]:
    return {
        "status": "ok",
        "status_code": 200,
        "method": "GET",
        "path": path,
        "started_at_utc": "2026-06-08T10:00:00Z",
        "finished_at_utc": "2026-06-08T10:00:00Z",
        "payload": payload,
    }


def _account_collector() -> dict[str, object]:
    endpoint_results = {
        "account_v2": _endpoint(
            "/fapi/v2/account",
            {
                "canTrade": True,
                "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
                "positions": [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
            },
        ),
        "account_v3": _endpoint(
            "/fapi/v3/account",
            {
                "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
                "positions": [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
            },
        ),
        "account_config": _endpoint("/fapi/v1/accountConfig", {"dualSidePosition": False}),
        "position_mode": _endpoint("/fapi/v1/positionSide/dual", {"dualSidePosition": False}),
        "open_orders": _endpoint("/fapi/v1/openOrders", []),
        "api_restrictions": _endpoint(
            "/sapi/v1/account/apiRestrictions",
            {"enableReading": True, "enableFutures": True, "enableWithdrawals": False, "ipRestrict": True},
        ),
    }
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1",
        "status": "ready",
        "blockers": [],
        "remote_runner_identity_readback": _identity(),
        "pre_egress_ip": "203.0.113.10",
        "post_egress_ip": "203.0.113.10",
        "pre_endpoint_results": endpoint_results,
        "post_endpoint_results": endpoint_results,
        "proof_symbols": ["BTCUSDT"],
        "history_delta": {
            "order_history_fingerprint_stable": True,
            "trade_history_fingerprint_stable": True,
            "order_history_hash_pre": "orders",
            "order_history_hash_post": "orders",
            "trade_history_hash_pre": "trades",
            "trade_history_hash_post": "trades",
        },
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "fill_count": 0,
            "trade_count": 0,
            "http_methods_used": ["GET"],
            "only_http_get_endpoints": True,
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "supervisor_invoked": False,
            "timer_path_invoked": False,
            "candidate_executed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
        },
    }


def _market_collector(*, min_notional: str, min_qty: str, best_bid: str, best_ask: str) -> dict[str, object]:
    fresh_account = {
        "status": "ready",
        "pre": {
            "account_readable": True,
            "position_mode": "one_way",
            "open_order_count": 0,
            "egress_ip": "203.0.113.10",
            "expected_egress_ip": "203.0.113.10",
        },
        "post": {
            "account_readable": True,
            "position_mode": "one_way",
            "open_order_count": 0,
            "egress_ip": "203.0.113.10",
            "expected_egress_ip": "203.0.113.10",
        },
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "supervisor_invoked": False,
            "timer_path_invoked": False,
            "candidate_executed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
        },
    }
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_remote_stdout_collector.v1",
        "status": "ready",
        "blockers": [],
        "remote_runner_identity_readback": _identity(),
        "fresh_remote_account_read": fresh_account,
        "pre_position_fingerprint": {"stable_hash": "positions"},
        "post_position_fingerprint": {"stable_hash": "positions"},
        "pre_open_order_fingerprint": {"stable_hash": "open-orders"},
        "post_open_order_fingerprint": {"stable_hash": "open-orders"},
        "pre_balance_fingerprint": {"stable_hash": "balances"},
        "post_balance_fingerprint": {"stable_hash": "balances"},
        "pre_fill_trade_fingerprint": {
            "order_history_fingerprint": {"history_hash": "orders"},
            "trade_history_fingerprint": {"history_hash": "trades"},
        },
        "post_fill_trade_fingerprint": {
            "order_history_fingerprint": {"history_hash": "orders"},
            "trade_history_fingerprint": {"history_hash": "trades"},
        },
        "fresh_order_book": {
            "status": "ready",
            "symbol": "BTCUSDT",
            "book": {"best_bid": [best_bid, "1"], "best_ask": [best_ask, "1"]},
        },
        "exchange_filter_readback": _exchange_filters(min_notional=min_notional, min_qty=min_qty),
        "fingerprint_stability": {
            "position_fingerprint_stable": True,
            "open_order_fingerprint_stable": True,
            "balance_fingerprint_stable": True,
            "fill_trade_fingerprint_stable": True,
        },
        "side_effects": fresh_account["side_effects"],
    }


def _exchange_filters(*, min_notional: str, min_qty: str) -> dict[str, object]:
    return {
        "status": "ready",
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "1", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": min_qty, "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": min_notional},
                ],
            }
        ],
        "symbol_count": 1,
    }


def _terms() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_approved_single_canary_terms.v1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "risk_ceiling_usdt": 25.0,
        "max_notional_usdt": 10.0,
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "only_distance_to_high_60_contribution_changed": True,
        "baseline_target_plan_sha256": "baseline-sha",
        "candidate_target_plan_sha256": "candidate-sha",
        "reduce_only_required_for_rollback_exits": True,
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
