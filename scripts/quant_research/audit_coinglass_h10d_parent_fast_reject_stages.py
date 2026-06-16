from __future__ import annotations

import argparse
import json
import sys
import traceback
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings("ignore")

import enhengclaw.quant_research.hypothesis_batch as hb  # noqa: E402
import enhengclaw.quant_research.validation_contract as vc  # noqa: E402
from enhengclaw.ops.evidence_contracts import required_source_commit_sha  # noqa: E402
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)


DEFAULT_REPLAY_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_immutable_replay_2026-05-06_01"
)
DEFAULT_MANIFEST = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)
DEFAULT_JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_fast_reject_stage_audit_2026-05-06.json"
)
DEFAULT_REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / "coinglass_h10d_parent_fast_reject_stage_audit_2026-05-06.md"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_progress(path: Path, payload: dict[str, Any], stage: str, details: dict[str, Any] | None = None) -> None:
    payload["last_stage"] = stage
    payload.setdefault("stage_events", []).append(
        {
            "stage": stage,
            "details": details or {},
            "at_utc": _utc_now(),
        }
    )
    _write_json(path, payload)


def _patch_contracts(manifest: dict[str, Any]) -> None:
    contract_tag = str(manifest.get("contract_version") or "").rsplit(".", 1)[-1]
    hb.FAST_REJECT_REPORT_CONTRACT_VERSION = f"quant_cross_sectional_fast_reject_report.{contract_tag}"
    vc.VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
    validation_payload = _read_json(vc.VALIDATION_CONTRACT_PATH)
    vc.VALIDATION_CONTRACT_VERSION = str(
        validation_payload.get("contract_version") or vc.VALIDATION_CONTRACT_VERSION
    )


def _load_feature_set(replay_root: Path, *, as_of: str) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    feature_manifest_path = (
        replay_root
        / "features"
        / f"{as_of}-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"
        / "feature_manifest.json"
    )
    dataset_manifest_path = (
        replay_root
        / "datasets"
        / f"{as_of}-cross-sectional-daily-1d"
        / "dataset_manifest.json"
    )
    features_path = feature_manifest_path.parent / "features.csv.gz"
    feature_manifest = _read_json(feature_manifest_path)
    dataset_manifest = _read_json(dataset_manifest_path)
    frame = pd.read_csv(features_path, compression="gzip")
    feature_set = {
        "dataframe": frame,
        "dataset_profile": feature_manifest.get("dataset_profile"),
        "dataset_data_readiness": dataset_manifest.get("data_readiness"),
        "dataset_manifest_path": str(dataset_manifest_path),
        "manifest_path": str(feature_manifest_path),
        "feature_set_id": feature_manifest.get("feature_set_id"),
        "numeric_feature_columns": feature_manifest.get("numeric_feature_columns"),
        "split_realization_contract": feature_manifest.get("split_realization_contract"),
        "label_contract_id": feature_manifest.get("label_contract_id"),
        "target_column": feature_manifest.get("target_column"),
        "forward_return_column": feature_manifest.get("forward_return_column"),
    }
    return feature_set, feature_manifest, frame


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass H10D Parent Fast-Reject Stage Audit",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{payload['decision']}`",
        f"- alpha_rerun_allowed: `{payload['alpha_rerun_allowed']}`",
        f"- last_stage: `{payload.get('last_stage')}`",
        f"- replay_root: `{payload['inputs']['replay_root']}`",
        f"- official_fast_reject_report_path: `{payload.get('official_fast_reject_report_path')}`",
        "",
        "## Stage Events",
        "",
        "| stage | details |",
        "| --- | --- |",
    ]
    for item in list(payload.get("stage_events") or []):
        lines.append(f"| {item.get('stage')} | `{item.get('details')}` |")
    if payload.get("exception"):
        lines.extend(
            [
                "",
                "## Exception",
                "",
                "```text",
                str(payload["exception"]).strip(),
                "```",
            ]
        )
    metrics = payload.get("metrics") or {}
    if metrics:
        lines.extend(
            [
                "",
                "## Metrics",
                "",
                f"- split_row_counts: `{metrics.get('split_row_counts')}`",
                f"- validation: `{metrics.get('validation')}`",
                f"- test: `{metrics.get('test')}`",
                f"- walk_forward_lite: `{metrics.get('walk_forward_lite')}`",
                f"- factor_evidence_lite: `{metrics.get('factor_evidence_lite')}`",
                f"- regime_holdout_lite: `{metrics.get('regime_holdout_lite')}`",
                f"- fast_reject_passed: `{metrics.get('fast_reject_passed')}`",
                f"- blocker_codes: `{metrics.get('blocker_codes')}`",
                f"- advisory_codes: `{metrics.get('advisory_codes')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            str(payload["stop_rule"]),
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    replay_root = args.replay_root.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    json_out = args.json_out.expanduser().resolve()
    report_out = args.report_out.expanduser().resolve()
    manifest = _read_json(manifest_path)
    _patch_contracts(manifest)
    entry = dict(list(manifest.get("entries") or [])[0])
    payload: dict[str, Any] = {
        "alpha_rerun_allowed": False,
        "artifact_family": "coinglass_h10d_parent_fast_reject_stage_audit",
        "contract_version": "coinglass_h10d_parent_fast_reject_stage_audit.v1",
        "decision": "fail_closed_until_official_fast_reject_completes",
        "generated_at_utc": _utc_now(),
        "inputs": {
            "manifest": str(manifest_path),
            "replay_root": str(replay_root),
        },
        "promotion_allowed": False,
        "stage_events": [],
        "status": "running",
        "stop_rule": "Do not use this replay for alpha promotion unless the official fast-reject path writes a normal fast_reject_report.json and subsequent strict validation/falsification gates pass.",
    }
    _write_progress(json_out, payload, "start")
    try:
        feature_set, feature_manifest, raw_frame = _load_feature_set(replay_root, as_of=args.as_of)
        _write_progress(
            json_out,
            payload,
            "features_loaded",
            {"rows": int(len(raw_frame)), "columns": int(len(raw_frame.columns))},
        )
        feature_set_for_candidate = hb._feature_set_for_candidate(feature_sets=[feature_set], candidate_entry=entry)
        if feature_set_for_candidate is None:
            raise RuntimeError("candidate feature set not found")
        selected_feature_columns = hb._select_candidate_feature_columns(
            candidate_entry=entry,
            numeric_feature_columns=list(feature_set_for_candidate.get("numeric_feature_columns") or []),
        )
        _write_progress(json_out, payload, "selected_features", {"count": len(selected_feature_columns)})
        strategy_entry = hb._materialize_strict_strategy_entry(entry)
        constraints = dict(strategy_entry.get("profile_constraints") or {})
        constraints["strategy_profile"] = str(strategy_entry.get("strategy_profile") or "")
        frame = hb._apply_universe_filter(
            feature_set_for_candidate["dataframe"],
            universe_filter=dict(strategy_entry.get("universe_filter") or {}),
        )
        frame = hb.filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
        _write_progress(
            json_out,
            payload,
            "execution_frame_ready",
            {"rows": int(len(frame)), "subjects": int(frame["subject"].nunique()) if not frame.empty else 0},
        )
        data_gap_blockers = hb._initial_data_gap_blockers(
            shape="cross_sectional",
            strategy_entry=strategy_entry,
            frame=frame,
            dataset_data_readiness=dict(feature_set_for_candidate.get("dataset_data_readiness") or {}),
            contract=hb.load_data_readiness_contract(),
            subject_count_override=(
                int(feature_set_for_candidate["dataframe"]["subject"].nunique())
                if not feature_set_for_candidate["dataframe"].empty
                else 0
            ),
        )
        if data_gap_blockers:
            payload["status"] = "fail_closed_data_gap_blockers"
            payload["decision"] = "fail_closed_official_fast_reject_not_replayable"
            payload["blocker_codes"] = data_gap_blockers
            _write_progress(json_out, payload, "data_gap_blocked", {"blockers": data_gap_blockers})
            return payload
        split_realization_contract = dict(feature_set_for_candidate["split_realization_contract"])
        split = hb._chronological_split(
            frame,
            time_col="timestamp_ms",
            split_realization_contract=split_realization_contract,
        )
        if split is None:
            raise RuntimeError("unable_to_split")
        train_df, validation_df, test_df = split
        payload.setdefault("metrics", {})["split_row_counts"] = {
            "train": int(len(train_df)),
            "validation": int(len(validation_df)),
            "test": int(len(test_df)),
        }
        _write_progress(json_out, payload, "split_ready", payload["metrics"]["split_row_counts"])
        prediction_bundle = hb._fit_and_score(
            model_family=str(entry["model_family"]),
            shape="cross_sectional",
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            feature_columns=selected_feature_columns,
            target_column=str(feature_manifest.get("target_column") or "target_execution_up"),
        )
        _write_progress(json_out, payload, "fit_and_score_ready")
        validation_contract = hb.load_validation_contract()
        reference_capital_usd = validation_contract_reference_capital_usd(
            strategy_profile=str(entry["strategy_profile"]),
            contract=validation_contract,
        )
        capacity_limits = execution_capacity_limits(validation_contract)
        base_execution_cost_model, stress_execution_cost_model = hb._resolved_execution_cost_models()
        validation_metrics = hb._backtest_cross_sectional(
            prediction_bundle["validation"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        test_metrics = hb._backtest_cross_sectional(
            prediction_bundle["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        payload["metrics"]["validation"] = {
            "net_return": validation_metrics.get("net_return"),
            "sharpe": validation_metrics.get("sharpe"),
        }
        payload["metrics"]["test"] = {
            "net_return": test_metrics.get("net_return"),
            "sharpe": test_metrics.get("sharpe"),
        }
        _write_progress(json_out, payload, "backtests_ready")
        walk_forward = hb._run_walk_forward(
            frame=frame,
            shape="cross_sectional",
            model_family=str(entry["model_family"]),
            feature_columns=selected_feature_columns,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            target_column=str(feature_manifest.get("target_column") or "target_execution_up"),
            execution_cost_model=base_execution_cost_model,
            stress_execution_cost_model=stress_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            validation_contract=validation_contract,
        )
        walk_forward_lite = hb.build_walk_forward_assessment(
            walk_forward=walk_forward,
            contract={"walk_forward_assessment": dict(hb.load_fast_reject_contract()["walk_forward_assessment_lite"])},
        )
        payload["metrics"]["walk_forward_lite"] = walk_forward_lite
        _write_progress(json_out, payload, "walk_forward_ready")
        fast_reject_contract = hb.load_fast_reject_contract()
        factor_evidence = hb._build_factor_evidence_section(
            prediction_frame=prediction_bundle["test"],
            test_metrics=test_metrics,
            thesis_profile=dict(entry["thesis_profile"]),
            selected_feature_columns=selected_feature_columns,
            strategy_entry=strategy_entry,
            forward_return_column=str(feature_manifest.get("forward_return_column") or "target_execution_forward_return"),
            label_contract_id=str(feature_manifest.get("label_contract_id") or hb.DEFAULT_LABEL_CONTRACT_ID),
        )
        factor_evidence_lite = hb._build_factor_evidence_lite_section(
            factor_evidence=factor_evidence,
            contract=fast_reject_contract,
        )
        payload["metrics"]["factor_evidence_lite"] = factor_evidence_lite
        regime_holdout_contract_section = dict(fast_reject_contract["regime_holdout_lite"])
        regime_holdout_mode = str(regime_holdout_contract_section.get("mode") or "blocker").strip().lower()
        regime_holdout_lite = hb.build_regime_holdout_section(
            walk_forward=walk_forward,
            contract={"regime_holdout": regime_holdout_contract_section},
        )
        regime_holdout_lite["mode"] = regime_holdout_mode
        payload["metrics"]["regime_holdout_lite"] = regime_holdout_lite
        _write_progress(json_out, payload, "factor_evidence_ready")
        regime_is_blocker = regime_holdout_mode != "advisory"
        fast_reject_passed = (
            bool(factor_evidence_lite.get("passed"))
            and bool(walk_forward_lite.get("passed"))
            and (bool(regime_holdout_lite.get("passed")) or not regime_is_blocker)
        )
        blocker_codes: list[str] = []
        advisory_codes: list[str] = []
        if not bool(factor_evidence_lite.get("passed")):
            blocker_codes.append(hb.LITE_BLOCKER_FACTOR)
        if not bool(walk_forward_lite.get("passed")):
            blocker_codes.append(hb.LITE_BLOCKER_WALK_FORWARD)
        if not bool(regime_holdout_lite.get("passed")):
            if regime_is_blocker:
                blocker_codes.append(hb.LITE_BLOCKER_REGIME)
            else:
                advisory_codes.append(hb.LITE_ADVISORY_REGIME)
        target_column = str(feature_manifest.get("target_column") or "target_execution_up")
        forward_return_column = str(
            feature_manifest.get("forward_return_column") or "target_execution_forward_return"
        )
        label_contract_id = str(feature_manifest.get("label_contract_id") or hb.DEFAULT_LABEL_CONTRACT_ID)
        family_root = replay_root / "hypothesis_batches" / args.as_of / "families" / str(entry["candidate_id"])
        official_report = hb._write_fast_reject_report(
            path=family_root / "fast_reject_report.json",
            payload={
                "status": "success",
                "success": True,
                "as_of": args.as_of,
                "candidate_id": str(entry["candidate_id"]),
                "base_mechanism_id": str(entry["base_mechanism_id"]),
                "horizon_id": str(entry["horizon_id"]),
                "target_horizon_bars": int(entry["target_horizon_bars"]),
                "label_contract_id": label_contract_id,
                "strategy_id": str(entry["candidate_id"]),
                "dataset_profile": hb.HYPOTHESIS_BATCH_DATASET_PROFILE,
                "feature_set_id": str(feature_set_for_candidate.get("feature_set_id") or ""),
                "split_realization_contract": split_realization_contract,
                "target_column": target_column,
                "forward_return_column": forward_return_column,
                "dataset_manifest_path": hb.portable_path(
                    Path(str(feature_set_for_candidate.get("dataset_manifest_path") or "")), repo_root=ROOT
                ),
                "feature_manifest_path": hb.portable_path(
                    Path(str(feature_set_for_candidate.get("manifest_path") or "")), repo_root=ROOT
                ),
                "selected_feature_columns": selected_feature_columns,
                "split_row_counts": {
                    "train": int(len(train_df)),
                    "validation": int(len(validation_df)),
                    "test": int(len(test_df)),
                },
                "validation_metrics_lite": {
                    "net_return": float(validation_metrics.get("net_return", 0.0) or 0.0),
                    "sharpe": float(validation_metrics.get("sharpe", 0.0) or 0.0),
                },
                "test_metrics_lite": {
                    "net_return": float(test_metrics.get("net_return", 0.0) or 0.0),
                    "sharpe": float(test_metrics.get("sharpe", 0.0) or 0.0),
                },
                "factor_evidence_lite": factor_evidence_lite,
                "walk_forward_assessment_lite": walk_forward_lite,
                "regime_holdout_lite": regime_holdout_lite,
                "fast_reject_passed": fast_reject_passed,
                "blocker_codes": blocker_codes,
                "advisory_codes": advisory_codes,
            },
            source_commit_sha=required_source_commit_sha(repo_root=ROOT),
        )
        payload["metrics"]["fast_reject_passed"] = fast_reject_passed
        payload["metrics"]["blocker_codes"] = blocker_codes
        payload["metrics"]["advisory_codes"] = advisory_codes
        payload["official_fast_reject_report_path"] = str(official_report["path"])
        payload["status"] = "completed_official_fast_reject_replay"
        payload["decision"] = (
            f"official_{args.as_of}_fast_reject_replayed_on_non_overwriting_root"
            if fast_reject_passed
            else f"official_{args.as_of}_fast_reject_replayed_but_failed"
        )
        _write_progress(
            json_out,
            payload,
            "official_fast_reject_written",
            {"fast_reject_passed": fast_reject_passed, "path": str(official_report["path"])},
        )
        return payload
    except BaseException:
        payload["exception"] = traceback.format_exc()
        payload["status"] = "fail_closed_stage_exception"
        payload["decision"] = "fail_closed_official_fast_reject_not_replayable"
        _write_progress(json_out, payload, "exception")
        return payload
    finally:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(_render_report(payload), encoding="utf-8")


def finalize_aborted_run(args: argparse.Namespace) -> dict[str, Any]:
    json_out = args.json_out.expanduser().resolve()
    report_out = args.report_out.expanduser().resolve()
    payload = _read_json(json_out)
    last_stage = str(payload.get("last_stage") or "unknown")
    payload["status"] = f"fail_closed_process_aborted_after_{last_stage}"
    payload["decision"] = "fail_closed_official_fast_reject_replay_did_not_complete"
    payload["alpha_rerun_allowed"] = False
    payload["promotion_allowed"] = False
    payload["stop_rule"] = (
        "Do not use this replay for alpha promotion. The stage audit did not reach walk_forward_ready, "
        "factor_evidence_ready, or official_fast_reject_written, so the official fast-reject contract is incomplete."
    )
    _write_progress(
        json_out,
        payload,
        "process_abort_finalized",
        {
            "after_stage": last_stage,
            "reason": "previous run left status=running and did not produce a report",
        },
    )
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(_render_report(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-level audit for the CoinGlass h10d parent fast-reject replay.")
    parser.add_argument("--as-of", default="2026-04-29")
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--finalize-aborted-run", action="store_true")
    args = parser.parse_args()
    payload = finalize_aborted_run(args) if args.finalize_aborted_run else run(args)
    print(
        json.dumps(
            {
                "json": str(args.json_out),
                "report": str(args.report_out),
                "status": payload.get("status"),
                "decision": payload.get("decision"),
                "last_stage": payload.get("last_stage"),
            },
            indent=2,
        )
    )
    return 0 if str(payload.get("status")).startswith("completed_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
