from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import tempfile
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
from enhengclaw.quant_research.stablecoin_regime import (  # noqa: E402
    DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
    DEFAULT_STABLECOIN_OVERLAY_ID,
    DEFAULT_STABLECOIN_OVERLAY_V2_ID,
    DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    compute_stablecoin_exchange_absorption_overlay_v1,
    compute_stablecoin_issuance_velocity_overlay_v1,
    compute_stablecoin_issuance_velocity_overlay_v2,
    compute_stablecoin_whale_to_exchange_stress_overlay_v1,
    stablecoin_overlay_summary,
)


ARTIFACT_FAMILY = "stablecoin_overlay_cycle_increment_diagnostic"
CONTRACT_VERSION = "quant_stablecoin_overlay_cycle_increment_diagnostic.v1"
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
DEFAULT_CANDIDATE_ID = "xs_alpha_ontology_v6_lsk3_g_stablecoin_v1_h10d"
DEFAULT_BASE_MECHANISM_ID = "xs_alpha_ontology_v6_lsk3_g_stablecoin_v1"
DEFAULT_MANIFEST_CONTRACT_TAG = "alpha_ontology_v6_lsk3_g_stablecoin_v1_h10d"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify whether the M3.2 stablecoin overlay shows cycle-layer increment."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument(
        "--overlay-id",
        choices=(
            DEFAULT_STABLECOIN_OVERLAY_ID,
            DEFAULT_STABLECOIN_OVERLAY_V2_ID,
            DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
            DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
        ),
        default=DEFAULT_STABLECOIN_OVERLAY_V2_ID,
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--run-cycle-when-ready", action="store_true", default=True)
    parser.add_argument("--skip-cycle-run", dest="run_cycle_when_ready", action="store_false")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Rerun the candidate cycle even if an experiment already exists on disk.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = str(args.as_of)
    candidate_id, base_mechanism_id, manifest_contract_tag = _candidate_identity_for_overlay(args.overlay_id)
    baseline_manifest = _load_json(BASELINE_MANIFEST_PATH)
    baseline_metrics = _extract_validation_metrics(_load_json(BASELINE_VALIDATION_REPORT_PATH))
    overlay_summary = stablecoin_overlay_summary(overlay_id=args.overlay_id)
    overlay_table = _overlay_table_for_id(args.overlay_id)

    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / f"{args.overlay_id}_cycle_increment_diagnostic.json")
    manifest_output_path = report_dir / f"generated_manifest_{candidate_id}.json"

    candidate_manifest = _build_candidate_manifest_payload(
        baseline_manifest=baseline_manifest,
        overlay_id=args.overlay_id,
        candidate_id=candidate_id,
        base_mechanism_id=base_mechanism_id,
        manifest_contract_tag=manifest_contract_tag,
    )
    manifest_output_path.write_text(json.dumps(candidate_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    overlay_ready = bool(overlay_summary.get("history_ready")) and bool(overlay_table)
    report_payload: dict[str, Any] = {
        "verification_status": "pending",
        "cycle_verdict": "pending",
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "baseline_validation_report_path": str(BASELINE_VALIDATION_REPORT_PATH),
        "baseline_metrics": baseline_metrics,
        "candidate_overlay_id": args.overlay_id,
        "candidate_manifest_path": str(manifest_output_path),
        "candidate_candidate_id": candidate_id,
        "overlay_table_size": int(len(overlay_table)),
        "overlay_ready": overlay_ready,
        "overlay_summary": overlay_summary,
        "input_watermarks": {
            "as_of": as_of,
            "target_horizon_bars": int(args.target_horizon_bars),
            "baseline_candidate_id": "xs_alpha_ontology_v6_lsk3_g_v2_h10d",
        },
        "upstream_versions": {
            "baseline_manifest_contract_version": baseline_manifest.get("contract_version"),
            "overlay_contract_version": overlay_summary.get("contract_version"),
            "oneoff_runner_path": str(ONEOFF_RUNNER_PATH),
        },
    }

    if not overlay_ready:
        report_payload.update(
            {
                "verification_status": "insufficient_history",
                "cycle_verdict": "not_testable",
                "reason": (
                    "stablecoin overlay history is not ready yet; current overlay table is empty, "
                    "so running the candidate now would fail open to multiplier=1.0 and be "
                    "non-informative for cycle-layer increment."
                ),
                "would_fail_open_to_baseline": True,
                "recommended_next_step": (
                    "wait for the M3.2 async bootstrap to materialize enough complete multi-token "
                    "full-day rows, then rerun this diagnostic."
                ),
            }
        )
        _write_report(output_path=output_path, payload=report_payload)
        print(json.dumps(report_payload, indent=2, sort_keys=True))
        return 0

    if not args.run_cycle_when_ready:
        report_payload.update(
            {
                "verification_status": "history_ready_cycle_skipped",
                "cycle_verdict": "not_run",
                "reason": "overlay history is ready, but cycle run was skipped by flag.",
            }
        )
        _write_report(output_path=output_path, payload=report_payload)
        print(json.dumps(report_payload, indent=2, sort_keys=True))
        return 0

    candidate_validation_path = _resolve_candidate_validation_path(
        as_of=as_of,
        candidate_id=candidate_id,
        overlay_id=args.overlay_id,
    )
    if args.force_rerun or candidate_validation_path is None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_manifest_path = Path(tmp_dir) / manifest_output_path.name
            temp_manifest_path.write_text(
                json.dumps(candidate_manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=temp_manifest_path,
            )
        candidate_validation_path = _resolve_candidate_validation_path(
            as_of=as_of,
            candidate_id=candidate_id,
            overlay_id=args.overlay_id,
        )
    if candidate_validation_path is None:
        raise FileNotFoundError(
            "unable to resolve candidate validation report after cycle run for "
            f"candidate_id={candidate_id!r} overlay_id={args.overlay_id!r}"
        )

    candidate_metrics = _extract_validation_metrics(_load_json(candidate_validation_path))
    baseline_execution_metrics = _extract_execution_metrics(_load_json(BASELINE_VALIDATION_REPORT_PATH))
    candidate_execution_metrics = _extract_execution_metrics(_load_json(candidate_validation_path))
    comparison = _compare_metrics(baseline_metrics=baseline_metrics, candidate_metrics=candidate_metrics)
    report_payload.update(
        {
            "verification_status": "completed",
            "cycle_verdict": comparison["cycle_verdict"],
            "candidate_validation_report_path": str(candidate_validation_path),
            "candidate_metrics": candidate_metrics,
            "baseline_execution_metrics": baseline_execution_metrics,
            "candidate_execution_metrics": candidate_execution_metrics,
            "execution_metric_comparison": _compare_execution_metrics(
                baseline_metrics=baseline_execution_metrics,
                candidate_metrics=candidate_execution_metrics,
            ),
            "comparison": comparison,
            "would_fail_open_to_baseline": False,
            "force_rerun": bool(args.force_rerun),
        }
    )
    _write_report(output_path=output_path, payload=report_payload)
    print(json.dumps(report_payload, indent=2, sort_keys=True))
    return 0


def _build_candidate_manifest_payload(
    *,
    baseline_manifest: dict[str, Any],
    overlay_id: str,
    candidate_id: str,
    base_mechanism_id: str,
    manifest_contract_tag: str,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = f"quant_cross_sectional_hypothesis_batch_manifest.{manifest_contract_tag}"
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = (
        "M3.2 first stablecoin issuance/velocity overlay candidate. Same v6_h10d score and "
        "portfolio construction as v6_lsk3_g_v2_h10d; only the position_multiplier_overlay_id "
        f"is swapped to {overlay_id}."
    )
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = BASELINE_MANIFEST_PATH.name
    lineage["overlay_id"] = overlay_id
    lineage["method"] = (
        "M3.2 overlay test: keep v6_h10d score fixed, replace W3.5 regime_gating_v2 overlay with "
        f"{overlay_id} derived from complete prior-day Ethereum USDT/USDC/DAI "
        "daily aggregates."
    )
    lineage["sub_path"] = "M3.2 stablecoin_plumbing"

    entry = payload["entries"][0]
    entry["candidate_id"] = candidate_id
    entry["base_mechanism_id"] = base_mechanism_id
    entry["profile_constraints"]["position_multiplier_overlay_id"] = overlay_id
    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = candidate_id
    thesis["thesis_family"] = f"hypothesis_{candidate_id}"
    thesis["market_mechanism"] = (
        "M3.2 stablecoin issuance / velocity overlay test: universe-wide size multiplier computed from "
        + _overlay_mechanism_text(overlay_id)
    )
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


def _overlay_table_for_id(overlay_id: str) -> dict[str, float]:
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_ID:
        return compute_stablecoin_issuance_velocity_overlay_v1()
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_V2_ID:
        return compute_stablecoin_issuance_velocity_overlay_v2()
    if overlay_id == DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID:
        return compute_stablecoin_exchange_absorption_overlay_v1()
    if overlay_id == DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID:
        return compute_stablecoin_whale_to_exchange_stress_overlay_v1()
    raise ValueError(f"unsupported overlay id: {overlay_id!r}")


def _candidate_identity_for_overlay(overlay_id: str) -> tuple[str, str, str]:
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_ID:
        return (
            DEFAULT_CANDIDATE_ID,
            DEFAULT_BASE_MECHANISM_ID,
            DEFAULT_MANIFEST_CONTRACT_TAG,
        )
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_V2_ID:
        return (
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_v2_h10d",
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_v2",
            "alpha_ontology_v6_lsk3_g_stablecoin_v2_h10d",
        )
    if overlay_id == DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID:
        return (
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_exchange_absorption_v1_h10d",
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_exchange_absorption_v1",
            "alpha_ontology_v6_lsk3_g_stablecoin_exchange_absorption_v1_h10d",
        )
    if overlay_id == DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID:
        return (
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_whale_stress_v1_h10d",
            "xs_alpha_ontology_v6_lsk3_g_stablecoin_whale_stress_v1",
            "alpha_ontology_v6_lsk3_g_stablecoin_whale_stress_v1_h10d",
        )
    raise ValueError(f"unsupported overlay id: {overlay_id!r}")


def _overlay_mechanism_text(overlay_id: str) -> str:
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_ID:
        return (
            "prior-day complete Ethereum stablecoin plumbing aggregates. Expansion regime leaves size at 1.0, "
            "neutral throttles to 0.85, contraction throttles to 0.70."
        )
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_V2_ID:
        return (
            "prior-day complete Ethereum stablecoin plumbing aggregates. v2 leaves open/watch states at 1.0 "
            "and only throttles confirmed contraction states."
        )
    if overlay_id == DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID:
        return (
            "prior-day complete Ethereum stablecoin flow aggregates with PIT-safe address labels. "
            "Only days with sufficient labeled notional coverage are active; drain states throttle when "
            "exchange netflow turns negative under weak issuance."
        )
    if overlay_id == DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID:
        return (
            "prior-day complete Ethereum stablecoin flow aggregates with PIT-safe address labels. "
            "Only days with sufficient labeled notional coverage are active; stress states throttle when "
            "whale-to-exchange flow spikes against negative exchange netflow."
        )
    raise ValueError(f"unsupported overlay id: {overlay_id!r}")


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


def _run_candidate_cycle(*, as_of: str, target_horizon_bars: int, manifest_path: Path) -> None:
    python_exe = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)
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
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "stablecoin overlay candidate cycle failed:\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        )


def _resolve_candidate_validation_path(
    *,
    as_of: str,
    candidate_id: str,
    overlay_id: str,
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
        profile_constraints = dict(spec_payload.get("profile_constraints") or {})
        spec_overlay_id = str(profile_constraints.get("position_multiplier_overlay_id") or "")
        if experiment_id == f"{as_of}-{candidate_id}" or spec_overlay_id == overlay_id:
            candidates.append((validation_path.stat().st_mtime, validation_path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _compare_metrics(*, baseline_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> dict[str, Any]:
    baseline_walk = float(baseline_metrics["walk_forward_median_oos_sharpe"])
    candidate_walk = float(candidate_metrics["walk_forward_median_oos_sharpe"])
    baseline_positive = float(baseline_metrics["positive_regime_fraction"])
    candidate_positive = float(candidate_metrics["positive_regime_fraction"])
    baseline_worst = float(baseline_metrics["worst_regime_median_oos_sharpe"])
    candidate_worst = float(candidate_metrics["worst_regime_median_oos_sharpe"])

    delta_walk = candidate_walk - baseline_walk
    delta_positive = candidate_positive - baseline_positive
    delta_worst = candidate_worst - baseline_worst

    if candidate_metrics.get("regime_holdout_passed") and delta_walk > 0.05:
        verdict = "incremental_positive"
    elif candidate_metrics.get("regime_holdout_passed") and abs(delta_walk) <= 0.05 and delta_positive >= 0 and delta_worst >= 0:
        verdict = "no_material_change"
    elif candidate_metrics.get("regime_holdout_passed") and delta_walk > -0.05 and (delta_positive > 0 or delta_worst > 0):
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
    def _delta(metric_name: str) -> float | None:
        baseline_value = baseline_metrics.get(metric_name)
        candidate_value = candidate_metrics.get(metric_name)
        if baseline_value is None or candidate_value is None:
            return None
        return float(candidate_value) - float(baseline_value)

    return {
        "delta_test_net_return": _delta("test_net_return"),
        "delta_test_sharpe": _delta("test_sharpe"),
        "delta_test_max_drawdown": _delta("test_max_drawdown"),
        "delta_test_turnover": _delta("test_turnover"),
        "delta_stress_test_net_return": _delta("stress_test_net_return"),
        "delta_stress_test_sharpe": _delta("stress_test_sharpe"),
        "delta_stress_test_max_drawdown": _delta("stress_test_max_drawdown"),
        "baseline_execution_stress_passed": baseline_metrics.get("execution_stress_passed"),
        "candidate_execution_stress_passed": candidate_metrics.get("execution_stress_passed"),
    }


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


if __name__ == "__main__":
    raise SystemExit(main())
