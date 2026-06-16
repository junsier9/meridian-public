from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata  # noqa: E402
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


ARTIFACT_FAMILY = "stablecoin_flow_interaction_cycle_increment_diagnostic"
CONTRACT_VERSION = "quant_stablecoin_flow_interaction_cycle_increment_diagnostic.v1"
DEFAULT_AS_OF = "2026-04-29"
DEFAULT_TARGET_HORIZON_BARS = 10
BASELINE_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2_h10d.json"
)
BASELINE_VALIDATION_REPORT_PATH = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "experiments"
    / f"{DEFAULT_AS_OF}-xs_alpha_ontology_v6_lsk3_g_v2_h10d"
    / "validation_report.json"
)
ONEOFF_RUNNER_PATH = ROOT / "scripts" / "quant_research" / "run_alpha_ontology_horizon_cycle_oneoff.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate M3.2 stablecoin flow interaction / score candidates versus the active v6_h10d baseline."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    parser.add_argument("--force-rerun", action="store_true")
    return parser


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {
            "label": "absorption_quote_share_v1",
            "candidate_id": "xs_alpha_ontology_v11_absorb_qshare_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v11_absorb_qshare",
            "model_family": "xs_alpha_ontology_v11_absorb_qshare_h10d",
            "manifest_contract_tag": "alpha_ontology_v11_absorb_qshare_h10d",
            "required_feature_columns_append": [
                "quote_share_change_30d",
                "stablecoin_labeled_coverage_ratio",
                "stablecoin_exchange_netflow_ratio",
                "stablecoin_exchange_absorption_score_v1",
            ],
            "description": (
                "M3.2 interaction candidate A. Keep v6_h10d intact, but in exchange-absorption states "
                "increase the score lift of cross-sectional quote-share gainers."
            ),
            "factor_formula": (
                "raw = v6_h10d_base_raw + 0.035 * activation(absorption_state) * z(quote_share_change_30d); "
                "final_score = tanh((percentile_rank(raw)-0.5)*1.80)"
            ),
        },
        {
            "label": "drain_relative_strength_v1",
            "candidate_id": "xs_alpha_ontology_v11_drain_rs_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v11_drain_rs",
            "model_family": "xs_alpha_ontology_v11_drain_rs_h10d",
            "manifest_contract_tag": "alpha_ontology_v11_drain_rs_h10d",
            "required_feature_columns_append": [
                "relative_strength_20",
                "stablecoin_labeled_coverage_ratio",
                "stablecoin_exchange_netflow_ratio",
                "stablecoin_exchange_absorption_score_v1",
            ],
            "description": (
                "M3.2 interaction candidate B. In stablecoin drain states, penalize recent relative "
                "strength instead of applying a portfolio-level throttle."
            ),
            "factor_formula": (
                "raw = v6_h10d_base_raw - 0.035 * activation(drain_state) * z(relative_strength_20); "
                "final_score = tanh((percentile_rank(raw)-0.5)*1.80)"
            ),
        },
        {
            "label": "flow_blend_v1",
            "candidate_id": "xs_alpha_ontology_v11_flow_blend_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v11_flow_blend",
            "model_family": "xs_alpha_ontology_v11_flow_blend_h10d",
            "manifest_contract_tag": "alpha_ontology_v11_flow_blend_h10d",
            "required_feature_columns_append": [
                "quote_share_change_30d",
                "relative_strength_20",
                "stablecoin_labeled_coverage_ratio",
                "stablecoin_exchange_netflow_ratio",
                "stablecoin_exchange_absorption_score_v1",
                "stablecoin_whale_exchange_stress_score_v1",
            ],
            "description": (
                "M3.2 interaction candidate C. Blend absorption x quote-share, drain x relative-strength "
                "reversal, and whale-stress x mid-liquidity short bias inside the score layer."
            ),
            "factor_formula": (
                "raw = v6_h10d_base_raw + 0.030 * activation(absorption_state) * z(quote_share_change_30d) "
                "- 0.028 * activation(drain_state) * z(relative_strength_20) "
                "- 0.024 * activation(whale_stress_state) * I(mid_liquidity) * "
                "(clip_pos(z(relative_strength_20)) + 0.5*clip_pos(z(quote_share_change_30d))); "
                "final_score = tanh((percentile_rank(raw)-0.5)*1.80)"
            ),
        },
    ]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_validation_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    walk = dict(payload.get("walk_forward_assessment") or {})
    regime = dict(payload.get("regime_holdout") or {})
    return {
        "report_kind": "validation",
        "experiment_status": payload.get("experiment_status"),
        "falsification_status": payload.get("falsification_status"),
        "walk_forward_median_oos_sharpe": walk.get("median_oos_sharpe"),
        "walk_forward_loss_window_fraction": walk.get("loss_window_fraction"),
        "walk_forward_window_count": walk.get("window_count"),
        "walk_forward_passed": walk.get("passed"),
        "regime_holdout_passed": regime.get("passed"),
        "positive_regime_fraction": regime.get("positive_regime_fraction"),
        "worst_regime_median_oos_sharpe": regime.get("worst_regime_median_oos_sharpe"),
        "covered_regime_count": regime.get("covered_regime_count"),
        "test_net_return": dict(payload.get("test_metrics") or {}).get("net_return"),
        "test_sharpe": dict(payload.get("test_metrics") or {}).get("sharpe"),
        "test_max_drawdown": dict(payload.get("test_metrics") or {}).get("max_drawdown"),
        "test_turnover": dict(payload.get("test_metrics") or {}).get("turnover"),
    }


def _extract_fast_reject_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    walk = dict(payload.get("walk_forward_assessment_lite") or {})
    regime = dict(payload.get("regime_holdout_lite") or {})
    test = dict(payload.get("test_metrics_lite") or {})
    return {
        "report_kind": "fast_reject",
        "experiment_status": "fast_reject_failed" if not payload.get("fast_reject_passed") else "fast_reject_passed",
        "falsification_status": None,
        "walk_forward_median_oos_sharpe": walk.get("median_oos_sharpe"),
        "walk_forward_loss_window_fraction": walk.get("loss_window_fraction"),
        "walk_forward_window_count": walk.get("window_count"),
        "walk_forward_passed": walk.get("passed"),
        "regime_holdout_passed": regime.get("passed"),
        "positive_regime_fraction": regime.get("positive_regime_fraction"),
        "worst_regime_median_oos_sharpe": regime.get("worst_regime_median_oos_sharpe"),
        "covered_regime_count": regime.get("covered_regime_count"),
        "test_net_return": test.get("net_return"),
        "test_sharpe": test.get("sharpe"),
        "test_max_drawdown": test.get("max_drawdown"),
        "test_turnover": test.get("turnover"),
        "fast_reject_passed": payload.get("fast_reject_passed"),
        "blocker_codes": list(payload.get("blocker_codes") or []),
    }


def _compare_metrics(*, baseline_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> dict[str, Any]:
    def _to_float(name: str) -> float | None:
        lhs = baseline_metrics.get(name)
        rhs = candidate_metrics.get(name)
        if lhs is None or rhs is None:
            return None
        return float(rhs) - float(lhs)

    delta_walk = _to_float("walk_forward_median_oos_sharpe")
    delta_positive = _to_float("positive_regime_fraction")
    delta_worst = _to_float("worst_regime_median_oos_sharpe")
    if (
        candidate_metrics.get("regime_holdout_passed")
        and delta_walk is not None
        and delta_walk > 0.05
    ):
        verdict = "incremental_positive"
    elif (
        candidate_metrics.get("regime_holdout_passed")
        and delta_walk is not None
        and abs(delta_walk) <= 0.05
        and (delta_positive or 0.0) >= 0.0
        and (delta_worst or 0.0) >= 0.0
    ):
        verdict = "no_material_change"
    elif (
        candidate_metrics.get("regime_holdout_passed")
        and delta_walk is not None
        and delta_walk > -0.05
        and ((delta_positive or 0.0) > 0.0 or (delta_worst or 0.0) > 0.0)
    ):
        verdict = "tradeoff_positive"
    else:
        verdict = "incremental_negative"
    return {
        "cycle_verdict": verdict,
        "delta_walk_forward_median_oos_sharpe": delta_walk,
        "delta_positive_regime_fraction": delta_positive,
        "delta_worst_regime_median_oos_sharpe": delta_worst,
        "delta_test_sharpe": _to_float("test_sharpe"),
        "delta_test_net_return": _to_float("test_net_return"),
        "delta_test_max_drawdown": _to_float("test_max_drawdown"),
        "delta_test_turnover": _to_float("test_turnover"),
        "baseline_experiment_status": baseline_metrics.get("experiment_status"),
        "candidate_experiment_status": candidate_metrics.get("experiment_status"),
    }


def _run_candidate_cycle(*, as_of: str, target_horizon_bars: int, manifest_path: Path) -> None:
    python_exe = Path(sys.executable)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    run_log_path = report_dir / f"{manifest_path.stem}_cycle_runner.log"
    command = [
        str(python_exe),
        str(ONEOFF_RUNNER_PATH),
        "--as-of",
        str(as_of),
        "--manifest",
        str(manifest_path),
        "--target-horizon-bars",
        str(target_horizon_bars),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONWARNINGS", "ignore")
    with run_log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=1800,
            env=env,
        )
    if completed.returncode != 0:
        log_tail = run_log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        raise RuntimeError(
            "stablecoin flow interaction candidate cycle failed:\n"
            f"log_path: {run_log_path}\n\nlog_tail:\n{log_tail}"
        )


def _resolve_candidate_validation_path(
    *,
    as_of: str,
    candidate_id: str,
    model_family: str,
) -> Path | None:
    experiments_root = ROOT / "artifacts" / "quant_research" / "experiments"
    direct_path = experiments_root / f"{as_of}-{candidate_id}" / "validation_report.json"
    if direct_path.exists():
        return direct_path
    candidates: list[tuple[float, Path]] = []
    prefix = f"{as_of}-"
    for experiment_dir in experiments_root.iterdir():
        if not experiment_dir.is_dir() or not experiment_dir.name.startswith(prefix):
            continue
        spec_path = experiment_dir / "experiment_spec.json"
        validation_path = experiment_dir / "validation_report.json"
        if not spec_path.exists() or not validation_path.exists():
            continue
        try:
            spec_payload = _load_json(spec_path)
        except json.JSONDecodeError:
            continue
        experiment_id = str(spec_payload.get("experiment_id") or "")
        spec_model_family = str(spec_payload.get("model_family") or "")
        strategy_id = str(spec_payload.get("strategy_id") or "")
        if (
            experiment_id == f"{as_of}-{candidate_id}"
            or strategy_id == candidate_id
            or spec_model_family == model_family
        ):
            candidates.append((validation_path.stat().st_mtime, validation_path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _resolve_candidate_fast_reject_path(*, as_of: str, candidate_id: str) -> Path | None:
    path = (
        ROOT
        / "artifacts"
        / "quant_research"
        / "hypothesis_batches"
        / as_of
        / "families"
        / candidate_id
        / "fast_reject_report.json"
    )
    return path if path.exists() else None


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
        "M3.2 interaction / score-candidate test. Keep v6_h10d long-short top-3 perp construction and "
        "W3.5 regime overlay fixed; only inject PIT-safe stablecoin flow state into selected cross-sectional "
        "features at the score layer."
    )
    lineage["sub_path"] = "M3.2 interaction_score_candidates"

    entry = payload["entries"][0]
    entry["candidate_id"] = spec["candidate_id"]
    entry["base_mechanism_id"] = spec["base_mechanism_id"]
    entry["model_family"] = spec["model_family"]
    required = list(entry.get("required_feature_columns") or [])
    for column in list(spec.get("required_feature_columns_append") or []):
        if column not in required:
            required.append(column)
    entry["required_feature_columns"] = required
    feature_groups = list(entry.get("feature_groups") or [])
    if any(column.startswith("stablecoin_") for column in required) and "core_context" not in feature_groups:
        feature_groups.append("core_context")
    entry["feature_groups"] = feature_groups

    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = spec["candidate_id"]
    thesis["thesis_family"] = f"hypothesis_{spec['candidate_id']}"
    thesis["market_mechanism"] = spec["description"]
    thesis["directional_claim"] = (
        "Stablecoin flow is not being used as a universe-wide gross throttle here. Instead, it only modulates "
        "specific cross-sectional features on the dates where flow context is informative. Claim fails if cycle "
        "trade-offs remain below the active parent."
    )
    thesis["factor_formula"] = spec["factor_formula"]
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


def _write_report(*, output_path: Path, payload: dict[str, Any]) -> None:
    wrapped = with_evidence_metadata(
        payload,
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(wrapped, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = str(args.as_of)
    baseline_manifest = _load_json(BASELINE_MANIFEST_PATH)
    baseline_metrics = _extract_validation_metrics(_load_json(BASELINE_VALIDATION_REPORT_PATH))

    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "stablecoin_flow_interaction_cycle_diagnostic.json")
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    variants: dict[str, Any] = {}
    verdict_counts: dict[str, int] = {}

    for spec in _variant_specs():
        manifest_payload = _build_candidate_manifest_payload(
            baseline_manifest=baseline_manifest,
            spec=spec,
        )
        manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        validation_path = _resolve_candidate_validation_path(
            as_of=as_of,
            candidate_id=spec["candidate_id"],
            model_family=spec["model_family"],
        )
        fast_reject_path = _resolve_candidate_fast_reject_path(as_of=as_of, candidate_id=spec["candidate_id"])

        if not args.skip_cycle_run and (args.force_rerun or (validation_path is None and fast_reject_path is None)):
            _run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )
            validation_path = _resolve_candidate_validation_path(
                as_of=as_of,
                candidate_id=spec["candidate_id"],
                model_family=spec["model_family"],
            )
            fast_reject_path = _resolve_candidate_fast_reject_path(as_of=as_of, candidate_id=spec["candidate_id"])

        if validation_path is not None:
            candidate_metrics = _extract_validation_metrics(_load_json(validation_path))
            report_path = validation_path
            report_kind = "validation"
        elif fast_reject_path is not None:
            candidate_metrics = _extract_fast_reject_metrics(_load_json(fast_reject_path))
            report_path = fast_reject_path
            report_kind = "fast_reject"
        else:
            raise FileNotFoundError(
                f"no cycle report found for candidate_id={spec['candidate_id']!r} after evaluation"
            )

        comparison = _compare_metrics(
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
        )
        verdict = str(comparison["cycle_verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        variants[spec["label"]] = {
            "candidate_id": spec["candidate_id"],
            "model_family": spec["model_family"],
            "description": spec["description"],
            "factor_formula": spec["factor_formula"],
            "required_feature_columns": list(spec["required_feature_columns_append"]),
            "manifest_path": str(manifest_path),
            "report_kind": report_kind,
            "cycle_report_path": str(report_path),
            "metrics": candidate_metrics,
            "comparison_vs_baseline": comparison,
        }

    payload = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "as_of": as_of,
        "target_horizon_bars": int(args.target_horizon_bars),
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "baseline_validation_report_path": str(BASELINE_VALIDATION_REPORT_PATH),
        "baseline_metrics": baseline_metrics,
        "variants": variants,
        "summary": {
            "candidate_count": len(variants),
            "verdict_counts": verdict_counts,
            "best_walk_forward_candidate": max(
                variants.items(),
                key=lambda item: float(item[1]["metrics"].get("walk_forward_median_oos_sharpe") or float("-inf")),
            )[0]
            if variants
            else None,
        },
        "force_rerun": bool(args.force_rerun),
        "skip_cycle_run": bool(args.skip_cycle_run),
    }
    _write_report(output_path=output_path, payload=payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
