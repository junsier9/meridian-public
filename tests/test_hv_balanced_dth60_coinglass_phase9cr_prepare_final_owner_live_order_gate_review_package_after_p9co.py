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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cq_define_final_owner_live_order_gate_scope_after_p9co import (  # noqa: E402
    CONTRACT_VERSION as P9CQ_CONTRACT,
    P9CR_GATE,
    P9CR_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (  # noqa: E402
    APPROVE_P9CR_DECISION,
    CONTRACT_VERSION as P9CR_CONTRACT,
    P9CS_GATE,
    build_phase9cr,
)


class Phase9CRFinalOwnerReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cr-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_final_owner_review_package_only(self) -> None:
        paths = self._write_ready_p9cq_inputs()

        summary, exit_code = build_phase9cr(
            self._args(paths, output_root=self.temp_dir / "p9cr"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CR_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cr_final_owner_live_order_gate_review_package_prepared"])
        self.assertTrue(summary["p9cq_sufficient_for_p9cr_review_package"])
        self.assertTrue(summary["review_package_prepared_after_p9co"])
        self.assertEqual(summary["required_final_gate_evidence_count"], 12)
        self.assertFalse(summary["final_gate_evidence_collected_in_p9cr"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cr"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cr"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["p9cr_satisfies_final_owner_live_order_gate"])
        self.assertTrue(summary["eligible_for_future_p9cs_package_review"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CS_GATE)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["canary_side"], "BUY")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")

        package = _load_json(
            Path(summary["output_files"]["final_owner_live_order_gate_review_package"])
        )
        canary = _load_json(Path(summary["output_files"]["canary_order_terms"]))
        evidence_plan = _load_json(Path(summary["output_files"]["final_gate_evidence_plan"]))
        checklist = _load_json(Path(summary["output_files"]["approval_checklist"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertTrue(package["package_only"])
        self.assertEqual(package["package_decision"], "prepared_for_future_review_only")
        self.assertFalse(package["p9cr_satisfies_final_owner_live_order_gate"])
        self.assertFalse(package["live_order_submission_authorized"])
        self.assertFalse(package["candidate_enter_executor_target_plan_path_authorized"])
        self.assertEqual(package["orders_submitted"], 0)
        self.assertFalse(canary["would_submit_order"])
        self.assertFalse(canary["market_orders_allowed"])
        self.assertEqual(canary["order_type"], "post_only_limit")
        self.assertEqual(len(evidence_plan["evidence"]), 12)
        self.assertEqual(
            {row["status_in_p9cr"] for row in evidence_plan["evidence"]},
            {"packaged_only_not_final_approved"},
        )
        self.assertEqual(
            {row["collection_status_in_p9cr"] for row in evidence_plan["evidence"]},
            {"not_collected"},
        )
        by_item = {row["item"]: row for row in checklist["approval_items"]}
        self.assertTrue(
            by_item["p9co_account_blocker_cleared_and_canTrade_v2_true"][
                "satisfied_in_p9cr"
            ]
        )
        self.assertFalse(
            by_item["all_required_final_gate_evidence_present_and_unexpired"][
                "satisfied_in_p9cr"
            ]
        )
        self.assertFalse(
            by_item["explicit_final_owner_live_order_decision"]["satisfied_in_p9cr"]
        )
        self.assertTrue(
            non_auth["authorizations"]["prepare_final_owner_live_order_gate_review_package"]
        )
        self.assertFalse(non_auth["authorizations"]["final_owner_live_order_gate_approval"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cq_allowed_next_gate_is_not_p9cr(self) -> None:
        paths = self._write_ready_p9cq_inputs(
            summary_overrides={"allowed_next_gate": "P9CS_skip_package_review"}
        )

        summary, exit_code = build_phase9cr(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cq_summary_ready_for_p9cr_package", summary["blockers"])
        self.assertFalse(summary["p9cr_final_owner_live_order_gate_review_package_prepared"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_live_order_authority(self) -> None:
        paths = self._write_ready_p9cq_inputs()

        summary, exit_code = build_phase9cr(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 9, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cr_package_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9cr_final_owner_live_order_gate_review_package_prepared"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_if_p9cq_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_p9cq_inputs()
        matrix = _load_json(paths["non_auth"])
        matrix["authorizations"]["live_order_submission"] = True
        _write_json(paths["non_auth"], matrix)

        summary, exit_code = build_phase9cr(
            self._args(paths, output_root=self.temp_dir / "bad-non-auth"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cq_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CR_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cq_summary=str(paths["p9cq_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cq_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        root = self.temp_dir / "p9cq"
        proof_root = root / "proof_artifacts" / "p9cq" / "run"
        paths = {
            "project_profile": project_profile,
            "p9cq_summary": root / "summary.json",
            "scope": proof_root / "final_owner_live_order_gate_scope.json",
            "evidence": proof_root / "required_final_gate_evidence.json",
            "non_auth": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
        }
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(paths["scope"], _p9cq_scope())
        _write_json(paths["evidence"], _required_final_gate_evidence())
        _write_json(paths["non_auth"], _p9cq_non_authorization())
        _write_json(paths["control"], _p9cq_control())
        summary = _p9cq_summary(paths)
        summary.update(summary_overrides or {})
        _write_json(paths["p9cq_summary"], summary)
        return paths


def _p9cq_summary(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_version": P9CQ_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cq_final_owner_live_order_gate_scope_defined": True,
        "p9cp_sufficient_for_p9cq_scope_definition": True,
        "p9co_retained_read_only_fresh_proofs_ready": True,
        "account_blocker_cleared_by_p9co": True,
        "final_owner_live_order_gate_scope_defined_after_p9co": True,
        "required_final_gate_evidence_count": 12,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "p9cq_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cr_review_package": True,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cq": False,
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
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "canary_symbol": "BTCUSDT",
        "canary_side": "BUY",
        "risk_ceiling_usdt": 25.0,
        "max_notional_usdt": 10.0,
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "market_orders_allowed": False,
        "source_p9co_baseline_target_plan_sha256": BASELINE_SHA,
        "source_p9co_candidate_target_plan_sha256": CANDIDATE_SHA,
        "source_p9co_can_trade_pre": True,
        "source_p9co_can_trade_post": True,
        "source_p9co_open_order_count_pre": 0,
        "source_p9co_open_order_count_post": 0,
        "source_p9co_order_cancel_fill_trade_delta_zero": True,
        "source_p9co_remote_control_boundary_unchanged": True,
        "source_p9co_only_distance_to_high_60_contribution_changed": True,
        "allowed_next_gate": P9CR_GATE,
        "allowed_next_gate_scope": P9CR_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "checks": {"all_p9cq_checks": True},
        "output_files": {
            "summary": str(paths["p9cq_summary"]),
            "final_owner_live_order_gate_scope": str(paths["scope"]),
            "required_final_gate_evidence": str(paths["evidence"]),
            "non_authorization": str(paths["non_auth"]),
            "control_boundary_readback": str(paths["control"]),
        },
    }


def _p9cq_scope() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_final_owner_live_order_gate_scope.v1",
        "scope_definition_only": True,
        "scope_basis": "retained_p9cp_review_of_p9co_read_only_fresh_remote_proofs",
        "source_p9co_baseline_target_plan_sha256": BASELINE_SHA,
        "source_p9co_candidate_target_plan_sha256": CANDIDATE_SHA,
        "final_owner_gate_name": "final_owner_live_order_gate_after_p9co",
        "final_owner_gate_may_discuss": [
            "whether to approve candidate entry into the executor target-plan path",
            "whether to approve replacing the baseline executor input with the retained candidate target-plan hash",
            "whether to submit one maker-only post-only canary order under exact risk terms",
        ],
        "final_owner_gate_may_not_skip": [
            "freshness evaluation for every required final-gate evidence row",
            "PIT-safe account permission decision from /fapi/v2/account.canTrade",
            "baseline/candidate same-risk target-plan binding",
            "distance_to_high_60-only contribution delta proof",
            "kill switch and rollback readback on the target runner",
            "explicit final owner approval naming candidate path, order terms, and rollback terms",
        ],
        "exact_canary_terms": {
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
        },
        "candidate_path_terms": {
            "candidate_may_enter_executor_target_plan_path_only_in_final_gate": True,
            "candidate_execution_may_be_authorized_only_in_final_gate": True,
            "target_plan_replacement_may_be_authorized_only_in_final_gate": True,
            "executor_input_mutation_may_be_authorized_only_in_final_gate": True,
            "must_bind_candidate_target_plan_hash": True,
            "must_preserve_same_timestamp_same_risk_inputs": True,
            "only_allowed_strategy_delta": "distance_to_high_60_contribution",
        },
        "rollback_conditions": [
            "any required final-gate evidence is missing, stale, or hash-mismatched",
            "/fapi/v2/account.canTrade is false or missing",
            "/fapi/v3/account.canTrade is used for permission decisions",
            "candidate target-plan hash differs from the final no-order approved hash",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "order book no longer supports maker-only post-only execution",
            "exchange filters reject the canary order terms",
            "open-order, fill, trade, balance, or position delta is unexplained",
        ],
        "out_of_scope_for_p9cq": [
            "fresh remote proof collection",
            "order-test endpoint calls",
            "actual order placement",
            "candidate execution",
            "actual target-plan replacement",
            "executor-input mutation",
            "timer or service mutation",
            "supervisor invocation",
            "remote execution",
        ],
    }


def _required_final_gate_evidence() -> dict[str, object]:
    evidence = [
        ("pit_safe_v2v3_account_proof", 60, "final_owner_live_order_gate_approval"),
        (
            "fresh_position_open_order_balance_fingerprints",
            60,
            "final_owner_live_order_gate_approval",
        ),
        ("fresh_order_trade_history_delta", 60, "final_owner_live_order_gate_approval"),
        ("fresh_order_book_and_exchange_filters", 10, "final_owner_live_order_gate_approval"),
        ("same_risk_paired_target_plan_binding", 60, "final_owner_live_order_gate_approval"),
        ("distance_to_high_60_only_delta", 60, "final_owner_live_order_gate_approval"),
        (
            "no_order_candidate_target_plan_replacement_dry_run",
            60,
            "final_owner_live_order_gate_approval",
        ),
        ("kill_switch_and_rollback_readback", 60, "final_owner_live_order_gate_approval"),
        ("final_owner_live_order_gate_approval", 300, "final_owner_live_order_gate_approval"),
        ("explicit_final_owner_live_order_decision", 300, "any_order_submission"),
        ("pre_order_control_boundary_readback", 60, "any_candidate_executor_path_entry"),
        ("post_order_observation_and_rollback_plan", 300, "any_order_submission"),
    ]
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_required_final_gate_evidence.v1",
        "scope_definition_only": True,
        "final_owner_gate_required_before_any_order_submission": True,
        "p9cq_satisfies_final_owner_live_order_gate": False,
        "fresh_remote_proof_collection_performed_in_p9cq": False,
        "evidence": [
            {
                "evidence_id": evidence_id,
                "max_age_seconds": max_age,
                "required_before": required_before,
                "must_be_retained": True,
            }
            for evidence_id, max_age, required_before in evidence
        ],
    }


def _p9cq_non_authorization() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_non_authorization.v1",
        "authorizations": {
            "define_final_owner_live_order_gate_scope": True,
            "prepare_future_p9cr_review_package": True,
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
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }


def _p9cq_control() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_control_boundary.v1",
        "scope": "final_owner_live_order_gate_scope_definition_only",
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


BASELINE_SHA = "f2c49b0f409b41eac06a4b104bfa707da06b4e9be6dc7c3a15ba809ababe3e14"
CANDIDATE_SHA = "c1bc8b82192ce26bfe3b13d493c4d7dd19e5bf10c1f29fbe6d0d64f71f4aa2f0"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
