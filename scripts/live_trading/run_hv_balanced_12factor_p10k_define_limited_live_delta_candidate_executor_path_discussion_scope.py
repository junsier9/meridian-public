from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10j_review_p10i_single_cycle_live_delta_canary import (  # noqa: E402
    CONTRACT_VERSION as P10J_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P10J_PARENT,
    P10K_GATE,
    P10K_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_12factor_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope.v1"
APPROVE_P10K_DECISION = "approve_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10k_limited_live_delta_candidate_executor_path_discussion_scope"
P10L_GATE = "P10L_prepare_limited_live_delta_candidate_executor_path_discussion_proposal_package_only_if_separately_requested"
P10L_SCOPE = (
    "prepare_proposal_package_only_for_limited_live_delta_candidate_executor_path_discussion_after_p10k_no_execution_no_live_order_no_continuous_automation"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10K scope-only gate: define the scope for a future limited "
            "live_delta / candidate executor-path discussion after P10J. It does "
            "not SSH, call Binance, submit orders, mutate executor input, replace "
            "target plans, load timer/supervisor paths, or authorize continuous "
            "automated order flow."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--p10j-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10K_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p10k_define_limited_live_delta_candidate_executor_path_"
            "discussion_scope_only_if_separately_requested"
        ),
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


def latest_p10j_summary(args: argparse.Namespace) -> Path:
    if str(args.p10j_summary).strip():
        return resolve_path(args.p10j_summary)
    return latest_match(P10J_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p10j_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10J_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10j_review_p10i_single_cycle_live_delta_canary_ready") is True
        and summary.get("p10i_retained_evidence_sufficient_for_p10j_review") is True
        and summary.get("p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion") is True
        and summary.get("p10i_sufficient_for_live_order_submission_without_new_gate") is False
        and summary.get("p10i_sufficient_for_candidate_executor_path_execution_without_new_gate") is False
        and summary.get("p10i_sufficient_for_continuous_automated_order_flow") is False
        and summary.get("allowed_scope_after_p10j") == "discussion_and_scope_definition_only"
        and summary.get("eligible_for_future_p10k_scope_definition_gate") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and int(summary.get("p10i_orders_submitted") or 0) == 1
        and int(summary.get("p10i_orders_canceled") or 0) == 1
        and int(summary.get("p10i_fill_count") or 0) == 0
        and int(summary.get("p10i_trade_count") or 0) == 0
        and summary.get("p10i_remote_control_boundary_unchanged") is True
        and summary.get("allowed_next_gate") == P10K_GATE
        and summary.get("allowed_next_gate_scope") == P10K_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10j_review_ready(review: dict[str, Any]) -> bool:
    constraints = dict(review.get("required_next_discussion_constraints") or {})
    return (
        review.get("contract_version") == "hv_balanced_12factor_p10j_p10i_retained_evidence_review.v1"
        and review.get("review_only") is True
        and review.get("p10i_retained_evidence_sufficient_for_p10j_review") is True
        and review.get("p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion") is True
        and review.get("p10i_sufficient_for_live_order_submission_without_new_gate") is False
        and review.get("p10i_sufficient_for_candidate_executor_path_execution_without_new_gate") is False
        and review.get("p10i_sufficient_for_continuous_automated_order_flow") is False
        and constraints.get("scope_type") == "discussion_and_scope_definition_only"
        and int(constraints.get("max_cycles_to_discuss") or 0) == 1
        and constraints.get("candidate_path_mode") == "limited_single_cycle_canary_discussion_only"
        and constraints.get("continuous_automated_order_flow") == "not_allowed"
        and constraints.get("default_order_state") == "disabled_until_separate_execution_gate"
        and constraints.get("must_define_candidate_plan_hash_binding") is True
        and constraints.get("must_define_exact_executor_target_plan_replacement_semantics") is True
        and constraints.get("must_define_baseline_fallback") is True
        and constraints.get("must_define_kill_switch") is True
        and constraints.get("must_define_max_notional_and_symbol_universe") is True
        and constraints.get("must_define_post_run_reconciliation") is True
    )


def p10j_non_authorization_ready(non_auth: dict[str, Any]) -> bool:
    authorizations = dict(non_auth.get("authorizations") or {})
    return (
        non_auth.get("contract_version") == "hv_balanced_12factor_p10j_non_authorization.v1"
        and authorizations.get("review_p10i_retained_evidence") is True
        and authorizations.get("allow_future_limited_live_delta_candidate_executor_path_discussion_scope_gate") is True
        and authorizations.get("live_order_submission_in_p10j") is False
        and authorizations.get("candidate_executor_path_execution_in_p10j") is False
        and authorizations.get("candidate_target_plan_replacement_in_p10j") is False
        and authorizations.get("executor_input_mutation_in_p10j") is False
        and authorizations.get("timer_path_load_in_p10j") is False
        and authorizations.get("supervisor_invocation_in_p10j") is False
        and authorizations.get("remote_execution_in_p10j") is False
        and authorizations.get("remote_sync_in_p10j") is False
        and authorizations.get("remote_file_write_in_p10j") is False
        and authorizations.get("continuous_automated_order_flow") is False
        and authorizations.get("stage_governance_change") is False
    )


def p10j_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_12factor_p10j_control_boundary.v1"
        and control.get("scope") == "retained_evidence_review_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
        and control.get("live_order_submission_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("timer_path_loaded") is False
        and control.get("remote_sync_performed") is False
        and int_zero(control, "remote_files_written")
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def discussion_scope(now: datetime, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10k_limited_live_delta_candidate_executor_path_discussion_scope.v1",
        "owner": args.owner,
        "defined_at_utc": iso_z(now),
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "scope_only": True,
        "scope_label": "limited_live_delta_candidate_executor_path_discussion_after_p10i",
        "scope_purpose": (
            "allow a future proposal package to discuss how the 12-factor candidate "
            "could enter a strictly bounded executor/target-plan path after a "
            "single-cycle no-fill P10I canary"
        ),
        "may_discuss": [
            "candidate target-plan replacement semantics for one bounded cycle",
            "same-risk baseline fallback and executor input hash checks",
            "P10G/P10H/P10I candidate plan hash binding and stale-proof rejection",
            "max notional, symbol universe, order type, and time-in-force terms",
            "fresh account, order-book, filter, position, open-order, fill, and trade proof",
            "kill switch behavior before and after any future execution gate",
            "post-run reconciliation and retained evidence acceptance",
        ],
        "must_define_before_any_future_execution_gate": [
            "explicit owner approval for a specific execution-path canary",
            "candidate plan hash must bind to retained P10G or a fresh rerun",
            "executor input replacement must be exact, reversible, and one-cycle only",
            "baseline fallback must trigger on any stale, missing, or mismatched proof",
            "kill switch must force baseline-only with zero candidate orders",
            "fresh remote account proof must use /fapi/v2/account.canTrade",
            "pre/post position, open-order, fill, trade, and order-history fingerprints must be stable except the allowed bounded order/cancel delta",
            "post-run open orders must be zero",
            "no continuous automation, no timer/supervisor load, and no config/operator/timer mutation unless a later gate explicitly authorizes it",
        ],
        "hard_limits_for_discussion": {
            "max_cycles": 1,
            "max_symbols": 1,
            "continuous_automated_order_flow": False,
            "default_order_state": "disabled_until_separate_execution_gate",
            "default_timer_path_state": "not_loaded",
            "default_supervisor_invocation": "not_invoked",
            "default_candidate_execution": "not_executed",
            "default_target_plan_replacement": "not_replaced",
            "default_executor_input_mutation": "not_mutated",
            "default_remote_sync": "not_performed",
            "default_remote_file_write": 0,
            "must_remain_stage_3_human_approved_execution": True,
        },
        "not_authorized_by_this_scope": [
            "live order submission",
            "candidate executor-path execution",
            "actual target-plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "remote file write",
            "continuous automated order flow",
            "stage governance change",
        ],
        "allowed_next_gate": P10L_GATE,
        "allowed_next_gate_scope": P10L_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
    }


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P10K_DECISION
    return {
        "contract_version": "hv_balanced_12factor_p10k_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_limited_live_delta_candidate_executor_path_discussion_scope_only",
        "recorded_at_utc": iso_z(now),
        "p10k_scope_definition_approved": approved,
        "future_p10l_proposal_package_may_be_requested": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "continuous_automated_order_flow_approved": False,
    }


def build_p10k(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof"
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p10j_path = latest_p10j_summary(args)
    p10j = load_optional(p10j_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    review_path = source_output_path(p10j, "p10i_retained_evidence_review")
    non_auth_path = source_output_path(p10j, "non_authorization")
    control_path = source_output_path(p10j, "control_boundary_readback")
    review = load_optional(review_path)
    non_auth = load_optional(non_auth_path)
    source_control = load_optional(control_path)
    scope = discussion_scope(started_at, args)
    owner_record = owner_decision_record(args, started_at)
    limits = dict(scope["hard_limits_for_discussion"])

    gates = {
        "owner_decision_p10k_scope_definition_recorded": str(args.owner_decision) == APPROVE_P10K_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p10j_summary_exists": bool(p10j),
        "p10j_summary_ready_for_p10k": p10j_summary_ready(p10j),
        "p10j_review_ready": p10j_review_ready(review),
        "p10j_non_authorization_ready": p10j_non_authorization_ready(non_auth),
        "p10j_control_boundary_ready": p10j_control_ready(source_control),
        "scope_is_definition_only": scope.get("scope_only") is True,
        "scope_keeps_max_cycles_one": int(limits.get("max_cycles") or 0) == 1,
        "scope_keeps_max_symbols_one": int(limits.get("max_symbols") or 0) == 1,
        "scope_keeps_default_order_disabled": limits.get("default_order_state")
        == "disabled_until_separate_execution_gate",
        "scope_forbids_continuous_automation": limits.get("continuous_automated_order_flow") is False,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"

    non_authorization = {
        "contract_version": "hv_balanced_12factor_p10k_non_authorization.v1",
        "authorizations": {
            "define_discussion_scope": str(args.owner_decision) == APPROVE_P10K_DECISION,
            "future_p10l_proposal_package_request_allowed": status == "ready",
            "live_order_submission_in_p10k": False,
            "candidate_executor_path_execution_in_p10k": False,
            "candidate_target_plan_replacement_in_p10k": False,
            "executor_input_mutation_in_p10k": False,
            "timer_path_load_in_p10k": False,
            "supervisor_invocation_in_p10k": False,
            "remote_execution_in_p10k": False,
            "remote_sync_in_p10k": False,
            "remote_file_write_in_p10k": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10k_control_boundary.v1",
        "scope": "scope_definition_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    proof_files = {
        "discussion_scope": proof_root / "discussion_scope.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["discussion_scope"], scope)
    write_json(proof_files["non_authorization"], non_authorization)
    write_json(proof_files["control_boundary_readback"], control)
    write_json(proof_files["owner_decision_record"], owner_record)
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_12factor_p10k_proof_artifact_manifest.v1",
        "artifact_count": len(proof_files),
        "artifacts": {key: evidence_file(path) for key, path in sorted(proof_files.items())},
    }
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)

    p10j_inputs_ready = (
        p10j_summary_ready(p10j)
        and p10j_review_ready(review)
        and p10j_non_authorization_ready(non_auth)
        and p10j_control_ready(source_control)
    )
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p10k_limited_live_delta_candidate_executor_path_discussion_scope_ready": status == "ready",
        "p10j_sufficient_for_p10k_scope_definition": p10j_inputs_ready,
        "scope_definition_only": True,
        "scope_label": scope["scope_label"],
        "allowed_scope_after_p10k": "proposal_package_preparation_only",
        "eligible_for_future_p10l_proposal_package_gate": status == "ready",
        "max_cycles_discussion_scope": 1,
        "max_symbols_discussion_scope": 1,
        "default_order_state": "disabled_until_separate_execution_gate",
        "continuous_automated_order_flow_allowed": False,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": {
            "p10j_summary": evidence_file(p10j_path),
            "p10j_review": evidence_file(review_path),
            "p10j_non_authorization": evidence_file(non_auth_path),
            "p10j_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P10L_GATE,
        "allowed_next_gate_scope": P10L_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p10k_limited_live_delta_candidate_executor_path_discussion_scope.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p10k_limited_live_delta_candidate_executor_path_discussion_scope.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10K Limited Executor-Path Discussion Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P10K defines scope only. It does not execute, load, or authorize continuous automated order flow.",
        "",
        "```text",
        f"scope_definition_only = {str(bool(summary['scope_definition_only'])).lower()}",
        f"scope_label = {summary['scope_label']}",
        f"max_cycles_discussion_scope = {summary['max_cycles_discussion_scope']}",
        f"max_symbols_discussion_scope = {summary['max_symbols_discussion_scope']}",
        f"default_order_state = {summary['default_order_state']}",
        "continuous_automated_order_flow_allowed = false",
        "live_order_submission_authorized = false",
        "candidate_executor_path_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "```",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    lines.extend([f"- `{item}`" for item in blockers] if blockers else ["- none"])
    lines.extend(["", "## Allowed Next Gate", "", "```text", str(summary["allowed_next_gate"]), "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p10k(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
