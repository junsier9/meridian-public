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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9db_review_p9da_blocked_no_order_evidence import (
    APPROVE_P9DB_DECISION,
    build_phase9db,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dc_define_approve_0_001_btcusdt_round_trip_canary_terms import (
    APPROVE_P9DC_DECISION,
    P9DD_GATE,
    build_phase9dc,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dd_execute_0_001_btcusdt_round_trip_canary import (
    APPROVE_P9DD_DECISION,
    build_phase9dd,
)


class Phase9DBDCDDCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9dbdcdd-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9db_and_p9dc_ready_from_blocked_no_order_p9da_fixture(self) -> None:
        paths = self._write_p9da_blocked_fixture()

        p9db, p9db_exit = build_phase9db(
            self._p9db_args(paths, output_root=self.temp_dir / "p9db"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(p9db_exit, 0)
        self.assertEqual(p9db["status"], "ready")
        self.assertTrue(p9db["p9da_proved_order_submitter_not_invoked"])
        self.assertEqual(p9db["orders_submitted"], 0)

        p9dc, p9dc_exit = build_phase9dc(
            self._p9dc_args(paths, p9db, output_root=self.temp_dir / "p9dc"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 5, 0, tzinfo=UTC),
        )
        self.assertEqual(p9dc_exit, 0)
        self.assertEqual(p9dc["status"], "ready")
        self.assertEqual(p9dc["allowed_next_gate"], P9DD_GATE)
        self.assertEqual(p9dc["max_notional_per_leg_usdt"], 75.0)
        self.assertEqual(p9dc["orders_submitted"], 0)

    def test_p9dd_ready_accepts_exact_fake_round_trip_and_baseline_boundary(self) -> None:
        paths = self._write_p9da_blocked_fixture()
        p9db, p9db_exit = build_phase9db(
            self._p9db_args(paths, output_root=self.temp_dir / "p9db"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 10, 0, tzinfo=UTC),
        )
        self.assertEqual(p9db_exit, 0)
        p9dc, p9dc_exit = build_phase9dc(
            self._p9dc_args(paths, p9db, output_root=self.temp_dir / "p9dc"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 15, 0, tzinfo=UTC),
        )
        self.assertEqual(p9dc_exit, 0)
        runner = SequenceCommandRunner([_snapshot(), _round_trip_submission(), _snapshot()])

        summary, exit_code = build_phase9dd(
            self._p9dd_args(paths, p9dc, output_root=self.temp_dir / "p9dd"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 20, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["orders_submitted"], 2)
        self.assertEqual(summary["fill_count"], 2)
        self.assertTrue(summary["post_position_equals_pre"])
        self.assertTrue(summary["remote_control_boundary_unchanged"])
        self.assertEqual(
            runner.labels_seen,
            ["pre_control_snapshot", "remote_round_trip_canary_order_submitter", "post_control_snapshot"],
        )

    def test_p9dd_blocks_before_remote_commands_when_p9dc_terms_are_bad(self) -> None:
        paths = self._write_p9da_blocked_fixture()
        p9db, _ = build_phase9db(
            self._p9db_args(paths, output_root=self.temp_dir / "p9db"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 25, 0, tzinfo=UTC),
        )
        p9dc, _ = build_phase9dc(
            self._p9dc_args(paths, p9db, output_root=self.temp_dir / "p9dc"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 30, 0, tzinfo=UTC),
        )
        terms_path = Path(p9dc["output_files"]["approved_round_trip_terms"])
        terms = _load_json(terms_path)
        terms["market_orders_allowed"] = True
        _write_json(terms_path, terms)
        runner = SequenceCommandRunner([])

        summary, exit_code = build_phase9dd(
            self._p9dd_args(paths, p9dc, output_root=self.temp_dir / "bad-p9dd"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 35, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9dc_terms_ready_for_p9dd", summary["blockers"])
        self.assertEqual(runner.labels_seen, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def _p9db_args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9da_summary=str(paths["p9da_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DB_DECISION,
            owner_decision_source="unit_test",
        )

    def _p9dc_args(self, paths: dict[str, Path], p9db: dict[str, object], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9db_summary=str(p9db["output_files"]["summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DC_DECISION,
            owner_decision_source="unit_test",
        )

    def _p9dd_args(self, paths: dict[str, Path], p9dc: dict[str, object], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9dc_summary=str(p9dc["output_files"]["summary"]),
            remote_host="root@203.0.113.10",
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            expected_egress_ip="203.0.113.10",
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DD_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_p9da_blocked_fixture(self) -> dict[str, Path]:
        root = self.temp_dir / "p9da"
        proof = root / "proof_artifacts" / "p9da" / "run"
        project_profile = self.temp_dir / "project_profile.json"
        p9da_summary = root / "summary.json"
        plan = proof / "canary_order_plan.json"
        command_records = root / "command_records.json"
        submission = proof / "remote_single_post_only_canary_order_submission.json"
        control = proof / "control_boundary_readback.json"
        account = proof / "pit_safe_v2v3_account_proof.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            plan,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9da_canary_order_plan.v1",
                "status": "blocked",
                "blockers": [
                    "canary_minimum_notional_exceeds_authorized_max:required=62.978:max=10",
                    "computed_notional_below_min_notional:0<50",
                    "computed_quantity_below_min_qty:0<0.001",
                ],
                "symbol": "BTCUSDT",
                "side": "BUY",
                "minimum_executable_notional_usdt": "62.978",
                "max_notional_usdt": "10",
                "min_qty": "0.001",
                "min_notional": "50",
                "quantity": "0",
                "notional_usdt": "0",
            },
        )
        _write_json(
            command_records,
            {
                "commands": [
                    {"label": "pre_control_snapshot"},
                    {"label": "remote_stdout_pit_safe_v2v3_account_collector"},
                    {"label": "remote_stdout_market_and_fingerprint_collector"},
                    {"label": "post_control_snapshot"},
                ]
            },
        )
        _write_json(submission, {})
        _write_json(
            control,
            {
                "live_order_submission_performed": False,
                "timer_path_loaded": False,
                "ran_supervisor": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
            },
        )
        _write_json(
            account,
            {
                "can_trade_source": "/fapi/v2/account.canTrade",
                "can_trade_pre": True,
                "can_trade_post": True,
            },
        )
        _write_json(
            p9da_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9da_single_post_only_canary_live_order.v1",
                "status": "blocked",
                "blockers": [
                    "canary_minimum_notional_exceeds_authorized_max:required=62.978:max=10",
                    "canary_order_plan_not_ready",
                    "computed_notional_below_min_notional:0<50",
                    "computed_quantity_below_min_qty:0<0.001",
                ],
                "p9da_single_post_only_canary_live_order_ready": False,
                "p9cz_sufficient_for_p9da_execution": True,
                "fresh_pre_submit_readback_performed": True,
                "fresh_remote_account_read_performed": True,
                "fresh_order_book_read_performed": True,
                "exchange_filter_read_performed": True,
                "pit_safe_v2v3_account_proof_ready": True,
                "can_trade_decision_source": "/fapi/v2/account.canTrade",
                "can_trade_pre": True,
                "can_trade_post": True,
                "canary_order_plan_ready": False,
                "remote_control_boundary_unchanged": True,
                "live_order_submission_authorized": True,
                "live_order_submission_performed": False,
                "actual_live_order_submission_performed": False,
                "actual_candidate_execution_performed": False,
                "actual_candidate_executor_target_path_entry_performed": False,
                "actual_executor_input_mutation_performed": False,
                "actual_target_plan_replacement_performed": False,
                "order_test_endpoint_called": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
                "canary_minimum_executable_notional_usdt": "62.978",
                "max_notional_usdt": 10.0,
                "allowed_next_gate": "P9DB_review_p9da_single_post_only_canary_live_order_only_if_separately_requested",
                "allowed_next_gate_scope": "review_p9da_single_post_only_canary_retained_evidence_before_any_next_live_order_or_broader_candidate_execution",
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "canary_order_plan": str(plan),
                    "command_records": str(command_records),
                    "remote_single_post_only_canary_order_submission": str(submission),
                    "control_boundary_readback": str(control),
                    "pit_safe_v2v3_account_proof": str(account),
                },
            },
        )
        return {"project_profile": project_profile, "p9da_summary": p9da_summary}


class SequenceCommandRunner:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.labels_seen: list[str] = []

    def __call__(self, args: list[str]) -> CommandResult:
        command = " ".join(str(item) for item in args)
        if "remote_round_trip_canary_submitter" in command or "P9DD-round-trip-canary" in command:
            self.labels_seen.append("remote_round_trip_canary_order_submitter")
        elif "systemctl" in command or "remote_live_config_sha256" in command:
            label = "pre_control_snapshot" if "pre_control_snapshot" not in self.labels_seen else "post_control_snapshot"
            self.labels_seen.append(label)
        else:
            self.labels_seen.append("unknown")
        if not self.payloads:
            raise AssertionError(f"unexpected command: {command[:200]}")
        return CommandResult(args=list(args), returncode=0, stdout=json.dumps(self.payloads.pop(0)), stderr="")


def _snapshot() -> dict[str, object]:
    return {
        "remote_live_config_sha256": "config-sha",
        "live_supervisor_sha256": "supervisor-sha",
        "operator_state": {"live_delta_armed": {"value": "true"}},
        "systemd_units": {
            "meridian-alpha-mainnet-supervisor-live.timer": {
                "LoadState": "loaded",
                "UnitFileState": "enabled",
                "ActiveState": "active",
                "SubState": "waiting",
                "FragmentPath": "/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.timer",
            }
        },
    }


def _round_trip_submission() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dd_remote_round_trip_canary_submitter.v1",
        "status": "ready",
        "blockers": [],
        "symbol": "BTCUSDT",
        "quantity_btc": "0.001",
        "max_notional_per_leg_usdt": "75",
        "max_gross_turnover_usdt": "150",
        "buy_executed_qty": "0.001",
        "sell_executed_qty": "0.001",
        "orders_submitted": 2,
        "orders_canceled": 0,
        "fill_count": 2,
        "trade_count": 2,
        "gross_turnover_usdt": "126",
        "pre_btcusdt_position_amt": "0.014",
        "post_btcusdt_position_amt": "0.014",
        "post_position_equals_pre": True,
        "pre_submit_readback": {
            "account_v2": {"status": "ok", "payload": {"canTrade": True}},
            "depth": {"status": "ok"},
            "exchange_info": {"status": "ok"},
        },
        "side_effects": {
            "http_methods_used": ["GET", "POST"],
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "supervisor_invoked": False,
            "timer_path_invoked": False,
            "candidate_executed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "order_test_endpoint_called": False,
        },
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
