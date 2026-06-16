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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CF_CONTRACT,
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
    P9CG_GATE,
    P9CG_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cg_define_live_order_readiness_blocker_resolution_scope import (  # noqa: E402
    APPROVE_P9CG_DECISION,
    P9CH_GATE,
    P9CH_SCOPE,
    build_phase9cg,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ch_pit_safe_read_only_account_proof_owner_gate import (  # noqa: E402
    APPROVE_P9CH_DECISION,
    CONTRACT_VERSION as P9CH_CONTRACT,
    P9CI_GATE,
    build_phase9ch,
)


class Phase9CHPitSafeReadOnlyAccountProofOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ch-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_allows_future_p9ci_gate_but_does_not_collect_or_order(self) -> None:
        paths = self._write_ready_p9cg_inputs()

        summary, exit_code = build_phase9ch(
            self._args(paths, output_root=self.temp_dir / "p9ch"),
            now_fn=lambda: datetime(2026, 6, 10, 22, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CH_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9ch_pit_safe_read_only_account_proof_owner_gate_ready"])
        self.assertTrue(summary["p9cg_sufficient_for_p9ch_owner_gate"])
        self.assertTrue(summary["pit_safe_read_only_account_proof_owner_gate_approved_in_p9ch"])
        self.assertTrue(summary["eligible_for_future_p9ci_account_proof_execution_gate"])
        self.assertFalse(
            summary["eligible_for_future_pit_safe_account_proof_without_separate_request"]
        )
        self.assertFalse(summary["fresh_remote_proof_collection_execution_approved_in_p9ch"])
        self.assertFalse(summary["pit_safe_account_proof_collection_performed_in_p9ch"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["fresh_order_book_read_performed"])
        self.assertFalse(summary["exchange_filter_read_performed"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertEqual(
            summary["replacement_blockers"],
            [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE],
        )
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CI_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])

        outputs = summary["output_files"]
        owner = _load_json(Path(outputs["owner_decision_record"]))
        terms = _load_json(Path(outputs["account_proof_execution_gate_terms"]))
        future_contract = _load_json(Path(outputs["future_p9ci_acceptance_contract"]))
        matrix = _load_json(Path(outputs["non_authorization"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))

        self.assertTrue(owner["pit_safe_read_only_account_proof_owner_gate_approved"])
        self.assertFalse(owner["pit_safe_account_proof_collection_approved_in_p9ch"])
        self.assertEqual(terms["allowed_next_gate"], P9CI_GATE)
        self.assertTrue(terms["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(terms["pit_safe_read_only_account_proof_may_be_requested_next"])
        self.assertFalse(terms["pit_safe_account_proof_collection_performed_in_p9ch"])
        self.assertEqual(terms["can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertEqual(
            terms["replacement_blockers"],
            [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE],
        )
        self.assertTrue(
            future_contract["p9ci_must_fail_closed_unless"][
                "canTrade_decision_source_is_fapi_v2_account"
            ]
        )
        self.assertTrue(
            matrix["authorizations"]["allow_future_p9ci_account_proof_gate_request"]
        )
        self.assertFalse(
            matrix["authorizations"]["execute_pit_safe_read_only_account_proof_in_p9ch"]
        )
        self.assertFalse(matrix["authorizations"]["fresh_remote_account_read"])
        self.assertFalse(matrix["authorizations"]["order_test_endpoint"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["remote_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["order_test_endpoint_called"])
        self.assertFalse(control["fresh_proofs_collected"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_wrong_owner_decision_blocks_without_collection_or_order_authority(self) -> None:
        paths = self._write_ready_p9cg_inputs()

        summary, exit_code = build_phase9ch(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_collect_account_proof_now",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 22, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ch_owner_gate_recorded", summary["blockers"])
        self.assertFalse(summary["p9ch_pit_safe_read_only_account_proof_owner_gate_ready"])
        self.assertFalse(summary["pit_safe_account_proof_collection_performed_in_p9ch"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_when_p9cg_allowed_next_gate_is_not_p9ch(self) -> None:
        paths = self._write_ready_p9cg_inputs()
        p9cg = _load_json(paths["p9cg_summary"])
        p9cg["allowed_next_gate"] = "P9CI_skip_owner_gate_collect_now"
        _write_json(paths["p9cg_summary"], p9cg)

        summary, exit_code = build_phase9ch(
            self._args(paths, output_root=self.temp_dir / "wrong-next"),
            now_fn=lambda: datetime(2026, 6, 10, 22, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cg_summary_ready_for_p9ch_owner_gate", summary["blockers"])
        self.assertFalse(summary["pit_safe_read_only_account_proof_owner_gate_approved_in_p9ch"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_when_p9cg_builder_contract_or_scope_is_malformed(self) -> None:
        paths = self._write_ready_p9cg_inputs()
        p9cg = _load_json(paths["p9cg_summary"])
        builder_path = Path(p9cg["output_files"]["pit_safe_account_proof_builder_contract"])
        scope_path = Path(p9cg["output_files"]["blocker_resolution_scope"])
        builder = _load_json(builder_path)
        scope = _load_json(scope_path)
        builder["permission_field_contract"]["can_trade_source"] = "/fapi/v3/account.canTrade"
        scope["account_v3_canTrade_must_be_ignored_for_permission_decision"] = False
        _write_json(builder_path, builder)
        _write_json(scope_path, scope)

        summary, exit_code = build_phase9ch(
            self._args(paths, output_root=self.temp_dir / "bad-contract"),
            now_fn=lambda: datetime(2026, 6, 10, 22, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cg_builder_contract_ready", summary["blockers"])
        self.assertIn("p9cg_scope_definition_ready", summary["blockers"])
        self.assertFalse(summary["pit_safe_account_proof_collection_performed_in_p9ch"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CH_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cg_summary=str(paths["p9cg_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cg_inputs(self) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cf_summary = self.temp_dir / "p9cf" / "summary.json"
        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "project": "Meridian Alpha Platform",
            },
        )
        _write_json(p9cf_summary, _p9cf_summary_payload())
        p9cg_summary, exit_code = build_phase9cg(
            Namespace(
                output_root=str(self.temp_dir / "p9cg"),
                project_profile=str(project_profile),
                phase9cf_summary=str(p9cf_summary),
                account_proof_builder=str(
                    ROOT
                    / "scripts/live_trading/hv_balanced_binance_usdm_pit_safe_account_proof_builder.py"
                ),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CG_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 21, 55, tzinfo=UTC),
        )
        self.assertEqual(exit_code, 0)
        return {
            "project_profile": project_profile,
            "p9cg_summary": Path(p9cg_summary["output_files"]["summary"]),
        }


def _p9cf_summary_payload() -> dict[str, object]:
    return {
        "contract_version": P9CF_CONTRACT,
        "run_id": "20260610T215000Z",
        "status": "ready",
        "blockers": [],
        "p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready": True,
        "p9ce_sufficient_for_read_only_collection_review": True,
        "p9ce_sufficient_for_live_order_gate": False,
        "live_order_readiness_blockers": [LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE],
        "eligible_for_future_p9cg_live_order_readiness_blocker_scope_gate": True,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "fresh_remote_proof_collection_performed_in_p9cf": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_execution_authorized": False,
        "allowed_next_gate": P9CG_GATE,
        "allowed_next_gate_scope": P9CG_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
