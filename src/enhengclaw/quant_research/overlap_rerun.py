from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import Any

from .alpha_manifest import daily_alpha_manifest_root, load_daily_alpha_manifest, write_daily_alpha_manifest
from .bridge import export_passed_alphas_to_workbench
from .contracts import portable_path, read_json, resolve_portable_path, utc_now, write_json
from .experiment_status import EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
from .governance import load_strategy_library, save_strategy_library
from .lab import ROOT, QUANT_ARTIFACTS_ROOT, WORKBENCH_ROOT, update_alpha_registry
from .promotion import write_promotion_decisions_for_manifest
from .research_health import build_research_quality_summary, write_research_quality_summary
from .validation_contract import VALIDATION_CONTRACT_VERSION


def overlap_rerun_root(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "assessments" / "overlap_reruns" / as_of


def overlap_rerun_baseline_path(*, artifacts_root: Path, as_of: str) -> Path:
    return overlap_rerun_root(artifacts_root=artifacts_root, as_of=as_of) / "pre_rerun_snapshot.json"


def overlap_rerun_comparison_path(*, artifacts_root: Path, as_of: str) -> Path:
    return overlap_rerun_root(artifacts_root=artifacts_root, as_of=as_of) / "rerun_comparison.json"


def discover_experiments_needing_overlap_rerun(
    *,
    artifacts_root: Path | None = None,
    as_of: str | None = None,
) -> dict[str, list[str]]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    if as_of is not None:
        manifest_dates = [as_of]
    else:
        manifest_dates = _available_daily_manifest_dates(artifacts_root=resolved_artifacts_root)
    affected: dict[str, list[str]] = {}
    for manifest_as_of in manifest_dates:
        experiment_ids = affected_experiment_ids_for_as_of(
            artifacts_root=resolved_artifacts_root,
            as_of=manifest_as_of,
        )
        if experiment_ids:
            affected[manifest_as_of] = experiment_ids
    return affected


def affected_experiment_ids_for_as_of(
    *,
    artifacts_root: Path | None = None,
    as_of: str,
) -> list[str]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    experiments = load_canonical_experiments_for_as_of(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    affected_ids: list[str] = []
    for experiment in experiments:
        alpha_card = dict(experiment.get("alpha_card") or {})
        validation_report = dict(experiment.get("validation_report") or {})
        experiment_id = str(experiment.get("experiment_id") or alpha_card.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        if _legacy_overlap_rerun_required(alpha_card=alpha_card, validation_report=validation_report):
            affected_ids.append(experiment_id)
    return sorted(set(affected_ids))


def remediate_historical_overlap_reruns(
    *,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    affected_by_as_of = discover_experiments_needing_overlap_rerun(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    per_as_of: list[dict[str, Any]] = []
    for target_as_of in sorted(affected_by_as_of):
        affected_experiment_ids = affected_by_as_of[target_as_of]
        rerun_summary = mark_experiments_needing_overlap_rerun(
            artifacts_root=resolved_artifacts_root,
            workbench_root=resolved_workbench_root,
            as_of=target_as_of,
            experiment_ids=affected_experiment_ids,
        )
        comparison = write_overlap_rerun_comparison(
            artifacts_root=resolved_artifacts_root,
            as_of=target_as_of,
        )
        per_as_of.append(
            {
                "as_of": target_as_of,
                "affected_experiment_ids": affected_experiment_ids,
                "affected_experiment_count": len(affected_experiment_ids),
                "baseline_snapshot_path": rerun_summary["baseline_snapshot_path"],
                "comparison_path": comparison["path"],
                "daily_alpha_manifest_path": rerun_summary["daily_alpha_manifest_path"],
                "research_quality_summary_path": rerun_summary["research_quality_summary_path"],
                "bridge_summary_path": rerun_summary["bridge_summary_path"],
            }
        )
    return {
        "status": "success",
        "generated_at_utc": utc_now(),
        "requested_as_of": as_of,
        "affected_dates": [entry["as_of"] for entry in per_as_of],
        "affected_experiment_count": sum(int(entry["affected_experiment_count"]) for entry in per_as_of),
        "per_as_of": per_as_of,
    }


def capture_overlap_rerun_baseline(
    *,
    artifacts_root: Path | None = None,
    as_of: str,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    experiments = load_canonical_experiments_for_as_of(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    snapshot = _build_overlap_rerun_snapshot(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        experiments=experiments,
        snapshot_kind="pre_rerun",
    )
    path = overlap_rerun_baseline_path(artifacts_root=resolved_artifacts_root, as_of=as_of)
    write_json(path, snapshot)
    snapshot["path"] = portable_path(path, repo_root=ROOT)
    return snapshot


def mark_experiments_needing_overlap_rerun(
    *,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
    as_of: str,
    experiment_ids: Collection[str] | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    requested_experiment_ids = (
        {
            str(experiment_id).strip()
            for experiment_id in experiment_ids
            if str(experiment_id).strip()
        }
        if experiment_ids is not None
        else None
    )
    baseline = capture_overlap_rerun_baseline(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    manifest = load_daily_alpha_manifest(artifacts_root=resolved_artifacts_root, as_of=as_of)
    manifest_entries_by_id = {
        str(entry.get("experiment_id") or ""): dict(entry)
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("experiment_id") or "").strip()
    }
    strategy_library = load_strategy_library(artifacts_root=resolved_artifacts_root)
    strategy_entries_by_id = {
        str(entry.get("strategy_id") or ""): entry
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }
    rewritten_experiment_ids: list[str] = []
    for experiment_id, manifest_entry in manifest_entries_by_id.items():
        if requested_experiment_ids is not None and experiment_id not in requested_experiment_ids:
            continue
        alpha_card_path = resolve_portable_path(str(manifest_entry["alpha_card_path"]), repo_root=ROOT)
        experiment_root = alpha_card_path.parent
        alpha_card = read_json(alpha_card_path)
        strategy_id = str(alpha_card.get("strategy_id") or manifest_entry.get("strategy_id") or "").strip()
        existing_validation = str(alpha_card.get("validation") or "").strip()
        validation = "leakage_audit_required" if existing_validation == "leakage_audit_required" else "insufficient_track_record"
        overlap_integrity = dict(alpha_card.get("overlap_integrity") or {})
        quality_summary = dict(alpha_card.get("quality_summary") or {})
        existing_blockers = [str(item) for item in quality_summary.get("quality_blockers", [])]
        rerun_blocker = "overlap_fix_pending_rerun"
        if rerun_blocker not in existing_blockers:
            existing_blockers.append(rerun_blocker)

        alpha_card["experiment_status"] = EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
        alpha_card["validation"] = validation
        alpha_card["publication_status"] = "archived_only"
        alpha_card["quality_summary"] = {
            "quality_gate_passed": False,
            "quality_blockers": existing_blockers,
            "metrics_snapshot": dict(quality_summary.get("metrics_snapshot") or {}),
        }
        alpha_card["reason"] = "overlap_fix_pending_rerun"
        write_json(alpha_card_path, alpha_card)

        for file_name in ("validation_report.json", "backtest_report.json", "experiment_spec.json"):
            report_path = experiment_root / file_name
            if not report_path.exists():
                continue
            payload = read_json(report_path)
            if not isinstance(payload, dict):
                continue
            payload["experiment_status"] = EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
            payload["validation"] = validation
            payload["publication_status"] = "archived_only"
            payload["reason"] = "overlap_fix_pending_rerun"
            if "overlap_integrity" not in payload and overlap_integrity:
                payload["overlap_integrity"] = overlap_integrity
            if file_name != "experiment_spec.json":
                payload["quality_summary"] = alpha_card["quality_summary"]
            write_json(report_path, payload)

        manifest_entry["experiment_status"] = EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
        manifest_entries_by_id[experiment_id] = manifest_entry

        if strategy_id and strategy_id in strategy_entries_by_id:
            strategy_entry = strategy_entries_by_id[strategy_id]
            strategy_entry["last_daily_as_of"] = as_of
            strategy_entry["last_daily_experiment_status"] = EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
            strategy_entry["daily_pass_streak"] = 0
            strategy_entry["daily_fail_streak"] = 0
            strategy_entry["watch_pass_streak"] = 0
            strategy_entry["daily_result_window"] = []
            strategy_entry["watch_result_window"] = []
            strategy_entry["last_transition_reason"] = "awaiting_overlap_rerun"
            strategy_entry["updated_at_utc"] = utc_now()

        rewritten_experiment_ids.append(experiment_id)

    if not rewritten_experiment_ids:
        return {
            "status": "success",
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "baseline_snapshot_path": baseline["path"],
            "rewritten_experiment_count": 0,
            "rewritten_experiment_ids": [],
            "strategy_library_path": portable_path(Path(str(strategy_library["path"])), repo_root=ROOT),
            "daily_alpha_manifest_path": portable_path(
                resolved_artifacts_root / "governance" / "daily_alpha_manifests" / f"{as_of}.json",
                repo_root=ROOT,
            ),
            "research_quality_summary_path": portable_path(
                resolved_artifacts_root / "cycles" / as_of / "research_quality_summary.json",
                repo_root=ROOT,
            ),
            "promotion_decision_count": 0,
            "bridge_summary_path": portable_path(
                resolved_artifacts_root / "bridge_exports" / as_of / "bridge_summary.json",
                repo_root=ROOT,
            ),
        }

    write_daily_alpha_manifest(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        entries=[manifest_entries_by_id[key] for key in sorted(manifest_entries_by_id)],
    )
    strategy_library["generated_at_utc"] = utc_now()
    save_strategy_library(artifacts_root=resolved_artifacts_root, payload=strategy_library)
    canonical_experiments = load_canonical_experiments_for_as_of(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    registry = update_alpha_registry(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        experiments=canonical_experiments,
    )
    research_quality_path = resolved_artifacts_root / "cycles" / as_of / "research_quality_summary.json"
    research_quality = write_research_quality_summary(
        path=research_quality_path,
        experiments=canonical_experiments,
        artifacts_root=resolved_artifacts_root,
        scope="daily_cycle",
        as_of=as_of,
        canonical_universe_count=len(canonical_experiments),
    )
    refreshed_strategy_library = load_strategy_library(artifacts_root=resolved_artifacts_root)
    promotion_decisions = write_promotion_decisions_for_manifest(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        strategy_library=refreshed_strategy_library,
    )
    bridge_summary = export_passed_alphas_to_workbench(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        workbench_root=resolved_workbench_root,
        queue="quant",
    )
    return {
        "status": "success",
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "baseline_snapshot_path": baseline["path"],
        "rewritten_experiment_count": len(rewritten_experiment_ids),
        "rewritten_experiment_ids": rewritten_experiment_ids,
        "strategy_library_path": portable_path(Path(str(refreshed_strategy_library["path"])), repo_root=ROOT),
        "registry_path": registry["registry_path"],
        "daily_alpha_manifest_path": portable_path(
            resolved_artifacts_root / "governance" / "daily_alpha_manifests" / f"{as_of}.json",
            repo_root=ROOT,
        ),
        "research_quality_summary_path": research_quality["research_quality_summary_path"],
        "promotion_decision_count": len(promotion_decisions),
        "bridge_summary_path": bridge_summary["bridge_summary_path"],
    }


def write_overlap_rerun_comparison(
    *,
    artifacts_root: Path | None = None,
    as_of: str,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    baseline_path = overlap_rerun_baseline_path(artifacts_root=resolved_artifacts_root, as_of=as_of)
    if not baseline_path.exists():
        raise FileNotFoundError(f"overlap rerun baseline snapshot is missing for as_of={as_of}: {baseline_path}")
    baseline = read_json(baseline_path)
    experiments = load_canonical_experiments_for_as_of(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    after = _build_overlap_rerun_snapshot(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        experiments=experiments,
        snapshot_kind="post_rerun",
    )
    comparison = {
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "baseline_snapshot_path": portable_path(baseline_path, repo_root=ROOT),
        "before": baseline,
        "after": after,
        "comparison": {
            "experiment_status_counts": {
                "before": dict(baseline.get("experiment_status_counts") or {}),
                "after": dict(after.get("experiment_status_counts") or {}),
            },
            "raw_pass_rate": {
                "before": baseline.get("raw_pass_rate"),
                "after": after.get("raw_pass_rate"),
            },
            "audit_cleared_pass_rate": {
                "before": baseline.get("audit_cleared_pass_rate"),
                "after": after.get("audit_cleared_pass_rate"),
            },
            "cross_sectional_median_oos_sharpe": {
                "before": _summary_median(baseline.get("cross_sectional_median_oos_sharpe")),
                "after": _summary_median(after.get("cross_sectional_median_oos_sharpe")),
            },
            "sharpe_anomaly_candidates": {
                "before": [str(item.get("experiment_id") or "") for item in baseline.get("sharpe_anomaly_candidates", [])],
                "after": [str(item.get("experiment_id") or "") for item in after.get("sharpe_anomaly_candidates", [])],
            },
        },
    }
    path = overlap_rerun_comparison_path(artifacts_root=resolved_artifacts_root, as_of=as_of)
    write_json(path, comparison)
    comparison["path"] = portable_path(path, repo_root=ROOT)
    return comparison


def load_canonical_experiments_for_as_of(
    *,
    artifacts_root: Path | None = None,
    as_of: str,
) -> list[dict[str, Any]]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    manifest = load_daily_alpha_manifest(artifacts_root=resolved_artifacts_root, as_of=as_of)
    experiments: list[dict[str, Any]] = []
    for entry in manifest.get("entries", []):
        alpha_card_path = resolve_portable_path(str(entry.get("alpha_card_path") or ""), repo_root=ROOT)
        alpha_card = read_json(alpha_card_path)
        experiments.append(
            _experiment_payload_from_alpha_card(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
            )
        )
    return experiments


def _build_overlap_rerun_snapshot(
    *,
    artifacts_root: Path,
    as_of: str,
    experiments: list[dict[str, Any]],
    snapshot_kind: str,
) -> dict[str, Any]:
    quality = build_research_quality_summary(
        experiments=experiments,
        artifacts_root=artifacts_root,
        scope="daily_cycle",
        as_of=as_of,
        canonical_universe_count=len(experiments),
    )
    return {
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "snapshot_kind": snapshot_kind,
        "canonical_experiment_count": len(experiments),
        "experiment_status_counts": dict(quality.get("experiment_status_counts") or {}),
        "raw_pass_rate": quality.get("raw_pass_rate"),
        "audit_cleared_pass_rate": quality.get("audit_cleared_pass_rate"),
        "cross_sectional_median_oos_sharpe": dict(quality.get("cross_sectional_median_oos_sharpe") or {}),
        "sharpe_anomaly_candidates": list(quality.get("sharpe_anomaly_candidates") or []),
    }


def _experiment_payload_from_alpha_card(*, alpha_card_path: Path, alpha_card: dict[str, Any]) -> dict[str, Any]:
    experiment_root = alpha_card_path.parent
    validation_report_path = experiment_root / "validation_report.json"
    backtest_report_path = experiment_root / "backtest_report.json"
    validation_report = read_json(validation_report_path) if validation_report_path.exists() else {}
    return {
        "experiment_id": alpha_card.get("experiment_id"),
        "shape": alpha_card.get("shape"),
        "model_family": alpha_card.get("model_family"),
        "strategy_profile": alpha_card.get("strategy_profile"),
        "subject": alpha_card.get("subject"),
        "strategy_id": alpha_card.get("strategy_id"),
        "spec_hash": alpha_card.get("spec_hash"),
        "source": alpha_card.get("source"),
        "monitoring_status": alpha_card.get("monitoring_status", alpha_card.get("lifecycle")),
        "selection_lane": alpha_card.get("selection_lane", alpha_card.get("monitoring_status", alpha_card.get("lifecycle"))),
        "promotion_state": alpha_card.get("promotion_state", "staged"),
        "compiler_backend": alpha_card.get("compiler_backend"),
        "backend_mode": alpha_card.get("backend_mode"),
        "experiment_status": alpha_card.get("experiment_status"),
        "lifecycle": alpha_card.get("lifecycle"),
        "validation": alpha_card.get("validation"),
        "publication_status": alpha_card.get("publication_status"),
        "experiment_root": str(experiment_root),
        "experiment_spec_path": str(experiment_root / "experiment_spec.json"),
        "backtest_report": read_json(backtest_report_path) if backtest_report_path.exists() else {},
        "backtest_report_path": str(backtest_report_path),
        "validation_report": validation_report,
        "validation_report_path": str(validation_report_path),
        "alpha_card": alpha_card,
        "alpha_card_path": str(alpha_card_path),
        "alpha_card_md_path": str(experiment_root / "alpha_card.md"),
        "quality_summary": alpha_card.get("quality_summary"),
        "overlap_integrity": validation_report.get("overlap_integrity") or alpha_card.get("overlap_integrity"),
    }


def _summary_median(summary: Any) -> Any:
    if isinstance(summary, dict):
        return summary.get("median")
    return None


def _available_daily_manifest_dates(*, artifacts_root: Path) -> list[str]:
    manifest_root = daily_alpha_manifest_root(artifacts_root=artifacts_root)
    if not manifest_root.exists():
        return []
    return sorted(path.stem for path in manifest_root.glob("*.json"))


def _payload_has_non_positive_bar_interval(payload: dict[str, Any]) -> bool:
    interval_ms = _payload_bar_interval_ms(payload)
    return interval_ms is not None and interval_ms <= 0


def _payload_bar_interval_ms(payload: dict[str, Any]) -> int | None:
    raw_value = payload.get("bar_interval_ms")
    if raw_value is None or raw_value == "":
        raw_value = dict(payload.get("overlap_integrity") or {}).get("bar_interval_ms")
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _legacy_overlap_rerun_required(*, alpha_card: dict[str, Any], validation_report: dict[str, Any]) -> bool:
    alpha_contract = dict(alpha_card.get("validation_contract") or {})
    report_contract = dict(validation_report.get("validation_contract") or {})
    has_split_realization_contract = bool(
        alpha_card.get("split_realization_contract")
        or validation_report.get("split_realization_contract")
        or dict(validation_report.get("split_integrity") or {}).get("split_realization_contract")
    )
    if _payload_has_non_positive_bar_interval(alpha_card) or _payload_has_non_positive_bar_interval(validation_report):
        return True
    if not has_split_realization_contract:
        return True
    if str(alpha_contract.get("contract_version") or "") != VALIDATION_CONTRACT_VERSION:
        return True
    if str(report_contract.get("contract_version") or "") != VALIDATION_CONTRACT_VERSION:
        return True
    return False
