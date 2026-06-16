from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata
from enhengclaw.quant_research.contracts import QuantUniverseCandidate, read_json, utc_now
from enhengclaw.quant_research.features import DEFAULT_LABEL_CONTRACT_ID
from enhengclaw.quant_research.hypothesis_batch import HYPOTHESIS_BATCH_TARGET_HORIZONS
from enhengclaw.quant_research.lab import (
    QUANT_ARTIFACTS_ROOT,
    build_quant_datasets,
    build_quant_feature_sets,
    load_quant_universe_snapshot,
    require_derivatives_sync_summary,
)
from scripts.market_data.binance_ohlcv import resolve_external_history_root


AS_OF = "2026-05-04"
RESET_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_coverage_reset_2026-05-04.json"
JSON_OUT = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_dataset_feature_smoke_2026-05-04.json"
REPORT_OUT = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_dataset_feature_smoke_2026-05-04.md"


def build_payload(
    *,
    as_of: str,
    artifacts_root: Path,
    smoke_artifacts_root: Path,
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
    cross_sectional_daily_target_horizons: tuple[int, ...],
    artifact_family: str,
    contract_version: str,
    feature_set_version: str,
    spot_ohlc_source: str,
    coinglass_spot_ohlc_consumed: bool,
    spot_ohlc_trust_status: str,
    quarantine_reason: str,
) -> dict[str, Any]:
    resolved_artifacts_root = artifacts_root.expanduser().resolve()
    resolved_smoke_root = smoke_artifacts_root.expanduser().resolve()
    resolved_ohlcv_root = resolve_external_history_root(external_root=ohlcv_external_root)
    resolved_spot_ohlcv_root = (
        spot_ohlcv_external_root.expanduser().resolve()
        if spot_ohlcv_external_root is not None
        else None
    )
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    universe_snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=resolved_artifacts_root)
    universe_candidates = tuple(
        QuantUniverseCandidate.from_payload(item)
        for item in list(universe_snapshot.get("candidates") or [])
        if isinstance(item, dict)
    )
    derivatives_sync, derivatives_sync_path = require_derivatives_sync_summary(
        as_of=as_of,
        derivatives_external_root=derivatives_external_root,
    )
    datasets = build_quant_datasets(
        as_of=as_of,
        artifacts_root=resolved_smoke_root,
        universe_snapshot=universe_snapshot,
        universe_candidates=universe_candidates,
        ohlcv_external_root=resolved_ohlcv_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_root,
        derivatives_external_root=derivatives_external_root,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
    )
    feature_sets = build_quant_feature_sets(
        artifacts_root=resolved_smoke_root,
        datasets=datasets,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
        cross_sectional_daily_target_horizons=cross_sectional_daily_target_horizons,
        cross_sectional_daily_label_contract_ids=(DEFAULT_LABEL_CONTRACT_ID,),
        feature_set_version=feature_set_version,
    )
    reset = read_json(RESET_PATH) if RESET_PATH.exists() else {}
    dataset_summaries = [_summarize_dataset(dataset) for dataset in datasets]
    feature_summaries = [_summarize_feature_set(feature_set) for feature_set in feature_sets]
    alpha_blockers = []
    if dict(reset.get("decision") or {}).get("provider_concordance") != "pass":
        alpha_blockers.append("strict_spot_ohlc_provider_concordance_failed")
    if str(spot_ohlc_trust_status).strip() != "canonical":
        alpha_blockers.append("coinglass_spot_ohlc_quarantined_not_canonical")
    for blocker in _dataset_data_gap_blockers(dataset_summaries):
        alpha_blockers.append(blocker)
    if any(item.get("bad_oi_policy_row_count", 0) for item in dataset_summaries):
        alpha_blockers.append("bad_oi_canonical_policy_detected")
    if any(
        str(item.get("dataset_profile") or "") in {"cross_sectional_daily_4h", "cross_sectional_intraday_1h"}
        and not bool((item.get("research_dataset") or {}).get("minimum_executable_history_passed"))
        for item in dataset_summaries
    ):
        alpha_blockers.append("minimum_executable_history_failed")
    return with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "artifact_family": artifact_family,
            "as_of": as_of,
            "status": "pass_alpha_blocked" if alpha_blockers else "pass",
            "alpha_rerun_allowed": False if alpha_blockers else bool(dict(reset.get("decision") or {}).get("alpha_rerun_allowed", False)),
            "alpha_blockers": _dedupe(alpha_blockers),
            "smoke_artifacts_root": str(resolved_smoke_root),
            "canonical_input_policy": {
                "ohlcv_external_root": str(resolved_ohlcv_root),
                "spot_ohlcv_external_root": str(resolved_spot_ohlcv_root) if resolved_spot_ohlcv_root else None,
                "spot_ohlc_source": spot_ohlc_source,
                "coinglass_spot_ohlc_consumed": bool(coinglass_spot_ohlc_consumed),
                "spot_ohlc_trust_status": spot_ohlc_trust_status,
                "quarantine_reason": quarantine_reason,
                "oi_sidecar_policy": "open_interest_value may be overlaid from CoinGlass native USD sidecar",
                "derived_oi_policy": "metadata-only quarantine; not promoted into open_interest",
            },
            "universe": {
                "path": str(universe_snapshot.get("path") or ""),
                "candidate_count": len(universe_candidates),
                "executable_perp_count": sum(1 for item in universe_candidates if item.usdm_symbol and item.first_perp_bar_utc),
            },
            "derivatives_sync": {
                "path": str(derivatives_sync_path),
                "provider": derivatives_sync.get("provider"),
                "status": derivatives_sync.get("status"),
                "warning_count": derivatives_sync.get("warning_count"),
                "warning_codes": derivatives_sync.get("warning_codes"),
            },
            "coverage_reset_decision": dict(reset.get("decision") or {}),
            "dataset_summaries": dataset_summaries,
            "feature_summaries": feature_summaries,
        },
        evidence_family=artifact_family,
        contract_version=contract_version,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )


def _summarize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    frame = dataset["raw_dataframe"].copy()
    source_counts = _value_counts(frame, "open_interest_value_source")
    policy_counts = _value_counts(frame, "open_interest_value_canonical_policy")
    formula_counts = _value_counts(frame, "derived_native_formula_status")
    research_dataset = dict(dataset.get("research_dataset") or {})
    data_readiness = dict(dataset.get("data_readiness") or {})
    return {
        "dataset_id": str(dataset.get("dataset_id") or ""),
        "shape": str(dataset.get("shape") or ""),
        "dataset_profile": str(dataset.get("dataset_profile") or ""),
        "primary_interval": str(dataset.get("primary_interval") or ""),
        "row_count": int(len(frame)),
        "subject_count": int(frame["subject"].nunique()) if not frame.empty and "subject" in frame.columns else 0,
        "min_timestamp_utc": str(frame["timestamp_utc"].min()) if not frame.empty and "timestamp_utc" in frame.columns else None,
        "max_timestamp_utc": str(frame["timestamp_utc"].max()) if not frame.empty and "timestamp_utc" in frame.columns else None,
        "missing_spot_symbols_by_interval": dict(
            (data_readiness.get("spot_subject_coverage") or {}).get("missing_spot_symbols_by_interval") or {}
        ),
        "data_gap_blockers": list(data_readiness.get("data_gap_blockers") or []),
        "dataset_lane_eligible": data_readiness.get("dataset_lane_eligible"),
        "spot_subject_coverage": dict(data_readiness.get("spot_subject_coverage") or {}),
        "research_dataset": {
            "required_sidecar_families_present": research_dataset.get("required_sidecar_families_present"),
            "missing_required_sidecar_families": research_dataset.get("missing_required_sidecar_families"),
            "minimum_executable_history_passed": research_dataset.get("minimum_executable_history_passed"),
            "minimum_executable_history_subject_coverage": research_dataset.get("minimum_executable_history_subject_coverage"),
            "perp_executable_subject_count": research_dataset.get("perp_executable_subject_count"),
            "open_interest_coverage": research_dataset.get("open_interest_coverage"),
            "sidecar_fingerprint_families": sorted(dict(research_dataset.get("sidecar_fingerprints") or {}).keys()),
        },
        "oi_sidecar": {
            "native_usd_row_count": _non_null_count(frame, "open_interest_value_native_usd"),
            "selected_oi_value_row_count": _non_null_count(frame, "open_interest_value"),
            "source_counts": source_counts,
            "canonical_policy_counts": policy_counts,
            "derived_native_formula_status_counts": formula_counts,
        },
        "bad_oi_policy_row_count": _bad_oi_policy_row_count(frame),
        "manifest_path": str(dataset.get("manifest_path") or ""),
    }


def _dataset_data_gap_blockers(dataset_summaries: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for item in dataset_summaries:
        blockers.extend(str(blocker) for blocker in list(item.get("data_gap_blockers") or []) if str(blocker).strip())
    return _dedupe(blockers)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        output.append(normalized)
        seen.add(normalized)
    return output


def _summarize_feature_set(feature_set: dict[str, Any]) -> dict[str, Any]:
    quality = dict(feature_set.get("derivatives_feature_quality") or {})
    features = dict(quality.get("features") or {})
    return {
        "feature_set_id": str(feature_set.get("feature_set_id") or ""),
        "dataset_id": str(feature_set.get("dataset_id") or ""),
        "dataset_profile": str(feature_set.get("dataset_profile") or ""),
        "row_count": int(len(feature_set.get("dataframe"))),
        "numeric_feature_count": len(list(feature_set.get("numeric_feature_columns") or [])),
        "excluded_numeric_count": len(list(feature_set.get("excluded_numeric_columns") or [])),
        "label_contract_id": str(feature_set.get("label_contract_id") or ""),
        "target_horizon_bars": feature_set.get("target_horizon_bars"),
        "derivatives_feature_quality": {
            "interval": quality.get("interval"),
            "oi_change_5": _feature_quality_summary(features.get("oi_change_5")),
            "funding_zscore_20": _feature_quality_summary(features.get("funding_zscore_20")),
            "basis_zscore_20": _feature_quality_summary(features.get("basis_zscore_20")),
            "funding_minus_open_interest_gap_days": dict(quality.get("funding_minus_open_interest_gap_days") or {}),
        },
        "manifest_path": str(feature_set.get("manifest_path") or ""),
    }


def _feature_quality_summary(payload: Any) -> dict[str, Any]:
    item = dict(payload or {})
    return {
        "row_source_fraction": item.get("row_source_fraction"),
        "row_ready_fraction": item.get("row_ready_fraction"),
        "subject_ready_count": item.get("subject_ready_count"),
        "ready_coverage_days": dict(item.get("ready_coverage_days") or {}),
        "warning_counts": dict(item.get("warning_counts") or {}),
    }


def _non_null_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").notna().sum())


def _value_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if frame.empty or column not in frame.columns:
        return {}
    counter: Counter[str] = Counter()
    for value in frame[column].dropna().tolist():
        text = str(value).strip()
        if text:
            counter[text] += 1
    return dict(sorted(counter.items()))


def _bad_oi_policy_row_count(frame: pd.DataFrame) -> int:
    if frame.empty or "open_interest_value_native_usd" not in frame.columns:
        return 0
    native_mask = pd.to_numeric(frame["open_interest_value_native_usd"], errors="coerce").notna()
    if not bool(native_mask.any()):
        return 0
    if "open_interest_value_canonical_policy" not in frame.columns:
        return int(native_mask.sum())
    policy = frame["open_interest_value_canonical_policy"].astype("string").fillna("")
    return int((native_mask & policy.ne("native_usd_only")).sum())


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass Dataset Feature Smoke 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Status: `{payload['status']}`.",
        f"- Alpha rerun allowed: `{payload['alpha_rerun_allowed']}`.",
        f"- Alpha blockers: `{', '.join(payload['alpha_blockers']) if payload['alpha_blockers'] else 'none'}`.",
        f"- Smoke artifacts root: `{payload['smoke_artifacts_root']}`.",
        f"- Spot OHLC source: `{payload['canonical_input_policy']['spot_ohlc_source']}`.",
        f"- Spot OHLC trust status: `{payload['canonical_input_policy'].get('spot_ohlc_trust_status')}`.",
        f"- Spot OHLC external root: `{payload['canonical_input_policy'].get('spot_ohlcv_external_root')}`.",
        f"- CoinGlass spot OHLC consumed: `{payload['canonical_input_policy']['coinglass_spot_ohlc_consumed']}`.",
        f"- Quarantine reason: `{payload['canonical_input_policy'].get('quarantine_reason') or 'none'}`.",
        f"- OI sidecar policy: `{payload['canonical_input_policy']['oi_sidecar_policy']}`.",
        "",
        "## Datasets",
        "",
        "| dataset | profile | rows | subjects | lane eligible | data blockers | OI native rows | bad OI policy | min history passed | sidecar families |",
        "| --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in payload["dataset_summaries"]:
        research = dict(item["research_dataset"])
        oi = dict(item["oi_sidecar"])
        lines.append(
            f"| {item['dataset_id']} | {item['dataset_profile']} | {item['row_count']} | {item['subject_count']} | "
            f"{item['dataset_lane_eligible']} | {', '.join(item['data_gap_blockers']) if item['data_gap_blockers'] else 'none'} | "
            f"{oi['native_usd_row_count']} | {item['bad_oi_policy_row_count']} | "
            f"{research.get('minimum_executable_history_passed')} | {', '.join(research.get('sidecar_fingerprint_families') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Features",
            "",
            "| feature set | profile | rows | numeric features | horizon | OI ready frac | OI subject ready | funding ready frac | basis ready frac |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["feature_summaries"]:
        quality = dict(item["derivatives_feature_quality"])
        oi = dict(quality.get("oi_change_5") or {})
        funding = dict(quality.get("funding_zscore_20") or {})
        basis = dict(quality.get("basis_zscore_20") or {})
        lines.append(
            f"| {item['feature_set_id']} | {item['dataset_profile']} | {item['row_count']} | "
            f"{item['numeric_feature_count']} | {item['target_horizon_bars']} | "
            f"{oi.get('row_ready_fraction')} | {oi.get('subject_ready_count')} | "
            f"{funding.get('row_ready_fraction')} | {basis.get('row_ready_fraction')} |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "This smoke only proves the compiler can build datasets/features under the declared input policy. It does not authorize alpha reruns while strict spot OHLC provider concordance remains failed or any spot OHLC input is quarantined.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build dataset/feature smoke artifacts for CoinGlass reset without running alpha experiments.")
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument(
        "--smoke-artifacts-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "coinglass" / "dataset_feature_smoke_2026-05-04",
    )
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument("--daily-target-horizons", nargs="+", type=int, default=list(HYPOTHESIS_BATCH_TARGET_HORIZONS))
    parser.add_argument("--json-out", type=Path, default=JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=REPORT_OUT)
    parser.add_argument("--artifact-family", default="coinglass_dataset_feature_smoke")
    parser.add_argument("--contract-version", default="coinglass_dataset_feature_smoke.v1")
    parser.add_argument("--feature-set-version", default="coinglass-smoke-v1")
    parser.add_argument("--spot-ohlc-source", default="binance_ohlcv")
    parser.add_argument("--coinglass-spot-ohlc-consumed", action="store_true")
    parser.add_argument("--spot-ohlc-trust-status", default="canonical")
    parser.add_argument("--quarantine-reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_payload(
        as_of=args.as_of,
        artifacts_root=args.artifacts_root,
        smoke_artifacts_root=args.smoke_artifacts_root,
        ohlcv_external_root=args.ohlcv_external_root,
        spot_ohlcv_external_root=args.spot_ohlcv_external_root,
        derivatives_external_root=args.derivatives_external_root,
        cross_sectional_daily_target_horizons=tuple(args.daily_target_horizons),
        artifact_family=args.artifact_family,
        contract_version=args.contract_version,
        feature_set_version=args.feature_set_version,
        spot_ohlc_source=args.spot_ohlc_source,
        coinglass_spot_ohlc_consumed=args.coinglass_spot_ohlc_consumed,
        spot_ohlc_trust_status=args.spot_ohlc_trust_status,
        quarantine_reason=args.quarantine_reason,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    args.report_out.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(args.json_out), "report": str(args.report_out), "status": payload["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
