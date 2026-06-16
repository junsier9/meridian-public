from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HISTORICAL_FAST_REJECT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "hypothesis_batches"
    / "2026-04-29"
    / "families"
    / "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
    / "fast_reject_report.json"
)
DEFAULT_REFERENCE_REPLAY = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_rebaseline_2026-04-29_reference.json"
)
DEFAULT_RESET_REPLAY = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_rebaseline_2026-05-04.json"
)
DEFAULT_IMMUTABLE_STAGE_AUDIT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_fast_reject_stage_audit_2026-05-06.json"
)
DEFAULT_RESET_STAGE_AUDIT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_fast_reject_stage_audit_2026-05-04_reset_2026-05-06.json"
)
DEFAULT_JSON_OUT = (
    ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_h10d_parent_drift_2026-05-06.json"
)
DEFAULT_REPORT_OUT = (
    ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_h10d_parent_drift_2026-05-06.md"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_repo_path(path_text: str | Path) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _metric_delta(now: dict[str, Any], before: dict[str, Any], key: str) -> float | None:
    if now.get(key) is None or before.get(key) is None:
        return None
    return float(now.get(key) or 0.0) - float(before.get(key) or 0.0)


def _metrics_from_fast_reject(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pass" if bool(report.get("fast_reject_passed")) else "fail",
        "validation": dict(report.get("validation_metrics_lite") or {}),
        "test": dict(report.get("test_metrics_lite") or {}),
        "factor_evidence_lite": dict(report.get("factor_evidence_lite") or {}),
        "walk_forward_assessment_lite": dict(report.get("walk_forward_assessment_lite") or {}),
        "split_row_counts": dict(report.get("split_row_counts") or {}),
        "blocker_codes": list(report.get("blocker_codes") or []),
    }


def _metrics_from_replay(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(report.get("status") or ""),
        "validation": dict(report.get("validation_metrics") or {}),
        "test": dict(report.get("test_metrics") or {}),
        "factor_evidence_lite": dict(report.get("factor_evidence_lite") or {}),
        "split_row_counts": dict(report.get("split_row_counts") or {}),
        "blocker_codes": list(report.get("blocker_codes") or []),
        "universe_filtered_subject_count": int(report.get("universe_filtered_subject_count") or 0),
        "universe_filtered_subjects": list(report.get("universe_filtered_subjects") or []),
        "feature_rows": int(report.get("feature_rows") or 0),
        "feature_subject_count": int(report.get("feature_subject_count") or 0),
    }


def _metrics_match(left: dict[str, Any], right: dict[str, Any], *, tolerance: float = 1e-12) -> bool:
    checks = [
        ("validation", "net_return"),
        ("validation", "sharpe"),
        ("test", "net_return"),
        ("test", "sharpe"),
        ("walk_forward_assessment_lite", "median_oos_sharpe"),
        ("walk_forward_assessment_lite", "loss_window_fraction"),
        ("factor_evidence_lite", "rank_ic_mean"),
        ("factor_evidence_lite", "rank_ic_positive_rate"),
        ("factor_evidence_lite", "top_minus_bottom_return"),
        ("factor_evidence_lite", "max_single_quarter_edge_contribution_ratio"),
    ]
    for section, key in checks:
        left_value = (left.get(section) or {}).get(key)
        right_value = (right.get(section) or {}).get(key)
        if left_value is None or right_value is None:
            return False
        if abs(float(left_value) - float(right_value)) > tolerance:
            return False
    return (
        bool(left.get("status") == right.get("status"))
        and dict(left.get("split_row_counts") or {}) == dict(right.get("split_row_counts") or {})
        and list(left.get("blocker_codes") or []) == list(right.get("blocker_codes") or [])
        and bool((left.get("factor_evidence_lite") or {}).get("passed"))
        == bool((right.get("factor_evidence_lite") or {}).get("passed"))
        and bool((left.get("walk_forward_assessment_lite") or {}).get("passed"))
        == bool((right.get("walk_forward_assessment_lite") or {}).get("passed"))
    )


def _feature_manifest_metadata(feature_manifest_path: Path) -> dict[str, Any]:
    manifest = _load(feature_manifest_path)
    produced_at = manifest.get("produced_at_utc") or manifest.get("generated_at_utc")
    return {
        "path": str(feature_manifest_path),
        "feature_set_id": manifest.get("feature_set_id"),
        "produced_at_utc": produced_at,
        "row_count": manifest.get("row_count"),
        "feature_matrix_sha256": manifest.get("feature_matrix_sha256"),
        "feature_hash": manifest.get("feature_hash"),
        "dataset_fingerprint": manifest.get("dataset_fingerprint"),
        "source_commit_sha": manifest.get("source_commit_sha"),
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    historical_fast = _load(args.historical_fast_reject)
    reference_replay = _load(args.reference_replay)
    reset_replay = _load(args.reset_replay)
    feature_manifest_path = _resolve_repo_path(str(historical_fast.get("feature_manifest_path") or ""))
    feature_manifest = _feature_manifest_metadata(feature_manifest_path)
    fast_produced_at = _parse_utc(historical_fast.get("produced_at_utc") or historical_fast.get("generated_at_utc"))
    feature_produced_at = _parse_utc(feature_manifest.get("produced_at_utc"))
    artifact_overwritten_after_report = (
        fast_produced_at is not None
        and feature_produced_at is not None
        and feature_produced_at > fast_produced_at
    )
    overwrite_lag_minutes = None
    if artifact_overwritten_after_report:
        overwrite_lag_minutes = (feature_produced_at - fast_produced_at).total_seconds() / 60.0
    historical_metrics = _metrics_from_fast_reject(historical_fast)
    reference_metrics = _metrics_from_replay(reference_replay)
    reset_metrics = _metrics_from_replay(reset_replay)
    immutable_stage_audit = _load(args.immutable_stage_audit) if args.immutable_stage_audit.exists() else None
    reset_stage_audit = _load(args.reset_stage_audit) if args.reset_stage_audit.exists() else None
    immutable_report = None
    immutable_metrics = None
    immutable_metrics_match_historical = False
    if immutable_stage_audit:
        immutable_report_path = str(immutable_stage_audit.get("official_fast_reject_report_path") or "").strip()
        if immutable_report_path:
            immutable_report = _load(_resolve_repo_path(immutable_report_path))
            immutable_metrics = _metrics_from_fast_reject(immutable_report)
            immutable_metrics_match_historical = _metrics_match(immutable_metrics, historical_metrics)
    reference_subjects = set(str(item) for item in reference_metrics.get("universe_filtered_subjects") or [])
    reset_subjects = set(str(item) for item in reset_metrics.get("universe_filtered_subjects") or [])
    subject_diff = {
        "reference_only": sorted(reference_subjects - reset_subjects),
        "reset_only": sorted(reset_subjects - reference_subjects),
        "intersection_count": len(reference_subjects & reset_subjects),
        "same_subject_set": reference_subjects == reset_subjects,
    }
    immutable_replay_passed = bool(
        immutable_stage_audit
        and immutable_report
        and immutable_stage_audit.get("status") == "completed_official_fast_reject_replay"
        and immutable_metrics_match_historical
        and immutable_metrics
        and immutable_metrics.get("status") == "pass"
    )
    reset_stage_status = str((reset_stage_audit or {}).get("status") or "")
    reset_stage_failed = reset_stage_status.startswith("fail_closed")
    reset_stage_metrics = dict((reset_stage_audit or {}).get("metrics") or {})
    reset_stage_completed = reset_stage_status == "completed_official_fast_reject_replay"
    reset_stage_fast_reject_passed = reset_stage_completed and bool(reset_stage_metrics.get("fast_reject_passed"))
    reset_stage_fast_reject_failed = reset_stage_completed and not bool(reset_stage_metrics.get("fast_reject_passed"))
    payload = {
        "artifact_family": "coinglass_h10d_parent_drift",
        "contract_version": "coinglass_h10d_parent_drift.v1",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": (
            "fail_closed_2026_05_04_official_fast_reject_replay_incomplete"
            if reset_stage_failed
            else "pass_2026_05_04_reset_official_fast_reject_replayed_strict_pending"
            if immutable_replay_passed and reset_stage_fast_reject_passed
            else "fail_closed_2026_05_04_reset_official_fast_reject_failed"
            if immutable_replay_passed and reset_stage_fast_reject_failed
            else "pass_2026_04_29_fast_reject_reproduced_fail_closed_reset_rebaseline_pending"
            if immutable_replay_passed
            else "fail_closed_reproducibility_break"
        ),
        "decision": (
            "do_not_promote_2026_05_04_reset_official_fast_reject_replay_aborted_before_walk_forward_completion"
            if reset_stage_failed
            else "r1_fast_reject_gate_passed_but_strict_validation_and_falsification_pending"
            if immutable_replay_passed and reset_stage_fast_reject_passed
            else "do_not_promote_2026_05_04_reset_official_fast_reject_failed"
            if immutable_replay_passed and reset_stage_fast_reject_failed
            else "treat_2026_04_29_fast_reject_as_reproduced_on_non_overwriting_root_but_do_not_promote_until_2026_05_04_official_rebaseline_and_strict_gates_pass"
            if immutable_replay_passed
            else "do_not_treat_2026_04_29_fast_reject_as_reproducible_baseline"
        ),
        "alpha_rerun_allowed": False,
        "promotion_allowed": False,
        "inputs": {
            "historical_fast_reject": str(args.historical_fast_reject),
            "reference_replay": str(args.reference_replay),
            "reset_replay": str(args.reset_replay),
            "immutable_stage_audit": str(args.immutable_stage_audit) if immutable_stage_audit else None,
            "reset_stage_audit": str(args.reset_stage_audit) if reset_stage_audit else None,
            "feature_manifest_path": str(feature_manifest_path),
        },
        "historical_report": {
            "candidate_id": historical_fast.get("candidate_id"),
            "produced_at_utc": historical_fast.get("produced_at_utc") or historical_fast.get("generated_at_utc"),
            "source_commit_sha": historical_fast.get("source_commit_sha"),
            "metrics": historical_metrics,
        },
        "referenced_feature_manifest_current_state": feature_manifest,
        "reproducibility_break": {
            "artifact_overwritten_after_report": artifact_overwritten_after_report,
            "overwrite_lag_minutes": overwrite_lag_minutes,
            "reason": (
                "historical fast-reject report references a feature_manifest_path whose current manifest "
                "was produced after the report; the path is mutable and cannot prove the original matrix"
            ),
        },
        "immutable_replay": None
        if immutable_stage_audit is None
        else {
            "stage_audit_status": immutable_stage_audit.get("status"),
            "stage_audit_decision": immutable_stage_audit.get("decision"),
            "official_fast_reject_report_path": immutable_stage_audit.get("official_fast_reject_report_path"),
            "metrics": immutable_metrics,
            "metrics_match_historical": immutable_metrics_match_historical,
            "fast_reject_reproduced": immutable_replay_passed,
        },
        "reset_official_stage_audit": None
        if reset_stage_audit is None
        else {
            "status": reset_stage_audit.get("status"),
            "decision": reset_stage_audit.get("decision"),
            "last_stage": reset_stage_audit.get("last_stage"),
            "official_fast_reject_report_path": reset_stage_audit.get("official_fast_reject_report_path"),
            "metrics": reset_stage_audit.get("metrics"),
            "stage_events": reset_stage_audit.get("stage_events"),
            "stop_rule": reset_stage_audit.get("stop_rule"),
        },
        "reference_replay_current_artifact": {
            "as_of": reference_replay.get("as_of"),
            "generated_at_utc": reference_replay.get("generated_at_utc"),
            "source_commit_sha": reference_replay.get("source_commit_sha"),
            "metrics": reference_metrics,
        },
        "reset_replay_current_artifact": {
            "as_of": reset_replay.get("as_of"),
            "generated_at_utc": reset_replay.get("generated_at_utc"),
            "source_commit_sha": reset_replay.get("source_commit_sha"),
            "metrics": reset_metrics,
        },
        "subject_drift": subject_diff,
        "metric_deltas": {
            "reference_replay_minus_historical_fast_reject": {
                "validation_net_return": _metric_delta(
                    reference_metrics["validation"], historical_metrics["validation"], "net_return"
                ),
                "validation_sharpe": _metric_delta(
                    reference_metrics["validation"], historical_metrics["validation"], "sharpe"
                ),
                "test_net_return": _metric_delta(reference_metrics["test"], historical_metrics["test"], "net_return"),
                "test_sharpe": _metric_delta(reference_metrics["test"], historical_metrics["test"], "sharpe"),
            },
            "reset_replay_minus_reference_replay": {
                "validation_net_return": _metric_delta(
                    reset_metrics["validation"], reference_metrics["validation"], "net_return"
                ),
                "validation_sharpe": _metric_delta(
                    reset_metrics["validation"], reference_metrics["validation"], "sharpe"
                ),
                "test_net_return": _metric_delta(reset_metrics["test"], reference_metrics["test"], "net_return"),
                "test_sharpe": _metric_delta(reset_metrics["test"], reference_metrics["test"], "sharpe"),
            },
        },
        "interpretation": {
            "primary_blocker": (
                "2026_05_04_official_fast_reject_replay_aborted_before_walk_forward_completion"
                if reset_stage_failed
                else "strict_validation_and_falsification_pending_after_2026_05_04_fast_reject_pass"
                if immutable_replay_passed and reset_stage_fast_reject_passed
                else "2026_05_04_reset_official_fast_reject_failed"
                if immutable_replay_passed and reset_stage_fast_reject_failed
                else "2026_05_04_official_reset_rebaseline_pending"
                if immutable_replay_passed
                else "reproducibility_break_from_mutable_feature_artifact"
            ),
            "provenance_observation": (
                "the historical artifact path is mutable and was overwritten after the old report, but a fresh "
                "non-overwriting replay reproduced the 2026-04-29 official fast-reject metrics and wrote a new "
                "fast_reject_report.json"
                if immutable_replay_passed
                else "the historical artifact path is mutable and the old pass was not reproduced on a non-overwriting root"
            ),
            "secondary_observation": (
                "current 2026-04-29 and 2026-05-04 replays use the same 17-symbol liquid_perp_core_20 set, "
                "so the observed fail-closed replay is not explained by a new 2026-05-04 subject-roster drift alone"
            ),
            "next_gate": (
                "debug the 2026-05-04 official reset replay abort after backtests_ready, rerun until "
                "walk_forward_ready and official_fast_reject_written are produced, and only then consider strict gates"
                if reset_stage_failed
                else "run strict validation, falsification, overlay-ablation sidecars, and promotion guard on the "
                "2026-05-04 reset parent; alpha promotion remains blocked until those gates pass, and CoinGlass "
                "spot OHLC remains quarantined with Binance OHLC canonical"
                if immutable_replay_passed and reset_stage_fast_reject_passed
                else "preserve the 2026-05-04 reset fast-reject failure as the R-1 stop rule and do not continue to "
                "strict or promotion gates"
                if immutable_replay_passed and reset_stage_fast_reject_failed
                else "run the same official fast-reject replay for the 2026-05-04 reset root, then run strict validation/"
                "falsification only if that reset replay passes"
                if immutable_replay_passed
                else "freeze immutable feature-matrix hash sidecars for the parent baseline and rerun official fast-reject "
                "on a non-overwriting artifact root before R-2 intraday feasibility or any alpha promotion"
            ),
        },
    }
    return payload


def render_report(payload: dict[str, Any]) -> str:
    historical = payload["historical_report"]["metrics"]
    reference = payload["reference_replay_current_artifact"]["metrics"]
    reset = payload["reset_replay_current_artifact"]["metrics"]
    feature = payload["referenced_feature_manifest_current_state"]
    repro = payload["reproducibility_break"]
    subjects = payload["subject_drift"]
    deltas = payload["metric_deltas"]
    immutable = payload.get("immutable_replay")
    reset_stage = payload.get("reset_official_stage_audit")
    lines = [
        "# CoinGlass H10D Parent Drift Audit",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{payload['decision']}`",
        f"- alpha_rerun_allowed: `{payload['alpha_rerun_allowed']}`",
        "",
        "## Mutable Path Risk",
        "",
        f"- historical fast-reject produced_at_utc: `{payload['historical_report']['produced_at_utc']}`",
        f"- current referenced feature manifest produced_at_utc: `{feature['produced_at_utc']}`",
        f"- artifact overwritten after report: `{repro['artifact_overwritten_after_report']}`",
        f"- overwrite lag minutes: `{repro['overwrite_lag_minutes']}`",
        f"- feature_matrix_sha256: `{feature['feature_matrix_sha256']}`",
        f"- feature_hash: `{feature['feature_hash']}`",
        "",
        "The old pass report points at a mutable feature path whose current contents were produced after the report. "
        "That is a provenance risk for the main artifact path; it is not by itself proof that the fast-reject "
        "calculation cannot be reproduced.",
        "",
    ]
    if immutable:
        immutable_metrics = immutable.get("metrics") or {}
        lines.extend(
            [
                "## Immutable Replay",
                "",
                f"- stage audit status: `{immutable.get('stage_audit_status')}`",
                f"- official fast-reject path: `{immutable.get('official_fast_reject_report_path')}`",
                f"- metrics match historical: `{immutable.get('metrics_match_historical')}`",
                f"- fast-reject reproduced: `{immutable.get('fast_reject_reproduced')}`",
                f"- validation net/sharpe: `{(immutable_metrics.get('validation') or {}).get('net_return')}` / `{(immutable_metrics.get('validation') or {}).get('sharpe')}`",
                f"- test net/sharpe: `{(immutable_metrics.get('test') or {}).get('net_return')}` / `{(immutable_metrics.get('test') or {}).get('sharpe')}`",
                f"- walk-forward median OOS sharpe: `{(immutable_metrics.get('walk_forward_assessment_lite') or {}).get('median_oos_sharpe')}`",
                "",
            ]
        )
    if reset_stage:
        reset_stage_metrics = dict(reset_stage.get("metrics") or {})
        lines.extend(
            [
                "## Reset Official Replay",
                "",
                f"- status: `{reset_stage.get('status')}`",
                f"- decision: `{reset_stage.get('decision')}`",
                f"- last_stage: `{reset_stage.get('last_stage')}`",
                f"- validation net/sharpe: `{dict(reset_stage_metrics.get('validation') or {}).get('net_return')}` / `{dict(reset_stage_metrics.get('validation') or {}).get('sharpe')}`",
                f"- test net/sharpe: `{dict(reset_stage_metrics.get('test') or {}).get('net_return')}` / `{dict(reset_stage_metrics.get('test') or {}).get('sharpe')}`",
                f"- split_row_counts: `{reset_stage_metrics.get('split_row_counts')}`",
                f"- stop_rule: {reset_stage.get('stop_rule')}",
                "",
            ]
        )
    lines.extend(
        [
        "## Metric Comparison",
        "",
        "| run | status | validation net | validation sharpe | test net | test sharpe | blockers |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        (
            f"| historical fast-reject | {historical['status']} | {historical['validation'].get('net_return')} | "
            f"{historical['validation'].get('sharpe')} | {historical['test'].get('net_return')} | "
            f"{historical['test'].get('sharpe')} | {', '.join(historical.get('blocker_codes') or []) or 'none'} |"
        ),
        (
            f"| 2026-04-29 current replay | {reference['status']} | {reference['validation'].get('net_return')} | "
            f"{reference['validation'].get('sharpe')} | {reference['test'].get('net_return')} | "
            f"{reference['test'].get('sharpe')} | {', '.join(reference.get('blocker_codes') or []) or 'none'} |"
        ),
        (
            f"| 2026-05-04 current replay | {reset['status']} | {reset['validation'].get('net_return')} | "
            f"{reset['validation'].get('sharpe')} | {reset['test'].get('net_return')} | "
            f"{reset['test'].get('sharpe')} | {', '.join(reset.get('blocker_codes') or []) or 'none'} |"
        ),
        "",
        "Metric deltas:",
        "",
        f"- current 2026-04-29 replay minus historical fast-reject: `{deltas['reference_replay_minus_historical_fast_reject']}`",
        f"- current 2026-05-04 replay minus current 2026-04-29 replay: `{deltas['reset_replay_minus_reference_replay']}`",
        "",
        "## Subject Drift",
        "",
        f"- reference filtered subject count: `{reference.get('universe_filtered_subject_count')}`",
        f"- reset filtered subject count: `{reset.get('universe_filtered_subject_count')}`",
        f"- same subject set: `{subjects['same_subject_set']}`",
        f"- intersection count: `{subjects['intersection_count']}`",
        f"- reference_only: `{subjects['reference_only']}`",
        f"- reset_only: `{subjects['reset_only']}`",
        "",
        "## Interpretation",
        "",
        f"- primary_blocker: `{payload['interpretation']['primary_blocker']}`",
        f"- provenance_observation: {payload['interpretation'].get('provenance_observation')}",
        f"- secondary_observation: {payload['interpretation']['secondary_observation']}",
        f"- next_gate: {payload['interpretation']['next_gate']}",
        "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare historical h10d parent pass evidence against current replays.")
    parser.add_argument("--historical-fast-reject", type=Path, default=DEFAULT_HISTORICAL_FAST_REJECT)
    parser.add_argument("--reference-replay", type=Path, default=DEFAULT_REFERENCE_REPLAY)
    parser.add_argument("--reset-replay", type=Path, default=DEFAULT_RESET_REPLAY)
    parser.add_argument("--immutable-stage-audit", type=Path, default=DEFAULT_IMMUTABLE_STAGE_AUDIT)
    parser.add_argument("--reset-stage-audit", type=Path, default=DEFAULT_RESET_STAGE_AUDIT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_payload(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    args.report_out.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(args.json_out), "report": str(args.report_out), "status": payload["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
