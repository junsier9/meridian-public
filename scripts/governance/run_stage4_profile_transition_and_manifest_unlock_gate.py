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


CONTRACT_VERSION = "project_governance_stage4_profile_transition_and_manifest_unlock_gate.v1"
APPROVE_PROFILE_TRANSITION = (
    "approve_stage4_profile_transition_and_manifest_unlock_apply_stage_advance_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/governance/stage4_profile_transition_and_manifest_unlock_gate"

PROJECT_PROFILE = "config/project_governance/project_profile.json"
STAGE_CONTRACT = "config/project_governance/stage_contract.json"
AGENT_LAYER_MANIFEST = "config/agent_layer_governance/manifest.json"
STAGE3 = "stage_3_human_approved_execution"
STAGE4 = "stage_4_automated_execution"

NEXT_GATE = "Restricted_unattended_gate_only_if_separately_requested"
NEXT_GATE_SCOPE = (
    "set_continuous_automated_order_flow_and_timer_path_load_authorizations_with_"
    "numeric_caps_small_epoch_and_non_self_recovering_disarm_after_stage4_active"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the Stage 4 project-profile transition (current_stage stage_3 -> "
            "stage_4) after the code-gate verification and Stage-4 boundary owner "
            "gates are ready. The agent-layer broad unlock is a SEPARATE axis and is "
            "never touched here. Without --apply this is a dry-run that mutates "
            "nothing. It never enables runtime order flow, timers, supervisors, or "
            "submits orders -- the restricted-unattended gate does that separately."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--stage-contract", default=STAGE_CONTRACT)
    parser.add_argument("--agent-layer-manifest", default=AGENT_LAYER_MANIFEST)
    parser.add_argument("--code-gate-summary", default="")
    parser.add_argument("--stage4-boundary-summary", default="")
    parser.add_argument("--max-evidence-age-seconds", type=float, default=86400.0)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write current_stage=stage_4 to the project profile. Owner-only.",
    )
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_PROFILE_TRANSITION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:stage4_profile_transition_and_manifest_unlock_gate",
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


def load_optional(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        return dict(json.loads(resolved.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stage_index(stage_contract: dict[str, Any], stage_id: str) -> int:
    for index, stage in enumerate(stage_contract.get("stages") or []):
        if dict(stage).get("stage_id") == stage_id:
            return index
    return -1


def _evidence_age_ok(summary: dict[str, Any], now: datetime, max_age_seconds: float) -> bool:
    stamp = str(summary.get("generated_at_utc") or "").strip()
    if not stamp:
        return False
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age = (now - parsed).total_seconds()
    return 0.0 <= age <= float(max_age_seconds)


def build_stage4_profile_transition_and_manifest_unlock_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "stage4_profile_transition" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_path(args.project_profile)
    stage_contract_path = resolve_path(args.stage_contract)
    manifest_path = resolve_path(args.agent_layer_manifest)
    project_profile = load_optional(args.project_profile)
    stage_contract = load_optional(args.stage_contract)
    agent_manifest = load_optional(args.agent_layer_manifest)
    code_gate = load_optional(args.code_gate_summary)
    boundary = load_optional(args.stage4_boundary_summary)

    current_stage = str(project_profile.get("current_stage") or "")
    target_stage = str(project_profile.get("target_stage") or "")
    unlocks = dict(stage_contract.get("unlock_minimum_stages") or {})
    automated_execution_minimum = str(unlocks.get("automated_execution_unlock") or "")
    owner_decision_ok = str(args.owner_decision) == APPROVE_PROFILE_TRANSITION

    checks = {
        "owner_decision_profile_transition_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "stage_contract_exists": bool(stage_contract),
        "agent_layer_manifest_exists": bool(agent_manifest),
        "current_stage_is_stage3": current_stage == STAGE3,
        "target_stage_is_stage4": target_stage == STAGE4,
        "automated_execution_unlock_minimum_is_stage4": automated_execution_minimum == STAGE4,
        "broad_agent_layer_remains_disabled": agent_manifest.get("broad_agent_layer_enabled") is False,
        "code_gate_summary_ready": (
            code_gate.get("status") == "ready"
            and bool(code_gate.get("code_gate_verification_gate_ready"))
        ),
        "code_gate_summary_fresh": _evidence_age_ok(code_gate, now, args.max_evidence_age_seconds),
        "stage4_boundary_summary_ready": (
            boundary.get("status") == "ready"
            and bool(boundary.get("stage4_automated_execution_boundary_owner_gate_ready"))
            and bool(boundary.get("future_stage4_profile_transition_request_allowed"))
        ),
        "stage4_boundary_summary_fresh": _evidence_age_ok(boundary, now, args.max_evidence_age_seconds),
    }
    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers

    # Mutation happens ONLY when ready AND --apply. Without --apply this is a dry-run.
    apply_requested = bool(args.apply)
    applied = False
    post_transition_stage = current_stage
    if ready and apply_requested:
        new_profile = dict(project_profile)
        new_profile["current_stage"] = STAGE4
        write_json(project_profile_path, new_profile)
        applied = True
        post_transition_stage = STAGE4

    status = "ready" if ready else "blocked"

    owner_record = {
        "contract_version": "project_governance_stage4_profile_transition_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "profile_transition_recorded": owner_decision_ok,
        "apply_requested": apply_requested,
        "stage_advance_applied": applied,
        "broad_agent_layer_unlock_in_this_gate": False,
        "runtime_order_flow_enablement_approved_now": False,
    }

    non_authorization = {
        "contract_version": "project_governance_stage4_profile_transition_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "stage4_profile_transition_recorded": ready,
            "stage_advance_applied": applied,
            "restricted_unattended_gate_request_allowed": ready,
            "broad_agent_layer_enablement_in_this_gate": False,
            "continuous_automated_order_flow": False,
            "timer_path_load": False,
            "live_order_submission": False,
            "candidate_execution": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }

    control = {
        "contract_version": "project_governance_stage4_profile_transition_control_readback.v1",
        "run_id": run_id,
        "scope": "stage_advance_only_no_runtime_enablement",
        "apply_requested": apply_requested,
        "project_profile_changed": applied,
        "agent_layer_manifest_changed": False,
        "broad_agent_layer_enabled_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "live_order_submission_performed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "transition_readback": str(proof_root / "transition_readback.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "stage4_profile_transition_and_manifest_unlock_gate.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": status,
        "blockers": blockers,
        "stage4_profile_transition_gate_ready": ready,
        "apply_requested": apply_requested,
        "stage_advance_applied": applied,
        "pre_transition_stage": current_stage,
        "post_transition_stage": post_transition_stage,
        "target_stage": target_stage,
        "automated_execution_stage_unlocked": post_transition_stage == STAGE4,
        "broad_agent_layer_enablement_performed": False,
        "continuous_automated_order_flow_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "allowed_next_gate": NEXT_GATE if (ready and applied) else "",
        "allowed_next_gate_scope": NEXT_GATE_SCOPE if (ready and applied) else "",
        "allowed_next_gate_must_be_separately_requested": ready and applied,
        "source_evidence": {
            "project_profile": evidence_file(args.project_profile),
            "stage_contract": evidence_file(args.stage_contract),
            "agent_layer_manifest": evidence_file(args.agent_layer_manifest),
            "code_gate_summary": evidence_file(args.code_gate_summary),
            "stage4_boundary_summary": evidence_file(args.stage4_boundary_summary),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(
        Path(output_files["transition_readback"]),
        {
            "contract_version": "project_governance_stage4_profile_transition_readback.v1",
            "run_id": run_id,
            "pre_transition_stage": current_stage,
            "post_transition_stage": post_transition_stage,
            "applied": applied,
            "checks": checks,
            "blockers": blockers,
        },
    )
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Stage 4 Profile Transition and Manifest Unlock Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "Advances `current_stage` stage_3 -> stage_4 (the automated-execution stage "
        "unlock) only when the code-gate verification and Stage-4 boundary owner gates "
        "are ready. The agent-layer broad unlock is a separate axis and is untouched. "
        "Without --apply nothing is mutated. No runtime order flow is enabled here.",
        "",
        "## Transition",
        "",
        "```text",
        f"stage4_profile_transition_gate_ready = {str(bool(summary['stage4_profile_transition_gate_ready'])).lower()}",
        f"apply_requested = {str(bool(summary['apply_requested'])).lower()}",
        f"stage_advance_applied = {str(bool(summary['stage_advance_applied'])).lower()}",
        f"pre_transition_stage = {summary['pre_transition_stage']}",
        f"post_transition_stage = {summary['post_transition_stage']}",
        "continuous_automated_order_flow_authorized = false",
        "timer_path_load_authorized = false",
        "orders_submitted = 0",
        "```",
        "",
        "## Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        f"allowed_next_gate_must_be_separately_requested = {str(bool(summary['allowed_next_gate_must_be_separately_requested'])).lower()}",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_stage4_profile_transition_and_manifest_unlock_gate(parse_args(argv))
    print(
        "stage4_profile_transition_gate_ready="
        + str(bool(summary["stage4_profile_transition_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"stage_advance_applied={str(bool(summary['stage_advance_applied'])).lower()}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
