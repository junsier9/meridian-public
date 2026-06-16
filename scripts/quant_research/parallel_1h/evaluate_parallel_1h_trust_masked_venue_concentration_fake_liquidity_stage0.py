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

from scripts.quant_research.parallel_1h import evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0 as atom_eval  # noqa: E402
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0 as cap_eval  # noqa: E402
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval  # noqa: E402


CONTRACT_VERSION = "parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.v1"
RESEARCH_ID = "trust_masked_venue_concentration_fake_liquidity_stage0_1h"
DEFAULT_HORIZONS = trap_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 evaluator for trust-masked venue-concentration fake-liquidity risk. "
            "It consumes the trust-masked sidecar only as selector/exposure/capacity input "
            "and does not mutate h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--trust-sidecar-path", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _default_sidecar_path() -> Path:
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "sidecars"
        / "trust_masked_venue_concentration_1h"
        / "trust_masked_venue_concentration_1h.csv.gz"
    )


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _rolling_quantile_by_symbol(grouped: Any, column: str, q: float) -> pd.Series:
    return grouped[column].transform(lambda s: trap_eval._rolling_quantile(s, q))


def _load_trust_sidecar(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    columns = [
        "subject",
        "symbol",
        "open_time_ms",
        "trusted_eligible_venue_count",
        "trusted_locally_listed_venue_count",
        "trusted_observed_venue_count",
        "trusted_missing_venue_count",
        "trusted_total_quote_volume_usd",
        "trusted_top_venue",
        "trusted_top_venue_quote_volume_share",
        "trusted_venue_share_hhi",
        "trusted_non_binance_quote_volume_share",
        "binance_direct_quote_volume_usd",
        "binance_direct_quote_volume_share",
        "okex_quote_volume_usd",
        "okex_quote_volume_share",
        "bybitspot_quote_volume_usd",
        "bybitspot_quote_volume_share",
        "bybitspot_trust_status",
        "data_trust_status",
        "research_validation_status",
    ]
    header = pd.read_csv(path, nrows=0).columns
    usecols = [column for column in columns if column in set(header)]
    if "subject" not in usecols or "open_time_ms" not in usecols:
        return pd.DataFrame()
    sidecar = pd.read_csv(path, usecols=usecols)
    sidecar["subject"] = sidecar["subject"].astype(str).str.upper()
    sidecar["open_time_ms"] = pd.to_numeric(sidecar["open_time_ms"], errors="coerce")
    sidecar = sidecar.dropna(subset=["open_time_ms"]).copy()
    sidecar["open_time_ms"] = sidecar["open_time_ms"].astype("int64")
    numeric_columns = [
        "trusted_eligible_venue_count",
        "trusted_locally_listed_venue_count",
        "trusted_observed_venue_count",
        "trusted_missing_venue_count",
        "trusted_total_quote_volume_usd",
        "trusted_top_venue_quote_volume_share",
        "trusted_venue_share_hhi",
        "trusted_non_binance_quote_volume_share",
        "binance_direct_quote_volume_usd",
        "binance_direct_quote_volume_share",
        "okex_quote_volume_usd",
        "okex_quote_volume_share",
        "bybitspot_quote_volume_usd",
        "bybitspot_quote_volume_share",
    ]
    for column in numeric_columns:
        if column in sidecar.columns:
            sidecar[column] = pd.to_numeric(sidecar[column], errors="coerce")
    return sidecar.drop_duplicates(["subject", "open_time_ms"], keep="last")


def _sidecar_coverage(frame: pd.DataFrame, sidecar: pd.DataFrame, sidecar_path: Path) -> dict[str, Any]:
    if frame.empty:
        return {
            "sidecar_path": str(sidecar_path),
            "sidecar_exists": bool(sidecar_path.exists()),
            "research_frame_row_count": 0,
            "matched_row_count": 0,
        }
    matched = frame["trust_masked_venue_sidecar_available_flag"].fillna(False).astype(bool)
    multi = frame["trusted_multi_venue_observed_flag"].fillna(False).astype(bool)
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    multi_candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    events = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    by_symbol_rows: list[dict[str, Any]] = []
    candidate_frame = frame.loc[candidates, ["subject"]].copy()
    if not candidate_frame.empty:
        candidate_frame["sidecar_matched"] = matched.loc[candidate_frame.index].to_numpy(dtype=bool)
        candidate_frame["multi_venue_candidate"] = multi_candidates.loc[candidate_frame.index].to_numpy(dtype=bool)
        candidate_frame["event"] = events.loc[candidate_frame.index].to_numpy(dtype=bool)
        for subject, group in candidate_frame.groupby("subject"):
            post_pump_count = int(len(group))
            matched_count = int(group["sidecar_matched"].sum())
            multi_count = int(group["multi_venue_candidate"].sum())
            event_count = int(group["event"].sum())
            by_symbol_rows.append(
                {
                    "subject": str(subject),
                    "post_pump_candidate_count": post_pump_count,
                    "sidecar_matched_candidate_count": matched_count,
                    "multi_venue_candidate_count": multi_count,
                    "event_count": event_count,
                    "sidecar_missing_candidate_count": int(post_pump_count - matched_count),
                    "sidecar_matched_candidate_fraction": float(matched_count / max(post_pump_count, 1)),
                    "multi_venue_candidate_fraction": float(multi_count / max(post_pump_count, 1)),
                }
            )
    by_symbol_rows = sorted(
        by_symbol_rows,
        key=lambda row: (
            -int(row["sidecar_missing_candidate_count"]),
            -int(row["post_pump_candidate_count"]),
            str(row["subject"]),
        ),
    )
    sidecar_subjects = sorted(sidecar["subject"].astype(str).unique().tolist()) if not sidecar.empty else []
    return {
        "sidecar_path": str(sidecar_path),
        "sidecar_exists": bool(sidecar_path.exists()),
        "sidecar_row_count": int(len(sidecar)),
        "sidecar_subject_count": int(len(sidecar_subjects)),
        "sidecar_subjects": sidecar_subjects,
        "research_frame_row_count": int(len(frame)),
        "research_frame_subject_count": int(frame["subject"].astype(str).nunique()),
        "matched_row_count": int(matched.sum()),
        "matched_row_fraction": float(matched.mean()) if len(frame) else None,
        "multi_venue_observed_row_count": int(multi.sum()),
        "post_pump_candidate_count_before_sidecar_gate": int(candidates.sum()),
        "post_pump_candidate_count_with_sidecar_match": int((candidates & matched).sum()),
        "post_pump_candidate_count_with_multi_venue_gate": int(multi_candidates.sum()),
        "sidecar_match_candidate_fraction": float((candidates & matched).sum() / max(int(candidates.sum()), 1)),
        "multi_venue_candidate_fraction": float(multi_candidates.sum() / max(int(candidates.sum()), 1)),
        "bybitspot_trust_status_counts_on_matched_rows": {
            str(k): int(v)
            for k, v in frame.loc[matched, "bybitspot_trust_status"].value_counts(dropna=False).items()
        },
        "trusted_observed_venue_count_on_matched_rows": {
            str(k): int(v)
            for k, v in frame.loc[matched, "trusted_observed_venue_count"].value_counts(dropna=False).items()
        },
        "candidate_sidecar_coverage_by_symbol_top_missing": by_symbol_rows[:30],
    }


def _add_trust_masked_venue_state(base_frame: pd.DataFrame, sidecar: pd.DataFrame) -> pd.DataFrame:
    out = atom_eval._add_atom_state(base_frame) if not base_frame.empty else base_frame.copy()
    if out.empty:
        return out
    out = out.sort_values(["subject", "open_time_ms"]).copy()
    out["subject"] = out["subject"].astype(str).str.upper()

    sidecar_columns = [
        "subject",
        "open_time_ms",
        "trusted_eligible_venue_count",
        "trusted_locally_listed_venue_count",
        "trusted_observed_venue_count",
        "trusted_missing_venue_count",
        "trusted_total_quote_volume_usd",
        "trusted_top_venue",
        "trusted_top_venue_quote_volume_share",
        "trusted_venue_share_hhi",
        "trusted_non_binance_quote_volume_share",
        "binance_direct_quote_volume_usd",
        "binance_direct_quote_volume_share",
        "okex_quote_volume_usd",
        "okex_quote_volume_share",
        "bybitspot_quote_volume_usd",
        "bybitspot_quote_volume_share",
        "bybitspot_trust_status",
        "data_trust_status",
        "research_validation_status",
    ]
    available_columns = [column for column in sidecar_columns if column in sidecar.columns]
    out = out.merge(sidecar[available_columns], on=["subject", "open_time_ms"], how="left")

    numeric_columns = [
        "trusted_eligible_venue_count",
        "trusted_locally_listed_venue_count",
        "trusted_observed_venue_count",
        "trusted_missing_venue_count",
        "trusted_total_quote_volume_usd",
        "trusted_top_venue_quote_volume_share",
        "trusted_venue_share_hhi",
        "trusted_non_binance_quote_volume_share",
        "binance_direct_quote_volume_usd",
        "binance_direct_quote_volume_share",
        "okex_quote_volume_usd",
        "okex_quote_volume_share",
        "bybitspot_quote_volume_usd",
        "bybitspot_quote_volume_share",
    ]
    for column in numeric_columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    out["raw_capacity_proxy_usd"] = pd.to_numeric(out["capacity_proxy_usd"], errors="coerce")
    out["raw_capacity_haircut_candidate_flag"] = (
        out["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    )
    out["raw_fake_liquidity_capacity_haircut_flag"] = (
        out["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    )
    out["trust_masked_venue_sidecar_available_flag"] = (
        pd.to_numeric(out["trusted_total_quote_volume_usd"], errors="coerce").gt(0.0)
        & pd.to_numeric(out["trusted_observed_venue_count"], errors="coerce").ge(1)
    ).fillna(False)
    out["trusted_multi_venue_observed_flag"] = (
        out["trust_masked_venue_sidecar_available_flag"]
        & pd.to_numeric(out["trusted_observed_venue_count"], errors="coerce").ge(2)
    ).fillna(False)

    grouped = out.groupby("subject", group_keys=False, sort=False)
    out["trusted_top_venue_share_q80"] = _rolling_quantile_by_symbol(
        grouped, "trusted_top_venue_quote_volume_share", 0.80
    )
    out["trusted_venue_hhi_q80"] = _rolling_quantile_by_symbol(
        grouped, "trusted_venue_share_hhi", 0.80
    )
    out["trusted_non_binance_share_q80"] = _rolling_quantile_by_symbol(
        grouped, "trusted_non_binance_quote_volume_share", 0.80
    )

    top_share = pd.to_numeric(out["trusted_top_venue_quote_volume_share"], errors="coerce")
    hhi = pd.to_numeric(out["trusted_venue_share_hhi"], errors="coerce")
    non_binance = pd.to_numeric(out["trusted_non_binance_quote_volume_share"], errors="coerce")
    out["trusted_top_venue_share_high_flag"] = (
        out["trusted_multi_venue_observed_flag"]
        & top_share.ge(np.maximum(pd.to_numeric(out["trusted_top_venue_share_q80"], errors="coerce"), 0.90))
    ).fillna(False)
    out["trusted_venue_hhi_high_flag"] = (
        out["trusted_multi_venue_observed_flag"]
        & hhi.ge(np.maximum(pd.to_numeric(out["trusted_venue_hhi_q80"], errors="coerce"), 0.82))
    ).fillna(False)
    out["trusted_non_binance_dominance_flag"] = (
        out["trusted_multi_venue_observed_flag"]
        & non_binance.ge(np.maximum(pd.to_numeric(out["trusted_non_binance_share_q80"], errors="coerce"), 0.35))
    ).fillna(False)
    out["trusted_missing_venue_context_flag"] = (
        out["trust_masked_venue_sidecar_available_flag"]
        & pd.to_numeric(out["trusted_eligible_venue_count"], errors="coerce").ge(2)
        & pd.to_numeric(out["trusted_missing_venue_count"], errors="coerce").gt(0)
    ).fillna(False)
    out["bybit_fail_closed_context_flag"] = (
        out["bybitspot_trust_status"].astype(str).ne("sampled_pass")
    ).fillna(False)
    out["trust_masked_venue_concentration_suspect_flag"] = (
        out["trusted_top_venue_share_high_flag"]
        | out["trusted_venue_hhi_high_flag"]
        | out["trusted_non_binance_dominance_flag"]
    ).fillna(False)

    base_candidate = out["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    out["capacity_haircut_candidate_flag"] = (
        base_candidate & out["trusted_multi_venue_observed_flag"]
    ).fillna(False)
    out["trust_masked_venue_concentration_fake_liquidity_flag"] = (
        out["capacity_haircut_candidate_flag"]
        & out["trust_masked_venue_concentration_suspect_flag"]
        & (
            out["volume_oi_brushing_atom_flag"].fillna(False).astype(bool)
            | out["high_slippage_proxy_atom_flag"].fillna(False).astype(bool)
            | out["kill_switch_score_gte4_atom_flag"].fillna(False).astype(bool)
        )
    ).fillna(False)
    out["fake_liquidity_capacity_haircut_flag"] = (
        out["trust_masked_venue_concentration_fake_liquidity_flag"]
    )

    out["trust_masked_spot_capacity_proxy_usd"] = (
        pd.to_numeric(out["trusted_total_quote_volume_usd"], errors="coerce") * 0.005
    )
    out["capacity_proxy_usd"] = np.minimum(
        pd.to_numeric(out["raw_capacity_proxy_usd"], errors="coerce"),
        pd.to_numeric(out["trust_masked_spot_capacity_proxy_usd"], errors="coerce"),
    )
    out["capacity_haircut_multiplier"] = np.select(
        [
            out["fake_liquidity_capacity_haircut_flag"],
            out["capacity_haircut_candidate_flag"]
            & out["trust_masked_venue_concentration_suspect_flag"],
        ],
        [0.25, 0.50],
        default=1.0,
    )
    out["capacity_after_haircut_usd"] = (
        pd.to_numeric(out["capacity_proxy_usd"], errors="coerce")
        * pd.to_numeric(out["capacity_haircut_multiplier"], errors="coerce")
    )
    return out


def _feature_definitions() -> dict[str, Any]:
    return {
        "capacity_haircut_candidate_flag": (
            "post_pump_short_candidate_flag AND trust-masked sidecar has at least two observed trusted venues; "
            "single-venue coverage is treated as data context, not concentration evidence."
        ),
        "trusted_top_venue_share_high_flag": (
            "trusted_top_venue_quote_volume_share >= max(shifted rolling q80 by subject, 0.90), "
            "only when trusted_observed_venue_count >= 2."
        ),
        "trusted_venue_hhi_high_flag": (
            "trusted_venue_share_hhi >= max(shifted rolling q80 by subject, 0.82), "
            "only when trusted_observed_venue_count >= 2."
        ),
        "trusted_non_binance_dominance_flag": (
            "trusted_non_binance_quote_volume_share >= max(shifted rolling q80 by subject, 0.35), "
            "only when trusted_observed_venue_count >= 2."
        ),
        "trust_masked_venue_concentration_suspect_flag": (
            "top venue high OR HHI high OR non-Binance trusted venue dominance."
        ),
        "trust_masked_venue_concentration_fake_liquidity_flag": (
            "capacity candidate AND trust-masked venue concentration suspect AND "
            "(volume_oi_brushing OR high_slippage_proxy OR kill_switch_score>=4)."
        ),
        "capacity_proxy_usd": (
            "min(existing perp/OI capacity proxy, 0.5% of trusted spot venue quote volume)."
        ),
        "capacity_haircut_multiplier": (
            "0.25 for trust-masked venue fake-liquidity flag; 0.50 for venue-concentration suspect "
            "candidate rows; 1.0 otherwise."
        ),
        "bybitspot_trust_status": (
            "sampled_pass, sampled_fail_outlier, or unsampled_fail_closed from the sidecar builder; "
            "used as coverage/trust context, not as a standalone alpha rule."
        ),
        "pit_rule": (
            "venue thresholds use shifted rolling quantiles; current 1h venue fields are closed-bar inputs; "
            "forward returns and funding over horizons are labels only."
        ),
    }


def _data_sources_and_coverage(
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    sidecar: pd.DataFrame,
    sidecar_path: Path,
) -> dict[str, Any]:
    payload = cap_eval._data_sources_and_coverage(frame, meta, root)
    payload["research_lane"] = RESEARCH_ID
    payload["sources"]["trust_masked_venue_concentration_1h"] = str(sidecar_path)
    payload["provider_gap_note"] = (
        "This evaluator uses only the trust-masked venue sidecar: direct Binance, OKEX trusted-by-sample, "
        "Bybit sampled-pass symbols only, and Coinbase excluded."
    )
    payload["trust_masked_sidecar_coverage"] = _sidecar_coverage(frame, sidecar, sidecar_path)
    payload["source_reuse_note"] = (
        "Reuses the local 1h loader and fake-liquidity atom constructors; h10d state remains untouched."
    )
    return payload


def _venue_component_counts(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    event = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    components = [
        "trusted_top_venue_share_high_flag",
        "trusted_venue_hhi_high_flag",
        "trusted_non_binance_dominance_flag",
        "volume_oi_brushing_atom_flag",
        "high_slippage_proxy_atom_flag",
        "kill_switch_score_gte4_atom_flag",
        "trusted_missing_venue_context_flag",
        "bybit_fail_closed_context_flag",
    ]
    out: dict[str, Any] = {
        "candidate_rows": int(candidates.sum()),
        "event_rows": int((candidates & event).sum()),
    }
    for column in components:
        if column in frame.columns:
            out[column] = {
                "candidate_true_count": int((candidates & frame[column].fillna(False).astype(bool)).sum()),
                "event_true_count": int((event & frame[column].fillna(False).astype(bool)).sum()),
            }
    return out


def _pass_fail_decision(
    *,
    frame: pd.DataFrame,
    shuffle_tests: dict[str, Any],
    symbol_holdout: dict[str, Any],
    liquidity_bucket_consistency: dict[str, Any],
    delay_robustness: dict[str, Any],
    capacity_haircut_diagnostic: dict[str, Any],
) -> dict[str, Any]:
    base = cap_eval._pass_fail_decision(
        frame=frame,
        shuffle_tests=shuffle_tests,
        symbol_holdout=symbol_holdout,
        liquidity_bucket_consistency=liquidity_bucket_consistency,
        delay_robustness=delay_robustness,
        capacity_haircut_diagnostic=capacity_haircut_diagnostic,
    )
    coverage = frame["trust_masked_venue_sidecar_available_flag"].fillna(False).astype(bool) if not frame.empty else pd.Series(dtype=bool)
    multi_candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool) if not frame.empty else pd.Series(dtype=bool)
    extra_blockers = list(base.get("blockers") or [])
    if frame.empty:
        pass
    elif int(coverage.sum()) < 1_000:
        extra_blockers.append("trust_masked_sidecar_matched_rows_below_1000")
    elif int(multi_candidates.sum()) < 100:
        extra_blockers.append("multi_venue_capacity_candidate_count_below_100")
    if extra_blockers:
        base["label"] = "blocked"
        base["blockers"] = sorted(set(extra_blockers))
    base["alpha_admission_allowed"] = False
    base["h10d_promotion_state_mutation"] = False
    base["decision_rule"] = (
        "pass only if sidecar coverage/candidate minimums clear and capacity diagnostic, shuffle, "
        "symbol holdout, liquidity bucket, and +1h/+6h/+24h delay robustness all pass. "
        "A pass would admit only a quarantined selector/exposure research state, not live alpha."
    )
    return base


def _next_landing_shape(decision: dict[str, Any]) -> dict[str, Any]:
    label = decision.get("label")
    if label == "pass":
        return {
            "recommended_shape": "quarantined_selector_exposure_capacity_policy",
            "next_step": (
                "Run a parent-interaction simulator with hard-veto, reduce-short, and capacity-haircut variants; "
                "do not bridge to h10d or live."
            ),
        }
    if label == "blocked":
        return {
            "recommended_shape": "data_or_universe_repair",
            "next_step": "Repair trust-masked sidecar coverage before interpreting the venue-concentration rule.",
        }
    return {
        "recommended_shape": "fail_closed",
        "next_step": (
            "Do not continue this rule as an admission candidate. Use the report only for attribution, "
            "or run wider Bybit concordance / native exchange-flow sidecars before defining a new candidate."
        ),
    }


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    sidecar: pd.DataFrame,
    sidecar_path: Path,
    output_path: Path,
    as_of: str,
    horizons: tuple[int, ...],
    shuffle_iterations: int,
) -> dict[str, Any]:
    shuffle_tests = cap_eval._shuffle_tests(frame, iterations=shuffle_iterations, horizon=24) if not frame.empty else {"passed": False}
    symbol_holdout = cap_eval._symbol_holdout(frame, horizon=24) if not frame.empty else {"passed": False}
    liquidity_bucket_consistency = (
        cap_eval._liquidity_bucket_consistency(frame, horizon=24) if not frame.empty else {"passed": False}
    )
    delay_robustness = cap_eval._delay_robustness(frame, horizon=24) if not frame.empty else {"passed": False}
    capacity_haircut_diagnostic = (
        cap_eval._capacity_haircut_diagnostic(frame, horizon=24) if not frame.empty else {"passed": False}
    )
    decision = _pass_fail_decision(
        frame=frame,
        shuffle_tests=shuffle_tests,
        symbol_holdout=symbol_holdout,
        liquidity_bucket_consistency=liquidity_bucket_consistency,
        delay_robustness=delay_robustness,
        capacity_haircut_diagnostic=capacity_haircut_diagnostic,
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
        "data_sources_and_coverage": _data_sources_and_coverage(frame, meta, root, sidecar, sidecar_path),
        "feature_definitions": _feature_definitions(),
        "venue_component_counts": _venue_component_counts(frame),
        "event_count_by_symbol": cap_eval._event_count_by_symbol(frame) if not frame.empty else {},
        "event_count_by_liquidity_bucket": cap_eval._event_count_by_liquidity_bucket(frame) if not frame.empty else {},
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": cap_eval._forward_return_table(frame, horizons)
        if not frame.empty
        else {},
        "selected_short_changed_rows_equivalent": cap_eval._selected_short_changed_rows_equivalent(frame, horizon=24)
        if not frame.empty
        else {},
        "funding_drag_summary": cap_eval._funding_drag_summary(frame, horizons) if not frame.empty else {},
        "slippage_or_capacity_proxy": cap_eval._capacity_summary(frame) if not frame.empty else {},
        "capacity_haircut_diagnostic": capacity_haircut_diagnostic,
        "shuffle_tests": shuffle_tests,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": liquidity_bucket_consistency,
        "delay_robustness": delay_robustness,
        "pass_fail_decision": decision,
        "next_landing_shape": _next_landing_shape(decision),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = trap_eval._resolve_market_history_root(args.market_history_root)
    sidecar_path = args.trust_sidecar_path or _default_sidecar_path()
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "trust_masked_venue_concentration_fake_liquidity_stage0_1h.json"
    horizons = tuple(DEFAULT_HORIZONS)
    symbols = trap_eval._discover_symbols(root, requested=str(args.symbols), limit=int(args.symbol_limit))
    base_frame, meta = trap_eval._load_research_frame(root, symbols, horizons)
    sidecar = _load_trust_sidecar(sidecar_path)
    frame = _add_trust_masked_venue_state(base_frame, sidecar) if not base_frame.empty and not sidecar.empty else pd.DataFrame()
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        sidecar=sidecar,
        sidecar_path=sidecar_path,
        output_path=output_path,
        as_of=str(args.as_of),
        horizons=horizons,
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "loaded_symbol_count": report["data_sources_and_coverage"].get("loaded_symbol_count"),
        "row_count": report["data_sources_and_coverage"].get("row_count"),
        "sidecar_coverage": report["data_sources_and_coverage"].get("trust_masked_sidecar_coverage"),
        "capacity_haircut_candidate_row_count": report["pass_fail_decision"].get(
            "capacity_haircut_candidate_row_count"
        ),
        "haircut_event_count": report["pass_fail_decision"].get("haircut_event_count"),
        "event_count_by_liquidity_bucket": report.get("event_count_by_liquidity_bucket"),
        "primary_effect_h24": report.get("selected_short_changed_rows_equivalent", {}).get("effect"),
        "capacity_haircut_diagnostic_passed": report.get("capacity_haircut_diagnostic", {}).get("passed"),
        "shuffle_passed": report.get("shuffle_tests", {}).get("passed"),
        "symbol_holdout_passed": report.get("symbol_holdout", {}).get("passed"),
        "liquidity_bucket_consistency_passed": report.get("liquidity_bucket_consistency", {}).get("passed"),
        "delay_robustness_passed": report.get("delay_robustness", {}).get("passed"),
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
