from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .alpha_manifest import load_daily_alpha_manifest, write_daily_alpha_manifest_from_experiments
from .contracts import QuantUniverseCandidate, portable_path, read_json, resolve_portable_path, utc_now, write_json
from .experiment_status import (
    EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
    is_quarantined_experiment_status,
)
from .governance import apply_daily_governance, load_strategy_library
from .lab import (
    ROOT,
    QUANT_ARTIFACTS_ROOT,
    WORKBENCH_ROOT,
    build_quant_datasets,
    build_quant_feature_sets,
    require_derivatives_sync_summary,
    run_quant_experiments_for_strategies,
    update_alpha_registry,
)
from .overlap_rerun import load_canonical_experiments_for_as_of
from .positive_controls import build_positive_control_summary, write_positive_control_summary
from .promotion import write_promotion_decisions_for_manifest
from .research_health import write_research_quality_summary
from .runtime_support import load_quant_universe_snapshot


SINGLE_ASSET_REPAIR_CONTRACT_VERSION = "quant_single_asset_repair.v1"
SINGLE_ASSET_REPAIR_EVIDENCE_FAMILY = "quant_single_asset_repair"
DEFAULT_REPAIR_AS_OFS = ("2026-04-20", "2026-04-21")
KNOWN_PRE_FIX_SINGLE_ASSET_BASELINE: dict[str, dict[str, Any]] = {
    "2026-04-20": {
        "pipeline_health": "broken",
        "control_cases": [
            {
                "control_id": "2026-04-20-single-asset-eth-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -3.9299030084670954},
                "nonzero_position_fraction": 1.0,
            },
            {
                "control_id": "2026-04-20-single-asset-jto-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -0.8209049654291123},
                "nonzero_position_fraction": 0.9935483870967742,
            },
            {
                "control_id": "2026-04-20-single-asset-sui-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -3.54701065081176},
                "nonzero_position_fraction": 1.0,
            },
        ],
    },
    "2026-04-21": {
        "pipeline_health": "broken",
        "control_cases": [
            {
                "control_id": "2026-04-21-single-asset-eth-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -3.687675518206305},
                "nonzero_position_fraction": 1.0,
            },
            {
                "control_id": "2026-04-21-single-asset-sui-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -5.013924149699355},
                "nonzero_position_fraction": 1.0,
            },
            {
                "control_id": "2026-04-21-single-asset-uni-strong-oracle",
                "shape": "single_asset",
                "control_kind": "strong_oracle",
                "raw_positive": False,
                "test_metrics": {"sharpe": -3.1058658781210857},
                "nonzero_position_fraction": 1.0,
            },
        ],
    },
}


def single_asset_repair_root(*, artifacts_root: Path) -> Path:
    return artifacts_root / "assessments" / "single_asset_repairs"


def single_asset_partition_path(*, artifacts_root: Path) -> Path:
    return single_asset_repair_root(artifacts_root=artifacts_root) / "pre_fix_partition.json"


def single_asset_repair_validation_path(*, artifacts_root: Path) -> Path:
    return single_asset_repair_root(artifacts_root=artifacts_root) / "repair_validation.json"


def run_single_asset_repair_rerun(
    *,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
    as_ofs: tuple[str, ...] = DEFAULT_REPAIR_AS_OFS,
    compiler_backend: str = "deterministic",
    ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()

    before_positive_controls = {
        as_of: _load_or_build_positive_control_summary(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
            now_utc=now_utc,
        )
        for as_of in as_ofs
    }
    partition = write_single_asset_pre_fix_partition(
        artifacts_root=resolved_artifacts_root,
        as_ofs=as_ofs,
    )

    rerun_results = []
    for as_of in as_ofs:
        rerun_results.append(
            _rerun_single_asset_for_as_of(
                artifacts_root=resolved_artifacts_root,
                workbench_root=resolved_workbench_root,
                as_of=as_of,
                compiler_backend=compiler_backend,
                ohlcv_external_root=ohlcv_external_root,
                derivatives_external_root=derivatives_external_root,
                now_utc=now_utc,
            )
        )

    after_positive_controls = {
        as_of: build_positive_control_summary(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
            repo_root=ROOT,
            now_utc=now_utc,
        )
        for as_of in as_ofs
    }
    validation = _write_single_asset_repair_validation(
        artifacts_root=resolved_artifacts_root,
        as_ofs=as_ofs,
        before_positive_controls=before_positive_controls,
        after_positive_controls=after_positive_controls,
    )
    _assert_single_asset_oracle_repair(after_positive_controls=after_positive_controls, as_ofs=as_ofs)
    return {
        "generated_at_utc": now_utc or utc_now(),
        "status": "success",
        "as_ofs": list(as_ofs),
        "partition_path": portable_path(single_asset_partition_path(artifacts_root=resolved_artifacts_root), repo_root=ROOT),
        "repair_validation_path": portable_path(single_asset_repair_validation_path(artifacts_root=resolved_artifacts_root), repo_root=ROOT),
        "partition": partition,
        "reruns": rerun_results,
        "repair_validation": validation,
    }


def write_single_asset_pre_fix_partition(
    *,
    artifacts_root: Path,
    as_ofs: tuple[str, ...],
) -> dict[str, Any]:
    root = single_asset_repair_root(artifacts_root=artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    payload = _build_single_asset_pre_fix_partition(
        artifacts_root=artifacts_root,
        as_ofs=as_ofs,
    )
    path = single_asset_partition_path(artifacts_root=artifacts_root)
    write_json(path, payload)
    payload["path"] = portable_path(path, repo_root=ROOT)
    return payload


def _build_single_asset_pre_fix_partition(
    *,
    artifacts_root: Path,
    as_ofs: tuple[str, ...],
) -> dict[str, Any]:
    cross_sectional_entries: list[dict[str, Any]] = []
    single_asset_entries: list[dict[str, Any]] = []
    by_as_of: dict[str, dict[str, Any]] = {}
    for as_of in as_ofs:
        manifest = load_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of)
        canonical_experiments = load_canonical_experiments_for_as_of(
            artifacts_root=artifacts_root,
            as_of=as_of,
        )
        per_as_of = {
            "cross_sectional": [],
            "single_asset": [],
        }
        for experiment in canonical_experiments:
            entry = {
                "as_of": as_of,
                "experiment_id": str(experiment.get("experiment_id") or ""),
                "strategy_id": str(experiment.get("strategy_id") or ""),
                "shape": str(experiment.get("shape") or ""),
                "experiment_status": str(experiment.get("experiment_status") or ""),
                "validation": str(experiment.get("validation") or ""),
                "publication_status": str(experiment.get("publication_status") or ""),
                "alpha_card_path": portable_path(Path(str(experiment.get("alpha_card_path"))), repo_root=ROOT),
            }
            if entry["shape"] == "single_asset":
                single_asset_entries.append(entry)
                per_as_of["single_asset"].append(entry)
            else:
                cross_sectional_entries.append(entry)
                per_as_of["cross_sectional"].append(entry)
        by_as_of[as_of] = {
            "manifest_entry_count": int(manifest.get("entry_count") or 0),
            "cross_sectional_count": len(per_as_of["cross_sectional"]),
            "single_asset_count": len(per_as_of["single_asset"]),
            "cross_sectional_experiment_ids": [item["experiment_id"] for item in per_as_of["cross_sectional"]],
            "single_asset_experiment_ids": [item["experiment_id"] for item in per_as_of["single_asset"]],
        }
    return with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "as_ofs": list(as_ofs),
            "downgrade_status": EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
            "cross_sectional_count": len(cross_sectional_entries),
            "single_asset_count": len(single_asset_entries),
            "total_canonical_count": len(cross_sectional_entries) + len(single_asset_entries),
            "cross_sectional_entries": cross_sectional_entries,
            "single_asset_entries": single_asset_entries,
            "by_as_of": by_as_of,
        },
        evidence_family=SINGLE_ASSET_REPAIR_EVIDENCE_FAMILY,
        contract_version=SINGLE_ASSET_REPAIR_CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )


def _rerun_single_asset_for_as_of(
    *,
    artifacts_root: Path,
    workbench_root: Path,
    as_of: str,
    compiler_backend: str,
    ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
    now_utc: str | None,
) -> dict[str, Any]:
    require_derivatives_sync_summary(
        as_of=as_of,
        derivatives_external_root=derivatives_external_root,
    )
    existing_experiments = load_canonical_experiments_for_as_of(
        artifacts_root=artifacts_root,
        as_of=as_of,
    )
    cross_sectional_experiments = [experiment for experiment in existing_experiments if str(experiment.get("shape") or "") == "cross_sectional"]
    single_asset_experiments = [experiment for experiment in existing_experiments if str(experiment.get("shape") or "") == "single_asset"]

    legacy_records = _archive_pre_fix_single_asset_experiments(
        artifacts_root=artifacts_root,
        as_of=as_of,
        experiments=single_asset_experiments,
    )

    universe_snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=artifacts_root)
    universe_candidates = tuple(
        QuantUniverseCandidate.from_payload(item)
        for item in universe_snapshot.get("candidates", [])
        if isinstance(item, dict)
    )
    datasets = build_quant_datasets(
        as_of=as_of,
        artifacts_root=artifacts_root,
        universe_candidates=universe_candidates,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=None,
        derivatives_external_root=derivatives_external_root,
    )
    feature_sets = build_quant_feature_sets(
        artifacts_root=artifacts_root,
        datasets=datasets,
    )
    strategies = _single_asset_rerun_strategies(
        artifacts_root=artifacts_root,
        experiments=single_asset_experiments,
    )
    rerun_experiments = run_quant_experiments_for_strategies(
        as_of=as_of,
        artifacts_root=artifacts_root,
        strategies=strategies,
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    combined_experiments = cross_sectional_experiments + rerun_experiments
    strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    governance_summary = apply_daily_governance(
        artifacts_root=artifacts_root,
        strategy_library=strategy_library,
        experiments=combined_experiments,
        as_of=as_of,
    )
    manifest = write_daily_alpha_manifest_from_experiments(
        artifacts_root=artifacts_root,
        as_of=as_of,
        experiments=combined_experiments,
    )
    refreshed_strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    promotion_decisions = write_promotion_decisions_for_manifest(
        artifacts_root=artifacts_root,
        as_of=as_of,
        strategy_library=refreshed_strategy_library,
    )
    registry = update_alpha_registry(
        artifacts_root=artifacts_root,
        as_of=as_of,
        experiments=combined_experiments,
    )
    from .bridge import export_passed_alphas_to_workbench

    bridge_summary = export_passed_alphas_to_workbench(
        as_of=as_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
        ohlcv_external_root=ohlcv_external_root,
        queue="quant",
    )
    research_quality = write_research_quality_summary(
        path=artifacts_root / "cycles" / as_of / "research_quality_summary.json",
        experiments=combined_experiments,
        artifacts_root=artifacts_root,
        scope="daily_cycle",
        as_of=as_of,
        canonical_universe_count=int(manifest.get("entry_count") or len(manifest.get("entries", []))),
    )
    positive_control = write_positive_control_summary(
        as_of=as_of,
        artifacts_root=artifacts_root,
        repo_root=ROOT,
        now_utc=now_utc,
    )
    return {
        "as_of": as_of,
        "legacy_single_asset_count": len(legacy_records),
        "fresh_single_asset_count": len(rerun_experiments),
        "cross_sectional_count": len(cross_sectional_experiments),
        "governance": governance_summary,
        "daily_alpha_manifest_path": portable_path(Path(str(manifest["path"])), repo_root=ROOT),
        "research_quality_summary_path": research_quality["research_quality_summary_path"],
        "registry_path": registry["registry_path"],
        "promotion_decision_count": len(promotion_decisions),
        "bridge_summary_path": bridge_summary["bridge_summary_path"],
        "positive_control_summary_path": portable_path(
            artifacts_root / "assessments" / "positive_controls" / as_of / "positive_control_summary.json",
            repo_root=ROOT,
        ),
    }


def _archive_pre_fix_single_asset_experiments(
    *,
    artifacts_root: Path,
    as_of: str,
    experiments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    legacy_root = artifacts_root / "experiments" / "legacy" / "single_asset_pipeline_fix" / as_of
    legacy_root.mkdir(parents=True, exist_ok=True)
    for experiment in experiments:
        experiment_id = str(experiment.get("experiment_id") or "")
        alpha_card_path = Path(str(experiment.get("alpha_card_path") or ""))
        experiment_root = alpha_card_path.parent
        if not experiment_root.exists():
            continue
        legacy_target = legacy_root / experiment_root.name
        if legacy_target.exists():
            shutil.rmtree(legacy_target)
        shutil.move(str(experiment_root), str(legacy_target))
        _rewrite_legacy_single_asset_experiment(legacy_target=legacy_target)
        records.append(
            {
                "experiment_id": experiment_id,
                "original_experiment_root": portable_path(experiment_root, repo_root=ROOT),
                "legacy_experiment_root": portable_path(legacy_target, repo_root=ROOT),
            }
        )
    return records


def _rewrite_legacy_single_asset_experiment(*, legacy_target: Path) -> None:
    alpha_card_path = legacy_target / "alpha_card.json"
    if not alpha_card_path.exists():
        return
    alpha_card = read_json(alpha_card_path)
    existing_validation = str(alpha_card.get("validation") or "").strip()
    validation = "leakage_audit_required" if existing_validation == "leakage_audit_required" else "insufficient_track_record"
    blockers = [str(item) for item in dict(alpha_card.get("quality_summary") or {}).get("quality_blockers", [])]
    rerun_blocker = "pipeline_unreliable_pending_single_asset_fix"
    if rerun_blocker not in blockers:
        blockers.append(rerun_blocker)
    alpha_card["experiment_status"] = EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX
    alpha_card["validation"] = validation
    alpha_card["publication_status"] = "archived_only"
    alpha_card["reason"] = "single_asset_pipeline_fix_pending_rerun"
    alpha_card["quality_summary"] = {
        "quality_gate_passed": False,
        "quality_blockers": blockers,
        "metrics_snapshot": dict(dict(alpha_card.get("quality_summary") or {}).get("metrics_snapshot") or {}),
    }
    write_json(alpha_card_path, alpha_card)

    for file_name in ("validation_report.json", "backtest_report.json", "experiment_spec.json"):
        report_path = legacy_target / file_name
        if not report_path.exists():
            continue
        payload = read_json(report_path)
        if not isinstance(payload, dict):
            continue
        payload["experiment_status"] = EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX
        payload["validation"] = validation
        payload["publication_status"] = "archived_only"
        payload["reason"] = "single_asset_pipeline_fix_pending_rerun"
        if file_name != "experiment_spec.json":
            payload["quality_summary"] = alpha_card["quality_summary"]
        write_json(report_path, payload)


def _single_asset_rerun_strategies(
    *,
    artifacts_root: Path,
    experiments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    entries_by_id = {
        str(entry.get("strategy_id") or ""): dict(entry)
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict)
    }
    strategies: list[dict[str, Any]] = []
    for experiment in experiments:
        strategy_id = str(experiment.get("strategy_id") or "").strip()
        entry = dict(entries_by_id.get(strategy_id) or {})
        if not entry:
            alpha_card = dict(experiment.get("alpha_card") or {})
            entry = {
                "strategy_id": strategy_id,
                "shape": str(alpha_card.get("shape") or "single_asset"),
                "strategy_profile": str(alpha_card.get("strategy_profile") or ""),
                "subject": alpha_card.get("subject"),
                "universe_filter": dict(alpha_card.get("universe_filter") or {}),
                "model_family": str(alpha_card.get("model_family") or ""),
                "feature_groups": list(alpha_card.get("feature_groups") or []),
                "profile_constraints": dict(alpha_card.get("profile_constraints") or {}),
                "profile_constraints_override": dict(alpha_card.get("profile_constraints_override") or {}),
                "source": str(alpha_card.get("source") or "baseline"),
                "lifecycle": str(alpha_card.get("lifecycle") or "active"),
                "monitoring_status": str(alpha_card.get("monitoring_status") or alpha_card.get("lifecycle") or "active"),
                "selection_lane": str(alpha_card.get("selection_lane") or alpha_card.get("monitoring_status") or "active"),
                "promotion_state": str(alpha_card.get("promotion_state") or "staged"),
                "spec_hash": str(alpha_card.get("spec_hash") or ""),
            }
        if str(entry.get("shape") or "") != "single_asset":
            continue
        strategies.append(entry)
    strategies.sort(key=lambda item: str(item.get("strategy_id") or ""))
    return strategies


def _write_single_asset_repair_validation(
    *,
    artifacts_root: Path,
    as_ofs: tuple[str, ...],
    before_positive_controls: dict[str, dict[str, Any]],
    after_positive_controls: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    root = single_asset_repair_root(artifacts_root=artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    before_positive_controls = _resolve_before_positive_controls(
        artifacts_root=artifacts_root,
        as_ofs=as_ofs,
        before_positive_controls=before_positive_controls,
    )
    post_fix_status_by_as_of = {
        as_of: _post_fix_single_asset_status_summary(
            artifacts_root=artifacts_root,
            as_of=as_of,
        )
        for as_of in as_ofs
    }
    payload = with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "as_ofs": list(as_ofs),
            "before_pipeline_health": {
                as_of: str(before_positive_controls[as_of]["pipeline_health"])
                for as_of in as_ofs
            },
            "after_pipeline_health": {
                as_of: str(after_positive_controls[as_of]["pipeline_health"])
                for as_of in as_ofs
            },
            "after_pipeline_health_rationale": {
                as_of: str(after_positive_controls[as_of].get("pipeline_health_rationale") or "")
                for as_of in as_ofs
            },
            "assessment_trust_by_as_of": {
                as_of: _assessment_trust_from_pipeline_health(after_positive_controls[as_of])
                for as_of in as_ofs
            },
            "post_fix_single_asset_status_counts": post_fix_status_by_as_of,
            "post_fix_single_asset_total_status_counts": _aggregate_single_asset_status_counts(
                per_as_of=post_fix_status_by_as_of
            ),
            "single_asset_strong_oracle": {
                as_of: _single_asset_strong_oracle_matrix(
                    before_payload=before_positive_controls[as_of],
                    after_payload=after_positive_controls[as_of],
                )
                for as_of in as_ofs
            },
        },
        evidence_family=SINGLE_ASSET_REPAIR_EVIDENCE_FAMILY,
        contract_version=SINGLE_ASSET_REPAIR_CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    path = single_asset_repair_validation_path(artifacts_root=artifacts_root)
    write_json(path, payload)
    payload["path"] = portable_path(path, repo_root=ROOT)
    return payload


def _resolve_before_positive_controls(
    *,
    artifacts_root: Path,
    as_ofs: tuple[str, ...],
    before_positive_controls: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    existing_path = single_asset_repair_validation_path(artifacts_root=artifacts_root)
    if existing_path.exists():
        existing = read_json(existing_path)
        existing_before = dict(existing.get("before_pipeline_health") or {})
        if existing_before and all(str(existing_before.get(as_of) or "") == "broken" for as_of in as_ofs):
            reconstructed: dict[str, dict[str, Any]] = {}
            for as_of in as_ofs:
                existing_matrix = list(dict(existing.get("single_asset_strong_oracle") or {}).get(as_of, []))
                reconstructed[as_of] = {
                    "pipeline_health": "broken",
                    "control_cases": [
                        {
                            "control_id": str(record.get("control_id") or ""),
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "raw_positive": bool(record.get("before_raw_positive")),
                            "test_metrics": {"sharpe": record.get("before_test_sharpe")},
                            "nonzero_position_fraction": record.get("before_nonzero_position_fraction"),
                        }
                        for record in existing_matrix
                    ],
                }
            return reconstructed
    if all(as_of in KNOWN_PRE_FIX_SINGLE_ASSET_BASELINE for as_of in as_ofs):
        return {
            as_of: {
                "pipeline_health": str(KNOWN_PRE_FIX_SINGLE_ASSET_BASELINE[as_of]["pipeline_health"]),
                "control_cases": list(KNOWN_PRE_FIX_SINGLE_ASSET_BASELINE[as_of]["control_cases"]),
            }
            for as_of in as_ofs
        }
    return before_positive_controls


def _assessment_trust_from_pipeline_health(payload: dict[str, Any]) -> str:
    pipeline_health = str(payload.get("pipeline_health") or "")
    if pipeline_health == "healthy":
        return "trusted"
    if pipeline_health == "marginal":
        return "trusted_with_weak_oracle_headroom_limit"
    return "untrusted"


def _post_fix_single_asset_status_summary(*, artifacts_root: Path, as_of: str) -> dict[str, Any]:
    manifest = load_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of)
    counts: dict[str, int] = {}
    experiment_ids_by_status: dict[str, list[str]] = {}
    total = 0
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("shape") or "") != "single_asset":
            continue
        alpha_card_path = resolve_portable_path(str(entry.get("alpha_card_path") or ""), repo_root=ROOT)
        if not alpha_card_path.exists():
            continue
        alpha_card = read_json(alpha_card_path)
        status = str(alpha_card.get("experiment_status") or "")
        counts[status] = counts.get(status, 0) + 1
        experiment_ids_by_status.setdefault(status, []).append(str(entry.get("experiment_id") or ""))
        total += 1
    for ids in experiment_ids_by_status.values():
        ids.sort()
    return {
        "single_asset_count": total,
        "status_counts": {key: counts[key] for key in sorted(counts)},
        "experiment_ids_by_status": {key: experiment_ids_by_status[key] for key in sorted(experiment_ids_by_status)},
    }


def _aggregate_single_asset_status_counts(*, per_as_of: dict[str, dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for payload in per_as_of.values():
        for status, count in dict(payload.get("status_counts") or {}).items():
            totals[str(status)] = totals.get(str(status), 0) + int(count)
    return {key: totals[key] for key in sorted(totals)}


def _single_asset_strong_oracle_matrix(
    *,
    before_payload: dict[str, Any],
    after_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    before_cases = {
        str(case.get("control_id") or ""): case
        for case in before_payload.get("control_cases", [])
        if str(case.get("shape") or "") == "single_asset" and str(case.get("control_kind") or "") == "strong_oracle"
    }
    after_cases = {
        str(case.get("control_id") or ""): case
        for case in after_payload.get("control_cases", [])
        if str(case.get("shape") or "") == "single_asset" and str(case.get("control_kind") or "") == "strong_oracle"
    }
    records: list[dict[str, Any]] = []
    for control_id in sorted(set(before_cases) | set(after_cases)):
        before_case = before_cases.get(control_id, {})
        after_case = after_cases.get(control_id, {})
        records.append(
            {
                "control_id": control_id,
                "before_raw_positive": before_case.get("raw_positive"),
                "after_raw_positive": after_case.get("raw_positive"),
                "before_test_sharpe": _metric_value(before_case, "test_metrics", "sharpe"),
                "after_test_sharpe": _metric_value(after_case, "test_metrics", "sharpe"),
                "before_nonzero_position_fraction": before_case.get("nonzero_position_fraction"),
                "after_nonzero_position_fraction": after_case.get("nonzero_position_fraction"),
            }
        )
    return records


def _metric_value(payload: dict[str, Any], metrics_key: str, key: str) -> Any:
    metrics = payload.get(metrics_key)
    if not isinstance(metrics, dict):
        return None
    return metrics.get(key)


def _assert_single_asset_oracle_repair(
    *,
    after_positive_controls: dict[str, dict[str, Any]],
    as_ofs: tuple[str, ...],
) -> None:
    failures: list[str] = []
    for as_of in as_ofs:
        payload = after_positive_controls[as_of]
        if str(payload.get("pipeline_health") or "") == "broken":
            failures.append(f"{as_of}: pipeline_health is still broken")
        for case in payload.get("control_cases", []):
            if str(case.get("shape") or "") != "single_asset":
                continue
            if str(case.get("control_kind") or "") != "strong_oracle":
                continue
            if case.get("raw_positive") is not True:
                failures.append(f"{as_of}: {case.get('control_id')} did not become raw_positive")
    if failures:
        raise RuntimeError("single-asset oracle repair validation failed: " + " | ".join(failures))


def _load_or_build_positive_control_summary(
    *,
    as_of: str,
    artifacts_root: Path,
    now_utc: str | None,
) -> dict[str, Any]:
    path = artifacts_root / "assessments" / "positive_controls" / as_of / "positive_control_summary.json"
    if path.exists():
        return read_json(path)
    return build_positive_control_summary(
        as_of=as_of,
        artifacts_root=artifacts_root,
        repo_root=ROOT,
        now_utc=now_utc,
    )
