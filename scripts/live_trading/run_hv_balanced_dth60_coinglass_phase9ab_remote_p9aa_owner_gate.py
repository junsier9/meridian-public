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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    CONTRACT_VERSION as P9AA_CONTRACT,
    zero_orders_fills,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate.v1"
APPROVE_P9AB_DECISION = "approve_p9ab_remote_runner_no_order_p9aa_owner_gate_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ab_remote_p9aa_owner_gate"
PHASE9AA_PARENT = "artifacts/live_trading/p9aa_timer_shadow"
P9AC_GATE = "P9AC_remote_runner_consecutive_no_order_p9aa_readback_only_if_separately_requested"
DEFAULT_REMOTE_HOST = "root@203.0.113.10"
DEFAULT_REMOTE_REPO = "/root/meridian_alpha_live_runner/repo"
DEFAULT_REMOTE_CONFIG = (
    "/root/meridian_alpha_live_runner/repo/config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml"
)
DEFAULT_EXPECTED_EGRESS_IP = "203.0.113.10"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9AB is a separate owner gate that may allow a future remote-runner "
            "no-order P9AA readback. This gate writes proof artifacts only; it "
            "does not SSH, sync files, invoke timers, run the supervisor, or "
            "submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9aa-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AB_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:request_p9ab_remote_p9aa_owner_gate")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AB_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ab_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "allow_remote_runner_no_order_p9aa_readback_only",
        "decision_effect": "allow_p9ac_remote_no_order_p9aa_readback" if approved else "none",
        "p9ab_owner_gate_approved": approved,
        "future_p9ac_remote_runner_p9aa_approved": approved,
        "future_p9ac_remote_sync_approved": approved,
        "future_p9ac_remote_supervisor_entrypoint_invocation_approved": approved,
        "future_p9ac_fresh_remote_account_read_proof_required": True,
        "future_p9ac_generated_no_order_config_required": True,
        "future_p9ac_observe_only_hook_readback_approved": approved,
        "future_p9ac_consecutive_cycles_required": 3,
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


def p9aa_fail_closed_for_remote_gate(summary: dict[str, Any]) -> bool:
    blockers = set(str(item) for item in summary.get("blockers") or [])
    account_blockers = list(summary.get("account_read_blockers") or [])
    missing_plan_cycles = list(summary.get("plan_artifact_missing_cycles") or [])
    return (
        summary.get("contract_version") == P9AA_CONTRACT
        and summary.get("status") == "blocked"
        and summary.get("timer_path_shadow_cycles_ready") is False
        and int(summary.get("completed_shadow_cycles") or 0) >= 3
        and summary.get("fresh_proof_each_cycle") is True
        and summary.get("same_risk_no_order_config_each_cycle") is True
        and summary.get("timer_path_supervisor_entrypoint_invoked") is True
        and summary.get("systemd_timer_service_invoked") is False
        and summary.get("production_timer_service_loaded_or_modified") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed_outside_generated_p9aa_state") is False
        and summary.get("timer_state_changed") is False
        and zero_orders_fills(summary)
        and "timer_path_account_read_blocked" in blockers
        and "timer_path_plan_artifact_missing" in blockers
        and bool(account_blockers)
        and len(missing_plan_cycles) >= 3
    )


def remote_runner_declared(args: argparse.Namespace) -> bool:
    return all(str(getattr(args, name, "")).strip() for name in ("remote_host", "remote_repo", "remote_config", "expected_egress_ip"))


def build_phase9ab(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9ab" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9aa_path = (
        resolve_path(args.phase9aa_summary)
        if str(args.phase9aa_summary).strip()
        else latest_match(PHASE9AA_PARENT, "*/summary.json")
    )
    p9aa = load_optional(p9aa_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    gates = {
        "owner_decision_p9ab_gate_only": args.owner_decision == APPROVE_P9AB_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9aa_blocked_fail_closed_due_local_account_read": p9aa_fail_closed_for_remote_gate(p9aa),
        "remote_runner_identity_declared": remote_runner_declared(args),
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "future_fresh_remote_account_read_proof_required": True,
        "future_remote_account_read_must_be_same_run_fresh": True,
        "future_remote_account_read_must_prove_can_trade_and_one_way": True,
        "future_remote_account_read_must_prove_zero_orders_fills_before_cycles": True,
        "future_p9ac_must_use_generated_no_order_config": True,
        "future_p9ac_must_run_at_least_three_consecutive_cycles": True,
        "future_p9ac_must_keep_executor_baseline_only": True,
        "future_p9ac_must_keep_candidate_shadow_only": True,
        "future_p9ac_must_keep_orders_and_fills_zero": True,
        "future_p9ac_must_not_load_production_timer_service": True,
        "future_p9ac_must_not_mutate_live_config_operator_or_timer": True,
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "production_timer_service_load_forbidden": True,
        "no_remote_sync_in_p9ab": True,
        "no_remote_execution_in_p9ab": True,
        "zero_orders_fills_in_p9ab": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    remote_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_gate.v1",
        "run_id": run_id,
        "gate_status": status,
        "authorized_next_gate": P9AC_GATE if status == "ready" else "",
        "remote_runner": {
            "host": args.remote_host,
            "repo": args.remote_repo,
            "config": args.remote_config,
            "expected_egress_ip": args.expected_egress_ip,
        },
        "future_p9ac_requirements": {
            "fresh_remote_account_read_proof": True,
            "fresh_remote_account_read_same_run": True,
            "no_order_generated_config": True,
            "consecutive_shadow_cycles": 3,
            "supervisor_entrypoint_wrapper_only": True,
            "proof_artifacts_output_only": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "orders_submitted_zero": True,
            "fill_count_zero": True,
            "production_timer_service_loaded_or_modified": False,
            "live_config_operator_timer_mutation": False,
        },
        "non_authorizations": {
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "production_timer_service_load": False,
            "stage_governance_change": False,
        },
    }
    write_json(proof_root / "remote_p9aa_owner_gate.json", remote_gate)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9ab_remote_p9aa_owner_gate_ready": status == "ready",
        "eligible_for_p9ac_remote_runner_no_order_p9aa": status == "ready",
        "allowed_next_gate": P9AC_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "future_p9ac_remote_sync_authorized": status == "ready",
        "future_p9ac_remote_execution_authorized": status == "ready",
        "future_p9ac_remote_supervisor_entrypoint_authorized": status == "ready",
        "future_p9ac_fresh_remote_account_read_proof_required": True,
        "future_p9ac_consecutive_cycles_required": 3,
        "future_p9ac_generated_no_order_config_required": True,
        "future_p9ac_baseline_only_executor_required": True,
        "future_p9ac_candidate_shadow_only_required": True,
        "future_p9ac_zero_orders_fills_required": True,
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
        "remote_runner": {
            "host": args.remote_host,
            "repo": args.remote_repo,
            "config": args.remote_config,
            "expected_egress_ip": args.expected_egress_ip,
        },
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9aa_summary": evidence_file(p9aa_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha},
            "hook_module_sha256": hook_sha,
            "live_supervisor_sha256": supervisor_sha,
        },
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "remote_p9aa_owner_gate": str(proof_root / "remote_p9aa_owner_gate.json"),
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ab(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
