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
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import evaluate_v6_h10d_post_pump_news_veto_ab as news_ab  # noqa: E402
import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score,
    xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_v6_h10d_post_pump_selected_short_news_veto_ab.v1"
DEFAULT_AS_OF = base_eval.DEFAULT_AS_OF
DEFAULT_TARGET_HORIZON_BARS = base_eval.DEFAULT_TARGET_HORIZON_BARS
DEFAULT_NEWS_EFFECTIVE_MODE = news_ab.DEFAULT_NEWS_EFFECTIVE_MODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A/B test selected-short news veto / forced replacement on the active SP-K short-slot rule."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument(
        "--news-effective-mode",
        choices=("t1", "t0"),
        default=DEFAULT_NEWS_EFFECTIVE_MODE,
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    return parser


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {
            "label": "baseline_v6_h10d",
            "candidate_id": base_eval.BASELINE_CANDIDATE_ID,
            "base_mechanism_id": "xs_alpha_ontology_v6_lsk3_g_v2",
            "model_family": "xs_alpha_ontology_v6_h10d",
            "manifest_path": base_eval.BASELINE_MANIFEST_PATH,
            "manifest_contract_tag": "alpha_ontology_v6_lsk3_g_v2_h10d",
            "required_feature_columns_append": [],
            "description": "Active alternative baseline: v6_h10d core-20 perp strategy.",
            "report_root": news_ab.ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Winner SP-K short replacement without a news veto layer.",
            "report_root": news_ab.ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "ss_veto_mini",
            "candidate_id": "xs_alpha_ontology_v6_spk_ss_veto_mini_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_ss_veto_mini",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_ss_veto_mini",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_ss_veto_mini",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_mini_flag",
            ],
            "description": (
                "Start from the `replace_mid_v1` short book, then veto already-selected shorts when the "
                "mini-model news layer says the move is durable repricing rather than hype. Replace the ejected "
                "slot with the nearest non-veto tail candidate, preferring post-pump-stall mid-liquidity names."
            ),
            "report_root": None,
            "news_veto_label": "mini",
        },
        {
            "label": "ss_veto_adjudicated",
            "candidate_id": "xs_alpha_ontology_v6_spk_ss_veto_adjudicated_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_ss_veto_adjudicated",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_ss_veto_adjudicated",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_adjudicated_flag",
            ],
            "description": (
                "Same selected-short veto / forced replacement rule, but use the adjudicated news labels on "
                "the short book itself."
            ),
            "report_root": None,
            "news_veto_label": "adjudicated",
        },
    ]


def _build_manifest_payload(*, baseline_manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    payload = base_eval._build_candidate_manifest_payload(baseline_manifest=baseline_manifest, spec=spec)
    entry = payload["entries"][0]
    feature_groups = [str(item).strip() for item in list(entry.get("feature_groups") or []) if str(item).strip()]
    required_columns = [
        str(item).strip() for item in list(entry.get("required_feature_columns") or []) if str(item).strip()
    ]
    if any(column.startswith("news_short_veto_") for column in required_columns) and "events" not in set(feature_groups):
        feature_groups.append("events")
        entry["feature_groups"] = feature_groups
    thesis = entry.setdefault("thesis_profile", {})
    veto_label = str(spec.get("news_veto_label") or "")
    if veto_label:
        thesis["market_mechanism"] = (
            "Attach SP-K to the active `replace_mid_v1` short book, then inspect the already-selected "
            f"shorts for {veto_label} durable-news flags. If a selected short is vetoed, remove it and fill "
            "the slot with the nearest non-veto tail candidate, preferring post-pump-stall mid-liquidity names."
        )
        thesis["directional_claim"] = (
            "The short-side news layer should work better when applied to names the strategy is actually "
            "shorting, not just to incoming replacement candidates. Claim fails if the selected-short veto "
            "does not improve short-basket economics or if it damages the parent walk-forward profile."
        )
        thesis["factor_formula"] = (
            "stage 1 = `replace_mid_v1`; stage 2 = inspect the selected short basket; if a selected short has "
            f"an active `{veto_label}` veto flag, eject it and fill with the nearest non-veto tail candidate, "
            "preferring post-pump-stall mid-liquidity names."
        )
    entry["thesis_profile"] = thesis
    entry["spec_hash"] = _compute_hypothesis_candidate_spec_hash(
        candidate_id=str(entry["candidate_id"]),
        base_mechanism_id=str(entry["base_mechanism_id"]),
        horizon_id=str(entry["horizon_id"]),
        target_horizon_bars=int(entry["target_horizon_bars"]),
        label_contract_id=str(entry.get("label_contract_id") or ""),
        shape=str(entry["shape"]),
        dataset_profile=str(entry["dataset_profile"]),
        strategy_profile=str(entry["strategy_profile"]),
        universe_filter=dict(entry.get("universe_filter") or {}),
        model_family=str(entry["model_family"]),
        feature_groups=list(entry.get("feature_groups") or []),
        required_feature_columns=list(entry.get("required_feature_columns") or []),
        requires_derivatives_features=bool(thesis.get("requires_derivatives_features")),
        profile_constraints=dict(entry.get("profile_constraints") or {}),
        thesis_profile=dict(thesis),
    )
    return payload


def _selected_short_news_hit_summary(
    *,
    frame: pd.DataFrame,
    selected_scorer,
    news_flag_column: str,
    short_count: int,
    target_horizon_bars: int,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    if news_flag_column not in filtered.columns:
        return {"status": "missing_news_flag_column"}
    filtered["score"] = selected_scorer(filtered)
    filtered["news_flag"] = pd.to_numeric(filtered[news_flag_column], errors="coerce").fillna(0).astype(int)
    rows: list[dict[str, Any]] = []
    hit_timestamps = 0
    total_timestamps = 0
    for _, group in filtered.groupby("timestamp_ms", sort=False):
        total_timestamps += 1
        shorts = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        if shorts["news_flag"].gt(0).any():
            hit_timestamps += 1
        for _, row in shorts.iterrows():
            rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "news_flag": int(row.get("news_flag") or 0),
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(
                        pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce"))
                    else np.nan,
                }
            )
    basket = pd.DataFrame(rows)
    hits = basket.loc[basket["news_flag"] > 0].copy()
    if hits.empty:
        return {
            "status": "ok",
            "selected_short_rows": int(len(basket)),
            "selected_short_news_hit_rows": 0,
            "selected_short_news_hit_fraction": 0.0,
            "selected_short_news_hit_timestamps": int(hit_timestamps),
            "selected_short_news_hit_timestamp_fraction": float(hit_timestamps / max(total_timestamps, 1)),
        }
    next_1d = pd.to_numeric(hits["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(hits[f"forward_{target_horizon_bars}d_log_return"], errors="coerce").dropna()
    return {
        "status": "ok",
        "selected_short_rows": int(len(basket)),
        "selected_short_news_hit_rows": int(len(hits)),
        "selected_short_news_hit_fraction": float(len(hits) / max(len(basket), 1)),
        "selected_short_news_hit_timestamps": int(hit_timestamps),
        "selected_short_news_hit_timestamp_fraction": float(hit_timestamps / max(total_timestamps, 1)),
        "selected_short_news_hit_subject_count": int(hits["subject"].astype(str).nunique()),
        "selected_short_news_hit_next_1d_mean": float(next_1d.mean()) if len(next_1d) else None,
        "selected_short_news_hit_next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else None,
        f"selected_short_news_hit_next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else None,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    news_effective_mode = str(args.news_effective_mode)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    default_report_name = (
        "v6_h10d_post_pump_selected_short_news_veto_ab_diagnostic_t0.json"
        if news_effective_mode == "t0"
        else "v6_h10d_post_pump_selected_short_news_veto_ab_diagnostic.json"
    )
    output_path = args.output_path or (report_dir / default_report_name)
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    augmented_artifacts_root, augmented_features_csv, news_summary = news_ab._prepare_augmented_feature_root(
        as_of=as_of,
        report_dir=report_dir,
        news_effective_mode=news_effective_mode,
    )
    baseline_manifest = base_eval._load_json(base_eval.BASELINE_MANIFEST_PATH)
    specs = _variant_specs()
    variant_metrics: dict[str, dict[str, Any]] = {}
    report_paths: dict[str, dict[str, str]] = {}
    generated_manifests: dict[str, str] = {}

    for spec in specs:
        label = str(spec["label"])
        if label == "baseline_v6_h10d":
            manifest_path = Path(spec["manifest_path"])
        else:
            manifest_payload = _build_manifest_payload(baseline_manifest=baseline_manifest, spec=spec)
            manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        generated_manifests[label] = str(manifest_path)

        artifacts_root = Path(spec["report_root"]) if spec.get("report_root") else augmented_artifacts_root
        report_paths[label] = {"artifacts_root": str(artifacts_root)}
        need_run = (
            label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
            and not news_ab._validation_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
            and not news_ab._fast_reject_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
        )
        if not args.skip_cycle_run and need_run:
            news_ab._run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
                artifacts_root=artifacts_root,
            )
        metrics, paths = news_ab._load_variant_metrics(
            as_of=as_of,
            candidate_id=str(spec["candidate_id"]),
            artifacts_root=artifacts_root,
        )
        variant_metrics[label] = metrics
        report_paths[label].update(paths)

    baseline_metrics = variant_metrics.get("baseline_v6_h10d", {})
    no_news_metrics = variant_metrics.get("replace_mid_v1_no_news", {})
    comparisons_vs_baseline: dict[str, Any] = {}
    comparisons_vs_no_news: dict[str, Any] = {}
    for spec in specs:
        label = str(spec["label"])
        if label != "baseline_v6_h10d":
            comparisons_vs_baseline[label] = base_eval._compare_metric_dicts(
                baseline=baseline_metrics,
                candidate=variant_metrics.get(label, {}),
            )
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}:
            comparisons_vs_no_news[label] = base_eval._compare_metric_dicts(
                baseline=no_news_metrics,
                candidate=variant_metrics.get(label, {}),
            )

    risk_frame = base_eval._build_risk_frame(
        augmented_features_csv,
        target_horizon_bars=args.target_horizon_bars,
    )
    scorer_map = {
        "baseline_v6_h10d": xs_alpha_ontology_v6_h10d_score,
        "replace_mid_v1_no_news": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "ss_veto_mini": xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score,
        "ss_veto_adjudicated": xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score,
    }
    risk_diagnostics: dict[str, Any] = {}
    selection_vs_baseline: dict[str, Any] = {}
    selection_vs_no_news: dict[str, Any] = {}
    for label, scorer in scorer_map.items():
        risk_diagnostics[f"{label}_bottom3"] = base_eval._short_risk_diagnostic(
            frame=risk_frame,
            scorer=scorer,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        )
        if label != "baseline_v6_h10d":
            selection_vs_baseline[label] = base_eval._selection_change_diagnostic(
                frame=risk_frame,
                baseline_scorer=scorer_map["baseline_v6_h10d"],
                candidate_scorer=scorer,
                long_count=3,
                short_count=3,
                target_horizon_bars=args.target_horizon_bars,
            )
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}:
            selection_vs_no_news[label] = base_eval._selection_change_diagnostic(
                frame=risk_frame,
                baseline_scorer=scorer_map["replace_mid_v1_no_news"],
                candidate_scorer=scorer,
                long_count=3,
                short_count=3,
                target_horizon_bars=args.target_horizon_bars,
            )

    selected_short_news_hit = {
        "mini": _selected_short_news_hit_summary(
            frame=risk_frame,
            selected_scorer=scorer_map["replace_mid_v1_no_news"],
            news_flag_column="news_short_veto_mini_flag",
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "adjudicated": _selected_short_news_hit_summary(
            frame=risk_frame,
            selected_scorer=scorer_map["replace_mid_v1_no_news"],
            news_flag_column="news_short_veto_adjudicated_flag",
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
    }
    boundary_diff_summary = news_ab._news_veto_boundary_diff_summary(risk_frame)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "news_effective_mode": news_effective_mode,
        "target_horizon_bars": int(args.target_horizon_bars),
        "augmented_artifacts_root": str(augmented_artifacts_root),
        "augmented_features_artifact": str(augmented_features_csv),
        "baseline_manifest_path": str(base_eval.BASELINE_MANIFEST_PATH),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "comparisons_vs_baseline": comparisons_vs_baseline,
        "comparisons_vs_no_news": comparisons_vs_no_news,
        "selection_change_vs_baseline": selection_vs_baseline,
        "selection_change_vs_no_news": selection_vs_no_news,
        "short_cost_and_squeeze_risk": risk_diagnostics,
        "selected_short_news_hit_summary": selected_short_news_hit,
        "news_veto_panel_summary": news_summary,
        "news_veto_boundary_diff_summary": boundary_diff_summary,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
