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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bw_review_after_p9bv import (  # noqa: E402
    CONTRACT_VERSION as P9BW_CONTRACT,
    P9BX_GATE,
    P9BX_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope_definition import (  # noqa: E402
    APPROVE_P9BX_DECISION,
    P9BY_GATE,
    build_p9bx_live_order_gate_scope_definition,
)


class Phase9BXLiveOrderGateScopeDefinitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bx-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_scope_only_without_order_or_execution_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bx_live_order_gate_scope_definition(
            self._args(paths, output_root=self.temp_dir / "p9bx"),
            now_fn=lambda: datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9bx_live_order_gate_scope_defined"])
        self.assertTrue(summary["p9bw_sufficient_for_scope_definition"])
        self.assertTrue(summary["eligible_for_future_live_order_gate_review_package"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9BY_GATE)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["canary_side"], "BUY")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        outputs = summary["output_files"]
        scope = _load_json(Path(outputs["live_order_gate_scope"]))
        proofs = _load_json(Path(outputs["required_fresh_proofs"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        proof_ids = {item["proof_id"] for item in proofs["proofs"]}
        self.assertIn("fresh_remote_account_read", proof_ids)
        self.assertIn("pre_position_fingerprint", proof_ids)
        self.assertIn("fresh_order_book", proof_ids)
        self.assertIn("final_owner_live_order_gate_approval", proof_ids)
        self.assertEqual(scope["canary_terms"]["order_type"], "post_only_limit")
        self.assertFalse(scope["canary_terms"]["market_orders_allowed"])
        self.assertIn("actual order placement", scope["out_of_scope_for_p9bx"])
        self.assertTrue(matrix["authorizations"]["define_live_order_gate_scope"])
        self.assertTrue(matrix["authorizations"]["prepare_future_live_order_gate_review_package"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])

    def test_blocks_when_p9bw_allowed_next_gate_is_not_p9bx(self) -> None:
        paths = self._write_ready_inputs(
            summary_overrides={"allowed_next_gate": "P9BY_skip_scope_and_submit_order"}
        )

        summary, exit_code = build_p9bx_live_order_gate_scope_definition(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 10, 12, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bw_summary_ready_for_scope_definition", summary["blockers"])
        self.assertFalse(summary["p9bx_live_order_gate_scope_defined"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9bw_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_inputs(
            matrix_overrides={
                "authorizations": {
                    **_p9bw_matrix_payload()["authorizations"],
                    "define_p9bx_scope": True,
                }
            }
        )

        summary, exit_code = build_p9bx_live_order_gate_scope_definition(
            self._args(paths, output_root=self.temp_dir / "bad-matrix"),
            now_fn=lambda: datetime(2026, 6, 10, 12, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bw_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_wrong_owner_decision_blocks_without_live_order_authority(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_p9bx_live_order_gate_scope_definition(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 12, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bx_scope_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9bx_live_order_gate_scope_defined"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BX_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bw_summary=str(paths["p9bw_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
        matrix_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9bw_root = self.temp_dir / "p9bw"
        proof_root = p9bw_root / "proof_artifacts" / "p9bw"
        p9bw_summary = p9bw_root / "summary.json"
        matrix_path = proof_root / "non_authorization.json"
        control_path = proof_root / "control.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        matrix = _p9bw_matrix_payload()
        matrix.update(matrix_overrides or {})
        summary = {
            "contract_version": P9BW_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bw_review_after_p9bv_ready": True,
            "p9bv_retained_evidence_sufficient_for_live_order_gate_discussion": True,
            "eligible_for_future_live_order_gate_discussion": True,
            "eligible_for_future_live_order_submission": False,
            "live_order_gate_approved": False,
            "allowed_next_gate": P9BX_GATE,
            "allowed_next_gate_scope": P9BX_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "simulated_executor_input_replacement_matches_candidate": True,
            "actual_executor_input_changed": False,
            "actual_target_plan_replaced": False,
            "only_distance_to_high_60_contribution_changed": True,
            "changed_symbol_count": 1,
            "order_intent_preview_count": 1,
            "candidate_enter_executor_target_plan_path_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "baseline_target_plan_sha256": BASELINE_SHA,
            "candidate_target_plan_sha256": CANDIDATE_SHA,
            "output_files": {
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(summary_overrides or {})
        _write_json(matrix_path, matrix)
        _write_json(control_path, _p9bw_control_payload())
        _write_json(p9bw_summary, summary)
        return {"project_profile": project_profile, "p9bw_summary": p9bw_summary}


BASELINE_SHA = "2d8b09504d4ae5a776868924f301d137ec9746f0c1ecd53e64a9fc9261910712"
CANDIDATE_SHA = "fed5ddb1b3dbe5cb5e5a904ebb7ee379d71d1fb8f5f5ffcaa5e61dd33757a7c2"


def _p9bw_matrix_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_non_authorization_matrix.v1",
        "authorizations": {
            "review_p9bv_retained_evidence": True,
            "enter_live_order_gate_discussion": True,
            "define_p9bx_scope": False,
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


def _p9bw_control_payload() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_control_boundary_readback.v1",
        "scope": "retained_review_only",
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
