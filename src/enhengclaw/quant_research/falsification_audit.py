from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
    portable_path,
    pit_universe_artifact_is_valid,
    pit_universe_artifact_metadata,
    read_json,
    resolve_portable_path,
    utc_now,
    write_json,
)
from .feature_admission import (
    FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_COLUMNS,
    FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES,
)


ROOT = Path(__file__).resolve().parents[3]
FALSIFICATION_AUDIT_CONTRACT_VERSION = "quant_falsification_audit.v2"
FALSIFICATION_AUDIT_STATUSES = ("cleared", "failed")
FALSIFICATION_REQUIRED_STATUS = "falsification_required"
NOT_REQUIRED_FALSIFICATION_STATUS = "not_required"
INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE = "invalidated_unverified_research_evidence"
LEGACY_PLACEHOLDER_AUDIT_MESSAGE = "placeholder audit retired; deterministic quant core requires real falsification evidence"
LEGACY_DATASET_FORBIDDEN_COLUMNS = frozenset(
    {
        "market_cap_rank",
        "market_cap_usd",
        "quote_volume_24h_usd",
        "asset_bucket",
        "event_flag_count",
        "narrative_tag_count",
    }
)
LEGACY_DATASET_FORBIDDEN_PREFIXES = ("event__", "narrative__")
MINIMUM_FALSIFICATION_BLOCKER_CODES = frozenset(
    {
        "missing_dataset_manifest",
        "missing_feature_manifest",
        "missing_universe_snapshot",
        "legacy_placeholder_audit",
        "legacy_dataset_columns_present",
        "legacy_feature_columns_present",
        "feature_admission_failed",
        "universe_metadata_mismatch",
        "subject_not_in_snapshot",
        "liquidity_bucket_mismatch",
        "split_boundary_contamination",
        "walk_forward_boundary_contamination",
        "backtest_realization_mismatch",
    }
)


class PlaceholderAuditRetiredError(RuntimeError):
    pass


def raise_placeholder_audit_retired() -> None:
    raise PlaceholderAuditRetiredError(LEGACY_PLACEHOLDER_AUDIT_MESSAGE)


def falsification_audit_path(*, experiment_root: Path) -> Path:
    return experiment_root / "falsification_audit.json"


def load_falsification_audit(*, experiment_root: Path) -> dict[str, Any] | None:
    path = falsification_audit_path(experiment_root=experiment_root)
    if not path.exists():
        return None
    payload = read_json(path)
    payload["falsification_audit_path"] = portable_path(path, repo_root=ROOT)
    return payload


def falsification_is_required(
    *,
    experiment_status: str,
    validation_contract: dict[str, Any] | None,
    blocker_codes: list[str] | None = None,
) -> bool:
    normalized_status = str(experiment_status or "").strip()
    validation_status = str((validation_contract or {}).get("status") or "").strip()
    observed_blockers = {
        str(item).strip()
        for item in list(blocker_codes or [])
        if str(item).strip()
    }
    observed_blockers.update(
        str(item.get("code") or "").strip()
        for item in list((validation_contract or {}).get("blockers") or [])
        if isinstance(item, dict) and str(item.get("code") or "").strip()
    )
    return (
        validation_status == FALSIFICATION_REQUIRED_STATUS
        or normalized_status == "quarantined"
        or "sharpe_anomaly_detected" in observed_blockers
    )


def falsification_outcome_for_skipped_audit(
    *,
    validation_contract: dict[str, Any] | None,
    universe_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    pit_valid = pit_universe_artifact_is_valid(universe_metadata)
    validation_status = str((validation_contract or {}).get("status") or "").strip()
    credible = pit_valid and validation_status not in {"failed", "incomplete", ""}
    return {
        "falsification_status": NOT_REQUIRED_FALSIFICATION_STATUS,
        "falsification_audit_path": None,
        "falsification_blocker_codes": [],
        "credible_research_evidence": credible,
    }


def run_falsification_audit(
    *,
    experiment_root: Path,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    dataset_manifest, dataset_manifest_path = _load_linked_json(
        str(dict(alpha_card.get("reproducibility") or {}).get("dataset_manifest_path") or ""),
    )
    feature_manifest, feature_manifest_path = _load_linked_json(
        str(dict(alpha_card.get("reproducibility") or {}).get("feature_manifest_path") or ""),
    )
    universe_snapshot, universe_snapshot_path = _load_linked_json(
        str(alpha_card.get("universe_snapshot_path") or ""),
    )
    timestamp_check = _timestamp_truthfulness_check(
        alpha_card=alpha_card,
        validation_report=validation_report,
        dataset_manifest=dataset_manifest,
        dataset_manifest_path=dataset_manifest_path,
        feature_manifest=feature_manifest,
        feature_manifest_path=feature_manifest_path,
    )
    membership_check = _membership_truthfulness_check(
        alpha_card=alpha_card,
        validation_report=validation_report,
        dataset_manifest=dataset_manifest,
        dataset_manifest_path=dataset_manifest_path,
        feature_manifest=feature_manifest,
        feature_manifest_path=feature_manifest_path,
        universe_snapshot=universe_snapshot,
        universe_snapshot_path=universe_snapshot_path,
    )
    split_check = _split_truthfulness_check(
        alpha_card=alpha_card,
        validation_report=validation_report,
        feature_manifest=feature_manifest,
        feature_manifest_path=feature_manifest_path,
    )
    blocker_codes = sorted(
        {
            *timestamp_check["blocker_codes"],
            *membership_check["blocker_codes"],
            *split_check["blocker_codes"],
        }
    )
    status = "cleared" if not blocker_codes else "failed"
    audit_path = falsification_audit_path(experiment_root=experiment_root)
    payload = {
        "contract_version": FALSIFICATION_AUDIT_CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "experiment_id": str(alpha_card.get("experiment_id") or "").strip(),
        "strategy_id": str(alpha_card.get("strategy_id") or "").strip(),
        "as_of": str(alpha_card.get("as_of") or "").strip(),
        "status": status,
        "credible_research_evidence": status == "cleared",
        "blocker_codes": blocker_codes,
        "trigger_reason": _trigger_reason(alpha_card=alpha_card, validation_report=validation_report),
        "evidence_paths": {
            "experiment_root": portable_path(experiment_root, repo_root=ROOT),
            "dataset_manifest_path": (
                portable_path(dataset_manifest_path, repo_root=ROOT) if dataset_manifest_path is not None else None
            ),
            "feature_manifest_path": (
                portable_path(feature_manifest_path, repo_root=ROOT) if feature_manifest_path is not None else None
            ),
            "universe_snapshot_path": (
                portable_path(universe_snapshot_path, repo_root=ROOT) if universe_snapshot_path is not None else None
            ),
        },
        "timestamp_truthfulness_check": timestamp_check,
        "membership_truthfulness_check": membership_check,
        "split_truthfulness_check": split_check,
        "universe_metadata": pit_universe_artifact_metadata(alpha_card),
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(audit_path, payload)
    payload["falsification_audit_path"] = portable_path(audit_path, repo_root=ROOT)
    return payload


def invalidate_legacy_placeholder_artifacts(*, artifacts_root: Path) -> dict[str, Any]:
    experiments_root = artifacts_root / "experiments"
    updated: list[dict[str, Any]] = []
    if not experiments_root.exists():
        return {
            "updated_experiment_count": 0,
            "updated_experiments": [],
        }
    for alpha_card_path in sorted(experiments_root.rglob("alpha_card.json")):
        experiment_root = alpha_card_path.parent
        result = invalidate_legacy_placeholder_experiment(experiment_root=experiment_root, artifacts_root=artifacts_root)
        if result is not None:
            updated.append(result)
    return {
        "updated_experiment_count": len(updated),
        "updated_experiments": updated,
    }


def invalidate_legacy_placeholder_experiment(
    *,
    experiment_root: Path,
    artifacts_root: Path | None = None,
) -> dict[str, Any] | None:
    alpha_card_path = experiment_root / "alpha_card.json"
    validation_report_path = experiment_root / "validation_report.json"
    if not alpha_card_path.exists() or not validation_report_path.exists():
        return None
    alpha_card = read_json(alpha_card_path)
    validation_report = read_json(validation_report_path)
    blockers: set[str] = set()
    if _legacy_placeholder_audit_detected(alpha_card=alpha_card, artifacts_root=artifacts_root):
        blockers.add("legacy_placeholder_audit")
    dataset_manifest, _ = _load_linked_json(
        str(dict(alpha_card.get("reproducibility") or {}).get("dataset_manifest_path") or ""),
    )
    feature_manifest, _ = _load_linked_json(
        str(dict(alpha_card.get("reproducibility") or {}).get("feature_manifest_path") or ""),
    )
    if _collect_legacy_dataset_columns(dataset_manifest):
        blockers.add("legacy_dataset_columns_present")
    if _collect_legacy_feature_columns(feature_manifest):
        blockers.add("legacy_feature_columns_present")
    if not blockers:
        return None
    sorted_blockers = sorted(blockers)
    for payload in (alpha_card, validation_report):
        payload["validation"] = INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE
        payload["experiment_status"] = "quarantined"
        payload["publication_status"] = "archived_only"
        payload["falsification_status"] = "failed"
        payload["falsification_audit_path"] = None
        payload["falsification_blocker_codes"] = sorted_blockers
        payload["credible_research_evidence"] = False
        quality_summary = dict(payload.get("quality_summary") or {})
        quality_blockers = [
            str(item).strip()
            for item in list(quality_summary.get("quality_blockers") or [])
            if str(item).strip()
        ]
        quality_summary["quality_gate_passed"] = False
        quality_summary["quality_blockers"] = sorted(set(quality_blockers) | blockers)
        metrics_snapshot = dict(quality_summary.get("metrics_snapshot") or {})
        metrics_snapshot["falsification_status"] = "failed"
        metrics_snapshot["credible_research_evidence"] = False
        metrics_snapshot["falsification_blocker_codes"] = sorted_blockers
        quality_summary["metrics_snapshot"] = metrics_snapshot
        payload["quality_summary"] = quality_summary
    write_json(alpha_card_path, alpha_card)
    write_json(validation_report_path, validation_report)
    return {
        "experiment_id": str(alpha_card.get("experiment_id") or "").strip(),
        "experiment_root": portable_path(experiment_root, repo_root=ROOT),
        "blocker_codes": sorted_blockers,
    }


def _load_linked_json(path_string: str) -> tuple[dict[str, Any] | None, Path | None]:
    normalized = str(path_string or "").strip()
    if not normalized:
        return None, None
    resolved = resolve_portable_path(normalized, repo_root=ROOT)
    if not resolved.exists():
        return None, resolved
    return read_json(resolved), resolved


def _timestamp_truthfulness_check(
    *,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
    dataset_manifest: dict[str, Any] | None,
    dataset_manifest_path: Path | None,
    feature_manifest: dict[str, Any] | None,
    feature_manifest_path: Path | None,
) -> dict[str, Any]:
    blockers: set[str] = set()
    dataset_columns = [
        str(item).strip()
        for item in list((dataset_manifest or {}).get("columns") or [])
        if str(item).strip()
    ]
    feature_numeric_columns = _feature_columns_under_audit(
        alpha_card=alpha_card,
        validation_report=validation_report,
        feature_manifest=feature_manifest,
    )
    legacy_dataset_columns = _collect_legacy_dataset_columns(dataset_manifest)
    legacy_feature_columns = _collect_legacy_feature_columns_from_selected(feature_numeric_columns)
    if dataset_manifest_path is None or dataset_manifest is None:
        blockers.add("missing_dataset_manifest")
    if feature_manifest_path is None or feature_manifest is None:
        blockers.add("missing_feature_manifest")
    if legacy_dataset_columns:
        blockers.add("legacy_dataset_columns_present")
    if legacy_feature_columns:
        blockers.add("legacy_feature_columns_present")
    for feature_admission in (
        dict(validation_report.get("feature_admission") or {}),
        dict(alpha_card.get("feature_admission") or {}),
    ):
        if feature_admission and not bool(feature_admission.get("passed")):
            blockers.add("feature_admission_failed")
    reproducibility = dict(alpha_card.get("reproducibility") or {})
    if dataset_manifest is not None:
        if str(dataset_manifest.get("dataset_fingerprint") or "") != str(reproducibility.get("dataset_fingerprint") or ""):
            blockers.add("dataset_fingerprint_mismatch")
    if feature_manifest is not None:
        if str(feature_manifest.get("feature_hash") or "") != str(reproducibility.get("feature_hash") or ""):
            blockers.add("feature_hash_mismatch")
        if str(feature_manifest.get("dataset_fingerprint") or "") != str(reproducibility.get("dataset_fingerprint") or ""):
            blockers.add("dataset_fingerprint_mismatch")
    if not _portable_path_matches(
        left=str(reproducibility.get("dataset_manifest_path") or ""),
        right=portable_path(dataset_manifest_path, repo_root=ROOT) if dataset_manifest_path is not None else "",
    ):
        blockers.add("dataset_manifest_path_mismatch")
    if not _portable_path_matches(
        left=str(reproducibility.get("feature_manifest_path") or ""),
        right=portable_path(feature_manifest_path, repo_root=ROOT) if feature_manifest_path is not None else "",
    ):
        blockers.add("feature_manifest_path_mismatch")
    universe_mismatch = _universe_metadata_consistency_failures(
        alpha_card=alpha_card,
        validation_report=validation_report,
        dataset_manifest=dataset_manifest,
        feature_manifest=feature_manifest,
    )
    blockers.update(universe_mismatch)
    return {
        "status": "passed" if not blockers else "failed",
        "passed": not blockers,
        "dataset_manifest_columns": dataset_columns,
        "feature_columns_under_audit": sorted(feature_numeric_columns),
        "legacy_dataset_columns": sorted(legacy_dataset_columns),
        "legacy_feature_columns": sorted(legacy_feature_columns),
        "blocker_codes": sorted(blockers),
    }


def _membership_truthfulness_check(
    *,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
    dataset_manifest: dict[str, Any] | None,
    dataset_manifest_path: Path | None,
    feature_manifest: dict[str, Any] | None,
    feature_manifest_path: Path | None,
    universe_snapshot: dict[str, Any] | None,
    universe_snapshot_path: Path | None,
) -> dict[str, Any]:
    blockers: set[str] = set()
    if universe_snapshot is None or universe_snapshot_path is None:
        blockers.add("missing_universe_snapshot")
        return {
            "status": "failed",
            "passed": False,
            "snapshot_subjects": [],
            "dataset_subjects": sorted(
                str(item).strip()
                for item in list((dataset_manifest or {}).get("subjects") or [])
                if str(item).strip()
            ),
            "blocker_codes": sorted(blockers),
        }
    snapshot_metadata = {
        "universe_definition_id": str(universe_snapshot.get("universe_definition_id") or "").strip(),
        "universe_contract_version": str(universe_snapshot.get("universe_contract_version") or "").strip(),
        "universe_snapshot_path": portable_path(universe_snapshot_path, repo_root=ROOT),
        "universe_selection_policy_hash": str(universe_snapshot.get("universe_selection_policy_hash") or "").strip(),
    }
    if (
        snapshot_metadata["universe_definition_id"] != QUANT_UNIVERSE_DEFINITION_ID
        or snapshot_metadata["universe_contract_version"] != QUANT_UNIVERSE_INPUT_CONTRACT_VERSION
    ):
        blockers.add("universe_metadata_mismatch")
    blockers.update(
        _universe_metadata_consistency_failures(
            alpha_card=alpha_card,
            validation_report=validation_report,
            dataset_manifest=dataset_manifest,
            feature_manifest=feature_manifest,
            canonical=snapshot_metadata,
        )
    )
    candidates = {
        str(item.get("subject") or "").strip(): dict(item)
        for item in list(universe_snapshot.get("candidates") or [])
        if isinstance(item, dict) and str(item.get("subject") or "").strip()
    }
    snapshot_subjects = sorted(candidates)
    dataset_subjects = sorted(
        str(item).strip()
        for item in list((dataset_manifest or {}).get("subjects") or [])
        if str(item).strip()
    )
    for subject in dataset_subjects:
        if subject not in candidates:
            blockers.add("subject_not_in_snapshot")
    subject = str(alpha_card.get("subject") or "").strip()
    if subject:
        candidate = candidates.get(subject)
        if candidate is None:
            blockers.add("subject_not_in_snapshot")
        else:
            if str(alpha_card.get("liquidity_bucket") or "").strip() != str(candidate.get("liquidity_bucket") or "").strip():
                blockers.add("liquidity_bucket_mismatch")
            market_symbols = dict(alpha_card.get("market_symbols") or {})
            if str(market_symbols.get("spot_symbol") or "").strip() != str(candidate.get("spot_symbol") or "").strip():
                blockers.add("universe_metadata_mismatch")
            observed_usdm = str(market_symbols.get("usdm_symbol") or "").strip()
            expected_usdm = str(candidate.get("usdm_symbol") or "").strip()
            if observed_usdm != expected_usdm:
                blockers.add("universe_metadata_mismatch")
    for row in list(alpha_card.get("top_long_candidates") or []):
        if not isinstance(row, dict):
            continue
        row_subject = str(row.get("subject") or "").strip()
        candidate = candidates.get(row_subject)
        if candidate is None:
            blockers.add("subject_not_in_snapshot")
            continue
        if str(row.get("liquidity_bucket") or "").strip() != str(candidate.get("liquidity_bucket") or "").strip():
            blockers.add("liquidity_bucket_mismatch")
    return {
        "status": "passed" if not blockers else "failed",
        "passed": not blockers,
        "snapshot_subjects": snapshot_subjects,
        "dataset_subjects": dataset_subjects,
        "blocker_codes": sorted(blockers),
    }


def _split_truthfulness_check(
    *,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
    feature_manifest: dict[str, Any] | None,
    feature_manifest_path: Path | None,
) -> dict[str, Any]:
    blockers: set[str] = set()
    if feature_manifest is None or feature_manifest_path is None:
        blockers.add("missing_feature_manifest")
    split_integrity = dict(validation_report.get("split_integrity") or {})
    if not bool(split_integrity.get("passed")):
        blockers.add("split_boundary_contamination")
    if int(split_integrity.get("split_boundary_contamination_total", 0) or 0) != 0:
        blockers.add("split_boundary_contamination")
    if int(split_integrity.get("walk_forward_boundary_contamination_total", 0) or 0) != 0:
        blockers.add("walk_forward_boundary_contamination")
    backtest_realization_mismatch = dict(
        split_integrity.get("backtest_realization_mismatch")
        or split_integrity.get("backtest_horizon_mismatch")
        or {}
    )
    if bool(backtest_realization_mismatch.get("detected")):
        blockers.add("backtest_realization_mismatch")
    leakage_checks = dict(validation_report.get("leakage_checks") or {})
    contract_assertions = dict(leakage_checks.get("contract_assertions") or {})
    if not bool(leakage_checks.get("passed", True)):
        blockers.add("split_boundary_contamination")
    if contract_assertions and not bool(contract_assertions.get("strict_ordering_passed", True)):
        blockers.add("split_boundary_contamination")
    if contract_assertions and not bool(contract_assertions.get("zero_boundary_contamination_passed", True)):
        blockers.add("walk_forward_boundary_contamination")
    for window in list(dict(validation_report.get("walk_forward") or {}).get("windows") or []):
        if isinstance(window, dict) and not bool(window.get("contract_passed", True)):
            blockers.add("walk_forward_boundary_contamination")
            break
    feature_contract = dict((feature_manifest or {}).get("split_realization_contract") or {})
    validation_contract = dict(validation_report.get("split_realization_contract") or {})
    alpha_contract = dict(alpha_card.get("split_realization_contract") or {})
    if feature_contract and validation_contract and _canonical_json(feature_contract) != _canonical_json(validation_contract):
        blockers.add("split_realization_contract_mismatch")
    if feature_contract and alpha_contract and _canonical_json(feature_contract) != _canonical_json(alpha_contract):
        blockers.add("split_realization_contract_mismatch")
    return {
        "status": "passed" if not blockers else "failed",
        "passed": not blockers,
        "split_boundary_contamination_total": int(split_integrity.get("split_boundary_contamination_total", 0) or 0),
        "walk_forward_boundary_contamination_total": int(
            split_integrity.get("walk_forward_boundary_contamination_total", 0) or 0
        ),
        "backtest_realization_mismatch": backtest_realization_mismatch,
        "blocker_codes": sorted(blockers),
    }


def _feature_columns_under_audit(
    *,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
    feature_manifest: dict[str, Any] | None,
) -> set[str]:
    observed: set[str] = set()
    _ = feature_manifest
    for payload in (alpha_card, validation_report):
        feature_admission = dict(payload.get("feature_admission") or {})
        observed.update(
            str(item).strip()
            for item in list(feature_admission.get("selected_feature_columns") or [])
            if str(item).strip()
        )
        thesis_profile = dict(payload.get("thesis_profile") or {})
        observed.update(
            str(item).strip()
            for item in list(thesis_profile.get("required_feature_columns") or [])
            if str(item).strip()
        )
        factor_evidence = dict(payload.get("factor_evidence") or {})
        for field_name in ("selected_feature_columns", "required_feature_columns"):
            observed.update(
                str(item).strip()
                for item in list(factor_evidence.get(field_name) or [])
                if str(item).strip()
            )
        feature_registry = dict(payload.get("feature_registry") or {})
        for field_name in ("selected_feature_columns", "required_feature_columns"):
            observed.update(
                str(item).strip()
                for item in list(feature_registry.get(field_name) or [])
                if str(item).strip()
            )
        model_fit_summary = dict(payload.get("model_fit_summary") or {})
        observed.update(
            str(item).strip()
            for item in dict(model_fit_summary.get("weights") or {}).keys()
            if str(item).strip()
        )
        boundary_rule = dict(model_fit_summary.get("mf01_boundary_rule") or {})
        signal_column = str(boundary_rule.get("signal_column") or "").strip()
        if signal_column:
            observed.add(signal_column)
    return observed


def _collect_legacy_dataset_columns(dataset_manifest: dict[str, Any] | None) -> set[str]:
    dataset_columns = [
        str(item).strip()
        for item in list((dataset_manifest or {}).get("columns") or [])
        if str(item).strip()
    ]
    offenders = {
        column
        for column in dataset_columns
        if column in LEGACY_DATASET_FORBIDDEN_COLUMNS
        or any(column.startswith(prefix) for prefix in LEGACY_DATASET_FORBIDDEN_PREFIXES)
    }
    return offenders


def _collect_legacy_feature_columns(feature_manifest: dict[str, Any] | None) -> set[str]:
    feature_columns = set()
    for field_name in ("numeric_feature_columns", "available_numeric_columns"):
        feature_columns.update(
            str(item).strip()
            for item in list((feature_manifest or {}).get(field_name) or [])
            if str(item).strip()
        )
    return _collect_legacy_feature_columns_from_selected(feature_columns)


def _collect_legacy_feature_columns_from_selected(feature_columns: set[str]) -> set[str]:
    return {
        column
        for column in feature_columns
        if column in FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_COLUMNS
        or any(column.startswith(prefix) for prefix in FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES)
    }


def _portable_path_matches(*, left: str, right: str) -> bool:
    normalized_left = str(left or "").strip()
    normalized_right = str(right or "").strip()
    if not normalized_left and not normalized_right:
        return True
    return normalized_left == normalized_right


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _universe_metadata_consistency_failures(
    *,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
    dataset_manifest: dict[str, Any] | None,
    feature_manifest: dict[str, Any] | None,
    canonical: dict[str, Any] | None = None,
) -> set[str]:
    blockers: set[str] = set()
    payloads = [
        pit_universe_artifact_metadata(alpha_card),
        pit_universe_artifact_metadata(validation_report),
        pit_universe_artifact_metadata(dataset_manifest),
        pit_universe_artifact_metadata(feature_manifest),
    ]
    if not all(pit_universe_artifact_is_valid(payload) for payload in payloads if payload):
        blockers.add("universe_metadata_mismatch")
    if canonical is None:
        canonical = next((payload for payload in payloads if any(payload.values())), {})
    normalized_canonical = {
        "universe_definition_id": str(canonical.get("universe_definition_id") or "").strip(),
        "universe_contract_version": str(canonical.get("universe_contract_version") or "").strip(),
        "universe_snapshot_path": str(canonical.get("universe_snapshot_path") or "").strip(),
        "universe_selection_policy_hash": str(canonical.get("universe_selection_policy_hash") or "").strip(),
    }
    for payload in payloads:
        if not payload:
            continue
        comparable = {
            "universe_definition_id": str(payload.get("universe_definition_id") or "").strip(),
            "universe_contract_version": str(payload.get("universe_contract_version") or "").strip(),
            "universe_snapshot_path": str(payload.get("universe_snapshot_path") or "").strip(),
            "universe_selection_policy_hash": str(payload.get("universe_selection_policy_hash") or "").strip(),
        }
        if comparable != normalized_canonical:
            blockers.add("universe_metadata_mismatch")
            break
    return blockers


def _trigger_reason(*, alpha_card: dict[str, Any], validation_report: dict[str, Any]) -> str:
    validation_contract = dict(alpha_card.get("validation_contract") or validation_report.get("validation_contract") or {})
    if str(validation_contract.get("status") or "").strip() == FALSIFICATION_REQUIRED_STATUS:
        return "validation_contract_requires_falsification"
    if str(alpha_card.get("experiment_status") or validation_report.get("experiment_status") or "").strip() == "quarantined":
        return "quarantined_experiment"
    blocker_codes = {
        str(item).strip()
        for item in list(alpha_card.get("falsification_blocker_codes") or [])
        if str(item).strip()
    }
    blocker_codes.update(
        str(item.get("code") or "").strip()
        for item in list(validation_contract.get("blockers") or [])
        if isinstance(item, dict) and str(item.get("code") or "").strip()
    )
    if "sharpe_anomaly_detected" in blocker_codes:
        return "sharpe_anomaly_detected"
    return "explicit_falsification_required"


def _legacy_placeholder_audit_detected(*, alpha_card: dict[str, Any], artifacts_root: Path | None) -> bool:
    if artifacts_root is None:
        return str(alpha_card.get("validation") or "").strip() == "leakage_audit_required"
    as_of = str(alpha_card.get("as_of") or "").strip()
    experiment_id = str(alpha_card.get("experiment_id") or "").strip()
    if not as_of or not experiment_id:
        return False
    legacy_path = artifacts_root / "governance" / "leakage_audits" / as_of / f"{experiment_id}.leakage_audit.json"
    if not legacy_path.exists():
        return False
    payload = read_json(legacy_path)
    return (
        str(payload.get("contract_version") or "").strip() == "quant_leakage_audit.v1"
        or str(payload.get("status") or "").strip() == "pending"
    )
