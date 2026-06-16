from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.features import (  # noqa: E402
    build_cross_sectional_feature_bundle,
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)
from enhengclaw.quant_research.lab import _apply_liquid_perp_core_20  # noqa: E402


CONTRACT_VERSION = "quant_v6_h10d_post_pump_short_overlay_diagnostic.v2"
DEFAULT_AS_OF = "2026-05-01"
DEFAULT_TARGET_HORIZON_BARS = 10
BASELINE_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2_h10d.json"
)
BASELINE_CANDIDATE_ID = "xs_alpha_ontology_v6_lsk3_g_v2_h10d"
ONEOFF_RUNNER_PATH = ROOT / "scripts" / "quant_research" / "run_alpha_ontology_horizon_cycle_oneoff.py"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a post_pump_stall short-side overlay on the active v6_h10d strategy."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    return parser


def _features_artifact_path(as_of: str) -> Path:
    artifact = (
        ROOT
        / "artifacts"
        / "quant_research"
        / "features"
        / f"{as_of}-cross-sectional-daily-1d-features-v1"
        / "features.csv.gz"
    )
    if not artifact.exists():
        raise FileNotFoundError(f"features artifact not found: {artifact}")
    return artifact


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {
            "label": "baseline_v6_h10d",
            "candidate_id": BASELINE_CANDIDATE_ID,
            "base_mechanism_id": "xs_alpha_ontology_v6_lsk3_g_v2",
            "model_family": "xs_alpha_ontology_v6_h10d",
            "overlay_weight": 0.0,
            "manifest_path": BASELINE_MANIFEST_PATH,
            "manifest_contract_tag": "alpha_ontology_v6_lsk3_g_v2_h10d",
            "required_feature_columns_append": [],
            "description": "Active alternative baseline: v6_h10d core-20 perp strategy.",
        },
        {
            "label": "overlay_mid_short_w005",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w005_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w005",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005",
            "overlay_weight": 0.05,
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_overlay_mid_w005",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": (
                "Short-side-only SP-K overlay on v6_h10d. Only mid-liquidity names with negative "
                "post_pump_stall_core_score_3d receive extra downward score pressure."
            ),
        },
        {
            "label": "overlay_mid_short_w010",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w010_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w010",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010",
            "overlay_weight": 0.10,
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_overlay_mid_w010",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Same overlay, medium weight.",
        },
        {
            "label": "overlay_mid_short_w015",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w015_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_overlay_mid_w015",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015",
            "overlay_weight": 0.15,
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_overlay_mid_w015",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Same overlay, aggressive weight.",
        },
    ]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validation_report_path(*, as_of: str, candidate_id: str) -> Path:
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "experiments"
        / f"{as_of}-{candidate_id}"
        / "validation_report.json"
    )


def _fast_reject_report_path(*, as_of: str, candidate_id: str) -> Path:
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "hypothesis_batches"
        / as_of
        / "families"
        / candidate_id
        / "fast_reject_report.json"
    )


def _extract_validation_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    walk = dict(payload.get("walk_forward_assessment") or {})
    regime = dict(payload.get("regime_holdout") or {})
    execution = dict(payload.get("execution_stress") or {})
    factor_evidence = dict(payload.get("factor_evidence") or {})
    return {
        "report_kind": "validation",
        "validation_status": str(dict(payload.get("validation_contract") or {}).get("status") or ""),
        "walk_forward_median_oos_sharpe": walk.get("median_oos_sharpe"),
        "walk_forward_loss_window_fraction": walk.get("loss_window_fraction"),
        "walk_forward_window_count": walk.get("window_count"),
        "regime_holdout_passed": regime.get("passed"),
        "positive_regime_fraction": regime.get("positive_regime_fraction"),
        "worst_regime_median_oos_sharpe": regime.get("worst_regime_median_oos_sharpe"),
        "execution_stress_passed": execution.get("passed"),
        "max_trade_participation_rate": execution.get("max_trade_participation_rate"),
        "max_inventory_participation_rate": execution.get("max_inventory_participation_rate"),
        "rank_ic_mean": factor_evidence.get("rank_ic_mean"),
        "rank_ic_positive_rate": factor_evidence.get("rank_ic_positive_rate"),
        "top_minus_bottom_return": factor_evidence.get("top_minus_bottom_return"),
        "validation_net_return": dict(payload.get("validation_metrics") or {}).get("net_return"),
        "validation_sharpe": dict(payload.get("validation_metrics") or {}).get("sharpe"),
        "test_net_return": dict(payload.get("test_metrics") or {}).get("net_return"),
        "test_sharpe": dict(payload.get("test_metrics") or {}).get("sharpe"),
    }


def _extract_fast_reject_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    walk = dict(payload.get("walk_forward_assessment_lite") or {})
    regime = dict(payload.get("regime_holdout_lite") or {})
    factor_evidence = dict(payload.get("factor_evidence_lite") or {})
    validation = dict(payload.get("validation_metrics_lite") or {})
    test = dict(payload.get("test_metrics_lite") or {})
    return {
        "report_kind": "fast_reject",
        "validation_status": "fast_reject_failed" if not payload.get("fast_reject_passed") else "fast_reject_passed",
        "walk_forward_median_oos_sharpe": walk.get("median_oos_sharpe"),
        "walk_forward_loss_window_fraction": walk.get("loss_window_fraction"),
        "walk_forward_window_count": walk.get("window_count"),
        "regime_holdout_passed": regime.get("passed"),
        "positive_regime_fraction": regime.get("positive_regime_fraction"),
        "worst_regime_median_oos_sharpe": regime.get("worst_regime_median_oos_sharpe"),
        "execution_stress_passed": None,
        "max_trade_participation_rate": None,
        "max_inventory_participation_rate": None,
        "rank_ic_mean": factor_evidence.get("rank_ic_mean"),
        "rank_ic_positive_rate": factor_evidence.get("rank_ic_positive_rate"),
        "top_minus_bottom_return": factor_evidence.get("top_minus_bottom_return"),
        "validation_net_return": validation.get("net_return"),
        "validation_sharpe": validation.get("sharpe"),
        "test_net_return": test.get("net_return"),
        "test_sharpe": test.get("sharpe"),
        "fast_reject_passed": payload.get("fast_reject_passed"),
        "blocker_codes": list(payload.get("blocker_codes") or []),
    }


def _compare_metric_dicts(*, baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    comparable_fields = [
        field
        for field in [
            "walk_forward_median_oos_sharpe",
            "walk_forward_loss_window_fraction",
            "positive_regime_fraction",
            "worst_regime_median_oos_sharpe",
            "rank_ic_mean",
            "validation_sharpe",
            "validation_net_return",
            "test_sharpe",
            "test_net_return",
            "max_trade_participation_rate",
        ]
        if baseline.get(field) is not None and candidate.get(field) is not None
    ]
    comparable = bool(comparable_fields)

    def _delta(field: str) -> float | None:
        lhs = candidate.get(field)
        rhs = baseline.get(field)
        if lhs is None or rhs is None:
            return None
        return float(lhs) - float(rhs)

    return {
        "metric_basis": f"{baseline.get('report_kind')}->{candidate.get('report_kind')}",
        "directly_comparable": comparable,
        "comparable_fields": comparable_fields,
        "walk_forward_median_delta": _delta("walk_forward_median_oos_sharpe"),
        "loss_window_fraction_delta": _delta("walk_forward_loss_window_fraction"),
        "positive_regime_fraction_delta": _delta("positive_regime_fraction"),
        "worst_regime_delta": _delta("worst_regime_median_oos_sharpe"),
        "rank_ic_mean_delta": _delta("rank_ic_mean"),
        "validation_sharpe_delta": _delta("validation_sharpe"),
        "validation_net_return_delta": _delta("validation_net_return"),
        "test_sharpe_delta": _delta("test_sharpe"),
        "test_net_return_delta": _delta("test_net_return"),
        "max_trade_participation_delta": _delta("max_trade_participation_rate"),
    }


def _run_candidate_cycle(*, as_of: str, target_horizon_bars: int, manifest_path: Path) -> None:
    command = [
        sys.executable,
        str(ONEOFF_RUNNER_PATH),
        "--as-of",
        as_of,
        "--manifest",
        str(manifest_path),
        "--target-horizon-bars",
        str(target_horizon_bars),
    ]
    subprocess.run(command, cwd=str(ROOT), check=True)


def _build_candidate_manifest_payload(
    *,
    baseline_manifest: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = (
        f"quant_cross_sectional_hypothesis_batch_manifest.{spec['manifest_contract_tag']}"
    )
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = spec["description"]
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = BASELINE_MANIFEST_PATH.name
    lineage["method"] = (
        "SP-K short-overlay test on the active v6_h10d strategy. Keep the core-20 universe, "
        "same regime-gating overlay, same top-3/bottom-3 construction; only add a clipped "
        "mid-liquidity `post_pump_stall_core_score_3d` penalty on short-side candidates."
    )
    lineage["sub_path"] = "SP-K"

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
    thesis["market_mechanism"] = (
        "Attach SP-K as a short-side-only overlay to v6_h10d. The active parent strategy stays on "
        "`liquid_perp_core_20`; only mid-liquidity names with bearish post-pump-stall states are "
        "pushed lower in score, making them more likely to enter the short basket."
    )
    thesis["directional_claim"] = (
        f"Keep the active v6_h10d portfolio construction unchanged and add "
        f"+{float(spec['overlay_weight']):.3f} * min(z(post_pump_stall_core_score_3d), 0) "
        "only on `mid_liquidity` names. Claim fails if walk-forward / regime trade-offs do not improve "
        "versus the active parent strategy."
    )
    thesis["factor_formula"] = (
        "v6_h10d_raw + "
        f"{float(spec['overlay_weight']):.3f}"
        " * I(liquidity_bucket == mid_liquidity) * min(z(post_pump_stall_core_score_3d), 0); "
        "final_score = tanh((percentile_rank(raw)-0.5)*1.80)"
    )
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


def _build_risk_frame(features_artifact: Path, *, target_horizon_bars: int) -> pd.DataFrame:
    panel = pd.read_csv(features_artifact, compression="gzip")
    features = build_cross_sectional_feature_bundle(
        panel,
        target_shift_bars=target_horizon_bars,
    )["dataframe"].copy()
    features = features.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    features["forward_1d_log_return"] = features.groupby("subject", sort=False)["spot_close"].transform(
        lambda close: np.log(close.shift(-1) / close)
    )
    features[f"forward_{target_horizon_bars}d_log_return"] = features.groupby("subject", sort=False)["spot_close"].transform(
        lambda close: np.log(close.shift(-target_horizon_bars) / close)
    )
    return _apply_liquid_perp_core_20(features)


def _short_risk_diagnostic(
    *,
    frame: pd.DataFrame,
    scorer,
    short_count: int,
    target_horizon_bars: int,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["score"] = scorer(filtered)
    rows: list[dict[str, float | str]] = []
    for _, group in filtered.groupby("timestamp_ms"):
        ordered = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        for _, row in ordered.iterrows():
            factor_value = pd.to_numeric(row.get("post_pump_stall_core_score_3d"), errors="coerce")
            rows.append(
                {
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "funding_rate": float(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    else np.nan,
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(
                        pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce"))
                    else np.nan,
                    "post_pump_stall_core_score_3d": float(factor_value) if pd.notna(factor_value) else np.nan,
                }
            )
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "no_rows"}
    funding = pd.to_numeric(basket["funding_rate"], errors="coerce").dropna()
    next_1d = pd.to_numeric(basket["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(
        basket[f"forward_{target_horizon_bars}d_log_return"],
        errors="coerce",
    ).dropna()
    factor = pd.to_numeric(basket["post_pump_stall_core_score_3d"], errors="coerce").dropna()
    bucket = basket["liquidity_bucket"].astype(str)
    return {
        "status": "ok",
        "n_short_rows": int(len(basket)),
        "shorts_receive_funding_fraction": float((funding > 0).mean()) if len(funding) else 0.0,
        "shorts_pay_funding_fraction": float((funding < 0).mean()) if len(funding) else 0.0,
        "mean_funding_rate": float(funding.mean()) if len(funding) else 0.0,
        "median_funding_rate": float(funding.median()) if len(funding) else 0.0,
        "next_1d_adverse_move_mean": float(next_1d.mean()) if len(next_1d) else 0.0,
        "next_1d_adverse_move_p90": float(next_1d.quantile(0.90)) if len(next_1d) else 0.0,
        "next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else 0.0,
        "next_1d_squeeze_gt_10pct_fraction": float((next_1d > 0.10).mean()) if len(next_1d) else 0.0,
        f"next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else 0.0,
        f"next_{target_horizon_bars}d_negative_fraction": float((next_h < 0).mean()) if len(next_h) else 0.0,
        "mid_liquidity_short_fraction": float(bucket.eq("mid_liquidity").mean()) if len(bucket) else 0.0,
        "top_liquidity_short_fraction": float(bucket.eq("top_liquidity").mean()) if len(bucket) else 0.0,
        "overlay_active_short_fraction": float((factor < 0).mean()) if len(factor) else 0.0,
        "mean_post_pump_stall_core_score_3d": float(factor.mean()) if len(factor) else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    baseline_manifest = _load_json(BASELINE_MANIFEST_PATH)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "v6_h10d_post_pump_short_overlay_diagnostic.json")
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    specs = _variant_specs()
    report_paths: dict[str, dict[str, str]] = {}
    variant_metrics: dict[str, dict[str, Any]] = {}
    generated_manifests: dict[str, str] = {}

    for spec in specs:
        if spec["label"] == "baseline_v6_h10d":
            manifest_path = spec["manifest_path"]
        else:
            manifest_payload = _build_candidate_manifest_payload(
                baseline_manifest=baseline_manifest,
                spec=spec,
            )
            manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        generated_manifests[spec["label"]] = str(manifest_path)

        validation_path = _validation_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        fast_reject_path = _fast_reject_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        report_paths[spec["label"]] = {
            "validation_report": str(validation_path),
            "fast_reject_report": str(fast_reject_path),
        }

        need_run = (
            spec["label"] != "baseline_v6_h10d"
            and not validation_path.exists()
            and not fast_reject_path.exists()
        )
        if not args.skip_cycle_run and need_run:
            _run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )

        if validation_path.exists():
            variant_metrics[spec["label"]] = _extract_validation_metrics(_load_json(validation_path))
        elif fast_reject_path.exists():
            variant_metrics[spec["label"]] = _extract_fast_reject_metrics(_load_json(fast_reject_path))
        else:
            variant_metrics[spec["label"]] = {"status": "missing_cycle_reports"}

    comparisons_vs_baseline: dict[str, Any] = {}
    baseline_metrics = variant_metrics.get("baseline_v6_h10d", {})
    for spec in specs:
        label = spec["label"]
        if label == "baseline_v6_h10d":
            continue
        candidate_metrics = variant_metrics.get(label, {})
        if "walk_forward_median_oos_sharpe" in baseline_metrics and "walk_forward_median_oos_sharpe" in candidate_metrics:
            comparisons_vs_baseline[label] = _compare_metric_dicts(
                baseline=baseline_metrics,
                candidate=candidate_metrics,
            )

    features_artifact = _features_artifact_path(as_of)
    risk_frame = _build_risk_frame(features_artifact, target_horizon_bars=args.target_horizon_bars)
    risk_diagnostics = {
        "baseline_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v6_h10d_score,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "overlay_mid_short_w005_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "overlay_mid_short_w010_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "overlay_mid_short_w015_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score,
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
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "comparisons_vs_baseline": comparisons_vs_baseline,
        "short_cost_and_squeeze_risk": risk_diagnostics,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
