from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CO_CONTRACT,
    P9CP_GATE,
    P9CP_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    APPROVE_P9CP_DECISION,
    CONTRACT_VERSION as P9CP_CONTRACT,
    P9CQ_GATE,
    build_phase9cp,
)


class Phase9CPReviewP9COTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cp-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9co_retained_evidence_without_remote_or_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9cp(
            self._args(paths, output_root=self.temp_dir / "p9cp"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 40, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CP_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"
            ]
        )
        self.assertTrue(summary["p9co_retained_evidence_sufficient_for_p9cp_review"])
        self.assertTrue(summary["p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate"])
        self.assertFalse(summary["p9co_sufficient_for_live_order_submission"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertTrue(summary["eligible_for_future_p9cq_scope_definition"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["remote_files_written"], 0)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CQ_GATE)

        sufficiency = _load_json(Path(summary["output_files"]["p9co_sufficiency_review"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(sufficiency["p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate"])
        self.assertFalse(sufficiency["p9co_sufficient_for_live_order_submission"])
        self.assertTrue(non_auth["authorizations"]["review_p9co_retained_evidence"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["candidate_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["order_test_endpoint_called"])

    def test_blocks_when_p9co_live_order_flag_is_polluted(self) -> None:
        paths = self._write_ready_inputs(summary_overrides={"live_order_gate_approved": True})

        summary, exit_code = build_phase9cp(
            self._args(paths, output_root=self.temp_dir / "blocked"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 45, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9co_summary_ready_for_p9cp_review", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9cq_scope_definition"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_authorizing_next_scope(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9cp(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 6, 50, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cp_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9cq_scope_definition"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_when_command_records_contain_forbidden_mutation(self) -> None:
        paths = self._write_ready_inputs(command_overrides={"forbidden": True})

        summary, exit_code = build_phase9cp(
            self._args(paths, output_root=self.temp_dir / "bad-command"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 55, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9co_command_records_ready", summary["blockers"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CP_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9co_summary=str(paths["p9co_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        command_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        root = self.temp_dir / "p9co"
        proof_root = root / "proof_artifacts" / "p9co" / "run"
        paths = {
            "project_profile": project_profile,
            "p9co_summary": root / "summary.json",
            "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
            "proof_status_matrix": proof_root / "proof_status_matrix.json",
            "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
            "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
            "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
            "market_proof_collection_delta_acceptance": proof_root / "market_delta.json",
            "fresh_order_book": proof_root / "fresh_order_book.json",
            "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
            "no_order_candidate_target_plan_replacement_dry_run_summary": proof_root / "p9bv_summary.json",
            "kill_switch_rollback_readback": proof_root / "kill_switch_rollback_readback.json",
            "non_authorization": proof_root / "non_authorization.json",
            "control_boundary_readback": proof_root / "control_boundary_readback.json",
            "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
            "remote_stdout_account_collector_sanitized": proof_root / "account_collector.json",
            "remote_stdout_market_collector": proof_root / "market_collector.json",
            "command_records": root / "command_records.json",
        }
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(paths["proof_status_matrix"], _proof_status_matrix())
        _write_json(paths["pit_safe_v2v3_account_proof"], _account_proof())
        _write_json(paths["account_delta_acceptance"], _account_delta())
        _write_json(paths["account_history_delta_acceptance"], _history_delta())
        _write_json(paths["market_proof_collection_delta_acceptance"], _market_delta())
        _write_json(paths["fresh_order_book"], _fresh_book())
        _write_json(paths["exchange_filter_readback"], _exchange_filters())
        _write_json(paths["no_order_candidate_target_plan_replacement_dry_run_summary"], _p9bv_summary())
        _write_json(paths["kill_switch_rollback_readback"], _kill_switch())
        _write_json(paths["non_authorization"], _non_authorization())
        _write_json(paths["control_boundary_readback"], _control())
        _write_json(paths["remote_runner_identity_readback"], {"contract_version": "identity.v1"})
        _write_json(paths["remote_stdout_account_collector_sanitized"], {"status": "ready"})
        _write_json(paths["remote_stdout_market_collector"], {"status": "ready"})
        _write_json(paths["command_records"], _command_records(**(command_overrides or {})))
        _write_json(paths["proof_artifact_manifest"], _manifest(paths))
        summary = _p9co_summary(paths)
        summary.update(summary_overrides or {})
        _write_json(paths["p9co_summary"], summary)
        return paths


def _p9co_summary(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_version": P9CO_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready": True,
        "p9cn_sufficient_for_p9co_execution": True,
        "fresh_remote_proof_collection_performed_in_p9co": True,
        "pit_safe_v2v3_account_proof_ready": True,
        "fresh_remote_account_read_performed": True,
        "fresh_order_book_read_performed": True,
        "exchange_filter_read_performed": True,
        "order_test_endpoint_called": False,
        "remote_execution_performed": True,
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "target_runner_identity_proven_in_p9co": True,
        "target_deploy_root_proven_in_p9co": True,
        "can_trade_decision_source": "/fapi/v2/account.canTrade",
        "can_trade_pre": True,
        "can_trade_post": True,
        "account_v2_has_canTrade_pre": True,
        "account_v2_has_canTrade_post": True,
        "account_v3_canTrade_ignored_for_permission_decision": True,
        "account_blocker_cleared_by_p9co": True,
        "live_order_readiness_blockers": [],
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
        "same_risk_paired_target_plan_binding": True,
        "distance_to_high_60_only_delta": True,
        "no_order_candidate_target_plan_replacement_dry_run_ready": True,
        "baseline_target_plan_sha256": "baseline-sha",
        "candidate_target_plan_sha256": "candidate-sha",
        "only_distance_to_high_60_contribution_changed": True,
        "read_only_fresh_proofs_ready": True,
        "live_order_gate_approval_collected": False,
        "live_order_gate_approved": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "allowed_next_gate": P9CP_GATE,
        "allowed_next_gate_scope": P9CP_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": {"all_p9co_gates": True},
        "output_files": {key: str(path) for key, path in paths.items() if key != "project_profile"},
    }


def _proof_status_matrix() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_proof_status_matrix.v1",
        "read_only_fresh_proofs_ready": True,
        "live_order_gate_approval_collected": False,
        "p9co_satisfies_live_order_gate": False,
        "proofs": [
            {
                "proof_id": proof_id,
                "max_age_seconds": max_age,
                "status": "ready"
                if proof_id != "final_owner_live_order_gate_approval"
                else "not_collected_by_design",
                **({"live_order_gate_approved": False} if proof_id == "final_owner_live_order_gate_approval" else {}),
            }
            for proof_id, max_age in EXPECTED_PROOFS.items()
        ],
    }


def _account_proof() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_binance_usdm_pit_safe_read_only_account_proof.v1",
        "pit_safe_read_only_account_proof_ready": True,
        "blockers": [],
        "can_trade_source": "/fapi/v2/account.canTrade",
        "can_trade_pre": True,
        "can_trade_post": True,
        "account_v2_has_canTrade_pre": True,
        "account_v2_has_canTrade_post": True,
        "account_v3_canTrade_ignored_for_permission_decision": True,
        "eligible_to_clear_p9cf_account_can_trade_blocker": True,
        "account_permission_source_corrected": True,
        "live_order_readiness_blockers": [],
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
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
    }


def _account_delta() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_account_delta_acceptance.v1",
        "position_fingerprint_stable": True,
        "open_order_fingerprint_stable": True,
        "balance_fingerprint_stable": True,
        "position_delta_zero_or_stable": True,
        "open_order_delta_zero_or_stable": True,
        "balance_delta_zero_or_stable": True,
        "open_order_count_zero_pre_post": True,
        "open_position_count_pre": 11,
        "open_position_count_post": 11,
        "open_order_count_pre": 0,
        "open_order_count_post": 0,
        "side_effects_zero": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _history_delta() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_history_delta_acceptance.v1",
        "order_history_fingerprint_stable": True,
        "trade_history_fingerprint_stable": True,
        "order_cancel_fill_trade_delta_zero": True,
        "order_history_hash_pre": "orders",
        "order_history_hash_post": "orders",
        "trade_history_hash_pre": "trades",
        "trade_history_hash_post": "trades",
        "proof_symbols": [CANARY_SYMBOL],
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _market_delta() -> dict[str, object]:
    payload = _history_delta()
    payload.update(
        {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ce_delta_acceptance.v1",
            "position_fingerprint_stable": True,
            "open_order_fingerprint_stable": True,
            "balance_fingerprint_stable": True,
            "fill_trade_fingerprint_stable": True,
            "position_delta_zero_or_stable": True,
            "balance_delta_zero_or_stable": True,
            "open_position_count_pre": 11,
            "open_position_count_post": 11,
            "open_order_count_pre": 0,
            "open_order_count_post": 0,
        }
    )
    return payload


def _fresh_book() -> dict[str, object]:
    return {
        "status": "ready",
        "symbol": CANARY_SYMBOL,
        "endpoint": "/fapi/v1/depth",
        "method": "GET",
        "book_hash": "book-hash",
        "book": {"symbol": CANARY_SYMBOL, "best_bid": ["1", "1"], "best_ask": ["2", "1"]},
    }


def _exchange_filters() -> dict[str, object]:
    return {
        "status": "ready",
        "endpoint": "/fapi/v1/exchangeInfo",
        "method": "GET",
        "filters_hash": "filters-hash",
        "symbol_count": 1,
        "symbols": [
            {
                "symbol": CANARY_SYMBOL,
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "filters": [{"filterType": "PRICE_FILTER"}],
            }
        ],
    }


def _p9bv_summary() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run.v1",
        "status": "ready",
        "blockers": [],
        "p9bv_no_order_replacement_dry_run_ready": True,
        "candidate_target_plan_replacement_semantics_proven": True,
        "exact_p9bu_terms_applied": True,
        "same_timestamp_context": True,
        "same_risk_inputs": True,
        "candidate_plan_differs_from_baseline": True,
        "simulated_executor_input_replacement_matches_candidate": True,
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "only_distance_to_high_60_contribution_changed": True,
        "changed_symbol_count": 1,
        "order_intent_preview_count": 1,
        "baseline_target_plan_sha256": "baseline-sha",
        "candidate_target_plan_sha256": "candidate-sha",
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _kill_switch() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_kill_switch_rollback_readback.v1",
        "remote_control_boundary_unchanged": True,
        "kill_switch_or_operator_state_mutated_by_p9co": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "candidate_executed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "pre_control_snapshot": {"exists": True},
        "post_control_snapshot": {"exists": True},
    }


def _non_authorization() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_non_authorization.v1",
        "authorizations": {
            "p9co_post_account_blocker_read_only_fresh_remote_proof_collection": True,
            "remote_stdout_read_only_account_market_collection": True,
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


def _control() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_control_boundary.v1",
        "scope": "post_account_blocker_read_only_fresh_remote_proof_collection_stdout_only",
        "ssh_invoked": True,
        "remote_network_connection_performed": True,
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": True,
        "fresh_order_book_read_performed": True,
        "exchange_filter_read_performed": True,
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


def _command_records(*, forbidden: bool = False) -> dict[str, object]:
    labels = [
        "pre_control_snapshot",
        "remote_stdout_pit_safe_v2v3_account_collector",
        "remote_stdout_market_and_fingerprint_collector",
        "post_control_snapshot",
    ]
    commands = []
    for index, label in enumerate(labels):
        args = ["ssh", "root@203.0.113.10", f"readonly-{label}"]
        if forbidden and index == 1:
            args.append("/fapi/v1/order/test")
        commands.append(
            {
                "label": label,
                "args": args,
                "returncode": 0,
                "stdout_sha256": f"stdout-{index}",
                "stdout_bytes": 10,
                "stderr_tail": "",
            }
        )
    return {"commands": commands}


def _manifest(paths: dict[str, Path]) -> dict[str, object]:
    artifact_keys = {
        "account_delta_acceptance",
        "account_history_delta_acceptance",
        "control_boundary_readback",
        "exchange_filter_readback",
        "fresh_order_book",
        "kill_switch_rollback_readback",
        "market_proof_collection_delta_acceptance",
        "no_order_candidate_target_plan_replacement_dry_run_summary",
        "non_authorization",
        "pit_safe_v2v3_account_proof",
        "proof_status_matrix",
        "remote_runner_identity_readback",
        "remote_stdout_account_collector_sanitized",
        "remote_stdout_market_collector",
    }
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_proof_artifact_manifest.v1",
        "artifact_count": len(artifact_keys),
        "artifacts": {
            key: {"exists": True, "path": str(paths[key]), "sha256": f"{key}-sha"}
            for key in artifact_keys
        },
        "self": {"exists": True, "path": str(paths["proof_artifact_manifest"]), "sha256": "self-sha"},
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
