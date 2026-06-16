from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "parallel_1h_stage0_decision_ledger.v1"
REPORT_DIR = Path("artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0")
LEDGER_NAME = "parallel_1h_stage0_decision_ledger.json"
LEDGER_MD_NAME = "parallel_1h_stage0_decision_ledger.md"


ROW_POLICY: dict[str, dict[str, Any]] = {
    "low_float_squeeze_trap_stage0_1h": {
        "stage": "first_batch_stage0",
        "current_decision": "fail",
        "decisive_blocker": "shuffle, symbol holdout, and delay robustness failed",
        "allowed_next_action": "closed unless a new exogenous short-squeeze completion feature is introduced",
        "mechanism_status": "rejected_trap_veto_candidate",
    },
    "post_squeeze_exit_short_stage0_1h": {
        "stage": "first_batch_stage0",
        "current_decision": "fail",
        "decisive_blocker": "shuffle, symbol holdout, liquidity-bucket consistency, and delay robustness failed",
        "allowed_next_action": "closed; use only as source of candidate diagnostics",
        "mechanism_status": "rejected_delayed_short_entry_candidate",
    },
    "fake_liquidity_capacity_haircut_stage0_1h": {
        "stage": "first_batch_stage0",
        "current_decision": "quarantined_state_evidence",
        "decisive_blocker": "state-level Stage 0 passed, but parent interaction and repair tests later failed",
        "allowed_next_action": "data-unlock retry only after pre-registered venue concentration or native PIT exchange-flow sidecar",
        "mechanism_status": "useful_mechanism_hypothesis_not_admitted",
    },
    "fake_liquidity_atomic_decomposition_1h": {
        "stage": "fake_liquidity_repair",
        "current_decision": "quarantined_state_evidence",
        "decisive_blocker": "only aggregate haircut survived; standalone components did not admit",
        "allowed_next_action": "supporting evidence only; no standalone atom promotion",
        "mechanism_status": "aggregate_only_supporting_evidence",
    },
    "fake_liquidity_aggregate_parent_interaction_1h": {
        "stage": "fake_liquidity_parent_interaction",
        "current_decision": "fail",
        "decisive_blocker": "hard-veto, quarter-size, and soft-multiplier variants failed strict symbol holdout",
        "allowed_next_action": "closed for admission; explanatory attribution only",
        "mechanism_status": "rejected_parent_interaction",
    },
    "fake_liquidity_capacity_haircut_atoms_stage0_1h": {
        "stage": "fake_liquidity_repair",
        "current_decision": "fail",
        "decisive_blocker": "requested standalone atoms failed holdout, shuffle, direction, or bucket gates",
        "allowed_next_action": "closed; volume_oi_brushing can be retried only with venue/provider sidecar",
        "mechanism_status": "rejected_standalone_atoms",
    },
    "fake_liquidity_parent_symbol_provider_sensitivity_1h": {
        "stage": "fake_liquidity_sensitivity",
        "current_decision": "fail_explanatory_audit",
        "decisive_blocker": "provider watchlist, missing fields, and live-tail exclusions did not repair symbol holdout",
        "allowed_next_action": "explanatory only; no post-hoc symbol exclusion",
        "mechanism_status": "root_cause_audit_not_admission",
    },
    "fake_liquidity_age_gated_parent_interaction_1h": {
        "stage": "fake_liquidity_repair",
        "current_decision": "fail",
        "decisive_blocker": "age gate fixed symbol holdout but failed same-timestamp shuffle and +24h delay",
        "allowed_next_action": "closed; no age-only rescue",
        "mechanism_status": "rejected_age_gated_repair",
    },
    "fake_liquidity_age_30_180d_sidecar_1h": {
        "stage": "fake_liquidity_repair",
        "current_decision": "fail",
        "decisive_blocker": "pre-registered age sidecar failed primary variants and remains data-mining quarantined",
        "allowed_next_action": "closed; needs fresh OOS or trusted exogenous sidecar before retry",
        "mechanism_status": "rejected_pre_registered_age_sidecar",
    },
    "short_liquidation_completion_cooldown_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": "symbol holdout consistency was 0.5867, below the 0.60 hard gate",
        "allowed_next_action": "closed for admission; mechanism evidence only",
        "mechanism_status": "useful_liquidation_pressure_hypothesis_not_admitted",
    },
    "funding_settlement_squeeze_window_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": "same-timestamp feature/label shuffles failed and +24h delay flipped the delta",
        "allowed_next_action": "closed for admission; timing/carry-risk diagnostic only",
        "mechanism_status": "timing_carry_risk_diagnostic_not_admitted",
    },
    "top_trader_fade_retail_chase_veto_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": "same-timestamp feature/label shuffles failed",
        "allowed_next_action": "closed for admission; account-ratio timing diagnostic only",
        "mechanism_status": "account_ratio_timing_diagnostic_not_admitted",
    },
    "post_pump_bid_replenishment_failure_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": (
            "primary h24 short-return delta was negative, adverse-squeeze risk was higher, and shuffle, "
            "symbol holdout, liquidity-bucket consistency, and delay robustness all failed"
        ),
        "allowed_next_action": (
            "closed for delayed-short admission; retain only as evidence that naive bid-replenishment failure "
            "may still be a squeeze-continuation risk state"
        ),
        "mechanism_status": "rejected_delayed_short_entry_candidate",
    },
    "funding_normalization_after_deep_negative_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": (
            "primary h24 short-return delta was positive and symbol/bucket checks passed, but same-timestamp "
            "feature/label shuffles reproduced stronger deltas and +24h delay flipped the edge"
        ),
        "allowed_next_action": (
            "closed for admission; retain as funding-timing diagnostic only, with any retry requiring a fresh "
            "pre-registered causal confirmation rather than threshold rescue"
        ),
        "mechanism_status": "funding_timing_diagnostic_not_admitted",
    },
    "liquidation_cluster_aftershock_veto_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": (
            "primary h24 veto delta was strongly negative and symbol/bucket/delay checks passed, but same-timestamp "
            "feature/label shuffles reproduced the effect"
        ),
        "allowed_next_action": (
            "closed for admission; retain as liquidation-risk diagnostic only, with any retry requiring a narrower "
            "pre-registered causal state that beats same-timestamp shuffles"
        ),
        "mechanism_status": "liquidation_aftershock_risk_diagnostic_not_admitted",
    },
    "low_liquidity_hour_kill_switch_stage0_1h": {
        "stage": "fresh_mechanical_flow_stage0",
        "current_decision": "fail",
        "decisive_blocker": (
            "low-liquidity-hour rows had lower capacity but better h24 short returns, lower adverse-squeeze rate, "
            "lower slippage proxy, and failed shuffle, symbol holdout, bucket, and delay gates"
        ),
        "allowed_next_action": (
            "closed for kill-switch admission; retain only as capacity diagnostic evidence and do not bridge to h10d "
            "or live selectors"
        ),
        "mechanism_status": "rejected_execution_kill_switch_candidate",
    },
    "trust_masked_venue_concentration_fake_liquidity_stage0_1h": {
        "stage": "stage1a_data_unlock_retry",
        "current_decision": "fail",
        "decisive_blocker": (
            "after 60-subject coverage repair the minimum sample cleared with 683 candidates and 32 event rows, "
            "but shuffle, symbol holdout, liquidity-bucket consistency, and +6h/+24h delay robustness failed"
        ),
        "allowed_next_action": (
            "closed for admission; further work must be data-foundation expansion, wider native concordance, "
            "or a fresh pre-registered state, with no h10d bridge or live use"
        ),
        "mechanism_status": "rejected_after_coverage_repair_capacity_diagnostic_only",
    },
    "native_exchange_flow_1h_availability_audit": {
        "stage": "stage1a_data_sidecar_unlock",
        "current_decision": "blocked_by_data",
        "decisive_blocker": (
            "local exchange-flow sources are daily or macro-only, available 1h panels have no inflow/outflow/netflow "
            "fields, no symbol-level altcoin exchange-flow coverage exists for the post-pump universe, and the "
            "CryptoQuant hourly provider probe returned HTTP 403 for the sampled scopes"
        ),
        "allowed_next_action": (
            "resolve provider entitlement/capability or identify an alternate PIT 1h exchange-flow source; "
            "cex_inflow_bait_vs_exit Stage 0 remains blocked, with no h10d bridge or live use"
        ),
        "mechanism_status": "blocked_no_native_pit_1h_exchange_flow_sidecar",
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the parallel 1h Stage 0 decision ledger from local reports."
    )
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--as-of", default="2026-05-07")
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path(payload: dict[str, Any], path: list[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _gate_status(report: dict[str, Any]) -> dict[str, Any]:
    gates: dict[str, Any] = {}
    for key in ("shuffle_tests", "symbol_holdout", "liquidity_bucket_consistency", "delay_robustness"):
        value = report.get(key)
        gates[key] = value.get("passed") if isinstance(value, dict) else None
    decision = report.get("pass_fail_decision")
    gates["local_label"] = decision.get("label") if isinstance(decision, dict) else None
    gates["local_failed_checks"] = decision.get("failed_checks") if isinstance(decision, dict) else None
    gates["local_blockers"] = decision.get("blockers") if isinstance(decision, dict) else None
    return gates


def _primary_effect(report: dict[str, Any]) -> dict[str, Any]:
    primary = report.get("primary_effect_h24")
    if isinstance(primary, dict):
        return {
            key: primary.get(key)
            for key in (
                "status",
                "short_return_delta",
                "adverse_squeeze_gt_5pct_delta",
                "trap_count",
                "exit_count",
                "haircut_count",
                "cooldown_count",
                "kill_switch_count",
                "window_count",
                "entry_count",
                "control_count",
            )
            if key in primary
        }
    effect = _get_path(report, ["selected_short_changed_rows_equivalent", "effect"])
    if isinstance(effect, dict):
        return {
            key: effect.get(key)
            for key in (
                "status",
                "short_return_delta",
                "adverse_squeeze_gt_5pct_delta",
                "trap_count",
                "exit_count",
                "haircut_count",
                "cooldown_count",
                "kill_switch_count",
                "window_count",
                "entry_count",
                "control_count",
            )
            if key in effect
        }
    ranked_variants = report.get("ranked_variants")
    if isinstance(ranked_variants, list) and ranked_variants:
        first = ranked_variants[0]
        return {
            "best_ranked_variant": first.get("variant"),
            "variant_label": first.get("label"),
            "h24_gross_pnl_delta": first.get("h24_gross_pnl_delta"),
            "h24_adverse_tail_delta": first.get("h24_adverse_tail_delta"),
        }
    ranked_components = report.get("ranked_components")
    if isinstance(ranked_components, list) and ranked_components:
        first = ranked_components[0]
        return {
            "best_ranked_component": first.get("component"),
            "component_label": first.get("label"),
            "h24_short_return_delta": first.get("h24_short_return_delta"),
        }
    return {}


def _event_counts(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("pass_fail_decision")
    payload: dict[str, Any] = {}
    if isinstance(decision, dict):
        for key, value in decision.items():
            if key.endswith("_count") or key.endswith("_row_count"):
                payload[key] = value
    primary = report.get("primary_effect_h24")
    if isinstance(primary, dict):
        for key in ("kill_switch_count", "cooldown_count", "control_count"):
            if key in primary:
                payload[key] = primary.get(key)
    changed = report.get("selected_short_changed_rows_equivalent")
    if isinstance(changed, dict) and "row_count" in changed:
        payload["selected_short_changed_row_count"] = changed.get("row_count")
    for key in ("candidate_count", "aggregate_haircut_row_count"):
        if key in report:
            payload[key] = report.get(key)
    return payload


def _coverage(report: dict[str, Any]) -> dict[str, Any]:
    coverage = report.get("data_sources_and_coverage")
    if not isinstance(coverage, dict):
        return {}
    out = {
        "status": coverage.get("status"),
        "loaded_symbol_count": coverage.get("loaded_symbol_count"),
        "symbols_loaded": coverage.get("symbols_loaded"),
        "symbols_discovered": coverage.get("symbols_discovered"),
        "subject_count": coverage.get("subject_count"),
        "row_count": coverage.get("row_count"),
        "rows_loaded": coverage.get("rows_loaded"),
        "post_pump_short_candidate_rows": coverage.get("post_pump_short_candidate_rows"),
        "start_utc": coverage.get("start_utc"),
        "end_utc": coverage.get("end_utc"),
    }
    trust_sidecar = coverage.get("trust_masked_sidecar_coverage")
    if isinstance(trust_sidecar, dict):
        out["trust_masked_sidecar_summary"] = {
            "sidecar_subject_count": trust_sidecar.get("sidecar_subject_count"),
            "matched_row_count": trust_sidecar.get("matched_row_count"),
            "matched_row_fraction": trust_sidecar.get("matched_row_fraction"),
            "post_pump_candidate_count_before_sidecar_gate": trust_sidecar.get(
                "post_pump_candidate_count_before_sidecar_gate"
            ),
            "post_pump_candidate_count_with_sidecar_match": trust_sidecar.get(
                "post_pump_candidate_count_with_sidecar_match"
            ),
            "post_pump_candidate_count_with_multi_venue_gate": trust_sidecar.get(
                "post_pump_candidate_count_with_multi_venue_gate"
            ),
        }
    return out


def _ledger_row(report_dir: Path, research_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    report_path = report_dir / f"{research_id}.json"
    exists = report_path.exists()
    report = _load_json(report_path) if exists else {}
    local_decision = report.get("pass_fail_decision")
    local_label = local_decision.get("label") if isinstance(local_decision, dict) else None
    return {
        "research_id": research_id,
        "stage": policy["stage"],
        "report_path": str(report_path),
        "report_exists": bool(exists),
        "report_generated_at_utc": report.get("generated_at_utc"),
        "contract_version": report.get("contract_version"),
        "local_report_label": local_label,
        "current_decision": policy["current_decision"],
        "mechanism_status": policy["mechanism_status"],
        "decisive_blocker": policy["decisive_blocker"],
        "allowed_next_action": policy["allowed_next_action"],
        "gate_status": _gate_status(report),
        "event_counts": _event_counts(report),
        "primary_effect": _primary_effect(report),
        "data_sources_and_coverage": _coverage(report),
        "h10d_bridge_allowed": False,
        "live_use_allowed": False,
    }


def _summarize(rows: list[dict[str, Any]], report_dir: Path) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    for row in rows:
        key = str(row["current_decision"])
        decisions[key] = decisions.get(key, 0) + 1
    missing = [row["research_id"] for row in rows if not row["report_exists"]]
    nonclosed = [
        row["research_id"]
        for row in rows
        if row["h10d_bridge_allowed"] or row["live_use_allowed"]
    ]
    return {
        "report_dir": str(report_dir),
        "row_count": int(len(rows)),
        "missing_report_count": int(len(missing)),
        "missing_reports": missing,
        "decision_counts": decisions,
        "admitted_alpha_count": 0,
        "admitted_parent_interaction_count": 0,
        "live_candidate_count": 0,
        "h10d_bridge_allowed_count": 0,
        "live_use_allowed_count": 0,
        "nonclosed_rows": nonclosed,
        "overall_decision": "fail",
        "next_recommended_step": "Stage 1A data sidecars only where they unlock blocked high-value branches; do not rescue failed 1h states without new pre-registered information.",
    }


def _write_markdown(ledger: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Parallel 1h Stage 0 Decision Ledger",
        "",
        f"Generated at UTC: `{ledger['generated_at_utc']}`",
        f"As of: `{ledger['as_of']}`",
        "",
        "## Summary",
        "",
        f"- Overall decision: `{ledger['summary']['overall_decision']}`",
        f"- Rows: `{ledger['summary']['row_count']}`",
        f"- Admitted alpha count: `{ledger['summary']['admitted_alpha_count']}`",
        f"- Admitted parent interaction count: `{ledger['summary']['admitted_parent_interaction_count']}`",
        f"- Live candidate count: `{ledger['summary']['live_candidate_count']}`",
        "",
        "## Rows",
        "",
        "| research_id | current_decision | decisive_blocker | allowed_next_action |",
        "| --- | --- | --- | --- |",
    ]
    for row in ledger["rows"]:
        lines.append(
            "| `{research_id}` | `{current_decision}` | {decisive_blocker} | {allowed_next_action} |".format(
                research_id=row["research_id"],
                current_decision=row["current_decision"],
                decisive_blocker=row["decisive_blocker"],
                allowed_next_action=row["allowed_next_action"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- h10d canonical parent status: `not_modified`",
            "- h10d bridge allowed: `false` for every row",
            "- live use allowed: `false` for every row",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_ledger(report_dir: Path, as_of: str) -> dict[str, Any]:
    rows = [
        _ledger_row(report_dir, research_id, policy)
        for research_id, policy in ROW_POLICY.items()
    ]
    return {
        "artifact_family": "parallel_1h_alpha_mining_stage0_decision_ledger",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "ledger_policy": {
            "local_stage0_pass_is_not_promotion": True,
            "provider_coverage_is_not_provider_trust": True,
            "h10d_canonical_parent_must_remain_untouched": True,
            "fail_closed_default": True,
        },
        "summary": _summarize(rows, report_dir),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report_dir = args.report_dir
    output_path = report_dir / LEDGER_NAME
    md_path = report_dir / LEDGER_MD_NAME
    ledger = build_ledger(report_dir, str(args.as_of))
    output_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    _write_markdown(ledger, md_path)
    compact = {
        "output_path": str(output_path),
        "markdown_path": str(md_path),
        "row_count": ledger["summary"]["row_count"],
        "missing_report_count": ledger["summary"]["missing_report_count"],
        "decision_counts": ledger["summary"]["decision_counts"],
        "overall_decision": ledger["summary"]["overall_decision"],
        "admitted_alpha_count": ledger["summary"]["admitted_alpha_count"],
        "h10d_bridge_allowed_count": ledger["summary"]["h10d_bridge_allowed_count"],
        "live_use_allowed_count": ledger["summary"]["live_use_allowed_count"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
