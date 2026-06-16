from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest


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
    build_phase9cy,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision_gate import (
    APPROVE_P9CZ_DECISION,
    CONTRACT_VERSION as P9CZ_CONTRACT,
    P9DA_GATE,
    build_phase9cz,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (
    _p9cv_control,
    _p9cv_gap_matrix,
    _p9cv_non_authorization,
    _p9cv_sufficiency_review,
    _p9cv_summary,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package import (
    FakeP9COBuilderWithCommands,
    NoCommandRunner,
)


class Phase9CZFinalOwnerLiveOrderDecisionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cz-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_collects_final_decision_but_submits_zero_orders(self) -> None:
        paths = self._write_ready_p9cy_inputs()

        summary, exit_code = build_phase9cz(
            self._args(paths, output_root=self.temp_dir / "p9cz"),
            now_fn=lambda: datetime(2026, 6, 8, 17, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CZ_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cz_final_owner_live_order_decision_gate_ready"])
        self.assertTrue(summary["final_owner_live_order_gate_approval_collected"])
        self.assertTrue(summary["explicit_final_owner_live_order_decision_collected"])
        self.assertTrue(summary["p9cz_satisfies_final_owner_live_order_decision_gate"])
        self.assertTrue(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertTrue(summary["target_plan_replacement_authorized"])
        self.assertTrue(summary["candidate_execution_authorized"])
        self.assertTrue(summary["live_order_submission_authorized"])
        self.assertEqual(summary["authorization_scope"], "future_p9da_single_post_only_canary_only")
        self.assertFalse(summary["actual_candidate_executor_target_path_entry_performed"])
        self.assertFalse(summary["actual_target_plan_replacement_performed"])
        self.assertFalse(summary["actual_executor_input_mutation_performed"])
        self.assertFalse(summary["actual_candidate_execution_performed"])
        self.assertFalse(summary["actual_live_order_submission_performed"])
        self.assertTrue(summary["fresh_pre_submit_readback_required_before_p9da"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["remote_files_written"], 0)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["canary_side"], "BUY")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")
        self.assertEqual(summary["allowed_next_gate"], P9DA_GATE)

        decision = _load_json(Path(summary["output_files"]["final_owner_live_order_decision"]))
        terms = _load_json(Path(summary["output_files"]["approved_single_canary_terms"]))
        pre_submit = _load_json(Path(summary["output_files"]["pre_submit_requirements_for_p9da"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertEqual(decision["decision_status"], "approved")
        self.assertTrue(decision["live_order_submission_authorized_for_future_single_canary"])
        self.assertFalse(decision["actual_order_submission_performed"])
        self.assertTrue(terms["post_only_required"])
        self.assertTrue(terms["maker_only_required"])
        self.assertTrue(pre_submit["cancel_if_not_maker_or_unexpected_delta"])
        self.assertTrue(non_auth["authorizations"]["future_p9da_single_post_only_canary_request_allowed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p9cz"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["executor_input_changed"])

    def test_blocks_when_p9cy_does_not_allow_p9cz(self) -> None:
        paths = self._write_ready_p9cy_inputs()
        p9cy = _load_json(paths["p9cy_summary"])
        p9cy["allowed_next_gate"] = "P9DA_skip_p9cz"
        _write_json(paths["p9cy_summary"], p9cy)

        summary, exit_code = build_phase9cz(
            self._args(paths, output_root=self.temp_dir / "bad-next"),
            now_fn=lambda: datetime(2026, 6, 8, 17, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cy_summary_ready_for_p9cz", summary["blockers"])
        self.assertFalse(summary["p9cz_final_owner_live_order_decision_gate_ready"])
        self.assertFalse(summary["actual_live_order_submission_performed"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_actual_order(self) -> None:
        paths = self._write_ready_p9cy_inputs()

        summary, exit_code = build_phase9cz(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_unbounded_live_order",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 17, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cz_final_live_order_decision_recorded", summary["blockers"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_if_p9cy_control_claims_remote_execution(self) -> None:
        paths = self._write_ready_p9cy_inputs()
        p9cy = _load_json(paths["p9cy_summary"])
        control_path = Path(p9cy["output_files"]["control_boundary_readback"])
        control = _load_json(control_path)
        control["remote_execution_performed"] = True
        _write_json(control_path, control)

        summary, exit_code = build_phase9cz(
            self._args(paths, output_root=self.temp_dir / "bad-control"),
            now_fn=lambda: datetime(2026, 6, 8, 17, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cy_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["actual_live_order_submission_performed"])
        self.assertFalse(summary["actual_executor_input_mutation_performed"])
        self.assertEqual(summary["trade_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CZ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cy_summary=str(paths["p9cy_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cy_inputs(self) -> dict[str, Path]:
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
                remote_host="root@203.0.113.10",
                remote_repo="/root/meridian_alpha_live_runner/repo",
                remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
                remote_live_env="/root/meridian_alpha_live_runner/.env",
                remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
                expected_egress_ip="203.0.113.10",
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
        p9cy_summary, p9cy_exit_code = build_phase9cy(
            Namespace(
                output_root=str(self.temp_dir / "p9cy"),
                project_profile=str(project_profile),
                phase9cx_summary=str(p9cx_summary["output_files"]["summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CY_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(p9cy_exit_code, 0)
        return {
            "project_profile": project_profile,
            "p9cy_summary": Path(p9cy_summary["output_files"]["summary"]),
        }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
