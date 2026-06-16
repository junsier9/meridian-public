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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    CommandResult,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CF_CONTRACT,
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
    P9CG_GATE,
    P9CG_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cg_define_live_order_readiness_blocker_resolution_scope import (  # noqa: E402
    APPROVE_P9CG_DECISION,
    build_phase9cg,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ch_pit_safe_read_only_account_proof_owner_gate import (  # noqa: E402
    APPROVE_P9CH_DECISION,
    build_phase9ch,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    APPROVE_P9CI_DECISION,
    CONTRACT_VERSION as P9CI_CONTRACT,
    P9CJ_GATE,
    build_phase9ci,
)


class Phase9CIPitSafeReadOnlyAccountProofV2V3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ci-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_executes_v2v3_proof_and_ignores_v3_canTrade(self) -> None:
        paths = self._write_ready_p9ch_inputs()
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(
                    _collector_payload(can_trade_v2=True, can_trade_v3_marker=False)
                ),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ci(
            self._args(paths, output_root=self.temp_dir / "p9ci"),
            now_fn=lambda: datetime(2026, 6, 10, 23, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CI_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9ci_pit_safe_read_only_account_proof_v2v3_ready"])
        self.assertTrue(summary["pit_safe_v2v3_account_proof_executed"])
        self.assertTrue(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertEqual(summary["can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertTrue(summary["can_trade_pre"])
        self.assertTrue(summary["can_trade_post"])
        self.assertTrue(summary["account_v2_has_canTrade_pre"])
        self.assertTrue(summary["account_v3_has_canTrade_pre"])
        self.assertTrue(summary["account_v3_canTrade_ignored_for_permission_decision"])
        self.assertEqual(summary["live_order_readiness_blockers"], [])
        self.assertTrue(summary["eligible_to_clear_p9cf_account_can_trade_blocker"])
        self.assertEqual(
            summary["prior_p9ce_blocker_reclassification"],
            "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap",
        )
        self.assertTrue(summary["position_fingerprint_stable"])
        self.assertTrue(summary["open_order_fingerprint_stable"])
        self.assertTrue(summary["balance_fingerprint_stable"])
        self.assertTrue(summary["order_cancel_fill_trade_delta_zero"])
        self.assertTrue(summary["remote_control_boundary_unchanged"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CJ_GATE)
        self.assertIs(
            summary["gates"]["remote_stdout_pit_safe_v2v3_account_collector_ready"],
            True,
        )

        outputs = summary["output_files"]
        proof = _load_json(Path(outputs["pit_safe_account_proof"]))
        history_delta = _load_json(Path(outputs["history_delta_acceptance"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        commands = _load_json(Path(outputs["command_records"]))["commands"]

        self.assertEqual(proof["can_trade_source"], CAN_TRADE_SOURCE)
        self.assertTrue(proof["account_v3_canTrade_ignored_for_permission_decision"])
        self.assertTrue(history_delta["order_cancel_fill_trade_delta_zero"])
        self.assertFalse(control["fresh_order_book_read_performed"])
        self.assertFalse(control["order_test_endpoint_called"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertNotIn("stdout_tail", commands[1])
        self.assertIn("stdout_sha256", commands[1])
        command_text = "\n".join(" ".join(record["args"]) for record in commands)
        self.assertNotIn("scp ", command_text)
        self.assertNotIn("systemctl start", command_text)
        self.assertNotIn("systemctl enable", command_text)

    def test_canTrade_false_is_ready_but_retains_live_order_blocker(self) -> None:
        paths = self._write_ready_p9ch_inputs()
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(
                    _collector_payload(can_trade_v2=False, can_trade_v3_marker=True)
                ),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ci(
            self._args(paths, output_root=self.temp_dir / "p9ci-false"),
            now_fn=lambda: datetime(2026, 6, 10, 23, 5, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertFalse(summary["can_trade_pre"])
        self.assertFalse(summary["can_trade_post"])
        self.assertEqual(summary["live_order_readiness_blockers"], [BLOCKER_CAN_TRADE_FALSE])
        self.assertFalse(summary["eligible_to_clear_p9cf_account_can_trade_blocker"])
        self.assertEqual(
            summary["prior_p9ce_blocker_reclassification"],
            "account_side_permission_blocker",
        )
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9ch_does_not_allow_p9ci_without_running_remote(self) -> None:
        paths = self._write_ready_p9ch_inputs()
        p9ch = _load_json(paths["p9ch_summary"])
        p9ch["allowed_next_gate"] = "P9CJ_skip_p9ci_review"
        _write_json(paths["p9ch_summary"], p9ch)
        runner = SequentialRunner([])

        summary, exit_code = build_phase9ci(
            self._args(paths, output_root=self.temp_dir / "blocked-p9ch"),
            now_fn=lambda: datetime(2026, 6, 10, 23, 10, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ch_summary_ready_for_p9ci", summary["blockers"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(runner.calls, [])

    def test_blocks_when_endpoint_or_history_delta_fails(self) -> None:
        paths = self._write_ready_p9ch_inputs()
        bad_collector = _collector_payload(
            can_trade_v2=True,
            can_trade_v3_marker=None,
            collector_overrides={
                "status": "blocked",
                "blockers": ["read_only_endpoint_failed:account_v2:401"],
            },
            history_delta_overrides={"trade_history_fingerprint_stable": False},
        )
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(bad_collector),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ci(
            self._args(paths, output_root=self.temp_dir / "bad-remote"),
            now_fn=lambda: datetime(2026, 6, 10, 23, 15, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "remote_stdout_pit_safe_v2v3_account_collector_not_ready",
            summary["blockers"],
        )
        self.assertIn("order_cancel_fill_trade_delta_not_zero_or_unproven", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CI_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ch_summary=str(paths["p9ch_summary"]),
            remote_host=DEFAULT_REMOTE_HOST,
            remote_repo=DEFAULT_REMOTE_REPO,
            remote_config=DEFAULT_REMOTE_CONFIG,
            remote_live_env=DEFAULT_REMOTE_LIVE_ENV,
            remote_python=DEFAULT_REMOTE_PYTHON,
            expected_egress_ip=DEFAULT_EXPECTED_EGRESS_IP,
            history_canary_symbol="BTCUSDT",
            max_history_symbols=20,
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ch_inputs(self) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cf_summary = self.temp_dir / "p9cf" / "summary.json"
        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "project": "Meridian Alpha Platform",
            },
        )
        _write_json(p9cf_summary, _p9cf_summary_payload())
        p9cg_summary, p9cg_exit = build_phase9cg(
            Namespace(
                output_root=str(self.temp_dir / "p9cg"),
                project_profile=str(project_profile),
                phase9cf_summary=str(p9cf_summary),
                account_proof_builder=str(
                    ROOT
                    / "scripts/live_trading/hv_balanced_binance_usdm_pit_safe_account_proof_builder.py"
                ),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CG_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 22, 45, tzinfo=UTC),
        )
        self.assertEqual(p9cg_exit, 0)
        p9ch_summary, p9ch_exit = build_phase9ch(
            Namespace(
                output_root=str(self.temp_dir / "p9ch"),
                project_profile=str(project_profile),
                phase9cg_summary=str(p9cg_summary["output_files"]["summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CH_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 22, 50, tzinfo=UTC),
        )
        self.assertEqual(p9ch_exit, 0)
        return {
            "project_profile": project_profile,
            "p9ch_summary": Path(p9ch_summary["output_files"]["summary"]),
        }


class SequentialRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, args: object) -> CommandResult:
        call = [str(item) for item in args]  # type: ignore[iteration-over-annotation]
        self.calls.append(call)
        if not self.results:
            return CommandResult(args=call, returncode=1, stdout="", stderr="unexpected call")
        result = self.results.pop(0)
        return CommandResult(args=call, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _p9cf_summary_payload() -> dict[str, object]:
    return {
        "contract_version": P9CF_CONTRACT,
        "run_id": "20260610T224000Z",
        "status": "ready",
        "blockers": [],
        "p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready": True,
        "p9ce_sufficient_for_read_only_collection_review": True,
        "p9ce_sufficient_for_live_order_gate": False,
        "live_order_readiness_blockers": [LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE],
        "eligible_for_future_p9cg_live_order_readiness_blocker_scope_gate": True,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "fresh_remote_proof_collection_performed_in_p9cf": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_execution_authorized": False,
        "allowed_next_gate": P9CG_GATE,
        "allowed_next_gate_scope": P9CG_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _snapshot_payload() -> dict[str, object]:
    return {
        "remote_repo": DEFAULT_REMOTE_REPO,
        "remote_config": DEFAULT_REMOTE_CONFIG,
        "remote_live_config_sha256": "config-sha",
        "live_supervisor_sha256": "supervisor-sha",
        "hook_sha256": "hook-sha",
        "operator_state": {
            "paused": {"value": "false", "updated_at_utc": "2026-06-10T23:00:00Z"}
        },
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


def _collector_payload(
    *,
    can_trade_v2: bool | _Missing,
    can_trade_v3_marker: bool | None,
    collector_overrides: dict[str, object] | None = None,
    history_delta_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    side_effects = {
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
    history_delta = {
        "order_history_fingerprint_stable": True,
        "trade_history_fingerprint_stable": True,
        "order_history_hash_pre": "order-history-hash",
        "order_history_hash_post": "order-history-hash",
        "trade_history_hash_pre": "trade-history-hash",
        "trade_history_hash_post": "trade-history-hash",
    }
    history_delta.update(history_delta_overrides or {})
    payload = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1",
        "status": "ready",
        "blockers": [],
        "started_at_utc": "2026-06-10T23:00:01Z",
        "finished_at_utc": "2026-06-10T23:00:08Z",
        "remote_runner_identity_readback": {
            "whoami": "root",
            "hostname": "meridian-runner",
            "cwd": DEFAULT_REMOTE_REPO,
            "repo_path": DEFAULT_REMOTE_REPO,
            "config_path": DEFAULT_REMOTE_CONFIG,
            "python_executable": DEFAULT_REMOTE_PYTHON,
            "egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "config_sha256": "config-sha",
            "live_supervisor_sha256": "supervisor-sha",
            "hook_sha256": "hook-sha",
        },
        "pre_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "post_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "pre_endpoint_results": _endpoint_results(can_trade_v2, can_trade_v3_marker),
        "post_endpoint_results": _endpoint_results(can_trade_v2, can_trade_v3_marker),
        "proof_symbols": ["BTCUSDT"],
        "pre_history_fingerprint": _history_payload(),
        "post_history_fingerprint": _history_payload(),
        "history_delta": history_delta,
        "operator_control_readback": {"operator_state": {}, "systemd_units": {}},
        "side_effects": side_effects,
    }
    payload.update(collector_overrides or {})
    return payload


class _Missing:
    pass


_MISSING = _Missing()


def _endpoint_results(
    can_trade_v2: bool | _Missing,
    can_trade_v3_marker: bool | None,
) -> dict[str, object]:
    account_v2 = {
        "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
        "positions": [_position()],
    }
    if not isinstance(can_trade_v2, _Missing):
        account_v2["canTrade"] = can_trade_v2
    account_v3 = {
        "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
        "positions": [_position()],
    }
    if can_trade_v3_marker is not None:
        account_v3["canTrade"] = can_trade_v3_marker
    return {
        "account_v2": _endpoint(ACCOUNT_V2_ENDPOINT, account_v2),
        "account_v3": _endpoint(ACCOUNT_V3_ENDPOINT, account_v3),
        "account_config": _endpoint(
            ACCOUNT_CONFIG_ENDPOINT,
            {"feeTier": 0, "multiAssetsMargin": False, "tradeGroupId": -1},
        ),
        "position_mode": _endpoint(POSITION_MODE_ENDPOINT, {"dualSidePosition": False}),
        "open_orders": _endpoint(OPEN_ORDERS_ENDPOINT, []),
        "api_restrictions": _endpoint(
            API_RESTRICTIONS_ENDPOINT,
            {
                "ipRestrict": True,
                "enableFutures": True,
                "enableReading": True,
                "enableWithdrawals": False,
                "permitsUniversalTransfer": True,
            },
        ),
    }


def _endpoint(path: str, payload: object) -> dict[str, object]:
    return {
        "path": path,
        "method": "GET",
        "status": "ok",
        "status_code": 200,
        "started_at_utc": "2026-06-10T23:00:01Z",
        "finished_at_utc": "2026-06-10T23:00:02Z",
        "payload": payload,
    }


def _position() -> dict[str, str]:
    return {
        "symbol": "BTCUSDT",
        "positionSide": "BOTH",
        "positionAmt": "0.01",
        "entryPrice": "60000",
        "breakEvenPrice": "60000",
        "isolated": "false",
        "isolatedWallet": "0",
    }


def _history_payload() -> dict[str, object]:
    return {
        "status": "ready",
        "blockers": [],
        "proof_symbols": ["BTCUSDT"],
        "order_history_fingerprint": {"history_hash": "order-history-hash"},
        "trade_history_fingerprint": {"history_hash": "trade-history-hash"},
        "endpoint_results": [],
    }


def _command_json(payload: dict[str, object], *, returncode: int = 0) -> CommandResult:
    return CommandResult(args=[], returncode=returncode, stdout=json.dumps(payload), stderr="")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
