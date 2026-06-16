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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase6_owner_review_pack.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase6_owner_promotion_review"
)
STEP1_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "step1_coinglass_api_health"
)
PHASE2_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase2_pit_sidecar_join"
)
PHASE2B_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase2b_shock_branch_builder"
)
PHASE3_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase3_candidate_parity"
)
PHASE4_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase4_paired_target_plan_shadow"
)
PHASE5A_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase5a_remote_no_order_observation"
)
PHASE5B_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase5b_remote_no_order_observation"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
TARGET_CONTRIBUTION = "contribution_distance_to_high_60"
PENDING_DECISION_STATUS = "pending_owner_review"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the owner promotion review pack for the hv_balanced "
            "DTH60/CoinGlass shock-or-crowded candidate. Writes review evidence only."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--step1-summary", default="")
    parser.add_argument("--phase2-summary", default="")
    parser.add_argument("--phase2b-summary", default="")
    parser.add_argument("--phase3-summary", default="")
    parser.add_argument("--phase4-summary", default="")
    parser.add_argument("--p5a-phase3-summary", default="")
    parser.add_argument("--p5a-phase4-summary", default="")
    parser.add_argument("--p5b-summary", default="")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def latest_match(parent: str, pattern: str) -> Path:
    root = resolve_path(parent)
    matches = sorted(root.glob(pattern))
    if not matches:
        return Path("")
    return matches[-1]


def evidence_file(path: Path) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def no_live_mutation(summary: dict[str, Any]) -> bool:
    return all(summary.get(key) is False for key in (
        "applied_to_live",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
    ))


def is_zero_order(summary: dict[str, Any]) -> bool:
    return (
        int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and summary.get("mainnet_order_submission_authorized") is False
        and summary.get("exchange_order_submission") == "disabled"
    )


def build_row(
    *,
    phase: str,
    title: str,
    summary_path: Path,
    checks: dict[str, bool],
    highlights: dict[str, Any],
) -> dict[str, Any]:
    missing = not summary_path or not resolve_path(summary_path).exists()
    ready = bool(checks) and all(bool(value) for value in checks.values()) and not missing
    return {
        "phase": phase,
        "title": title,
        "status": "ready" if ready else "blocked",
        "summary": evidence_file(summary_path),
        "checks": checks,
        "highlights": highlights,
        "blockers": [] if ready else [key for key, value in checks.items() if not value] + (
            ["summary_missing"] if missing else []
        ),
    }


def load_optional(path: Path) -> dict[str, Any]:
    return load_json(resolve_path(path)) if path and resolve_path(path).exists() else {}


def build_owner_review_pack(
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
        "step1": resolve_path(args.step1_summary) if args.step1_summary else latest_match(STEP1_PARENT, "*/summary.json"),
        "phase2": resolve_path(args.phase2_summary) if args.phase2_summary else latest_match(PHASE2_PARENT, "*/summary.json"),
        "phase2b": resolve_path(args.phase2b_summary) if args.phase2b_summary else latest_match(PHASE2B_PARENT, "*/summary.json"),
        "phase3": resolve_path(args.phase3_summary) if args.phase3_summary else latest_match(PHASE3_PARENT, "*/summary.json"),
        "phase4": resolve_path(args.phase4_summary) if args.phase4_summary else latest_match(PHASE4_PARENT, "*/summary.json"),
        "p5a_phase3": (
            resolve_path(args.p5a_phase3_summary)
            if args.p5a_phase3_summary
            else latest_match(PHASE5A_PARENT, "*/remote_readback/phase3_remote_candidate_parity/summary.json")
        ),
        "p5a_phase4": (
            resolve_path(args.p5a_phase4_summary)
            if args.p5a_phase4_summary
            else latest_match(PHASE5A_PARENT, "*/remote_readback/phase4_remote_paired_target_plan_shadow/summary.json")
        ),
        "p5b": resolve_path(args.p5b_summary) if args.p5b_summary else latest_match(PHASE5B_PARENT, "*/p5b_summary.json"),
    }

    project_profile = load_optional(paths["project_profile"])
    step1 = load_optional(paths["step1"])
    phase2 = load_optional(paths["phase2"])
    phase2b = load_optional(paths["phase2b"])
    phase3 = load_optional(paths["phase3"])
    phase4 = load_optional(paths["phase4"])
    p5a_phase3 = load_optional(paths["p5a_phase3"])
    p5a_phase4 = load_optional(paths["p5a_phase4"])
    p5b = load_optional(paths["p5b"])

    evidence_rows = [
        build_row(
            phase="P1",
            title="CoinGlass API health and coverage",
            summary_path=paths["step1"],
            checks={
                "status_ready": step1.get("status") == "ready",
                "api_key_present": step1.get("api_key_present") is True,
                "all_requested_symbols_ready": step1.get("ready_symbol_count") == step1.get("requested_symbol_count"),
                "exchange_order_submission_disabled": step1.get("exchange_order_submission") == "disabled",
                "no_live_mutation": no_live_mutation(step1),
            },
            highlights={
                "generated_at_utc": step1.get("generated_at_utc"),
                "ready_symbol_count": step1.get("ready_symbol_count"),
                "requested_symbol_count": step1.get("requested_symbol_count"),
                "required_endpoint_id": step1.get("required_endpoint_id"),
            },
        ),
        build_row(
            phase="P2",
            title="PIT-safe CoinGlass crowded sidecar join",
            summary_path=paths["phase2"],
            checks={
                "status_ready": phase2.get("status") == "ready",
                "all_symbols_joined": phase2.get("joined_symbol_count") == phase2.get("requested_symbol_count"),
                "no_future_fill": phase2.get("no_future_fill_proven") is True,
                "no_stale_fill": phase2.get("no_stale_fill_proven") is True,
                "no_zero_fill": phase2.get("no_zero_fill_proven") is True,
                "no_live_mutation": no_live_mutation(phase2),
            },
            highlights={
                "decision_time_utc": phase2.get("decision_time_utc"),
                "joined_symbol_count": phase2.get("joined_symbol_count"),
                "freshness_seconds": phase2.get("freshness_seconds"),
            },
        ),
        build_row(
            phase="P2B",
            title="PIT-safe Binance shock branch builder",
            summary_path=paths["phase2b"],
            checks={
                "status_ready": phase2b.get("status") == "ready",
                "all_symbols_joined": phase2b.get("joined_symbol_count") == phase2b.get("requested_symbol_count"),
                "no_future_fill": phase2b.get("no_future_fill_proven") is True,
                "no_stale_fill": phase2b.get("no_stale_fill_proven") is True,
                "no_zero_fill": phase2b.get("no_zero_fill_proven") is True,
                "train_excludes_decision_row": phase2b.get("train_includes_decision_row") is False,
                "no_live_mutation": no_live_mutation(phase2b),
            },
            highlights={
                "decision_time_utc": phase2b.get("decision_time_utc"),
                "selected_provider_timestamp_utc": phase2b.get("selected_provider_timestamp_utc"),
                "shock_branch_triggered": phase2b.get("shock_branch_triggered"),
            },
        ),
        build_row(
            phase="P3",
            title="Local candidate parity wrapper",
            summary_path=paths["phase3"],
            checks={
                "status_ready": phase3.get("status") == "ready",
                "combined_candidate_trigger_proven": phase3.get("combined_candidate_trigger_proven") is True,
                "disabled_wrapper_score_matches_core": phase3.get("disabled_wrapper_score_matches_core") is True,
                "only_target_contribution_changed": phase3.get("changed_contribution_columns") == [TARGET_CONTRIBUTION],
                "non_target_contribution_diff_zero": float(
                    phase3.get("non_target_contribution_max_abs_diff_enabled_vs_disabled") or 0.0
                )
                == 0.0,
                "no_live_mutation": no_live_mutation(phase3),
            },
            highlights={
                "run_id": phase3.get("run_id"),
                "generated_at_utc": phase3.get("generated_at_utc"),
                "overlay_triggered_row_count": phase3.get("overlay_triggered_row_count"),
            },
        ),
        build_row(
            phase="P4",
            title="Local paired target-plan shadow",
            summary_path=paths["phase4"],
            checks={
                "status_ready": phase4.get("status") == "ready",
                "same_timestamp_context": phase4.get("same_timestamp_context_proven") is True,
                "same_risk_inputs": phase4.get("same_risk_inputs_proven") is True,
                "deterministic_target_difference": phase4.get("deterministic_target_difference_proven") is True,
                "zero_orders_fills": is_zero_order(phase4),
                "no_live_mutation": no_live_mutation(phase4),
            },
            highlights={
                "run_id": phase4.get("run_id"),
                "generated_at_utc": phase4.get("generated_at_utc"),
                "target_weight_delta_symbol_count": phase4.get("target_weight_delta_symbol_count"),
                "absolute_target_weight_delta_sum": phase4.get("absolute_target_weight_delta_sum"),
            },
        ),
        build_row(
            phase="P5A",
            title="Remote no-order candidate observation",
            summary_path=paths["p5a_phase4"],
            checks={
                "phase3_ready": p5a_phase3.get("status") == "ready",
                "phase4_ready": p5a_phase4.get("status") == "ready",
                "same_risk_inputs": p5a_phase4.get("same_risk_inputs_proven") is True,
                "combined_candidate_trigger_proven": p5a_phase4.get("combined_candidate_trigger_proven") is True,
                "zero_orders_fills": is_zero_order(p5a_phase4),
                "no_live_mutation": no_live_mutation(p5a_phase3) and no_live_mutation(p5a_phase4),
            },
            highlights={
                "phase3_run_id": p5a_phase3.get("run_id"),
                "phase4_run_id": p5a_phase4.get("run_id"),
                "phase4_generated_at_utc": p5a_phase4.get("generated_at_utc"),
                "target_weight_delta_symbol_count": p5a_phase4.get("target_weight_delta_symbol_count"),
            },
        ),
        build_row(
            phase="P5B",
            title="Consecutive remote no-order observation",
            summary_path=paths["p5b"],
            checks={
                "status_ready": p5b.get("status") == "ready",
                "three_cycles_ready": p5b.get("ready_cycle_count") == 3,
                "three_cycles_fresh_proof": p5b.get("fresh_proof_cycle_count") == 3,
                "three_cycles_same_risk": p5b.get("same_risk_paired_plan_cycle_count") == 3,
                "three_cycles_zero_orders_fills": p5b.get("zero_orders_fills_cycle_count") == 3,
                "three_cycles_target_boundary": p5b.get("target_contribution_boundary_cycle_count") == 3,
                "db_zero_execution_plans": (
                    ((p5b.get("control_plane_snapshot") or {}).get("db_window_counts") or {})
                    .get("counts", {})
                    .get("execution_plans")
                    == 0
                ),
                "db_zero_orders_fills": (
                    ((p5b.get("control_plane_snapshot") or {}).get("db_window_counts") or {})
                    .get("counts", {})
                    .get("paper_orders")
                    == 0
                    and ((p5b.get("control_plane_snapshot") or {}).get("db_window_counts") or {})
                    .get("counts", {})
                    .get("paper_fills")
                    == 0
                ),
            },
            highlights={
                "remote_clean_root": p5b.get("remote_clean_root"),
                "generated_at_utc": p5b.get("generated_at_utc"),
                "cycle_count_observed": p5b.get("cycle_count_observed"),
                "zero_orders_fills_cycle_count": p5b.get("zero_orders_fills_cycle_count"),
            },
        ),
    ]

    stage_is_stage1 = project_profile.get("current_stage") == "stage_1_research_readiness_only"
    all_evidence_ready = all(row["status"] == "ready" for row in evidence_rows)
    p5b_cycles = p5b.get("cycles") or []
    no_cycle_live_mutation = bool(p5b_cycles) and all(
        cycle.get("no_live_mutation_flags_proven") is True for cycle in p5b_cycles
    )
    proof_gates = {
        "all_phase_evidence_ready": all_evidence_ready,
        "project_stage_boundary_preserved": stage_is_stage1,
        "p5b_has_three_consecutive_ready_cycles": p5b.get("ready_cycle_count") == 3,
        "p5b_fresh_proof_each_cycle": p5b.get("fresh_proof_cycle_count") == 3,
        "p5b_same_risk_paired_plan_each_cycle": p5b.get("same_risk_paired_plan_cycle_count") == 3,
        "p5b_zero_orders_fills_each_cycle": p5b.get("zero_orders_fills_cycle_count") == 3,
        "p5b_overlay_only_changes_distance_to_high_60": p5b.get("target_contribution_boundary_cycle_count") == 3,
        "p5b_no_live_mutation_flags_each_cycle": no_cycle_live_mutation,
        "owner_decision_required_before_live_shadow_integration": True,
        "no_execution_authority_change_requested": True,
    }
    eligible_for_owner_review = all(bool(value) for value in proof_gates.values())
    status = "ready" if eligible_for_owner_review else "blocked"

    pack: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "candidate_id": "hybrid_q90_or_crowded_zero__dth60_combined_shock_or_crowded",
        "baseline_strategy": "v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget:multiphase_10_sleeve",
        "candidate_trigger_contract": "dth60_combined_shock_or_crowded.v1",
        "candidate_trigger_formula": (
            "dth60_shock_branch_trigger OR "
            "(distance_to_high_60_rank_pct >= 0.75 AND "
            "coinglass_top_trader_long_pct_smooth_5_rank_pct >= 0.80)"
        ),
        "target_contribution_boundary": TARGET_CONTRIBUTION,
        "project_stage": {
            "current_stage": project_profile.get("current_stage"),
            "target_stage": project_profile.get("target_stage"),
            "stage_boundary_preserved": stage_is_stage1,
        },
        "evidence_matrix": evidence_rows,
        "proof_gates": proof_gates,
        "eligible_for_owner_promotion_review": eligible_for_owner_review,
        "eligible_for_live_order_submission": False,
        "live_integration_delta_draft": {
            "status": "draft_only_not_applied",
            "allowed_scope_if_owner_approves": "guarded_live_shadow_plan_only",
            "forbidden_without_separate_approval": [
                "live order submission",
                "operator-state mutation",
                "timer enablement or disablement",
                "service restart",
                "repo stage/profile change",
            ],
            "candidate_runtime_delta": [
                "load PIT-safe CoinGlass crowded sidecar proof",
                "load PIT-safe Binance shock branch proof",
                "build combined shock-or-crowded trigger",
                "apply overlay only to distance_to_high_60 contribution",
                "emit baseline and candidate target plans side by side",
                "keep exchange order submission disabled",
            ],
            "rollback": [
                "disable candidate overlay wrapper",
                "fall back to current hv_balanced baseline target plan",
                "retain last paired shadow bundle for audit",
            ],
        },
        "owner_decision_record": {
            "owner": "rulebook_owner",
            "decision_status": PENDING_DECISION_STATUS,
            "allowed_decisions": [
                "approve_guarded_live_shadow_plan_only",
                "defer_for_more_no_order_observation",
                "reject_candidate_promotion",
            ],
            "current_decision_effect": "none",
            "requires_signed_owner_record_before_p7": True,
        },
        "recommended_next_phase_if_owner_approves": {
            "phase": "P7",
            "name": "guarded live shadow integration draft",
            "order_authority": "unchanged_disabled",
            "required_first_step": "fresh provider proof rebuild immediately before integration draft",
        },
        "blockers": [] if status == "ready" else [
            key for key, value in proof_gates.items() if not value
        ],
    }
    write_json(output_root / "owner_review_pack.json", pack)
    markdown = render_markdown(pack)
    (output_root / "owner_review_pack.md").write_text(markdown, encoding="utf-8")
    pack["output_files"] = {
        "owner_review_pack_json": str(output_root / "owner_review_pack.json"),
        "owner_review_pack_md": str(output_root / "owner_review_pack.md"),
    }
    write_json(output_root / "summary.json", pack)
    return pack, 0 if status == "ready" else 2


def render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass Owner Promotion Review Pack",
        "",
        f"Status: `{pack['status']}`",
        f"Generated: `{pack['generated_at_utc']}`",
        "",
        "## Decision Boundary",
        "",
        "- This pack opens owner review only.",
        "- It does not approve live order submission.",
        "- It does not change operator state, timers, services, config, or repo stage.",
        "",
        "## Evidence Matrix",
        "",
        "| Phase | Status | Summary | Key Result |",
        "| --- | --- | --- | --- |",
    ]
    for row in pack["evidence_matrix"]:
        summary_path = row["summary"]["path"] or "missing"
        highlights = ", ".join(
            f"{key}={value}" for key, value in row["highlights"].items() if value not in (None, "")
        )
        lines.append(f"| {row['phase']} {row['title']} | {row['status']} | `{summary_path}` | {highlights} |")
    lines.extend([
        "",
        "## Gates",
        "",
    ])
    for gate, value in pack["proof_gates"].items():
        lines.append(f"- {gate}: `{str(value).lower()}`")
    lines.extend([
        "",
        "## Owner Decision Record",
        "",
        f"- owner: `{pack['owner_decision_record']['owner']}`",
        f"- decision_status: `{pack['owner_decision_record']['decision_status']}`",
        "- current_decision_effect: `none`",
        "",
        "## Next Phase If Approved",
        "",
        "- P7 guarded live shadow integration draft.",
        "- Order authority remains disabled.",
        "- Fresh provider proof must be rebuilt immediately before any integration draft.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_owner_review_pack(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['owner_review_pack_json']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
