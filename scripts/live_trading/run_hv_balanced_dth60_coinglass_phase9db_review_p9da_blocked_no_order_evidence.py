from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9da_execute_single_post_only_canary_live_order import (  # noqa: E402
    CONTRACT_VERSION as P9DA_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9DA_PARENT,
    P9DB_GATE,
    P9DB_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9db_review_p9da_blocked_no_order_evidence.v1"
APPROVE_P9DB_DECISION = "approve_p9db_review_p9da_blocked_no_order_evidence_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9db_review_p9da_blocked_no_order_evidence"
P9DC_GATE = "P9DC_define_and_approve_0_001_btcusdt_round_trip_canary_terms"
P9DC_SCOPE = (
    "define_and_approve_new_0_001_btcusdt_buy_then_reduce_only_sell_canary_terms_after_p9da_blocked_no_order_review"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9DA evidence. P9DB is review-only: it proves the "
            "single post-only canary failed closed with zero order/fill effects "
            "before a separate P9DC terms gate may be discussed."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9da-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DB_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9db_review_p9da_blocked_no_order_evidence",
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


def latest_p9da_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9da_summary).strip():
        return resolve_path(args.phase9da_summary)
    return latest_match(P9DA_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9da_summary_is_blocked_no_order(summary: dict[str, Any]) -> bool:
    blockers = [str(item) for item in list(summary.get("blockers") or [])]
    return (
        summary.get("contract_version") == P9DA_CONTRACT
        and summary.get("status") == "blocked"
        and summary.get("p9da_single_post_only_canary_live_order_ready") is False
        and summary.get("p9cz_sufficient_for_p9da_execution") is True
        and summary.get("fresh_pre_submit_readback_performed") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("pit_safe_v2v3_account_proof_ready") is True
        and summary.get("can_trade_decision_source") == "/fapi/v2/account.canTrade"
        and summary.get("can_trade_pre") is True
        and summary.get("can_trade_post") is True
        and summary.get("canary_order_plan_ready") is False
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("live_order_submission_authorized") is True
        and summary.get("live_order_submission_performed") is False
        and summary.get("actual_live_order_submission_performed") is False
        and summary.get("actual_candidate_execution_performed") is False
        and summary.get("actual_candidate_executor_target_path_entry_performed") is False
        and summary.get("actual_executor_input_mutation_performed") is False
        and summary.get("actual_target_plan_replacement_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and any(item.startswith("canary_minimum_notional_exceeds_authorized_max") for item in blockers)
        and "canary_order_plan_not_ready" in blockers
        and summary.get("allowed_next_gate") == P9DB_GATE
        and summary.get("allowed_next_gate_scope") == P9DB_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p9da_plan_is_min_notional_blocked(plan: dict[str, Any]) -> bool:
    blockers = [str(item) for item in list(plan.get("blockers") or [])]
    return (
        plan.get("contract_version") == "hv_balanced_dth60_coinglass_phase9da_canary_order_plan.v1"
        and plan.get("status") == "blocked"
        and plan.get("symbol") == "BTCUSDT"
        and plan.get("side") == "BUY"
        and decimal_value(plan.get("minimum_executable_notional_usdt")) > decimal_value(plan.get("max_notional_usdt"))
        and decimal_value(plan.get("min_qty")) == Decimal("0.001")
        and decimal_value(plan.get("min_notional")) >= Decimal("50")
        and decimal_value(plan.get("quantity")) == Decimal("0")
        and decimal_value(plan.get("notional_usdt")) == Decimal("0")
        and any(item.startswith("canary_minimum_notional_exceeds_authorized_max") for item in blockers)
        and any(item.startswith("computed_notional_below_min_notional") for item in blockers)
        and any(item.startswith("computed_quantity_below_min_qty") for item in blockers)
    )


def p9da_command_records_prove_no_submitter(command_records: dict[str, Any]) -> bool:
    labels = [str(row.get("label")) for row in list(command_records.get("commands") or []) if isinstance(row, dict)]
    return (
        labels == [
            "pre_control_snapshot",
            "remote_stdout_pit_safe_v2v3_account_collector",
            "remote_stdout_market_and_fingerprint_collector",
            "post_control_snapshot",
        ]
        and "remote_single_post_only_canary_order_submitter" not in labels
    )


def p9da_remote_submission_empty(submission: dict[str, Any]) -> bool:
    return not submission or (
        submission.get("status") in {"", "not_attempted", None}
        and int_zero(submission, "orders_submitted")
        and int_zero(submission, "fill_count")
    )


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DB_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9db_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9da_blocked_no_order_evidence_only",
        "recorded_at_utc": iso_z(now),
        "p9db_review_approved": approved,
        "live_order_submission_approved": False,
        "round_trip_terms_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "candidate_execution_approved": False,
    }


def build_phase9db(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9db" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9da_path = latest_p9da_summary(args)
    p9da = load_optional(p9da_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    plan_path = source_output_path(p9da, "canary_order_plan")
    command_records_path = source_output_path(p9da, "command_records")
    submission_path = source_output_path(p9da, "remote_single_post_only_canary_order_submission")
    control_path = source_output_path(p9da, "control_boundary_readback")
    account_proof_path = source_output_path(p9da, "pit_safe_v2v3_account_proof")
    plan = load_optional(plan_path)
    command_records = load_optional(command_records_path)
    submission = load_optional(submission_path)
    control = load_optional(control_path)
    account_proof = load_optional(account_proof_path)
    owner_record = owner_decision_record(args, started_at)

    gates = {
        "owner_decision_p9db_review_recorded": str(args.owner_decision) == APPROVE_P9DB_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9da_summary_exists": bool(p9da),
        "p9da_summary_blocked_no_order": p9da_summary_is_blocked_no_order(p9da),
        "p9da_canary_plan_min_notional_blocked": p9da_plan_is_min_notional_blocked(plan),
        "p9da_command_records_prove_no_submitter": p9da_command_records_prove_no_submitter(command_records),
        "p9da_remote_submission_empty_or_not_invoked": p9da_remote_submission_empty(submission),
        "p9da_control_boundary_no_live_mutation": control.get("live_order_submission_performed") is False
        and control.get("timer_path_loaded") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and int_zero(control, "remote_files_written"),
        "p9da_account_proof_can_trade_v2_true": account_proof.get("can_trade_source")
        == "/fapi/v2/account.canTrade"
        and account_proof.get("can_trade_pre") is True
        and account_proof.get("can_trade_post") is True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"

    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9db_p9da_retained_evidence_review.v1",
        "review_only": True,
        "p9da_retained_evidence_sufficient_for_p9db_review": status == "ready",
        "p9da_proved_blocked_before_order_submitter": gates["p9da_command_records_prove_no_submitter"],
        "p9da_proved_zero_orders_fills": p9da_summary_is_blocked_no_order(p9da),
        "p9da_blocker_class": "approved_max_notional_below_current_btcusdt_minimum_executable_notional",
        "observed_minimum_executable_notional_usdt": p9da.get("canary_minimum_executable_notional_usdt"),
        "observed_approved_max_notional_usdt": p9da.get("max_notional_usdt"),
        "future_terms_change_required": True,
        "future_terms_change": "new P9DC approval required; do not mutate P9CZ or P9DA in place",
        "checks": gates,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9db_non_authorization.v1",
        "authorizations": {
            "review_p9da_retained_evidence": str(args.owner_decision) == APPROVE_P9DB_DECISION,
            "define_p9dc_round_trip_terms_next": status == "ready",
            "live_order_submission_in_p9db": False,
            "round_trip_terms_approval_in_p9db": False,
            "remote_execution": False,
            "remote_sync": False,
            "remote_file_write": False,
            "candidate_execution": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
        },
    }

    proof_files = {
        "p9da_retained_evidence_review": proof_root / "p9da_retained_evidence_review.json",
        "non_authorization": proof_root / "non_authorization.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["p9da_retained_evidence_review"], review)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["owner_decision_record"], owner_record)
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9db_proof_artifact_manifest.v1",
        "artifact_count": len(proof_files),
        "artifacts": {key: evidence_file(path) for key, path in sorted(proof_files.items())},
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9db_review_p9da_blocked_no_order_evidence_ready": status == "ready",
        "p9da_retained_evidence_sufficient_for_p9db_review": status == "ready",
        "p9da_proved_fresh_pre_submit_readback": p9da.get("fresh_pre_submit_readback_performed") is True,
        "p9da_proved_btcusdt_minimum_notional_exceeded_authorized_max": gates[
            "p9da_canary_plan_min_notional_blocked"
        ],
        "p9da_proved_order_submitter_not_invoked": gates["p9da_command_records_prove_no_submitter"],
        "p9da_proved_zero_orders_fills": p9da_summary_is_blocked_no_order(p9da),
        "p9da_observed_minimum_executable_notional_usdt": p9da.get("canary_minimum_executable_notional_usdt"),
        "p9da_observed_authorized_max_notional_usdt": p9da.get("max_notional_usdt"),
        "future_round_trip_terms_change_required": True,
        "eligible_for_future_p9dc_round_trip_terms_gate": status == "ready",
        "eligible_for_live_order_submission": False,
        "round_trip_terms_approved": False,
        "live_order_submission_authorized": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "source_evidence": {
            "phase9da_summary": evidence_file(p9da_path),
            "phase9da_canary_order_plan": evidence_file(plan_path),
            "phase9da_command_records": evidence_file(command_records_path),
            "phase9da_remote_single_post_only_canary_order_submission": evidence_file(submission_path),
            "phase9da_control_boundary_readback": evidence_file(control_path),
            "phase9da_pit_safe_v2v3_account_proof": evidence_file(account_proof_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P9DC_GATE,
        "allowed_next_gate_scope": P9DC_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9db_review_p9da_blocked_no_order_evidence.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9db_review_p9da_blocked_no_order_evidence.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DB P9DA Blocked No-Order Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DB is review-only. It checks the retained P9DA evidence before a separate P9DC terms gate.",
        "",
        "```text",
        f"p9da_proved_order_submitter_not_invoked = {str(bool(summary['p9da_proved_order_submitter_not_invoked'])).lower()}",
        f"p9da_proved_zero_orders_fills = {str(bool(summary['p9da_proved_zero_orders_fills'])).lower()}",
        f"p9da_observed_minimum_executable_notional_usdt = {summary['p9da_observed_minimum_executable_notional_usdt']}",
        f"p9da_observed_authorized_max_notional_usdt = {summary['p9da_observed_authorized_max_notional_usdt']}",
        "live_order_submission_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
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
    summary, exit_code = build_phase9db(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
