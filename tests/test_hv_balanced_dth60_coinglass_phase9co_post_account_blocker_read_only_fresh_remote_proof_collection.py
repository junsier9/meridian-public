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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    CONTRACT_VERSION as P9BU_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_RISK_CEILING_USDT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_ORDER_TYPE,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CN_CONTRACT,
    P9CO_GATE,
    P9CO_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    APPROVE_P9CO_DECISION,
    CONTRACT_VERSION as P9CO_CONTRACT,
    P9CP_GATE,
    build_phase9co,
)
from tests.test_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    _collector_payload as _market_collector_payload,
    _snapshot_payload,
)
from tests.test_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    _collector_payload as _account_collector_payload,
)


class Phase9COPostAccountBlockerReadOnlyFreshRemoteProofCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9co-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_collects_post_account_blocker_fresh_proofs_without_order_or_execution_path(self) -> None:
        paths = self._write_ready_inputs()
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(_account_collector_payload(can_trade_v2=True, can_trade_v3_marker=False)),
                _command_json(_market_collector_payload()),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9co(
            self._args(paths, output_root=self.temp_dir / "p9co"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 0, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CO_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"])
        self.assertTrue(summary["p9cn_sufficient_for_p9co_execution"])
        self.assertTrue(summary["fresh_remote_proof_collection_performed_in_p9co"])
        self.assertTrue(summary["pit_safe_v2v3_account_proof_ready"])
        self.assertEqual(summary["can_trade_decision_source"], "/fapi/v2/account.canTrade")
        self.assertTrue(summary["can_trade_pre"])
        self.assertTrue(summary["can_trade_post"])
        self.assertTrue(summary["account_blocker_cleared_by_p9co"])
        self.assertTrue(summary["account_v3_canTrade_ignored_for_permission_decision"])
        self.assertTrue(summary["fresh_order_book_read_performed"])
        self.assertTrue(summary["exchange_filter_read_performed"])
        self.assertTrue(summary["position_fingerprint_stable"])
        self.assertTrue(summary["open_order_fingerprint_stable"])
        self.assertTrue(summary["balance_fingerprint_stable"])
        self.assertTrue(summary["order_cancel_fill_trade_delta_zero"])
        self.assertTrue(summary["remote_control_boundary_unchanged"])
        self.assertTrue(summary["same_risk_paired_target_plan_binding"])
        self.assertTrue(summary["distance_to_high_60_only_delta"])
        self.assertTrue(summary["no_order_candidate_target_plan_replacement_dry_run_ready"])
        self.assertTrue(summary["read_only_fresh_proofs_ready"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_gate_approval_collected"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CP_GATE)

        outputs = summary["output_files"]
        proof_status = _load_json(Path(outputs["proof_status_matrix"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        non_auth = _load_json(Path(outputs["non_authorization"]))
        manifest = _load_json(Path(outputs["proof_artifact_manifest"]))
        commands = _load_json(Path(outputs["command_records"]))["commands"]

        ready_rows = {
            row["proof_id"]: row["status"]
            for row in proof_status["proofs"]
        }
        self.assertEqual(ready_rows["pit_safe_v2v3_account_proof"], "ready")
        self.assertEqual(ready_rows["fresh_order_book_and_exchange_filters"], "ready")
        self.assertEqual(
            ready_rows["final_owner_live_order_gate_approval"],
            "not_collected_by_design",
        )
        self.assertTrue(manifest["self"]["exists"])
        self.assertEqual(control["remote_files_written"], 0)
        self.assertFalse(control["remote_sync_performed"])
        self.assertFalse(control["order_test_endpoint_called"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["candidate_execution_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertFalse(control["executor_input_changed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["candidate_execution"])

        self.assertEqual(
            [record["label"] for record in commands],
            [
                "pre_control_snapshot",
                "remote_stdout_pit_safe_v2v3_account_collector",
                "remote_stdout_market_and_fingerprint_collector",
                "post_control_snapshot",
            ],
        )
        command_text = "\n".join(" ".join(record["args"]) for record in commands)
        self.assertNotIn("scp ", command_text)
        self.assertNotIn("/fapi/v1/order/test", command_text)
        self.assertNotIn("systemctl start", command_text)
        self.assertNotIn("systemctl enable", command_text)

    def test_blocks_when_p9cn_does_not_allow_p9co_without_running_remote(self) -> None:
        paths = self._write_ready_inputs()
        p9cn = _load_json(paths["p9cn_summary"])
        p9cn["allowed_next_gate"] = "P9CP_skip_p9co"
        _write_json(paths["p9cn_summary"], p9cn)
        runner = SequentialRunner([])

        summary, exit_code = build_phase9co(
            self._args(paths, output_root=self.temp_dir / "blocked-p9cn"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 5, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cn_summary_ready_for_p9co", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9co"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(runner.calls, [])

    def test_blocks_when_v2_can_trade_false_after_account_blocker(self) -> None:
        paths = self._write_ready_inputs()
        runner = SequentialRunner(
            [
                _command_json(_snapshot_payload()),
                _command_json(_account_collector_payload(can_trade_v2=False, can_trade_v3_marker=True)),
                _command_json(_market_collector_payload()),
                _command_json(_snapshot_payload()),
            ]
        )

        summary, exit_code = build_phase9co(
            self._args(paths, output_root=self.temp_dir / "cantrade-false"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 10, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("can_trade_v2_false_or_missing_after_account_blocker", summary["blockers"])
        self.assertFalse(summary["can_trade_pre"])
        self.assertFalse(summary["account_blocker_cleared_by_p9co"])
        self.assertEqual(summary["live_order_readiness_blockers"], ["canTrade_false"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CO_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cn_summary=str(paths["p9cn_summary"]),
            phase9bu_summary=str(paths["p9bu_summary"]),
            remote_host=DEFAULT_REMOTE_HOST,
            remote_repo=DEFAULT_REMOTE_REPO,
            remote_config=DEFAULT_REMOTE_CONFIG,
            remote_live_env=DEFAULT_REMOTE_LIVE_ENV,
            remote_python=DEFAULT_REMOTE_PYTHON,
            expected_egress_ip=DEFAULT_EXPECTED_EGRESS_IP,
            canary_symbol=CANARY_SYMBOL,
            max_history_symbols=20,
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        p9cn_paths = self._write_p9cn_fixture()
        p9bu_summary = self._write_p9bu_fixture(project_profile)
        return {
            "project_profile": project_profile,
            "p9cn_summary": p9cn_paths["summary"],
            "p9bu_summary": p9bu_summary,
        }

    def _write_p9cn_fixture(self) -> dict[str, Path]:
        root = self.temp_dir / "p9cn"
        proof_root = root / "proof_artifacts" / "p9cn" / "run"
        paths = {
            "summary": root / "summary.json",
            "owner_gate": proof_root / "read_only_fresh_remote_proof_collection_owner_gate.json",
            "future_scope": proof_root / "future_p9co_execution_gate_scope.json",
            "non_authorization": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
        }
        proof_rows = _proof_rows()
        _write_json(
            paths["owner_gate"],
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9cn_owner_gate.v1",
                "owner_gate_only": True,
                "owner_gate_decision": "allow_future_p9co_execution_gate_request_only",
                "p9cm_sufficient_for_p9cn_owner_gate": True,
                "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn": True,
                "eligible_for_future_p9co_execution_gate_request": True,
                "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
                "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
                "fresh_remote_proof_collection_performed_in_p9cn": False,
                "live_order_gate_approved": False,
                "live_order_submission_authorized": False,
                "candidate_execution_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "future_gate": P9CO_GATE,
                "future_gate_scope": P9CO_SCOPE,
                "future_gate_must_be_separately_requested": True,
                "required_proofs_to_collect_later": proof_rows,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
            },
        )
        _write_json(
            paths["future_scope"],
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9cn_future_p9co_execution_gate_scope.v1",
                "owner_gate_only": True,
                "future_gate": P9CO_GATE,
                "future_gate_scope": P9CO_SCOPE,
                "future_gate_must_be_separately_requested": True,
                "future_gate_may_execute_only": [
                    "read-only fresh remote proof collection",
                    "PIT-safe v2/v3 account proof",
                    "fresh position, open-order, balance, order, trade, book, and filter reads",
                    "no-order same-risk paired target-plan and distance_to_high_60 contribution checks",
                    "kill-switch and rollback readbacks",
                ],
                "future_gate_may_not_execute": [
                    "live order submission",
                    "order-test endpoint call",
                    "candidate execution",
                    "target-plan replacement",
                    "executor-input mutation",
                    "timer path load",
                    "supervisor invocation",
                    "remote sync",
                    "live config, operator state, or timer mutation",
                ],
                "required_proofs": proof_rows,
                "fresh_remote_proof_collection_performed_in_p9cn": False,
                "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
                "live_order_submission_authorized": False,
            },
        )
        _write_json(
            paths["non_authorization"],
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9cn_non_authorization.v1",
                "authorizations": {
                    "allow_future_p9co_execution_gate_request": True,
                    "fresh_remote_proof_collection_execution": False,
                    "fresh_remote_proof_collection": False,
                    "fresh_remote_account_read": False,
                    "fresh_order_book_read": False,
                    "exchange_filter_read": False,
                    "order_test_endpoint": False,
                    "remote_execution": False,
                    "remote_sync": False,
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
                    "stage_governance_change": False,
                },
            },
        )
        _write_json(paths["control"], _p9cn_control())
        _write_json(paths["summary"], _p9cn_summary(paths))
        return paths

    def _write_p9bu_fixture(self, project_profile: Path) -> Path:
        root = self.temp_dir / "p9bu"
        terms_path = root / "proof_artifacts" / "p9bu" / "terms.json"
        preapproval_path = root / "proof_artifacts" / "p9bu" / "preapproval.json"
        summary_path = root / "summary.json"
        _write_json(terms_path, _p9bu_terms())
        _write_json(preapproval_path, _p9bu_preapproval())
        _write_json(
            summary_path,
            {
                "contract_version": P9BU_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p9bu_preapproval_terms_review_ready": True,
                "candidate_executor_target_path_preapproval_exists": True,
                "candidate_executor_target_path_preapproval_review_passed": True,
                "requested_live_order_terms_complete": True,
                "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
                "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
                "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
                "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
                "order_type": DEFAULT_ORDER_TYPE,
                "time_in_force": DEFAULT_TIME_IN_FORCE,
                "candidate_enter_executor_target_plan_path_authorized": False,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "output_files": {
                    "risk_order_terms": str(terms_path),
                    "candidate_executor_target_plan_preapproval": str(preapproval_path),
                },
            },
        )
        return summary_path


class SequentialRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def __call__(self, args: Any) -> CommandResult:
        call = list(args)
        self.calls.append(call)
        if not self.results:
            return CommandResult(args=call, returncode=99, stdout="", stderr="unexpected")
        result = self.results.pop(0)
        return CommandResult(args=call, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _proof_rows() -> list[dict[str, object]]:
    return [
        {
            "proof_id": proof_id,
            "required": True,
            "max_age_seconds": max_age,
            "required_before": "future_live_order_gate_approval"
            if proof_id != "final_owner_live_order_gate_approval"
            else "any_order_submission",
            "acceptance": [f"{proof_id}_acceptance"],
            "collection_status_in_p9cl": "not_collected",
            "future_collection_requires_separate_owner_gate": True,
        }
        for proof_id, max_age in EXPECTED_PROOFS.items()
    ]


def _p9cn_summary(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_version": P9CN_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready": True,
        "p9cm_sufficient_for_p9cn_owner_gate": True,
        "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn": True,
        "eligible_for_future_p9co_execution_gate_request": True,
        "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
        "fresh_remote_proof_collection_performed_in_p9cn": False,
        "fresh_proofs_collected_in_p9cn": False,
        "fresh_proofs_satisfied_by_p9cn": False,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "required_fresh_proof_count": len(EXPECTED_PROOFS),
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P9CO_GATE,
        "allowed_next_gate_scope": P9CO_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "output_files": {
            "read_only_fresh_remote_proof_collection_owner_gate": str(paths["owner_gate"]),
            "future_p9co_execution_gate_scope": str(paths["future_scope"]),
            "non_authorization": str(paths["non_authorization"]),
            "control_boundary_readback": str(paths["control"]),
        },
    }


def _p9cn_control() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_control_boundary.v1",
        "scope": "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
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


def _p9bu_terms() -> dict[str, object]:
    return {
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "reduce_only_required_for_rollback_exits": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "candidate_overlay_components": [
            "coinglass_top_trader_crowded_branch",
            "binance_shock_branch",
        ],
        "fresh_account_read_max_age_seconds": 60,
        "fresh_position_fingerprint_max_age_seconds": 60,
        "fresh_open_order_fingerprint_max_age_seconds": 60,
        "fresh_fill_trade_fingerprint_max_age_seconds": 60,
        "fresh_order_book_max_age_seconds": 10,
        "candidate_artifact_stale_after_seconds": 60,
        "limit_price_must_not_cross_spread": True,
        "max_limit_price_distance_bps_from_mid": 5,
        "max_mark_price_deviation_bps": 10,
        "order_lifetime_seconds": 60,
        "kill_switch": "disable candidate and revert executor to baseline-only",
        "rollback_conditions": [
            "candidate proof missing",
            "executor hash mismatch",
            "unexplained order delta",
        ],
    }


def _p9bu_preapproval() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval.v1",
        "run_id": "unit-test",
        "status": "ready",
        "candidate_executor_target_path_preapproval_exists": True,
        "candidate_executor_target_path_preapproval_review_passed": True,
        "candidate_enter_executor_target_plan_path_authorized_now": False,
        "candidate_execution_authorized_now": False,
        "live_order_submission_authorized_now": False,
        "integration_contract": {
            "baseline_plan_must_be_generated_first": True,
            "candidate_plan_must_be_paired_with_baseline_same_timestamp": True,
            "candidate_plan_must_use_same_risk_inputs_as_baseline": True,
            "candidate_target_plan_replacement_requires_future_no_order_dry_run": True,
        },
    }


def _command_json(payload: dict[str, object], *, returncode: int = 0) -> CommandResult:
    return CommandResult(args=["fake"], returncode=returncode, stdout=json.dumps(payload), stderr="")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
