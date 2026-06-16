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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9c_owner_decision.v1"
APPROVE_P9C_IMPLEMENTATION_DECISION = "approve_p9c_observe_only_hook_implementation"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9c_owner_decision"
)
PHASE9C_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9c_owner_shadow_hook_review"
)
PHASE9R_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9r_research_to_live_parity"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record the owner P9C decision. This only authorizes default-off "
            "observe-only hook implementation work when retained P9C/P9R "
            "proof gates are ready. It never deploys a hook, loads timer path, "
            "mutates executor input, or authorizes orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9c-summary", default="")
    parser.add_argument("--phase9r-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--decision", default=APPROVE_P9C_IMPLEMENTATION_DECISION)
    parser.add_argument(
        "--decision-source",
        default="user_chat:approve_p9c_observe_only_hook_implementation",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def latest_match(parent: str, pattern: str) -> Path:
    root = resolve_path(parent)
    matches = [path for path in root.glob(pattern) if path.is_file()]
    if not matches:
        return Path("")
    return sorted(matches, key=lambda path: (path.stat().st_mtime, str(path)))[-1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with resolve_path(path).open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def load_optional(path: Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    return load_json(resolved) if resolved.exists() else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_file(path: Path) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def row_parity_zero(p9r: dict[str, Any]) -> bool:
    row = dict(p9r.get("row_parity") or {})
    return all(
        int(row.get(key) or 0) == 0
        for key in (
            "trigger_mismatch_count",
            "multiplier_mismatch_count",
            "target_contribution_mismatch_count",
            "score_mismatch_count",
        )
    )


def p9r_research_parity_ready(p9r: dict[str, Any]) -> bool:
    target = dict(p9r.get("target_weight_parity") or {})
    slices = dict(p9r.get("slice_metric_parity") or {})
    retained = dict(p9r.get("retained_forward_artifact_compare") or {})
    return (
        p9r.get("status") == "ready"
        and not p9r.get("blockers")
        and p9r.get("candidate_scorer_mode") == "research_h10d_contract"
        and p9r.get("candidate_scorer_mode_scope") == "proof_harness_only"
        and p9r.get("candidate_scorer_loaded_into_live_wrapper") is False
        and p9r.get("candidate_scorer_loaded_into_timer") is False
        and p9r.get("candidate_scorer_loaded_into_executor") is False
        and row_parity_zero(p9r)
        and int(target.get("mismatch_count") or 0) == 0
        and int(slices.get("mismatch_count") or 0) == 0
        and retained.get("status") == "ready"
        and int(p9r.get("orders_submitted") or 0) == 0
        and int(p9r.get("fills_observed") or 0) == 0
        and p9r.get("applied_to_live") is False
        and p9r.get("live_config_changed") is False
        and p9r.get("operator_state_changed") is False
        and p9r.get("live_supervisor_timer_loaded_candidate_overlay") is False
    )


def all_true(values: dict[str, Any]) -> bool:
    return all(value is True for value in values.values())


def build_owner_decision(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id

    paths = {
        "phase9c": (
            resolve_path(args.phase9c_summary)
            if str(getattr(args, "phase9c_summary", "") or "").strip()
            else latest_match(PHASE9C_PARENT, "*/summary.json")
        ),
        "phase9r": (
            resolve_path(args.phase9r_summary)
            if str(getattr(args, "phase9r_summary", "") or "").strip()
            else latest_match(PHASE9R_PARENT, "*/summary.json")
        ),
    }
    p9c = load_optional(paths["phase9c"])
    p9r = load_optional(paths["phase9r"])

    p9c_hard_guards = dict(p9c.get("p9c_hard_guards") or {})
    p9c_proof_gates = dict(p9c.get("proof_gates") or {})
    decision = str(args.decision)
    decision_gates = {
        "decision_is_allowed": decision in set(p9c.get("allowed_owner_decisions") or []),
        "decision_is_p9c_implementation_approval": decision == APPROVE_P9C_IMPLEMENTATION_DECISION,
        "phase9c_ready": p9c.get("status") == "ready" and not p9c.get("blockers"),
        "phase9c_owner_review_eligible": p9c.get("eligible_for_owner_p9c_review") is True,
        "phase9c_hard_guards_all_true": bool(p9c_hard_guards) and all_true(p9c_hard_guards),
        "phase9c_proof_gates_all_true": bool(p9c_proof_gates) and all_true(p9c_proof_gates),
        "phase9c_no_timer_or_executor_load": p9c_hard_guards.get("no_timer_or_executor_load") is True,
        "phase9c_zero_orders_fills": p9c_hard_guards.get("zero_orders_fills_all_inputs") is True,
        "phase9c_no_live_mutation": p9c_hard_guards.get("no_live_mutation_all_inputs") is True,
        "phase9r_research_parity_ready": p9r_research_parity_ready(p9r),
    }
    blockers = [key for key, value in decision_gates.items() if not value]
    approved = not blockers
    status = "approved" if approved else "blocked"

    source_evidence = {
        "phase9c_summary": evidence_file(paths["phase9c"]),
        "phase9r_summary": evidence_file(paths["phase9r"]),
    }
    decision_record = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "blockers": blockers,
        "owner": str(args.owner),
        "decision": decision,
        "decision_source": str(args.decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_default_off_observe_only_hook_implementation_only"
            if approved
            else "none"
        ),
        "scorer_reproduction_assessment": {
            "research_baseline_reproduced_in_p9r_harness": p9r_research_parity_ready(p9r),
            "research_scorer_contract": p9r.get("candidate_scorer_mode"),
            "research_scorer_scope": p9r.get("candidate_scorer_mode_scope"),
            "row_trigger_mismatch_count": int(dict(p9r.get("row_parity") or {}).get("trigger_mismatch_count") or 0),
            "row_multiplier_mismatch_count": int(
                dict(p9r.get("row_parity") or {}).get("multiplier_mismatch_count") or 0
            ),
            "row_target_contribution_mismatch_count": int(
                dict(p9r.get("row_parity") or {}).get("target_contribution_mismatch_count") or 0
            ),
            "row_score_mismatch_count": int(dict(p9r.get("row_parity") or {}).get("score_mismatch_count") or 0),
            "target_weight_mismatch_count": int(dict(p9r.get("target_weight_parity") or {}).get("mismatch_count") or 0),
            "slice_metric_mismatch_count": int(dict(p9r.get("slice_metric_parity") or {}).get("mismatch_count") or 0),
            "candidate_scorer_loaded_into_live_wrapper": p9r.get("candidate_scorer_loaded_into_live_wrapper"),
            "candidate_scorer_loaded_into_timer": p9r.get("candidate_scorer_loaded_into_timer"),
            "candidate_scorer_loaded_into_executor": p9r.get("candidate_scorer_loaded_into_executor"),
            "interpretation": (
                "complete research-baseline reproduction in proof harness; not loaded into live execution path"
            ),
        },
        "authorized_scope": {
            "observe_only_hook_implementation": approved,
            "default_off_required": True,
            "proof_artifacts_only_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_order_authority": "disabled",
        },
        "not_authorized": {
            "hook_deployment": True,
            "timer_path_load": True,
            "live_order_submission": True,
            "target_plan_replacement": True,
            "executor_input_mutation": True,
            "live_config_mutation": True,
            "operator_state_mutation": True,
            "timer_or_service_mutation": True,
            "stage_governance_change": True,
        },
        "next_step": (
            "P9D_default_off_observe_only_hook_contract_implementation"
            if approved
            else "resolve_owner_decision_blockers_before_p9d"
        ),
        "decision_gates": decision_gates,
        "source_evidence": source_evidence,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "report": str(output_root / "owner_decision_report.md"),
        },
    }

    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", decision_record)
    write_json(output_root / "owner_decision_record.json", decision_record)
    write_report(output_root / "owner_decision_report.md", decision_record)
    return decision_record, 0 if approved else 2


def write_report(path: Path, record: dict[str, Any]) -> None:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9C Owner Decision",
        "",
        f"`Status: {record['status']}`",
        "",
        "## Decision",
        "",
        "```text",
        f"owner = {record['owner']}",
        f"decision = {record['decision']}",
        f"decision_effect = {record['decision_effect']}",
        f"recorded_at_utc = {record['recorded_at_utc']}",
        "```",
        "",
        "## Scorer Assessment",
        "",
        "```text",
    ]
    for key, value in dict(record.get("scorer_reproduction_assessment") or {}).items():
        lines.append(f"{key} = {value}")
    lines.extend(["```", "", "## Authorized Scope", "", "```text"])
    for key, value in dict(record.get("authorized_scope") or {}).items():
        lines.append(f"{key} = {value}")
    lines.extend(["```", "", "## Not Authorized", "", "```text"])
    for key, value in dict(record.get("not_authorized") or {}).items():
        lines.append(f"{key} = {value}")
    lines.extend(["```", "", "## Gate Verdicts", "", "```text"])
    for key, value in dict(record.get("decision_gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    record, exit_code = build_owner_decision(parse_args(argv))
    print(f"status={record['status']} run_id={record['run_id']}")
    print(f"summary={record['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
