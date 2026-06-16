from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
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
from enhengclaw.quant_research.hypothesis_batch import _compute_hypothesis_candidate_spec_hash  # noqa: E402
from enhengclaw.quant_research.multiplier_overlay import overlay_table_for_id  # noqa: E402
from enhengclaw.quant_research.onchain_m3_2_features import (  # noqa: E402
    DEFAULT_MF13_TRON_FLOW_IMPULSE_OVERLAY_ID,
)


ARTIFACT_FAMILY = "mf13_tron_regime_gate_ab_diagnostic"
CONTRACT_VERSION = "quant_mf13_tron_regime_gate_ab_diagnostic.v1"
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

OVERLAY_SPEC = {
    "overlay_id": DEFAULT_MF13_TRON_FLOW_IMPULSE_OVERLAY_ID,
    "candidate_id": "xs_alpha_ontology_v6_lsk3_g_mf13_tron_flow_impulse_overlay_v1_h10d",
    "base_mechanism_id": "xs_alpha_ontology_v6_lsk3_g_mf13_tron_flow_impulse_overlay_v1",
    "manifest_contract_tag": "alpha_ontology_v6_lsk3_g_mf13_tron_flow_impulse_overlay_v1_h10d",
    "mechanism_text": (
        "stacked on top of alpha_ontology_regime_gating_v2. When extreme USDT_TRX flow-impulse "
        "states cross confirm/hard thresholds, the portfolio applies an extra throttle of 0.90 / 0.75; "
        "calm days leave the baseline v2 multiplier unchanged."
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run formal A/B for MF-13 TRON regime-aware multiplier overlay."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--run-cycle-when-ready", action="store_true", default=True)
    parser.add_argument("--skip-cycle-run", dest="run_cycle_when_ready", action="store_false")
    parser.add_argument("--force-rerun", action="store_true")
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_validation_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    walk = dict(payload.get("walk_forward_assessment") or {})
    regime = dict(payload.get("regime_holdout") or {})
    regimes = []
    for item in regime.get("regimes") or []:
        regimes.append(
            {
                "regime_id": item.get("regime_id"),
                "median_oos_sharpe": item.get("median_oos_sharpe"),
                "positive": item.get("positive"),
                "window_count": item.get("window_count"),
            }
        )
    return {
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
        "regimes": regimes,
    }


def _extract_execution_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    test_metrics = dict(payload.get("test_metrics") or {})
    execution_stress = dict(payload.get("execution_stress") or {})
    stress_test_metrics = dict(execution_stress.get("test_metrics") or {})
    return {
        "test_net_return": test_metrics.get("net_return"),
        "test_sharpe": test_metrics.get("sharpe"),
        "test_max_drawdown": test_metrics.get("max_drawdown"),
        "test_turnover": test_metrics.get("turnover"),
        "test_gross_return_before_costs": test_metrics.get("gross_return_before_costs"),
        "stress_test_net_return": stress_test_metrics.get("net_return"),
        "stress_test_sharpe": stress_test_metrics.get("sharpe"),
        "stress_test_max_drawdown": stress_test_metrics.get("max_drawdown"),
        "stress_test_turnover": stress_test_metrics.get("turnover"),
        "execution_stress_passed": execution_stress.get("passed"),
        "execution_stress_walk_forward_median_oos_sharpe": execution_stress.get("walk_forward_median_oos_sharpe"),
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
        "baseline_experiment_status": baseline_metrics.get("experiment_status"),
        "candidate_experiment_status": candidate_metrics.get("experiment_status"),
    }


def _compare_execution_metrics(*, baseline_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "test_net_return",
        "test_sharpe",
        "test_max_drawdown",
        "test_turnover",
        "stress_test_net_return",
        "stress_test_sharpe",
        "stress_test_max_drawdown",
        "stress_test_turnover",
        "execution_stress_walk_forward_median_oos_sharpe",
    ):
        lhs = baseline_metrics.get(key)
        rhs = candidate_metrics.get(key)
        out[f"delta_{key}"] = None if lhs is None or rhs is None else float(rhs) - float(lhs)
    out["baseline_execution_stress_passed"] = baseline_metrics.get("execution_stress_passed")
    out["candidate_execution_stress_passed"] = candidate_metrics.get("execution_stress_passed")
    return out


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
    with run_log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=1800,
        )
    if completed.returncode != 0:
        log_tail = run_log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        raise RuntimeError(
            "MF13 TRON regime gate candidate cycle failed:\n"
            f"log_path: {run_log_path}\n\nlog_tail:\n{log_tail}"
        )


def _resolve_candidate_validation_path(*, as_of: str, candidate_id: str, overlay_id: str) -> Path | None:
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
        strategy_id = str(spec_payload.get("strategy_id") or "")
        profile_constraints = dict(spec_payload.get("profile_constraints") or {})
        spec_overlay_id = str(profile_constraints.get("position_multiplier_overlay_id") or "")
        if (
            experiment_id == f"{as_of}-{candidate_id}"
            or strategy_id == candidate_id
            or spec_overlay_id == overlay_id
        ):
            candidates.append((validation_path.stat().st_mtime, validation_path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _build_candidate_manifest_payload(
    *,
    baseline_manifest: dict[str, Any],
    overlay_id: str,
    candidate_id: str,
    base_mechanism_id: str,
    manifest_contract_tag: str,
    mechanism_text: str,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = f"quant_cross_sectional_hypothesis_batch_manifest.{manifest_contract_tag}"
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = (
        "M3.2 MF-13 TRON overlay test. Same v6_h10d score and portfolio construction as "
        "v6_lsk3_g_v2_h10d; only the position_multiplier_overlay_id is swapped."
    )
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = BASELINE_MANIFEST_PATH.name
    lineage["overlay_id"] = overlay_id
    lineage["method"] = (
        "M3.2 MF-13 TRON overlay test: keep v6_h10d score fixed, keep W3.5 v2 regime gate as base, "
        f"and swap the position_multiplier_overlay_id to {overlay_id}."
    )
    lineage["sub_path"] = "M3.2 MF13_TRON regime gate"

    entry = payload["entries"][0]
    entry["candidate_id"] = candidate_id
    entry["base_mechanism_id"] = base_mechanism_id
    entry["profile_constraints"]["position_multiplier_overlay_id"] = overlay_id
    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = candidate_id
    thesis["thesis_family"] = f"hypothesis_{candidate_id}"
    thesis["market_mechanism"] = "M3.2 MF-13 TRON market-state gate: " + mechanism_text
    thesis["directional_claim"] = (
        "Identical score function and long-short top-3 perp construction as v6_lsk3_g_v2_h10d. "
        f"Only the position multiplier overlay changes to {overlay_id}. "
        "Claim is falsified if the overlay fails to improve walk-forward / regime-holdout trade-offs "
        "relative to the baseline active alternative."
    )
    thesis["factor_formula"] = str(thesis.get("factor_formula") or "").replace(
        "regime_gating_v2_multiplier(t)",
        f"{overlay_id}_multiplier(t)",
    )
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


def _overlay_distribution(table: dict[str, float]) -> dict[str, float | int | None]:
    if not table:
        return {
            "n_dates": 0,
            "multiplier_min": None,
            "multiplier_max": None,
            "multiplier_mean": None,
            "fraction_at_full": None,
            "fraction_below_0_95": None,
        }
    import pandas as pd

    series = pd.Series(list(table.values()), dtype="float64")
    return {
        "n_dates": int(series.shape[0]),
        "multiplier_min": float(series.min()),
        "multiplier_max": float(series.max()),
        "multiplier_mean": float(series.mean()),
        "fraction_at_full": float((series >= 0.999).mean()),
        "fraction_below_0_95": float((series < 0.95).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline_manifest = _load_json(BASELINE_MANIFEST_PATH)
    baseline_payload = _load_json(BASELINE_VALIDATION_REPORT_PATH)
    baseline_metrics = _extract_validation_metrics(baseline_payload)
    baseline_execution_metrics = _extract_execution_metrics(baseline_payload)

    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "mf13_tron_regime_gate_ab_diagnostic.json")

    overlay_id = str(OVERLAY_SPEC["overlay_id"])
    overlay_table = overlay_table_for_id(overlay_id)
    manifest_path = report_dir / f"generated_manifest_{OVERLAY_SPEC['candidate_id']}.json"
    manifest_payload = _build_candidate_manifest_payload(
        baseline_manifest=baseline_manifest,
        overlay_id=overlay_id,
        candidate_id=str(OVERLAY_SPEC["candidate_id"]),
        base_mechanism_id=str(OVERLAY_SPEC["base_mechanism_id"]),
        manifest_contract_tag=str(OVERLAY_SPEC["manifest_contract_tag"]),
        mechanism_text=str(OVERLAY_SPEC["mechanism_text"]),
    )
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    candidate_report: dict[str, Any] = {
        "overlay_id": overlay_id,
        "candidate_id": OVERLAY_SPEC["candidate_id"],
        "base_mechanism_id": OVERLAY_SPEC["base_mechanism_id"],
        "manifest_contract_tag": OVERLAY_SPEC["manifest_contract_tag"],
        "candidate_manifest_path": str(manifest_path),
        "overlay_table_size": int(len(overlay_table)),
        "overlay_distribution": _overlay_distribution(overlay_table),
        "verification_status": "pending",
        "cycle_verdict": "pending",
    }
    if overlay_table:
        candidate_report["overlay_preview"] = [
            {"decision_date_utc": key, "multiplier": overlay_table[key]}
            for key in list(sorted(overlay_table))[-5:]
        ]

    if not args.run_cycle_when_ready:
        candidate_report["verification_status"] = "history_ready_cycle_skipped"
        candidate_report["cycle_verdict"] = "not_run"
    else:
        validation_path = _resolve_candidate_validation_path(
            as_of=str(args.as_of),
            candidate_id=str(OVERLAY_SPEC["candidate_id"]),
            overlay_id=overlay_id,
        )
        if args.force_rerun or validation_path is None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                temp_manifest_path = Path(tmp_dir) / manifest_path.name
                temp_manifest_path.write_text(
                    json.dumps(manifest_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                _run_candidate_cycle(
                    as_of=str(args.as_of),
                    target_horizon_bars=int(args.target_horizon_bars),
                    manifest_path=temp_manifest_path,
                )
            validation_path = _resolve_candidate_validation_path(
                as_of=str(args.as_of),
                candidate_id=str(OVERLAY_SPEC["candidate_id"]),
                overlay_id=overlay_id,
            )
        if validation_path is None:
            raise FileNotFoundError(
                "unable to resolve candidate validation report after cycle run for "
                f"candidate_id={OVERLAY_SPEC['candidate_id']!r} overlay_id={overlay_id!r}"
            )

        payload = _load_json(validation_path)
        candidate_metrics = _extract_validation_metrics(payload)
        candidate_execution_metrics = _extract_execution_metrics(payload)
        candidate_report.update(
            {
                "verification_status": "completed",
                "cycle_verdict": _compare_metrics(
                    baseline_metrics=baseline_metrics,
                    candidate_metrics=candidate_metrics,
                )["cycle_verdict"],
                "candidate_validation_report_path": str(validation_path),
                "candidate_metrics": candidate_metrics,
                "candidate_execution_metrics": candidate_execution_metrics,
                "comparison": _compare_metrics(
                    baseline_metrics=baseline_metrics,
                    candidate_metrics=candidate_metrics,
                ),
                "execution_metric_comparison": _compare_execution_metrics(
                    baseline_metrics=baseline_execution_metrics,
                    candidate_metrics=candidate_execution_metrics,
                ),
            }
        )

    report_payload: dict[str, Any] = {
        "verification_status": "completed",
        "artifact_family": ARTIFACT_FAMILY,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "baseline_validation_report_path": str(BASELINE_VALIDATION_REPORT_PATH),
        "baseline_metrics": baseline_metrics,
        "baseline_execution_metrics": baseline_execution_metrics,
        "input_watermarks": {
            "as_of": str(args.as_of),
            "target_horizon_bars": int(args.target_horizon_bars),
        },
        "candidate": candidate_report,
    }
    with_evidence_metadata(
        report_payload,
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        produced_at_utc=report_payload["generated_at_utc"],
    )
    output_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
