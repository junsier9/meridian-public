from __future__ import annotations

import argparse
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as PHASE6_PARENT,
    PHASE2_PARENT,
    PHASE2B_PARENT,
    PHASE3_PARENT,
    PHASE4_PARENT,
    TARGET_CONTRIBUTION,
    evidence_file,
    is_zero_order,
    latest_match,
    load_json,
    no_live_mutation,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase7_guarded_live_shadow_draft.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase7_guarded_live_shadow_draft"
)
APPROVE_P7_DECISION = "approve_guarded_live_shadow_plan_only"
DEFAULT_MAX_REBUILD_AGE_SECONDS = 3600
LIVE_CONFIG_PATH = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a guarded live-shadow integration draft for the hv_balanced "
            "DTH60/CoinGlass candidate. Writes evidence only; never changes live config."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--owner-review-pack", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P7_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:approved_p7")
    parser.add_argument("--phase2-summary", default="")
    parser.add_argument("--phase2b-summary", default="")
    parser.add_argument("--phase3-summary", default="")
    parser.add_argument("--phase4-summary", default="")
    parser.add_argument("--live-config-path", default=LIVE_CONFIG_PATH)
    parser.add_argument("--max-rebuild-age-seconds", type=int, default=DEFAULT_MAX_REBUILD_AGE_SECONDS)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_z(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def age_seconds(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds()


def within_age(later: datetime | None, earlier: datetime | None, max_age: int) -> bool:
    age = age_seconds(later, earlier)
    return age is not None and 0 <= age <= max_age


def build_phase7_draft(
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
        "owner_review_pack": (
            resolve_path(args.owner_review_pack)
            if args.owner_review_pack
            else latest_match(PHASE6_PARENT, "*/owner_review_pack.json")
        ),
        "phase2": resolve_path(args.phase2_summary) if args.phase2_summary else latest_match(PHASE2_PARENT, "*/summary.json"),
        "phase2b": resolve_path(args.phase2b_summary) if args.phase2b_summary else latest_match(PHASE2B_PARENT, "*/summary.json"),
        "phase3": resolve_path(args.phase3_summary) if args.phase3_summary else latest_match(PHASE3_PARENT, "*/summary.json"),
        "phase4": resolve_path(args.phase4_summary) if args.phase4_summary else latest_match(PHASE4_PARENT, "*/summary.json"),
        "live_config": resolve_path(args.live_config_path),
    }

    owner_review_pack = load_json(paths["owner_review_pack"]) if paths["owner_review_pack"].exists() else {}
    phase2 = load_json(paths["phase2"]) if paths["phase2"].exists() else {}
    phase2b = load_json(paths["phase2b"]) if paths["phase2b"].exists() else {}
    phase3 = load_json(paths["phase3"]) if paths["phase3"].exists() else {}
    phase4 = load_json(paths["phase4"]) if paths["phase4"].exists() else {}

    max_rebuild_age = int(args.max_rebuild_age_seconds)
    phase4_time = parse_z(str(phase4.get("generated_at_utc") or ""))
    phase2_time = parse_z(str(phase2.get("generated_at_utc") or phase2.get("decision_time_utc") or ""))
    phase2b_time = parse_z(str(phase2b.get("generated_at_utc") or phase2b.get("decision_time_utc") or ""))
    p2_provider_time = parse_z(str(phase2.get("decision_time_utc") or ""))
    p2b_provider_time = parse_z(str(phase2b.get("selected_provider_timestamp_utc") or ""))
    phase2_freshness = int(phase2.get("freshness_seconds") or 0)
    phase2b_freshness = int(phase2b.get("freshness_seconds") or phase2.get("freshness_seconds") or 0)

    owner_decision_record = {
        "contract_version": "hv_balanced_dth60_coinglass_p7_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": "authorize_p7_guarded_live_shadow_draft_only",
        "live_order_submission_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "live_config_mutation_approved": False,
        "repo_stage_change_approved": False,
    }

    draft_contract = {
        "contract_version": "hv_balanced_dth60_coinglass_guarded_live_shadow_integration_draft.v1",
        "status": "draft_only_not_applied",
        "mode": "guarded_live_shadow_plan_only",
        "baseline_strategy": "v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget:multiphase_10_sleeve",
        "candidate_id": "hybrid_q90_or_crowded_zero__dth60_combined_shock_or_crowded",
        "candidate_trigger_contract": "dth60_combined_shock_or_crowded.v1",
        "target_contribution_boundary": TARGET_CONTRIBUTION,
        "live_config_path": str(paths["live_config"]),
        "draft_runtime_delta": [
            "load fresh PIT-safe CoinGlass crowded sidecar proof",
            "load fresh PIT-safe Binance shock branch proof",
            "build dth60 shock-or-crowded trigger",
            f"apply overlay only to {TARGET_CONTRIBUTION}",
            "emit baseline and candidate target plans side by side",
            "write plan-only evidence bundle",
        ],
        "runtime_guards": {
            "plan_only": True,
            "exchange_order_submission": "disabled",
            "mainnet_order_submission_authorized": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "live_config_changed": False,
            "service_restart_requested": False,
        },
        "forbidden_without_later_separate_approval": [
            "live order submission",
            "operator-state mutation",
            "timer enablement or disablement",
            "service restart",
            "live config replacement",
            "repo stage/profile change",
        ],
        "rollback": [
            "do not apply draft",
            "keep current hv_balanced baseline target plan",
            "retain draft bundle for audit",
        ],
    }

    phase3_target_boundary_ok = (
        phase3.get("changed_contribution_columns") == [TARGET_CONTRIBUTION]
        and not phase3.get("changed_non_target_contribution_columns")
        and float(phase3.get("non_target_contribution_max_abs_diff_enabled_vs_disabled") or 0.0) == 0.0
    )
    p2_provider_age = age_seconds(phase4_time, p2_provider_time)
    p2b_provider_age = age_seconds(phase4_time, p2b_provider_time)
    gates = {
        "owner_review_pack_ready": owner_review_pack.get("status") == "ready",
        "owner_review_pack_eligible": owner_review_pack.get("eligible_for_owner_promotion_review") is True,
        "owner_approved_p7_guarded_shadow_only": str(args.owner_decision) == APPROVE_P7_DECISION,
        "fresh_phase2_ready": phase2.get("status") == "ready",
        "fresh_phase2b_ready": phase2b.get("status") == "ready",
        "fresh_phase2_rebuilt_immediately_before_phase4": within_age(phase4_time, phase2_time, max_rebuild_age),
        "fresh_phase2b_rebuilt_immediately_before_phase4": within_age(phase4_time, phase2b_time, max_rebuild_age),
        "fresh_phase2_no_future_stale_zero_fill": all(
            phase2.get(key) is True for key in (
                "no_future_fill_proven",
                "no_stale_fill_proven",
                "no_zero_fill_proven",
            )
        ),
        "fresh_phase2b_no_future_stale_zero_fill": all(
            phase2b.get(key) is True for key in (
                "no_future_fill_proven",
                "no_stale_fill_proven",
                "no_zero_fill_proven",
            )
        ),
        "fresh_phase2_provider_within_freshness_gate": (
            p2_provider_age is not None and phase2_freshness > 0 and 0 <= p2_provider_age <= phase2_freshness
        ),
        "fresh_phase2b_provider_within_freshness_gate": (
            p2b_provider_age is not None and phase2b_freshness > 0 and 0 <= p2b_provider_age <= phase2b_freshness
        ),
        "phase3_ready": phase3.get("status") == "ready",
        "phase3_combined_trigger_proven": phase3.get("combined_candidate_trigger_proven") is True,
        "phase3_disabled_wrapper_matches_core": phase3.get("disabled_wrapper_score_matches_core") is True,
        "phase3_overlay_only_target_contribution": phase3_target_boundary_ok,
        "phase3_no_live_mutation": no_live_mutation(phase3),
        "phase4_ready": phase4.get("status") == "ready",
        "phase4_same_timestamp_context": phase4.get("same_timestamp_context_proven") is True,
        "phase4_same_risk_inputs": phase4.get("same_risk_inputs_proven") is True,
        "phase4_same_symbol_set": phase4.get("same_symbol_set_proven") is True,
        "phase4_same_portfolio_engine": phase4.get("same_portfolio_engine_proven") is True,
        "phase4_plan_only_risk_gates_passed": (
            phase4.get("baseline_plan_only_risk_gate_status") == "passed"
            and phase4.get("candidate_plan_only_risk_gate_status") == "passed"
        ),
        "phase4_deterministic_target_difference": phase4.get("deterministic_target_difference_proven") is True,
        "phase4_zero_orders_fills": is_zero_order(phase4),
        "phase4_no_live_mutation": no_live_mutation(phase4),
        "live_config_exists_for_draft_reference": paths["live_config"].exists(),
        "draft_requests_no_execution_authority": draft_contract["runtime_guards"]["mainnet_order_submission_authorized"] is False,
    }
    ready = all(bool(value) for value in gates.values())
    status = "ready" if ready else "blocked"
    output_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "owner_decision": owner_decision_record,
        "draft_contract": draft_contract,
        "source_evidence": {
            "owner_review_pack": evidence_file(paths["owner_review_pack"]),
            "phase2_summary": evidence_file(paths["phase2"]),
            "phase2b_summary": evidence_file(paths["phase2b"]),
            "phase3_summary": evidence_file(paths["phase3"]),
            "phase4_summary": evidence_file(paths["phase4"]),
            "live_config_reference": evidence_file(paths["live_config"]),
        },
        "freshness": {
            "max_rebuild_age_seconds": max_rebuild_age,
            "phase2_generated_at_utc": phase2.get("generated_at_utc"),
            "phase2b_generated_at_utc": phase2b.get("generated_at_utc"),
            "phase4_generated_at_utc": phase4.get("generated_at_utc"),
            "phase2_age_seconds_at_phase4": age_seconds(phase4_time, phase2_time),
            "phase2b_age_seconds_at_phase4": age_seconds(phase4_time, phase2b_time),
            "phase2_provider_age_seconds_at_phase4": p2_provider_age,
            "phase2b_provider_age_seconds_at_phase4": p2b_provider_age,
            "phase2_freshness_seconds": phase2_freshness,
            "phase2b_freshness_seconds": phase2b_freshness,
        },
        "paired_plan": {
            "phase4_run_id": phase4.get("run_id"),
            "same_timestamp_context_proven": phase4.get("same_timestamp_context_proven"),
            "same_risk_inputs_proven": phase4.get("same_risk_inputs_proven"),
            "target_weight_delta_symbol_count": phase4.get("target_weight_delta_symbol_count"),
            "absolute_target_weight_delta_sum": phase4.get("absolute_target_weight_delta_sum"),
            "orders_submitted": phase4.get("orders_submitted"),
            "fill_count": phase4.get("fill_count"),
            "mainnet_order_submission_authorized": phase4.get("mainnet_order_submission_authorized"),
        },
        "gates": gates,
        "eligible_for_p7_guarded_live_shadow_draft": ready,
        "eligible_for_live_order_submission": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "blockers": [] if ready else [key for key, value in gates.items() if not value],
    }
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(output_root / "guarded_live_shadow_integration_draft.json", draft_contract)
    write_json(output_root / "summary.json", summary)
    (output_root / "guarded_live_shadow_integration_draft.md").write_text(render_markdown(summary), encoding="utf-8")
    summary["output_files"] = {
        "summary": str(output_root / "summary.json"),
        "owner_decision_record": str(output_root / "owner_decision_record.json"),
        "guarded_live_shadow_integration_draft": str(output_root / "guarded_live_shadow_integration_draft.json"),
        "guarded_live_shadow_integration_draft_md": str(output_root / "guarded_live_shadow_integration_draft.md"),
    }
    write_json(output_root / "summary.json", summary)
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P7 Guarded Live Shadow Draft",
        "",
        f"Status: `{summary['status']}`",
        f"Generated: `{summary['generated_at_utc']}`",
        "",
        "## Boundary",
        "",
        "- Draft only, not applied.",
        "- Order submission remains disabled.",
        "- No operator state, timer, service, live config, or repo stage change is approved.",
        "",
        "## Owner Decision",
        "",
        f"- owner: `{summary['owner_decision']['owner']}`",
        f"- decision: `{summary['owner_decision']['decision']}`",
        f"- decision_effect: `{summary['owner_decision']['decision_effect']}`",
        "",
        "## Gates",
        "",
    ]
    for key, value in summary["gates"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend([
        "",
        "## Paired Plan",
        "",
        f"- phase4_run_id: `{summary['paired_plan']['phase4_run_id']}`",
        f"- same_timestamp_context_proven: `{summary['paired_plan']['same_timestamp_context_proven']}`",
        f"- same_risk_inputs_proven: `{summary['paired_plan']['same_risk_inputs_proven']}`",
        f"- target_weight_delta_symbol_count: `{summary['paired_plan']['target_weight_delta_symbol_count']}`",
        f"- orders_submitted: `{summary['paired_plan']['orders_submitted']}`",
        f"- fill_count: `{summary['paired_plan']['fill_count']}`",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase7_draft(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
