from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.hypothesis_batch as hb  # noqa: E402
from enhengclaw.ops.evidence_contracts import required_source_commit_sha  # noqa: E402
from enhengclaw.quant_research.contracts import portable_path, utc_now, write_json  # noqa: E402
from enhengclaw.quant_research.execution_backtest import filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.lab import (  # noqa: E402
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _backtest_cross_sectional,
    _build_factor_evidence_section,
    _chronological_split,
    _fit_and_score,
    _resolved_execution_cost_models,
)
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    load_validation_contract,
    validation_contract_reference_capital_usd,
)
from scripts.quant_research.run_alpha_ontology_horizon_cycle_oneoff import (  # noqa: E402
    _patch_hypothesis_batch_for_variant,
)


CONTRACT_VERSION = "coinglass_h10d_parent_rebaseline.v1"
DEFAULT_MANIFEST = (
    SRC
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_repo_path(path_text: str | Path) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _candidate_from_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_payload = _read_json(manifest_path)
    entries = list(manifest_payload.get("entries") or [])
    if len(entries) != 1:
        raise ValueError(f"h10d parent rebaseline manifest must contain exactly one entry: {manifest_path}")
    entry = dict(entries[0])
    target_horizon_bars = int(entry.get("target_horizon_bars") or 0)
    if target_horizon_bars != 10:
        raise ValueError(f"expected target_horizon_bars=10, got {target_horizon_bars}")
    contract_version = str(manifest_payload.get("contract_version") or "").strip()
    contract_tag = contract_version.rsplit(".", 1)[-1]
    _patch_hypothesis_batch_for_variant(
        manifest_path=manifest_path,
        contract_tag=contract_tag,
        base_mechanism_id=str(entry["base_mechanism_id"]),
        candidate_id=str(entry["candidate_id"]),
        target_horizon_bars=target_horizon_bars,
    )
    return dict(hb.load_cross_sectional_hypothesis_batch_manifest()["entries"][0])


def _load_feature_frame(
    *,
    feature_manifest: dict[str, Any],
    candidate_entry: dict[str, Any],
    feature_root: Path,
) -> tuple[pd.DataFrame, list[str]]:
    numeric_feature_columns = list(feature_manifest.get("numeric_feature_columns") or [])
    selected_feature_columns = hb._select_candidate_feature_columns(
        candidate_entry=candidate_entry,
        numeric_feature_columns=numeric_feature_columns,
    )
    required_columns = {
        "timestamp_ms",
        "subject",
        "liquidity_bucket",
        "has_perp_as_of",
        "usdm_symbol",
        "perp_execution_eligible",
        "perp_executable_start_ms",
        "perp_close",
        "perp_volume",
        "perp_quote_volume_usd",
        "open_interest_value",
        str(feature_manifest.get("target_column") or "target_up"),
        str(feature_manifest.get("forward_return_column") or "target_forward_return"),
        *selected_feature_columns,
    }
    features_path = _resolve_repo_path(str(feature_manifest.get("features_path") or feature_root / "features.csv.gz"))
    required_columns = {column for column in required_columns if column}
    frame = pd.read_csv(features_path, usecols=lambda column: column in required_columns)
    missing_columns = sorted(column for column in required_columns if column not in frame.columns)
    if missing_columns:
        raise ValueError(f"feature frame missing required columns: {missing_columns}")
    return frame, selected_feature_columns


def _metric_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "net_return": float(metrics.get("net_return", 0.0) or 0.0),
        "sharpe": float(metrics.get("sharpe", 0.0) or 0.0),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
        "turnover": float(metrics.get("turnover", 0.0) or 0.0),
        "trade_count": int(metrics.get("trade_count", 0) or 0),
        "rebalance_count": int(metrics.get("rebalance_count", 0) or 0),
        "max_trade_participation_rate": float(metrics.get("max_trade_participation_rate", 0.0) or 0.0),
        "max_inventory_participation_rate": float(metrics.get("max_inventory_participation_rate", 0.0) or 0.0),
        "data_gap_blockers": list(metrics.get("data_gap_blockers") or []),
    }


def _write_report(*, path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CoinGlass Canonical H10D Parent Rebaseline",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{payload['decision']}`",
        f"- alpha_rerun_allowed: `{payload['alpha_rerun_allowed']}`",
        f"- candidate_id: `{payload['candidate_id']}`",
        f"- spot_ohlc_source: `{payload['canonical_input_policy']['spot_ohlc_source']}`",
        f"- coinglass_spot_ohlc_consumed: `{payload['canonical_input_policy']['coinglass_spot_ohlc_consumed']}`",
        "",
        "## Data Slice",
        "",
        f"- feature_set_id: `{payload['feature_set_id']}`",
        f"- feature_rows: `{payload['feature_rows']}`",
        f"- selected_feature_count: `{payload['selected_feature_count']}`",
        f"- universe_filtered_rows: `{payload['universe_filtered_rows']}`",
        f"- universe_filtered_subject_count: `{payload['universe_filtered_subject_count']}`",
        f"- execution_filtered_rows: `{payload['execution_filtered_rows']}`",
        f"- execution_filtered_subject_count: `{payload['execution_filtered_subject_count']}`",
        f"- split_row_counts: `{payload.get('split_row_counts', {})}`",
        "",
        "## Metrics",
        "",
        f"- validation: `{payload.get('validation_metrics', {})}`",
        f"- test: `{payload.get('test_metrics', {})}`",
        f"- factor_evidence_lite: `{payload.get('factor_evidence_lite', {})}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(payload.get("blocker_codes") or [])
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a fail-closed rebaseline audit, not a promotion run. CoinGlass spot OHLC remains quarantined; "
            "the audit consumes Binance OHLC as canonical and allows CoinGlass only through native USD OI sidecar fields. "
            "Because the canonical parent fails before strict walk-forward promotion evidence, downstream alpha reruns remain blocked.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    as_of = str(args.as_of)
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    manifest_path = args.manifest.expanduser().resolve()
    candidate_entry = _candidate_from_manifest(manifest_path)
    feature_manifest_path = args.feature_manifest.expanduser().resolve()
    feature_manifest = _read_json(feature_manifest_path)
    feature_root = feature_manifest_path.parent
    dataset_manifest_path = _resolve_repo_path(str(feature_manifest.get("dataset_manifest_path") or ""))
    dataset_manifest = _read_json(dataset_manifest_path) if dataset_manifest_path.exists() else {}
    frame0, selected_feature_columns = _load_feature_frame(
        feature_manifest=feature_manifest,
        candidate_entry=candidate_entry,
        feature_root=feature_root,
    )
    strategy_entry = hb._materialize_strict_strategy_entry(candidate_entry)
    constraints = dict(strategy_entry.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(strategy_entry.get("strategy_profile") or "")
    universe_filtered = _apply_universe_filter(
        frame0,
        universe_filter=dict(strategy_entry.get("universe_filter") or {}),
    )
    execution_filtered = filter_cross_sectional_execution_frame(
        frame=universe_filtered,
        constraints=constraints,
    )
    blocker_codes: list[str] = []
    split_row_counts: dict[str, int] = {}
    validation_metrics: dict[str, Any] = {}
    test_metrics: dict[str, Any] = {}
    factor_evidence_lite: dict[str, Any] = {}
    factor_evidence_error = ""

    split = None
    if execution_filtered.empty:
        blocker_codes.append("execution_filtered_frame_empty")
    else:
        split = _chronological_split(
            execution_filtered,
            time_col="timestamp_ms",
            split_realization_contract=dict(feature_manifest.get("split_realization_contract") or {}),
        )
        if split is None:
            blocker_codes.append("unable_to_create_h10d_purged_split")

    if split is not None:
        train_df, validation_df, test_df = split
        split_row_counts = {
            "train": int(len(train_df)),
            "validation": int(len(validation_df)),
            "test": int(len(test_df)),
        }
        prediction_bundle = _fit_and_score(
            model_family=str(candidate_entry["model_family"]),
            shape="cross_sectional",
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            feature_columns=selected_feature_columns,
            target_column=str(feature_manifest.get("target_column") or "target_up"),
        )
        validation_contract = load_validation_contract()
        reference_capital_usd = validation_contract_reference_capital_usd(
            strategy_profile=str(candidate_entry["strategy_profile"]),
            contract=validation_contract,
        )
        capacity_limits = execution_capacity_limits(validation_contract)
        base_execution_cost_model, _ = _resolved_execution_cost_models()
        validation_metrics = _metric_snapshot(
            _backtest_cross_sectional(
                prediction_bundle["validation"],
                constraints=constraints,
                split_realization_contract=dict(feature_manifest.get("split_realization_contract") or {}),
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
            )
        )
        test_metrics = _metric_snapshot(
            _backtest_cross_sectional(
                prediction_bundle["test"],
                constraints=constraints,
                split_realization_contract=dict(feature_manifest.get("split_realization_contract") or {}),
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
            )
        )
        try:
            factor_evidence = _build_factor_evidence_section(
                prediction_frame=prediction_bundle["test"],
                test_metrics=test_metrics,
                thesis_profile=dict(candidate_entry.get("thesis_profile") or {}),
                selected_feature_columns=selected_feature_columns,
                strategy_entry=strategy_entry,
                forward_return_column=str(feature_manifest.get("forward_return_column") or "target_forward_return"),
                label_contract_id=str(feature_manifest.get("label_contract_id") or ""),
            )
            factor_evidence_lite = hb._build_factor_evidence_lite_section(
                factor_evidence=factor_evidence,
                contract=hb.load_fast_reject_contract(),
            )
        except Exception:
            factor_evidence_error = traceback.format_exc()
            blocker_codes.append("factor_evidence_lite_runtime_error")
        if validation_metrics["net_return"] <= 0.0:
            blocker_codes.append("validation_net_return_non_positive")
        if validation_metrics["sharpe"] <= 0.0:
            blocker_codes.append("validation_sharpe_non_positive")
        if validation_metrics["data_gap_blockers"]:
            blocker_codes.append("validation_data_gap_blockers_present")
        if test_metrics["net_return"] <= 0.0:
            blocker_codes.append("test_net_return_non_positive")
        if test_metrics["sharpe"] <= 0.0:
            blocker_codes.append("test_sharpe_non_positive")
        if test_metrics["data_gap_blockers"]:
            blocker_codes.append("test_data_gap_blockers_present")
        if factor_evidence_lite and not bool(factor_evidence_lite.get("passed")):
            blocker_codes.append("factor_evidence_lite_failed")

    status = "pass_pre_strict" if not blocker_codes else "fail_closed_pre_strict"
    decision = (
        "pre_strict_rebaseline_passed_ready_for_walk_forward"
        if status == "pass_pre_strict"
        else "fail_closed_do_not_run_alpha_or_promotion"
    )
    payload = {
        "artifact_family": "coinglass_h10d_parent_rebaseline",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "source_commit_sha": source_commit_sha,
        "as_of": as_of,
        "status": status,
        "decision": decision,
        "alpha_rerun_allowed": False,
        "promotion_allowed": False,
        "candidate_id": str(candidate_entry["candidate_id"]),
        "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
        "model_family": str(candidate_entry["model_family"]),
        "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
        "canonical_input_policy": {
            "spot_ohlc_source": "binance_ohlcv",
            "coinglass_spot_ohlc_consumed": False,
            "oi_sidecar_policy": "CoinGlass native USD OI sidecar allowed; derived OI remains metadata/quarantine",
        },
        "manifest_path": portable_path(manifest_path, repo_root=ROOT),
        "feature_manifest_path": portable_path(feature_manifest_path, repo_root=ROOT),
        "dataset_manifest_path": portable_path(dataset_manifest_path, repo_root=ROOT)
        if dataset_manifest_path.exists()
        else "",
        "feature_set_id": str(feature_manifest.get("feature_set_id") or ""),
        "feature_rows": int(len(frame0)),
        "feature_subject_count": int(frame0["subject"].nunique()) if "subject" in frame0.columns else 0,
        "selected_feature_count": int(len(selected_feature_columns)),
        "selected_feature_columns": selected_feature_columns,
        "universe_filter": dict(strategy_entry.get("universe_filter") or {}),
        "universe_filtered_rows": int(len(universe_filtered)),
        "universe_filtered_subject_count": int(universe_filtered["subject"].nunique()) if "subject" in universe_filtered.columns else 0,
        "universe_filtered_subjects": sorted(str(item) for item in universe_filtered["subject"].dropna().unique())
        if "subject" in universe_filtered.columns
        else [],
        "execution_filtered_rows": int(len(execution_filtered)),
        "execution_filtered_subject_count": int(execution_filtered["subject"].nunique()) if "subject" in execution_filtered.columns else 0,
        "split_row_counts": split_row_counts,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "factor_evidence_lite": factor_evidence_lite,
        "factor_evidence_error": factor_evidence_error,
        "blocker_codes": sorted(set(blocker_codes)),
        "full_walk_forward_status": "not_run_after_pre_strict_fail_closed_veto",
        "dataset_research_dataset": dict(dataset_manifest.get("research_dataset") or {}),
        "dataset_data_readiness": dict(dataset_manifest.get("data_readiness") or {}),
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the h10d canonical parent on Binance-canonical OHLC after CoinGlass coverage reset."
    )
    parser.add_argument("--as-of", default="2026-05-04")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--feature-manifest",
        type=Path,
        required=True,
        help="Feature manifest for the Binance-canonical cross_sectional_daily_4h h10d feature set.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=QUANT_ARTIFACTS_ROOT / "coinglass" / "coinglass_h10d_parent_rebaseline_2026-05-04.json",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=QUANT_ARTIFACTS_ROOT / "reports" / "coinglass_h10d_parent_rebaseline_2026-05-04.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run_audit(args)
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.json_out, payload)
    _write_report(path=args.report_out, payload=payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
