from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9AB_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    CONTRACT_VERSION as P9AC_CONTRACT,
    preflight_ready,
    snapshot_boundary_ok,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ad_nonflat_no_order_readback_contract.v1"
APPROVE_P9AD_DECISION = "approve_p9ad_define_nonflat_no_order_readback_contract_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ad_nonflat_no_order_contract"
PHASE9AB_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ab_remote_p9aa_owner_gate"
PHASE9AC_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ac_remote_runner_p9aa_readback"
P9AE_GATE = "P9AE_nonflat_remote_runner_no_order_p9aa_readback_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9AD defines the owner-gated non-flat account no-order readback "
            "contract after P9AC blocked on existing positions. It writes "
            "proof artifacts only; it does not SSH, sync files, invoke the "
            "supervisor, load timers, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ab-summary", default="")
    parser.add_argument("--phase9ac-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AD_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:define_nonflat_no_order_readback_contract")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AD_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ad_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_nonflat_account_no_order_readback_contract_only",
        "decision_effect": "define_p9ae_nonflat_no_order_readback_contract" if approved else "none",
        "p9ad_contract_definition_approved": approved,
        "p9ae_execution_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def p9ab_ready_for_p9ad(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9AB_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ab_remote_p9aa_owner_gate_ready") is True
        and summary.get("eligible_for_p9ac_remote_runner_no_order_p9aa") is True
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
    )


def side_effects_zero(preflight: dict[str, Any]) -> bool:
    side_effects = dict(preflight.get("side_effects") or {})
    return (
        side_effects.get("orders_submitted") == 0
        and side_effects.get("orders_canceled") == 0
        and side_effects.get("order_test_calls", 0) == 0
        and side_effects.get("only_http_get_endpoints") is True
    )


def p9ac_blocked_on_nonflat_account(summary: dict[str, Any]) -> bool:
    blockers = set(str(item) for item in summary.get("blockers") or [])
    preflight = load_optional(resolve_path(dict(summary.get("fresh_remote_account_read_pre") or {}).get("path", "")))
    pre_snapshot = load_optional(resolve_path(dict(summary.get("pre_control_snapshot") or {}).get("path", "")))
    post_snapshot = load_optional(resolve_path(dict(summary.get("post_control_snapshot") or {}).get("path", "")))
    preflight_blockers = set(str(item) for item in preflight.get("blockers") or [])
    return (
        summary.get("contract_version") == P9AC_CONTRACT
        and summary.get("status") == "blocked"
        and "fresh_remote_account_read_pre_failed" in blockers
        and summary.get("remote_sync_performed") is False
        and summary.get("remote_execution_performed") is False
        and int(summary.get("completed_shadow_cycles") or 0) == 0
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and summary.get("production_timer_service_loaded_or_modified") is False
        and preflight.get("account_readable") is True
        and preflight.get("can_trade") is True
        and preflight.get("position_mode") == "one_way"
        and int(preflight.get("open_order_count") or 0) == 0
        and int(preflight.get("open_position_count") or 0) > 0
        and any(item.startswith("mainnet_open_positions_exist:") for item in preflight_blockers)
        and side_effects_zero(preflight)
        and bool(pre_snapshot and post_snapshot)
        and snapshot_boundary_ok(pre_snapshot, post_snapshot)
    )


def nonflat_readback_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ad_nonflat_no_order_contract_body.v1",
        "run_id": run_id,
        "allowed_next_gate": P9AE_GATE,
        "purpose": "allow a separately requested no-order readback on a non-flat account without treating existing positions as candidate execution",
        "admission": {
            "fresh_remote_account_read_same_run": True,
            "account_readable_required": True,
            "can_trade_required": True,
            "position_mode_required": "one_way",
            "open_order_count_required": 0,
            "open_position_count_may_be_nonzero": True,
            "open_positions_must_be_declared": True,
            "read_only_endpoints_only": True,
            "orders_submitted_zero_before_cycles": True,
            "orders_canceled_zero_before_cycles": True,
            "order_test_calls_zero_before_cycles": True,
        },
        "position_safety_contract": {
            "position_fingerprint_required_before_each_cycle": True,
            "position_fingerprint_required_after_each_cycle": True,
            "position_fingerprint_fields": [
                "symbol",
                "positionSide",
                "positionAmt",
                "entryPrice",
                "breakEvenPrice",
                "isolated",
                "isolatedWallet",
            ],
            "allowed_to_drift_between_fingerprints": [
                "markPrice",
                "notional",
                "unRealizedProfit",
                "marginRatio",
                "updateTime",
            ],
            "position_symbols_and_quantities_must_remain_unchanged": True,
            "position_entry_prices_must_remain_unchanged": True,
            "no_new_positions": True,
            "no_closed_positions": True,
            "no_position_size_change": True,
        },
        "cycle_contract": {
            "consecutive_shadow_cycles_required": 3,
            "same_risk_inputs_each_cycle": True,
            "fresh_proof_each_cycle": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "production_timer_service_load_or_mutation": False,
            "live_config_operator_timer_mutation": False,
        },
        "post_cycle_contract": {
            "open_order_count_required": 0,
            "orders_submitted_delta_required": 0,
            "orders_canceled_delta_required": 0,
            "fills_delta_required": 0,
            "account_trade_delta_required": 0,
            "position_fingerprint_must_match_pre_cycle_baseline": True,
            "remote_control_boundary_must_be_unchanged": True,
        },
        "non_authorizations": {
            "p9ae_execution": False,
            "remote_sync": False,
            "remote_execution": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "stage_governance_change": False,
        },
    }


def build_phase9ad(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9ad" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    phase9ab_path = (
        resolve_path(args.phase9ab_summary)
        if str(args.phase9ab_summary).strip()
        else latest_match(PHASE9AB_PARENT, "*/summary.json")
    )
    phase9ac_path = (
        resolve_path(args.phase9ac_summary)
        if str(args.phase9ac_summary).strip()
        else latest_match(PHASE9AC_PARENT, "*/summary.json")
    )
    p9ab = load_optional(phase9ab_path)
    p9ac = load_optional(phase9ac_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    decision = owner_decision_record(args, generated_at)
    contract = nonflat_readback_contract(run_id)
    write_json(proof_root / "nonflat_no_order_readback_contract.json", contract)
    write_json(root / "owner_decision_record.json", decision)

    p9ac_preflight = load_optional(resolve_path(dict(p9ac.get("fresh_remote_account_read_pre") or {}).get("path", "")))
    zero_order_flat_preflight_ready = preflight_ready(p9ac_preflight)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    gates = {
        "owner_decision_p9ad_contract_only": args.owner_decision == APPROVE_P9AD_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ab_remote_gate_ready": p9ab_ready_for_p9ad(p9ab),
        "p9ac_blocked_on_nonflat_account": p9ac_blocked_on_nonflat_account(p9ac),
        "p9ac_zero_order_flat_preflight_not_ready": zero_order_flat_preflight_ready is False,
        "nonflat_contract_allows_existing_positions_only": True,
        "nonflat_contract_requires_zero_open_orders": True,
        "nonflat_contract_requires_position_fingerprint_stability": True,
        "nonflat_contract_requires_order_fill_and_trade_delta_zero": True,
        "nonflat_contract_requires_baseline_only_executor": True,
        "nonflat_contract_requires_candidate_shadow_only": True,
        "nonflat_contract_forbids_candidate_execution": True,
        "nonflat_contract_forbids_live_order_submission": True,
        "nonflat_contract_forbids_target_plan_replacement": True,
        "nonflat_contract_forbids_executor_input_mutation": True,
        "nonflat_contract_forbids_live_config_operator_timer_mutation": True,
        "nonflat_contract_forbids_production_timer_service_load": True,
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "no_remote_sync_in_p9ad": True,
        "no_remote_execution_in_p9ad": True,
        "zero_orders_fills_in_p9ad": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9ad_nonflat_no_order_contract_ready": status == "ready",
        "eligible_for_p9ae_nonflat_remote_no_order_readback_gate": status == "ready",
        "allowed_next_gate": P9AE_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ae_remote_sync_authorized": False,
        "p9ae_remote_execution_authorized": False,
        "p9ae_execution_requires_separate_owner_gate": True,
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "nonflat_contract": {
            "allows_existing_positions": True,
            "requires_zero_open_orders": True,
            "requires_position_fingerprint_stability": True,
            "requires_order_fill_and_trade_delta_zero": True,
            "requires_baseline_only_executor_input": True,
            "requires_candidate_shadow_only": True,
            "does_not_authorize_execution": True,
        },
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9ab_summary": evidence_file(phase9ab_path),
            "phase9ac_summary": evidence_file(phase9ac_path),
            "phase9ac_fresh_remote_account_read_pre": evidence_file(
                resolve_path(dict(p9ac.get("fresh_remote_account_read_pre") or {}).get("path", ""))
            ),
            "phase9ac_pre_control_snapshot": evidence_file(
                resolve_path(dict(p9ac.get("pre_control_snapshot") or {}).get("path", ""))
            ),
            "phase9ac_post_control_snapshot": evidence_file(
                resolve_path(dict(p9ac.get("post_control_snapshot") or {}).get("path", ""))
            ),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {
                "path": str(live_config_dir),
                "exists": live_config_dir.exists(),
                "sha256": tree_sha256(live_config_dir),
            },
            "hook_module_sha256": file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else "",
            "live_supervisor_sha256": file_sha256(supervisor_path)
            if supervisor_path.exists() and supervisor_path.is_file()
            else "",
        },
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "nonflat_no_order_readback_contract": str(proof_root / "nonflat_no_order_readback_contract.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ad(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
