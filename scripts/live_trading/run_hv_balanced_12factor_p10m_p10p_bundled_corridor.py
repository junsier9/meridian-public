from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10g_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P10G_PARENT,
)
from scripts.live_trading.run_hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P10H_PARENT,
    p10g_ready,
    stable_payload_sha256,
)
from scripts.live_trading.run_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary import (  # noqa: E402
    build_p10i,
    parse_args as parse_p10i_args,
)
from scripts.live_trading.run_hv_balanced_12factor_p10l_prepare_limited_live_delta_candidate_executor_path_discussion_proposal_package import (  # noqa: E402
    CONTRACT_VERSION as P10L_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P10L_PARENT,
    P10M_GATE,
    P10M_SCOPE,
    RESEARCH_SCORER_REQUIRED_FEATURES,
    terms_ready as p10l_terms_ready,
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


CONTRACT_VERSION = "hv_balanced_12factor_p10m_p10p_bundled_corridor.v1"

P10M_CONTRACT = "hv_balanced_12factor_p10m_review_p10l_proposal_package.v1"
P10N_CONTRACT = "hv_balanced_12factor_p10n_candidate_executor_path_canary_terms.v1"
P10O_CONTRACT = "hv_balanced_12factor_p10o_single_cycle_candidate_executor_path_live_delta_canary.v1"
P10P_CONTRACT = "hv_balanced_12factor_p10p_review_p10o_retained_evidence.v1"

DEFAULT_CORRIDOR_PARENT = "artifacts/live_trading/proof_artifacts/p10m_p10p_bundled_corridor"
DEFAULT_P10M_PARENT = "artifacts/live_trading/proof_artifacts/p10m_review_p10l_limited_executor_path_package"
DEFAULT_P10N_PARENT = "artifacts/live_trading/proof_artifacts/p10n_candidate_executor_path_canary_terms"
DEFAULT_P10O_PARENT = "artifacts/live_trading/proof_artifacts/p10o_single_cycle_candidate_executor_path_live_delta_canary"
DEFAULT_P10P_PARENT = "artifacts/live_trading/proof_artifacts/p10p_review_p10o_retained_evidence"

APPROVE_P10M_DECISION = "approve_p10m_review_p10l_proposal_package_only"
APPROVE_P10N_DECISION = "approve_p10n_single_cycle_candidate_executor_path_canary_terms_only"
APPROVE_P10O_DECISION = "approve_p10o_execute_single_cycle_candidate_executor_path_live_delta_canary_only"
APPROVE_P10P_DECISION = "approve_p10p_review_p10o_retained_evidence_only"

P10N_GATE = "P10N_approve_single_cycle_candidate_executor_path_canary_terms_only_if_separately_requested"
P10O_GATE = "P10O_execute_single_cycle_candidate_executor_path_live_delta_canary_only_if_separately_requested"
P10P_GATE = "P10P_review_p10o_single_cycle_candidate_executor_path_live_delta_canary_only_if_separately_requested"
P10Q_GATE = "P10Q_define_limited_live_delta_candidate_executor_path_followup_scope_only_if_separately_requested"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_MAX_NOTIONAL_USDT = 75.0
DEFAULT_MAX_GROSS_TURNOVER_USDT = 150.0
DEFAULT_ORDER_TYPE = "post_only_limit"
DEFAULT_TIME_IN_FORCE = "GTX"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the owner-authorized P10M-P10P bundled corridor. P10M and P10N "
            "are local review/terms gates. P10O may submit exactly one BTCUSDT "
            "post-only GTX canary through the existing P10I remote submitter if "
            "all proof gates are green. P10P reviews the retained P10O evidence. "
            "No continuous automation, timer-path load, supervisor invocation, "
            "live config mutation, or production executor mutation is authorized."
        )
    )
    parser.add_argument("--corridor-root", default="")
    parser.add_argument("--p10l-summary", default="")
    parser.add_argument("--p10g-summary", default="")
    parser.add_argument("--p10h-summary", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:authorized_p10m_p10p_bundled_corridor",
    )
    parser.add_argument("--order-lifetime-seconds", type=int, default=1)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(parent: str, run_id: str, corridor_root: Path | None, phase_id: str) -> Path:
    if corridor_root is not None:
        return corridor_root / phase_id
    return resolve_path(parent) / run_id


def latest_summary(parent: str | Path, explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(parent, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p10l_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10L_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package_ready") is True
        and summary.get("proposal_package_only") is True
        and summary.get("discussion_proposal_only") is True
        and summary.get("proposal_scope") == "limited_live_delta_candidate_executor_path_discussion"
        and int(summary.get("research_scorer_required_feature_count") or 0) == len(RESEARCH_SCORER_REQUIRED_FEATURES)
        and list(summary.get("research_scorer_required_features") or []) == list(RESEARCH_SCORER_REQUIRED_FEATURES)
        and summary.get("symbol") == DEFAULT_SYMBOL
        and int(summary.get("max_cycles_total") or 0) == 1
        and int(summary.get("max_symbols_total") or 0) == 1
        and int(summary.get("max_candidate_entry_orders_total") or 0) == 1
        and int(summary.get("max_reduce_only_rollback_orders_total") or 0) <= 1
        and abs(float(summary.get("max_notional_usdt") or 0.0) - DEFAULT_MAX_NOTIONAL_USDT) <= 1e-12
        and float(summary.get("max_gross_turnover_usdt") or 0.0) <= DEFAULT_MAX_GROSS_TURNOVER_USDT
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("maker_only_required") is True
        and summary.get("post_only_required") is True
        and summary.get("market_orders_allowed") is False
        and summary.get("candidate_delta_source") == "12factor_scorer_candidate_target_plan"
        and summary.get("candidate_plan_hash_binding_defined") is True
        and summary.get("executor_path_semantics_defined") is True
        and summary.get("baseline_fallback_defined") is True
        and summary.get("kill_switch_defined") is True
        and summary.get("post_run_reconciliation_defined") is True
        and summary.get("eligible_for_future_p10m_review_gate") is True
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
        and summary.get("allowed_next_gate") == P10M_GATE
        and summary.get("allowed_next_gate_scope") == P10M_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10m_review(
    *,
    args: argparse.Namespace,
    run_id: str,
    p10l_path: Path,
    corridor_root: Path | None,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    root = phase_root(DEFAULT_P10M_PARENT, run_id, corridor_root, "p10m_review")
    proof_root = root / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    p10l = load_optional(p10l_path)
    terms_path = source_output_path(p10l, "risk_order_terms")
    proposal_path = source_output_path(p10l, "proposal_package")
    binding_path = source_output_path(p10l, "candidate_plan_hash_binding")
    semantics_path = source_output_path(p10l, "executor_path_semantics")
    fallback_path = source_output_path(p10l, "baseline_fallback_kill_switch")
    reconciliation_path = source_output_path(p10l, "post_run_reconciliation")
    control_path = source_output_path(p10l, "control_boundary_readback")

    terms = load_optional(terms_path)
    term_checks = p10l_terms_ready(terms) if terms else {}
    gates = {
        "owner_decision_p10m_recorded": True,
        "p10l_summary_ready": p10l_summary_ready(p10l),
        "p10l_terms_file_exists": terms_path.exists(),
        "p10l_terms_all_checks_ready": bool(term_checks) and all(term_checks.values()),
        "p10l_proposal_file_exists": proposal_path.exists(),
        "p10l_hash_binding_file_exists": binding_path.exists(),
        "p10l_executor_semantics_file_exists": semantics_path.exists(),
        "p10l_fallback_kill_switch_file_exists": fallback_path.exists(),
        "p10l_reconciliation_file_exists": reconciliation_path.exists(),
        "p10l_control_boundary_file_exists": control_path.exists(),
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"

    owner = {
        "contract_version": "hv_balanced_12factor_p10m_owner_decision.v1",
        "owner": args.owner,
        "decision": APPROVE_P10M_DECISION,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10m_p10l_review.v1",
        "status": status,
        "blockers": blockers,
        "p10l_summary": evidence_file(p10l_path),
        "p10l_terms": evidence_file(terms_path),
        "term_checks": term_checks,
        "conclusion": (
            "p10l_sufficient_for_p10n_terms_gate" if status == "ready" else "p10l_not_sufficient_for_p10n"
        ),
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10m_control_boundary.v1",
        "scope": "review_only",
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "timer_path_loaded": False,
        "supervisor_invoked": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision": str(proof_root / "owner_decision.json"),
        "review": str(proof_root / "p10l_review.json"),
        "control_boundary": str(proof_root / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10M_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10m_review_p10l_proposal_package_ready": status == "ready",
        "p10l_sufficient_for_p10n_terms_gate": status == "ready",
        "review_only": True,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10l_summary": evidence_file(p10l_path)},
        "allowed_next_gate": P10N_GATE,
        "allowed_next_gate_scope": "approve_terms_only_no_execution_no_order",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    for path, payload in (
        (Path(output_files["owner_decision"]), owner),
        (Path(output_files["review"]), review),
        (Path(output_files["control_boundary"]), control),
        (Path(output_files["summary"]), summary),
    ):
        write_json(path, payload)
    return summary, 0 if status == "ready" else 2


def p10n_terms_gate(
    *,
    args: argparse.Namespace,
    run_id: str,
    p10m_summary: dict[str, Any],
    p10m_path: Path,
    p10l_path: Path,
    p10g_path: Path,
    corridor_root: Path | None,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    root = phase_root(DEFAULT_P10N_PARENT, run_id, corridor_root, "p10n_terms")
    proof_root = root / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    p10l = load_optional(p10l_path)
    p10g = load_optional(p10g_path)
    p10l_terms_path = source_output_path(p10l, "risk_order_terms")
    p10l_terms = load_optional(p10l_terms_path)
    candidate_plan_path = source_output_path(p10g, "candidate_target_plan")
    candidate_plan = load_optional(candidate_plan_path)
    candidate_plan_hash = str(p10g.get("candidate_target_plan_sha256") or "")
    candidate_plan_file_hash = stable_payload_sha256(candidate_plan) if candidate_plan else ""
    term_checks = p10l_terms_ready(p10l_terms) if p10l_terms else {}

    terms = {
        "contract_version": "hv_balanced_12factor_p10n_single_cycle_candidate_executor_path_canary_terms.v1",
        "scope": "single_cycle_candidate_executor_path_live_delta_canary",
        "symbol": DEFAULT_SYMBOL,
        "symbol_universe": [DEFAULT_SYMBOL],
        "cycles": 1,
        "continuous_automation": False,
        "max_symbols_total": 1,
        "max_candidate_entry_orders_total": 1,
        "max_reduce_only_rollback_orders_total": 1,
        "max_orders_total": 2,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "maker_only_required": True,
        "post_only_required": True,
        "market_orders_allowed": False,
        "taker_execution_allowed": False,
        "candidate_delta_source": "12factor_scorer_candidate_target_plan",
        "candidate_plan_hash": candidate_plan_hash,
        "candidate_plan_hash_source": "retained_p10g_or_fresh_p10g_rerun",
        "baseline_fallback": "any failed check keeps executor baseline-only and submits zero candidate orders",
        "kill_switch": "candidate_live_delta_enabled=false / executor_target_source=baseline_only",
        "rollback": "cancel open candidate order; reduce-only close only if filled; post-run reconciliation",
    }
    gates = {
        "owner_decision_p10n_recorded": True,
        "p10m_ready": p10m_summary.get("status") == "ready"
        and p10m_summary.get("p10l_sufficient_for_p10n_terms_gate") is True,
        "p10l_summary_ready": p10l_summary_ready(p10l),
        "p10l_terms_all_checks_ready": bool(term_checks) and all(term_checks.values()),
        "p10g_summary_ready": p10g_ready(p10g),
        "candidate_plan_file_hash_matches_p10g": bool(candidate_plan_hash)
        and candidate_plan_hash == candidate_plan_file_hash,
        "symbol_is_btcusdt": terms["symbol"] == DEFAULT_SYMBOL,
        "max_notional_is_75": terms["max_notional_usdt"] == DEFAULT_MAX_NOTIONAL_USDT,
        "gross_turnover_bounded": terms["max_gross_turnover_usdt"] <= DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "post_only_gtx": terms["order_type"] == DEFAULT_ORDER_TYPE
        and terms["time_in_force"] == DEFAULT_TIME_IN_FORCE,
        "single_cycle_only": terms["cycles"] == 1 and terms["continuous_automation"] is False,
        "candidate_hash_binding_present": bool(terms["candidate_plan_hash"]),
        "fallback_defined": "baseline-only" in terms["baseline_fallback"],
        "kill_switch_defined": "candidate_live_delta_enabled=false" in terms["kill_switch"],
        "rollback_defined": "reduce-only close only if filled" in terms["rollback"],
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10n_owner_decision.v1",
        "owner": args.owner,
        "decision": APPROVE_P10N_DECISION,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "future_p10o_single_cycle_candidate_executor_path_canary_approved_if_separately_requested": status == "ready",
        "execute_canary_inside_p10n": False,
        "continuous_automation_approved": False,
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10n_control_boundary.v1",
        "scope": "terms_only",
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "timer_path_loaded": False,
        "supervisor_invoked": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision": str(proof_root / "owner_decision.json"),
        "terms": str(proof_root / "terms.json"),
        "control_boundary": str(proof_root / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10N_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10n_candidate_executor_path_canary_terms_ready": status == "ready",
        "p10m_sufficient_for_p10n": gates["p10m_ready"],
        "candidate_plan_hash": candidate_plan_hash,
        "baseline_target_plan_sha256": p10g.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p10g.get("candidate_target_plan_sha256"),
        "target_plan_diff_sha256": p10g.get("target_plan_diff_sha256"),
        "symbol": terms["symbol"],
        "max_notional_usdt": terms["max_notional_usdt"],
        "max_gross_turnover_usdt": terms["max_gross_turnover_usdt"],
        "max_orders_total": terms["max_orders_total"],
        "order_type": terms["order_type"],
        "time_in_force": terms["time_in_force"],
        "future_p10o_execution_authorized_if_separately_requested": status == "ready",
        "live_order_submission_authorized_now": False,
        "candidate_executor_path_execution_authorized_now": False,
        "target_plan_replacement_authorized_now": False,
        "executor_input_mutation_authorized_now": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10m_summary": evidence_file(p10m_path),
            "p10l_summary": evidence_file(p10l_path),
            "p10l_terms": evidence_file(p10l_terms_path),
            "p10g_summary": evidence_file(p10g_path),
            "candidate_target_plan": evidence_file(candidate_plan_path),
        },
        "allowed_next_gate": P10O_GATE,
        "allowed_next_gate_scope": "execute_one_btcusdt_post_only_gtx_candidate_executor_path_canary_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    for path, payload in (
        (Path(output_files["owner_decision"]), owner),
        (Path(output_files["terms"]), terms),
        (Path(output_files["control_boundary"]), control),
        (Path(output_files["summary"]), summary),
    ):
        write_json(path, payload)
    return summary, 0 if status == "ready" else 2


def p10o_execute(
    *,
    args: argparse.Namespace,
    run_id: str,
    p10n_summary: dict[str, Any],
    p10n_path: Path,
    p10g_path: Path,
    p10h_path: Path,
    corridor_root: Path | None,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    root = phase_root(DEFAULT_P10O_PARENT, run_id, corridor_root, "p10o_execution")
    proof_root = root / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    p10g = load_optional(p10g_path)
    candidate_plan_path = source_output_path(p10g, "candidate_target_plan")
    baseline_plan_path = source_output_path(p10g, "baseline_target_plan")
    diff_path = source_output_path(p10g, "target_plan_diff")
    candidate_hash = str(p10g.get("candidate_target_plan_sha256") or "")
    baseline_hash = str(p10g.get("baseline_target_plan_sha256") or "")

    owner = {
        "contract_version": "hv_balanced_12factor_p10o_owner_decision.v1",
        "owner": args.owner,
        "decision": APPROVE_P10O_DECISION,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "single_cycle_candidate_executor_path_canary_approved": p10n_summary.get("status") == "ready",
        "max_orders_total": 2,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "continuous_automation_approved": False,
    }
    replacement_binding = {
        "contract_version": "hv_balanced_12factor_p10o_candidate_executor_input_binding.v1",
        "scope": "single_cycle_candidate_executor_path_canary_wrapper",
        "baseline_target_plan_sha256": baseline_hash,
        "candidate_target_plan_sha256": candidate_hash,
        "approved_candidate_plan_hash": p10n_summary.get("candidate_plan_hash"),
        "candidate_plan_hash_matches_terms": candidate_hash == str(p10n_summary.get("candidate_plan_hash") or ""),
        "executor_input_before_source": "baseline_target_plan",
        "executor_input_for_canary_source": "candidate_target_plan",
        "executor_input_for_canary_sha256": candidate_hash,
        "post_cycle_executor_input_source": "baseline_target_plan",
        "post_cycle_executor_input_sha256": baseline_hash,
        "production_executor_input_mutation_performed": False,
        "live_supervisor_target_plan_replacement_performed": False,
        "timer_path_load_performed": False,
        "candidate_order_delta_source": "P10G target_plan_diff / BTCUSDT delta",
    }
    pre_gates = {
        "owner_decision_p10o_recorded": owner["single_cycle_candidate_executor_path_canary_approved"],
        "p10n_ready": p10n_summary.get("status") == "ready"
        and p10n_summary.get("future_p10o_execution_authorized_if_separately_requested") is True,
        "p10g_ready": p10g_ready(p10g),
        "candidate_hash_matches_p10n": replacement_binding["candidate_plan_hash_matches_terms"],
        "candidate_plan_exists": candidate_plan_path.exists(),
        "baseline_plan_exists": baseline_plan_path.exists(),
        "target_plan_diff_exists": diff_path.exists(),
        "p10h_summary_exists_for_reused_submitter": p10h_path.exists(),
    }
    blockers = sorted(key for key, ready in pre_gates.items() if not ready)
    p10i_summary: dict[str, Any] = {}
    p10i_exit = 2
    if not blockers:
        p10i_args = parse_p10i_args(
            [
                "--output-root",
                str(root / "underlying_p10i_live_delta_submitter"),
                "--p10h-summary",
                str(p10h_path),
                "--p10g-summary",
                str(p10g_path),
                "--order-lifetime-seconds",
                str(int(args.order_lifetime_seconds or 0)),
                "--owner-decision-source",
                "user_chat:p10o_underlying_p10i_submitter_for_p10m_p10p_corridor",
            ]
        )
        p10i_summary, p10i_exit = build_p10i(p10i_args)
        if p10i_exit != 0:
            blockers.append("underlying_p10i_submitter_failed_or_blocked")
        if p10i_summary.get("status") != "ready":
            blockers.append("underlying_p10i_summary_not_ready")

    order_checks = {
        "underlying_p10i_ready": p10i_summary.get("status") == "ready",
        "orders_submitted_exactly_one": int(p10i_summary.get("orders_submitted") or 0) == 1,
        "orders_canceled_at_most_one": int(p10i_summary.get("orders_canceled") or 0) <= 1,
        "zero_fills": int(p10i_summary.get("fill_count") or 0) == 0,
        "zero_trades": int(p10i_summary.get("trade_count") or 0) == 0,
        "actual_live_order_submission_performed": p10i_summary.get("actual_live_order_submission_performed") is True,
        "fresh_pre_submit_readback_performed": p10i_summary.get("fresh_pre_submit_readback_performed") is True,
        "candidate_hash_bound": p10i_summary.get("candidate_target_plan_sha256") == candidate_hash,
        "remote_control_boundary_unchanged": p10i_summary.get("remote_control_boundary_unchanged") is True,
        "production_executor_input_not_mutated": p10i_summary.get("actual_executor_input_mutation_performed") is False,
        "production_target_plan_not_replaced": p10i_summary.get("actual_target_plan_replacement_performed") is False,
        "timer_not_loaded": p10i_summary.get("timer_path_load_authorized") is False,
        "supervisor_not_invoked": p10i_summary.get("supervisor_invocation_authorized") is False,
        "continuous_automation_disabled": p10i_summary.get("continuous_automation_enabled") is False,
    }
    if p10i_summary:
        blockers.extend(key for key, ready in order_checks.items() if not ready)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    reconciliation = {
        "contract_version": "hv_balanced_12factor_p10o_post_run_reconciliation.v1",
        "status": status,
        "blockers": blockers,
        "orders_submitted": int(p10i_summary.get("orders_submitted") or 0),
        "orders_canceled": int(p10i_summary.get("orders_canceled") or 0),
        "fill_count": int(p10i_summary.get("fill_count") or 0),
        "trade_count": int(p10i_summary.get("trade_count") or 0),
        "candidate_plan_hash": candidate_hash,
        "baseline_fallback_post_cycle_source": "baseline_target_plan",
        "post_cycle_executor_input_sha256": baseline_hash,
        "remote_control_boundary_unchanged": p10i_summary.get("remote_control_boundary_unchanged") is True,
        "continuous_automation_enabled": False,
        "second_cycle_attempted": False,
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision": str(proof_root / "owner_decision.json"),
        "replacement_binding": str(proof_root / "candidate_executor_input_binding.json"),
        "post_run_reconciliation": str(proof_root / "post_run_reconciliation.json"),
    }
    if p10i_summary:
        output_files["underlying_p10i_summary"] = str(
            root / "underlying_p10i_live_delta_submitter" / "summary.json"
        )
    summary = {
        "contract_version": P10O_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10o_single_cycle_candidate_executor_path_live_delta_canary_ready": status == "ready",
        "p10n_sufficient_for_p10o_execution": pre_gates["p10n_ready"],
        "candidate_executor_path_execution_authorized": True,
        "candidate_executor_path_execution_performed": status == "ready",
        "candidate_target_plan_replacement_for_canary_performed": status == "ready",
        "candidate_target_plan_sha256": candidate_hash,
        "baseline_target_plan_sha256": baseline_hash,
        "executor_input_for_canary_sha256": candidate_hash,
        "post_cycle_executor_input_sha256": baseline_hash,
        "actual_live_order_submission_performed": p10i_summary.get("actual_live_order_submission_performed") is True,
        "orders_submitted": int(p10i_summary.get("orders_submitted") or 0),
        "orders_canceled": int(p10i_summary.get("orders_canceled") or 0),
        "fill_count": int(p10i_summary.get("fill_count") or 0),
        "trade_count": int(p10i_summary.get("trade_count") or 0),
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "symbol": DEFAULT_SYMBOL,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "production_executor_input_mutation_performed": False,
        "actual_target_plan_replacement_performed": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automation_enabled": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "baseline_fallback_post_cycle_ready": status == "ready",
        "kill_switch_remains_available": True,
        "post_run_reconciliation_ready": status == "ready",
        "pre_gates": pre_gates,
        "order_checks": order_checks,
        "blockers": blockers,
        "source_evidence": {
            "p10n_summary": evidence_file(p10n_path),
            "p10g_summary": evidence_file(p10g_path),
            "p10h_summary": evidence_file(p10h_path),
            "candidate_target_plan": evidence_file(candidate_plan_path),
            "baseline_target_plan": evidence_file(baseline_plan_path),
            "target_plan_diff": evidence_file(diff_path),
        },
        "allowed_next_gate": P10P_GATE,
        "allowed_next_gate_scope": "review_p10o_retained_evidence_no_new_order_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    for path, payload in (
        (Path(output_files["owner_decision"]), owner),
        (Path(output_files["replacement_binding"]), replacement_binding),
        (Path(output_files["post_run_reconciliation"]), reconciliation),
        (Path(output_files["summary"]), summary),
    ):
        write_json(path, payload)
    return summary, 0 if status == "ready" else 2


def p10p_review(
    *,
    args: argparse.Namespace,
    run_id: str,
    p10o_summary: dict[str, Any],
    p10o_path: Path,
    corridor_root: Path | None,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    root = phase_root(DEFAULT_P10P_PARENT, run_id, corridor_root, "p10p_review")
    proof_root = root / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    review_checks = {
        "owner_decision_p10p_recorded": True,
        "p10o_summary_ready": p10o_summary.get("status") == "ready",
        "candidate_executor_path_canary_performed": p10o_summary.get("candidate_executor_path_execution_performed") is True,
        "single_order_or_less": int(p10o_summary.get("orders_submitted") or 0) <= 1,
        "zero_fills": int(p10o_summary.get("fill_count") or 0) == 0,
        "zero_trades": int(p10o_summary.get("trade_count") or 0) == 0,
        "post_cycle_baseline_fallback_ready": p10o_summary.get("baseline_fallback_post_cycle_ready") is True,
        "production_executor_input_not_mutated": p10o_summary.get("production_executor_input_mutation_performed") is False,
        "production_target_plan_not_replaced": p10o_summary.get("actual_target_plan_replacement_performed") is False,
        "timer_not_loaded": p10o_summary.get("timer_path_load_authorized") is False,
        "supervisor_not_invoked": p10o_summary.get("supervisor_invocation_authorized") is False,
        "continuous_automation_disabled": p10o_summary.get("continuous_automation_enabled") is False,
        "remote_no_sync_no_file_write": p10o_summary.get("remote_sync_performed") is False
        and int(p10o_summary.get("remote_files_written") or 0) == 0,
    }
    blockers = sorted(key for key, ready in review_checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10p_owner_decision.v1",
        "owner": args.owner,
        "decision": APPROVE_P10P_DECISION,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_followup_scope_discussion_allowed": status == "ready",
        "live_order_submission_without_new_gate_approved": False,
        "continuous_automation_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10p_retained_evidence_review.v1",
        "status": status,
        "blockers": blockers,
        "p10o_summary": evidence_file(p10o_path),
        "conclusion": (
            "p10o_sufficient_for_limited_live_delta_candidate_executor_path_followup_discussion"
            if status == "ready"
            else "p10o_not_sufficient_for_followup"
        ),
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision": str(proof_root / "owner_decision.json"),
        "review": str(proof_root / "p10o_review.json"),
    }
    summary = {
        "contract_version": P10P_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10p_review_p10o_retained_evidence_ready": status == "ready",
        "p10o_sufficient_for_limited_live_delta_candidate_executor_path_followup_discussion": status == "ready",
        "p10o_sufficient_for_live_order_submission_without_new_gate": False,
        "p10o_sufficient_for_continuous_automated_order_flow": False,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "review_checks": review_checks,
        "blockers": blockers,
        "source_evidence": {"p10o_summary": evidence_file(p10o_path)},
        "allowed_next_gate": P10Q_GATE if status == "ready" else "",
        "allowed_next_gate_scope": (
            "define_followup_scope_only_no_new_order_no_continuous_automation" if status == "ready" else ""
        ),
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    for path, payload in (
        (Path(output_files["owner_decision"]), owner),
        (Path(output_files["review"]), review),
        (Path(output_files["summary"]), summary),
    ):
        write_json(path, payload)
    return summary, 0 if status == "ready" else 2


def write_corridor_summary(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "summary.json", payload)


def run_corridor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    corridor_root = resolve_path(args.corridor_root) if str(args.corridor_root or "").strip() else resolve_path(DEFAULT_CORRIDOR_PARENT) / run_id
    p10l_path = latest_summary(P10L_PARENT, args.p10l_summary)
    p10g_path = latest_summary(P10G_PARENT, args.p10g_summary)
    p10h_path = latest_summary(P10H_PARENT, args.p10h_summary)

    steps: list[dict[str, Any]] = []
    status = "ready"
    blockers: list[str] = []

    p10m, p10m_code = p10m_review(
        args=args,
        run_id=run_id,
        p10l_path=p10l_path,
        corridor_root=corridor_root,
        now=started,
    )
    p10m_path = resolve_path(p10m["output_files"]["summary"])
    steps.append({"gate": "P10M", "status": p10m.get("status"), "summary": evidence_file(p10m_path)})
    if p10m_code != 0:
        status = "blocked"
        blockers.append("p10m_blocked")
    p10n: dict[str, Any] = {}
    p10n_path = Path("")
    if status == "ready":
        p10n, p10n_code = p10n_terms_gate(
            args=args,
            run_id=run_id,
            p10m_summary=p10m,
            p10m_path=p10m_path,
            p10l_path=p10l_path,
            p10g_path=p10g_path,
            corridor_root=corridor_root,
            now=started,
        )
        p10n_path = resolve_path(p10n["output_files"]["summary"])
        steps.append({"gate": "P10N", "status": p10n.get("status"), "summary": evidence_file(p10n_path)})
        if p10n_code != 0:
            status = "blocked"
            blockers.append("p10n_blocked")

    p10o: dict[str, Any] = {}
    p10o_path = Path("")
    if status == "ready":
        p10o, p10o_code = p10o_execute(
            args=args,
            run_id=run_id,
            p10n_summary=p10n,
            p10n_path=p10n_path,
            p10g_path=p10g_path,
            p10h_path=p10h_path,
            corridor_root=corridor_root,
            now=utc_now(),
        )
        p10o_path = resolve_path(p10o["output_files"]["summary"])
        steps.append({"gate": "P10O", "status": p10o.get("status"), "summary": evidence_file(p10o_path)})
        if p10o_code != 0:
            status = "blocked"
            blockers.append("p10o_blocked")

        p10p, p10p_code = p10p_review(
            args=args,
            run_id=run_id,
            p10o_summary=p10o,
            p10o_path=p10o_path,
            corridor_root=corridor_root,
            now=utc_now(),
        )
        p10p_path = resolve_path(p10p["output_files"]["summary"])
        steps.append({"gate": "P10P", "status": p10p.get("status"), "summary": evidence_file(p10p_path)})
        if p10p_code != 0:
            status = "blocked"
            blockers.append("p10p_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10m_p10p_bundled_corridor_ready": status == "ready",
        "corridor_scope": "P10M_review + P10N_terms + P10O_single_cycle_candidate_executor_path_canary + P10P_review",
        "hard_limits": {
            "symbol": DEFAULT_SYMBOL,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "cycles": 1,
            "continuous_automation": False,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
        },
        "live_order_submission_performed": bool(p10o.get("actual_live_order_submission_performed") is True),
        "orders_submitted": int(p10o.get("orders_submitted") or 0),
        "orders_canceled": int(p10o.get("orders_canceled") or 0),
        "fill_count": int(p10o.get("fill_count") or 0),
        "trade_count": int(p10o.get("trade_count") or 0),
        "production_executor_input_mutation_performed": False,
        "actual_target_plan_replacement_performed": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automation_enabled": False,
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {
            "p10l_summary": evidence_file(p10l_path),
            "p10g_summary": evidence_file(p10g_path),
            "p10h_summary": evidence_file(p10h_path),
            "project_profile": evidence_file(resolve_path(args.project_profile)),
        },
        "allowed_next_gate": P10Q_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "define_followup_scope_only_no_new_order_no_continuous_automation" if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(corridor_root / "summary.json")},
    }
    write_corridor_summary(corridor_root, summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, code = run_corridor(parse_args(argv))
    print("status=" + str(summary["status"]))
    print("run_id=" + str(summary["run_id"]))
    print("orders_submitted=" + str(summary["orders_submitted"]))
    print("orders_canceled=" + str(summary["orders_canceled"]))
    print("fill_count=" + str(summary["fill_count"]))
    print("summary=" + str(summary["output_files"]["summary"]))
    if summary.get("blockers"):
        print("blockers=" + ",".join(summary["blockers"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
