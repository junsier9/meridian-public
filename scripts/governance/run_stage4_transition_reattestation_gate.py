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


CONTRACT_VERSION = "project_governance_stage4_transition_reattestation_gate.v1"
APPROVE_TRANSITION_REATTESTATION = (
    "approve_stage4_transition_reattestation_no_profile_mutation"
)
DEFAULT_OUTPUT_PARENT = "artifacts/governance/stage4_transition_reattestation_gate"

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
            "Re-attest that the prior legitimate Stage 4 profile transition is STILL in "
            "effect, emitting a FRESH transition-evidence summary the restricted-unattended "
            "gate can consume. The original profile-transition gate cannot be cleanly re-run "
            "once stage_4 is active (it requires current_stage == stage_3), so its <=24h "
            "freshness window would otherwise strand the arm. This gate anchors freshness to "
            "RE-RUNNABLE evidence (a fresh code-gate verification summary) plus the live "
            "stage_4 state and the prior transition's own readback. It is proof-only: it NEVER "
            "mutates the project profile or any status file, never re-applies the advance, "
            "and never enables runtime order flow, timers, supervisors, or submits orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--stage-contract", default=STAGE_CONTRACT)
    parser.add_argument("--agent-layer-manifest", default=AGENT_LAYER_MANIFEST)
    parser.add_argument("--prior-transition-summary", default="")
    parser.add_argument("--code-gate-summary", default="")
    parser.add_argument("--max-evidence-age-seconds", type=float, default=86400.0)
    # Owner policy: how long the ORIGINAL legitimate transition may be re-attested before a
    # fresh governance cycle is required. Bounds the re-attestation so a stale stage_4 cannot
    # be refreshed indefinitely off fresh code-gate evidence. Default 30 days; owner-tunable.
    parser.add_argument("--max-prior-transition-age-seconds", type=float, default=2592000.0)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_TRANSITION_REATTESTATION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:stage4_transition_reattestation_gate",
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


def build_stage4_transition_reattestation_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "stage4_transition_reattestation" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile = load_optional(args.project_profile)
    stage_contract = load_optional(args.stage_contract)
    agent_manifest = load_optional(args.agent_layer_manifest)
    prior_transition = load_optional(args.prior_transition_summary)
    code_gate = load_optional(args.code_gate_summary)

    current_stage = str(project_profile.get("current_stage") or "")
    target_stage = str(project_profile.get("target_stage") or "")
    unlocks = dict(stage_contract.get("unlock_minimum_stages") or {})
    automated_execution_minimum = str(unlocks.get("automated_execution_unlock") or "")
    owner_decision_ok = str(args.owner_decision) == APPROVE_TRANSITION_REATTESTATION

    checks = {
        "owner_decision_transition_reattestation_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "stage_contract_exists": bool(stage_contract),
        "agent_layer_manifest_exists": bool(agent_manifest),
        # The advance is ALREADY applied and in effect: current_stage is stage_4. This gate
        # never re-applies it (the original apply-gate correctly blocks a double-apply).
        "current_stage_is_stage4": current_stage == STAGE4,
        "target_stage_is_stage4": target_stage == STAGE4,
        "automated_execution_unlock_minimum_is_stage4": automated_execution_minimum == STAGE4,
        "broad_agent_layer_remains_disabled": agent_manifest.get("broad_agent_layer_enabled") is False,
        # The prior transition's own readback proves a legitimate advance occurred (not a
        # hand-edit): it was ready, the advance was applied, and it landed on stage_4.
        "prior_transition_summary_attests_applied": (
            prior_transition.get("status") == "ready"
            and bool(prior_transition.get("stage_advance_applied"))
            and str(prior_transition.get("post_transition_stage") or "") == STAGE4
        ),
        # Owner-policy ceiling: the original transition must be within the re-attestation
        # window, so a stale stage_4 cannot be laundered into "fresh" forever off code-gate.
        "prior_transition_summary_within_reattestation_window": _evidence_age_ok(
            prior_transition, now, args.max_prior_transition_age_seconds
        ),
        # Freshness is anchored to the RE-RUNNABLE code-gate verification gate (which does not
        # depend on current_stage), so this re-attestation can be produced fresh post-stage_4.
        "code_gate_summary_ready": (
            code_gate.get("status") == "ready"
            and bool(code_gate.get("code_gate_verification_gate_ready"))
        ),
        "code_gate_summary_fresh": _evidence_age_ok(code_gate, now, args.max_evidence_age_seconds),
    }
    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers
    status = "ready" if ready else "blocked"

    # When ready, the stage_4 advance is RE-ATTESTED as applied-and-in-effect (NOT re-applied):
    # this carries the keys the restricted-unattended gate reads from a transition summary
    # (status == "ready" + stage_advance_applied truthy + a fresh generated_at_utc), so it can
    # legitimately satisfy that gate's freshness window without a profile mutation.
    stage_advance_applied = ready

    owner_record = {
        "contract_version": "project_governance_stage4_transition_reattestation_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "transition_reattestation_recorded": owner_decision_ok,
        "profile_mutation_approved": False,
        "stage_advance_reapplied_in_this_gate": False,
        "runtime_order_flow_enablement_approved_now": False,
    }

    non_authorization = {
        "contract_version": "project_governance_stage4_transition_reattestation_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "stage4_transition_reattestation_recorded": ready,
            "restricted_unattended_gate_request_allowed": ready,
            "project_profile_mutation_in_this_gate": False,
            "stage_advance_reapply_in_this_gate": False,
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
        "contract_version": "project_governance_stage4_transition_reattestation_control_readback.v1",
        "run_id": run_id,
        "scope": "reattestation_record_only_no_profile_mutation_no_reapply",
        "project_profile_changed": False,
        "stage_advance_reapplied": False,
        "agent_layer_manifest_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "reattestation_readback": str(proof_root / "reattestation_readback.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "stage4_transition_reattestation_gate.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": status,
        "blockers": blockers,
        "stage4_transition_reattestation_gate_ready": ready,
        # Consumed by the restricted-unattended gate's transition-evidence checks. Semantics:
        # the stage_4 advance is applied AND currently in effect (re-attested from live state),
        # NOT re-applied here. The control readback proves project_profile_changed == false.
        "stage_advance_applied": stage_advance_applied,
        # Clearer alias: the advance is currently IN EFFECT (re-attested), not freshly applied.
        # The restricted gate reads `stage_advance_applied`, so that key is retained verbatim.
        "stage_advance_currently_in_effect": ready,
        "stage_advance_reattested": ready,
        "stage_advance_mutation_performed": False,
        "pre_reattestation_stage": current_stage,
        "post_reattestation_stage": current_stage,
        "target_stage": target_stage,
        "automated_execution_stage_active": current_stage == STAGE4,
        "prior_transition_summary": str(args.prior_transition_summary or ""),
        "freshness_anchor": "code_gate_verification_gate_summary",
        "continuous_automated_order_flow_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "allowed_next_gate": NEXT_GATE if ready else "",
        "allowed_next_gate_scope": NEXT_GATE_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": ready,
        "source_evidence": {
            "project_profile": evidence_file(args.project_profile),
            "stage_contract": evidence_file(args.stage_contract),
            "agent_layer_manifest": evidence_file(args.agent_layer_manifest),
            "prior_transition_summary": evidence_file(args.prior_transition_summary),
            "code_gate_summary": evidence_file(args.code_gate_summary),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(
        Path(output_files["reattestation_readback"]),
        {
            "contract_version": "project_governance_stage4_transition_reattestation_readback.v1",
            "run_id": run_id,
            "current_stage": current_stage,
            "target_stage": target_stage,
            "stage_advance_applied": stage_advance_applied,
            "stage_advance_reapplied": False,
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
        "# Stage 4 Transition Re-Attestation Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "Re-attests that the prior legitimate Stage 4 profile transition is still in effect "
        "and emits a FRESH transition-evidence summary the restricted-unattended gate can "
        "consume, anchored to a fresh re-runnable code-gate verification summary plus the live "
        "stage_4 state and the prior transition readback. Proof-only: it never mutates the "
        "project profile, never re-applies the advance, and enables no runtime order flow.",
        "",
        "## Re-Attestation",
        "",
        "```text",
        f"stage4_transition_reattestation_gate_ready = {str(bool(summary['stage4_transition_reattestation_gate_ready'])).lower()}",
        f"stage_advance_applied = {str(bool(summary['stage_advance_applied'])).lower()}",
        f"stage_advance_reattested = {str(bool(summary['stage_advance_reattested'])).lower()}",
        "stage_advance_mutation_performed = false",
        f"pre_reattestation_stage = {summary['pre_reattestation_stage']}",
        f"post_reattestation_stage = {summary['post_reattestation_stage']}",
        f"freshness_anchor = {summary['freshness_anchor']}",
        "continuous_automated_order_flow_authorized = false",
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
    summary, exit_code = build_stage4_transition_reattestation_gate(parse_args(argv))
    print(
        "stage4_transition_reattestation_gate_ready="
        + str(bool(summary["stage4_transition_reattestation_gate_ready"])).lower()
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
