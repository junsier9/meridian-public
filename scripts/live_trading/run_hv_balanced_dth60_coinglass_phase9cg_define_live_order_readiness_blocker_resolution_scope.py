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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_PROOF_CONTRACT_VERSION,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
    CONTRACT_VERSION as ACCOUNT_BUILDER_CONTRACT,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CF_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CF_PARENT,
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
    P9CG_GATE,
    P9CG_SCOPE,
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


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9cg_define_live_order_readiness_blocker_resolution_scope.v1"
)
APPROVE_P9CG_DECISION = (
    "approve_p9cg_define_live_order_readiness_blocker_resolution_scope_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cg_live_order_readiness_blocker_resolution_scope"
)
P9CH_GATE = (
    "P9CH_allow_pit_safe_read_only_account_proof_v2v3_owner_gate_only_if_separately_requested"
)
P9CH_SCOPE = (
    "allow_future_pit_safe_read_only_account_proof_v2v3_collection_only_no_order_no_candidate_no_timer_no_supervisor"
)
ACCOUNT_PROOF_BUILDER_PATH = (
    "scripts/live_trading/hv_balanced_binance_usdm_pit_safe_account_proof_builder.py"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define the P9CG blocker-resolution scope after P9CF. P9CG is "
            "scope-definition-only: it does not SSH, read Binance, collect fresh "
            "proofs, run supervisor/timer paths, mutate executor/target plans, "
            "or authorize live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cf-summary", default="")
    parser.add_argument("--account-proof-builder", default=ACCOUNT_PROOF_BUILDER_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CG_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cg_define_live_order_readiness_blocker_resolution_scope_only_if_separately_requested"
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


def latest_p9cf_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cf_summary).strip():
        return resolve_path(args.phase9cf_summary)
    return latest_match(P9CF_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cf_summary_ready(summary: dict[str, Any]) -> bool:
    blockers = set(str(item) for item in list(summary.get("live_order_readiness_blockers") or []))
    return (
        summary.get("contract_version") == P9CF_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready")
        is True
        and summary.get("p9ce_sufficient_for_read_only_collection_review") is True
        and summary.get("p9ce_sufficient_for_live_order_gate") is False
        and LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE in blockers
        and summary.get("eligible_for_future_p9cg_live_order_readiness_blocker_scope_gate")
        is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cf") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CG_GATE
        and summary.get("allowed_next_gate_scope") == P9CG_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def build_phase9cg_define_live_order_readiness_blocker_resolution_scope(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cg" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cf_path = latest_p9cf_summary(args)
    p9cf = load_optional(p9cf_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    builder_path = resolve_path(args.account_proof_builder)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CG_DECISION
    checks = {
        "owner_decision_p9cg_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cf_summary_exists": bool(p9cf),
        "p9cf_summary_ready_for_blocker_resolution_scope": p9cf_summary_ready(p9cf),
        "account_proof_builder_exists": builder_path.exists() and builder_path.is_file(),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_blocker_resolution_scope_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "p9cg_scope_definition_approved": owner_decision_ok,
        "pit_safe_account_proof_collection_approved": False,
        "fresh_remote_account_read_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    scope_definition = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_scope_definition.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "scope": "define_live_order_readiness_blocker_resolution_only",
        "prior_blocker": LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "pit_safe_read_only_account_proof_builder_required": True,
        "pit_safe_read_only_account_proof_contract": ACCOUNT_PROOF_CONTRACT_VERSION,
        "account_proof_builder_contract": ACCOUNT_BUILDER_CONTRACT,
        "required_read_only_endpoints": [
            ACCOUNT_V2_ENDPOINT,
            ACCOUNT_V3_ENDPOINT,
            ACCOUNT_CONFIG_ENDPOINT,
            POSITION_MODE_ENDPOINT,
            OPEN_ORDERS_ENDPOINT,
            API_RESTRICTIONS_ENDPOINT,
        ],
        "can_trade_decision_source": CAN_TRADE_SOURCE,
        "account_v3_canTrade_must_be_ignored_for_permission_decision": True,
        "if_v2_canTrade_true": {
            "classification": "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap",
            "required_next_evidence": [
                "fresh v2/v3 read-only account proof",
                "pre/post position fingerprint stable",
                "pre/post open-order fingerprint stable and zero open orders",
                "pre/post fill/trade delta zero",
                "rerun retained P9CF-style review on the corrected proof",
            ],
        },
        "if_v2_canTrade_false": {
            "classification": "account_side_permission_blocker",
            "required_owner_actions_before_any_live_order_gate": [
                "confirm Futures account is enabled",
                "confirm API key has Futures/trading permission",
                "confirm API key IP restriction includes 203.0.113.10",
                "recreate API key if it predates Futures-account enablement",
                "do not enable withdrawal permission",
            ],
        },
        "forbidden_in_p9cg": [
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "fresh remote account read",
            "order-test endpoint",
            "supervisor/timer invocation",
            "remote sync",
            "live config/operator/timer mutation",
        ],
    }
    builder_contract = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_account_proof_builder_contract.v1",
        "run_id": run_id,
        "builder_path": str(builder_path),
        "builder_source": evidence_file(builder_path),
        "builder_contract_version": ACCOUNT_BUILDER_CONTRACT,
        "account_proof_contract_version": ACCOUNT_PROOF_CONTRACT_VERSION,
        "permission_field_contract": {
            "can_trade_source": CAN_TRADE_SOURCE,
            "account_v2_endpoint": ACCOUNT_V2_ENDPOINT,
            "account_v3_endpoint": ACCOUNT_V3_ENDPOINT,
            "account_v3_canTrade_ignored_for_permission_decision": True,
            "split_missing_blocker": BLOCKER_CAN_TRADE_MISSING,
            "split_false_blocker": BLOCKER_CAN_TRADE_FALSE,
        },
        "side_effect_contract": {
            "http_methods_allowed": ["GET"],
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "order_test_calls": 0,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        },
    }
    remediation = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_remediation_scope.v1",
        "run_id": run_id,
        "if_v2_canTrade_true": [
            "treat retained P9CE blocker as endpoint-schema proof bug",
            "rerun fresh proof using the PIT-safe v2/v3 account proof builder",
            "rerun retained review proving no live-order blocker remains",
        ],
        "if_v2_canTrade_false": [
            "do not proceed to live-order gate",
            "fix account/API-key permissions outside repo",
            "ensure Futures account is enabled",
            "ensure API key has Futures/trading permission",
            "ensure API key IP restriction includes 203.0.113.10",
            "recreate API key if it predates Futures-account enablement",
            "keep withdrawal permission disabled",
            "rerun fresh read-only proof after the account-side fix",
        ],
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_blocker_resolution_scope": ready,
            "allow_future_p9ch_account_proof_owner_gate": ready,
            "pit_safe_account_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cg_control_boundary.v1",
        "run_id": run_id,
        "scope": "blocker_resolution_scope_definition_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
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
    scope_path = proof_root / "blocker_resolution_scope.json"
    builder_path_out = proof_root / "pit_safe_account_proof_builder_contract.json"
    remediation_path = proof_root / "remediation_runbook.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cg_blocker_resolution_scope.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "blocker_resolution_scope": str(scope_path),
        "pit_safe_account_proof_builder_contract": str(builder_path_out),
        "remediation_runbook": str(remediation_path),
        "non_authorization": str(non_auth_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cg_live_order_readiness_blocker_resolution_scope_defined": ready,
        "p9cf_sufficient_for_p9cg_scope_definition": p9cf_summary_ready(p9cf),
        "pit_safe_v2v3_account_proof_builder_defined": ready,
        "can_trade_decision_source": CAN_TRADE_SOURCE,
        "prior_p9ce_blocker": LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "account_v3_canTrade_must_be_ignored_for_permission_decision": True,
        "eligible_for_future_p9ch_account_proof_owner_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "fresh_remote_proof_collection_performed_in_p9cg": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P9CH_GATE,
        "allowed_next_gate_scope": P9CH_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cf_summary": evidence_file(p9cf_path),
            "project_profile": evidence_file(project_profile_path),
            "account_proof_builder": evidence_file(builder_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, scope_definition)
    write_json(builder_path_out, builder_contract)
    write_json(remediation_path, remediation)
    write_json(non_auth_path, non_authorization)
    write_json(control_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cg(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cg_define_live_order_readiness_blocker_resolution_scope(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CG Blocker Resolution Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CG defines blocker-resolution scope only. It does not SSH, read Binance, call an order-test endpoint, collect fresh proofs, run supervisor/timer paths, mutate live state, execute the candidate, replace target plans, or submit orders.",
        "",
        "## Scope",
        "",
        "```text",
        "p9cg_live_order_readiness_blocker_resolution_scope_defined = "
        f"{str(bool(summary['p9cg_live_order_readiness_blocker_resolution_scope_defined'])).lower()}",
        f"prior_p9ce_blocker = {summary['prior_p9ce_blocker']}",
        "replacement_blockers = "
        + ", ".join(summary["replacement_blockers"]),
        f"can_trade_decision_source = {summary['can_trade_decision_source']}",
        "account_v3_canTrade_must_be_ignored_for_permission_decision = true",
        "eligible_for_future_live_order_submission = false",
        "eligible_for_future_candidate_execution = false",
        "fresh_remote_account_read_performed = false",
        "order_test_endpoint_called = false",
        "live_order_submission_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cg(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    print(
        "p9cg_live_order_readiness_blocker_resolution_scope_defined="
        + str(bool(summary["p9cg_live_order_readiness_blocker_resolution_scope_defined"])).lower()
    )
    print(f"can_trade_decision_source={summary['can_trade_decision_source']}")
    print("replacement_blockers=" + ",".join(summary["replacement_blockers"]))
    print("orders_submitted=0")
    print("fill_count=0")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
