from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import portable_path, read_json, utc_now, write_json
from enhengclaw.quant_research.execution_backtest import filter_cross_sectional_execution_frame
from enhengclaw.quant_research.fixed_set_comparison import (
    extract_period_frame,
    pairwise_comparison,
    performance_summary,
    periods_per_year,
)
from enhengclaw.quant_research.lab import (
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _experiment_directory_name,
    _resolved_execution_cost_models,
    _run_walk_forward,
)
from enhengclaw.quant_research.overlay_ablation import (
    build_overlay_ablation_gate_assessment,
    load_overlay_ablation_contract,
    overlay_ablation_candidate_entries,
    overlay_ablation_variant_entries,
)
from enhengclaw.quant_research.validation_contract import (
    build_regime_holdout_section,
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)


H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
OVERLAY_ABLATION_CONTRACT = load_overlay_ablation_contract()
BOOTSTRAP_SEED = int(dict(OVERLAY_ABLATION_CONTRACT.get("bootstrap") or {}).get("seed", 20260503) or 20260503)
BOOTSTRAP_ITERATIONS = int(dict(OVERLAY_ABLATION_CONTRACT.get("bootstrap") or {}).get("iterations", 4000) or 4000)


def _resolve_repo_path(path_text: str | Path) -> Path:
    candidate = Path(str(path_text))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _load_candidate_artifact(*, entry: dict[str, Any], artifacts_root: Path) -> dict[str, Any]:
    experiment_id = str(entry.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ValueError(f"overlay ablation candidate entry missing experiment_id: {entry}")
    experiment_root = artifacts_root / "experiments" / _experiment_directory_name(experiment_id)
    if not experiment_root.exists():
        raise FileNotFoundError(f"experiment artifact missing: {experiment_root}")
    experiment_spec = dict(read_json(experiment_root / "experiment_spec.json"))
    validation_report = dict(read_json(experiment_root / "validation_report.json"))
    feature_manifest = dict(read_json(_resolve_repo_path(experiment_spec["feature_manifest_path"])))
    return {
        "label": str(entry.get("label") or experiment_id).strip(),
        "role": str(entry.get("role") or "").strip(),
        "experiment_id": experiment_id,
        "experiment_root": experiment_root,
        "experiment_spec": experiment_spec,
        "validation_report": validation_report,
        "feature_manifest": feature_manifest,
    }


def _load_shared_feature_frame(candidate_artifacts: list[dict[str, Any]]) -> pd.DataFrame:
    feature_manifest_paths = {
        str(item["experiment_spec"].get("feature_manifest_path") or "").strip()
        for item in candidate_artifacts
    }
    if len(feature_manifest_paths) != 1:
        raise ValueError(f"overlay ablation expects a shared feature manifest, got: {sorted(feature_manifest_paths)}")
    features_path = _resolve_repo_path(candidate_artifacts[0]["feature_manifest"]["features_path"])
    return pd.read_csv(features_path, low_memory=False)


def _overlay_context(*, experiment_spec: dict[str, Any], feature_manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "features_path": str(feature_manifest.get("features_path") or ""),
        "feature_manifest_path": str(experiment_spec.get("feature_manifest_path") or ""),
        "universe_snapshot_path": str(feature_manifest.get("universe_snapshot_path") or ""),
    }


def _constraints_for_variant(
    *,
    experiment_spec: dict[str, Any],
    feature_manifest: dict[str, Any],
    overlay_id: str | None,
) -> dict[str, Any]:
    constraints = dict(experiment_spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(experiment_spec.get("strategy_profile") or "")
    if overlay_id:
        constraints["position_multiplier_overlay_id"] = str(overlay_id)
    else:
        constraints.pop("position_multiplier_overlay_id", None)
    context = _overlay_context(experiment_spec=experiment_spec, feature_manifest=feature_manifest)
    if any(str(value).strip() for value in context.values()):
        constraints["position_multiplier_overlay_context"] = context
    return constraints


def _recompute_variant(
    *,
    feature_frame: pd.DataFrame,
    candidate_artifact: dict[str, Any],
    overlay_variant: dict[str, Any],
    validation_contract: dict[str, Any],
    base_execution_cost_model: dict[str, Any],
    stress_execution_cost_model: dict[str, Any],
) -> dict[str, Any]:
    spec = candidate_artifact["experiment_spec"]
    feature_manifest = candidate_artifact["feature_manifest"]
    overlay_label = str(overlay_variant.get("label") or "overlay").strip()
    overlay_id_value = overlay_variant.get("overlay_id")
    overlay_id = str(overlay_id_value).strip() if overlay_id_value is not None else None
    frame = _apply_universe_filter(feature_frame, universe_filter=spec.get("universe_filter"))
    constraints = _constraints_for_variant(
        experiment_spec=spec,
        feature_manifest=feature_manifest,
        overlay_id=overlay_id,
    )
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    walk_forward = _run_walk_forward(
        frame=frame,
        shape=str(spec.get("shape") or "cross_sectional"),
        model_family=str(spec["model_family"]),
        feature_columns=list(spec.get("feature_columns") or []),
        constraints=constraints,
        split_realization_contract=dict(spec["split_realization_contract"]),
        target_column=str(spec.get("target_column") or "target_up"),
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=execution_capacity_limits(validation_contract),
        validation_contract=validation_contract,
        model_definition=None,
        include_periods=True,
    )
    period_label = f"{candidate_artifact['label']}__{overlay_label}"
    periods = extract_period_frame(candidate_label=period_label, walk_forward=walk_forward)
    periods_annualization = periods_per_year(
        bar_interval_ms=int(spec["split_realization_contract"]["bar_interval_ms"]),
        evaluation_step_bars=int(spec["split_realization_contract"]["realization_step_bars"]),
    )
    performance = performance_summary(periods["net_period_return"], periods_per_year=periods_annualization)
    loss_period_fraction = float((periods["net_period_return"] < 0.0).mean()) if not periods.empty else 0.0
    regime_holdout = build_regime_holdout_section(walk_forward=walk_forward, contract=validation_contract)
    summary = {
        "candidate_label": candidate_artifact["label"],
        "experiment_id": str(candidate_artifact["experiment_id"]),
        "overlay_label": overlay_label,
        "overlay_id": overlay_id,
        "overlay_role": str(overlay_variant.get("role") or "").strip(),
        "eligible_subject_count": int(frame["subject"].nunique()) if "subject" in frame.columns else 0,
        "walk_forward_median_oos_sharpe": float(walk_forward.get("median_oos_sharpe") or 0.0),
        "walk_forward_window_count": int(walk_forward.get("window_count") or 0),
        "regime_holdout_passed": bool(regime_holdout.get("passed")),
        "worst_regime_median_oos_sharpe": float(regime_holdout.get("worst_regime_median_oos_sharpe") or 0.0),
        "positive_regime_fraction": float(regime_holdout.get("positive_regime_fraction") or 0.0),
        "full_oos_period_count": int(len(periods)),
        "full_oos_start_utc": str(periods["timestamp_utc"].iloc[0]) if not periods.empty else None,
        "full_oos_end_utc": str(periods["timestamp_utc"].iloc[-1]) if not periods.empty else None,
        "full_oos_cumulative_net_return": float(performance["net_return"]),
        "full_oos_period_sharpe": float(performance["sharpe"]),
        "full_oos_max_drawdown": float(performance["max_drawdown"]),
        "full_oos_loss_period_fraction": float(loss_period_fraction),
        "full_oos_mean_period_return": float(periods["net_period_return"].mean()) if not periods.empty else 0.0,
        "full_oos_turnover_total": float(periods["turnover"].sum()) if not periods.empty else 0.0,
        "full_oos_max_trade_participation_rate": float(periods["trade_participation_rate"].max()) if not periods.empty else 0.0,
        "full_oos_max_inventory_participation_rate": float(periods["inventory_participation_rate"].max()) if not periods.empty else 0.0,
    }
    return {
        "candidate_label": candidate_artifact["label"],
        "overlay_label": overlay_label,
        "walk_forward": walk_forward,
        "periods": periods,
        "periods_per_year": int(periods_annualization),
        "summary": summary,
    }


def _write_markdown(
    *,
    output_path: Path,
    title: str,
    section: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Status: `{section.get('status')}`")
    if section.get("candidate_label"):
        lines.append(f"- Candidate: `{section.get('candidate_label')}`")
    promotion_gate = dict(section.get("promotion_gate") or {})
    if promotion_gate:
        lines.append(f"- Promotion gate passed: `{promotion_gate.get('passed')}`")
        lines.append(f"- Promotion blockers: `{', '.join(promotion_gate.get('blocker_codes') or []) or 'none'}`")
    lines.append("")
    lines.append("| Candidate | Overlay | WF Median | Full OOS CumRet | Full OOS Sharpe | Loss Period Frac | Worst Regime | Max Trade Part. |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in list(section.get("variant_summaries") or []):
        lines.append(
            "| {candidate} | {overlay} | {wf:.3f} | {cum:.3f} | {sharpe:.3f} | {loss:.3f} | {worst:.3f} | {max_trade:.4f} |".format(
                candidate=item["candidate_label"],
                overlay=item["overlay_label"],
                wf=float(item["walk_forward_median_oos_sharpe"]),
                cum=float(item["full_oos_cumulative_net_return"]),
                sharpe=float(item["full_oos_period_sharpe"]),
                loss=float(item["full_oos_loss_period_fraction"]),
                worst=float(item["worst_regime_median_oos_sharpe"]),
                max_trade=float(item["full_oos_max_trade_participation_rate"]),
            )
        )
    if section.get("pairwise_results"):
        lines.append("")
        lines.append("## Pairwise Results")
        lines.append("")
        lines.append("| A | B | N | CumRet Diff | Sharpe Diff | P(A>B CumRet) |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for item in list(section.get("pairwise_results") or []):
            lines.append(
                "| {a} | {b} | {n} | {cum:.3f} | {sharpe:.3f} | {prob:.3f} |".format(
                    a=item["candidate_a"],
                    b=item["candidate_b"],
                    n=int(item["aligned_period_count"]),
                    cum=float(item["observed_cumulative_return_diff"]),
                    sharpe=float(item["observed_sharpe_diff"]),
                    prob=float(dict(item.get("bootstrap") or {}).get("probability_a_beats_b_on_cumulative_return", 0.0) or 0.0),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _candidate_section(
    *,
    candidate_artifact: dict[str, Any],
    all_results: dict[str, dict[str, Any]],
    pairwise_results: list[dict[str, Any]],
    output_root: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    candidate_label = str(candidate_artifact["label"])
    variant_summaries = [
        dict(all_results[f"{candidate_label}__{str(variant.get('label') or '').strip()}"]["summary"])
        for variant in overlay_ablation_variant_entries(contract)
    ]
    candidate_pairwise = [
        dict(item)
        for item in pairwise_results
        if str(item.get("candidate_a") or "").startswith(f"{candidate_label}__")
        and str(item.get("candidate_b") or "").startswith(f"{candidate_label}__")
    ]
    promotion_gate = build_overlay_ablation_gate_assessment(
        variant_summaries=variant_summaries,
        contract=contract,
    )
    section = {
        "contract_version": str(contract.get("contract_version") or ""),
        "status": "computed",
        "candidate_label": candidate_label,
        "experiment_id": str(candidate_artifact["experiment_id"]),
        "overlay_variant_labels": [
            str(item.get("label") or "").strip()
            for item in overlay_ablation_variant_entries(contract)
            if str(item.get("label") or "").strip()
        ],
        "variant_summaries": variant_summaries,
        "pairwise_results": candidate_pairwise,
        "promotion_gate": promotion_gate,
        "artifact_paths": {
            "comparison_json_path": portable_path(output_root / "overlay_ablation.json", repo_root=ROOT),
            "comparison_markdown_path": portable_path(output_root / "overlay_ablation.md", repo_root=ROOT),
            "aligned_period_returns_path": portable_path(output_root / "overlay_ablation_aligned_period_returns.csv", repo_root=ROOT),
            "pairwise_comparisons_path": portable_path(output_root / "overlay_ablation_pairwise_comparisons.csv", repo_root=ROOT),
        },
    }
    return section


def _backfill_candidate_artifacts(*, candidate_artifact: dict[str, Any], section: dict[str, Any]) -> None:
    experiment_root = Path(candidate_artifact["experiment_root"])
    sidecar_json = experiment_root / "overlay_ablation.json"
    sidecar_md = experiment_root / "overlay_ablation.md"
    aligned_csv = experiment_root / "overlay_ablation_aligned_period_returns.csv"
    pairwise_csv = experiment_root / "overlay_ablation_pairwise_comparisons.csv"
    sidecar_section = dict(section)
    sidecar_section["artifact_paths"] = {
        "comparison_json_path": portable_path(sidecar_json, repo_root=ROOT),
        "comparison_markdown_path": portable_path(sidecar_md, repo_root=ROOT),
        "aligned_period_returns_path": portable_path(aligned_csv, repo_root=ROOT),
        "pairwise_comparisons_path": portable_path(pairwise_csv, repo_root=ROOT),
    }
    write_json(sidecar_json, sidecar_section)
    _write_markdown(output_path=sidecar_md, title="Alpha Ontology H10D Overlay Ablation", section=sidecar_section)

    candidate_label = str(candidate_artifact["label"])
    period_frames = []
    for item in list(sidecar_section.get("variant_summaries") or []):
        key = f"{candidate_label}__{item['overlay_label']}"
        period_frame = _BACKFILL_RESULTS[key]["periods"].copy()
        period_frame.rename(columns={"net_period_return": str(item["overlay_label"])}, inplace=True)
        period_frames.append(period_frame[["timestamp_ms", "timestamp_utc", str(item["overlay_label"])]])
    aligned = period_frames[0]
    for frame in period_frames[1:]:
        aligned = aligned.merge(frame, on=["timestamp_ms", "timestamp_utc"], how="outer")
    aligned.sort_values("timestamp_ms").to_csv(aligned_csv, index=False)
    pd.DataFrame.from_records(sidecar_section["pairwise_results"]).to_csv(pairwise_csv, index=False)

    for file_name in ("validation_report.json", "alpha_card.json"):
        path = experiment_root / file_name
        payload = dict(read_json(path))
        payload["overlay_ablation"] = sidecar_section
        payload["updated_at_utc"] = utc_now()
        write_json(path, payload)


_BACKFILL_RESULTS: dict[str, dict[str, Any]] = {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Overlay ablation for v5/v5_rw_bridge h10d candidates.")
    parser.add_argument("--as-of", default="2026-04-29")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    parser.add_argument("--output-date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--candidate-label", default=None)
    parser.add_argument("--variant-label", default=None)
    parser.add_argument("--combine-partials", action="store_true")
    parser.add_argument("--no-backfill", action="store_true")
    args = parser.parse_args(argv)

    validation_contract = dict(read_json(H10D_VALIDATION_CONTRACT_PATH))
    base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()
    candidate_entries = overlay_ablation_candidate_entries(OVERLAY_ABLATION_CONTRACT)
    if args.candidate_label:
        candidate_entries = [
            entry
            for entry in candidate_entries
            if str(entry.get("label") or "").strip() == str(args.candidate_label).strip()
        ]
    variant_entries = overlay_ablation_variant_entries(OVERLAY_ABLATION_CONTRACT)
    if args.variant_label:
        variant_entries = [
            entry
            for entry in variant_entries
            if str(entry.get("label") or "").strip() == str(args.variant_label).strip()
        ]
    if not candidate_entries:
        raise ValueError(f"no overlay ablation candidates matched {args.candidate_label!r}")
    if not variant_entries:
        raise ValueError(f"no overlay ablation variants matched {args.variant_label!r}")
    candidate_artifacts = [
        _load_candidate_artifact(entry=entry, artifacts_root=args.artifacts_root)
        for entry in candidate_entries
    ]
    expected_all_keys = [
        f"{entry.get('label')}__{variant.get('label')}"
        for entry in overlay_ablation_candidate_entries(OVERLAY_ABLATION_CONTRACT)
        for variant in overlay_ablation_variant_entries(OVERLAY_ABLATION_CONTRACT)
    ]

    output_suffix = ""
    if args.candidate_label or args.variant_label:
        output_suffix = "-" + "-".join(
            item
            for item in [
                str(args.candidate_label or "").strip(),
                str(args.variant_label or "").strip(),
            ]
            if item
        )
    output_root = args.artifacts_root / "factor_reports" / (
        f"{args.output_date}-alpha_ontology_h10d_overlay_ablation{output_suffix}"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    aligned_period_returns_path = output_root / "aligned_period_returns.csv"
    pairwise_csv_path = output_root / "pairwise_comparisons.csv"
    summary_json_path = output_root / "summary.json"
    summary_md_path = output_root / "summary.md"

    if args.combine_partials:
        results_by_key: dict[str, dict[str, Any]] = {}
        for key in expected_all_keys:
            partial_summary_path = (
                args.artifacts_root
                / "factor_reports"
                / f"{args.output_date}-alpha_ontology_h10d_overlay_ablation-{key.replace('__', '-')}"
                / "summary.json"
            )
            if not partial_summary_path.exists():
                raise FileNotFoundError(f"missing overlay ablation partial: {partial_summary_path}")
            partial = dict(read_json(partial_summary_path))
            summaries = list(partial.get("variant_summaries") or [])
            if len(summaries) != 1:
                raise ValueError(f"partial {partial_summary_path} expected exactly one variant summary")
            returns_path = _resolve_repo_path(dict(partial.get("artifacts") or {})["aligned_period_returns_csv"])
            returns_frame = pd.read_csv(returns_path)
            if key not in returns_frame.columns:
                raise ValueError(f"partial returns missing {key}: {returns_path}")
            periods = returns_frame[["timestamp_ms", "timestamp_utc", key]].rename(
                columns={key: "net_period_return"}
            )
            results_by_key[key] = {
                "periods": periods,
                "periods_per_year": periods_per_year(
                    bar_interval_ms=86400000,
                    evaluation_step_bars=10,
                ),
                "summary": dict(summaries[0]),
            }
        _BACKFILL_RESULTS.clear()
        _BACKFILL_RESULTS.update(results_by_key)
    else:
        feature_frame = _load_shared_feature_frame(candidate_artifacts)
        results_by_key = {}
        for candidate in candidate_artifacts:
            for variant in variant_entries:
                key = f"{candidate['label']}__{str(variant.get('label') or '').strip()}"
                print(f"[overlay-ablation] recomputing {key}", flush=True)
                results_by_key[key] = _recompute_variant(
                    feature_frame=feature_frame,
                    candidate_artifact=candidate,
                    overlay_variant=variant,
                    validation_contract=validation_contract,
                    base_execution_cost_model=base_execution_cost_model,
                    stress_execution_cost_model=stress_execution_cost_model,
                )
        _BACKFILL_RESULTS.clear()
        _BACKFILL_RESULTS.update(results_by_key)

    variant_summaries = [dict(results_by_key[key]["summary"]) for key in sorted(results_by_key)]
    pairwise_results: list[dict[str, Any]] = []
    ordered_keys = [
        f"{candidate['label']}__{str(variant.get('label') or '').strip()}"
        for candidate in candidate_artifacts
        for variant in variant_entries
    ]
    for pair_index, (key_a, key_b) in enumerate(combinations(ordered_keys, 2)):
        # Cross-candidate pairs are included for diagnostics; promotion uses within-candidate ablations.
        result_a = results_by_key[key_a]
        result_b = results_by_key[key_b]
        pairwise_results.append(
            pairwise_comparison(
                label_a=key_a,
                label_b=key_b,
                periods_a=result_a["periods"],
                periods_b=result_b["periods"],
                periods_per_year=int(result_a["periods_per_year"]),
                iterations=int(args.bootstrap_iterations),
                seed=BOOTSTRAP_SEED + pair_index,
            )
        )

    all_period_frames = []
    for key in ordered_keys:
        frame = results_by_key[key]["periods"].copy()
        frame.rename(columns={"net_period_return": key}, inplace=True)
        all_period_frames.append(frame[["timestamp_ms", "timestamp_utc", key]])
    aligned_period_returns = all_period_frames[0]
    for frame in all_period_frames[1:]:
        aligned_period_returns = aligned_period_returns.merge(frame, on=["timestamp_ms", "timestamp_utc"], how="outer")
    aligned_period_returns.sort_values("timestamp_ms").to_csv(aligned_period_returns_path, index=False)
    pd.DataFrame.from_records(pairwise_results).to_csv(pairwise_csv_path, index=False)

    all_variant_labels = {
        str(item.get("label") or "").strip()
        for item in overlay_ablation_variant_entries(OVERLAY_ABLATION_CONTRACT)
    }
    candidate_sections = []
    for candidate in candidate_artifacts:
        candidate_label = str(candidate["label"])
        available_variant_labels = {
            key.split("__", 1)[1]
            for key in results_by_key
            if key.startswith(f"{candidate_label}__")
        }
        if all_variant_labels.issubset(available_variant_labels):
            candidate_sections.append(
                _candidate_section(
                    candidate_artifact=candidate,
                    all_results=results_by_key,
                    pairwise_results=pairwise_results,
                    output_root=output_root,
                    contract=OVERLAY_ABLATION_CONTRACT,
                )
            )
    summary_payload = {
        "contract_version": str(OVERLAY_ABLATION_CONTRACT.get("contract_version") or ""),
        "analysis_date": str(args.output_date),
        "as_of": str(args.as_of),
        "status": "computed",
        "variant_summaries": variant_summaries,
        "pairwise_results": pairwise_results,
        "candidate_sections": candidate_sections,
        "artifacts": {
            "aligned_period_returns_csv": portable_path(aligned_period_returns_path, repo_root=ROOT),
            "pairwise_comparisons_csv": portable_path(pairwise_csv_path, repo_root=ROOT),
            "summary_md": portable_path(summary_md_path, repo_root=ROOT),
        },
    }
    write_json(summary_json_path, summary_payload)
    _write_markdown(output_path=summary_md_path, title="Alpha Ontology H10D Overlay Ablation", section=summary_payload)

    if not args.no_backfill and candidate_sections:
        for candidate, section in zip(candidate_artifacts, candidate_sections, strict=True):
            _backfill_candidate_artifacts(candidate_artifact=candidate, section=section)

    print(json.dumps(summary_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
