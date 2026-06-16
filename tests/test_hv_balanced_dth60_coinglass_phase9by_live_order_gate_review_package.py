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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope_definition import (  # noqa: E402
    CONTRACT_VERSION as P9BX_CONTRACT,
    P9BY_GATE,
    P9BY_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9by_live_order_gate_review_package import (  # noqa: E402
    APPROVE_P9BY_DECISION,
    P9BZ_GATE,
    build_p9by_live_order_gate_review_package,
)


class Phase9BYLiveOrderGateReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9by-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_review_package_only_without_fresh_proofs_or_orders(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9by_live_order_gate_review_package(
            self._args(paths, output_root=self.temp_dir / "p9by"),
            now_fn=lambda: datetime(2026, 6, 10, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9by_live_order_gate_review_package_prepared"])
        self.assertTrue(summary["p9bx_sufficient_for_review_package"])
        self.assertTrue(summary["eligible_for_future_p9bz_package_review"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9by"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9BZ_GATE)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["required_fresh_proof_count"], 12)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        package = _load_json(Path(outputs["live_order_gate_review_package"]))
        canary = _load_json(Path(outputs["canary_order_terms"]))
        fresh_plan = _load_json(Path(outputs["fresh_proof_collection_plan"]))
        checklist = _load_json(Path(outputs["approval_checklist"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertFalse(package["fresh_proofs_collected_in_p9by"])
        self.assertFalse(canary["would_submit_order"])
        self.assertFalse(canary["market_orders_allowed"])
        self.assertEqual(canary["order_type"], "post_only_limit")
        self.assertEqual(len(fresh_plan["proofs"]), 12)
        self.assertEqual(
            {row["collection_status_in_p9by"] for row in fresh_plan["proofs"]},
            {"not_collected"},
        )
        self.assertTrue(all(item["required_for_live_order_gate"] for item in checklist["approval_items"]))
        self.assertTrue(all(not item["satisfied_in_p9by"] for item in checklist["approval_items"]))
        self.assertTrue(matrix["authorizations"]["prepare_live_order_gate_review_package"])
        self.assertFalse(matrix["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9bx_allowed_next_gate_is_not_p9by(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9BZ_skip_package_and_collect_proofs"}
        )

        summary, exit_code = build_p9by_live_order_gate_review_package(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 13, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bx_summary_ready_for_review_package", summary["blockers"])
        self.assertFalse(summary["p9by_live_order_gate_review_package_prepared"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_required_fresh_proofs_are_incomplete(self) -> None:
        paths = self._write_ready_inputs(
            proofs_overrides={"proofs": _required_proofs_payload()["proofs"][:-1]}
        )

        summary, exit_code = build_p9by_live_order_gate_review_package(
            self._args(paths, output_root=self.temp_dir / "missing-proof"),
            now_fn=lambda: datetime(2026, 6, 10, 13, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bx_required_fresh_proofs_ready", summary["blockers"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9by"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_live_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9by_live_order_gate_review_package(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_remote_proofs_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 13, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9by_package_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9by_live_order_gate_review_package_prepared"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BY_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bx_summary=str(paths["p9bx_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        proofs_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bx_root = self.temp_dir / "p9bx"
        proof_root = p9bx_root / "proof_artifacts" / "p9bx"
        p9bx_summary = p9bx_root / "summary.json"
        scope_path = proof_root / "live_order_gate_scope.json"
        proofs_path = proof_root / "required_fresh_proofs.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        proofs = _required_proofs_payload()
        proofs.update(proofs_overrides or {})
        summary = {
            "contract_version": P9BX_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bx_live_order_gate_scope_defined": True,
            "p9bw_sufficient_for_scope_definition": True,
            "eligible_for_future_live_order_gate_review_package": True,
            "eligible_for_future_live_order_submission": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "allowed_next_gate": P9BY_GATE,
            "allowed_next_gate_scope": P9BY_SCOPE,
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
            "changed_symbol_count": 1,
            "order_intent_preview_count": 1,
            "orders_submitted": 0,
            "fill_count": 0,
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "output_files": {
                "live_order_gate_scope": str(scope_path),
                "required_fresh_proofs": str(proofs_path),
                "non_authorization": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(scope_path, _scope_payload())
        _write_json(proofs_path, proofs)
        _write_json(matrix_path, _p9bx_matrix_payload())
        _write_json(control_path, _p9bx_control_payload())
        _write_json(p9bx_summary, summary)
        return {"project_profile": project_profile, "p9bx_summary": p9bx_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _scope_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope.v1",
        "scope_definition_only": True,
        "future_gate_name": "candidate_live_order_gate",
        "future_gate_may_discuss": [
            "single canary order submission under exact P9BU terms",
            "candidate target-plan replacement semantics if fresh no-order binding still passes",
            "post-order observation and rollback obligations",
        ],
        "future_gate_may_not_skip": [
            "fresh remote account read",
            "pre/post position fingerprint",
            "pre/post open-order fingerprint",
            "pre/post fill and trade fingerprint",
            "fresh order book",
            "exchange filters and post-only support",
            "final owner live-order gate approval",
        ],
        "canary_terms": {
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
        "rollback_conditions": [
            "any required fresh proof is missing, stale, or hash-mismatched",
            "candidate target-plan hash differs from no-order approved hash",
            "executor input is not explicitly bound to the candidate target-plan hash in the final gate",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "open-order, fill, trade, or position delta is unexplained",
            "order book no longer supports maker-only post-only execution",
            "supervisor, timer, operator, exchange, or provider health readback reports an exception",
            "kill switch readback is unavailable",
        ],
        "out_of_scope_for_p9bx": [
            "actual order placement",
            "candidate execution",
            "actual target-plan replacement",
            "executor-input mutation",
            "live config mutation",
            "operator-state mutation",
            "timer or service mutation",
            "supervisor invocation",
            "remote sync",
            "remote execution",
            "stage change",
        ],
    }


def _required_proofs_payload() -> dict[str, object]:
    proof_rows = [
        ("fresh_remote_account_read", 60),
        ("pre_position_fingerprint", 60),
        ("pre_open_order_fingerprint", 60),
        ("pre_fill_trade_fingerprint", 60),
        ("fresh_order_book", 10),
        ("exchange_filter_readback", 60),
        ("p9bu_terms_operator_acceptance", 300),
        ("candidate_target_plan_hash_binding", 60),
        ("baseline_candidate_plan_diff", 60),
        ("kill_switch_readback", 60),
        ("rollback_command_readback", 60),
        ("final_owner_live_order_gate_approval", 300),
    ]
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_required_fresh_proofs.v1",
        "scope_definition_only": True,
        "fresh_proofs_required_before_any_future_order_submission": True,
        "p9bx_satisfies_fresh_proofs": False,
        "proofs": [
            {
                "proof_id": proof_id,
                "max_age_seconds": max_age,
                "required_before": "future_live_order_gate_approval",
                "purpose": f"unit test {proof_id}",
            }
            for proof_id, max_age in proof_rows
        ],
    }


def _p9bx_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_non_authorization.v1",
        "authorizations": {
            "define_live_order_gate_scope": True,
            "prepare_future_live_order_gate_review_package": True,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }


def _p9bx_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_control_boundary.v1",
        "scope": "live_order_gate_scope_definition_only",
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
