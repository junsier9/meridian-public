from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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

from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_tape_spk_stage0 as event_stage0,
    evaluate_m3_3_strict_event_state_stage0 as strict_stage0,
)
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "m3_3_robustness_v2_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_SHUFFLE_ITERATIONS = 80


@dataclass(frozen=True)
class VariantSpec:
    label: str
    min_quality: float
    max_noise_ratio: float = 0.0
    require_no_hype: bool = True
    replacement_pool_size: int = 8
    max_replacements: int = 3
    eligible_liquidity_buckets: tuple[str, ...] = ()
    excluded_subjects: tuple[str, ...] = ()
    diagnostic_only: bool = False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="M3.3 robustness-oriented v2 Stage 0 diagnostics."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_stage0.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument(
        "--variant-label",
        action="append",
        default=None,
        help="Run only the named variant label. Can be repeated.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec(label="v1_strict_q1_noise0", min_quality=1.0),
        VariantSpec(label="v2_q15_noise0", min_quality=1.5),
        VariantSpec(label="v2_q2_noise0", min_quality=2.0),
        VariantSpec(label="v2_q1_noise0_one_replacement", min_quality=1.0, max_replacements=1),
        VariantSpec(
            label="v2_q15_top_liquidity_only",
            min_quality=1.5,
            eligible_liquidity_buckets=("top_liquidity",),
        ),
        VariantSpec(
            label="diagnostic_q1_without_avax_uni",
            min_quality=1.0,
            excluded_subjects=("AVAX", "UNI"),
            diagnostic_only=True,
        ),
    ]


def _eligible_mask(frame: pd.DataFrame, spec: VariantSpec) -> pd.Series:
    mask = strict_stage0._eligible_mask(
        frame,
        min_quality=spec.min_quality,
        max_noise_ratio=spec.max_noise_ratio,
        require_no_hype=spec.require_no_hype,
    )
    if spec.eligible_liquidity_buckets and "liquidity_bucket" in frame.columns:
        buckets = {item.lower() for item in spec.eligible_liquidity_buckets}
        mask &= frame["liquidity_bucket"].astype(str).str.lower().isin(buckets)
    if spec.excluded_subjects and "subject" in frame.columns:
        excluded = {item.upper() for item in spec.excluded_subjects}
        mask &= ~frame["subject"].astype(str).str.upper().isin(excluded)
    return mask.fillna(False)


def _select_rows(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    target_horizon_bars: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    work = frame.copy()
    if "parent_score" not in work.columns:
        work["parent_score"] = xs_alpha_ontology_v5_score(work)
    work["strict_eligible"] = _eligible_mask(work, spec)
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        "strict_eligible",
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    parent_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    changed = 0
    eligible = 0
    total = 0
    short_count = 3
    pool_size = max(int(spec.replacement_pool_size), short_count + 1)
    max_replacements = max(int(spec.max_replacements), 0)
    for _, group in work.groupby("timestamp_ms", sort=False):
        total += 1
        ordered = group.sort_values("parent_score", ascending=False).copy()
        if len(ordered) <= short_count:
            continue
        parent_shorts = ordered.tail(short_count).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        eligible_pool = tail_pool.loc[tail_pool["strict_eligible"]].copy()
        if not eligible_pool.empty:
            eligible += 1
        selected = parent_shorts.copy()
        if max_replacements > 0 and not eligible_pool.empty:
            candidate_order = eligible_pool.sort_values(
                ["m3_3_event_state_short_quality_v1", "parent_score"],
                ascending=[False, True],
            ).copy()
            parent_subjects = set(parent_shorts["subject"].astype(str))
            entrants = candidate_order.loc[
                ~candidate_order["subject"].astype(str).isin(parent_subjects)
            ].head(max_replacements)
            if not entrants.empty:
                keep_parent = parent_shorts.sort_values("parent_score", ascending=True).head(
                    max(short_count - len(entrants), 0)
                )
                selected = pd.concat([entrants, keep_parent], axis=0).head(short_count)
        parent_subjects = set(parent_shorts["subject"].astype(str))
        selected_subjects = set(selected["subject"].astype(str))
        if parent_subjects != selected_subjects:
            changed += 1
        parent_rows.extend(parent_shorts[keep].to_dict("records"))
        selected_rows.extend(selected[keep].to_dict("records"))
        entered_rows.extend(selected.loc[~selected["subject"].astype(str).isin(parent_subjects), keep].to_dict("records"))
        exited_rows.extend(parent_shorts.loc[~parent_shorts["subject"].astype(str).isin(selected_subjects), keep].to_dict("records"))
    meta = {
        "timestamp_count": int(total),
        "eligible_timestamp_count": int(eligible),
        "changed_timestamp_count": int(changed),
        "eligible_timestamp_fraction": float(eligible / max(total, 1)),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
    }
    return (
        pd.DataFrame(parent_rows),
        pd.DataFrame(selected_rows),
        pd.DataFrame(entered_rows),
        pd.DataFrame(exited_rows),
        meta,
    )


def _horizon_field(target_horizon_bars: int) -> str:
    return f"next_{target_horizon_bars}d_mean"


def _edge_from_summaries(
    *,
    selected_summary: dict[str, Any],
    parent_summary: dict[str, Any],
    target_horizon_bars: int,
) -> float | None:
    field = _horizon_field(target_horizon_bars)
    if selected_summary.get(field) is None or parent_summary.get(field) is None:
        return None
    return float(parent_summary[field]) - float(selected_summary[field])


def _evaluate(frame: pd.DataFrame, *, spec: VariantSpec, target_horizon_bars: int) -> dict[str, Any]:
    parent, selected, entered, exited, meta = _select_rows(
        frame,
        spec=spec,
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = strict_stage0._summarize(parent, target_horizon_bars=target_horizon_bars)
    selected_summary = strict_stage0._summarize(selected, target_horizon_bars=target_horizon_bars)
    entered_summary = strict_stage0._summarize(entered, target_horizon_bars=target_horizon_bars)
    exited_summary = strict_stage0._summarize(exited, target_horizon_bars=target_horizon_bars)
    return {
        "label": spec.label,
        "diagnostic_only": spec.diagnostic_only,
        "spec": {
            "min_quality": spec.min_quality,
            "max_noise_ratio": spec.max_noise_ratio,
            "require_no_hype": spec.require_no_hype,
            "replacement_pool_size": spec.replacement_pool_size,
            "max_replacements": spec.max_replacements,
            "eligible_liquidity_buckets": list(spec.eligible_liquidity_buckets),
            "excluded_subjects": list(spec.excluded_subjects),
        },
        "timestamp_activity": meta,
        "parent_short_summary": parent_summary,
        "selected_summary": selected_summary,
        "selected_vs_parent": strict_stage0._compare(
            candidate=selected_summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "edge_vs_parent_mean_return": _edge_from_summaries(
            selected_summary=selected_summary,
            parent_summary=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "entered": entered_summary,
        "exited": exited_summary,
        "entered_minus_exited": strict_stage0._compare(
            candidate=entered_summary,
            baseline=exited_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "rows": {
            "selected": selected,
            "entered": entered,
            "exited": exited,
        },
    }


def _shift_event_columns_by_subject(frame: pd.DataFrame, *, rng: np.random.Generator) -> pd.DataFrame:
    columns = [
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
    ]
    shifted = frame.copy()
    if "subject" not in shifted.columns:
        return shifted
    for _, idx in shifted.groupby("subject", sort=False).groups.items():
        index = list(idx)
        if len(index) <= 1:
            continue
        offset = int(rng.integers(1, len(index)))
        for column in columns:
            values = shifted.loc[index, column].to_numpy(copy=True)
            shifted.loc[index, column] = np.roll(values, offset)
    return shifted


def _shuffle_labels_within_timestamp(
    frame: pd.DataFrame,
    *,
    target_horizon_bars: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    shuffled = frame.copy().reset_index(drop=True)
    columns = ["forward_1d_log_return", f"forward_{target_horizon_bars}d_log_return"]
    for _, idx in shuffled.groupby("timestamp_ms", sort=False).groups.items():
        index = list(idx)
        if len(index) <= 1:
            continue
        permutation = rng.permutation(len(index))
        for column in columns:
            values = shuffled.loc[index, column].to_numpy(copy=True)
            shuffled.loc[index, column] = values[permutation]
    return shuffled


def _shuffle_test(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    target_horizon_bars: int,
    observed_edge: float | None,
    iterations: int,
    mode: str,
) -> dict[str, Any]:
    if observed_edge is None:
        return {"passed": False, "reason": "missing_observed_edge", "iterations": 0}
    rng = np.random.default_rng(20260504 if mode == "time" else 20260505)
    edges: list[float] = []
    for _ in range(max(int(iterations), 1)):
        if mode == "time":
            sample = _shift_event_columns_by_subject(frame, rng=rng)
        elif mode == "label":
            sample = _shuffle_labels_within_timestamp(frame, target_horizon_bars=target_horizon_bars, rng=rng)
        else:
            raise ValueError(f"unsupported shuffle mode: {mode}")
        result = _evaluate(sample, spec=spec, target_horizon_bars=target_horizon_bars)
        edge = result.get("edge_vs_parent_mean_return")
        if edge is not None:
            edges.append(float(edge))
    if not edges:
        return {"passed": False, "reason": "no_shuffle_edges", "iterations": 0}
    arr = np.asarray(edges, dtype=float)
    quantile = float(np.mean(arr <= float(observed_edge)))
    return {
        "passed": bool(quantile >= 0.90),
        "iterations": int(len(edges)),
        "observed_edge": float(observed_edge),
        "shuffle_edge_mean": float(arr.mean()),
        "shuffle_edge_p90": float(np.quantile(arr, 0.90)),
        "observed_edge_quantile": quantile,
    }


def _symbol_holdout(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    target_horizon_bars: int,
) -> dict[str, Any]:
    holdouts: list[dict[str, Any]] = []
    sign_flips: list[str] = []
    for subject in sorted(frame["subject"].dropna().astype(str).unique()):
        held = frame.loc[frame["subject"].astype(str) != subject].copy()
        if held.empty:
            continue
        result = _evaluate(held, spec=spec, target_horizon_bars=target_horizon_bars)
        edge = result.get("edge_vs_parent_mean_return")
        if edge is not None and float(edge) <= 0.0:
            sign_flips.append(subject)
        holdouts.append({"subject": subject, "edge_vs_parent_mean_return": edge})
    return {
        "passed": not sign_flips,
        "sign_flip_subjects": sign_flips,
        "holdouts": holdouts,
    }


def _liquidity_buckets(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    target_horizon_bars: int,
) -> dict[str, Any]:
    buckets: list[dict[str, Any]] = []
    positive = 0
    touched_positive = 0
    touched = 0
    for bucket in sorted(frame["liquidity_bucket"].dropna().astype(str).unique()):
        bucket_frame = frame.loc[frame["liquidity_bucket"].astype(str) == bucket].copy()
        result = _evaluate(bucket_frame, spec=spec, target_horizon_bars=target_horizon_bars)
        edge = result.get("edge_vs_parent_mean_return")
        changed = float(dict(result.get("timestamp_activity") or {}).get("changed_timestamp_fraction", 0.0) or 0.0)
        if edge is not None and float(edge) > 0.0:
            positive += 1
            if changed > 0.0:
                touched_positive += 1
        if changed > 0.0:
            touched += 1
        buckets.append(
            {
                "liquidity_bucket": bucket,
                "edge_vs_parent_mean_return": edge,
                "changed_timestamp_fraction": changed,
            }
        )
    return {
        "passed": positive >= 2,
        "positive_bucket_count": positive,
        "touched_bucket_count": touched,
        "touched_positive_bucket_count": touched_positive,
        "buckets": buckets,
    }


def _score_candidate(result: dict[str, Any], *, target_horizon_bars: int) -> dict[str, Any]:
    field = _horizon_field(target_horizon_bars)
    entered = dict(result.get("entered") or {})
    entered_minus_exited = dict(result.get("entered_minus_exited") or {})
    edge = result.get("edge_vs_parent_mean_return")
    return {
        "stage0_passed": bool(
            edge is not None
            and float(edge) > 0.0005
            and entered.get(field) is not None
            and float(entered[field]) < 0.0
            and entered_minus_exited.get(f"delta_{field}") is not None
            and float(entered_minus_exited[f"delta_{field}"]) < 0.0
            and float(dict(result.get("timestamp_activity") or {}).get("changed_timestamp_fraction", 0.0) or 0.0) >= 0.02
        ),
        "edge_vs_parent_mean_return": edge,
        "entered_next_h_mean": entered.get(field),
        "entered_minus_exited_next_h_delta": entered_minus_exited.get(f"delta_{field}"),
    }


def _strip_rows(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out.pop("rows", None)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-robustness-v2-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target_horizon_bars = int(args.target_horizon_bars)
    frame = strict_stage0._load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=0,
    )
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    delayed = strict_stage0._load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=1,
    )
    delayed["parent_score"] = xs_alpha_ontology_v5_score(delayed)
    evaluations: dict[str, Any] = {}
    row_artifacts: dict[str, dict[str, str]] = {}
    variant_labels = {str(item).strip() for item in list(args.variant_label or []) if str(item).strip()}
    specs = [spec for spec in _variant_specs() if not variant_labels or spec.label in variant_labels]
    if variant_labels and len(specs) != len(variant_labels):
        available = ", ".join(spec.label for spec in _variant_specs())
        raise SystemExit(f"unknown variant label; available: {available}")
    checkpoint_path = output_dir / "m3_3_robustness_v2_stage0.partial.json"
    for spec in specs:
        result = _evaluate(frame, spec=spec, target_horizon_bars=target_horizon_bars)
        delay_result = _evaluate(delayed, spec=spec, target_horizon_bars=target_horizon_bars)
        observed_edge = result.get("edge_vs_parent_mean_return")
        result["stage0_scorecard"] = _score_candidate(result, target_horizon_bars=target_horizon_bars)
        result["delay_plus_1d_scorecard"] = _score_candidate(delay_result, target_horizon_bars=target_horizon_bars)
        result["falsification_proxies"] = {
            "time_shuffle": _shuffle_test(
                frame,
                spec=spec,
                target_horizon_bars=target_horizon_bars,
                observed_edge=observed_edge,
                iterations=int(args.shuffle_iterations),
                mode="time",
            ),
            "label_shuffle": _shuffle_test(
                frame,
                spec=spec,
                target_horizon_bars=target_horizon_bars,
                observed_edge=observed_edge,
                iterations=max(int(args.shuffle_iterations) // 2, 1),
                mode="label",
            ),
            "symbol_holdout": _symbol_holdout(frame, spec=spec, target_horizon_bars=target_horizon_bars),
            "liquidity_bucket_consistency": _liquidity_buckets(
                frame,
                spec=spec,
                target_horizon_bars=target_horizon_bars,
            ),
        }
        row_artifacts[spec.label] = {}
        for row_name in ("selected", "entered", "exited"):
            path = output_dir / f"{spec.label}_{row_name}.csv"
            result["rows"][row_name].to_csv(path, index=False)
            row_artifacts[spec.label][row_name] = str(path)
        evaluations[spec.label] = _strip_rows(result)
        checkpoint = {
            "contract_version": CONTRACT_VERSION,
            "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "as_of": str(args.as_of),
            "target_horizon_bars": target_horizon_bars,
            "event_lookback_days": int(args.event_lookback_days),
            "shuffle_iterations": int(args.shuffle_iterations),
            "variant_filter": sorted(variant_labels),
            "row_artifacts": row_artifacts,
            "evaluation": evaluations,
        }
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    ranked = sorted(
        (
            {
                "label": label,
                "diagnostic_only": bool(payload.get("diagnostic_only")),
                **dict(payload.get("stage0_scorecard") or {}),
                "time_shuffle_passed": bool(
                    dict(payload.get("falsification_proxies", {}).get("time_shuffle") or {}).get("passed")
                ),
                "label_shuffle_passed": bool(
                    dict(payload.get("falsification_proxies", {}).get("label_shuffle") or {}).get("passed")
                ),
                "symbol_holdout_passed": bool(
                    dict(payload.get("falsification_proxies", {}).get("symbol_holdout") or {}).get("passed")
                ),
                "liquidity_bucket_passed": bool(
                    dict(payload.get("falsification_proxies", {}).get("liquidity_bucket_consistency") or {}).get("passed")
                ),
            }
            for label, payload in evaluations.items()
        ),
        key=lambda item: (
            bool(item["stage0_passed"]),
            bool(item["time_shuffle_passed"]),
            bool(item["label_shuffle_passed"]),
            bool(item["symbol_holdout_passed"]),
            bool(item["liquidity_bucket_passed"]),
            float(item["edge_vs_parent_mean_return"] or -999.0),
        ),
        reverse=True,
    )
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
        "event_lookback_days": int(args.event_lookback_days),
        "shuffle_iterations": int(args.shuffle_iterations),
        "news_artifact": str(args.news_artifact),
        "status_scope": "diagnostic_only_robustness_v2_search",
        "row_artifacts": row_artifacts,
        "ranked_variants": ranked,
        "evaluation": evaluations,
        "decision": {
            "promote_to_manifest_ab": False,
            "reason": "No v2 diagnostic variant is promotable until stage0 scorecard and falsification proxies clear together.",
        },
    }
    report_path = output_dir / "m3_3_robustness_v2_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 robustness v2 Stage 0 report to {report_path}")
    print(json.dumps({"ranked_variants": ranked}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
