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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9br_review_after_p9bq import (  # noqa: E402
    CONTRACT_VERSION as P9BR_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BR_PARENT,
    P9BS_GATE,
    P9BS_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition.v1"
APPROVE_P9BS_SCOPE_DECISION = (
    "approve_p9bs_define_execution_path_change_discussion_scope_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bs_execution_path_scope_definition"
)
P9BT_GATE = (
    "P9BT_stage3_human_approved_execution_profile_transition_only_if_separately_requested"
)
P9BT_SCOPE = (
    "transition_project_profile_to_stage3_human_approved_execution_no_live_order_no_candidate_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BS as the scope-definition gate allowed by P9BR. P9BS defines "
            "the bounded discussion scope for a future execution-path change, but "
            "does not prepare an implementation proposal, mutate executor input, "
            "replace target plans, invoke supervisor/timer path, remote sync, "
            "execute the candidate, or authorize live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9br-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BS_SCOPE_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:fix_p9br_scope_blocker_define_execution_path_change_scope_only",
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


def latest_p9br_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9br_summary).strip():
        return resolve_path(args.phase9br_summary)
    return latest_match(P9BR_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9br_ready_for_scope_definition(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BR_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9br_retained_evidence_review_ready") is True
        and summary.get("p9bq_retained_shadow_cycles_sufficient") is True
        and summary.get("sufficient_for_execution_path_change_discussion") is True
        and summary.get("eligible_for_future_p9bs_execution_path_change_discussion_scope_gate_request")
        is True
        and summary.get("allowed_next_gate") == P9BS_GATE
        and summary.get("allowed_next_gate_scope") == P9BS_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("execution_path_change_proposal_authorized") is False
        and summary.get("execution_path_change_implementation_authorized") is False
        and summary.get("execution_path_change_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def p9bs_scope_ready_for_live_order_gate_review(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == CONTRACT_VERSION
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bs_execution_path_scope_definition_ready") is True
        and summary.get("p9br_scope_blocker_resolved") is True
        and summary.get("p9bs_execution_path_change_discussion_scope_defined") is True
        and summary.get("eligible_for_future_execution_path_change_proposal") is True
        and summary.get("eligible_for_future_live_order_gate_terms_discussion") is True
        and summary.get("execution_path_change_implementation_authorized") is False
        and summary.get("execution_path_change_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def build_p9bs_execution_path_scope_definition(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bs_execution_path_scope_definition" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9br_summary_path = latest_p9br_summary(args)
    p9br = load_optional(p9br_summary_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BS_SCOPE_DECISION
    p9br_ready = p9br_ready_for_scope_definition(p9br)
    checks = {
        "owner_decision_p9bs_scope_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "p9br_summary_exists": bool(p9br),
        "p9br_ready_for_scope_definition": p9br_ready,
        "scope_definition_only_no_implementation": True,
        "no_timer_supervisor_remote_or_order_authority": True,
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    discussion_scope = {
        "scope_id": "candidate_execution_path_change_discussion_only",
        "may_discuss": [
            "candidate executor and target-plan path contract",
            "candidate target-plan replacement semantics to be proven in a no-order dry run",
            "explicit risk ceiling and maximum notional terms",
            "supported order type and exchange-side order constraints",
            "operator-visible kill switch",
            "rollback conditions and rollback command path",
            "fresh pre-trade account, position, open-order, fill, and trade fingerprints",
        ],
        "must_remain_out_of_scope": [
            "implementation",
            "timer-path load",
            "supervisor invocation",
            "remote sync",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "live config mutation",
            "operator-state mutation",
            "live order submission",
        ],
    }

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_scope_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_execution_path_change_discussion_scope_only",
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": owner_decision_ok,
        "implementation_approved": False,
        "execution_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "repo_stage_change_approved": False,
    }

    scope_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_packet.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "discussion_scope": discussion_scope,
        "p9br_scope_blocker_resolved": ready,
        "eligible_for_future_execution_path_change_proposal": ready,
        "eligible_for_future_live_order_gate_terms_discussion": ready,
        "live_order_gate_approved": False,
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_scope_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "define_execution_path_change_discussion_scope": ready,
            "prepare_execution_path_change_proposal": False,
            "execute_execution_path_change": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_scope_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "scope_definition_only",
        "phase9br_summary": evidence_file(p9br_summary_path),
        "project_profile": evidence_file(project_profile_path),
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
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

    owner_path = root / "owner_decision_record.json"
    scope_path = proof_root / "execution_path_scope_packet.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bs_execution_path_scope_definition.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "execution_path_scope_packet": str(scope_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9bs_execution_path_scope_definition_ready": ready,
        "p9bs_execution_path_change_discussion_scope_defined": ready,
        "p9br_scope_blocker_resolved": ready,
        "eligible_for_future_execution_path_change_proposal": ready,
        "eligible_for_future_live_order_gate_terms_discussion": ready,
        "allowed_next_gate": P9BT_GATE,
        "allowed_next_gate_scope": P9BT_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "discussion_scope": discussion_scope,
        "execution_path_change_proposal_authorized": False,
        "execution_path_change_implementation_authorized": False,
        "execution_path_change_execution_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "repo_stage_change_authorized": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": {
            "phase9br_summary": evidence_file(p9br_summary_path),
            "project_profile": evidence_file(project_profile_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_tree": {
                "path": str(live_config_path),
                "exists": live_config_path.exists(),
                "sha256": tree_sha256(live_config_path),
            },
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, scope_packet)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BS Execution-Path Scope Definition",
                "",
                f"`Status: {summary['status']}`",
                "",
                "## Decision",
                "",
                "P9BS defines only the bounded discussion scope for a future execution-path change. It does not approve implementation, candidate execution, target-plan replacement, executor-input mutation, timer/supervisor/remote activity, or live orders.",
                "",
                "```text",
                f"p9br_scope_blocker_resolved = {str(ready).lower()}",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
                "## Allowed Future Discussion Scope",
                "",
                *[f"- {item}" for item in discussion_scope["may_discuss"]],
                "",
                "## Explicitly Out Of Scope",
                "",
                *[f"- {item}" for item in discussion_scope["must_remain_out_of_scope"]],
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bs_execution_path_scope_definition(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
