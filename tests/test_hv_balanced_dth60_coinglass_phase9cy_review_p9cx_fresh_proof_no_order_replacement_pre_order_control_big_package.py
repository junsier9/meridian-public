from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from typing import Any


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    CommandResult,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection import (
    APPROVE_P9CO_DECISION,
    CONTRACT_VERSION as P9CO_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (
    APPROVE_P9CW_DECISION,
    build_phase9cw,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cx_execute_fresh_proof_no_order_replacement_pre_order_control_big_package import (
    APPROVE_P9CX_DECISION,
    build_phase9cx,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package import (
    APPROVE_P9CY_DECISION,
    CONTRACT_VERSION as P9CY_CONTRACT,
    P9CZ_GATE,
    build_phase9cy,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (
    _p9cv_control,
    _p9cv_gap_matrix,
    _p9cv_non_authorization,
    _p9cv_sufficiency_review,
    _p9cv_summary,
)


class Phase9CYReviewP9CXBigPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cy-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9cx_for_final_decision_discussion_only(self) -> None:
        paths = self._write_ready_p9cx_inputs()

        summary, exit_code = build_phase9cy(
            self._args(paths, output_root=self.temp_dir / "p9cy"),
            now_fn=lambda: datetime(2026, 6, 8, 16, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CY_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
            ]
        )
        self.assertTrue(summary["p9cx_retained_evidence_sufficient_for_p9cy_review"])
        self.assertTrue(
            summary[
                "p9cx_big_package_sufficient_for_final_live_order_decision_discussion"
            ]
        )
        self.assertFalse(summary["p9cx_big_package_sufficient_for_live_order_submission"])
        self.assertFalse(summary["p9cx_satisfies_final_owner_live_order_gate"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["explicit_final_owner_live_order_decision_collected"])
        self.assertEqual(summary["fresh_final_decision_evidence_total_count"], 12)
        self.assertEqual(summary["fresh_final_decision_evidence_read_only_or_plan_ready_count"], 10)
        self.assertEqual(summary["fresh_final_decision_evidence_not_collected_by_design_count"], 2)
        self.assertEqual(
            set(summary["remaining_gap_ids_before_final_live_order_decision"]),
            {"final_owner_live_order_gate_approval", "explicit_final_owner_live_order_decision"},
        )
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertEqual(summary["remote_files_written"], 0)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CZ_GATE)

        review = _load_json(Path(summary["output_files"]["p9cx_sufficiency_review"]))
        gap = _load_json(Path(summary["output_files"]["final_decision_gap_matrix"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertTrue(review["review_only"])
        self.assertTrue(review["p9cx_big_package_sufficient_for_final_live_order_decision_discussion"])
        self.assertFalse(review["p9cx_big_package_sufficient_for_live_order_submission"])
        self.assertEqual(gap["remaining_gap_count"], 2)
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["actual_executor_input_mutation"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["executor_input_changed"])

    def test_blocks_when_p9cx_does_not_allow_p9cy(self) -> None:
        paths = self._write_ready_p9cx_inputs()
        p9cx = _load_json(paths["p9cx_summary"])
        p9cx["allowed_next_gate"] = "P9CZ_skip_p9cy_review"
        _write_json(paths["p9cx_summary"], p9cx)

        summary, exit_code = build_phase9cy(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 16, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cx_summary_ready_for_p9cy_review", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_if_p9cx_proof_bundle_claims_final_approval_collected(self) -> None:
        paths = self._write_ready_p9cx_inputs()
        p9cx = _load_json(paths["p9cx_summary"])
        proof_path = Path(p9cx["output_files"]["fresh_final_decision_proof_bundle"])
        proof = _load_json(proof_path)
        proof["final_owner_live_order_gate_approval_collected"] = True
        proof["proof_rows"][8]["status"] = "ready"
        _write_json(proof_path, proof)

        summary, exit_code = build_phase9cy(
            self._args(paths, output_root=self.temp_dir / "bad-proof"),
            now_fn=lambda: datetime(2026, 6, 8, 16, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cx_proof_bundle_ready", summary["blockers"])
        self.assertFalse(summary["p9cx_big_package_sufficient_for_live_order_submission"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_live_authority(self) -> None:
        paths = self._write_ready_p9cx_inputs()

        summary, exit_code = build_phase9cy(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cy_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["trade_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CY_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cx_summary=str(paths["p9cx_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cx_inputs(self) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cv_root = self.temp_dir / "p9cv"
        p9cv_proof_root = p9cv_root / "proof_artifacts" / "p9cv" / "run"
        p9cv_paths = {
            "project_profile": project_profile,
            "p9cv_summary": p9cv_root / "summary.json",
            "sufficiency_review": p9cv_proof_root / "p9cu_sufficiency_review.json",
            "gap_matrix": p9cv_proof_root / "final_decision_gap_matrix.json",
            "non_authorization": p9cv_proof_root / "non_authorization.json",
            "control": p9cv_proof_root / "control_boundary_readback.json",
        }
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(p9cv_paths["sufficiency_review"], _p9cv_sufficiency_review())
        _write_json(p9cv_paths["gap_matrix"], _p9cv_gap_matrix())
        _write_json(p9cv_paths["non_authorization"], _p9cv_non_authorization())
        _write_json(p9cv_paths["control"], _p9cv_control())
        _write_json(p9cv_paths["p9cv_summary"], _p9cv_summary(p9cv_paths))

        p9cw_summary, p9cw_exit_code = build_phase9cw(
            Namespace(
                output_root=str(self.temp_dir / "p9cw"),
                project_profile=str(project_profile),
                phase9cv_summary=str(p9cv_paths["p9cv_summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CW_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 14, 30, 0, tzinfo=UTC),
        )
        self.assertEqual(p9cw_exit_code, 0)
        p9cx_summary, p9cx_exit_code = build_phase9cx(
            Namespace(
                output_root=str(self.temp_dir / "p9cx"),
                project_profile=str(project_profile),
                phase9cw_summary=str(p9cw_summary["output_files"]["summary"]),
                phase9cn_summary="",
                phase9bu_summary="",
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
                owner_decision=APPROVE_P9CX_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 15, 0, 0, tzinfo=UTC),
            command_runner=NoCommandRunner(),
            p9co_builder=FakeP9COBuilderWithCommands(),
        )
        self.assertEqual(p9cx_exit_code, 0)
        return {
            "project_profile": project_profile,
            "p9cx_summary": Path(p9cx_summary["output_files"]["summary"]),
        }


class FakeP9COBuilderWithCommands:
    def __call__(
        self,
        args: Namespace,
        *,
        now_fn: Any,
        command_runner: Any,
    ) -> tuple[dict[str, Any], int]:
        run_id = now_fn().strftime("%Y%m%dT%H%M%SZ")
        root = Path(args.output_root)
        proof_root = root / "proof_artifacts" / "p9co" / run_id
        files = {
            "summary": root / "summary.json",
            "command_records": root / "command_records.json",
            "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
            "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
            "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
            "market_proof_collection_delta_acceptance": proof_root / "market_proof_collection_delta_acceptance.json",
            "fresh_order_book": proof_root / "fresh_order_book.json",
            "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
            "no_order_candidate_target_plan_replacement_dry_run_summary": proof_root / "no_order_candidate_target_plan_replacement_dry_run_summary.json",
            "kill_switch_rollback_readback": proof_root / "kill_switch_rollback_readback.json",
        }
        for key, path in files.items():
            if key not in {"summary", "command_records"}:
                _write_json(path, {"status": "ready", "proof": key})
        _write_json(files["command_records"], {"commands": _command_records()})
        summary = _p9co_summary(run_id, files)
        _write_json(files["summary"], summary)
        return summary, 0


class NoCommandRunner:
    def __call__(self, args: Any) -> CommandResult:
        raise AssertionError(f"unexpected command runner call: {args}")


def _command_records() -> list[dict[str, Any]]:
    labels = [
        "pre_control_snapshot",
        "remote_stdout_pit_safe_v2v3_account_collector",
        "remote_stdout_market_and_fingerprint_collector",
        "post_control_snapshot",
    ]
    return [
        {
            "label": label,
            "args": ["ssh", "root@203.0.113.10", f"readonly-{label}"],
            "returncode": 0,
            "stdout_sha256": f"{label}-sha",
            "stdout_bytes": 100,
            "stderr_tail": "",
        }
        for label in labels
    ]


def _p9co_summary(run_id: str, files: dict[str, Path]) -> dict[str, Any]:
    return {
        "contract_version": P9CO_CONTRACT,
        "run_id": run_id,
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
        "account_blocker_cleared_by_p9co": True,
        "can_trade_pre": True,
        "can_trade_post": True,
        "position_fingerprint_stable": True,
        "open_order_fingerprint_stable": True,
        "balance_fingerprint_stable": True,
        "open_order_count_zero_pre_post": True,
        "order_cancel_fill_trade_delta_zero": True,
        "remote_control_boundary_unchanged": True,
        "same_risk_paired_target_plan_binding": True,
        "distance_to_high_60_only_delta": True,
        "no_order_candidate_target_plan_replacement_dry_run_ready": True,
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
        "baseline_target_plan_sha256": "baseline-p9co-sha",
        "candidate_target_plan_sha256": "candidate-p9co-sha",
        "only_distance_to_high_60_contribution_changed": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "output_files": {key: str(path) for key, path in files.items()},
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
