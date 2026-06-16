from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import hashlib
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CE_CONTRACT,
    P9CF_GATE,
    P9CF_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    APPROVE_P9CF_DECISION,
    CONTRACT_VERSION as P9CF_CONTRACT,
    EXPECTED_P9CE_ARTIFACT_KEYS,
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
    P9CG_GATE,
    build_phase9cf,
)


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


class Phase9CFReviewP9CEReadOnlyFreshRemoteProofCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cf-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9ce_but_blocks_live_order_due_account_can_trade(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9cf(
            self._args(paths, output_root=self.temp_dir / "p9cf"),
            now_fn=lambda: datetime(2026, 6, 10, 20, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CF_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary["p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready"]
        )
        self.assertTrue(summary["p9ce_sufficient_for_read_only_collection_review"])
        self.assertFalse(summary["p9ce_sufficient_for_live_order_gate"])
        self.assertEqual(
            summary["live_order_readiness_blockers"],
            [LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE],
        )
        self.assertTrue(
            summary["eligible_for_future_p9cg_live_order_readiness_blocker_scope_gate"]
        )
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CG_GATE)

        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization"]))
        review = _load_json(Path(summary["output_files"]["sufficiency_review"]))
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertEqual(control["orders_submitted"], 0)
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertTrue(
            matrix["authorizations"]["allow_future_p9cg_blocker_resolution_scope_gate"]
        )
        self.assertTrue(review["p9ce_sufficient_for_read_only_collection_review"])
        self.assertFalse(review["p9ce_sufficient_for_live_order_gate"])

    def test_blocks_when_owner_decision_is_not_p9cf_review_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9cf(
            self._args(
                paths,
                output_root=self.temp_dir / "bad-owner",
                owner_decision="approve_live_orders_instead",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 20, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cf_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9ce_sufficient_for_read_only_collection_review"])
        self.assertFalse(summary["p9ce_sufficient_for_live_order_gate"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9ce_summary_does_not_allow_p9cf(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9CG_skip_review"},
        )

        summary, exit_code = build_phase9cf(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 20, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ce_summary_ready_for_retained_review", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_delta_or_manifest_is_not_retained_ready(self) -> None:
        paths = self._write_ready_inputs(
            delta_overrides={"order_cancel_fill_trade_delta_zero": False},
            manifest_artifact_drop="fresh_order_book",
        )

        summary, exit_code = build_phase9cf(
            self._args(paths, output_root=self.temp_dir / "bad-delta"),
            now_fn=lambda: datetime(2026, 6, 10, 20, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ce_delta_acceptance_ready", summary["blockers"])
        self.assertIn("p9ce_proof_manifest_ready", summary["blockers"])
        self.assertFalse(summary["p9ce_sufficient_for_live_order_gate"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CF_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ce_summary=str(paths["p9ce_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        delta_overrides: dict[str, object] | None = None,
        manifest_artifact_drop: str = "",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9ce_root = self.temp_dir / "p9ce"
        proof_root = p9ce_root / "proof_artifacts" / "p9ce" / "20260610T195500Z"
        p9ce_summary = p9ce_root / "summary.json"

        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "project": "Meridian Alpha Platform",
            },
        )

        artifacts = {
            "remote_runner_identity_readback": {
                "repo_path": TARGET_DEPLOY_ROOT_HINT,
                "egress_ip": "203.0.113.10",
            },
            "fresh_remote_account_read": _fresh_account_payload(),
            "pre_position_fingerprint": {"stable_hash": "position-hash"},
            "post_position_fingerprint": {"stable_hash": "position-hash"},
            "pre_open_order_fingerprint": {"stable_hash": "open-order-hash"},
            "post_open_order_fingerprint": {"stable_hash": "open-order-hash"},
            "pre_fill_trade_fingerprint": {
                "order_history_fingerprint": {"history_hash": "order-history-hash"},
                "trade_history_fingerprint": {"history_hash": "trade-history-hash"},
            },
            "post_fill_trade_fingerprint": {
                "order_history_fingerprint": {"history_hash": "order-history-hash"},
                "trade_history_fingerprint": {"history_hash": "trade-history-hash"},
            },
            "fresh_order_book": {
                "status": "ready",
                "symbol": CANARY_SYMBOL,
                "endpoint": "/fapi/v1/depth",
                "method": "GET",
                "book_hash": "book-hash",
            },
            "exchange_filter_readback": {
                "status": "ready",
                "endpoint": "/fapi/v1/exchangeInfo",
                "method": "GET",
                "filters_hash": "filters-hash",
                "symbol_count": 20,
            },
            "p9bu_terms_operator_acceptance": {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_p9bu_terms_operator_acceptance.v1",
                "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
                "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
                "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
                "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
                "order_type": DEFAULT_ORDER_TYPE,
                "time_in_force": DEFAULT_TIME_IN_FORCE,
                "market_orders_allowed": False,
                "final_owner_live_order_gate_approval": False,
                "live_order_gate_approved": False,
                "candidate_execution_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
            },
            "candidate_target_plan_hash_binding": {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_target_plan_hash_binding.v1",
                "baseline_target_plan_sha256": BASELINE_SHA,
                "candidate_target_plan_sha256": CANDIDATE_SHA,
                "candidate_not_in_executor_path": True,
                "executor_input_remains_baseline_only": True,
                "target_plan_replacement_performed": False,
            },
            "baseline_candidate_plan_diff": {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_baseline_candidate_plan_diff.v1",
                "baseline_target_plan_sha256": BASELINE_SHA,
                "candidate_target_plan_sha256": CANDIDATE_SHA,
                "only_distance_to_high_60_contribution_changed": True,
                "executor_consumes_baseline_only": True,
                "candidate_shadow_only": True,
            },
            "kill_switch_readback": {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_kill_switch_readback.v1",
                "remote_control_boundary_unchanged": True,
                "kill_switch_or_operator_state_mutated_by_p9ce": False,
            },
            "rollback_command_readback": {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_rollback_command_readback.v1",
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "supervisor_invoked": False,
                "timer_path_invoked": False,
                "candidate_executed": False,
                "executor_input_mutated": False,
                "target_plan_replaced": False,
            },
            "proof_collection_delta_acceptance": _delta_payload(delta_overrides),
            "non_authorization": _non_authorization_payload(),
            "control_boundary_readback": _control_payload(),
        }
        output_files: dict[str, str] = {}
        for key, payload in artifacts.items():
            path = proof_root / f"{key}.json"
            _write_json(path, payload)
            output_files[key] = str(path)

        manifest_entries = {
            key: _evidence(proof_root / f"{key}.json")
            for key in sorted(EXPECTED_P9CE_ARTIFACT_KEYS)
            if key != manifest_artifact_drop
        }
        manifest_path = proof_root / "proof_artifact_manifest.json"
        _write_json(
            manifest_path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ce_proof_manifest.v1",
                "artifact_count": len(manifest_entries),
                "artifacts": manifest_entries,
                "self": {
                    "exists": True,
                    "path": str(manifest_path),
                    "sha256": "retained-self-hash",
                },
            },
        )
        output_files["proof_artifact_manifest"] = str(manifest_path)

        command_records = p9ce_root / "command_records.json"
        pre_snapshot = p9ce_root / "pre_control_snapshot.json"
        post_snapshot = p9ce_root / "post_control_snapshot.json"
        _write_json(command_records, {"commands": []})
        _write_json(pre_snapshot, {"remote_live_config_sha256": "config-sha"})
        _write_json(post_snapshot, {"remote_live_config_sha256": "config-sha"})
        output_files["command_records"] = str(command_records)
        output_files["pre_control_snapshot"] = str(pre_snapshot)
        output_files["post_control_snapshot"] = str(post_snapshot)

        summary = {
            "contract_version": P9CE_CONTRACT,
            "run_id": "20260610T195500Z",
            "status": "ready",
            "blockers": [],
            "p9ce_read_only_fresh_remote_proof_collection_ready": True,
            "fresh_remote_proof_collection_performed_in_p9ce": True,
            "fresh_remote_account_read_performed": True,
            "fresh_order_book_read_performed": True,
            "exchange_filter_read_performed": True,
            "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
            "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
            "target_runner_identity_proven_in_p9ce": True,
            "target_deploy_root_proven_in_p9ce": True,
            "remote_execution_performed": True,
            "remote_execution_scope": "stdout_read_only_collector_only",
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "supervisor_invocation_authorized": False,
            "timer_path_load_authorized": False,
            "production_timer_service_load_authorized": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "position_fingerprint_stable": True,
            "open_order_fingerprint_stable": True,
            "balance_fingerprint_stable": True,
            "fill_trade_fingerprint_stable": True,
            "order_cancel_fill_trade_delta_zero": True,
            "remote_control_boundary_unchanged": True,
            "open_position_count_pre": 1,
            "open_position_count_post": 1,
            "open_order_count_pre": 0,
            "open_order_count_post": 0,
            "account_can_trade_pre": False,
            "account_can_trade_post": False,
            "future_live_order_readiness_blockers": [
                LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
            ],
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
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "only_distance_to_high_60_contribution_changed": True,
            "eligible_for_future_live_order_submission": False,
            "eligible_for_future_candidate_execution": False,
            "allowed_next_gate": P9CF_GATE,
            "allowed_next_gate_scope": P9CF_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "output_files": output_files,
        }
        summary.update(summary_overrides or {})
        _write_json(p9ce_summary, summary)
        return {
            "project_profile": project_profile,
            "p9ce_summary": p9ce_summary,
        }


def _fresh_account_payload() -> dict[str, object]:
    side_effects = {
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
    }
    account = {
        "account_readable": True,
        "can_trade": False,
        "position_mode": "one_way",
        "open_order_count": 0,
        "open_position_count": 1,
        "egress_ip": "203.0.113.10",
        "future_live_order_readiness_blockers": [
            LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
        ],
    }
    return {
        "status": "ready",
        "pre": dict(account),
        "post": dict(account),
        "side_effects": side_effects,
    }


def _delta_payload(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_delta_acceptance.v1",
        "position_fingerprint_stable": True,
        "open_order_fingerprint_stable": True,
        "balance_fingerprint_stable": True,
        "fill_trade_fingerprint_stable": True,
        "position_delta_zero_or_stable": True,
        "balance_delta_zero_or_stable": True,
        "order_cancel_fill_trade_delta_zero": True,
        "open_order_count_pre": 0,
        "open_order_count_post": 0,
        "open_position_count_pre": 1,
        "open_position_count_post": 1,
        "order_history_hash_pre": "order-history-hash",
        "order_history_hash_post": "order-history-hash",
        "trade_history_hash_pre": "trade-history-hash",
        "trade_history_hash_post": "trade-history-hash",
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    payload.update(overrides or {})
    return payload


def _control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_control_boundary.v1",
        "scope": "read_only_fresh_remote_proof_collection_stdout_only",
        "ssh_invoked": True,
        "remote_network_connection_performed": True,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": True,
        "fresh_order_book_read_performed": True,
        "exchange_filter_read_performed": True,
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


def _non_authorization_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_non_authorization.v1",
        "authorizations": {
            "p9ce_read_only_fresh_remote_proof_collection": True,
            "remote_stdout_read_only_collection": True,
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence(path: Path) -> dict[str, object]:
    return {
        "exists": path.exists(),
        "path": str(path),
        "sha256": _sha256(path) if path.exists() else "",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
