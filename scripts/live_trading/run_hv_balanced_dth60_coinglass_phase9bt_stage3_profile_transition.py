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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    CONTRACT_VERSION as P9BS_SCOPE_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BS_SCOPE_PARENT,
    p9bs_scope_ready_for_live_order_gate_review,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bt_stage3_profile_transition.v1"
APPROVE_P9BT_STAGE3_DECISION = (
    "approve_p9bt_stage3_human_approved_execution_profile_transition_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bt_stage3_profile_transition"
)
STAGE_CONTRACT = "config/project_governance/stage_contract.json"
README_PATH = "README.md"
AGENTS_PATH = "AGENTS.md"
README_FOR_AGENT_PATH = "docs/README_FOR_AGENT.md"
PROJECT_STATE_PATH = "PROJECT_STATE.md"
STAGE3 = "stage_3_human_approved_execution"
STAGE4 = "stage_4_automated_execution"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read back the P9BT Stage-3 project profile transition. This validates "
            "that the repo profile and canonical docs now state Stage 3 while "
            "automated execution, candidate execution, target-plan replacement, "
            "executor mutation, supervisor/timer/remote activity, and live orders "
            "remain unauthorized."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--stage-contract", default=STAGE_CONTRACT)
    parser.add_argument("--phase9bs-scope-summary", default="")
    parser.add_argument("--readme", default=README_PATH)
    parser.add_argument("--agents", default=AGENTS_PATH)
    parser.add_argument("--readme-for-agent", default=README_FOR_AGENT_PATH)
    parser.add_argument("--project-state", default=PROJECT_STATE_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BT_STAGE3_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:fix_stage1_blocker_transition_repo_to_stage3",
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


def latest_p9bs_scope_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bs_scope_summary).strip():
        return resolve_path(args.phase9bs_scope_summary)
    return latest_match(P9BS_SCOPE_PARENT, "*/summary.json")


def stage_index(stage_contract: dict[str, Any], stage_id: str) -> int:
    for index, stage in enumerate(stage_contract.get("stages") or []):
        if dict(stage).get("stage_id") == stage_id:
            return index
    return -1


def stage_at_least(stage_contract: dict[str, Any], current: str, minimum: str) -> bool:
    current_index = stage_index(stage_contract, current)
    minimum_index = stage_index(stage_contract, minimum)
    return current_index >= 0 and minimum_index >= 0 and current_index >= minimum_index


def text_contains(path: Path, needle: str) -> bool:
    if not path.exists() or not path.is_file():
        return False
    return needle in path.read_text(encoding="utf-8", errors="ignore")


def canonical_docs_read_stage3(args: argparse.Namespace) -> dict[str, bool]:
    readme = resolve_path(args.readme)
    agents = resolve_path(args.agents)
    readme_for_agent = resolve_path(args.readme_for_agent)
    project_state = resolve_path(args.project_state)
    return {
        "README.md": text_contains(readme, "Current checked-in stage is `Stage 3: Human-Approved Execution`"),
        "AGENTS.md": text_contains(agents, "repo is now at `Stage 3: Human-Approved Execution`"),
        "docs/README_FOR_AGENT.md": text_contains(
            readme_for_agent,
            "Current checked-in state is `Stage 3: Human-Approved Execution`",
        ),
        "PROJECT_STATE.md": text_contains(
            project_state,
            "Current checked-in stage is `stage_3_human_approved_execution`",
        ),
    }


def build_p9bt_stage3_profile_transition(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bt_stage3_profile_transition" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bs_summary_path = latest_p9bs_scope_summary(args)
    p9bs_summary = load_optional(p9bs_summary_path)
    project_profile_path = resolve_path(args.project_profile)
    stage_contract_path = resolve_path(args.stage_contract)
    project_profile = load_optional(project_profile_path)
    stage_contract = load_optional(stage_contract_path)
    current_stage = str(project_profile.get("current_stage") or "")
    target_stage = str(project_profile.get("target_stage") or "")
    unlocks = dict(stage_contract.get("unlock_minimum_stages") or {})
    execution_minimum = str(unlocks.get("execution_manifest_unlock") or "")
    automated_minimum = str(unlocks.get("automated_execution_unlock") or "")
    docs_stage3 = canonical_docs_read_stage3(args)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BT_STAGE3_DECISION
    p9bs_ready = p9bs_scope_ready_for_live_order_gate_review(p9bs_summary)
    stage3_active = current_stage == STAGE3
    execution_manifest_stage_ok = stage_at_least(stage_contract, current_stage, execution_minimum)
    automated_execution_unlocked = stage_at_least(stage_contract, current_stage, automated_minimum)
    checks = {
        "owner_decision_stage3_transition_recorded": owner_decision_ok,
        "p9bs_scope_summary_exists": bool(p9bs_summary),
        "p9bs_scope_ready": p9bs_ready,
        "project_profile_exists": bool(project_profile),
        "stage_contract_exists": bool(stage_contract),
        "current_stage_is_stage3": stage3_active,
        "target_stage_remains_stage4": target_stage == STAGE4,
        "execution_manifest_unlock_minimum_is_stage3": execution_minimum == STAGE3,
        "automated_execution_unlock_minimum_is_stage4": automated_minimum == STAGE4,
        "execution_manifest_stage_minimum_satisfied": execution_manifest_stage_ok,
        "automated_execution_stage_minimum_not_satisfied": automated_execution_unlocked is False,
        "canonical_docs_read_stage3": all(docs_stage3.values()),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bt_stage3_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "transition_project_profile_to_stage3_human_approved_execution_only",
        "recorded_at_utc": iso_z(now),
        "stage3_profile_transition_approved": owner_decision_ok,
        "stage4_automated_execution_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }

    transition_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bt_stage3_transition_readback.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "current_stage": current_stage,
        "target_stage": target_stage,
        "execution_manifest_unlock_minimum": execution_minimum,
        "automated_execution_unlock_minimum": automated_minimum,
        "canonical_docs_read_stage3": docs_stage3,
        "stage3_transition_applied": ready,
        "automated_execution_unlocked": automated_execution_unlocked,
        "live_order_submission_authorized": False,
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bt_stage3_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "stage3_profile_transition": ready,
            "human_approved_execution_manifest_review": ready,
            "stage4_automated_execution": False,
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
        },
    }

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bt_stage3_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "repo_governance_profile_and_docs_readback_only",
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
    readback_path = proof_root / "stage3_profile_transition_readback.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bt_stage3_profile_transition.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "stage3_profile_transition_readback": str(readback_path),
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
        "p9bt_stage3_profile_transition_ready": ready,
        "stage_profile_transition_applied": ready,
        "current_stage": current_stage,
        "target_stage": target_stage,
        "project_stage_allows_human_approved_execution_manifest_review": ready,
        "project_stage_allows_live_order_gate_review": ready,
        "execution_manifest_stage_minimum_satisfied": execution_manifest_stage_ok,
        "automated_execution_unlocked": automated_execution_unlocked,
        "stage4_automated_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": {
            "phase9bs_scope_summary": evidence_file(p9bs_summary_path),
            "project_profile": evidence_file(project_profile_path),
            "stage_contract": evidence_file(stage_contract_path),
            "README.md": evidence_file(resolve_path(args.readme)),
            "AGENTS.md": evidence_file(resolve_path(args.agents)),
            "docs/README_FOR_AGENT.md": evidence_file(resolve_path(args.readme_for_agent)),
            "PROJECT_STATE.md": evidence_file(resolve_path(args.project_state)),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(readback_path, transition_readback)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BT Stage-3 Profile Transition",
                "",
                f"`Status: {summary['status']}`",
                "",
                "## Decision",
                "",
                "P9BT records that the repo profile and canonical docs now read Stage 3 human-approved execution. Stage 4 automated execution, candidate execution, executor mutation, target-plan replacement, timer/supervisor/remote activity, and live orders remain unauthorized.",
                "",
                "```text",
                f"current_stage = {current_stage}",
                f"automated_execution_unlocked = {str(automated_execution_unlocked).lower()}",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bt_stage3_profile_transition(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
