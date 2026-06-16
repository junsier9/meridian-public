from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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


ARTIFACT_FAMILY = "mf13_tron_cross_sectional_gate_increment_diagnostic"
CONTRACT_VERSION = "quant_mf13_tron_cross_sectional_gate_increment_diagnostic.v1"
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
        description="Evaluate MF-13 TRON local cross-sectional gate candidate versus the active v6_h10d baseline."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    parser.add_argument("--force-rerun", action="store_true")
    return parser


def _variant_spec() -> dict[str, Any]:
    return {
        "label": "mf13_tron_impulse_def_beta_v1",
        "candidate_id": "xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d",
        "base_mechanism_id": "xs_alpha_ontology_v13_mf13_tron_impulse_def_beta",
        "model_family": "xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d",
        "manifest_contract_tag": "alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d",
        "required_feature_columns_append": [
            "lead_lag_beta_btc",
            "m3_2_tron_flow_impulse_state",
        ],
        "description": (
            "MF-13 local gate. Keep v6_h10d fixed, but during extreme USDT_TRX flow-impulse "
            "states tilt toward defensive low-beta names inside the score layer."
        ),
        "factor_formula": (
            "raw = v6_h10d_base_raw - 0.030 * activation(m3_2_tron_flow_impulse_state) * "
            "z(lead_lag_beta_btc); final_score = tanh((percentile_rank(raw)-0.5)*1.80)"
        ),
    }


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
            "MF13 TRON cross-sectional gate candidate cycle failed:\n"
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
        "MF-13 TRON local gate test. Keep v6_h10d long-short top-3 perp construction and existing "
        "W3.5 regime overlay fixed; only inject USDT_TRX flow-impulse context into the cross-sectional "
        "beta exposure at the score layer."
    )
    lineage["sub_path"] = "M3.2 MF13_TRON_local_cross_sectional_gate"

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
    if "core_context" not in feature_groups:
        feature_groups.append("core_context")
    entry["feature_groups"] = feature_groups

    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = spec["candidate_id"]
    thesis["thesis_family"] = f"hypothesis_{spec['candidate_id']}"
    thesis["market_mechanism"] = spec["description"]
    thesis["directional_claim"] = (
        "Extreme USDT_TRX flow-impulse states are treated as a localized stablecoin-plumbing trigger. "
        "On those dates, the score should tilt toward defensive low-beta names; the claim fails if the "
        "cycle layer cannot improve or preserve parent trade-offs."
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = _variant_spec()
    baseline_manifest = _load_json(BASELINE_MANIFEST_PATH)
    baseline_payload = _load_json(BASELINE_VALIDATION_REPORT_PATH)
    baseline_metrics = _extract_validation_metrics(baseline_payload)

    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "mf13_tron_cross_sectional_gate_increment_diagnostic.json")

    manifest_path = report_dir / "generated_manifests" / f"{spec['candidate_id']}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = _build_candidate_manifest_payload(baseline_manifest=baseline_manifest, spec=spec)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    validation_path = _resolve_candidate_validation_path(
        as_of=str(args.as_of),
        candidate_id=str(spec["candidate_id"]),
        model_family=str(spec["model_family"]),
    )
    if not args.skip_cycle_run and (args.force_rerun or validation_path is None):
        _run_candidate_cycle(
            as_of=str(args.as_of),
            target_horizon_bars=int(args.target_horizon_bars),
            manifest_path=manifest_path,
        )
        validation_path = _resolve_candidate_validation_path(
            as_of=str(args.as_of),
            candidate_id=str(spec["candidate_id"]),
            model_family=str(spec["model_family"]),
        )

    metrics: dict[str, Any] | None = None
    report_kind = "missing"
    cycle_report_path: str | None = None
    if validation_path is not None and validation_path.exists():
        payload = _load_json(validation_path)
        metrics = _extract_validation_metrics(payload)
        report_kind = "validation"
        cycle_report_path = str(validation_path)
    else:
        fast_reject_path = _resolve_candidate_fast_reject_path(
            as_of=str(args.as_of),
            candidate_id=str(spec["candidate_id"]),
        )
        if fast_reject_path is not None and fast_reject_path.exists():
            payload = _load_json(fast_reject_path)
            metrics = _extract_fast_reject_metrics(payload)
            report_kind = "fast_reject"
            cycle_report_path = str(fast_reject_path)

    report_payload: dict[str, Any] = {
        "artifact_family": ARTIFACT_FAMILY,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "skip_cycle_run": bool(args.skip_cycle_run),
        "force_rerun": bool(args.force_rerun),
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "baseline_validation_report_path": str(BASELINE_VALIDATION_REPORT_PATH),
        "baseline_metrics": baseline_metrics,
        "variant": {
            "label": spec["label"],
            "candidate_id": spec["candidate_id"],
            "model_family": spec["model_family"],
            "description": spec["description"],
            "factor_formula": spec["factor_formula"],
            "required_feature_columns": spec["required_feature_columns_append"],
            "manifest_path": str(manifest_path),
            "cycle_report_path": cycle_report_path,
            "report_kind": report_kind,
            "metrics": metrics,
            "comparison_vs_baseline": (
                _compare_metrics(baseline_metrics=baseline_metrics, candidate_metrics=metrics)
                if metrics is not None
                else None
            ),
        },
    }
    summary_verdict = None
    if metrics is not None:
        summary_verdict = _compare_metrics(baseline_metrics=baseline_metrics, candidate_metrics=metrics)["cycle_verdict"]
    report_payload["summary"] = {
        "candidate_count": 1,
        "cycle_verdict": summary_verdict,
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
