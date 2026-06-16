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

from scripts.live_trading.run_hv_balanced_12factor_p10m_p10p_bundled_corridor import (  # noqa: E402
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_SYMBOL,
    DEFAULT_TIME_IN_FORCE,
    P10P_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_12factor_p10z_p10ab_followup_canary_corridor import (  # noqa: E402
    P10AB_CONTRACT,
    P10AC_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10ac_p10ae_limited_live_delta_expansion_corridor.v1"
P10AC_CONTRACT = "hv_balanced_12factor_p10ac_define_limited_live_delta_expansion_scope.v1"
P10AD_CONTRACT = "hv_balanced_12factor_p10ad_prepare_limited_live_delta_expansion_package.v1"
P10AE_CONTRACT = "hv_balanced_12factor_p10ae_review_limited_live_delta_expansion_package.v1"

DEFAULT_P10AB_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10z_p10ab_followup_canary_corridor"
DEFAULT_P10P_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10m_p10p_bundled_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10ac_p10ae_limited_live_delta_expansion_corridor"

P10AD_GATE = "P10AD_prepare_post_followup_canary_limited_live_delta_expansion_proposal_package_only_if_separately_requested"
P10AE_GATE = "P10AE_review_p10ad_post_followup_canary_limited_live_delta_expansion_package_only_if_separately_requested"
P10AF_GATE = "P10AF_owner_gate_allow_prepare_limited_live_delta_expansion_execution_terms_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AC-P10AE after retained P10AB. This corridor is local and "
            "proof-artifacts-only: it defines the limited live_delta expansion "
            "discussion scope, prepares a proposal package, and reviews that "
            "package. It does not SSH, call Binance, submit/cancel orders, "
            "invoke timer/supervisor paths, remote sync, or mutate live config, "
            "operator state, target plans, or executor input."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10ab-summary", default="")
    parser.add_argument("--p10p-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10ab",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_p10ab_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10AB_SEARCH_PARENT, "*/p10ab_review/summary.json")


def latest_p10p_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10P_SEARCH_PARENT, "*/p10p_review/summary.json")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def source_evidence_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def sibling_actual_order_readback(p10ab_path: Path) -> Path:
    if not p10ab_path:
        return Path("")
    return resolve_path(p10ab_path).parent / "proof" / "actual_order_submission_readback.json"


def p10ab_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AB_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10ab_review_p10aa_retained_evidence_ready") is True
        and summary.get("p10aa_sufficient_for_future_limited_scope_discussion") is True
        and summary.get("p10aa_sufficient_for_additional_live_order_without_new_gate") is False
        and summary.get("p10aa_sufficient_for_continuous_automated_order_flow") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
        and summary.get("allowed_next_gate") == P10AC_GATE
        and summary.get("allowed_next_gate_scope") == "define_scope_only_no_new_order_no_continuous_automation_no_timer_supervisor"
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10p_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10P_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10p_review_p10o_retained_evidence_ready") is True
        and summary.get("p10o_sufficient_for_limited_live_delta_candidate_executor_path_followup_discussion") is True
        and summary.get("p10o_sufficient_for_live_order_submission_without_new_gate") is False
        and summary.get("p10o_sufficient_for_continuous_automated_order_flow") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
    )


def successful_canary(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and summary.get("actual_live_order_submission_performed") is True
        and int(summary.get("orders_submitted") or 0) == 1
        and int(summary.get("orders_canceled") or 0) <= 1
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
        and summary.get("production_executor_input_mutation_performed") is False
        and summary.get("actual_target_plan_replacement_performed") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automation_enabled") is False
        and summary.get("remote_sync_performed") is False
        and int(summary.get("remote_files_written") or 0) == 0
    )


def actual_readback_ready(readback: dict[str, Any]) -> bool:
    checks = dict(readback.get("ready_checks") or {})
    return (
        readback.get("contract_version") == "hv_balanced_12factor_p10ab_actual_order_submission_readback.v1"
        and readback.get("status") == "ready"
        and readback.get("submit_status") == "ok"
        and readback.get("submit_status_code") == 200
        and readback.get("query_status") == "ok"
        and readback.get("cancel_status") == "ok"
        and readback.get("orders_submitted") == 1
        and readback.get("orders_canceled") == 1
        and readback.get("fill_count") == 0
        and readback.get("trade_count") == 0
        and all(checks.values())
    )


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def no_side_effects() -> dict[str, Any]:
    return {
        "proof_artifacts_only": True,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
        "target_plan_replacement_performed": False,
        "executor_input_mutation_performed": False,
        "timer_path_load_performed": False,
        "supervisor_invocation_performed": False,
    }


def non_authorization() -> dict[str, Any]:
    return {
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
    }


def build_p10ac(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ab: dict[str, Any],
    p10ab_path: Path,
    p10aa: dict[str, Any],
    p10aa_path: Path,
    p10p: dict[str, Any],
    p10p_path: Path,
    p10o: dict[str, Any],
    p10o_path: Path,
    actual_path: Path,
    actual: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10ac_recorded": True,
        "p10ab_ready_for_scope_definition": p10ab_ready(p10ab),
        "p10aa_followup_canary_ready": successful_canary(p10aa),
        "p10ab_actual_order_readback_ready": actual_readback_ready(actual),
        "p10p_prior_canary_review_ready": p10p_ready(p10p),
        "p10o_prior_canary_ready": successful_canary(p10o),
        "scope_is_define_only": True,
        "no_new_order_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    scope = {
        "contract_version": "hv_balanced_12factor_p10ac_limited_expansion_scope.v1",
        "status": status,
        "scope": "post_followup_canary_limited_live_delta_expansion_discussion_only",
        "scope_definition_only": True,
        "retained_evidence_basis": [
            "P10O first single-cycle candidate executor-path canary ready",
            "P10AA follow-up single-cycle candidate executor-path canary ready",
            "both canaries retained zero fills and zero trades",
            "both canaries retained no production executor/timer/supervisor mutation",
        ],
        "allowed_followup_work": [
            "prepare a proposal package for a future owner gate",
            "define bounded manual execution terms for future discussion",
            "define fresh-proof, hash-binding, baseline-fallback, kill-switch, and reconciliation requirements",
        ],
        "not_authorized": [
            "new live order",
            "additional candidate execution",
            "continuous automated order flow",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "live config/operator mutation",
            "production target plan replacement",
            "production executor input mutation",
        ],
        "allowed_next_gate": P10AD_GATE,
        "allowed_next_gate_scope": "prepare_package_only_no_order_no_remote_no_timer_supervisor",
        "allowed_next_gate_must_be_separately_requested": True,
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10ac_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ac_define_limited_live_delta_expansion_scope_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10ac_scope", {"owner_decision": owner, "scope": scope})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "scope": str(phase_dir / "proof" / "scope.json"),
    }
    summary = {
        "contract_version": P10AC_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ac_limited_live_delta_expansion_scope_ready": status == "ready",
        "scope_definition_only": True,
        "prior_ready_canary_count": 2 if gates["p10aa_followup_canary_ready"] and gates["p10o_prior_canary_ready"] else 0,
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10ab_summary": evidence_file(p10ab_path),
            "p10aa_summary": evidence_file(p10aa_path),
            "p10ab_actual_order_readback": evidence_file(actual_path),
            "p10p_summary": evidence_file(p10p_path),
            "p10o_summary": evidence_file(p10o_path),
        },
        "allowed_next_gate": P10AD_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "prepare_package_only_no_order_no_remote_no_timer_supervisor" if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10ad(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ac: dict[str, Any],
    p10ac_path: Path,
    p10aa: dict[str, Any],
    p10o: dict[str, Any],
    actual: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10ad_recorded": True,
        "p10ac_ready": p10ac.get("status") == "ready"
        and p10ac.get("p10ac_limited_live_delta_expansion_scope_ready") is True,
        "p10ac_allowed_p10ad": p10ac.get("allowed_next_gate") == P10AD_GATE,
        "package_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    actual_plan = dict(actual.get("actual_submitter_canary_order_plan") or {})
    package = {
        "contract_version": "hv_balanced_12factor_p10ad_limited_expansion_package.v1",
        "status": status,
        "package_scope": "future_limited_live_delta_expansion_owner_gate_preparation_only",
        "retained_canary_evidence": {
            "prior_p10o": {
                "orders_submitted": p10o.get("orders_submitted"),
                "orders_canceled": p10o.get("orders_canceled"),
                "fill_count": p10o.get("fill_count"),
                "trade_count": p10o.get("trade_count"),
                "candidate_target_plan_sha256": p10o.get("candidate_target_plan_sha256"),
                "baseline_target_plan_sha256": p10o.get("baseline_target_plan_sha256"),
            },
            "followup_p10aa": {
                "orders_submitted": p10aa.get("orders_submitted"),
                "orders_canceled": p10aa.get("orders_canceled"),
                "fill_count": p10aa.get("fill_count"),
                "trade_count": p10aa.get("trade_count"),
                "candidate_target_plan_sha256": p10aa.get("candidate_target_plan_sha256"),
                "baseline_target_plan_sha256": p10aa.get("baseline_target_plan_sha256"),
                "actual_submitter_plan": actual_plan,
            },
        },
        "future_discussion_terms_not_execution": {
            "symbols": [DEFAULT_SYMBOL],
            "max_symbols_total": 1,
            "max_cycles_total_per_future_gate": 1,
            "max_candidate_entry_orders_total_per_future_gate": 1,
            "max_orders_total_per_future_gate": 2,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
            "minimum_maker_buffer_ticks_for_future_discussion": 50,
            "continuous_automation_allowed": False,
            "timer_supervisor_path_allowed": False,
            "remote_sync_allowed": False,
        },
        "required_before_any_future_order_gate": [
            "separate owner gate",
            "fresh or explicitly re-bound candidate plan hash",
            "fresh account canTrade proof from /fapi/v2/account",
            "fresh open-order/order/fill/trade baseline",
            "fresh BTCUSDT order book and exchange filters",
            "post-only non-crossing price proof with maker buffer",
            "pre/post static control-boundary readback",
            "post-run order/cancel/fill/trade reconciliation",
        ],
        "baseline_fallback_and_kill_switch": [
            "any proof failure keeps executor baseline-only",
            "candidate_live_delta_enabled=false remains kill switch",
            "executor target source returns to baseline after any future canary",
            "no future gate may authorize continuous automated order flow",
        ],
        "not_authorized_by_p10ad": [
            "live order submission",
            "candidate execution",
            "production target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10ad_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ad_prepare_limited_live_delta_expansion_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "package_preparation_approved": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10ad_package", {"owner_decision": owner, "proposal_package": package})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "proposal_package": str(phase_dir / "proof" / "proposal_package.json"),
    }
    summary = {
        "contract_version": P10AD_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ad_limited_live_delta_expansion_package_ready": status == "ready",
        "package_only": True,
        "eligible_for_p10ae_review": status == "ready",
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10ac_summary": evidence_file(p10ac_path)},
        "allowed_next_gate": P10AE_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_package_only_no_order_no_remote_no_timer_supervisor" if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10ae(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ad: dict[str, Any],
    p10ad_path: Path,
) -> tuple[dict[str, Any], Path]:
    package_path = source_output_path(p10ad, "proposal_package")
    package = load_optional(package_path)
    terms = dict(package.get("future_discussion_terms_not_execution") or {})
    gates = {
        "owner_decision_p10ae_recorded": True,
        "p10ad_ready": p10ad.get("status") == "ready"
        and p10ad.get("p10ad_limited_live_delta_expansion_package_ready") is True,
        "p10ad_allowed_p10ae": p10ad.get("allowed_next_gate") == P10AE_GATE,
        "proposal_package_exists": package_path.exists() and package_path.is_file(),
        "future_terms_stay_single_symbol": terms.get("symbols") == [DEFAULT_SYMBOL],
        "future_terms_post_only_gtx": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "future_terms_no_continuous_automation": terms.get("continuous_automation_allowed") is False,
        "future_terms_no_timer_supervisor": terms.get("timer_supervisor_path_allowed") is False,
        "review_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    review = {
        "contract_version": "hv_balanced_12factor_p10ae_limited_expansion_package_review.v1",
        "status": status,
        "blockers": blockers,
        "p10ad_summary": evidence_file(p10ad_path),
        "p10ad_proposal_package": evidence_file(package_path),
        "p10ad_package_sufficient_for_p10ae_review": status == "ready",
        "p10ad_package_sufficient_for_future_p10af_owner_gate": status == "ready",
        "p10ad_package_sufficient_for_live_order_submission_without_p10af": False,
        "p10ad_package_sufficient_for_continuous_automation": False,
        "remaining_required_gate_before_any_future_order": P10AF_GATE,
        "does_not_authorize": [
            "new live order",
            "additional candidate execution",
            "continuous automated order flow",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "production executor input mutation",
            "production target plan replacement",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10ae_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ae_review_limited_live_delta_expansion_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_p10af_owner_gate_may_be_requested": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10ae_review", {"owner_decision": owner, "review": review})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "review": str(phase_dir / "proof" / "review.json"),
    }
    summary = {
        "contract_version": P10AE_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ae_review_limited_live_delta_expansion_package_ready": status == "ready",
        "p10ad_package_sufficient_for_future_p10af_owner_gate": status == "ready",
        "p10ad_package_sufficient_for_live_order_submission_without_p10af": False,
        "review_only": True,
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10ad_summary": evidence_file(p10ad_path), "p10ad_proposal_package": evidence_file(package_path)},
        "allowed_next_gate": P10AF_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_only_to_allow_prepare_future_limited_execution_terms_no_order_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def run_corridor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)

    p10ab_path = latest_p10ab_summary(args.p10ab_summary)
    p10ab = load_optional(p10ab_path)
    p10aa_path = source_evidence_path(p10ab, "p10aa_summary")
    p10aa = load_optional(p10aa_path)
    actual_path = sibling_actual_order_readback(p10ab_path)
    actual = load_optional(actual_path)
    p10p_path = latest_p10p_summary(args.p10p_summary)
    p10p = load_optional(p10p_path)
    p10o_path = source_evidence_path(p10p, "p10o_summary")
    p10o = load_optional(p10o_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10ac, p10ac_path = build_p10ac(
        root=root,
        run_id=run_id,
        args=args,
        now=started,
        p10ab=p10ab,
        p10ab_path=p10ab_path,
        p10aa=p10aa,
        p10aa_path=p10aa_path,
        p10p=p10p,
        p10p_path=p10p_path,
        p10o=p10o,
        p10o_path=p10o_path,
        actual_path=actual_path,
        actual=actual,
    )
    steps.append({"gate": "P10AC", "status": p10ac.get("status"), "summary": evidence_file(p10ac_path)})
    if p10ac.get("status") != "ready":
        status = "blocked"
        blockers.append("p10ac_blocked")

    p10ad: dict[str, Any] = {}
    p10ad_path = Path("")
    if status == "ready":
        p10ad, p10ad_path = build_p10ad(
            root=root,
            run_id=run_id,
            args=args,
            now=utc_now(),
            p10ac=p10ac,
            p10ac_path=p10ac_path,
            p10aa=p10aa,
            p10o=p10o,
            actual=actual,
        )
        steps.append({"gate": "P10AD", "status": p10ad.get("status"), "summary": evidence_file(p10ad_path)})
        if p10ad.get("status") != "ready":
            status = "blocked"
            blockers.append("p10ad_blocked")

    p10ae: dict[str, Any] = {}
    p10ae_path = Path("")
    if status == "ready":
        p10ae, p10ae_path = build_p10ae(
            root=root,
            run_id=run_id,
            args=args,
            now=utc_now(),
            p10ad=p10ad,
            p10ad_path=p10ad_path,
        )
        steps.append({"gate": "P10AE", "status": p10ae.get("status"), "summary": evidence_file(p10ae_path)})
        if p10ae.get("status") != "ready":
            status = "blocked"
            blockers.append("p10ae_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10ac_p10ae_limited_live_delta_expansion_corridor_ready": status == "ready",
        "corridor_scope": "P10AC scope definition + P10AD proposal package + P10AE package review",
        **non_authorization(),
        **no_side_effects(),
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {"p10ab_summary": evidence_file(p10ab_path)},
        "allowed_next_gate": P10AF_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_only_to_allow_prepare_future_limited_execution_terms_no_order_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(root / "summary.json")},
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, code = run_corridor(parse_args(argv))
    print("status=" + str(summary["status"]))
    print("run_id=" + str(summary["run_id"]))
    print("orders_submitted=" + str(summary["orders_submitted"]))
    print("fill_count=" + str(summary["fill_count"]))
    print("summary=" + str(summary["output_files"]["summary"]))
    if summary.get("blockers"):
        print("blockers=" + ",".join(summary["blockers"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
