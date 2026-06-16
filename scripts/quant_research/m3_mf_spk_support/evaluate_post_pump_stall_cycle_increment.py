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
    xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score,
    xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score,
    xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_sp_k_post_pump_stall_cycle_increment.v1"
DEFAULT_AS_OF = "2026-05-01"
DEFAULT_TARGET_HORIZON_BARS = 5
ONEOFF_RUNNER_PATH = ROOT / "scripts" / "quant_research" / "run_alpha_ontology_horizon_cycle_oneoff.py"

LSK3_BASELINE = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
]


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare post_pump_stall cycle candidates against a mid/tail lsk3 baseline."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    return parser


def _variant_specs() -> list[dict[str, Any]]:
    common_groups = ["volatility", "structure", "derivatives", "trend", "volume"]
    common_constraints = {
        "allowed_liquidity_buckets": ["mid_liquidity", "tail_liquidity"],
        "spot_only": False,
        "long_only": False,
        "short_allowed": True,
        "execution_venue": "perp",
        "max_gross_leverage": 1.0,
        "long_leverage": 0.5,
        "short_leverage": 0.5,
        "max_turnover_per_rebalance": 1.0,
        "top_long_count": 3,
        "bottom_short_count": 3,
    }
    return [
        {
            "label": "baseline",
            "candidate_id": "xs_alpha_ontology_spk_lsk3_mid_tail_h5d",
            "base_mechanism_id": "xs_alpha_ontology_spk_lsk3_mid_tail",
            "model_family": "xs_alpha_ontology_spk_lsk3_mid_tail_h5d",
            "required_feature_columns": list(LSK3_BASELINE),
            "profile_constraints": dict(common_constraints),
            "market_mechanism": "lsk3 baseline control on the mid/tail perp universe.",
            "directional_claim": "Use the unchanged lsk3 11-factor cross-sectional score as the control baseline on mid/tail perp names.",
            "factor_formula": (
                "raw = -0.20*z(iv_smooth_60) -0.10*z(rv_5) +0.18*z(dh_60) +0.15*z(dh_5) "
                "-0.07*z(tt_smooth_5) -0.10*z(liquidity_stress_qv_iv) -0.06*z(momentum_decay_5_20) "
                "+0.05*z(taker_imb_dispersion) -0.05*z(quality_funding_oi) "
                "+0.10*z(downside_upside_vol_ratio_30) +0.07*z(funding_basis_residual_implied_repo_30)"
            ),
            "feature_groups": list(common_groups),
        },
        {
            "label": "candidate_v1",
            "candidate_id": "xs_alpha_ontology_spk_post_pump_stall_v1_h5d",
            "base_mechanism_id": "xs_alpha_ontology_spk_post_pump_stall_v1",
            "model_family": "xs_alpha_ontology_spk_post_pump_stall_v1_h5d",
            "required_feature_columns": [*LSK3_BASELINE, "post_pump_stall_core_score_3d"],
            "profile_constraints": dict(common_constraints),
            "market_mechanism": (
                "Mid/tail-alt post-pump stall short alpha stacked on the lsk3 baseline. "
                "Detects upside blow-off followed by failed continuation."
            ),
            "directional_claim": (
                "Add +0.05 * z(post_pump_stall_core_score_3d) so names with lower post-pump stall scores "
                "are pushed toward the short book."
            ),
            "factor_formula": (
                "baseline_lsk3_raw + 0.05*z(post_pump_stall_core_score_3d)"
            ),
            "feature_groups": list(common_groups),
        },
        {
            "label": "candidate_v2_risk_managed",
            "candidate_id": "xs_alpha_ontology_spk_post_pump_stall_v2_h5d",
            "base_mechanism_id": "xs_alpha_ontology_spk_post_pump_stall_v2",
            "model_family": "xs_alpha_ontology_spk_post_pump_stall_v2_h5d",
            "required_feature_columns": [*LSK3_BASELINE, "post_pump_stall_core_score_3d"],
            "profile_constraints": {
                **common_constraints,
                "bottom_short_count": 4,
            },
            "market_mechanism": (
                "Risk-managed SP-K variant. The factor only penalizes bearish post-pump stall names "
                "and does not reward the non-event side for longs."
            ),
            "directional_claim": (
                "Apply the post-pump stall factor only to the bearish tail of the cross-section, "
                "while widening the short basket to 4 names and reducing turnover to lower squeeze risk."
            ),
            "factor_formula": (
                "baseline_lsk3_raw + 0.05*min(z(post_pump_stall_core_score_3d), 0)"
            ),
            "feature_groups": list(common_groups),
        },
    ]


def _build_manifest_payload(*, spec: dict[str, Any], target_horizon_bars: int) -> dict[str, Any]:
    horizon_id = f"h{target_horizon_bars}d"
    thesis_profile = {
        "thesis_id": spec["candidate_id"],
        "thesis_family": f"hypothesis_{spec['candidate_id']}",
        "market_mechanism": spec["market_mechanism"],
        "directional_claim": spec["directional_claim"],
        "universe_rule": {"liquidity_buckets": ["mid_liquidity", "tail_liquidity"]},
        "dataset_profile": "cross_sectional_daily_4h",
        "execution_venue": "perp",
        "requires_derivatives_features": True,
        "minimum_executable_history_days": 180,
        "minimum_executable_coverage_ratio": 0.85,
        "required_feature_columns": list(spec["required_feature_columns"]),
        "factor_formula": spec["factor_formula"],
        "intended_holding_horizon_bars": int(target_horizon_bars),
        "falsification_conditions": [
            "validation_return_negative",
            "walk_forward_median_oos_sharpe_non_positive",
            "regime_holdout_failed",
            "post_pump_stall_h5d_cycle_no_increment_vs_baseline",
        ],
    }
    entry = {
        "candidate_id": spec["candidate_id"],
        "base_mechanism_id": spec["base_mechanism_id"],
        "horizon_id": horizon_id,
        "target_horizon_bars": int(target_horizon_bars),
        "label_contract_id": "forward_return_ranking.v1",
        "enabled": True,
        "shape": "cross_sectional",
        "dataset_profile": "cross_sectional_daily_4h",
        "model_family": spec["model_family"],
        "strategy_profile": "conservative",
        "feature_groups": list(spec["feature_groups"]),
        "required_feature_columns": list(spec["required_feature_columns"]),
        "profile_constraints": dict(spec["profile_constraints"]),
        "universe_filter": {"liquidity_buckets": ["mid_liquidity", "tail_liquidity"]},
        "thesis_profile": thesis_profile,
    }
    entry["spec_hash"] = _compute_hypothesis_candidate_spec_hash(
        candidate_id=str(entry["candidate_id"]),
        base_mechanism_id=str(entry["base_mechanism_id"]),
        horizon_id=str(entry["horizon_id"]),
        target_horizon_bars=int(entry["target_horizon_bars"]),
        label_contract_id=str(entry["label_contract_id"]),
        shape=str(entry["shape"]),
        dataset_profile=str(entry["dataset_profile"]),
        strategy_profile=str(entry["strategy_profile"]),
        universe_filter=dict(entry["universe_filter"]),
        model_family=str(entry["model_family"]),
        feature_groups=list(entry["feature_groups"]),
        required_feature_columns=list(entry["required_feature_columns"]),
        requires_derivatives_features=True,
        profile_constraints=dict(entry["profile_constraints"]),
        thesis_profile=dict(thesis_profile),
    )
    return {
        "contract_version": f"quant_cross_sectional_hypothesis_batch_manifest.{spec['candidate_id']}",
        "lineage": {
            "doc_context_version": "2026-05-01.1",
            "sub_path": "SP-K",
            "method": spec["market_mechanism"],
            "scoring_family": spec["model_family"],
        },
        "entries": [entry],
        "lifecycle": "experimental",
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
        "fast_reject_passed": payload.get("fast_reject_passed"),
        "blocker_codes": list(payload.get("blocker_codes") or []),
        "validation_sharpe_lite": validation.get("sharpe"),
        "validation_net_return_lite": validation.get("net_return"),
        "test_sharpe_lite": test.get("sharpe"),
        "test_net_return_lite": test.get("net_return"),
    }


def _compare_against_baseline(*, baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    def _delta(field: str) -> float | None:
        lhs = candidate.get(field)
        rhs = baseline.get(field)
        if lhs is None or rhs is None:
            return None
        return float(lhs) - float(rhs)

    return {
        "walk_forward_median_delta": _delta("walk_forward_median_oos_sharpe"),
        "loss_window_fraction_delta": _delta("walk_forward_loss_window_fraction"),
        "positive_regime_fraction_delta": _delta("positive_regime_fraction"),
        "worst_regime_delta": _delta("worst_regime_median_oos_sharpe"),
        "rank_ic_mean_delta": _delta("rank_ic_mean"),
        "max_trade_participation_delta": _delta("max_trade_participation_rate"),
    }


def _build_risk_frame(features_artifact: Path) -> pd.DataFrame:
    panel = pd.read_csv(features_artifact, compression="gzip")
    features = build_cross_sectional_feature_bundle(panel, target_shift_bars=5)["dataframe"].copy()
    features = features.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    features["forward_1d_log_return"] = features.groupby("subject", sort=False)["spot_close"].transform(
        lambda close: np.log(close.shift(-1) / close)
    )
    features["forward_5d_log_return"] = features.groupby("subject", sort=False)["spot_close"].transform(
        lambda close: np.log(close.shift(-5) / close)
    )
    return features


def _short_risk_diagnostic(
    *,
    frame: pd.DataFrame,
    scorer,
    short_count: int,
) -> dict[str, Any]:
    filtered = frame.loc[
        frame["perp_execution_eligible"].fillna(False).astype(bool)
        & frame["liquidity_bucket"].isin(["mid_liquidity", "tail_liquidity"])
        & frame["spot_close"].fillna(0.0).gt(0.0)
    ].copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["score"] = scorer(filtered)
    rows: list[dict[str, float]] = []
    for _, group in filtered.groupby("timestamp_ms"):
        ordered = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        for _, row in ordered.iterrows():
            rows.append(
                {
                    "funding_rate": float(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    else np.nan,
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    "forward_5d_log_return": float(pd.to_numeric(row.get("forward_5d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_5d_log_return"), errors="coerce"))
                    else np.nan,
                }
            )
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "no_rows"}
    funding = pd.to_numeric(basket["funding_rate"], errors="coerce").dropna()
    next_1d = pd.to_numeric(basket["forward_1d_log_return"], errors="coerce").dropna()
    next_5d = pd.to_numeric(basket["forward_5d_log_return"], errors="coerce").dropna()
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
        "next_5d_mean": float(next_5d.mean()) if len(next_5d) else 0.0,
        "next_5d_negative_fraction": float((next_5d < 0).mean()) if len(next_5d) else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "post_pump_stall_cycle_increment_diagnostic.json")
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    variants = _variant_specs()
    generated_manifests: dict[str, str] = {}
    metrics: dict[str, dict[str, Any]] = {}
    report_paths: dict[str, dict[str, str]] = {}

    for spec in variants:
        manifest_payload = _build_manifest_payload(spec=spec, target_horizon_bars=args.target_horizon_bars)
        manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        generated_manifests[spec["label"]] = str(manifest_path)
        validation_path = _validation_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        fast_reject_path = _fast_reject_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        report_paths[spec["label"]] = {
            "validation_report": str(validation_path),
            "fast_reject_report": str(fast_reject_path),
        }
        if not args.skip_cycle_run and not validation_path.exists():
            _run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )
        if validation_path.exists():
            metrics[spec["label"]] = _extract_validation_metrics(
                json.loads(validation_path.read_text(encoding="utf-8"))
            )
        elif fast_reject_path.exists():
            metrics[spec["label"]] = _extract_fast_reject_metrics(
                json.loads(fast_reject_path.read_text(encoding="utf-8"))
            )
        else:
            metrics[spec["label"]] = {"status": "missing_cycle_reports"}

    comparisons = {}
    baseline_metrics = metrics.get("baseline", {})
    for label in ("candidate_v1", "candidate_v2_risk_managed"):
        if label in metrics and "walk_forward_median_oos_sharpe" in metrics[label]:
            comparisons[label] = _compare_against_baseline(
                baseline=baseline_metrics,
                candidate=metrics[label],
            )

    features_artifact = _features_artifact_path(as_of)
    risk_frame = _build_risk_frame(features_artifact)
    risk_diagnostics = {
        "baseline_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score,
            short_count=3,
        ),
        "candidate_v1_bottom3": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score,
            short_count=3,
        ),
        "candidate_v2_bottom4": _short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score,
            short_count=4,
        ),
    }

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": int(args.target_horizon_bars),
        "features_artifact": str(features_artifact),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": metrics,
        "comparisons_vs_baseline": comparisons,
        "short_cost_and_squeeze_risk": risk_diagnostics,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
