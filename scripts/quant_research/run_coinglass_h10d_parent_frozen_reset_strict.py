from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.hypothesis_batch as hb  # noqa: E402
import enhengclaw.quant_research.validation_contract as vc  # noqa: E402
from enhengclaw.ops.evidence_contracts import required_source_commit_sha  # noqa: E402
from enhengclaw.quant_research.derivatives_quality import (  # noqa: E402
    DERIVATIVES_FEATURE_SPECS,
    feature_ready_flag_column as derivatives_feature_ready_flag_column,
    feature_source_flag_column as derivatives_feature_source_flag_column,
    summarize_feature_derivatives_quality,
)
from enhengclaw.quant_research.feature_quality import (  # noqa: E402
    build_feature_quality_frame,
    summarize_feature_quality,
)
from enhengclaw.quant_research.lab import run_quant_experiments_for_strategies  # noqa: E402


AS_OF = "2026-05-04"
TARGET_HORIZON_BARS = 10
CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
DEFAULT_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)
DEFAULT_FROZEN_REPLAY_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_reset_replay_2026-05-04_2026-05-06_01"
)
DEFAULT_STRICT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_frozen_reset_strict_2026-05-04_2026-05-06_01"
)
DEFAULT_JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_frozen_reset_strict_2026-05-06.json"
)
DEFAULT_REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / "coinglass_h10d_parent_frozen_reset_strict_2026-05-06.md"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _feature_dir_name(as_of: str) -> str:
    return f"{as_of}-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"


def _patch_contracts(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    entry: dict[str, Any],
    target_horizon_bars: int,
) -> None:
    contract_version = str(manifest.get("contract_version") or "")
    contract_tag = contract_version.rsplit(".", 1)[-1]
    if not contract_tag:
        raise ValueError(f"could not infer contract tag from {contract_version!r}")
    horizon_id = f"h{target_horizon_bars}d"
    hb.HYPOTHESIS_BATCH_MANIFEST_PATH = manifest_path
    hb.HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION = (
        f"quant_cross_sectional_hypothesis_batch_manifest.{contract_tag}"
    )
    hb.FAST_REJECT_REPORT_CONTRACT_VERSION = f"quant_cross_sectional_fast_reject_report.{contract_tag}"
    hb.STRICT_CANDIDATE_LIST_CONTRACT_VERSION = (
        f"quant_cross_sectional_strict_candidate_list.{contract_tag}"
    )
    hb.STRICT_RESULT_CONTRACT_VERSION = f"quant_cross_sectional_strict_result.{contract_tag}"
    hb.BATCH_SUMMARY_CONTRACT_VERSION = f"quant_cross_sectional_hypothesis_batch_cycle.{contract_tag}"
    hb.HYPOTHESIS_BATCH_SOURCE = f"hypothesis_batch_manifest_{contract_tag}"
    hb.EXPECTED_BASE_MECHANISM_IDS = (str(entry["base_mechanism_id"]),)
    hb.EXPECTED_CANDIDATE_IDS = (str(entry["candidate_id"]),)
    hb.EXPECTED_HORIZON_SPECS = ((horizon_id, target_horizon_bars),)
    hb.EXPECTED_HORIZON_MAP = dict(hb.EXPECTED_HORIZON_SPECS)
    hb.HYPOTHESIS_BATCH_TARGET_HORIZONS = (target_horizon_bars,)
    validation_contract_path = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
    if validation_contract_path.exists():
        vc.VALIDATION_CONTRACT_PATH = validation_contract_path
        validation_payload = _read_json(validation_contract_path)
        vc.VALIDATION_CONTRACT_VERSION = str(
            validation_payload.get("contract_version") or vc.VALIDATION_CONTRACT_VERSION
        )


def _build_derivatives_quality_frame(frame: pd.DataFrame) -> pd.DataFrame:
    base_columns = [
        column
        for column in ("subject", "timestamp_ms", "liquidity_bucket", "usdm_symbol")
        if column in frame.columns
    ]
    quality = frame[base_columns].copy()
    for feature_name, spec in DERIVATIVES_FEATURE_SPECS.items():
        source_field = str(spec["source_field"])
        source_values = pd.to_numeric(
            frame.get(source_field, pd.Series(index=frame.index, dtype="float64")),
            errors="coerce",
        )
        if source_field == "open_interest":
            source_values = source_values.replace(0, pd.NA)
        feature_values = pd.to_numeric(
            frame.get(feature_name, pd.Series(index=frame.index, dtype="float64")),
            errors="coerce",
        )
        quality[derivatives_feature_source_flag_column(feature_name)] = source_values.notna().astype("bool")
        quality[derivatives_feature_ready_flag_column(feature_name)] = feature_values.notna().astype("bool")
    return quality


def _load_frozen_feature_set(
    *,
    replay_root: Path,
    as_of: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], pd.DataFrame]:
    feature_manifest_path = replay_root / "features" / _feature_dir_name(as_of) / "feature_manifest.json"
    features_path = feature_manifest_path.parent / "features.csv.gz"
    dataset_manifest_path = replay_root / "datasets" / f"{as_of}-cross-sectional-daily-1d" / "dataset_manifest.json"
    universe_snapshot_path = replay_root / "universe" / as_of / "universe_snapshot.json"
    if not feature_manifest_path.exists():
        raise FileNotFoundError(f"frozen feature manifest not found: {feature_manifest_path}")
    if not features_path.exists():
        raise FileNotFoundError(f"frozen features not found: {features_path}")
    if not dataset_manifest_path.exists():
        raise FileNotFoundError(f"frozen dataset manifest not found: {dataset_manifest_path}")

    feature_manifest = _read_json(feature_manifest_path)
    dataset_manifest = _read_json(dataset_manifest_path)
    frame = pd.read_csv(features_path, compression="gzip")
    derivatives_quality_frame = _build_derivatives_quality_frame(frame)
    derivatives_feature_quality = summarize_feature_derivatives_quality(
        quality_frame=derivatives_quality_frame,
        interval="1d",
    )
    numeric_feature_columns = list(feature_manifest.get("numeric_feature_columns") or [])
    feature_quality_frame = build_feature_quality_frame(
        feature_frame=frame,
        tracked_feature_columns=numeric_feature_columns,
        derivatives_quality_frame=derivatives_quality_frame,
    )
    feature_quality = summarize_feature_quality(
        feature_quality_frame=feature_quality_frame,
        tracked_feature_columns=numeric_feature_columns,
    )
    feature_set = {
        "shape": str(feature_manifest.get("shape") or "cross_sectional"),
        "dataset_profile": feature_manifest.get("dataset_profile"),
        "dataframe": frame,
        "feature_quality_frame": feature_quality_frame,
        "feature_quality": feature_quality,
        "derivatives_quality_frame": derivatives_quality_frame,
        "derivatives_feature_quality": derivatives_feature_quality,
        "split_realization_contract": dict(feature_manifest.get("split_realization_contract") or {}),
        "dataset_data_readiness": dict(dataset_manifest.get("data_readiness") or {}),
        "dataset_research_dataset": dict(dataset_manifest.get("research_dataset") or {}),
        "feature_admission_policy": dict(feature_manifest.get("feature_admission_policy") or {}),
        "available_numeric_columns": list(feature_manifest.get("available_numeric_columns") or []),
        "numeric_feature_columns": numeric_feature_columns,
        "excluded_numeric_columns": list(feature_manifest.get("excluded_numeric_columns") or []),
        "feature_set_id": str(feature_manifest.get("feature_set_id") or ""),
        "target_horizon_bars": int(
            dict(feature_manifest.get("split_realization_contract") or {}).get("target_horizon_bars")
            or TARGET_HORIZON_BARS
        ),
        "label_contract_id": str(feature_manifest.get("label_contract_id") or hb.DEFAULT_LABEL_CONTRACT_ID),
        "target_column": str(feature_manifest.get("target_column") or "target_execution_up"),
        "forward_return_column": str(
            feature_manifest.get("forward_return_column") or "target_execution_forward_return"
        ),
        "raw_forward_return_column": str(feature_manifest.get("raw_forward_return_column") or ""),
        "dataset_fingerprint": str(
            feature_manifest.get("dataset_fingerprint") or dataset_manifest.get("dataset_fingerprint") or ""
        ),
        "dataset_manifest_path": str(dataset_manifest_path),
        "manifest_path": str(feature_manifest_path),
        "features_path": str(features_path),
        "feature_hash": str(feature_manifest.get("feature_hash") or ""),
        "source_commit_sha": str(feature_manifest.get("source_commit_sha") or ""),
        "universe_definition_id": str(feature_manifest.get("universe_definition_id") or ""),
        "universe_contract_version": str(feature_manifest.get("universe_contract_version") or ""),
        "universe_snapshot_path": str(universe_snapshot_path)
        if universe_snapshot_path.exists()
        else str(feature_manifest.get("universe_snapshot_path") or ""),
        "universe_selection_policy_hash": str(feature_manifest.get("universe_selection_policy_hash") or ""),
    }
    return feature_set, feature_manifest, dataset_manifest, frame


def _load_stage_fast_reject_report(
    *,
    replay_root: Path,
    as_of: str,
    candidate_id: str,
) -> tuple[dict[str, Any], Path]:
    path = replay_root / "hypothesis_batches" / as_of / "families" / candidate_id / "fast_reject_report.json"
    if not path.exists():
        raise FileNotFoundError(f"stage fast-reject report not found: {path}")
    report = _read_json(path)
    report["path"] = str(path)
    if not bool(report.get("fast_reject_passed")):
        raise RuntimeError(f"stage fast-reject report did not pass: {path}")
    return report, path


def _write_batch_summary(
    *,
    strict_root: Path,
    as_of: str,
    manifest: dict[str, Any],
    feature_set: dict[str, Any],
    strict_results: dict[str, Any],
    strict_candidate_list: dict[str, Any],
    source_commit_sha: str,
    compiler_backend: str,
) -> dict[str, Any]:
    cycle_root = strict_root / "hypothesis_batches" / as_of
    payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": _utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_cross_sectional_hypothesis_batch_cycle",
        "contract_version": hb.BATCH_SUMMARY_CONTRACT_VERSION,
        "compiler_backend": compiler_backend,
        "artifacts_root": str(strict_root),
        "batch_manifest_path": str(hb.HYPOTHESIS_BATCH_MANIFEST_PATH),
        "batch_manifest_contract_version": str(manifest.get("contract_version") or ""),
        "dataset_ids": [str(feature_set.get("dataset_id") or "2026-05-04-cross-sectional-daily-1d")],
        "feature_set_ids": [str(feature_set.get("feature_set_id") or "")],
        "candidate_count": 1,
        "candidate_ids": [CANDIDATE_ID],
        "candidate_count_by_horizon": {"h10d": 1},
        "fast_reject_pass_count": 1,
        "fast_reject_pass_candidate_ids": [CANDIDATE_ID],
        "fast_reject_pass_count_by_horizon": {"h10d": 1},
        "fast_reject_pass_count_by_mechanism": {
            str((manifest.get("entries") or [{}])[0].get("base_mechanism_id") or ""): 1
        },
        "blocked_candidate_ids": [],
        "strict_candidate_count": len(strict_results["strict_candidates"]),
        "strict_candidate_ids": [str(item["candidate_id"]) for item in strict_results["strict_candidates"]],
        "strict_survivor_count": len(strict_results["strict_survivors"]),
        "strict_survivor_ids": [str(item["candidate_id"]) for item in strict_results["strict_survivors"]],
        "strict_survivor_count_by_horizon": {
            "h10d": sum(1 for item in strict_results["strict_survivors"] if item.get("horizon_id") == "h10d")
        },
        "strict_candidate_list_path": hb.portable_path(
            Path(str(strict_candidate_list["path"])),
            repo_root=ROOT,
        ),
        "source_commit_sha": source_commit_sha,
        "frozen_reset_feature_matrix": True,
    }
    document = hb._write_evidence(
        path=cycle_root / "batch_summary.json",
        payload=payload,
        evidence_family="quant_cross_sectional_hypothesis_batch_cycle",
        contract_version=hb.BATCH_SUMMARY_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    document["summary_path"] = str(cycle_root / "batch_summary.json")
    return document


def _first_strict_result(strict_root: Path, as_of: str, candidate_id: str) -> dict[str, Any]:
    path = strict_root / "hypothesis_batches" / as_of / "families" / candidate_id / "strict_result.json"
    if not path.exists():
        return {}
    payload = _read_json(path)
    payload["path"] = str(path)
    return payload


def _experiment_summary(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    if not experiments:
        return {}
    experiment = dict(experiments[0])
    validation_report = dict(experiment.get("validation_report") or {})
    alpha_card = dict(experiment.get("alpha_card") or {})
    validation_contract = dict(
        validation_report.get("validation_contract") or alpha_card.get("validation_contract") or {}
    )
    backtest = dict(
        validation_report.get("validation_metrics")
        or alpha_card.get("validation_metrics")
        or validation_report.get("backtest")
        or alpha_card.get("backtest")
        or {}
    )
    test = dict(
        validation_report.get("test_metrics")
        or alpha_card.get("test_metrics")
        or validation_report.get("test_backtest")
        or alpha_card.get("test_backtest")
        or {}
    )
    alpha_experiment_card = dict(
        validation_report.get("alpha_experiment_card")
        or alpha_card.get("alpha_experiment_card")
        or {}
    )
    return {
        "experiment_id": experiment.get("experiment_id"),
        "experiment_status": experiment.get("experiment_status"),
        "alpha_card_path": experiment.get("alpha_card_path"),
        "validation_report_path": experiment.get("validation_report_path"),
        "validation_contract_status": validation_contract.get("status"),
        "validation_contract_blocker_codes": validation_contract.get("blocker_codes"),
        "alpha_experiment_card_status": alpha_experiment_card.get("status"),
        "alpha_experiment_card_go_no_go": alpha_experiment_card.get("go_no_go"),
        "alpha_experiment_card_blocker_codes": alpha_experiment_card.get("blocker_codes"),
        "falsification_status": alpha_card.get("falsification_status")
        or validation_report.get("falsification_status"),
        "credible_research_evidence": alpha_card.get("credible_research_evidence")
        or validation_report.get("credible_research_evidence"),
        "validation_metrics": {
            "net_return": backtest.get("net_return"),
            "sharpe": backtest.get("sharpe"),
            "max_drawdown": backtest.get("max_drawdown"),
        },
        "test_metrics": {
            "net_return": test.get("net_return"),
            "sharpe": test.get("sharpe"),
            "max_drawdown": test.get("max_drawdown"),
        },
    }


def _render_report(payload: dict[str, Any]) -> str:
    stage = dict(payload.get("stage_fast_reject") or {})
    frozen = dict(payload.get("frozen_feature_matrix") or {})
    strict = dict(payload.get("strict_result") or {})
    experiment = dict(payload.get("experiment") or {})
    quality = dict(payload.get("reconstructed_quality_check") or {})
    lines = [
        "# CoinGlass H10D Parent Frozen Reset Strict Validation",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{payload['decision']}`",
        f"- alpha_rerun_allowed: `{payload['alpha_rerun_allowed']}`",
        f"- promotion_allowed: `{payload['promotion_allowed']}`",
        f"- strict_root: `{payload['inputs']['strict_root']}`",
        f"- frozen_replay_root: `{payload['inputs']['frozen_replay_root']}`",
        f"- candidate_id: `{payload['candidate_id']}`",
        "",
        "## Frozen Input",
        "",
        f"- feature_set_id: `{frozen.get('feature_set_id')}`",
        f"- feature_rows: `{frozen.get('feature_rows')}`",
        f"- feature_subject_count: `{frozen.get('feature_subject_count')}`",
        f"- feature_hash: `{frozen.get('feature_hash')}`",
        f"- feature_matrix_sha256: `{frozen.get('feature_matrix_sha256')}`",
        f"- dataset_fingerprint: `{frozen.get('dataset_fingerprint')}`",
        f"- dataset_min_timestamp_utc: `{frozen.get('dataset_min_timestamp_utc')}`",
        f"- dataset_max_timestamp_utc: `{frozen.get('dataset_max_timestamp_utc')}`",
        "",
        "## Fast-Reject Anchor",
        "",
        f"- fast_reject_report_path: `{stage.get('path')}`",
        f"- fast_reject_passed: `{stage.get('fast_reject_passed')}`",
        f"- validation_net_sharpe: `{stage.get('validation_net_return')}` / `{stage.get('validation_sharpe')}`",
        f"- test_net_sharpe: `{stage.get('test_net_return')}` / `{stage.get('test_sharpe')}`",
        f"- blocker_codes: `{stage.get('blocker_codes')}`",
        f"- advisory_codes: `{stage.get('advisory_codes')}`",
        "",
        "## Strict Result",
        "",
        f"- strict_validation_passed: `{strict.get('strict_validation_passed')}`",
        f"- validation_contract_status: `{strict.get('validation_contract_status')}`",
        f"- falsification_status: `{strict.get('falsification_status')}`",
        f"- statistical_falsification_status: `{strict.get('statistical_falsification_status')}`",
        f"- alpha_experiment_card_status: `{strict.get('alpha_experiment_card_status')}`",
        f"- alpha_experiment_card_go_no_go: `{strict.get('alpha_experiment_card_go_no_go')}`",
        f"- credible_research_evidence: `{strict.get('credible_research_evidence')}`",
        f"- strict_result_path: `{strict.get('path')}`",
        "",
        "Experiment summary:",
        "",
        f"- experiment_id: `{experiment.get('experiment_id')}`",
        f"- experiment_status: `{experiment.get('experiment_status')}`",
        f"- alpha_card_path: `{experiment.get('alpha_card_path')}`",
        f"- validation_report_path: `{experiment.get('validation_report_path')}`",
        f"- validation_contract_blocker_codes: `{experiment.get('validation_contract_blocker_codes')}`",
        f"- alpha_experiment_card_blocker_codes: `{experiment.get('alpha_experiment_card_blocker_codes')}`",
        f"- validation_metrics: `{experiment.get('validation_metrics')}`",
        f"- test_metrics: `{experiment.get('test_metrics')}`",
        "",
        "## Quality Reconstruction",
        "",
        f"- derivatives_quality_matches_manifest: `{quality.get('derivatives_quality_matches_manifest')}`",
        f"- max_abs_fraction_delta: `{quality.get('max_abs_fraction_delta')}`",
        f"- mismatches: `{quality.get('mismatches')}`",
        "",
        "## Next Gate",
        "",
        payload["next_gate"],
        "",
    ]
    return "\n".join(lines)


def _quality_check(
    *,
    feature_manifest: dict[str, Any],
    derivatives_feature_quality: dict[str, Any],
) -> dict[str, Any]:
    manifest_quality = dict(feature_manifest.get("derivatives_feature_quality") or {})
    manifest_features = dict(manifest_quality.get("features") or {})
    reconstructed_features = dict(derivatives_feature_quality.get("features") or {})
    mismatches: list[dict[str, Any]] = []
    max_delta = 0.0
    for feature_name in DERIVATIVES_FEATURE_SPECS:
        original = dict(manifest_features.get(feature_name) or {})
        reconstructed = dict(reconstructed_features.get(feature_name) or {})
        for field in ("row_source_fraction", "row_ready_fraction"):
            old_value = original.get(field)
            new_value = reconstructed.get(field)
            if old_value is None and new_value is None:
                continue
            delta = abs(float(new_value or 0.0) - float(old_value or 0.0))
            max_delta = max(max_delta, delta)
            if delta > 1e-12:
                mismatches.append(
                    {
                        "feature": feature_name,
                        "field": field,
                        "manifest": old_value,
                        "reconstructed": new_value,
                        "delta": delta,
                    }
                )
        if int(original.get("subject_ready_count") or 0) != int(
            reconstructed.get("subject_ready_count") or 0
        ):
            mismatches.append(
                {
                    "feature": feature_name,
                    "field": "subject_ready_count",
                    "manifest": original.get("subject_ready_count"),
                    "reconstructed": reconstructed.get("subject_ready_count"),
                    "delta": int(reconstructed.get("subject_ready_count") or 0)
                    - int(original.get("subject_ready_count") or 0),
                }
            )
    return {
        "derivatives_quality_matches_manifest": not mismatches,
        "max_abs_fraction_delta": max_delta,
        "mismatches": mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run strict validation for the CoinGlass reset h10d parent on the frozen reset feature matrix."
    )
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--frozen-replay-root", type=Path, default=DEFAULT_FROZEN_REPLAY_ROOT)
    parser.add_argument("--strict-root", type=Path, default=DEFAULT_STRICT_ROOT)
    parser.add_argument("--target-horizon-bars", type=int, default=TARGET_HORIZON_BARS)
    parser.add_argument("--compiler-backend", default="deterministic")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args(argv)

    manifest_path = args.manifest.expanduser().resolve()
    replay_root = args.frozen_replay_root.expanduser().resolve()
    strict_root = args.strict_root.expanduser().resolve()
    json_out = args.json_out.expanduser().resolve()
    report_out = args.report_out.expanduser().resolve()

    payload: dict[str, Any] = {
        "generated_at_utc": _utc_now(),
        "as_of": args.as_of,
        "candidate_id": CANDIDATE_ID,
        "status": "running",
        "decision": "running",
        "alpha_rerun_allowed": False,
        "promotion_allowed": False,
        "inputs": {
            "manifest_path": str(manifest_path),
            "frozen_replay_root": str(replay_root),
            "strict_root": str(strict_root),
            "json_out": str(json_out),
            "report_out": str(report_out),
        },
    }
    _write_json(json_out, payload)

    try:
        manifest = _read_json(manifest_path)
        entries = list(manifest.get("entries") or [])
        if len(entries) != 1:
            raise ValueError(f"expected one manifest entry, found {len(entries)}")
        entry = dict(entries[0])
        if str(entry.get("candidate_id") or "") != CANDIDATE_ID:
            raise ValueError(f"unexpected candidate_id: {entry.get('candidate_id')!r}")
        if int(entry.get("target_horizon_bars") or 0) != int(args.target_horizon_bars):
            raise ValueError("manifest horizon does not match requested target horizon")
        _patch_contracts(
            manifest_path=manifest_path,
            manifest=manifest,
            entry=entry,
            target_horizon_bars=int(args.target_horizon_bars),
        )
        feature_set, feature_manifest, dataset_manifest, frame = _load_frozen_feature_set(
            replay_root=replay_root,
            as_of=args.as_of,
        )
        stage_report, stage_report_path = _load_stage_fast_reject_report(
            replay_root=replay_root,
            as_of=args.as_of,
            candidate_id=CANDIDATE_ID,
        )
        source_commit_sha = required_source_commit_sha(repo_root=ROOT)
        strict_strategy = hb._materialize_strict_strategy_entry(entry)
        experiments = run_quant_experiments_for_strategies(
            as_of=args.as_of,
            artifacts_root=strict_root,
            strategies=[strict_strategy],
            feature_sets=[feature_set],
            compiler_backend=str(args.compiler_backend),
            source_commit_sha=source_commit_sha,
        )
        cycle_root = strict_root / "hypothesis_batches" / args.as_of
        strict_results = hb._write_strict_results(
            as_of=args.as_of,
            batch_root=cycle_root,
            reports=[stage_report],
            strict_experiments=experiments,
            source_commit_sha=source_commit_sha,
        )
        strict_candidate_list = hb._write_strict_candidate_list(
            path=cycle_root / "strict_candidate_list.json",
            as_of=args.as_of,
            manifest=manifest,
            strict_results=strict_results,
            source_commit_sha=source_commit_sha,
        )
        batch_summary = _write_batch_summary(
            strict_root=strict_root,
            as_of=args.as_of,
            manifest=manifest,
            feature_set=feature_set,
            strict_results=strict_results,
            strict_candidate_list=strict_candidate_list,
            source_commit_sha=source_commit_sha,
            compiler_backend=str(args.compiler_backend),
        )
        strict_result = _first_strict_result(strict_root, args.as_of, CANDIDATE_ID)
        experiment_summary = _experiment_summary(experiments)
        strict_passed = bool(strict_result.get("strict_validation_passed"))
        payload.update(
            {
                "status": "pass_frozen_reset_strict_validation"
                if strict_passed
                else "fail_closed_frozen_reset_strict_validation",
                "decision": "r1_frozen_reset_strict_gate_passed_continue_to_promotion_guard"
                if strict_passed
                else "r1_frozen_reset_fast_reject_passed_but_strict_validation_failed_closed",
                "alpha_rerun_allowed": bool(strict_passed),
                "promotion_allowed": False,
                "source_commit_sha": source_commit_sha,
                "frozen_feature_matrix": {
                    "feature_set_id": feature_set.get("feature_set_id"),
                    "feature_rows": int(len(frame)),
                    "feature_subject_count": int(frame["subject"].nunique()) if "subject" in frame.columns else None,
                    "feature_hash": feature_manifest.get("feature_hash"),
                    "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
                    "dataset_fingerprint": feature_manifest.get("dataset_fingerprint")
                    or dataset_manifest.get("dataset_fingerprint"),
                    "dataset_min_timestamp_utc": dataset_manifest.get("min_timestamp_utc"),
                    "dataset_max_timestamp_utc": dataset_manifest.get("max_timestamp_utc"),
                    "feature_manifest_path": str(Path(str(feature_set["manifest_path"]))),
                    "features_path": str(Path(str(feature_set["features_path"]))),
                    "dataset_manifest_path": str(Path(str(feature_set["dataset_manifest_path"]))),
                },
                "reconstructed_quality_check": _quality_check(
                    feature_manifest=feature_manifest,
                    derivatives_feature_quality=dict(feature_set.get("derivatives_feature_quality") or {}),
                ),
                "stage_fast_reject": {
                    "path": str(stage_report_path),
                    "fast_reject_passed": stage_report.get("fast_reject_passed"),
                    "validation_net_return": dict(stage_report.get("validation_metrics_lite") or {}).get(
                        "net_return"
                    ),
                    "validation_sharpe": dict(stage_report.get("validation_metrics_lite") or {}).get("sharpe"),
                    "test_net_return": dict(stage_report.get("test_metrics_lite") or {}).get("net_return"),
                    "test_sharpe": dict(stage_report.get("test_metrics_lite") or {}).get("sharpe"),
                    "blocker_codes": stage_report.get("blocker_codes"),
                    "advisory_codes": stage_report.get("advisory_codes"),
                },
                "strict_result": strict_result,
                "strict_candidate_list": {
                    "path": str(strict_candidate_list.get("path")),
                    "strict_candidate_count": strict_candidate_list.get("strict_candidate_count"),
                    "strict_survivor_count": strict_candidate_list.get("strict_survivor_count"),
                    "strict_candidates": strict_candidate_list.get("strict_candidates"),
                    "strict_survivors": strict_candidate_list.get("strict_survivors"),
                },
                "batch_summary": {
                    "path": str(batch_summary.get("path") or batch_summary.get("summary_path") or ""),
                    "fast_reject_pass_count": batch_summary.get("fast_reject_pass_count"),
                    "strict_candidate_count": batch_summary.get("strict_candidate_count"),
                    "strict_survivor_count": batch_summary.get("strict_survivor_count"),
                },
                "experiment": experiment_summary,
                "next_gate": "Strict validation passed on the frozen reset feature matrix. Run falsification sidecars, overlay ablation, and promotion guard before any canonical/promotion decision."
                if strict_passed
                else "Strict validation failed on the same frozen reset feature matrix. Keep alpha promotion blocked and inspect validation/falsification blocker codes before attempting optimization.",
            }
        )
    except Exception as exc:  # pragma: no cover - operational script
        payload.update(
            {
                "status": "error",
                "decision": "fail_closed_runner_error",
                "alpha_rerun_allowed": False,
                "promotion_allowed": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "next_gate": "Fix the runner error before interpreting the reset parent alpha.",
            }
        )
        _write_json(json_out, payload)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(_render_report(payload), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1

    _write_json(json_out, payload)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(_render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
