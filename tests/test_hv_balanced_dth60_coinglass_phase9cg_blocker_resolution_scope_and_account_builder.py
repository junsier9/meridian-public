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
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
    build_pit_safe_account_proof,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CF_CONTRACT,
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
    P9CG_GATE,
    P9CG_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cg_define_live_order_readiness_blocker_resolution_scope import (  # noqa: E402
    APPROVE_P9CG_DECISION,
    CONTRACT_VERSION as P9CG_CONTRACT,
    P9CH_GATE,
    build_phase9cg,
)


class Phase9CGBlockerResolutionScopeAndAccountBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cg-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_builder_uses_v2_canTrade_and_ignores_v3_missing_canTrade(self) -> None:
        proof = build_pit_safe_account_proof(
            _fixture(can_trade_v2=True, can_trade_v3_marker=None),
            generated_at=datetime(2026, 6, 10, 21, 0, tzinfo=UTC),
        )

        self.assertEqual(proof["status"], "ready")
        self.assertTrue(proof["pit_safe_read_only_account_proof_ready"])
        self.assertTrue(proof["account_permission_source_corrected"])
        self.assertEqual(proof["can_trade_source"], CAN_TRADE_SOURCE)
        self.assertTrue(proof["can_trade_pre"])
        self.assertTrue(proof["can_trade_post"])
        self.assertFalse(proof["account_v3_has_canTrade_pre"])
        self.assertTrue(proof["account_v3_canTrade_ignored_for_permission_decision"])
        self.assertEqual(proof["live_order_readiness_blockers"], [])
        self.assertTrue(proof["eligible_to_clear_p9cf_account_can_trade_blocker"])
        self.assertEqual(
            proof["prior_p9ce_blocker_reclassification"],
            "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap",
        )
        self.assertEqual(proof["orders_submitted"], 0)
        self.assertEqual(proof["fill_count"], 0)

    def test_builder_splits_canTrade_false_from_missing(self) -> None:
        false_proof = build_pit_safe_account_proof(
            _fixture(can_trade_v2=False, can_trade_v3_marker=True),
            generated_at=datetime(2026, 6, 10, 21, 5, tzinfo=UTC),
        )
        missing_proof = build_pit_safe_account_proof(
            _fixture(can_trade_v2=_MISSING, can_trade_v3_marker=True),
            generated_at=datetime(2026, 6, 10, 21, 10, tzinfo=UTC),
        )

        self.assertEqual(false_proof["status"], "ready")
        self.assertEqual(
            false_proof["live_order_readiness_blockers"],
            [BLOCKER_CAN_TRADE_FALSE],
        )
        self.assertFalse(false_proof["eligible_to_clear_p9cf_account_can_trade_blocker"])
        self.assertEqual(
            false_proof["prior_p9ce_blocker_reclassification"],
            "account_side_permission_blocker",
        )

        self.assertEqual(missing_proof["status"], "ready")
        self.assertEqual(
            missing_proof["live_order_readiness_blockers"],
            [BLOCKER_CAN_TRADE_MISSING],
        )
        self.assertIsNone(missing_proof["can_trade_pre"])
        self.assertTrue(missing_proof["account_v3_has_canTrade_pre"])
        self.assertFalse(missing_proof["eligible_to_clear_p9cf_account_can_trade_blocker"])
        self.assertEqual(
            missing_proof["prior_p9ce_blocker_reclassification"],
            "account_v2_canTrade_missing_blocker",
        )

    def test_builder_blocks_on_non_read_only_side_effect_or_open_order_change(self) -> None:
        fixture = _fixture(can_trade_v2=True, can_trade_v3_marker=None)
        fixture["side_effects"]["order_test_calls"] = 1
        fixture["post_endpoint_results"]["open_orders"]["payload"] = [
            {"symbol": "BTCUSDT", "orderId": 123, "status": "NEW"}
        ]

        proof = build_pit_safe_account_proof(
            fixture,
            generated_at=datetime(2026, 6, 10, 21, 15, tzinfo=UTC),
        )

        self.assertEqual(proof["status"], "blocked")
        self.assertIn("post_snapshot_ready", proof["blockers"])
        self.assertIn("open_order_fingerprint_stable", proof["blockers"])
        self.assertIn("open_order_count_zero_pre_post", proof["blockers"])
        self.assertIn("side_effects_zero", proof["blockers"])
        self.assertFalse(proof["eligible_to_clear_p9cf_account_can_trade_blocker"])

    def test_p9cg_ready_defines_scope_only_and_builder_contract(self) -> None:
        paths = self._write_ready_p9cf_inputs()

        summary, exit_code = build_phase9cg(
            self._args(paths, output_root=self.temp_dir / "p9cg"),
            now_fn=lambda: datetime(2026, 6, 10, 21, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CG_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary["p9cg_live_order_readiness_blocker_resolution_scope_defined"]
        )
        self.assertTrue(summary["pit_safe_v2v3_account_proof_builder_defined"])
        self.assertEqual(summary["can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertEqual(
            summary["replacement_blockers"],
            [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE],
        )
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CH_GATE)

        scope = _load_json(Path(summary["output_files"]["blocker_resolution_scope"]))
        builder_contract = _load_json(
            Path(summary["output_files"]["pit_safe_account_proof_builder_contract"])
        )
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization"]))
        self.assertEqual(scope["can_trade_decision_source"], CAN_TRADE_SOURCE)
        self.assertTrue(
            scope["account_v3_canTrade_must_be_ignored_for_permission_decision"]
        )
        self.assertEqual(
            builder_contract["permission_field_contract"]["split_missing_blocker"],
            BLOCKER_CAN_TRADE_MISSING,
        )
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertFalse(control["order_test_endpoint_called"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(matrix["authorizations"]["pit_safe_account_proof_collection"])

    def test_p9cg_blocks_wrong_owner_or_unready_p9cf(self) -> None:
        paths = self._write_ready_p9cf_inputs(
            summary_overrides={"allowed_next_gate": "P9CH_skip_scope"}
        )

        summary, exit_code = build_phase9cg(
            self._args(paths, output_root=self.temp_dir / "bad-p9cf"),
            now_fn=lambda: datetime(2026, 6, 10, 21, 25, tzinfo=UTC),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9cf_summary_ready_for_blocker_resolution_scope", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

        paths = self._write_ready_p9cf_inputs()
        summary, exit_code = build_phase9cg(
            self._args(
                paths,
                output_root=self.temp_dir / "bad-owner",
                owner_decision="approve_live_orders",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 21, 30, tzinfo=UTC),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cg_scope_only_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CG_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cf_summary=str(paths["p9cf_summary"]),
            account_proof_builder=str(
                ROOT
                / "scripts/live_trading/hv_balanced_binance_usdm_pit_safe_account_proof_builder.py"
            ),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cf_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cf_summary = self.temp_dir / "p9cf" / "summary.json"
        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "project": "Meridian Alpha Platform",
            },
        )
        summary = {
            "contract_version": P9CF_CONTRACT,
            "run_id": "20260610T211500Z",
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
        summary.update(summary_overrides or {})
        _write_json(p9cf_summary, summary)
        return {
            "project_profile": project_profile,
            "p9cf_summary": p9cf_summary,
        }


class _Missing:
    pass


_MISSING = _Missing()


def _fixture(
    *,
    can_trade_v2: bool | _Missing,
    can_trade_v3_marker: bool | None,
) -> dict[str, object]:
    return {
        "expected_egress_ip": "203.0.113.10",
        "pre_egress_ip": "203.0.113.10",
        "post_egress_ip": "203.0.113.10",
        "pre_endpoint_results": _endpoint_results(can_trade_v2, can_trade_v3_marker),
        "post_endpoint_results": _endpoint_results(can_trade_v2, can_trade_v3_marker),
        "side_effects": {
            "http_methods_used": ["GET"],
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
            "fill_count": 0,
            "trade_count": 0,
        },
    }


def _endpoint_results(
    can_trade_v2: bool | _Missing,
    can_trade_v3_marker: bool | None,
) -> dict[str, object]:
    account_v2 = {
        "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
        "positions": [_position()],
    }
    if not isinstance(can_trade_v2, _Missing):
        account_v2["canTrade"] = can_trade_v2
    account_v3 = {
        "assets": [{"asset": "USDT", "walletBalance": "100", "crossWalletBalance": "100"}],
        "positions": [_position()],
    }
    if can_trade_v3_marker is not None:
        account_v3["canTrade"] = can_trade_v3_marker
    return {
        "account_v2": _endpoint(ACCOUNT_V2_ENDPOINT, account_v2),
        "account_v3": _endpoint(ACCOUNT_V3_ENDPOINT, account_v3),
        "account_config": _endpoint(
            ACCOUNT_CONFIG_ENDPOINT,
            {"feeTier": 0, "multiAssetsMargin": False, "tradeGroupId": -1},
        ),
        "position_mode": _endpoint(POSITION_MODE_ENDPOINT, {"dualSidePosition": False}),
        "open_orders": _endpoint(OPEN_ORDERS_ENDPOINT, []),
        "api_restrictions": _endpoint(
            API_RESTRICTIONS_ENDPOINT,
            {
                "ipRestrict": True,
                "enableFutures": True,
                "enableReading": True,
                "enableWithdrawals": False,
                "permitsUniversalTransfer": True,
            },
        ),
    }


def _position() -> dict[str, str]:
    return {
        "symbol": "BTCUSDT",
        "positionSide": "BOTH",
        "positionAmt": "0.01",
        "entryPrice": "60000",
        "breakEvenPrice": "60000",
        "isolated": "false",
        "isolatedWallet": "0",
    }


def _endpoint(path: str, payload: object) -> dict[str, object]:
    return {
        "path": path,
        "method": "GET",
        "status": "ok",
        "status_code": 200,
        "started_at_utc": "2026-06-10T21:00:00Z",
        "finished_at_utc": "2026-06-10T21:00:01Z",
        "payload": payload,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
