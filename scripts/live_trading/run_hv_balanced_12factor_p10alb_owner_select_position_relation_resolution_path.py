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


CONTRACT_VERSION = "hv_balanced_12factor_p10alb_owner_select_position_relation_resolution_path.v1"
APPROVE_P10ALB = (
    "approve_p10alb_owner_select_candidate_position_relation_resolution_path_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/proof_artifacts/p10alb_owner_select_position_relation_resolution_path"
)

P10ALB_GATE = (
    "P10ALB_owner_select_candidate_position_relation_resolution_path_only_if_separately_requested"
)

# The three resolution paths prepared by the p10akz proposal; the owner selects exactly one.
VALID_PATHS = ("wait_for_executable_relation", "target_plan_position_alignment_refresh", "separate_reduce_only_reduction_canary")

# What each selected path authorizes as its (separately-requested) follow-up gate.
NEXT_GATE_BY_PATH: dict[str, str] = {
    "wait_for_executable_relation": (
        "Rerun_read_only_position_relation_proof_until_relation_flat_or_same_direction_"
        "only_if_separately_requested"
    ),
    "target_plan_position_alignment_refresh": (
        "Regenerate_candidate_target_plan_replacement_against_current_position_then_rerun_"
        "parity_only_if_separately_requested"
    ),
    "separate_reduce_only_reduction_canary": (
        "Define_owner_approved_reduce_only_reduction_canary_terms_only_if_separately_requested"
    ),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record the owner's selection of ONE candidate-side-vs-existing-position "
            "resolution path from the p10akz proposal. Proof-only: it reads the p10ala "
            "review summary, records the chosen path, and authorizes nothing -- no remote "
            "read, no order/cancel, no timer/supervisor, no live config/operator/executor "
            "mutation. The selected path's follow-up is a separate gate."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10ala-summary", default="")
    parser.add_argument("--selected-path", default="", choices=("", *VALID_PATHS))
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10ALB)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p10alb_owner_select_position_relation_resolution_path",
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


def no_execution_matrix() -> dict[str, Any]:
    return {
        "remote_api_called": False,
        "live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fills_observed": 0,
        "timer_path_load_authorized": False,
        "supervisor_invoked": False,
        "candidate_executed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "continuous_automated_order_flow_authorized": False,
    }


def build_p10alb_owner_select_path(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof"
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p10ala = load_optional(args.p10ala_summary)
    selected = str(args.selected_path or "").strip()
    owner_decision_ok = str(args.owner_decision) == APPROVE_P10ALB

    checks = {
        "owner_decision_p10alb_recorded": owner_decision_ok,
        "p10ala_review_ready": (
            p10ala.get("status") == "ready"
            and str(p10ala.get("allowed_next_gate") or "") == P10ALB_GATE
        ),
        "p10ala_requires_path_selection": bool(p10ala.get("resolution_path_selection_required")),
        "selected_path_is_one_of_three": selected in VALID_PATHS,
    }
    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers
    status = "ready" if ready else "blocked"

    next_gate = NEXT_GATE_BY_PATH.get(selected, "") if ready else ""

    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10alb_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "selected_resolution_path": selected if ready else "",
        "path_selection_only": True,
        "authorizes_selected_path_followup_gate": ready,
        "authorizes_live_order": False,
        "authorizes_remote_read": False,
    }

    selection = {
        "contract_version": "hv_balanced_12factor_p10alb_path_selection.v1",
        "status": status,
        "blockers": blockers,
        "selected_resolution_path": selected if ready else "",
        "available_paths": list(VALID_PATHS),
        "selected_path_followup_gate": next_gate,
        "does_not_authorize": [
            "the selected path's follow-up actions (separate gate)",
            "live order or cancel",
            "remote account read",
            "timer/supervisor path load",
            "live config / operator / executor mutation",
        ],
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision": str(proof_root / "owner_decision.json"),
        "path_selection": str(proof_root / "path_selection.json"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10alb_owner_path_selection_ready": ready,
        "resolution_path_selected": ready,
        "selected_resolution_path": selected if ready else "",
        "available_paths": list(VALID_PATHS),
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {"p10ala_summary": evidence_file(args.p10ala_summary)},
        "allowed_next_gate": next_gate,
        "allowed_next_gate_scope": (
            f"follow_up_for_selected_path:{selected}_no_order_no_remote_no_timer" if ready else ""
        ),
        "allowed_next_gate_must_be_separately_requested": ready,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision"]), owner_decision)
    write_json(Path(output_files["path_selection"]), selection)
    write_json(Path(output_files["summary"]), summary)
    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p10alb_owner_select_path(parse_args(argv))
    print(f"p10alb_owner_path_selection_ready={str(bool(summary['p10alb_owner_path_selection_ready'])).lower()}")
    print(f"status={summary['status']}")
    print(f"selected_resolution_path={summary['selected_resolution_path']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
