from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    P9AC_GATE,
    p9aa_ready,
    p9ab_ready,
    preflight_ready,
    snapshot_boundary_ok,
)


class Phase9ACRemoteRunnerP9AAReadbackTests(unittest.TestCase):
    def test_contract_predicates_accept_ready_remote_no_order_bundle(self) -> None:
        self.assertTrue(p9ab_ready(_p9ab()))
        self.assertTrue(preflight_ready(_preflight()))
        self.assertTrue(p9aa_ready(_p9aa()))
        self.assertTrue(snapshot_boundary_ok(_snapshot(), _snapshot()))

    def test_snapshot_boundary_rejects_operator_or_timer_change(self) -> None:
        changed_operator = _snapshot()
        changed_operator["operator_state"]["live_delta_armed"]["value"] = "false"
        self.assertFalse(snapshot_boundary_ok(_snapshot(), changed_operator))

        changed_timer = _snapshot()
        changed_timer["systemd_units"]["meridian-alpha-mainnet-supervisor-live.timer"]["UnitFileState"] = "disabled"
        self.assertFalse(snapshot_boundary_ok(_snapshot(), changed_timer))

    def test_p9aa_ready_rejects_candidate_execution_or_orders(self) -> None:
        bad = _p9aa()
        bad["orders_submitted"] = 1
        self.assertFalse(p9aa_ready(bad))
        bad = _p9aa()
        bad["candidate_execution_enabled"] = True
        self.assertFalse(p9aa_ready(bad))
        bad = _p9aa()
        bad["completed_shadow_cycles"] = 0
        self.assertFalse(p9aa_ready(bad))


def _p9ab() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate.v1",
        "status": "ready",
        "blockers": [],
        "p9ab_remote_p9aa_owner_gate_ready": True,
        "eligible_for_p9ac_remote_runner_no_order_p9aa": True,
        "allowed_next_gate": P9AC_GATE,
        "future_p9ac_remote_sync_authorized": True,
        "future_p9ac_remote_execution_authorized": True,
        "future_p9ac_fresh_remote_account_read_proof_required": True,
        "future_p9ac_consecutive_cycles_required": 3,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "production_timer_service_load_authorized": False,
        "owner_decision": {"decision": "approve_p9ab_remote_runner_no_order_p9aa_owner_gate_only"},
        "gates": {
            "p9aa_blocked_fail_closed_due_local_account_read": True,
            "future_fresh_remote_account_read_proof_required": True,
            "future_p9ac_must_keep_executor_baseline_only": True,
            "future_p9ac_must_keep_candidate_shadow_only": True,
            "future_p9ac_must_keep_orders_and_fills_zero": True,
            "future_p9ac_must_not_load_production_timer_service": True,
        },
    }


def _preflight() -> dict[str, object]:
    return {
        "status": "passed_read_only_account_probe",
        "blockers": [],
        "account_readable": True,
        "can_trade": True,
        "position_mode": "one_way",
        "open_order_count": 0,
        "open_position_count": 0,
        "side_effects": {"orders_submitted": 0, "orders_canceled": 0, "only_http_get_endpoints": True},
    }


def _p9aa() -> dict[str, object]:
    true_gates = {
        "all_cycles_ready",
        "all_executor_baseline_only",
        "all_candidate_artifacts_shadow_only",
        "all_candidate_plan_not_referenced_by_executor",
        "no_candidate_execution",
        "no_live_order_submission",
        "no_target_plan_replacement",
        "no_executor_input_mutation",
        "no_production_timer_service_mutation",
    }
    return {
        "status": "ready",
        "blockers": [],
        "timer_path_shadow_cycles_ready": True,
        "completed_shadow_cycles": 3,
        "fresh_proof_each_cycle": True,
        "same_risk_no_order_config_each_cycle": True,
        "timer_path_supervisor_entrypoint_invoked": True,
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "candidate_execution_enabled": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "live_config_changed": False,
        "operator_state_changed_outside_generated_p9aa_state": False,
        "timer_state_changed": False,
        "gates": {key: True for key in true_gates},
    }


def _snapshot() -> dict[str, object]:
    return {
        "remote_live_config_sha256": "cfg",
        "live_supervisor_sha256": "sup",
        "operator_state": {
            "live_delta_armed": {"value": "true", "updated_at_utc": "2026-06-07T00:00:00Z"},
            "paused": {"value": "false", "updated_at_utc": "2026-06-07T00:00:00Z"},
        },
        "systemd_units": {
            "meridian-alpha-mainnet-supervisor-live.timer": {
                "LoadState": "loaded",
                "UnitFileState": "enabled",
                "ActiveState": "active",
                "SubState": "waiting",
                "FragmentPath": "/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.timer",
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
