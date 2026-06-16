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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    CommandResult,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cd_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CD_CONTRACT,
    P9CE_GATE,
    P9CE_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    APPROVE_P9CE_DECISION,
    CONTRACT_VERSION as P9CE_CONTRACT,
    P9CF_GATE,
    build_phase9ce,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    EXPECTED_FORBIDDEN_ACTIONS,
    EXPECTED_PROOFS,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)


class Phase9CEReadOnlyFreshRemoteProofCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ce-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_collects_stdout_only_proofs_without_order_or_path_mutation(self) -> None:
        paths = self._write_ready_inputs()
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(_collector_payload()),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ce(
            self._args(paths, output_root=self.temp_dir / "p9ce"),
            now_fn=lambda: datetime(2026, 6, 10, 19, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CE_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9ce_read_only_fresh_remote_proof_collection_ready"])
        self.assertTrue(summary["fresh_remote_proof_collection_performed_in_p9ce"])
        self.assertTrue(summary["target_runner_identity_proven_in_p9ce"])
        self.assertTrue(summary["fresh_remote_account_read_performed"])
        self.assertTrue(summary["fresh_order_book_read_performed"])
        self.assertTrue(summary["exchange_filter_read_performed"])
        self.assertTrue(summary["position_fingerprint_stable"])
        self.assertTrue(summary["open_order_fingerprint_stable"])
        self.assertTrue(summary["balance_fingerprint_stable"])
        self.assertTrue(summary["fill_trade_fingerprint_stable"])
        self.assertTrue(summary["order_cancel_fill_trade_delta_zero"])
        self.assertTrue(summary["remote_control_boundary_unchanged"])
        self.assertEqual(summary["remote_files_written"], 0)
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["account_can_trade_pre"])
        self.assertFalse(summary["account_can_trade_post"])
        self.assertEqual(
            summary["future_live_order_readiness_blockers"],
            ["account_can_trade_false_or_missing"],
        )
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CF_GATE)

        outputs = summary["output_files"]
        manifest = _load_json(Path(outputs["proof_artifact_manifest"]))
        delta = _load_json(Path(outputs["proof_collection_delta_acceptance"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        matrix = _load_json(Path(outputs["non_authorization"]))

        self.assertTrue(manifest["self"]["exists"])
        self.assertIn("fresh_remote_account_read", manifest["artifacts"])
        self.assertTrue(delta["order_cancel_fill_trade_delta_zero"])
        self.assertTrue(delta["position_delta_zero_or_stable"])
        self.assertTrue(delta["balance_delta_zero_or_stable"])
        self.assertEqual(control["remote_files_written"], 0)
        self.assertFalse(control["remote_sync_performed"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["candidate_execution_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertFalse(control["executor_input_changed"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])

        labels = [record["label"] for record in _load_json(Path(outputs["command_records"]))["commands"]]
        self.assertEqual(
            labels,
            [
                "pre_control_snapshot",
                "remote_stdout_read_only_collector",
                "post_control_snapshot",
            ],
        )
        command_text = "\n".join(" ".join(record["args"]) for record in _load_json(Path(outputs["command_records"]))["commands"])
        self.assertNotIn("scp ", command_text)
        self.assertNotIn("mkdir -p", command_text)
        self.assertNotIn("systemctl start", command_text)
        self.assertNotIn("systemctl enable", command_text)

    def test_blocks_when_p9cd_does_not_allow_p9ce(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9CF_skip_p9ce_review"},
        )
        runner = SequentialRunner([])

        summary, exit_code = build_phase9ce(
            self._args(paths, output_root=self.temp_dir / "blocked"),
            now_fn=lambda: datetime(2026, 6, 10, 19, 5, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cd_summary_ready_for_p9ce", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9ce"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(runner.calls, [])

    def test_blocks_when_remote_collector_reports_endpoint_or_open_order_problem(self) -> None:
        paths = self._write_ready_inputs()
        bad_collector = _collector_payload(
            collector_overrides={
                "status": "blocked",
                "blockers": ["read_only_endpoint_failed:account:418"],
            },
            account_pre_overrides={"open_order_count": 1},
            account_post_overrides={"open_order_count": 1},
        )
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(bad_collector),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ce(
            self._args(paths, output_root=self.temp_dir / "remote-blocked"),
            now_fn=lambda: datetime(2026, 6, 10, 19, 10, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("remote_stdout_collector_not_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_account_read_ready"] if "fresh_remote_account_read_ready" in summary else False)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_pre_post_fingerprint_changes(self) -> None:
        paths = self._write_ready_inputs()
        changed = _collector_payload(
            collector_overrides={
                "status": "blocked",
                "blockers": ["position_fingerprint_changed"],
            },
            stability_overrides={"position_fingerprint_stable": False},
            post_position_overrides={"stable_hash": "changed-position"},
        )
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(changed),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9ce(
            self._args(paths, output_root=self.temp_dir / "fingerprint-change"),
            now_fn=lambda: datetime(2026, 6, 10, 19, 15, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("remote_stdout_collector_not_ready", summary["blockers"])
        self.assertIn("position_delta_not_zero_or_unstable", summary["blockers"])
        self.assertFalse(summary["position_fingerprint_stable"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CE_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cd_summary=str(paths["p9cd_summary"]),
            remote_host=DEFAULT_REMOTE_HOST,
            remote_repo=DEFAULT_REMOTE_REPO,
            remote_config=DEFAULT_REMOTE_CONFIG,
            remote_live_env=DEFAULT_REMOTE_LIVE_ENV,
            remote_python=DEFAULT_REMOTE_PYTHON,
            expected_egress_ip=DEFAULT_EXPECTED_EGRESS_IP,
            canary_symbol="BTCUSDT",
            max_history_symbols=20,
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        terms_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cd_root = self.temp_dir / "p9cd"
        proof_root = p9cd_root / "proof_artifacts" / "p9cd"
        p9cd_summary = p9cd_root / "summary.json"
        terms_path = proof_root / "read_only_collection_gate_terms.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        summary = _p9cd_summary_payload(terms_path, matrix_path, control_path)
        summary.update(summary_overrides or {})
        terms = _p9cd_terms_payload()
        terms.update(terms_overrides or {})
        _write_json(terms_path, terms)
        _write_json(matrix_path, _p9cd_matrix_payload())
        _write_json(control_path, _p9cd_control_payload())
        _write_json(p9cd_summary, summary)
        return {"project_profile": project_profile, "p9cd_summary": p9cd_summary}


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


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _p9cd_summary_payload(
    terms_path: Path,
    matrix_path: Path,
    control_path: Path,
) -> dict[str, object]:
    return {
        "contract_version": P9CD_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready": True,
        "p9cc_sufficient_for_p9cd_owner_gate": True,
        "read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd": True,
        "eligible_for_future_p9ce_read_only_collection_execution_gate": True,
        "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cd": False,
        "fresh_remote_proof_collection_performed_in_p9cd": False,
        "fresh_proofs_collected_in_p9cd": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cd": False,
        "target_deploy_root_proven_in_p9cd": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "allowed_next_gate": P9CE_GATE,
        "allowed_next_gate_scope": P9CE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "canary_symbol": "BTCUSDT",
        "canary_side": "BUY",
        "risk_ceiling_usdt": 25.0,
        "max_notional_usdt": 10.0,
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "market_orders_allowed": False,
        "required_fresh_proof_count": 12,
        "only_distance_to_high_60_contribution_changed": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "baseline_target_plan_sha256": BASELINE_SHA,
        "candidate_target_plan_sha256": CANDIDATE_SHA,
        "output_files": {
            "read_only_collection_gate_terms": str(terms_path),
            "non_authorization": str(matrix_path),
            "control_boundary_readback": str(control_path),
        },
    }


def _p9cd_terms_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_collection_gate_terms.v1",
        "owner_gate_only": True,
        "allowed_next_gate": P9CE_GATE,
        "allowed_next_gate_scope": P9CE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "read_only_fresh_remote_proof_collection_may_be_requested_next": True,
        "read_only_collection_execution_performed_in_p9cd": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cd": False,
        "target_deploy_root_proven_in_p9cd": False,
        "required_proofs": [
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": max_age,
                "point_in_time_safe_required": True,
                "collection_status_in_p9cd": "not_collected",
                "future_collection_status": "pending_separate_p9ce_request",
                "future_collection_channel": "remote_read_only",
            }
            for proof_id, max_age in EXPECTED_PROOFS.items()
        ],
        "forbidden_future_actions_during_proof_collection": sorted(EXPECTED_FORBIDDEN_ACTIONS),
        "delta_acceptance": {
            "order_delta_must_equal": 0,
            "cancel_delta_must_equal": 0,
            "fill_delta_must_equal": 0,
            "trade_delta_must_equal": 0,
            "position_delta_must_equal": 0,
            "balance_delta_must_equal": 0,
        },
        "staleness_policy": {
            "missing_proof_fails_closed": True,
            "stale_proof_fails_closed": True,
            "future_timestamp_fails_closed": True,
            "future_fill_or_stale_fill_evidence_must_fail_closed": True,
        },
        "hash_binding_required": {
            "candidate_target_plan_hash": True,
            "baseline_target_plan_hash": True,
            "baseline_candidate_distance_to_high_60_only_diff": True,
            "proof_artifact_manifest_hash": True,
        },
        "only_distance_to_high_60_contribution_changed": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _p9cd_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_non_authorization.v1",
        "authorizations": {
            "allow_future_p9ce_read_only_collection_gate_request": True,
            "execute_read_only_fresh_remote_proof_collection_in_p9cd": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }


def _p9cd_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_control_boundary.v1",
        "scope": "read_only_fresh_remote_proof_collection_owner_gate_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
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
        "operator_state": {"paused": {"value": "false", "updated_at_utc": "2026-06-10T18:00:00Z"}},
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
    collector_overrides: dict[str, object] | None = None,
    account_pre_overrides: dict[str, object] | None = None,
    account_post_overrides: dict[str, object] | None = None,
    stability_overrides: dict[str, object] | None = None,
    post_position_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    side_effects = {
        "orders_submitted": 0,
        "orders_canceled": 0,
        "order_test_calls": 0,
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
    account_pre = {
        "started_at_utc": "2026-06-10T19:00:01Z",
        "finished_at_utc": "2026-06-10T19:00:02Z",
        "account_readable": True,
        "can_trade": False,
        "position_mode": "one_way",
        "open_order_count": 0,
        "open_position_count": 1,
        "egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "expected_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "endpoint_results": {},
        "future_live_order_readiness_blockers": [
            "account_can_trade_false_or_missing"
        ],
    }
    account_post = dict(account_pre)
    account_post["started_at_utc"] = "2026-06-10T19:00:06Z"
    account_post["finished_at_utc"] = "2026-06-10T19:00:07Z"
    account_pre.update(account_pre_overrides or {})
    account_post.update(account_post_overrides or {})
    position = {
        "stable_fields": ["symbol", "positionSide", "positionAmt"],
        "stable_rows": [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0.01"}],
        "stable_hash": "position-hash",
    }
    post_position = dict(position)
    post_position.update(post_position_overrides or {})
    open_orders = {
        "stable_fields": ["symbol", "orderId", "status"],
        "stable_rows": [],
        "stable_hash": "open-orders-empty",
    }
    balance = {
        "stable_fields": ["asset", "walletBalance", "crossWalletBalance"],
        "stable_rows": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
        "stable_hash": "balance-hash",
    }
    fill_trade = {
        "order_history_fingerprint": {
            "stable_fields": ["symbol", "orderId", "status"],
            "history": {"BTCUSDT": []},
            "history_hash": "order-history-hash",
        },
        "trade_history_fingerprint": {
            "stable_fields": ["symbol", "id", "orderId"],
            "history": {"BTCUSDT": []},
            "history_hash": "trade-history-hash",
        },
        "endpoint_results": [],
    }
    stability = {
        "position_fingerprint_stable": True,
        "open_order_fingerprint_stable": True,
        "balance_fingerprint_stable": True,
        "fill_trade_fingerprint_stable": True,
    }
    stability.update(stability_overrides or {})
    payload = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_remote_stdout_collector.v1",
        "status": "ready",
        "blockers": [],
        "started_at_utc": "2026-06-10T19:00:00Z",
        "finished_at_utc": "2026-06-10T19:00:08Z",
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
        "fresh_remote_account_read": {
            "status": "ready",
            "pre": account_pre,
            "post": account_post,
            "side_effects": side_effects,
        },
        "pre_position_fingerprint": position,
        "post_position_fingerprint": post_position,
        "pre_open_order_fingerprint": open_orders,
        "post_open_order_fingerprint": open_orders,
        "pre_balance_fingerprint": balance,
        "post_balance_fingerprint": balance,
        "pre_fill_trade_fingerprint": fill_trade,
        "post_fill_trade_fingerprint": fill_trade,
        "fresh_order_book": {
            "status": "ready",
            "symbol": "BTCUSDT",
            "book_hash": "book-hash",
            "endpoint": "/fapi/v1/depth",
            "method": "GET",
        },
        "exchange_filter_readback": {
            "status": "ready",
            "filters_hash": "filters-hash",
            "symbol_count": 1,
            "endpoint": "/fapi/v1/exchangeInfo",
            "method": "GET",
        },
        "operator_control_readback": {"operator_state": {}, "systemd_units": {}},
        "fingerprint_stability": stability,
        "side_effects": side_effects,
    }
    payload.update(collector_overrides or {})
    return payload


def _command_json(payload: dict[str, object], *, returncode: int = 0) -> CommandResult:
    return CommandResult(args=[], returncode=returncode, stdout=json.dumps(payload), stderr="")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
