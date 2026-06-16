from __future__ import annotations

import argparse
import hashlib
import json
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


CONTRACT_VERSION = "project_governance_stage4_automated_execution_boundary_owner_gate.v1"
APPROVE_STAGE4_BOUNDARY_DECISION = (
    "approve_stage4_automated_execution_boundary_owner_gate_only_no_runtime_enablement"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/governance/stage4_automated_execution_boundary_owner_gate"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
STAGE_CONTRACT = "config/project_governance/stage_contract.json"
RUNTIME_OWNERSHIP_CONTRACT = "config/project_governance/runtime_ownership_contract.json"
AGENT_LAYER_MANIFEST = "config/agent_layer_governance/manifest.json"
STAGE3 = "stage_3_human_approved_execution"
STAGE4 = "stage_4_automated_execution"
NEXT_GATE = (
    "Stage4_project_profile_transition_and_automated_execution_manifest_unlock_gate_"
    "only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "apply_stage4_profile_transition_and_manifest_unlocks_after_fresh_readbacks_"
    "without_live_runtime_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a separate owner gate for the Stage 4 / automated execution "
            "boundary. This gate is governance-only: it does not mutate the "
            "project profile, unlock manifests, invoke timers or supervisors, "
            "remote sync, execute candidates, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--stage-contract", default=STAGE_CONTRACT)
    parser.add_argument(
        "--runtime-ownership-contract", default=RUNTIME_OWNERSHIP_CONTRACT
    )
    parser.add_argument("--agent-layer-manifest", default=AGENT_LAYER_MANIFEST)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_STAGE4_BOUNDARY_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:approve_stage4_automated_execution_boundary_owner_gate",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def load_optional(path: str | Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    with resolved.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def stage_index(stage_contract: dict[str, Any], stage_id: str) -> int:
    for index, stage in enumerate(stage_contract.get("stages") or []):
        if dict(stage).get("stage_id") == stage_id:
            return index
    return -1


def stage_at_least(stage_contract: dict[str, Any], current: str, minimum: str) -> bool:
    current_index = stage_index(stage_contract, current)
    minimum_index = stage_index(stage_contract, minimum)
    return current_index >= 0 and minimum_index >= 0 and current_index >= minimum_index


def build_stage4_automated_execution_boundary_owner_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "stage4_boundary" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_path(args.project_profile)
    stage_contract_path = resolve_path(args.stage_contract)
    runtime_contract_path = resolve_path(args.runtime_ownership_contract)
    manifest_path = resolve_path(args.agent_layer_manifest)
    project_profile = load_optional(project_profile_path)
    stage_contract = load_optional(stage_contract_path)
    runtime_contract = load_optional(runtime_contract_path)
    agent_manifest = load_optional(manifest_path)

    current_stage = str(project_profile.get("current_stage") or "")
    target_stage = str(project_profile.get("target_stage") or "")
    unlocks = dict(stage_contract.get("unlock_minimum_stages") or {})
    execution_manifest_minimum = str(unlocks.get("execution_manifest_unlock") or "")
    automated_execution_minimum = str(unlocks.get("automated_execution_unlock") or "")
    automated_execution_unlocked_now = stage_at_least(
        stage_contract, current_stage, automated_execution_minimum
    )
    owner_decision_ok = str(args.owner_decision) == APPROVE_STAGE4_BOUNDARY_DECISION

    checks = {
        "owner_decision_stage4_boundary_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "stage_contract_exists": bool(stage_contract),
        "runtime_ownership_contract_exists": bool(runtime_contract),
        "agent_layer_manifest_exists": bool(agent_manifest),
        "current_stage_is_stage3_human_approved_execution": current_stage == STAGE3,
        "target_stage_is_stage4_automated_execution": target_stage == STAGE4,
        "execution_manifest_unlock_minimum_is_stage3": execution_manifest_minimum == STAGE3,
        "automated_execution_unlock_minimum_is_stage4": automated_execution_minimum == STAGE4,
        "automated_execution_not_unlocked_by_current_stage": not automated_execution_unlocked_now,
        "owner_verification_required": runtime_contract.get("owner_verification_required") is True,
        "owner_verification_enforced_in_boundary_gates": (
            runtime_contract.get("owner_verification_enforced_in_boundary_gates") is True
        ),
        "broad_agent_layer_remains_disabled": (
            agent_manifest.get("broad_agent_layer_enabled") is False
        ),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "project_governance_stage4_boundary_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": (
            "approve_stage4_automated_execution_boundary_as_separate_owner_gate_"
            "without_runtime_enablement"
        ),
        "recorded_at_utc": iso_z(now),
        "stage4_automated_execution_boundary_owner_approval_collected": owner_decision_ok,
        "future_stage4_profile_transition_request_allowed_if_ready": ready,
        "project_profile_mutation_approved_in_this_gate": False,
        "automated_execution_runtime_enablement_approved_now": False,
        "continuous_automated_order_flow_approved": False,
        "live_order_submission_approved": False,
        "timer_or_service_enablement_approved": False,
        "supervisor_invocation_approved": False,
    }

    boundary_readback = {
        "contract_version": "project_governance_stage4_boundary_readback.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "current_stage": current_stage,
        "target_stage": target_stage,
        "execution_manifest_unlock_minimum": execution_manifest_minimum,
        "automated_execution_unlock_minimum": automated_execution_minimum,
        "stage4_automated_execution_boundary_owner_approval_collected": ready,
        "stage4_boundary_approval_effective_for_future_transition": ready,
        "stage4_currently_active": current_stage == STAGE4,
        "automated_execution_unlocked_now": automated_execution_unlocked_now,
        "automated_execution_runtime_enablement_authorized_now": False,
        "required_followup_gates_before_automation_runtime_enablement": [
            "separate Stage 4 project profile transition gate",
            "separate automated execution manifest unlock gate",
            "fresh owner verification boundary readback",
            "fresh operator/timer/supervisor control readback",
            "separate live-order or automated-order-flow gate with exact scope",
        ],
    }

    non_authorization = {
        "contract_version": "project_governance_stage4_boundary_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "stage4_automated_execution_boundary_owner_approval_recorded": ready,
            "future_stage4_profile_transition_request_allowed": ready,
            "project_profile_mutation_in_this_gate": False,
            "stage_governance_change_in_this_gate": False,
            "automated_execution_manifest_unlock_in_this_gate": False,
            "broad_agent_layer_enablement_in_this_gate": False,
            "continuous_automated_order_flow": False,
            "live_order_submission": False,
            "candidate_execution": False,
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

    control = {
        "contract_version": "project_governance_stage4_boundary_control_readback.v1",
        "run_id": run_id,
        "scope": "owner_gate_record_only_no_runtime_enablement",
        "project_profile_changed": False,
        "stage_contract_changed": False,
        "agent_layer_manifest_changed": False,
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

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "stage4_boundary_readback": str(proof_root / "stage4_boundary_readback.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "stage4_automated_execution_boundary_owner_gate.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "stage4_automated_execution_boundary_owner_gate_ready": ready,
        "stage4_automated_execution_boundary_owner_approval_collected": ready,
        "stage4_boundary_approval_scope": "future_stage4_transition_only_no_runtime_enablement",
        "current_stage": current_stage,
        "target_stage": target_stage,
        "execution_manifest_stage_minimum_satisfied": stage_at_least(
            stage_contract, current_stage, execution_manifest_minimum
        ),
        "automated_execution_unlocked_now": automated_execution_unlocked_now,
        "stage4_automated_execution_authorized_now": False,
        "future_stage4_profile_transition_request_allowed": ready,
        "allowed_next_gate": NEXT_GATE,
        "allowed_next_gate_scope": NEXT_GATE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "project_profile_mutation_performed": False,
        "stage_governance_change_performed": False,
        "automated_execution_manifest_unlock_performed": False,
        "broad_agent_layer_enablement_performed": False,
        "continuous_automated_order_flow_authorized": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
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
            "project_profile": evidence_file(project_profile_path),
            "stage_contract": evidence_file(stage_contract_path),
            "runtime_ownership_contract": evidence_file(runtime_contract_path),
            "agent_layer_manifest": evidence_file(manifest_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["stage4_boundary_readback"]), boundary_readback)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Stage 4 Automated Execution Boundary Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "This gate records a separate owner approval for the Stage 4 / automated execution boundary. It does not change the project profile, unlock manifests, enable timers or services, invoke supervisors, remote sync, execute candidates, or submit orders.",
        "",
        "## Decision",
        "",
        "```text",
        (
            "stage4_automated_execution_boundary_owner_approval_collected = "
            f"{str(bool(summary['stage4_automated_execution_boundary_owner_approval_collected'])).lower()}"
        ),
        f"current_stage = {summary['current_stage']}",
        f"target_stage = {summary['target_stage']}",
        (
            "automated_execution_unlocked_now = "
            f"{str(bool(summary['automated_execution_unlocked_now'])).lower()}"
        ),
        "stage4_automated_execution_authorized_now = false",
        "project_profile_mutation_performed = false",
        "continuous_automated_order_flow_authorized = false",
        "live_order_submission_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_stage4_automated_execution_boundary_owner_gate(
        parse_args(argv)
    )
    print(
        "stage4_automated_execution_boundary_owner_gate_ready="
        + str(bool(summary["stage4_automated_execution_boundary_owner_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
