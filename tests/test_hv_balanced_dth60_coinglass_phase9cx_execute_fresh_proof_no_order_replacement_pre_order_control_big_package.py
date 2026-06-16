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
    CONTRACT_VERSION as P9CX_CONTRACT,
    P9CY_GATE,
    build_phase9cx,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (
    _p9cv_control,
    _p9cv_gap_matrix,
    _p9cv_non_authorization,
    _p9cv_sufficiency_review,
    _p9cv_summary,
)


class Phase9CXBigPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cx-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_executes_big_package_without_live_order_or_executor_authority(self) -> None:
        paths = self._write_ready_p9cw_inputs()
        fake_p9co = FakeP9COBuilder(self.temp_dir)

        summary, exit_code = build_phase9cx(
            self._args(paths, output_root=self.temp_dir / "p9cx"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 0, 0, tzinfo=UTC),
            command_runner=NoCommandRunner(),
            p9co_builder=fake_p9co,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CX_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(len(fake_p9co.calls), 1)
        self.assertEqual(fake_p9co.calls[0].owner_decision, APPROVE_P9CO_DECISION)
        self.assertTrue(
            summary[
                "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
            ]
        )
        self.assertTrue(summary["p9cw_sufficient_for_p9cx_big_package_execution"])
        self.assertTrue(summary["fresh_proof_collection_performed_in_p9cx"])
        self.assertTrue(summary["fresh_remote_account_read_performed"])
        self.assertTrue(summary["fresh_order_book_read_performed"])
        self.assertTrue(summary["exchange_filter_read_performed"])
        self.assertTrue(summary["read_only_fresh_proofs_ready"])
        self.assertTrue(summary["no_order_candidate_target_plan_replacement_dry_run_ready"])
        self.assertTrue(summary["candidate_target_plan_replacement_semantics_proven"])
        self.assertTrue(summary["same_risk_paired_target_plan_binding"])
        self.assertTrue(summary["only_distance_to_high_60_contribution_changed"])
        self.assertTrue(summary["pre_order_control_readback_ready"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["explicit_final_owner_live_order_decision_collected"])
        self.assertFalse(summary["p9cx_satisfies_final_owner_live_order_gate"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertEqual(summary["remote_files_written"], 0)
        self.assertFalse(summary["remote_sync_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CY_GATE)

        proof_bundle = _load_json(Path(summary["output_files"]["fresh_final_decision_proof_bundle"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        rows = {row["proof_id"]: row for row in proof_bundle["proof_rows"]}

        self.assertEqual(rows["pit_safe_v2v3_account_proof"]["status"], "ready")
        self.assertEqual(rows["pre_order_control_boundary_readback"]["status"], "ready")
        self.assertEqual(
            rows["final_owner_live_order_gate_approval"]["status"],
            "not_collected_by_design",
        )
        self.assertEqual(
            rows["explicit_final_owner_live_order_decision"]["status"],
            "not_collected_by_design",
        )
        self.assertTrue(control["fresh_remote_proof_collection_performed"])
        self.assertTrue(control["pre_order_control_readback_performed"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["executor_input_changed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["candidate_execution"])

    def test_wrong_owner_decision_blocks_before_embedded_p9co(self) -> None:
        paths = self._write_ready_p9cw_inputs()
        fake_p9co = FakeP9COBuilder(self.temp_dir)

        summary, exit_code = build_phase9cx(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 15, 5, 0, tzinfo=UTC),
            command_runner=NoCommandRunner(),
            p9co_builder=fake_p9co,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cx_big_package_execute_recorded", summary["blockers"])
        self.assertEqual(fake_p9co.calls, [])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_mutated_p9cw_scope_blocks_before_embedded_p9co(self) -> None:
        paths = self._write_ready_p9cw_inputs()
        p9cw = _load_json(paths["p9cw_summary"])
        scope_path = Path(p9cw["output_files"]["p9cx_big_package_scope"])
        scope = _load_json(scope_path)
        scope["p9cx_may_not_execute"].remove("actual executor-input mutation")
        _write_json(scope_path, scope)
        fake_p9co = FakeP9COBuilder(self.temp_dir)

        summary, exit_code = build_phase9cx(
            self._args(paths, output_root=self.temp_dir / "bad-scope"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 10, 0, tzinfo=UTC),
            command_runner=NoCommandRunner(),
            p9co_builder=fake_p9co,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cw_scope_ready", summary["blockers"])
        self.assertEqual(fake_p9co.calls, [])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocked_embedded_p9co_blocks_p9cx_but_preserves_no_order_boundary(self) -> None:
        paths = self._write_ready_p9cw_inputs()
        fake_p9co = FakeP9COBuilder(self.temp_dir, ready=False)

        summary, exit_code = build_phase9cx(
            self._args(paths, output_root=self.temp_dir / "blocked-p9co"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 15, 0, tzinfo=UTC),
            command_runner=NoCommandRunner(),
            p9co_builder=fake_p9co,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("embedded_p9co_read_only_fresh_proof_collection_failed", summary["blockers"])
        self.assertIn("embedded_p9co_summary_not_ready_for_p9cx", summary["blockers"])
        self.assertFalse(summary["read_only_fresh_proofs_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["trade_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CX_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cw_summary=str(paths["p9cw_summary"]),
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
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cw_inputs(self) -> dict[str, Path]:
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
        return {
            "project_profile": project_profile,
            "p9cw_summary": Path(p9cw_summary["output_files"]["summary"]),
        }


class FakeP9COBuilder:
    def __init__(self, temp_dir: Path, *, ready: bool = True) -> None:
        self.temp_dir = temp_dir
        self.ready = ready
        self.calls: list[Namespace] = []

    def __call__(
        self,
        args: Namespace,
        *,
        now_fn: Any,
        command_runner: Any,
    ) -> tuple[dict[str, Any], int]:
        self.calls.append(args)
        run_id = now_fn().strftime("%Y%m%dT%H%M%SZ")
        root = Path(args.output_root)
        proof_root = root / "proof_artifacts" / "p9co" / run_id
        files = {
            "summary": root / "summary.json",
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
            if key != "summary":
                _write_json(path, {"status": "ready", "proof": key})
        summary = _p9co_summary(run_id, files, ready=self.ready)
        _write_json(files["summary"], summary)
        return summary, 0 if self.ready else 2


class NoCommandRunner:
    def __call__(self, args: Any) -> CommandResult:
        raise AssertionError(f"unexpected command runner call: {args}")


def _p9co_summary(
    run_id: str,
    files: dict[str, Path],
    *,
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": P9CO_CONTRACT,
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "blockers": [] if ready else ["fake_p9co_blocked"],
        "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready": ready,
        "p9cn_sufficient_for_p9co_execution": ready,
        "fresh_remote_proof_collection_performed_in_p9co": ready,
        "pit_safe_v2v3_account_proof_ready": ready,
        "fresh_remote_account_read_performed": ready,
        "fresh_order_book_read_performed": ready,
        "exchange_filter_read_performed": ready,
        "order_test_endpoint_called": False,
        "remote_execution_performed": ready,
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "account_blocker_cleared_by_p9co": ready,
        "can_trade_pre": ready,
        "can_trade_post": ready,
        "position_fingerprint_stable": ready,
        "open_order_fingerprint_stable": ready,
        "balance_fingerprint_stable": ready,
        "open_order_count_zero_pre_post": ready,
        "order_cancel_fill_trade_delta_zero": ready,
        "remote_control_boundary_unchanged": ready,
        "same_risk_paired_target_plan_binding": ready,
        "distance_to_high_60_only_delta": ready,
        "no_order_candidate_target_plan_replacement_dry_run_ready": ready,
        "read_only_fresh_proofs_ready": ready,
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
        "only_distance_to_high_60_contribution_changed": ready,
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
