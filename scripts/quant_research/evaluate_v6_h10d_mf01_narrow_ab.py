from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
import evaluate_v6_h10d_orderbook_short_replacement as mf01_broad  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_v6_h10d_mf01_narrow_ab.v1"
DEFAULT_AS_OF = base_eval.DEFAULT_AS_OF
DEFAULT_TARGET_HORIZON_BARS = base_eval.DEFAULT_TARGET_HORIZON_BARS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate narrow MF-01 landing shapes on top of the active SP-K short-boundary architecture."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
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
            "thesis_market_mechanism": "Active parent strategy without any SP-K or MF-01 boundary logic.",
            "thesis_directional_claim": "Reference baseline only.",
            "thesis_factor_formula": "baseline = v6_h10d_raw",
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Current winning SP-K short-boundary rule without any narrow MF-01 layer.",
            "thesis_market_mechanism": (
                "Winner SP-K boundary architecture: keep the active parent intact and only allow one marginal "
                "mid-liquidity post-pump-stall candidate to replace the weakest short near the cutoff."
            ),
            "thesis_directional_claim": (
                "Reference SP-K winner. Candidate MF-01 landing shapes must beat or at least preserve this profile."
            ),
            "thesis_factor_formula": (
                "stage 1 = baseline bottom-3 shorts; inspect the bottom-6 tail; if a mid-liquidity name has "
                "negative post_pump_stall z-score, it may replace the weakest short."
            ),
        },
        {
            "label": "mf01_spk_confirm_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_spk_confirm_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_spk_confirm_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_spk_confirm_v1",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "mf01_spk_confirmation_score",
            ],
            "description": (
                "Narrow MF-01 confirmation gate: only let an SP-K-style replacement candidate participate when "
                "orderbook fragility confirms the post-pump fade thesis."
            ),
            "flag_column": "mf01_spk_confirmation_flag",
            "thesis_market_mechanism": (
                "Use MF-01 as confirmation, not as a broad replacement engine. The SP-K winner already knows where "
                "to look; MF-01 should only decide whether the candidate is a real thin-book fade rather than just "
                "a generic post-pump stall."
            ),
            "thesis_directional_claim": (
                "The SP-K winner should improve if only MF-01-confirmed post-pump candidates are allowed to cross "
                "the short boundary."
            ),
            "thesis_factor_formula": (
                "same `replace_mid_v1` structure, but replacement candidates are active only when "
                "`mf01_spk_confirmation_score < 0`."
            ),
        },
        {
            "label": "mf01_spk_ss_veto_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_spk_ss_veto_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_spk_ss_veto_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "mf01_spk_selected_short_veto_flag",
            ],
            "description": (
                "Narrow MF-01 selected-short veto: after `replace_mid_v1`, eject already-selected SP-K-style shorts "
                "when the book shows supportive replenishment instead of fragility."
            ),
            "flag_column": "mf01_spk_selected_short_veto_flag",
            "thesis_market_mechanism": (
                "MF-01 should work as a local do-not-short rule only on the names SP-K itself wanted to short. "
                "Supportive replenishment after a post-pump stall is rebound-risk, not continuation-risk."
            ),
            "thesis_directional_claim": (
                "Ejecting already-selected SP-K shorts with supportive replenishment should reduce false-positive "
                "fades without damaging the parent short boundary."
            ),
            "thesis_factor_formula": (
                "stage 1 = `replace_mid_v1`; stage 2 = if an already-selected short has "
                "`mf01_spk_selected_short_veto_flag`, eject it and refill with the nearest non-veto tail candidate."
            ),
        },
        {
            "label": "mf01_post_cascade_guardrail_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_post_cascade_guardrail_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_post_cascade_guardrail_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "mf01_post_cascade_guardrail_flag",
            ],
            "description": (
                "Narrow MF-01 post-cascade guardrail: after `replace_mid_v1`, eject selected shorts that sit in a "
                "same-day downside-shock state with unusually supportive bid-side replenishment."
            ),
            "flag_column": "mf01_post_cascade_guardrail_flag",
            "thesis_market_mechanism": (
                "Post-cascade names can become rebound-risk when bid depth refills aggressively after the shock. "
                "MF-01 should guard the selected short book against fading those rebound windows."
            ),
            "thesis_directional_claim": (
                "Removing selected shorts that carry same-day post-cascade rebound-risk should improve basket quality "
                "or at least protect tails without damaging the healthy parent architecture."
            ),
            "thesis_factor_formula": (
                "stage 1 = `replace_mid_v1`; stage 2 = if a selected short has "
                "`mf01_post_cascade_guardrail_flag`, eject it and refill from the nearest non-guardrail tail candidate."
            ),
        },
    ]


def _build_manifest_payload(*, baseline_manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = (
        f"quant_cross_sectional_hypothesis_batch_manifest.{spec['manifest_contract_tag']}"
    )
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = spec["description"]
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = base_eval.BASELINE_MANIFEST_PATH.name
    lineage["method"] = (
        "MF-01 narrow landing-shape test on top of the active SP-K short-boundary architecture. "
        "Keep the core-20 universe and healthy parent score intact; only let MF-01 act as a local confirmation, "
        "selected-short veto, or post-cascade guardrail."
    )
    lineage["sub_path"] = "SP-L"

    entry = payload["entries"][0]
    entry["candidate_id"] = spec["candidate_id"]
    entry["base_mechanism_id"] = spec["base_mechanism_id"]
    entry["model_family"] = spec["model_family"]
    required = list(entry.get("required_feature_columns") or [])
    for column in list(spec.get("required_feature_columns_append") or []):
        if column not in required:
            required.append(column)
    entry["required_feature_columns"] = required

    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = spec["candidate_id"]
    thesis["thesis_family"] = f"hypothesis_{spec['candidate_id']}"
    thesis["market_mechanism"] = spec["thesis_market_mechanism"]
    thesis["directional_claim"] = spec["thesis_directional_claim"]
    thesis["factor_formula"] = spec["thesis_factor_formula"]
    thesis["required_feature_columns"] = required

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


def _selected_short_flag_hit_summary(
    *,
    frame: pd.DataFrame,
    selected_scorer,
    flag_column: str,
    short_count: int,
    target_horizon_bars: int,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    if flag_column not in filtered.columns:
        return {"status": "missing_flag_column"}
    filtered["score"] = selected_scorer(filtered)
    filtered["flag"] = filtered[flag_column].fillna(False).astype("bool")
    rows: list[dict[str, Any]] = []
    hit_timestamps = 0
    total_timestamps = 0
    for _, group in filtered.groupby("timestamp_ms", sort=False):
        total_timestamps += 1
        shorts = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        if shorts["flag"].any():
            hit_timestamps += 1
        for _, row in shorts.iterrows():
            rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "flag": bool(row.get("flag") or False),
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
    hits = basket.loc[basket["flag"]].copy()
    if hits.empty:
        return {
            "status": "ok",
            "selected_short_rows": int(len(basket)),
            "selected_short_flag_hit_rows": 0,
            "selected_short_flag_hit_fraction": 0.0,
            "selected_short_flag_hit_timestamps": int(hit_timestamps),
            "selected_short_flag_hit_timestamp_fraction": float(hit_timestamps / max(total_timestamps, 1)),
        }
    next_1d = pd.to_numeric(hits["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(hits[f"forward_{target_horizon_bars}d_log_return"], errors="coerce").dropna()
    return {
        "status": "ok",
        "selected_short_rows": int(len(basket)),
        "selected_short_flag_hit_rows": int(len(hits)),
        "selected_short_flag_hit_fraction": float(len(hits) / max(len(basket), 1)),
        "selected_short_flag_hit_timestamps": int(hit_timestamps),
        "selected_short_flag_hit_timestamp_fraction": float(hit_timestamps / max(total_timestamps, 1)),
        "selected_short_flag_hit_subject_count": int(hits["subject"].astype(str).nunique()),
        "selected_short_flag_hit_next_1d_mean": float(next_1d.mean()) if len(next_1d) else None,
        "selected_short_flag_hit_next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else None,
        f"selected_short_flag_hit_next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else None,
    }


def _augment_narrow_mf01_signals(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    supportive_replenishment = (
        pd.to_numeric(out.get("hourly_bar_count"), errors="coerce").fillna(0.0).ge(16.0)
        & pd.to_numeric(out.get("ob_bid_depth_mean_z30"), errors="coerce").gt(0.50)
        & pd.to_numeric(out.get("ob_bid_heavy_share_24h"), errors="coerce").gt(0.60)
        & pd.to_numeric(out.get("ob_imb_mean_24h"), errors="coerce").gt(0.05)
    )
    post_pump_negative = pd.to_numeric(
        out.get("post_pump_stall_core_score_3d"),
        errors="coerce",
    ).fillna(0.0).lt(0.0)
    mid_liquidity = out.get("liquidity_bucket", pd.Series("", index=out.index)).astype(str).eq("mid_liquidity")
    boundary_fragile = out.get(
        "boundary_fragile_orderbook_flag",
        pd.Series(False, index=out.index, dtype="bool"),
    ).fillna(False).astype("bool")
    pump_bid_fail = out.get(
        "pump_bid_replenishment_failure_flag",
        pd.Series(False, index=out.index, dtype="bool"),
    ).fillna(False).astype("bool")
    spk_confirmation_mask = mid_liquidity & post_pump_negative & (boundary_fragile | pump_bid_fail)
    spk_confirmation_score = (
        pd.to_numeric(out.get("boundary_fragile_orderbook_score"), errors="coerce").fillna(0.0)
        + 0.25 * pd.to_numeric(out.get("pump_bid_replenishment_failure_score"), errors="coerce").fillna(0.0)
        - 0.25 * pd.to_numeric(out.get("post_pump_stall_core_score_3d"), errors="coerce").abs().fillna(0.0)
    ).where(spk_confirmation_mask, 0.0)
    downside_shock_guardrail = (
        pd.to_numeric(out.get("hourly_bar_count"), errors="coerce").fillna(0.0).ge(16.0)
        & pd.to_numeric(out.get("pump_return_sigma"), errors="coerce").lt(-2.0)
        & pd.to_numeric(out.get("coinglass_liquidation_imbalance_24h"), errors="coerce").gt(0.15)
    )
    out["mf01_spk_confirmation_flag"] = spk_confirmation_mask.astype("bool")
    out["mf01_spk_confirmation_score"] = pd.to_numeric(spk_confirmation_score, errors="coerce").fillna(0.0)
    out["mf01_spk_selected_short_veto_flag"] = (mid_liquidity & post_pump_negative & supportive_replenishment).astype("bool")
    out["mf01_post_cascade_guardrail_flag"] = (downside_shock_guardrail & supportive_replenishment).astype("bool")
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "v6_h10d_mf01_narrow_ab_diagnostic.json")
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

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

        validation_path = base_eval._validation_report_path(as_of=as_of, candidate_id=str(spec["candidate_id"]))
        fast_reject_path = base_eval._fast_reject_report_path(as_of=as_of, candidate_id=str(spec["candidate_id"]))
        report_paths[label] = {
            "validation_report": str(validation_path),
            "fast_reject_report": str(fast_reject_path),
        }
        need_run = (
            label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
            and not validation_path.exists()
            and not fast_reject_path.exists()
        )
        if not args.skip_cycle_run and need_run:
            base_eval._run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )

        if validation_path.exists():
            variant_metrics[label] = base_eval._extract_validation_metrics(base_eval._load_json(validation_path))
        elif fast_reject_path.exists():
            variant_metrics[label] = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
        else:
            variant_metrics[label] = {"status": "missing_cycle_reports"}

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

    risk_frame, features_artifact = mf01_broad._build_risk_frame(
        as_of=as_of,
        target_horizon_bars=args.target_horizon_bars,
    )
    risk_frame = _augment_narrow_mf01_signals(risk_frame)
    scorer_map = {
        "baseline_v6_h10d": xs_alpha_ontology_v6_h10d_score,
        "replace_mid_v1_no_news": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "mf01_spk_confirm_v1": xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score,
        "mf01_spk_ss_veto_v1": xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score,
        "mf01_post_cascade_guardrail_v1": xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score,
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

    flag_hit_summary = {
        "mf01_spk_ss_veto_v1": _selected_short_flag_hit_summary(
            frame=risk_frame,
            selected_scorer=scorer_map["replace_mid_v1_no_news"],
            flag_column="mf01_spk_selected_short_veto_flag",
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "mf01_post_cascade_guardrail_v1": _selected_short_flag_hit_summary(
            frame=risk_frame,
            selected_scorer=scorer_map["replace_mid_v1_no_news"],
            flag_column="mf01_post_cascade_guardrail_flag",
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
    }

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": int(args.target_horizon_bars),
        "features_artifact": str(features_artifact),
        "baseline_manifest_path": str(base_eval.BASELINE_MANIFEST_PATH),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "comparisons_vs_baseline": comparisons_vs_baseline,
        "comparisons_vs_no_news": comparisons_vs_no_news,
        "selection_change_vs_baseline": selection_vs_baseline,
        "selection_change_vs_no_news": selection_vs_no_news,
        "short_cost_and_squeeze_risk": risk_diagnostics,
        "selected_short_flag_hit_summary": flag_hit_summary,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
