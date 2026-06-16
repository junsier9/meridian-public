from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STAGE_AUDIT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_fast_reject_stage_audit_2026-05-04_reset_rerun_2026-05-06.json"
)
DEFAULT_STAGE_REPLAY_ROOT = (
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
    / "h10d_parent_reset_strict_2026-05-04_2026-05-06_01"
)
DEFAULT_JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "coinglass_h10d_parent_strict_cycle_probe_2026-05-06.json"
)
DEFAULT_REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / "coinglass_h10d_parent_strict_cycle_probe_2026-05-06.md"
)
CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
FEATURE_SET_ID = "2026-05-04-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"
DATASET_ID = "2026-05-04-cross-sectional-daily-1d"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _feature_manifest_path(root: Path) -> Path:
    return root / "features" / FEATURE_SET_ID / "feature_manifest.json"


def _dataset_manifest_path(root: Path) -> Path:
    return root / "datasets" / DATASET_ID / "dataset_manifest.json"


def _strict_fast_reject_path(root: Path) -> Path:
    return root / "hypothesis_batches" / "2026-05-04" / "families" / CANDIDATE_ID / "fast_reject_report.json"


def _strict_summary_path(root: Path) -> Path:
    return root / "hypothesis_batches" / "2026-05-04" / "batch_summary.json"


def _manifest_summary(root: Path) -> dict[str, Any]:
    feature_manifest = _load(_feature_manifest_path(root))
    dataset_manifest = _load(_dataset_manifest_path(root))
    data_readiness = dict(dataset_manifest.get("data_readiness") or {})
    return {
        "root": str(root),
        "feature_manifest_path": str(_feature_manifest_path(root)),
        "dataset_manifest_path": str(_dataset_manifest_path(root)),
        "feature_row_count": feature_manifest.get("row_count"),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "feature_hash": feature_manifest.get("feature_hash"),
        "feature_features_path": feature_manifest.get("features_path"),
        "dataset_row_count": dataset_manifest.get("row_count"),
        "dataset_subject_count": dataset_manifest.get("subject_count"),
        "dataset_min_timestamp_utc": dataset_manifest.get("min_timestamp_utc"),
        "dataset_max_timestamp_utc": dataset_manifest.get("max_timestamp_utc"),
        "dataset_fingerprint": dataset_manifest.get("dataset_fingerprint"),
        "spot_lane": data_readiness.get("spot_lane"),
        "data_gap_blockers": data_readiness.get("data_gap_blockers"),
    }


def _fast_reject_summary(path: Path) -> dict[str, Any]:
    report = _load(path)
    return {
        "path": str(path),
        "status": report.get("status"),
        "fast_reject_passed": report.get("fast_reject_passed"),
        "blocker_codes": report.get("blocker_codes"),
        "advisory_codes": report.get("advisory_codes"),
        "split_row_counts": report.get("split_row_counts"),
        "validation_metrics_lite": report.get("validation_metrics_lite"),
        "test_metrics_lite": report.get("test_metrics_lite"),
        "factor_evidence_lite": report.get("factor_evidence_lite"),
        "walk_forward_assessment_lite": report.get("walk_forward_assessment_lite"),
        "regime_holdout_lite": report.get("regime_holdout_lite"),
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    stage_audit = _load(args.stage_audit)
    strict_summary = _load(_strict_summary_path(args.strict_root))
    stage_fast_reject_path = Path(str(stage_audit.get("official_fast_reject_report_path") or ""))
    if not stage_fast_reject_path.is_absolute():
        stage_fast_reject_path = (ROOT / stage_fast_reject_path).resolve()
    stage_manifest = _manifest_summary(args.stage_replay_root)
    strict_manifest = _manifest_summary(args.strict_root)
    stage_fast = _fast_reject_summary(stage_fast_reject_path)
    strict_fast = _fast_reject_summary(_strict_fast_reject_path(args.strict_root))
    feature_row_delta = int(strict_manifest["feature_row_count"] or 0) - int(stage_manifest["feature_row_count"] or 0)
    dataset_row_delta = int(strict_manifest["dataset_row_count"] or 0) - int(stage_manifest["dataset_row_count"] or 0)
    payload = {
        "artifact_family": "coinglass_h10d_parent_strict_cycle_probe",
        "contract_version": "coinglass_h10d_parent_strict_cycle_probe.v1",
        "generated_at_utc": _utc_now(),
        "status": "fail_closed_strict_cycle_input_matrix_drift",
        "decision": "do_not_interpret_fresh_strict_cycle_failure_as_alpha_failure_until_input_matrix_is_aligned",
        "alpha_rerun_allowed": False,
        "promotion_allowed": False,
        "candidate_id": CANDIDATE_ID,
        "stage_replay": {
            "stage_audit_path": str(args.stage_audit),
            "root": str(args.stage_replay_root),
            "manifest": stage_manifest,
            "fast_reject": stage_fast,
        },
        "fresh_strict_cycle": {
            "root": str(args.strict_root),
            "batch_summary_path": str(_strict_summary_path(args.strict_root)),
            "batch_summary": {
                "status": strict_summary.get("status"),
                "success": strict_summary.get("success"),
                "fast_reject_pass_count": strict_summary.get("fast_reject_pass_count"),
                "strict_candidate_count": strict_summary.get("strict_candidate_count"),
                "strict_survivor_count": strict_summary.get("strict_survivor_count"),
                "summary_hash": strict_summary.get("summary_hash"),
            },
            "manifest": strict_manifest,
            "fast_reject": strict_fast,
        },
        "diff": {
            "feature_row_delta_fresh_minus_stage": feature_row_delta,
            "dataset_row_delta_fresh_minus_stage": dataset_row_delta,
            "same_feature_hash": strict_manifest.get("feature_hash") == stage_manifest.get("feature_hash"),
            "same_feature_matrix_sha256": strict_manifest.get("feature_matrix_sha256")
            == stage_manifest.get("feature_matrix_sha256"),
            "same_dataset_fingerprint": strict_manifest.get("dataset_fingerprint")
            == stage_manifest.get("dataset_fingerprint"),
            "stage_dataset_min_timestamp_utc": stage_manifest.get("dataset_min_timestamp_utc"),
            "fresh_dataset_min_timestamp_utc": strict_manifest.get("dataset_min_timestamp_utc"),
            "stage_dataset_max_timestamp_utc": stage_manifest.get("dataset_max_timestamp_utc"),
            "fresh_dataset_max_timestamp_utc": strict_manifest.get("dataset_max_timestamp_utc"),
        },
        "interpretation": {
            "primary_blocker": "fresh_strict_cycle_rebuilt_a_different_and_shorter_feature_matrix",
            "why_it_matters": (
                "the stage replay passed official fast-reject on a frozen reset matrix, but the fresh strict cycle "
                "rebuilt a different feature matrix with materially fewer rows and then failed before strict candidates "
                "were admitted"
            ),
            "next_gate": (
                "rerun strict validation against the same frozen reset feature matrix, or rebuild the fresh strict "
                "cycle from a documented canonical Binance OHLC root with the same history span before interpreting "
                "parent alpha drift"
            ),
        },
    }
    return payload


def render_report(payload: dict[str, Any]) -> str:
    stage = payload["stage_replay"]
    strict = payload["fresh_strict_cycle"]
    diff = payload["diff"]
    stage_manifest = stage["manifest"]
    strict_manifest = strict["manifest"]
    stage_fast = stage["fast_reject"]
    strict_fast = strict["fast_reject"]
    lines = [
        "# CoinGlass H10D Parent Strict Cycle Probe",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{payload['decision']}`",
        f"- alpha_rerun_allowed: `{payload['alpha_rerun_allowed']}`",
        f"- candidate_id: `{payload['candidate_id']}`",
        "",
        "## Result",
        "",
        "| path | fast-reject passed | blockers | train/val/test rows | validation net/sharpe | test net/sharpe |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for label, fast in (("stage replay", stage_fast), ("fresh strict cycle", strict_fast)):
        validation = dict(fast.get("validation_metrics_lite") or {})
        test = dict(fast.get("test_metrics_lite") or {})
        split = dict(fast.get("split_row_counts") or {})
        rows = f"{split.get('train')}/{split.get('validation')}/{split.get('test')}"
        blockers = ", ".join(str(item) for item in list(fast.get("blocker_codes") or [])) or "none"
        lines.append(
            f"| {label} | `{fast.get('fast_reject_passed')}` | `{blockers}` | `{rows}` | "
            f"{validation.get('net_return')} / {validation.get('sharpe')} | "
            f"{test.get('net_return')} / {test.get('sharpe')} |"
        )
    lines.extend(
        [
            "",
            "## Input Matrix Diff",
            "",
            "| field | stage replay | fresh strict cycle |",
            "| --- | ---: | ---: |",
            f"| dataset rows | {stage_manifest.get('dataset_row_count')} | {strict_manifest.get('dataset_row_count')} |",
            f"| feature rows | {stage_manifest.get('feature_row_count')} | {strict_manifest.get('feature_row_count')} |",
            f"| dataset min timestamp | {stage_manifest.get('dataset_min_timestamp_utc')} | {strict_manifest.get('dataset_min_timestamp_utc')} |",
            f"| dataset max timestamp | {stage_manifest.get('dataset_max_timestamp_utc')} | {strict_manifest.get('dataset_max_timestamp_utc')} |",
            f"| feature hash | {stage_manifest.get('feature_hash')} | {strict_manifest.get('feature_hash')} |",
            f"| dataset fingerprint | {stage_manifest.get('dataset_fingerprint')} | {strict_manifest.get('dataset_fingerprint')} |",
            "",
            f"- feature_row_delta_fresh_minus_stage: `{diff['feature_row_delta_fresh_minus_stage']}`",
            f"- dataset_row_delta_fresh_minus_stage: `{diff['dataset_row_delta_fresh_minus_stage']}`",
            f"- same_feature_hash: `{diff['same_feature_hash']}`",
            f"- same_feature_matrix_sha256: `{diff['same_feature_matrix_sha256']}`",
            f"- same_dataset_fingerprint: `{diff['same_dataset_fingerprint']}`",
            "",
            "## Interpretation",
            "",
            f"- primary_blocker: `{payload['interpretation']['primary_blocker']}`",
            f"- why_it_matters: {payload['interpretation']['why_it_matters']}",
            f"- next_gate: {payload['interpretation']['next_gate']}",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare reset fast-reject stage replay with a fresh strict cycle.")
    parser.add_argument("--stage-audit", type=Path, default=DEFAULT_STAGE_AUDIT)
    parser.add_argument("--stage-replay-root", type=Path, default=DEFAULT_STAGE_REPLAY_ROOT)
    parser.add_argument("--strict-root", type=Path, default=DEFAULT_STRICT_ROOT)
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
