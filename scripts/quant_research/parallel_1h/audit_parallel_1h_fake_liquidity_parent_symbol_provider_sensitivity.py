from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.parallel_1h import simulate_parallel_1h_fake_liquidity_parent_interaction as parent_sim  # noqa: E402


CONTRACT_VERSION = "parallel_1h_fake_liquidity_parent_symbol_provider_sensitivity.v1"
RESEARCH_ID = "fake_liquidity_parent_symbol_provider_sensitivity_1h"
DEFAULT_HORIZON = 24
WATCHLIST_SUBJECTS = ("SYRUP", "SUN", "LUNC", "WIF")
CORE_PROVIDER_COLUMNS = (
    "orderbook_bids_usd",
    "orderbook_asks_usd",
    "taker_buy_volume_usd",
    "taker_sell_volume_usd",
    "open_interest_value",
    "perp_quote_volume_usd",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Symbol/bucket/provider sensitivity audit for the rejected fake-liquidity 1h "
            "parent interaction simulator."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _improvement(events: pd.DataFrame, *, variant: str, horizon: int = DEFAULT_HORIZON) -> float | None:
    if events.empty:
        return None
    flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
    exposure = parent_sim._variant_exposure(flag, variant)
    return parent_sim._improvement(events, exposure, horizon=horizon)


def _variant_policy_summary(
    events: pd.DataFrame,
    *,
    variant: str,
    horizon: int = DEFAULT_HORIZON,
) -> dict[str, Any]:
    if events.empty:
        return {
            "row_count": 0,
            "policy_row_count": 0,
            "improvement": None,
            "symbol_holdout_passed": False,
        }
    flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
    exposure = parent_sim._variant_exposure(flag, variant)
    portfolio = parent_sim._portfolio_metrics(events, exposure, horizons=(horizon,))
    baseline = parent_sim._portfolio_metrics(events, np.ones(len(events)), horizons=(horizon,))
    holdout = parent_sim._symbol_holdout(events, variant=variant, horizon=horizon)
    bucket = parent_sim._liquidity_bucket_consistency(events, variant=variant, horizon=horizon)
    return {
        "row_count": int(len(events)),
        "policy_row_count": int(flag.sum()),
        "policy_row_fraction": float(flag.mean()) if len(flag) else None,
        "improvement": _improvement(events, variant=variant, horizon=horizon),
        "baseline_h24_gross_pnl_per_candidate": baseline[f"h{horizon}"].get("gross_pnl_per_candidate"),
        "policy_h24_gross_pnl_per_candidate": portfolio[f"h{horizon}"].get("gross_pnl_per_candidate"),
        "baseline_adverse_squeeze_gt_5pct": baseline[f"h{horizon}"].get(
            "adverse_squeeze_gt_5pct_fraction_weighted"
        ),
        "policy_adverse_squeeze_gt_5pct": portfolio[f"h{horizon}"].get(
            "adverse_squeeze_gt_5pct_fraction_weighted"
        ),
        "mean_exposure": portfolio.get("mean_exposure"),
        "symbol_holdout": {
            "eligible_symbol_count": holdout.get("eligible_symbol_count"),
            "directionally_consistent_symbol_fraction": holdout.get(
                "directionally_consistent_symbol_fraction"
            ),
            "top_policy_symbol_event_share": holdout.get("top_policy_symbol_event_share"),
            "passed": holdout.get("passed"),
        },
        "liquidity_bucket_consistency": {
            "eligible_bucket_count": bucket.get("eligible_bucket_count"),
            "passed": bucket.get("passed"),
        },
    }


def _symbol_attribution(events: pd.DataFrame, *, variant: str) -> dict[str, Any]:
    total_n = max(len(events), 1)
    rows: list[dict[str, Any]] = []
    for subject, group in events.groupby("subject"):
        flag = group["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        exposure = parent_sim._variant_exposure(flag, variant)
        short_ret = pd.to_numeric(
            group[f"forward_{DEFAULT_HORIZON}h_short_return"],
            errors="coerce",
        ).to_numpy(dtype="float64")
        valid = np.isfinite(short_ret)
        contribution_sum = float(np.nansum((exposure[valid] - 1.0) * short_ret[valid])) if valid.any() else 0.0
        local_improvement = float(contribution_sum / max(valid.sum(), 1)) if valid.any() else None
        rows.append(
            {
                "subject": str(subject),
                "row_count": int(len(group)),
                "policy_row_count": int(flag.sum()),
                "policy_row_fraction": float(flag.mean()) if len(flag) else None,
                "local_improvement": local_improvement,
                "global_contribution": float(contribution_sum / total_n),
                "liquidity_bucket_counts": {
                    str(key): int(value)
                    for key, value in group.loc[flag].groupby("liquidity_bucket").size().items()
                },
                "is_provider_watchlist": str(subject) in WATCHLIST_SUBJECTS,
            }
        )
    positives = [row for row in rows if (row.get("local_improvement") or 0.0) > 0.0]
    negatives = [row for row in rows if (row.get("local_improvement") or 0.0) <= 0.0]
    positive_contributors = [
        row for row in rows if row["policy_row_count"] > 0 and row["global_contribution"] > 0.0
    ]
    negative_contributors = [
        row for row in rows if row["policy_row_count"] > 0 and row["global_contribution"] < 0.0
    ]
    return {
        "variant": variant,
        "eligible_symbol_count": int(len(rows)),
        "positive_symbol_count": int(len(positives)),
        "negative_symbol_count": int(len(negatives)),
        "positive_symbol_fraction": float(len(positives) / max(len(rows), 1)),
        "top_positive_contributors": sorted(
            positive_contributors,
            key=lambda row: row["global_contribution"],
            reverse=True,
        )[:15],
        "top_negative_contributors": sorted(
            negative_contributors,
            key=lambda row: row["global_contribution"],
        )[:15],
        "watchlist_symbols": [
            row for row in sorted(rows, key=lambda row: row["subject"]) if row["is_provider_watchlist"]
        ],
        "by_symbol": {row["subject"]: row for row in rows},
    }


def _scenario_masks(events: pd.DataFrame) -> dict[str, pd.Series]:
    end_ms = int(events["open_time_ms"].max()) if not events.empty else 0
    complete_core = pd.Series(True, index=events.index)
    for column in CORE_PROVIDER_COLUMNS:
        if column in events.columns:
            complete_core &= pd.to_numeric(events[column], errors="coerce").notna()
        else:
            complete_core &= False
    return {
        "all": pd.Series(True, index=events.index),
        "exclude_provider_watchlist": ~events["subject"].astype(str).isin(WATCHLIST_SUBJECTS),
        "provider_watchlist_only": events["subject"].astype(str).isin(WATCHLIST_SUBJECTS),
        "exclude_last_24h": events["open_time_ms"].lt(end_ms - 24 * parent_sim.HOUR_MS),
        "exclude_last_72h": events["open_time_ms"].lt(end_ms - 72 * parent_sim.HOUR_MS),
        "exclude_last_168h": events["open_time_ms"].lt(end_ms - 168 * parent_sim.HOUR_MS),
        "complete_core_provider_fields": complete_core,
    }


def _scenario_sensitivity(events: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for scenario, mask in _scenario_masks(events).items():
        subset = events.loc[mask].copy()
        out[scenario] = {
            variant: _variant_policy_summary(subset, variant=variant)
            for variant in ("hard_veto", "quarter_size", "soft_multiplier")
        }
    return out


def _listing_age_bins(frame: pd.DataFrame, events: pd.DataFrame, *, variant: str) -> dict[str, Any]:
    if events.empty:
        return {}
    first_by_subject = frame.groupby("subject")["open_time_ms"].min()
    local = events.copy()
    local["symbol_first_open_time_ms"] = local["subject"].map(first_by_subject)
    local["symbol_history_age_days_at_event"] = (
        local["open_time_ms"] - local["symbol_first_open_time_ms"]
    ) / (24.0 * parent_sim.HOUR_MS)
    bins = [-np.inf, 30, 90, 180, 365, np.inf]
    labels = ["lt_30d", "30_90d", "90_180d", "180_365d", "gte_365d"]
    local["age_bin"] = pd.cut(local["symbol_history_age_days_at_event"], bins=bins, labels=labels)
    out: dict[str, Any] = {}
    for label, group in local.groupby("age_bin", observed=True):
        out[str(label)] = _variant_policy_summary(group.copy(), variant=variant)
    return out


def _bucket_symbol_matrix(events: pd.DataFrame, *, variant: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        out[str(bucket)] = _symbol_attribution(group.copy(), variant=variant)
    return out


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
) -> dict[str, Any]:
    events = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    hard_veto_summary = _variant_policy_summary(events, variant="hard_veto")
    symbol_attribution = _symbol_attribution(events, variant="hard_veto")
    scenario_sensitivity = _scenario_sensitivity(events)
    listing_age = _listing_age_bins(frame, events, variant="hard_veto")
    bucket_symbol_matrix = _bucket_symbol_matrix(events, variant="hard_veto")

    provider_watchlist = scenario_sensitivity["exclude_provider_watchlist"]["hard_veto"]
    watchlist_only = scenario_sensitivity["provider_watchlist_only"]["hard_veto"]
    all_fraction = hard_veto_summary["symbol_holdout"].get("directionally_consistent_symbol_fraction")
    root_cause = (
        "hard_veto all-symbol directionally consistent fraction is below 0.60"
        if all_fraction is not None and float(all_fraction) < 0.60
        else "strict parent simulator remains rejected; this sensitivity audit is explanatory only"
    )
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "data_sources_and_coverage": parent_sim.haircut_eval._data_sources_and_coverage(frame, meta, root),
        "provider_watchlist_subjects": list(WATCHLIST_SUBJECTS),
        "parent_context": {
            "candidate_count": int(len(events)),
            "aggregate_haircut_row_count": int(
                events["fake_liquidity_capacity_haircut_flag"].fillna(False).sum()
            ),
            "audited_variant": "hard_veto",
            "reason": "hard_veto had the strongest aggregate improvement but failed symbol holdout in the parent simulator.",
        },
        "hard_veto_summary": hard_veto_summary,
        "symbol_attribution": symbol_attribution,
        "scenario_sensitivity": scenario_sensitivity,
        "listing_age_sensitivity": listing_age,
        "bucket_symbol_matrix": bucket_symbol_matrix,
        "pass_fail_decision": {
            "label": "fail",
            "decision_rule": (
                "This audit is explanatory only. Parent interaction remains rejected unless the all-symbol "
                "strict simulator passes symbol holdout without post-hoc exclusions."
            ),
            "root_cause": root_cause,
            "all_symbol_holdout_fraction": hard_veto_summary["symbol_holdout"].get(
                "directionally_consistent_symbol_fraction"
            ),
            "exclude_provider_watchlist_holdout_fraction": provider_watchlist["symbol_holdout"].get(
                "directionally_consistent_symbol_fraction"
            ),
            "provider_watchlist_only_improvement": watchlist_only.get("improvement"),
            "admission_allowed": False,
        },
        "next_landing_shape": {
            "recommended_shape": "do_not_promote_symbol_unstable_parent_interaction",
            "next_step": (
                "Use attribution to design a new pre-registered state or provider/venue sidecar; do not "
                "rescue the current simulator by excluding losing symbols after the fact."
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = parent_sim.haircut_eval.trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "fake_liquidity_parent_symbol_provider_sensitivity_1h.json"
    symbols = parent_sim.haircut_eval.trap_eval._discover_symbols(
        root,
        requested=str(args.symbols),
        limit=int(args.symbol_limit),
    )
    base_frame, meta = parent_sim.haircut_eval.trap_eval._load_research_frame(
        root,
        symbols,
        tuple(parent_sim.DEFAULT_HORIZONS),
    )
    frame = (
        parent_sim.haircut_eval._add_fake_liquidity_capacity_state(base_frame)
        if not base_frame.empty
        else base_frame
    )
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        output_path=output_path,
        as_of=str(args.as_of),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "candidate_count": report["parent_context"]["candidate_count"],
        "aggregate_haircut_row_count": report["parent_context"]["aggregate_haircut_row_count"],
        "all_symbol_holdout_fraction": report["pass_fail_decision"]["all_symbol_holdout_fraction"],
        "exclude_provider_watchlist_holdout_fraction": report["pass_fail_decision"][
            "exclude_provider_watchlist_holdout_fraction"
        ],
        "provider_watchlist_only_improvement": report["pass_fail_decision"]["provider_watchlist_only_improvement"],
        "top_negative_contributors": report["symbol_attribution"]["top_negative_contributors"][:5],
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
