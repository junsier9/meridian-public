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
    ACCOUNT_PROOF_CONTRACT_VERSION,
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
    DEFAULT_REMOTE_REPO,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    CONTRACT_VERSION as P9CI_CONTRACT,
    P9CJ_GATE,
    P9CJ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    APPROVE_P9CJ_DECISION,
    CONTRACT_VERSION as P9CJ_CONTRACT,
    P9CK_GATE,
    build_phase9cj,
)


class Phase9CJReviewP9CIPitSafeAccountProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cj-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_clears_account_blocker_without_live_order_authority(self) -> None:
        paths = self._write_ready_p9ci_inputs()

        summary, exit_code = build_phase9cj(
            self._args(paths, output_root=self.temp_dir / "p9cj"),
            now_fn=lambda: datetime(2026, 6, 11, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CJ_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary["p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready"]
        )
        self.assertTrue(summary["p9ci_sufficient_to_clear_account_can_trade_blocker"])
        self.assertTrue(summary["account_can_trade_blocker_cleared_by_p9cj_review"])
        self.assertTrue(summary["p9ce_false_or_missing_reclassified_as_endpoint_schema_gap"])
        self.assertEqual(summary["live_order_readiness_blockers_after_account_review"], [])
        self.assertEqual(summary["remaining_account_permission_blockers"], [])
        self.assertEqual(summary["source_p9ci_can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertTrue(summary["source_p9ci_can_trade_pre"])
        self.assertTrue(summary["source_p9ci_can_trade_post"])
        self.assertTrue(summary["source_p9ci_account_v2_has_canTrade_pre"])
        self.assertTrue(summary["source_p9ci_account_v2_has_canTrade_post"])
        self.assertFalse(summary["fresh_remote_account_read_performed_in_p9cj"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["retained_p9ci_payload_key_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CK_GATE)

        clearance = _load_json(Path(summary["output_files"]["account_blocker_clearance_decision"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization"]))
        review = _load_json(Path(summary["output_files"]["p9ci_sufficiency_review"]))

        self.assertTrue(clearance["account_can_trade_blocker_cleared_by_p9cj_review"])
        self.assertFalse(clearance["approves_live_order_submission"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertTrue(review["p9ci_sufficient_to_clear_account_can_trade_blocker"])

    def test_blocks_when_p9ci_canTrade_false(self) -> None:
        paths = self._write_ready_p9ci_inputs(can_trade=False)

        summary, exit_code = build_phase9cj(
            self._args(paths, output_root=self.temp_dir / "p9cj-blocked-cantrade"),
            now_fn=lambda: datetime(2026, 6, 11, 0, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ci_summary_ready_for_account_blocker_review", summary["blockers"])
        self.assertIn("p9ci_pit_safe_account_proof_ready", summary["blockers"])
        self.assertFalse(summary["account_can_trade_blocker_cleared_by_p9cj_review"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_retained_p9ci_artifact_contains_payload_key(self) -> None:
        paths = self._write_ready_p9ci_inputs()
        collector_path = paths["collector"]
        collector = _load_json(collector_path)
        collector["payload"] = {"raw": "must-not-be-retained"}
        _write_json(collector_path, collector)

        summary, exit_code = build_phase9cj(
            self._args(paths, output_root=self.temp_dir / "p9cj-payload"),
            now_fn=lambda: datetime(2026, 6, 11, 0, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ci_remote_stdout_collector_sanitized_ready", summary["blockers"])
        self.assertIn("retained_p9ci_payload_keys_absent", summary["blockers"])
        self.assertGreater(summary["retained_p9ci_payload_key_count"], 0)
        self.assertFalse(summary["account_can_trade_blocker_cleared_by_p9cj_review"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_blocks_wrong_owner_decision_without_remote_execution(self) -> None:
        paths = self._write_ready_p9ci_inputs()

        summary, exit_code = build_phase9cj(
            self._args(
                paths,
                output_root=self.temp_dir / "p9cj-wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 11, 0, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cj_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["account_can_trade_blocker_cleared_by_p9cj_review"])
        self.assertFalse(summary["fresh_remote_account_read_performed_in_p9cj"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CJ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ci_summary=str(paths["p9ci_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ci_inputs(self, *, can_trade: bool = True) -> dict[str, Path]:
        root = self.temp_dir / ("p9ci-ready" if can_trade else "p9ci-cantrade-false")
        proof_root = root / "proof_artifacts" / "p9ci" / "20260610T235924Z"
        proof_root.mkdir(parents=True)

        project_profile = self.temp_dir / "project_profile.json"
        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "target_stage": "stage_4_automated_execution",
            },
        )

        endpoint_group = _endpoint_group()
        side_effects = _side_effects()
        live_blockers = [] if can_trade else [BLOCKER_CAN_TRADE_FALSE]
        reclassification = (
            "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap"
            if can_trade
            else "account_side_permission_blocker"
        )
        proof = {
            "contract_version": ACCOUNT_PROOF_CONTRACT_VERSION,
            "status": "ready",
            "blockers": [] if can_trade else [BLOCKER_CAN_TRADE_FALSE],
            "pit_safe_read_only_account_proof_ready": can_trade,
            "account_permission_source_corrected": True,
            "can_trade_source": CAN_TRADE_SOURCE,
            "can_trade_pre": can_trade,
            "can_trade_post": can_trade,
            "account_v2_has_canTrade_pre": True,
            "account_v2_has_canTrade_post": True,
            "account_v3_has_canTrade_pre": False,
            "account_v3_has_canTrade_post": False,
            "account_v3_canTrade_ignored_for_permission_decision": True,
            "live_order_readiness_blockers": live_blockers,
            "eligible_to_clear_p9cf_account_can_trade_blocker": can_trade,
            "prior_p9ce_blocker_reclassification": reclassification,
            "split_live_order_readiness_blockers": [
                BLOCKER_CAN_TRADE_MISSING,
                BLOCKER_CAN_TRADE_FALSE,
            ],
            "checks": {
                "pre_snapshot_ready": True,
                "post_snapshot_ready": True,
                "can_trade_source_is_v2_account": True,
                "account_v3_canTrade_ignored": True,
                "can_trade_state_stable": True,
                "position_fingerprint_stable": True,
                "open_order_fingerprint_stable": True,
                "balance_fingerprint_stable": True,
                "open_order_count_zero_pre_post": True,
                "side_effects_zero": True,
            },
            "pre": _account_snapshot(can_trade, endpoint_group),
            "post": _account_snapshot(can_trade, endpoint_group),
            "side_effects": side_effects,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        }
        account_delta = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ci_account_delta_acceptance.v1",
            "position_fingerprint_stable": True,
            "open_order_fingerprint_stable": True,
            "balance_fingerprint_stable": True,
            "open_order_count_zero_pre_post": True,
            "side_effects_zero": True,
            "open_position_count_pre": 11,
            "open_position_count_post": 11,
            "open_order_count_pre": 0,
            "open_order_count_post": 0,
            "position_delta_zero_or_stable": True,
            "open_order_delta_zero_or_stable": True,
            "balance_delta_zero_or_stable": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        }
        history_delta = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ci_history_delta_acceptance.v1",
            "proof_symbols": ["BTCUSDT", "ETHUSDT"],
            "order_history_fingerprint_stable": True,
            "trade_history_fingerprint_stable": True,
            "order_history_hash_pre": "order-hash",
            "order_history_hash_post": "order-hash",
            "trade_history_hash_pre": "trade-hash",
            "trade_history_hash_post": "trade-hash",
            "order_cancel_fill_trade_delta_zero": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        }
        collector = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1",
            "status": "ready",
            "blockers": [],
            "pre_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "post_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "pre_endpoint_results": endpoint_group,
            "post_endpoint_results": endpoint_group,
            "proof_symbols": ["BTCUSDT", "ETHUSDT"],
            "history_delta": {
                "order_history_fingerprint_stable": True,
                "trade_history_fingerprint_stable": True,
                "order_history_hash_pre": "order-hash",
                "order_history_hash_post": "order-hash",
                "trade_history_hash_pre": "trade-hash",
                "trade_history_hash_post": "trade-hash",
            },
            "side_effects": side_effects,
        }
        identity = {
            "whoami": "root",
            "repo_path": DEFAULT_REMOTE_REPO,
            "config_path": DEFAULT_REMOTE_CONFIG,
            "egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "config_sha256": "config-sha",
            "live_supervisor_sha256": "supervisor-sha",
        }
        non_auth = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ci_non_authorization.v1",
            "authorizations": {
                "p9ci_pit_safe_v2v3_read_only_account_proof": True,
                "remote_stdout_read_only_account_collection": True,
                "fresh_order_book_read": False,
                "exchange_filter_read": False,
                "order_test_endpoint": False,
                "remote_files_written": False,
                "remote_sync": False,
                "supervisor_invocation": False,
                "timer_path_load": False,
                "production_timer_service_load": False,
                "candidate_execution": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "stage_governance_change": False,
            },
        }
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ci_control_boundary.v1",
            "scope": "pit_safe_v2v3_read_only_account_proof_stdout_only",
            "ssh_invoked": True,
            "remote_network_connection_performed": True,
            "remote_execution_scope": "stdout_pit_safe_v2v3_read_only_account_collector_only",
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "fresh_remote_account_read_performed": True,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "order_test_endpoint_called": False,
            "entered_timer_path": False,
            "ran_supervisor": False,
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
        commands = {
            "commands": [
                _command("pre_control_snapshot"),
                _command("remote_stdout_pit_safe_v2v3_account_collector"),
                _command("post_control_snapshot"),
            ]
        }

        paths = {
            "project_profile": project_profile,
            "proof": proof_root / "pit_safe_account_proof.json",
            "account_delta": proof_root / "account_delta_acceptance.json",
            "history_delta": proof_root / "history_delta_acceptance.json",
            "collector": proof_root / "remote_stdout_collector_sanitized.json",
            "identity": proof_root / "remote_runner_identity_readback.json",
            "non_auth": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
            "manifest": proof_root / "proof_artifact_manifest.json",
            "commands": root / "command_records.json",
            "p9ci_summary": root / "summary.json",
        }
        for key, payload in [
            ("proof", proof),
            ("account_delta", account_delta),
            ("history_delta", history_delta),
            ("collector", collector),
            ("identity", identity),
            ("non_auth", non_auth),
            ("control", control),
        ]:
            _write_json(paths[key], payload)
        _write_json(paths["commands"], commands)
        _write_json(
            paths["manifest"],
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ci_proof_manifest.v1",
                "artifact_count": 7,
                "artifacts": {
                    "account_delta_acceptance": _evidence(paths["account_delta"]),
                    "control_boundary_readback": _evidence(paths["control"]),
                    "history_delta_acceptance": _evidence(paths["history_delta"]),
                    "non_authorization": _evidence(paths["non_auth"]),
                    "pit_safe_account_proof": _evidence(paths["proof"]),
                    "remote_runner_identity_readback": _evidence(paths["identity"]),
                    "remote_stdout_collector_sanitized": _evidence(paths["collector"]),
                },
                "self": {"exists": True, "path": str(paths["manifest"]), "sha256": "self-sha"},
            },
        )

        p9ci_summary = {
            "contract_version": P9CI_CONTRACT,
            "run_id": "20260610T235924Z",
            "generated_at_utc": "2026-06-10T23:59:24Z",
            "status": "ready",
            "blockers": [],
            "p9ci_pit_safe_read_only_account_proof_v2v3_ready": True,
            "p9ch_sufficient_for_p9ci_execution": True,
            "fresh_remote_account_read_performed": True,
            "pit_safe_v2v3_account_proof_executed": True,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "order_test_endpoint_called": False,
            "remote_execution_scope": "stdout_pit_safe_v2v3_read_only_account_collector_only",
            "remote_execution_performed": True,
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "target_runner_identity_proven_in_p9ci": True,
            "target_deploy_root_proven_in_p9ci": True,
            "remote_host": DEFAULT_REMOTE_HOST,
            "remote_repo": DEFAULT_REMOTE_REPO,
            "remote_config": DEFAULT_REMOTE_CONFIG,
            "expected_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "remote_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
            "can_trade_decision_source": CAN_TRADE_SOURCE,
            "can_trade_pre": can_trade,
            "can_trade_post": can_trade,
            "account_v2_has_canTrade_pre": True,
            "account_v2_has_canTrade_post": True,
            "account_v3_has_canTrade_pre": False,
            "account_v3_has_canTrade_post": False,
            "account_v3_canTrade_ignored_for_permission_decision": True,
            "live_order_readiness_blockers": live_blockers,
            "eligible_to_clear_p9cf_account_can_trade_blocker": can_trade,
            "prior_p9ce_blocker_reclassification": reclassification,
            "eligible_for_future_live_order_submission": False,
            "eligible_for_future_candidate_execution": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "supervisor_invocation_authorized": False,
            "timer_path_load_authorized": False,
            "position_fingerprint_stable": True,
            "open_order_fingerprint_stable": True,
            "balance_fingerprint_stable": True,
            "open_order_count_zero_pre_post": True,
            "order_cancel_fill_trade_delta_zero": True,
            "remote_control_boundary_unchanged": True,
            "open_position_count_pre": 11,
            "open_position_count_post": 11,
            "open_order_count_pre": 0,
            "open_order_count_post": 0,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "allowed_next_gate": P9CJ_GATE,
            "allowed_next_gate_scope": P9CJ_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "gates": {
                "owner_decision_p9ci_execute_read_only_recorded": True,
                "p9ch_summary_ready_for_p9ci": True,
                "remote_stdout_pit_safe_v2v3_account_collector_ready": True,
                "remote_runner_identity_ready": True,
                "pit_safe_read_only_account_proof_ready": True,
                "can_trade_source_is_fapi_v2_account": True,
                "account_v3_canTrade_ignored": True,
                "position_fingerprint_stable": True,
                "open_order_fingerprint_stable": True,
                "balance_fingerprint_stable": True,
                "open_order_count_zero_pre_post": True,
                "order_cancel_fill_trade_delta_zero": True,
                "remote_control_boundary_unchanged": True,
                "zero_orders_fills_trades": True,
            },
            "output_files": {
                "proof_artifact_manifest": str(paths["manifest"]),
                "pit_safe_account_proof": str(paths["proof"]),
                "account_delta_acceptance": str(paths["account_delta"]),
                "history_delta_acceptance": str(paths["history_delta"]),
                "remote_stdout_collector_sanitized": str(paths["collector"]),
                "remote_runner_identity_readback": str(paths["identity"]),
                "non_authorization": str(paths["non_auth"]),
                "control_boundary_readback": str(paths["control"]),
                "command_records": str(paths["commands"]),
                "summary": str(paths["p9ci_summary"]),
            },
        }
        _write_json(paths["p9ci_summary"], p9ci_summary)
        return paths


def _endpoint_group() -> dict[str, dict[str, object]]:
    return {
        key: {
            "status": "ok",
            "status_code": 200,
            "method": "GET",
            "path": path,
            "error": None,
            "error_type": None,
        }
        for key, path in {
            "account_v2": ACCOUNT_V2_ENDPOINT,
            "account_v3": ACCOUNT_V3_ENDPOINT,
            "account_config": ACCOUNT_CONFIG_ENDPOINT,
            "position_mode": POSITION_MODE_ENDPOINT,
            "open_orders": OPEN_ORDERS_ENDPOINT,
            "api_restrictions": API_RESTRICTIONS_ENDPOINT,
        }.items()
    }


def _account_snapshot(can_trade: bool, endpoint_group: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_binance_usdm_pit_safe_account_snapshot.v1",
        "status": "ready",
        "blockers": [],
        "label": "pre",
        "account_readable": True,
        "account_v2_has_canTrade": True,
        "account_v3_has_canTrade": False,
        "account_v3_canTrade_ignored_for_permission_decision": True,
        "can_trade": can_trade,
        "can_trade_source": CAN_TRADE_SOURCE,
        "expected_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "position_mode": "one_way",
        "open_position_count": 11,
        "open_order_count": 0,
        "future_live_order_readiness_blockers": []
        if can_trade
        else [BLOCKER_CAN_TRADE_FALSE],
        "endpoint_results": endpoint_group,
        "endpoint_schema": {
            "account_v2_path": ACCOUNT_V2_ENDPOINT,
            "account_v3_path": ACCOUNT_V3_ENDPOINT,
            "can_trade_decision_source": CAN_TRADE_SOURCE,
            "account_v3_canTrade_must_not_clear_or_fail_permission": True,
            "can_trade_missing_blocker": BLOCKER_CAN_TRADE_MISSING,
            "can_trade_false_blocker": BLOCKER_CAN_TRADE_FALSE,
        },
        "api_restrictions_summary": {
            "enable_futures": True,
            "enable_reading": True,
            "enable_withdrawals": False,
            "ip_restrict": True,
        },
    }


def _side_effects() -> dict[str, object]:
    return {
        "http_methods_used": ["GET"],
        "only_http_get_endpoints": True,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "candidate_executed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "order_test_calls": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _command(label: str) -> dict[str, object]:
    return {
        "label": label,
        "args": ["ssh", DEFAULT_REMOTE_HOST, "bash -lc readonly-proof"],
        "returncode": 0,
        "stdout_sha256": label + "-sha",
        "stdout_bytes": 10,
        "stderr_tail": "",
    }


def _evidence(path: Path) -> dict[str, object]:
    return {"exists": True, "path": str(path), "sha256": path.name + "-sha"}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
