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

from scripts.live_trading.run_hv_balanced_12factor_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope import (  # noqa: E402
    P10L_GATE,
    P10L_SCOPE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10l_prepare_limited_live_delta_candidate_executor_path_discussion_proposal_package import (  # noqa: E402
    APPROVE_P10L_DECISION,
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_SYMBOL,
    DEFAULT_TIME_IN_FORCE,
    P10M_GATE,
    RESEARCH_SCORER_REQUIRED_FEATURES,
    build_p10l,
)


class HvBalanced12FactorP10lProposalPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10l-package-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_12factor_executor_path_discussion_package_only(self) -> None:
        paths = self._write_ready_p10k_bundle()

        summary, exit_code = build_p10l(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10l-ready"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package_ready"
            ]
        )
        self.assertTrue(summary["p10k_sufficient_for_p10l_proposal_package"])
        self.assertTrue(summary["proposal_package_only"])
        self.assertTrue(summary["discussion_proposal_only"])
        self.assertEqual(summary["research_scorer_required_feature_count"], 12)
        self.assertEqual(tuple(summary["research_scorer_required_features"]), RESEARCH_SCORER_REQUIRED_FEATURES)
        self.assertEqual(summary["symbol"], DEFAULT_SYMBOL)
        self.assertEqual(summary["max_notional_usdt"], DEFAULT_MAX_NOTIONAL_USDT)
        self.assertEqual(summary["max_gross_turnover_usdt"], DEFAULT_MAX_GROSS_TURNOVER_USDT)
        self.assertEqual(summary["order_type"], DEFAULT_ORDER_TYPE)
        self.assertEqual(summary["time_in_force"], DEFAULT_TIME_IN_FORCE)
        self.assertTrue(summary["candidate_plan_hash_binding_defined"])
        self.assertTrue(summary["executor_path_semantics_defined"])
        self.assertTrue(summary["baseline_fallback_defined"])
        self.assertTrue(summary["kill_switch_defined"])
        self.assertTrue(summary["post_run_reconciliation_defined"])
        self.assertEqual(summary["allowed_next_gate"], P10M_GATE)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        package = _load_json(Path(summary["output_files"]["proposal_package"]))
        terms = _load_json(Path(summary["output_files"]["risk_order_terms"]))
        scorer = _load_json(Path(summary["output_files"]["research_scorer_contract"]))
        hash_binding = _load_json(Path(summary["output_files"]["candidate_plan_hash_binding"]))
        semantics = _load_json(Path(summary["output_files"]["executor_path_semantics"]))
        fallback = _load_json(Path(summary["output_files"]["baseline_fallback_kill_switch"]))
        reconciliation = _load_json(Path(summary["output_files"]["post_run_reconciliation"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertEqual(package["proposal_status"], "prepared_for_future_review_only")
        self.assertFalse(package["p10l_authorizes_execution"])
        self.assertFalse(package["p10l_authorizes_live_order"])
        self.assertEqual(terms["candidate_delta_source"], "12factor_scorer_candidate_target_plan")
        self.assertEqual(terms["symbol"], "BTCUSDT")
        self.assertEqual(terms["max_orders_total"], 2)
        self.assertFalse(terms["market_orders_allowed"])
        self.assertEqual(scorer["required_feature_count"], 12)
        self.assertIn("settlement_cycle_premium_60d", scorer["required_feature_columns"])
        self.assertIn(
            "per_factor_values_sha256",
            hash_binding["required_hashes_before_future_execution"],
        )
        self.assertTrue(hash_binding["same_context_requirements"]["all_12_factor_inputs_match_research_contract"])
        self.assertTrue(
            hash_binding["same_context_requirements"][
                "p9_distance_to_high_60_only_delta_rule_not_sufficient_for_p10"
            ]
        )
        self.assertFalse(semantics["p10l_replaces_target_plan"])
        self.assertFalse(semantics["p10l_mutates_executor_input"])
        self.assertTrue(fallback["kill_switch"]["required"])
        self.assertIn(
            "keep executor input baseline-only",
            fallback["baseline_fallback_policy"]["fallback_action_before_submit"],
        )
        self.assertEqual(
            reconciliation["acceptance_conditions_for_future_execution_gate"][
                "completed_cycles_exactly"
            ],
            1,
        )
        self.assertTrue(non_auth["authorizations"]["future_p10m_review_request_allowed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p10l"])
        self.assertFalse(non_auth["authorizations"]["candidate_executor_path_execution_in_p10l"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_blocks_if_p10k_scope_allows_candidate_executor_path_execution(self) -> None:
        paths = self._write_ready_p10k_bundle()
        p10k = _load_json(paths["p10k_summary"])
        scope_path = Path(p10k["output_files"]["discussion_scope"])
        scope = _load_json(scope_path)
        scope["not_authorized_by_this_scope"].remove("candidate executor-path execution")
        _write_json(scope_path, scope)

        summary, exit_code = build_p10l(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10l-blocked"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10k_discussion_scope_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_authorizing_execution(self) -> None:
        paths = self._write_ready_p10k_bundle()

        summary, exit_code = build_p10l(
            self._args(
                paths,
                output_root=self.temp_dir / "proof_artifacts" / "p10l-wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 22, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p10l_proposal_package_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P10L_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            p10k_summary=str(paths["p10k_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
            symbol=DEFAULT_SYMBOL,
            max_notional_usdt=DEFAULT_MAX_NOTIONAL_USDT,
            max_gross_turnover_usdt=DEFAULT_MAX_GROSS_TURNOVER_USDT,
            max_candidate_entry_orders=1,
            max_reduce_only_rollback_orders=1,
            order_type=DEFAULT_ORDER_TYPE,
            time_in_force=DEFAULT_TIME_IN_FORCE,
        )

    def _write_ready_p10k_bundle(self) -> dict[str, Path]:
        root = self.temp_dir / "p10k"
        proof = root / "proof"
        project_profile = self.temp_dir / "project_profile.json"
        p10k_summary = root / "summary.json"
        scope = proof / "discussion_scope.json"
        non_auth = proof / "non_authorization.json"
        control = proof / "control_boundary_readback.json"

        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            scope,
            {
                "contract_version": "hv_balanced_12factor_p10k_limited_live_delta_candidate_executor_path_discussion_scope.v1",
                "scope_only": True,
                "scope_label": "limited_live_delta_candidate_executor_path_discussion_after_p10i",
                "must_define_before_any_future_execution_gate": [
                    "explicit owner approval for a specific execution-path canary",
                    "candidate plan hash must bind to retained P10G or a fresh rerun",
                    "executor input replacement must be exact, reversible, and one-cycle only",
                    "baseline fallback must trigger on any stale, missing, or mismatched proof",
                    "kill switch must force baseline-only with zero candidate orders",
                    "fresh remote account proof must use /fapi/v2/account.canTrade",
                    "pre/post position, open-order, fill, trade, and order-history fingerprints must be stable except the allowed bounded order/cancel delta",
                    "post-run open orders must be zero",
                    "no continuous automation, no timer/supervisor load, and no config/operator/timer mutation unless a later gate explicitly authorizes it",
                ],
                "hard_limits_for_discussion": {
                    "max_cycles": 1,
                    "max_symbols": 1,
                    "continuous_automated_order_flow": False,
                    "default_order_state": "disabled_until_separate_execution_gate",
                    "default_timer_path_state": "not_loaded",
                    "default_supervisor_invocation": "not_invoked",
                    "default_candidate_execution": "not_executed",
                    "default_target_plan_replacement": "not_replaced",
                    "default_executor_input_mutation": "not_mutated",
                    "default_remote_sync": "not_performed",
                    "default_remote_file_write": 0,
                    "must_remain_stage_3_human_approved_execution": True,
                },
                "not_authorized_by_this_scope": [
                    "live order submission",
                    "candidate executor-path execution",
                    "actual target-plan replacement",
                    "executor input mutation",
                    "timer path load",
                    "supervisor invocation",
                    "remote sync",
                    "remote file write",
                    "continuous automated order flow",
                    "stage governance change",
                ],
                "allowed_next_gate": P10L_GATE,
                "allowed_next_gate_scope": P10L_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
            },
        )
        _write_json(
            non_auth,
            {
                "contract_version": "hv_balanced_12factor_p10k_non_authorization.v1",
                "authorizations": {
                    "define_discussion_scope": True,
                    "future_p10l_proposal_package_request_allowed": True,
                    "live_order_submission_in_p10k": False,
                    "candidate_executor_path_execution_in_p10k": False,
                    "candidate_target_plan_replacement_in_p10k": False,
                    "executor_input_mutation_in_p10k": False,
                    "timer_path_load_in_p10k": False,
                    "supervisor_invocation_in_p10k": False,
                    "remote_execution_in_p10k": False,
                    "remote_sync_in_p10k": False,
                    "remote_file_write_in_p10k": False,
                    "continuous_automated_order_flow": False,
                    "stage_governance_change": False,
                },
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_12factor_p10k_control_boundary.v1",
                "scope": "scope_definition_only",
                "ssh_invoked": False,
                "remote_network_connection_performed": False,
                "fresh_remote_account_read_performed": False,
                "fresh_order_book_read_performed": False,
                "exchange_filter_read_performed": False,
                "order_test_endpoint_called": False,
                "live_order_submission_performed": False,
                "candidate_execution_performed": False,
                "target_plan_replaced": False,
                "executor_input_changed": False,
                "entered_timer_path": False,
                "ran_supervisor": False,
                "timer_path_loaded": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
            },
        )
        _write_json(
            p10k_summary,
            {
                "contract_version": "hv_balanced_12factor_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope.v1",
                "status": "ready",
                "blockers": [],
                "p10k_limited_live_delta_candidate_executor_path_discussion_scope_ready": True,
                "p10j_sufficient_for_p10k_scope_definition": True,
                "scope_definition_only": True,
                "scope_label": "limited_live_delta_candidate_executor_path_discussion_after_p10i",
                "allowed_scope_after_p10k": "proposal_package_preparation_only",
                "eligible_for_future_p10l_proposal_package_gate": True,
                "max_cycles_discussion_scope": 1,
                "max_symbols_discussion_scope": 1,
                "default_order_state": "disabled_until_separate_execution_gate",
                "continuous_automated_order_flow_allowed": False,
                "live_order_submission_authorized": False,
                "candidate_executor_path_execution_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "remote_execution_performed": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
                "allowed_next_gate": P10L_GATE,
                "allowed_next_gate_scope": P10L_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "discussion_scope": str(scope),
                    "non_authorization": str(non_auth),
                    "control_boundary_readback": str(control),
                },
            },
        )
        return {"project_profile": project_profile, "p10k_summary": p10k_summary}


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
