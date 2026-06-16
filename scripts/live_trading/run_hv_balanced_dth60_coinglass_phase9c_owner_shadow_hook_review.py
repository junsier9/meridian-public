from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9c_owner_shadow_hook_review.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9c_owner_shadow_hook_review"
)
PHASE9A_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9a_local_hook_contract_fixture"
)
PHASE9B_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9b_remote_supervisor_artifact_wrapper"
)
PHASE9R_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9r_research_to_live_parity"
)
P9_PROPOSAL_DOC = (
    "docs/live_trading/hv_balanced_binance_usdm_pipeline/"
    "mainnet_hv_balanced_dth60_coinglass_p9_live_supervisor_shadow_hook_proposal_2026_06_07.md"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
READY_DECISION_STATUS = "ready_for_owner_p9c_decision"
PENDING_OWNER_DECISION = "pending_owner_decision"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the owner-gated P9C review packet for a timer-adjacent "
            "observe-only shadow hook. This review reads retained P9A/P9B/P9R "
            "proofs only; it never mutates live config, timers, operator state, "
            "or executor inputs."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--proposal-doc", default=P9_PROPOSAL_DOC)
    parser.add_argument("--phase9a-summary", default="")
    parser.add_argument("--phase9b-summary", default="")
    parser.add_argument("--phase9r-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--review-request-source", default="user_chat:execute_p9c_review")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
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


def latest_match(parent: str, pattern: str) -> Path:
    root = resolve_path(parent)
    matches = [path for path in root.glob(pattern) if path.is_file()]
    if not matches:
        return Path("")
    return sorted(matches, key=lambda path: (path.stat().st_mtime, str(path)))[-1]


def explicit_false(summary: dict[str, Any], key: str, *, fallback_false_keys: Iterable[str] = ()) -> bool:
    if key in summary:
        return summary.get(key) is False
    return any(summary.get(fallback_key) is False for fallback_key in fallback_false_keys)


def no_live_mutation(summary: dict[str, Any]) -> bool:
    return (
        explicit_false(summary, "applied_to_live")
        and explicit_false(summary, "live_config_changed")
        and explicit_false(summary, "operator_state_changed")
        and explicit_false(
            summary,
            "timer_state_changed",
            fallback_false_keys=(
                "timer_path_invoked",
                "live_supervisor_timer_loaded_candidate_overlay",
            ),
        )
    )


def zero_order(summary: dict[str, Any]) -> bool:
    return (
        int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or summary.get("fills_observed") or 0) == 0
        and summary.get("mainnet_order_submission_authorized") is False
        and summary.get("exchange_order_submission") == "disabled"
    )


def all_row_parity_zero(summary: dict[str, Any]) -> bool:
    row = dict(summary.get("row_parity") or {})
    return all(
        int(row.get(key) or 0) == 0
        for key in (
            "trigger_mismatch_count",
            "multiplier_mismatch_count",
            "target_contribution_mismatch_count",
            "score_mismatch_count",
        )
    )


def p9r_ready(summary: dict[str, Any]) -> bool:
    target = dict(summary.get("target_weight_parity") or {})
    slices = dict(summary.get("slice_metric_parity") or {})
    retained = dict(summary.get("retained_forward_artifact_compare") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("candidate_scorer_mode") == "research_h10d_contract"
        and summary.get("candidate_scorer_mode_scope") == "proof_harness_only"
        and summary.get("candidate_scorer_loaded_into_live_wrapper") is False
        and summary.get("candidate_scorer_loaded_into_timer") is False
        and summary.get("candidate_scorer_loaded_into_executor") is False
        and all_row_parity_zero(summary)
        and int(target.get("mismatch_count") or 0) == 0
        and int(slices.get("mismatch_count") or 0) == 0
        and retained.get("status") == "ready"
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fills_observed") or 0) == 0
        and no_live_mutation(summary)
    )


def build_p9c_review(
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
        "project_profile": resolve_path(args.project_profile),
        "proposal_doc": resolve_path(args.proposal_doc),
        "phase9a": (
            resolve_path(args.phase9a_summary)
            if str(getattr(args, "phase9a_summary", "") or "").strip()
            else latest_match(PHASE9A_PARENT, "*/summary.json")
        ),
        "phase9b": (
            resolve_path(args.phase9b_summary)
            if str(getattr(args, "phase9b_summary", "") or "").strip()
            else latest_match(PHASE9B_PARENT, "**/verdict/summary.json")
        ),
        "phase9r": (
            resolve_path(args.phase9r_summary)
            if str(getattr(args, "phase9r_summary", "") or "").strip()
            else latest_match(PHASE9R_PARENT, "*/summary.json")
        ),
    }

    project_profile = load_optional(paths["project_profile"])
    p9a = load_optional(paths["phase9a"])
    p9b = load_optional(paths["phase9b"])
    p9r = load_optional(paths["phase9r"])

    p9a_gates = {
        "status_ready": p9a.get("status") == "ready",
        "disabled_hook_baseline_output_unchanged": p9a.get("disabled_hook_baseline_output_unchanged") is True,
        "enabled_hook_execution_target_unchanged": p9a.get("enabled_hook_execution_target_unchanged") is True,
        "executor_consumes_baseline_only": p9a.get("executor_consumes_baseline_only") is True,
        "candidate_artifacts_under_proof_artifacts_only": p9a.get("candidate_artifacts_under_proof_artifacts_only") is True,
        "candidate_plan_not_referenced_by_executor": p9a.get("candidate_plan_referenced_by_executor") is False,
        "candidate_order_authority_disabled": p9a.get("candidate_order_authority") == "disabled",
        "candidate_live_order_submission_authorized_false": p9a.get("candidate_live_order_submission_authorized") is False,
        "candidate_zero_orders_fills": zero_order(p9a),
        "no_live_mutation": no_live_mutation(p9a),
        "same_timestamp_context": p9a.get("same_timestamp_context_proven") is True,
        "same_risk_inputs": p9a.get("same_risk_inputs_proven") is True,
        "same_symbol_set": p9a.get("same_symbol_set_proven") is True,
        "same_portfolio_engine": p9a.get("same_portfolio_engine_proven") is True,
        "fresh_phase2": p9a.get("fresh_phase2_no_future_stale_zero_fill") is True,
        "fresh_phase2b": p9a.get("fresh_phase2b_no_future_stale_zero_fill") is True,
    }
    p9b_gates = {
        "status_ready": p9b.get("status") == "ready",
        "executor_consumes_baseline_only": p9b.get("executor_consumes_baseline_only") is True,
        "executor_input_plan_hash_equals_baseline": p9b.get("executor_input_plan_hash_equals_baseline") is True,
        "candidate_plan_not_referenced_by_executor": p9b.get("candidate_plan_referenced_by_executor") is False,
        "candidate_shadow_plan_not_generated": p9b.get("candidate_shadow_plan_generated") is False,
        "candidate_order_authority_disabled": p9b.get("candidate_order_authority") == "disabled",
        "candidate_live_order_submission_authorized_false": p9b.get("candidate_live_order_submission_authorized") is False,
        "candidate_zero_orders_fills": zero_order(p9b),
        "ran_supervisor_false": p9b.get("ran_supervisor") is False,
        "timer_path_invoked_false": p9b.get("timer_path_invoked") is False,
        "read_only_supervisor_artifacts": p9b.get("read_only_supervisor_artifacts") is True,
        "control_plane_unchanged": dict(p9b.get("control_plane") or {}).get("unchanged") is True,
        "wrapper_output_under_proof_artifacts": p9b.get("wrapper_output_under_proof_artifacts") is True,
        "no_live_mutation": no_live_mutation(p9b),
    }
    p9r_gates = {
        "status_ready": p9r.get("status") == "ready",
        "no_blockers": not p9r.get("blockers"),
        "research_contract_scorer": p9r.get("candidate_scorer_mode") == "research_h10d_contract",
        "proof_harness_only": p9r.get("candidate_scorer_mode_scope") == "proof_harness_only",
        "scorer_not_loaded_into_live_wrapper": p9r.get("candidate_scorer_loaded_into_live_wrapper") is False,
        "scorer_not_loaded_into_timer": p9r.get("candidate_scorer_loaded_into_timer") is False,
        "scorer_not_loaded_into_executor": p9r.get("candidate_scorer_loaded_into_executor") is False,
        "row_parity_zero": all_row_parity_zero(p9r),
        "target_weight_parity_zero": int(dict(p9r.get("target_weight_parity") or {}).get("mismatch_count") or 0) == 0,
        "slice_metric_parity_zero": int(dict(p9r.get("slice_metric_parity") or {}).get("mismatch_count") or 0) == 0,
        "retained_forward_compare_ready": dict(p9r.get("retained_forward_artifact_compare") or {}).get("status") == "ready",
        "zero_orders_fills": int(p9r.get("orders_submitted") or 0) == 0 and int(p9r.get("fills_observed") or 0) == 0,
        "no_live_mutation": no_live_mutation(p9r),
    }
    review_gates = {
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "proposal_doc_exists": paths["proposal_doc"].exists(),
        "phase9a_ready": all(p9a_gates.values()),
        "phase9b_ready": all(p9b_gates.values()),
        "phase9r_ready": p9r_ready(p9r),
        "candidate_order_authority_disabled": all(
            item.get("candidate_order_authority") == "disabled" for item in (p9a, p9b)
        ),
        "candidate_live_order_submission_authorized_false": all(
            item.get("candidate_live_order_submission_authorized") is False for item in (p9a, p9b)
        ),
        "execution_target_source_baseline_only": all(
            item.get("execution_target_source") == "baseline_only" for item in (p9a, p9b)
        ),
        "candidate_overlay_execution_path_excluded": p9a.get("candidate_overlay_execution_path") == "excluded",
        "candidate_artifact_sink_proof_only": all(
            item.get("candidate_artifact_sink") == "proof_artifacts_only" for item in (p9a, p9b)
        ),
        "no_timer_or_executor_load": (
            p9b.get("timer_path_invoked") is False
            and p9r.get("candidate_scorer_loaded_into_timer") is False
            and p9r.get("candidate_scorer_loaded_into_executor") is False
        ),
        "no_live_mutation_all_inputs": all(no_live_mutation(item) for item in (p9a, p9b, p9r)),
        "zero_orders_fills_all_inputs": (
            zero_order(p9a)
            and zero_order(p9b)
            and int(p9r.get("orders_submitted") or 0) == 0
            and int(p9r.get("fills_observed") or 0) == 0
        ),
    }
    blockers = [key for key, value in review_gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    owner_decision_record = {
        "owner": str(args.owner),
        "review_request_source": str(args.review_request_source),
        "review_status": READY_DECISION_STATUS if status == "ready" else "blocked_before_owner_decision",
        "timer_hook_implementation_decision": PENDING_OWNER_DECISION,
        "timer_hook_deployment_decision": PENDING_OWNER_DECISION,
        "live_order_submission_decision": "not_requested",
        "recorded_at_utc": iso_z(started_at),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "review_scope": "owner_gated_timer_adjacent_observe_only_hook_review",
        "project_stage": {
            "current_stage": project_profile.get("current_stage"),
            "target_stage": project_profile.get("target_stage"),
        },
        "owner_decision_record": owner_decision_record,
        "eligible_for_owner_p9c_review": status == "ready",
        "eligible_for_timer_hook_implementation": False,
        "timer_hook_implementation_authorized": False,
        "timer_hook_deployment_authorized": False,
        "eligible_for_live_order_submission": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "baseline_executor_input_must_remain_unchanged": True,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "exchange_order_submission": "disabled",
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "wrote_hook_config": False,
        "deployed_hook": False,
        "source_evidence": {
            "proposal_doc": evidence_file(paths["proposal_doc"]),
            "project_profile": evidence_file(paths["project_profile"]),
            "phase9a_summary": evidence_file(paths["phase9a"]),
            "phase9b_summary": evidence_file(paths["phase9b"]),
            "phase9r_summary": evidence_file(paths["phase9r"]),
        },
        "proof_gates": review_gates,
        "phase9a_gates": p9a_gates,
        "phase9b_gates": p9b_gates,
        "phase9r_gates": p9r_gates,
        "p9c_hard_guards": {
            "candidate_order_authority_disabled": review_gates["candidate_order_authority_disabled"],
            "candidate_live_order_submission_authorized_false": review_gates[
                "candidate_live_order_submission_authorized_false"
            ],
            "execution_target_source_baseline_only": review_gates["execution_target_source_baseline_only"],
            "candidate_overlay_execution_path_excluded": review_gates["candidate_overlay_execution_path_excluded"],
            "candidate_artifact_sink_proof_only": review_gates["candidate_artifact_sink_proof_only"],
            "candidate_plan_not_referenced_by_executor": (
                p9a.get("candidate_plan_referenced_by_executor") is False
                and p9b.get("candidate_plan_referenced_by_executor") is False
            ),
            "same_timestamp_context": p9a.get("same_timestamp_context_proven") is True,
            "same_risk_inputs": p9a.get("same_risk_inputs_proven") is True,
            "same_symbol_set": p9a.get("same_symbol_set_proven") is True,
            "same_portfolio_engine": p9a.get("same_portfolio_engine_proven") is True,
            "fresh_phase2_no_future_stale_zero_fill": p9a.get("fresh_phase2_no_future_stale_zero_fill") is True,
            "fresh_phase2b_no_future_stale_zero_fill": p9a.get("fresh_phase2b_no_future_stale_zero_fill") is True,
            "executor_consumes_baseline_only": (
                p9a.get("executor_consumes_baseline_only") is True
                and p9b.get("executor_consumes_baseline_only") is True
            ),
            "no_timer_or_executor_load": review_gates["no_timer_or_executor_load"],
            "no_live_mutation_all_inputs": review_gates["no_live_mutation_all_inputs"],
            "zero_orders_fills_all_inputs": review_gates["zero_orders_fills_all_inputs"],
            "research_to_live_parity_ready": p9r_ready(p9r),
        },
        "allowed_owner_decisions": [
            "approve_p9c_observe_only_hook_implementation",
            "defer_for_more_no_order_observation",
            "reject_p9c_hook",
        ],
        "next_step_if_owner_approves": (
            "Implement a default-off timer-adjacent observe-only hook contract that writes only proof_artifacts "
            "and proves executor input remains baseline-only; order authority remains disabled."
        ),
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "review_pack": str(output_root / "p9c_owner_shadow_hook_review.json"),
            "report": str(output_root / "p9c_owner_shadow_hook_review.md"),
        },
    }

    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", summary)
    write_json(output_root / "p9c_owner_shadow_hook_review.json", summary)
    write_report(output_root / "p9c_owner_shadow_hook_review.md", summary)
    return summary, 0 if status == "ready" else 2


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9C Owner Shadow-Hook Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is an owner-gated review packet only. It does not implement, deploy, or enable a timer hook.",
        "",
        "```text",
        f"eligible_for_owner_p9c_review = {str(summary['eligible_for_owner_p9c_review']).lower()}",
        "eligible_for_timer_hook_implementation = false",
        "timer_hook_implementation_authorized = false",
        "timer_hook_deployment_authorized = false",
        "eligible_for_live_order_submission = false",
        "candidate_order_authority = disabled",
        "execution_target_source = baseline_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Source Evidence",
        "",
    ]
    for key, item in dict(summary.get("source_evidence") or {}).items():
        lines.append(f"- {key}: `{item.get('path')}` sha256=`{item.get('sha256')}`")
    lines.extend(["", "## Gate Verdicts", "", "```text"])
    for key, value in dict(summary.get("proof_gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Owner Decision", "", "```text"])
    for key, value in dict(summary.get("owner_decision_record") or {}).items():
        lines.append(f"{key} = {value}")
    lines.extend(["```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _, exit_code = build_p9c_review(parse_args(argv))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
