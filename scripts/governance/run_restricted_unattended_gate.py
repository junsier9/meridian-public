from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


CONTRACT_VERSION = "project_governance_restricted_unattended_gate.v1"
APPROVE_RESTRICTED_UNATTENDED = (
    "approve_restricted_unattended_continuous_order_flow_with_caps_and_terminal_disarm"
)
DEFAULT_OUTPUT_PARENT = "artifacts/governance/restricted_unattended_gate"

PROJECT_PROFILE = "config/project_governance/project_profile.json"
STAGE4 = "stage_4_automated_execution"
BUDGET_GATE_FLAG = "unattended_budget_gate_enabled"  # under core_loop
PER_ORDER_GATE_FLAG = "per_order_notional_gate_enabled"  # under risk

NEXT_GATE = (
    "Owner_manual_live_delta_arm_with_gate_flags_already_on_only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "owner_flips_the_sqlite_live_delta_armed_flag_after_this_authorization_and_only_"
    "while_the_budget_and_per_order_gate_flags_are_on_and_a_small_epoch_is_open"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Authorize restricted-unattended continuous automated order flow + timer "
            "path load, only after stage_4 is active, the budget + per-order gate flags "
            "are ON in the host-loaded config, a small budget epoch is open, the host "
            "load-source is proven, and the terminal (non-self-recovering) budget disarm "
            "is confirmed. Without --apply this is a dry-run that authorizes nothing. "
            "This gate does NOT arm live_delta or submit orders -- the owner flips the "
            "SQLite live_delta_armed flag separately, with these gate flags already on."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--host-config", default="")
    parser.add_argument("--profile-transition-summary", default="")
    parser.add_argument("--epoch-summary", default="")
    parser.add_argument("--max-live-cycles-ceiling", type=int, default=6)
    parser.add_argument("--max-age-seconds-ceiling", type=float, default=3600.0)
    parser.add_argument("--max-cycles-before-human-review", type=int, default=6)
    parser.add_argument("--max-evidence-age-seconds", type=float, default=86400.0)
    parser.add_argument("--host-load-source-proven", action="store_true")
    parser.add_argument("--terminal-budget-disarm-confirmed", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Emit the authorization record with the continuous-flow / timer-load flags true. Owner-only.",
    )
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_RESTRICTED_UNATTENDED)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:restricted_unattended_gate",
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


def load_json_optional(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        return dict(json.loads(resolved.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def load_yaml_optional(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    import math

    return result if math.isfinite(result) else None


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


def build_restricted_unattended_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "restricted_unattended" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile = load_json_optional(args.project_profile)
    host_config = load_yaml_optional(args.host_config)
    transition = load_json_optional(args.profile_transition_summary)
    epoch = load_json_optional(args.epoch_summary)

    current_stage = str(project_profile.get("current_stage") or "")
    core_loop = dict(host_config.get("core_loop") or {})
    risk = dict(host_config.get("risk") or {})
    budget_gate_on = _as_bool(core_loop.get(BUDGET_GATE_FLAG))
    per_order_gate_on = _as_bool(risk.get(PER_ORDER_GATE_FLAG))

    epoch_status = str(epoch.get("status") or "").strip().lower()
    epoch_cycles = _finite(epoch.get("max_live_cycles"))
    epoch_age = _finite(epoch.get("max_age_seconds"))
    epoch_turnover = _finite(epoch.get("max_gross_turnover_usdt"))
    owner_decision_ok = str(args.owner_decision) == APPROVE_RESTRICTED_UNATTENDED

    checks = {
        "owner_decision_restricted_unattended_recorded": owner_decision_ok,
        "stage4_active": current_stage == STAGE4,
        "profile_transition_summary_ready": (
            transition.get("status") == "ready"
            and bool(transition.get("stage_advance_applied"))
        ),
        "profile_transition_summary_fresh": _evidence_age_ok(transition, now, args.max_evidence_age_seconds),
        "host_config_present": bool(host_config),
        "host_budget_gate_enabled": budget_gate_on,
        "host_per_order_gate_enabled": per_order_gate_on,
        "host_load_source_proven": bool(args.host_load_source_proven),
        "terminal_budget_disarm_confirmed": bool(args.terminal_budget_disarm_confirmed),
        "budget_epoch_open": epoch_status == "open",
        "epoch_cycles_within_ceiling": (
            epoch_cycles is not None and 0 < epoch_cycles <= float(args.max_live_cycles_ceiling)
        ),
        "epoch_age_within_ceiling": (
            epoch_age is not None and 0 < epoch_age <= float(args.max_age_seconds_ceiling)
        ),
        "epoch_turnover_bounded": epoch_turnover is not None and epoch_turnover > 0.0,
        "epoch_cycles_within_human_review_cadence": (
            epoch_cycles is not None and epoch_cycles <= float(args.max_cycles_before_human_review)
        ),
    }
    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers

    apply_requested = bool(args.apply)
    authorized = ready and apply_requested
    status = "ready" if ready else "blocked"

    owner_record = {
        "contract_version": "project_governance_restricted_unattended_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "restricted_unattended_recorded": owner_decision_ok,
        "apply_requested": apply_requested,
        "continuous_automated_order_flow_authorized": authorized,
        "timer_path_load_authorized": authorized,
        "max_cycles_before_human_review": int(args.max_cycles_before_human_review),
        "live_delta_arm_performed_in_this_gate": False,
        "order_submission_in_this_gate": False,
    }

    authorization = {
        "contract_version": "project_governance_restricted_unattended_authorization.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "continuous_automated_order_flow_authorized": authorized,
        "timer_path_load_authorized": authorized,
        "authorization_scope": "restricted_unattended_bounded_by_open_epoch_and_per_order_ceiling",
        "max_cycles_before_human_review": int(args.max_cycles_before_human_review),
        "epoch_max_live_cycles": epoch_cycles,
        "epoch_max_age_seconds": epoch_age,
        "epoch_max_gross_turnover_usdt": epoch_turnover,
        "non_self_recovering_budget_disarm_confirmed": bool(args.terminal_budget_disarm_confirmed),
        "remaining_owner_action": (
            "flip the SQLite live_delta_armed flag manually; the budget + per-order gate "
            "flags must already be on (they are verified here) and a small epoch open"
        ),
        "live_delta_armed_in_this_gate": False,
        "orders_submitted": 0,
    }

    non_authorization = {
        "contract_version": "project_governance_restricted_unattended_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "restricted_unattended_authorization_recorded": authorized,
            "continuous_automated_order_flow": authorized,
            "timer_path_load": authorized,
            # This gate never performs the arm or any order itself.
            "live_delta_arm_in_this_gate": False,
            "live_order_submission_in_this_gate": False,
            "candidate_execution_in_this_gate": False,
            "supervisor_invocation_in_this_gate": False,
            "remote_sync_in_this_gate": False,
            "host_config_mutation_in_this_gate": False,
            "epoch_mutation_in_this_gate": False,
        },
    }

    control = {
        "contract_version": "project_governance_restricted_unattended_control_readback.v1",
        "run_id": run_id,
        "scope": "authorization_record_only_no_arm_no_order",
        "host_config_changed": False,
        "epoch_changed": False,
        "live_delta_armed": False,
        "ran_supervisor": False,
        "entered_timer_path": False,
        "remote_sync_performed": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "restricted_unattended_authorization": str(proof_root / "restricted_unattended_authorization.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "restricted_unattended_gate.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": status,
        "blockers": blockers,
        "restricted_unattended_gate_ready": ready,
        "apply_requested": apply_requested,
        "continuous_automated_order_flow_authorized": authorized,
        "timer_path_load_authorized": authorized,
        "max_cycles_before_human_review": int(args.max_cycles_before_human_review),
        "epoch_max_live_cycles": epoch_cycles,
        "epoch_max_age_seconds": epoch_age,
        "epoch_max_gross_turnover_usdt": epoch_turnover,
        "non_self_recovering_budget_disarm_confirmed": bool(args.terminal_budget_disarm_confirmed),
        "host_load_source_proven": bool(args.host_load_source_proven),
        "live_delta_armed_in_this_gate": False,
        "live_order_submission_authorized": False,  # arming is a separate manual owner action
        "orders_submitted": 0,
        "fill_count": 0,
        "allowed_next_gate": NEXT_GATE if authorized else "",
        "allowed_next_gate_scope": NEXT_GATE_SCOPE if authorized else "",
        "allowed_next_gate_must_be_separately_requested": authorized,
        "source_evidence": {
            "project_profile": evidence_file(args.project_profile),
            "host_config": evidence_file(args.host_config),
            "profile_transition_summary": evidence_file(args.profile_transition_summary),
            "epoch_summary": evidence_file(args.epoch_summary),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["restricted_unattended_authorization"]), authorization)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Restricted-Unattended Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "Authorizes restricted-unattended continuous automated order flow + timer path "
        "load, bounded by a small open budget epoch and the per-order notional ceiling, "
        "with a non-self-recovering budget disarm. Verifies stage_4 is active and that "
        "the budget + per-order gate flags are ON in the host-loaded config. Without "
        "--apply nothing is authorized. This gate never arms live_delta or submits orders.",
        "",
        "## Authorization",
        "",
        "```text",
        f"restricted_unattended_gate_ready = {str(bool(summary['restricted_unattended_gate_ready'])).lower()}",
        f"apply_requested = {str(bool(summary['apply_requested'])).lower()}",
        f"continuous_automated_order_flow_authorized = {str(bool(summary['continuous_automated_order_flow_authorized'])).lower()}",
        f"timer_path_load_authorized = {str(bool(summary['timer_path_load_authorized'])).lower()}",
        f"max_cycles_before_human_review = {summary['max_cycles_before_human_review']}",
        f"epoch_max_live_cycles = {summary['epoch_max_live_cycles']}",
        f"epoch_max_age_seconds = {summary['epoch_max_age_seconds']}",
        f"non_self_recovering_budget_disarm_confirmed = {str(bool(summary['non_self_recovering_budget_disarm_confirmed'])).lower()}",
        "live_delta_armed_in_this_gate = false",
        "orders_submitted = 0",
        "```",
        "",
        "## Remaining owner action (outside this gate)",
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
    summary, exit_code = build_restricted_unattended_gate(parse_args(argv))
    print(
        "restricted_unattended_gate_ready="
        + str(bool(summary["restricted_unattended_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(
        "continuous_automated_order_flow_authorized="
        + str(bool(summary["continuous_automated_order_flow_authorized"])).lower()
    )
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
