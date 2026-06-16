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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms import (  # noqa: E402
    P10I_GATE,
    stable_payload_sha256,
)
from scripts.live_trading.run_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary import (  # noqa: E402
    APPROVE_P10I_DECISION,
    CandidateDelta,
    build_canary_order_plan,
    build_p10i,
    canary_position_rollback_contract,
    derive_candidate_delta,
    remote_p10i_order_command,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    CommandResult,
)


class HvBalanced12FactorP10iLiveDeltaCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10i-live-delta-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_path_derives_sell_from_p10g_delta_and_submits_one_fake_post_only_canary(self) -> None:
        paths = self._write_ready_inputs()
        runner = SequenceCommandRunner(
            [
                _snapshot(),
                _account_collector(),
                _market_collector(min_notional="5", min_qty="0.001", best_bid="10000.00", best_ask="10000.10"),
                _order_submission(side="SELL"),
                _snapshot(),
            ]
        )

        summary, exit_code = build_p10i(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10i-ready"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 0, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p10i_single_cycle_live_delta_canary_ready"])
        self.assertTrue(summary["p10h_sufficient_for_p10i_execution"])
        self.assertTrue(summary["p10g_hash_bound_to_p10h"])
        self.assertEqual(summary["candidate_delta_side"], "SELL")
        self.assertEqual(summary["candidate_delta_notional_usdt"], "-1497.7849977386668")
        self.assertEqual(summary["canary_capped_notional_usdt"], "75")
        self.assertTrue(summary["fresh_pre_submit_readback_performed"])
        self.assertTrue(summary["canary_order_plan_ready"])
        self.assertEqual(summary["canary_side"], "SELL")
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["orders_canceled"], 1)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["continuous_automation_enabled"])
        self.assertIn("remote_single_cycle_live_delta_canary_order_submitter", runner.labels_seen)

        delta = _load_json(Path(summary["output_files"]["candidate_delta_binding"]))
        plan = _load_json(Path(summary["output_files"]["canary_order_plan"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertEqual(delta["side"], "SELL")
        self.assertEqual(plan["side"], "SELL")
        self.assertTrue(plan["limit_order_must_not_cross_spread"])
        self.assertEqual(plan["price"], "10000.2")
        self.assertEqual(plan["quantity"], "0.007")
        self.assertEqual(plan["notional_usdt"], "70.0014")
        self.assertTrue(control["live_order_submission_performed"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["ran_supervisor"])

    def test_nonflat_long_plus_sell_blocks_before_remote_order_submitter(self) -> None:
        paths = self._write_ready_inputs()
        runner = SequenceCommandRunner(
            [
                _snapshot(),
                _account_collector(position_amt="0.013"),
                _snapshot(),
            ]
        )

        summary, exit_code = build_p10i(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10i-nonflat-long-sell"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 2, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("nonflat_long_plus_sell_would_require_non_reduce_only_buy_restoration", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertNotIn("remote_single_cycle_live_delta_canary_order_submitter", runner.labels_seen)
        self.assertFalse(summary["canary_position_rollback_contract_ready"])

        rollback = _load_json(Path(summary["output_files"]["canary_position_rollback_contract"]))
        self.assertEqual(rollback["status"], "blocked")
        self.assertEqual(rollback["pre_position_amt"], "0.013")
        self.assertFalse(rollback["non_reduce_only_restoration_authorized"])

    def test_position_rollback_contract_allows_flat_sell_canary(self) -> None:
        paths = self._write_ready_inputs()
        account = _account_collector(position_amt="0")
        fixture = {
            "expected_egress_ip": "203.0.113.10",
            "pre_egress_ip": account["pre_egress_ip"],
            "post_egress_ip": account["post_egress_ip"],
            "pre_endpoint_results": account["pre_endpoint_results"],
            "post_endpoint_results": account["post_endpoint_results"],
            "side_effects": account["side_effects"],
        }
        from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
            build_pit_safe_account_proof,
        )

        proof = build_pit_safe_account_proof(fixture, generated_at=datetime(2026, 6, 8, 20, 3, 0, tzinfo=UTC))
        p10g = _load_json(paths["p10g_summary"])
        p10h = _load_json(paths["p10h_summary"])
        delta = derive_candidate_delta(p10g, p10h)
        contract = canary_position_rollback_contract(account_proof=proof, candidate_delta=delta)

        self.assertEqual(contract.status, "ready")
        self.assertEqual(contract.pre_position_amt, "0")
        self.assertTrue(contract.reduce_only_restoration_possible_if_filled)

    def test_remote_submitter_has_fail_safe_cancel_and_position_guard(self) -> None:
        command = remote_p10i_order_command(
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            expected_egress_ip="203.0.113.10",
            symbol="BTCUSDT",
            side="SELL",
            client_order_id="p10i-test",
            max_notional_usdt="75",
            order_lifetime_seconds=1,
            maker_buffer_ticks=50,
        )

        self.assertIn('params.setdefault("recvWindow", "30000")', command)
        self.assertIn('"/fapi/v2/positionRisk"', command)
        self.assertIn("canary_order_query_failed", command)
        self.assertIn("canary_cancel_after_query_failed_failed", command)
        self.assertIn("nonflat_long_plus_sell_would_require_non_reduce_only_buy_restoration", command)

    def test_bad_p10h_blocks_before_remote_commands(self) -> None:
        paths = self._write_ready_inputs()
        p10h = _load_json(paths["p10h_summary"])
        p10h["allowed_next_gate"] = "P10I_wrong_gate"
        _write_json(paths["p10h_summary"], p10h)
        runner = SequenceCommandRunner([])

        summary, exit_code = build_p10i(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10i-bad-p10h"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 5, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10h_summary_ready_for_p10i", summary["blockers"])
        self.assertEqual(runner.labels_seen, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_canary_order_plan_rejects_sell_that_would_cross_spread(self) -> None:
        delta = CandidateDelta(
            status="ready",
            blockers=[],
            symbol="BTCUSDT",
            side="SELL",
            baseline_target_notional_usdt="100",
            candidate_target_notional_usdt="-100",
            target_notional_delta_usdt="-200",
            approved_notional_cap_usdt="75",
            canary_notional_usdt="75",
            target_plan_diff_sha256="diff-sha",
        )

        plan = build_canary_order_plan(
            {
                "status": "ready",
                "book": {"best_bid": ["100.00", "1"], "best_ask": ["100.00", "1"]},
            },
            _exchange_filters(min_notional="5", min_qty="0.001"),
            delta,
        )

        self.assertEqual(plan.status, "blocked")
        self.assertIn("invalid_or_locked_spread:bid=100.00:ask=100.00", plan.blockers)

    def test_derive_candidate_delta_requires_p10h_hash_match(self) -> None:
        paths = self._write_ready_inputs()
        p10g = _load_json(paths["p10g_summary"])
        p10h = _load_json(paths["p10h_summary"])
        p10h["candidate_plan_hash"] = "wrong"

        delta = derive_candidate_delta(p10g, p10h)

        self.assertEqual(delta.status, "blocked")
        self.assertIn("p10h_candidate_hash_mismatch_with_p10g", delta.blockers)
        self.assertEqual(delta.side, "SELL")

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            p10h_summary=str(paths["p10h_summary"]),
            p10g_summary=str(paths["p10g_summary"]),
            remote_host="root@203.0.113.10",
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            expected_egress_ip="203.0.113.10",
            max_history_symbols=20,
            ssh_connect_timeout=10,
            order_lifetime_seconds=0,
            maker_buffer_ticks=1,
            owner="rulebook_owner",
            owner_decision=APPROVE_P10I_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "inputs"
        project_profile = root / "project_profile.json"
        candidate_plan = root / "p10g" / "candidate_target_plan.json"
        target_plan_diff = root / "p10g" / "target_plan_diff.json"
        p10g_summary = root / "p10g" / "summary.json"
        p10h_terms = root / "p10h" / "proof" / "single_cycle_live_delta_canary_terms.json"
        p10h_summary = root / "p10h" / "summary.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        candidate_payload = {
            "contract_version": "hv_balanced_12factor_p10g_target_plan.v1",
            "positions": [
                {"symbol": "BTCUSDT", "side": "short", "target_weight": -0.1, "target_notional_usdt": -561.669374152},
                {"symbol": "ETHUSDT", "side": "short", "target_weight": -0.1, "target_notional_usdt": -561.669374152},
            ],
        }
        candidate_sha = stable_payload_sha256(candidate_payload)
        _write_json(candidate_plan, candidate_payload)
        _write_json(
            target_plan_diff,
            {
                "contract_version": "hv_balanced_12factor_p10g_target_plan_diff.v1",
                "changed_symbol_count": 1,
                "changed_symbols": ["BTCUSDT"],
                "rows": [
                    {
                        "symbol": "BTCUSDT",
                        "baseline_target_notional_usdt": 936.1156235866666,
                        "candidate_target_notional_usdt": -561.669374152,
                        "target_notional_delta_usdt": -1497.7849977386668,
                    }
                ],
            },
        )
        _write_json(
            p10g_summary,
            {
                "status": "ready",
                "p10g_candidate_target_plan_replacement_dry_run_ready": True,
                "candidate_target_plan_replacement_semantics_proven": True,
                "hash_binding_proven": True,
                "baseline_fallback_proven": True,
                "kill_switch_proven": True,
                "actual_executor_input_changed": False,
                "actual_target_plan_replaced": False,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "baseline_target_plan_sha256": "baseline-sha",
                "candidate_target_plan_sha256": candidate_sha,
                "output_files": {
                    "candidate_target_plan": str(candidate_plan),
                    "target_plan_diff": str(target_plan_diff),
                },
            },
        )
        terms = {
            "contract_version": "hv_balanced_12factor_p10h_single_cycle_live_delta_canary_terms.v1",
            "max_notional_usdt": 75.0,
            "symbol": "BTCUSDT",
            "order_type": "post_only_limit",
            "maker_only_required": True,
            "post_only_required": True,
            "time_in_force": "GTX",
            "cycles": 1,
            "continuous_automation": False,
            "max_orders_per_cycle": 1,
            "max_symbols_per_cycle": 1,
            "market_orders_allowed": False,
            "side": "derive_from_fresh_candidate_delta",
            "quantity": "derive_from_fresh_candidate_delta_capped_by_max_notional_and_exchange_filters",
            "candidate_plan_hash": candidate_sha,
            "baseline_fallback": "any_check_failure_reverts_to_baseline_only",
            "kill_switch": "candidate_live_delta_enabled=false / revert baseline-only",
            "rollback": "cancel open order; reduce-only close only if filled; post-run reconciliation",
        }
        _write_json(p10h_terms, terms)
        _write_json(
            p10h_summary,
            {
                "contract_version": "hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms.v1",
                "status": "ready",
                "blockers": [],
                "p10h_owner_gate_single_cycle_live_delta_canary_terms_ready": True,
                "approved_max_notional_usdt": 75.0,
                "approved_symbol": "BTCUSDT",
                "approved_order_type": "post_only_limit",
                "approved_time_in_force": "GTX",
                "approved_cycles": 1,
                "continuous_automation": False,
                "candidate_plan_hash": candidate_sha,
                "candidate_plan_hash_binding_ready": True,
                "baseline_fallback_ready": True,
                "kill_switch_ready": True,
                "rollback_ready": True,
                "future_p10i_single_cycle_canary_authorized_if_separately_requested": True,
                "fresh_remote_proof_required_before_execution": True,
                "execute_canary_inside_p10h": False,
                "candidate_execution_authorized_now": False,
                "live_order_submission_authorized_now": False,
                "target_plan_replacement_authorized_now": False,
                "executor_input_mutation_authorized_now": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "remote_sync_authorized": False,
                "remote_execution_authorized": False,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
                "allowed_next_gate": P10I_GATE,
                "allowed_next_gate_must_be_separately_requested": True,
                "source_evidence": {
                    "p10g_summary": {"path": str(p10g_summary), "exists": True, "sha256": "unused-in-test"}
                },
                "output_files": {
                    "terms": str(p10h_terms),
                    "summary": str(p10h_summary),
                },
            },
        )
        return {"project_profile": project_profile, "p10g_summary": p10g_summary, "p10h_summary": p10h_summary}


class SequenceCommandRunner:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.labels_seen: list[str] = []

    def __call__(self, args: Sequence[str]) -> CommandResult:
        command = " ".join(str(item) for item in args)
        if "remote_stdout_v2v3_account_collector" in command:
            self.labels_seen.append("remote_stdout_pit_safe_v2v3_account_collector")
        elif "remote_stdout_collector.v1" in command:
            self.labels_seen.append("remote_stdout_market_and_fingerprint_collector")
        elif "p10i_remote_single_cycle_live_delta_canary_submitter" in command:
            self.labels_seen.append("remote_single_cycle_live_delta_canary_order_submitter")
        elif "systemctl" in command or "remote_live_config_sha256" in command:
            label = "pre_control_snapshot" if "pre_control_snapshot" not in self.labels_seen else "post_control_snapshot"
            self.labels_seen.append(label)
        else:
            self.labels_seen.append("unknown")
        if not self.payloads:
            raise AssertionError(f"unexpected command: {command[:300]}")
        return CommandResult(args=list(args), returncode=0, stdout=json.dumps(self.payloads.pop(0)), stderr="")


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


def _account_collector(*, position_amt: str = "0") -> dict[str, object]:
    endpoint_results = {
        "account_v2": _endpoint(
            "/fapi/v2/account",
            {
                "canTrade": True,
                "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
                "positions": [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": position_amt}],
            },
        ),
        "account_v3": _endpoint(
            "/fapi/v3/account",
            {
                "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
                "positions": [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": position_amt}],
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
        "side_effects": _zero_side_effects(),
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
        "side_effects": _zero_side_effects(),
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
        "side_effects": _zero_side_effects(),
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


def _order_submission(*, side: str) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_12factor_p10i_remote_single_cycle_live_delta_canary_submitter.v1",
        "status": "ready",
        "blockers": [],
        "client_order_id": "p10i-test",
        "canary_order_plan": {"side": side, "price": "10000.1", "quantity": "0.007", "notional_usdt": "70.0007"},
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
            "continuous_automation_enabled": False,
        },
    }


def _zero_side_effects() -> dict[str, object]:
    return {
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
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
