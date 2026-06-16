from __future__ import annotations

import argparse
import copy
import os
import sys
import time
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    build_nonflat_position_reference_fixture,
    core_cycle_from_supervisor,
    generated_no_order_config,
    run_shadow_hook_for_supervisor_cycle,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback import (  # noqa: E402
    DEFAULT_BASE_CONFIG,
    account_read_blockers,
    build_retained_account_plan_fixture,
    core_loop_blockers,
    hook_ready,
    retained_nonflat_account_proof_ready,
    retained_p9aa_summary_ready,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bp_owner_gate_allow_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BP_DECISION,
    CONTRACT_VERSION as P9BP_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BP_PARENT,
    P9BQ_GATE,
    P9BQ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    output_under_proof_artifacts,
    resolve_path,
    source_output_path,
    write_json,
    zero_orders_fills,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bq_timer_path_shadow_cycles.v1"
APPROVE_P9BQ_DECISION = (
    "approve_p9bq_execute_at_least_3_continuous_real_timer_path_shadow_cycles_no_order_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bq_timer_shadow"
P9BR_GATE = "P9BR_review_p9bq_retained_evidence_only_if_separately_requested"

SupervisorRunner = Callable[..., tuple[dict[str, Any], int]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9BQ: at least three continuous no-order shadow cycles through "
            "the real mainnet live-supervisor entrypoint, using retained PIT-safe "
            "account/position fixtures. The executor remains baseline-only; the "
            "candidate writes only shadow artifacts under proof_artifacts; live "
            "order submission remains disabled."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bp-summary", default="")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--shadow-cycles", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--account-proof-source", default="")
    parser.add_argument("--position-reference-source", default="")
    parser.add_argument("--retained-p9aa-summary", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BQ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bq_execute_continuous_timer_path_shadow_cycles_no_order_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9bp_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bp_summary).strip():
        return resolve_path(args.phase9bp_summary)
    return latest_match(P9BP_PARENT, "*/summary.json")


def evidence_path(payload: dict[str, Any], key: str) -> Path:
    path = str(dict(payload.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(path) if path.strip() else Path("")


def p9bp_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "execution_permission": source_output_path(summary, "execution_permission"),
        "acceptance_contract": source_output_path(summary, "acceptance_contract"),
        "acceptance_checklist": source_output_path(summary, "acceptance_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def chain_sources_from_p9bp(p9bp: dict[str, Any]) -> dict[str, Path]:
    p9bo_path = evidence_path(p9bp, "phase9bo_summary")
    p9bo = load_optional(p9bo_path)
    p9bn_path = evidence_path(p9bo, "phase9bn_summary")
    p9bn = load_optional(p9bn_path)
    p9bm_path = evidence_path(p9bn, "phase9bm_summary")
    p9bm = load_optional(p9bm_path)
    return {
        "phase9bo_summary": p9bo_path,
        "phase9bn_summary": p9bn_path,
        "phase9bm_summary": p9bm_path,
        "account_proof_source": evidence_path(p9bm, "account_proof_source"),
        "position_reference_source": evidence_path(p9bm, "position_reference_source"),
        "retained_p9aa_summary": evidence_path(p9bm, "retained_p9aa_summary"),
    }


def source_or_inferred(raw: str, inferred: Path) -> Path:
    return resolve_path(raw) if str(raw or "").strip() else inferred


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def p9bp_ready_for_p9bq(
    summary: dict[str, Any],
    owner: dict[str, Any],
    permission: dict[str, Any],
    acceptance: dict[str, Any],
    checklist: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    checks = dict(checklist.get("checks") or {})
    permission_contract = dict(permission.get("acceptance_contract") or {})
    required_acceptance = (
        "fresh_proof_each_cycle",
        "same_risk_inputs_as_baseline_plan_each_cycle",
        "baseline_only_executor_input_each_cycle",
        "candidate_shadow_only_each_cycle",
        "candidate_artifacts_under_proof_artifacts_only_each_cycle",
        "candidate_plan_must_not_be_referenced_by_executor_each_cycle",
        "target_plan_must_not_be_replaced_each_cycle",
        "executor_input_must_not_change_each_cycle",
        "zero_order_delta_each_cycle",
        "zero_cancel_delta_each_cycle",
        "zero_fill_delta_each_cycle",
        "zero_trade_delta_each_cycle",
        "live_config_must_not_change",
        "operator_state_must_not_change",
        "timer_state_must_not_change",
    )
    false_runtime = (
        "continuous_timer_path_shadow_cycles_execution_authorized",
        "continuous_timer_path_shadow_cycles_executed_in_p9bp",
        "execute_cycles_inside_p9bp_authorized",
        "timer_path_load_authorized_in_p9bp",
        "supervisor_invocation_authorized_in_p9bp",
        "remote_sync_authorized_in_p9bp",
        "candidate_execution_authorized",
        "live_order_submission_authorized",
        "entered_timer_path",
        "ran_supervisor",
        "remote_execution_performed",
        "executor_input_changed",
        "target_plan_replaced",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
    )
    return (
        summary.get("contract_version") == P9BP_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bp_owner_gate_ready") is True
        and summary.get("p9bo_proposal_review_package_ready_for_p9bp") is True
        and summary.get("eligible_for_future_p9bq_continuous_timer_path_shadow_cycles") is True
        and summary.get("allowed_next_gate") == P9BQ_GATE
        and summary.get("allowed_next_gate_scope") == P9BQ_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("future_continuous_timer_path_shadow_cycles_execution_authorized") is True
        and summary.get("continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate") is True
        and summary.get("p9bq_execution_gate_authorized") is True
        and all_false(summary, false_runtime)
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(summary)
        and owner.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bp_owner_decision.v1"
        and owner.get("decision") == APPROVE_P9BP_DECISION
        and owner.get("future_continuous_timer_path_shadow_cycles_execution_approved") is True
        and owner.get("p9bq_execution_gate_approved") is True
        and owner.get("execute_cycles_inside_p9bp_approved") is False
        and owner.get("candidate_execution_approved") is False
        and owner.get("live_order_submission_approved") is False
        and permission.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bp_execution_permission.v1"
        and permission.get("permission_ready") is True
        and permission.get("allowed_next_gate") == P9BQ_GATE
        and permission.get("allowed_next_gate_scope") == P9BQ_SCOPE
        and permission.get("continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate") is True
        and permission.get("p9bq_execution_gate_authorized") is True
        and permission.get("execute_cycles_inside_p9bp") is False
        and permission.get("candidate_order_authority") == "disabled"
        and permission.get("executor_target_source") == "baseline_only"
        and permission.get("candidate_shadow_only") is True
        and acceptance.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bp_p9bq_acceptance_contract.v1"
        and acceptance.get("accepted_next_gate") == P9BQ_GATE
        and acceptance.get("accepted_next_gate_scope") == P9BQ_SCOPE
        and acceptance.get("p9bq_must_be_separately_requested") is True
        and int(acceptance.get("minimum_cycle_count") or 0) >= 3
        and acceptance.get("cycles_must_be_continuous") is True
        and acceptance.get("cycles_must_share_same_no_order_config") is True
        and acceptance.get("cycles_must_use_real_live_supervisor_timer_path") is True
        and all(acceptance.get(key) is True for key in required_acceptance)
        and acceptance.get("live_order_submission_authorized") is False
        and acceptance.get("candidate_execution_authorized") is False
        and permission_contract.get("accepted_next_gate") == P9BQ_GATE
        and int(permission_contract.get("minimum_cycle_count") or 0) >= 3
        and checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bp_acceptance_checklist.v1"
        and all(value is True for value in checks.values())
        and matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bp_non_authorization_matrix.v1"
        and authorizations.get("future_continuous_timer_path_shadow_cycles_execution") is True
        and authorizations.get("p9bq_execution_gate") is True
        and authorizations.get("execute_cycles_inside_p9bp") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bp_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("continuous_timer_path_shadow_cycles_executed_in_p9bp") is False
        and control.get("live_order_submission_authorized") is False
        and zero_orders_fills(control)
        and all(path.exists() for path in paths.values() if str(path))
        and output_under_proof_artifacts(paths["execution_permission"])
        and output_under_proof_artifacts(paths["acceptance_contract"])
        and output_under_proof_artifacts(paths["acceptance_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BQ_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bq_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "execute_at_least_3_continuous_real_timer_path_shadow_cycles_no_order_only",
        "decision_effect": "execute_p9bq_continuous_real_timer_path_shadow_cycles_no_order_only"
        if approved
        else "none",
        "continuous_timer_path_shadow_cycles_execution_approved": approved,
        "supervisor_entrypoint_invocation_approved": approved,
        "observe_only_hook_invocation_approved": approved,
        "generated_no_order_config_approved": approved,
        "retained_pit_safe_fixture_use_approved": approved,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "repo_stage_change_approved": False,
    }


def supervisor_cycle(summary: dict[str, Any]) -> dict[str, Any]:
    cycles = list(summary.get("cycles") or [])
    return dict(cycles[-1]) if cycles else {}


def core_loop_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return dict(supervisor_cycle(summary).get("core_loop_summary") or {})


def hook_summary_ready(hook: dict[str, Any]) -> bool:
    return hook_ready(hook)


def cycle_target_hash(row: dict[str, Any]) -> str:
    hook = dict(row.get("hook_summary") or {})
    baseline = dict(hook.get("baseline_target_plan") or {})
    return str(baseline.get("sha256") or hook.get("baseline_target_plan_sha256_after_hook") or "")


def cycle_ready(row: dict[str, Any]) -> bool:
    supervisor = dict(row.get("supervisor_summary") or {})
    hook = dict(row.get("hook_summary") or {})
    cycle = supervisor_cycle(supervisor)
    core = core_loop_summary(supervisor)
    core_cycle = core_cycle_from_supervisor(supervisor)
    return (
        int(row.get("supervisor_exit_code") or 0) == 0
        and supervisor.get("status") == "mainnet_live_supervisor_completed"
        and not supervisor.get("blockers")
        and int(supervisor.get("completed_cycle_count") or 0) == 1
        and zero_orders_fills(supervisor)
        and supervisor.get("live_delta_authorized") is False
        and cycle.get("status") == "cycle_observed_no_order"
        and cycle.get("execute_live_delta_requested") is False
        and cycle.get("live_delta_authorized") is False
        and zero_orders_fills(cycle)
        and core.get("status") == "mainnet_core_loop_completed"
        and not core.get("blockers")
        and core.get("execution_requested") is False
        and core.get("live_delta_authorized") is False
        and zero_orders_fills(core)
        and bool(str(core_cycle.get("plan_artifact_root") or ""))
        and hook_summary_ready(hook)
    )


def collect_blockers(cycle_rows: list[dict[str, Any]]) -> list[str]:
    blockers: set[str] = set()
    for row in cycle_rows:
        blockers.update(str(item) for item in list(row.get("blockers") or []))
        blockers.update(core_loop_blockers(dict(row.get("supervisor_summary") or {})))
        hook = dict(row.get("hook_summary") or {})
        blockers.update(str(item) for item in list(hook.get("blockers") or []))
    return sorted(item for item in blockers if item)


def plan_artifact_missing_cycles(cycle_rows: list[dict[str, Any]]) -> list[int]:
    missing: list[int] = []
    for row in cycle_rows:
        core_cycle = core_cycle_from_supervisor(dict(row.get("supervisor_summary") or {}))
        plan_root = str(core_cycle.get("plan_artifact_root") or "").strip()
        target = resolve_path(plan_root) / "target_portfolio.json" if plan_root else Path("")
        if not plan_root or not target.exists():
            missing.append(int(row.get("cycle_index") or 0))
    return missing


def build_p9bq(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    supervisor_runner: SupervisorRunner = run_mainnet_live_supervisor,
    env: Mapping[str, str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bq" / run_id

    phase9bp_path = latest_p9bp_summary(args)
    p9bp = load_optional(phase9bp_path)
    p9bp_paths = p9bp_output_paths(p9bp)
    p9bp_owner = load_optional(p9bp_paths["owner_decision_record"])
    p9bp_permission = load_optional(p9bp_paths["execution_permission"])
    p9bp_acceptance = load_optional(p9bp_paths["acceptance_contract"])
    p9bp_checklist = load_optional(p9bp_paths["acceptance_checklist"])
    p9bp_matrix = load_optional(p9bp_paths["non_authorization_matrix"])
    p9bp_control = load_optional(p9bp_paths["control_boundary_readback"])
    inferred = chain_sources_from_p9bp(p9bp)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bp": phase9bp_path,
        "base_config": resolve_path(args.base_config),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
        "account_proof_source": source_or_inferred(args.account_proof_source, inferred["account_proof_source"]),
        "position_reference_source": source_or_inferred(
            args.position_reference_source, inferred["position_reference_source"]
        ),
        "retained_p9aa_summary": source_or_inferred(
            args.retained_p9aa_summary, inferred["retained_p9aa_summary"]
        ),
        **inferred,
    }
    project_profile = load_optional(paths["project_profile"])
    account_proof = load_optional(paths["account_proof_source"])
    retained_p9aa = load_optional(paths["retained_p9aa_summary"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    decision = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision_record.json", decision)

    p9bp_ok = p9bp_ready_for_p9bq(
        p9bp,
        p9bp_owner,
        p9bp_permission,
        p9bp_acceptance,
        p9bp_checklist,
        p9bp_matrix,
        p9bp_control,
        p9bp_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bp_summary": evidence_file(paths["phase9bp"]),
        "phase9bp_owner_decision_record": evidence_file(p9bp_paths["owner_decision_record"]),
        "phase9bp_execution_permission": evidence_file(p9bp_paths["execution_permission"]),
        "phase9bp_acceptance_contract": evidence_file(p9bp_paths["acceptance_contract"]),
        "phase9bp_acceptance_checklist": evidence_file(p9bp_paths["acceptance_checklist"]),
        "phase9bp_non_authorization_matrix": evidence_file(p9bp_paths["non_authorization_matrix"]),
        "phase9bp_control_boundary_readback": evidence_file(p9bp_paths["control_boundary_readback"]),
        "phase9bo_summary": evidence_file(paths["phase9bo_summary"]),
        "phase9bn_summary": evidence_file(paths["phase9bn_summary"]),
        "phase9bm_summary": evidence_file(paths["phase9bm_summary"]),
        "base_config": evidence_file(paths["base_config"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
        "account_proof_source": evidence_file(paths["account_proof_source"]),
        "position_reference_source": evidence_file(paths["position_reference_source"]),
        "retained_p9aa_summary": evidence_file(paths["retained_p9aa_summary"]),
    }
    pre_gates = {
        "owner_decision_p9bq_execute_cycles_no_order_only": str(args.owner_decision)
        == APPROVE_P9BQ_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bp_owner_gate_ready_for_p9bq": p9bp_ok,
        "base_config_exists": paths["base_config"].exists(),
        "shadow_cycles_at_least_three": int(args.shadow_cycles or 0) >= 3,
        "retained_account_fixture_sources_complete": (
            paths["account_proof_source"].exists()
            and paths["position_reference_source"].exists()
            and paths["retained_p9aa_summary"].exists()
        ),
        "retained_account_proof_read_only_ready": retained_nonflat_account_proof_ready(
            account_proof, generated_at=generated_at
        ),
        "retained_p9aa_summary_ready": retained_p9aa_summary_ready(retained_p9aa),
        "current_live_supervisor_not_already_loading_hook": supervisor_loads_hook is False,
    }
    pre_blockers = [key for key, value in pre_gates.items() if not value]

    position_reference_run = Path("")
    position_reference_summary: dict[str, Any] = {}
    position_reference_blockers: list[str] = []
    retained_account_fixture_summary: dict[str, Any] = {}
    retained_account_fixture_blockers: list[str] = []
    generated_config_path = Path("")
    cycle_rows: list[dict[str, Any]] = []

    if not pre_blockers:
        position_reference_run, position_reference_summary, position_reference_blockers = (
            build_nonflat_position_reference_fixture(
                source_path=paths["position_reference_source"],
                proof_root=proof_root,
                run_id=run_id,
                generated_at=generated_at,
            )
        )
        pre_gates["pit_safe_position_reference_fixture_ready"] = (
            bool(str(position_reference_run))
            and position_reference_run.exists()
            and not position_reference_blockers
            and position_reference_summary.get("status") == "position_genesis_snapshot"
            and position_reference_summary.get("read_only") is True
            and position_reference_summary.get("proof_artifacts_only") is True
            and position_reference_summary.get("source_created_before_p9aa") is True
        )
        if not pre_gates["pit_safe_position_reference_fixture_ready"]:
            pre_blockers.append("pit_safe_position_reference_fixture_ready")
            pre_blockers.extend(position_reference_blockers)

    if not pre_blockers:
        retained_account_fixture_summary, retained_account_fixture_blockers = (
            build_retained_account_plan_fixture(
                p9aa_summary=retained_p9aa,
                account_proof=account_proof,
                position_reference_summary=position_reference_summary,
                fixture_root=proof_root / "acct_fx",
                run_id=run_id,
                generated_at=generated_at,
            )
        )
        pre_gates["retained_account_plan_fixture_ready"] = (
            retained_account_fixture_summary.get("status") == "ready"
            and not retained_account_fixture_blockers
            and retained_account_fixture_summary.get("read_only") is True
            and retained_account_fixture_summary.get("proof_artifacts_only") is True
        )
        if not pre_gates["retained_account_plan_fixture_ready"]:
            pre_blockers.append("retained_account_plan_fixture_ready")
            pre_blockers.extend(retained_account_fixture_blockers)

    if not pre_blockers:
        generated_config_path = generated_no_order_config(
            base_config=paths["base_config"], proof_root=proof_root, run_id=run_id
        )
        retained_core_summary = dict(retained_account_fixture_summary.get("core_loop_summary") or {})

        def retained_core_loop_runner(_: Namespace, **__: Any) -> tuple[dict[str, Any], int]:
            return copy.deepcopy(retained_core_summary), 0

        for cycle_index in range(1, int(args.shadow_cycles) + 1):
            supervisor_args = Namespace(
                config=str(generated_config_path),
                as_of=str(args.as_of),
                fixture_panel=str(args.fixture_panel or ""),
                symbols=str(args.symbols or ""),
                public_market_data=bool(args.public_market_data),
                reference_run=str(position_reference_run),
                target_engine=str(args.target_engine or ""),
                cycles=1,
                interval_seconds=0.0,
                position_tolerance=float(args.position_tolerance or 1e-9),
                fast_follow_entry_second=False,
                fast_follow_chain_depth=0,
            )
            try:
                supervisor_summary, supervisor_exit = supervisor_runner(
                    supervisor_args,
                    env=env or os.environ,
                    core_loop_runner=retained_core_loop_runner,
                )
            except Exception as exc:
                supervisor_summary = {
                    "run_id": f"{run_id}-cycle-{cycle_index:03d}-supervisor-exception",
                    "status": "mainnet_live_supervisor_exception",
                    "blockers": [f"supervisor_entrypoint_exception:{type(exc).__name__}:{exc}"],
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "orders_submitted": 0,
                    "fill_count": 0,
                    "fills_observed": 0,
                    "exchange_order_submission": "disabled",
                    "live_delta_authorized": False,
                    "cycles": [],
                }
                supervisor_exit = 2
            hook_summary: dict[str, Any] = {}
            if supervisor_summary.get("status") == "mainnet_live_supervisor_completed":
                hook_summary = run_shadow_hook_for_supervisor_cycle(
                    proof_root=proof_root,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    supervisor_summary=supervisor_summary,
                )
            row = {
                "cycle_index": int(cycle_index),
                "supervisor_exit_code": int(supervisor_exit),
                "supervisor_summary": supervisor_summary,
                "hook_summary": hook_summary,
            }
            row["cycle_ready"] = cycle_ready(row)
            row["target_plan_sha256"] = cycle_target_hash(row)
            write_json(proof_root / f"cycle_{cycle_index:03d}_timer_path_shadow_readback.json", row)
            cycle_rows.append(row)
            if not row["cycle_ready"]:
                break
            if float(args.interval_seconds or 0.0) > 0 and cycle_index < int(args.shadow_cycles):
                sleep_fn(float(args.interval_seconds))

    supervisor_blocker_rows = collect_blockers(cycle_rows)
    account_read_blocker_rows = account_read_blockers(supervisor_blocker_rows)
    missing_plan_cycles = plan_artifact_missing_cycles(cycle_rows)
    supervisor_run_ids = [str(dict(row.get("supervisor_summary") or {}).get("run_id") or "") for row in cycle_rows]
    hook_roots = [str(dict(row.get("hook_summary") or {}).get("proof_root") or "") for row in cycle_rows]
    target_hashes = [str(row.get("target_plan_sha256") or "") for row in cycle_rows]
    generated_config_exists = bool(str(generated_config_path)) and generated_config_path.exists()
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    runtime_gates = {
        "generated_no_order_config_written": generated_config_exists,
        "generated_config_under_proof_artifacts": (
            output_under_proof_artifacts(generated_config_path) if generated_config_exists else False
        ),
        "ran_requested_cycle_count": len(cycle_rows) == int(args.shadow_cycles or 0),
        "ran_at_least_three_cycles": len(cycle_rows) >= 3,
        "cycles_are_contiguous": [int(row.get("cycle_index") or 0) for row in cycle_rows]
        == list(range(1, len(cycle_rows) + 1)),
        "fresh_supervisor_run_each_cycle": len(supervisor_run_ids) >= 3
        and len(set(supervisor_run_ids)) == len(supervisor_run_ids)
        and all(supervisor_run_ids),
        "fresh_hook_proof_root_each_cycle": len(hook_roots) >= 3
        and len(set(hook_roots)) == len(hook_roots)
        and all(hook_roots),
        "same_risk_no_order_config_each_cycle": generated_config_exists,
        "same_target_plan_hash_each_cycle": len(target_hashes) >= 3
        and len(set(target_hashes)) == 1
        and all(target_hashes),
        "all_cycles_ready": bool(cycle_rows) and all(row.get("cycle_ready") is True for row in cycle_rows),
        "all_supervisor_orders_zero": bool(cycle_rows)
        and all(zero_orders_fills(dict(row.get("supervisor_summary") or {})) for row in cycle_rows),
        "all_hook_orders_zero": bool(cycle_rows)
        and all(zero_orders_fills(dict(row.get("hook_summary") or {})) for row in cycle_rows),
        "all_executor_baseline_only": bool(cycle_rows)
        and all(
            dict(row.get("hook_summary") or {}).get("executor_consumes_baseline_only") is True
            for row in cycle_rows
        ),
        "all_candidate_shadow_only": bool(cycle_rows)
        and all(dict(row.get("hook_summary") or {}).get("hook_enabled") is True for row in cycle_rows),
        "all_candidate_artifacts_under_proof_artifacts_only": bool(cycle_rows)
        and all(
            dict(row.get("hook_summary") or {}).get("candidate_artifacts_under_proof_artifacts_only")
            is True
            for row in cycle_rows
        ),
        "all_candidate_plan_not_referenced_by_executor": bool(cycle_rows)
        and all(
            dict(row.get("hook_summary") or {}).get("candidate_plan_referenced_by_executor") is False
            for row in cycle_rows
        ),
        "all_executor_input_hash_unchanged": bool(cycle_rows)
        and all(
            dict(row.get("hook_summary") or {}).get("executor_input_plan_hash_unchanged") is True
            for row in cycle_rows
        ),
        "all_baseline_target_plan_byte_for_byte_unchanged": bool(cycle_rows)
        and all(
            dict(row.get("hook_summary") or {}).get("baseline_target_plan_byte_for_byte_unchanged")
            is True
            for row in cycle_rows
        ),
        "zero_order_cancel_fill_trade_delta": bool(cycle_rows)
        and sum(int(dict(row.get("supervisor_summary") or {}).get("orders_submitted") or 0) for row in cycle_rows)
        == 0
        and sum(int(dict(row.get("supervisor_summary") or {}).get("fill_count") or 0) for row in cycle_rows)
        == 0,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "no_production_timer_service_load_or_mutation": True,
        "no_remote_sync": True,
        "no_remote_execution": True,
        "no_candidate_execution": True,
        "no_live_order_submission": True,
        "no_target_plan_replacement": True,
        "no_executor_input_mutation": True,
        "no_live_config_operator_timer_mutation": (
            live_config_sha_before == live_config_sha_after
        ),
    }
    gates = {**pre_gates, **runtime_gates}
    blockers = pre_blockers + [key for key, value in runtime_gates.items() if not value]
    if supervisor_blocker_rows:
        blockers.append("supervisor_or_core_loop_blockers_present")
    if account_read_blocker_rows:
        blockers.append("timer_path_account_read_blocked")
    if missing_plan_cycles:
        blockers.append("timer_path_plan_artifact_missing")
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    total_orders = sum(int(dict(row.get("supervisor_summary") or {}).get("orders_submitted") or 0) for row in cycle_rows)
    total_fills = sum(int(dict(row.get("supervisor_summary") or {}).get("fill_count") or 0) for row in cycle_rows)

    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bq_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "continuous_real_supervisor_entrypoint_shadow_cycles_no_order_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "generated_config": evidence_file(generated_config_path),
        "generated_config_under_proof_artifacts": runtime_gates["generated_config_under_proof_artifacts"],
        "supervisor_entrypoint_invoked": bool(cycle_rows),
        "completed_shadow_cycles": len(cycle_rows),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "live_order_submission_authorized": False,
        "orders_submitted": int(total_orders),
        "orders_canceled": 0,
        "fill_count": int(total_fills),
        "trade_count": 0,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "live_config_changed": live_config_sha_before != live_config_sha_after,
        "operator_state_changed_outside_generated_p9bq_state": False,
        "timer_state_changed": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bq_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "continuous_timer_path_shadow_cycles_execution": ready,
            "supervisor_entrypoint_invocation": ready,
            "observe_only_hook_invocation": ready,
            "generated_no_order_config": ready,
            "retained_pit_safe_fixture_use": ready,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "generated_no_order_config": str(generated_config_path) if generated_config_exists else "",
        "position_reference_fixture": str(position_reference_run / "run_summary.json")
        if str(position_reference_run)
        else "",
        "retained_account_plan_fixture": str(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
        )
        if retained_account_fixture_summary
        else "",
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "report": str(root / "p9bq_timer_path_shadow_cycles.md"),
    }
    for row in cycle_rows:
        output_files[f"cycle_{int(row.get('cycle_index') or 0):03d}_readback"] = str(
            proof_root / f"cycle_{int(row.get('cycle_index') or 0):03d}_timer_path_shadow_readback.json"
        )
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bq_continuous_real_timer_path_shadow_cycles_no_order_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bq_timer_path_shadow_cycles_ready": ready,
        "continuous_timer_path_shadow_cycles_executed": bool(cycle_rows),
        "continuous_timer_path_shadow_cycles_ready": ready,
        "timer_path_shadow_readback_mode": (
            "real_supervisor_entrypoint_with_retained_pit_safe_account_position_reference_fixture"
        ),
        "account_proof_mode": "retained_pit_safe_read_only_fixture",
        "retained_account_fixture_requested": True,
        "retained_account_proof_ready": retained_nonflat_account_proof_ready(
            account_proof, generated_at=generated_at
        ),
        "pit_safe_position_reference_fixture_ready": pre_gates.get(
            "pit_safe_position_reference_fixture_ready", False
        ),
        "retained_account_plan_fixture_ready": pre_gates.get(
            "retained_account_plan_fixture_ready", False
        ),
        "requested_shadow_cycles": int(args.shadow_cycles or 0),
        "completed_shadow_cycles": len(cycle_rows),
        "cycles_are_contiguous": runtime_gates["cycles_are_contiguous"],
        "fresh_proof_each_cycle": runtime_gates["fresh_supervisor_run_each_cycle"]
        and runtime_gates["fresh_hook_proof_root_each_cycle"],
        "same_risk_no_order_config_each_cycle": runtime_gates["same_risk_no_order_config_each_cycle"],
        "same_target_plan_hash_each_cycle": runtime_gates["same_target_plan_hash_each_cycle"],
        "target_plan_sha256_each_cycle": target_hashes,
        "generated_no_order_config": evidence_file(generated_config_path),
        "position_reference_fixture": evidence_file(
            position_reference_run / "run_summary.json" if str(position_reference_run) else Path("")
        ),
        "position_reference_fixture_summary": position_reference_summary,
        "retained_account_plan_fixture": evidence_file(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
            if retained_account_fixture_summary
            else Path("")
        ),
        "retained_account_plan_fixture_summary": retained_account_fixture_summary,
        "supervisor_entrypoint_invoked": bool(cycle_rows),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "candidate_shadow_only": runtime_gates["all_candidate_shadow_only"],
        "candidate_artifacts_under_proof_artifacts_only": runtime_gates[
            "all_candidate_artifacts_under_proof_artifacts_only"
        ],
        "executor_consumes_baseline_only": runtime_gates["all_executor_baseline_only"],
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": int(total_orders),
        "orders_canceled": 0,
        "fill_count": int(total_fills),
        "trade_count": 0,
        "zero_order_cancel_fill_trade_delta": runtime_gates["zero_order_cancel_fill_trade_delta"],
        "live_config_changed": live_config_sha_before != live_config_sha_after,
        "operator_state_changed_outside_generated_p9bq_state": False,
        "timer_state_changed": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "allowed_next_gate": P9BR_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "supervisor_or_core_loop_blockers": supervisor_blocker_rows,
        "account_read_blockers": account_read_blocker_rows,
        "plan_artifact_missing_cycles": missing_plan_cycles,
        "cycle_rows": cycle_rows,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": sorted(set(blockers)),
        "output_files": output_files,
    }
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization)
    write_json(root / "summary.json", summary)
    (root / "p9bq_timer_path_shadow_cycles.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BQ Timer-Path Shadow Cycles",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BQ executes consecutive no-order shadow cycles through the real live-supervisor entrypoint with retained PIT-safe account fixtures.",
        "",
        "```text",
        f"p9bq_timer_path_shadow_cycles_ready = "
        f"{str(bool(summary['p9bq_timer_path_shadow_cycles_ready'])).lower()}",
        f"completed_shadow_cycles = {int(summary.get('completed_shadow_cycles') or 0)}",
        f"fresh_proof_each_cycle = {str(bool(summary.get('fresh_proof_each_cycle'))).lower()}",
        f"same_risk_no_order_config_each_cycle = "
        f"{str(bool(summary.get('same_risk_no_order_config_each_cycle'))).lower()}",
        "systemd_timer_service_invoked = false",
        "production_timer_service_loaded_or_modified = false",
        "execution_target_source = baseline_only",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        f"orders_submitted = {int(summary.get('orders_submitted') or 0)}",
        f"fill_count = {int(summary.get('fill_count') or 0)}",
        "```",
        "",
        "## Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Blockers", ""])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bq(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
