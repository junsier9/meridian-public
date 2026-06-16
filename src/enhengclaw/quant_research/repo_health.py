from __future__ import annotations

import compileall
import json
from pathlib import Path
from typing import Any

from .alpha_manifest import (
    build_daily_alpha_manifest_entry,
    daily_alpha_manifest_path,
    write_daily_alpha_manifest_from_artifacts,
)
from .bridge import export_passed_alphas_to_workbench
from .bridge_contracts import verify_bridge_summary_contract
from .contracts import portable_path, read_json, resolve_portable_path, utc_now, write_json
from .execution_cost_model import EXECUTION_COST_MODEL_VERSION
from .feature_admission import FEATURE_ADMISSION_POLICY_VERSION
from .governance import load_strategy_library
from .lab import QUANT_ARTIFACTS_ROOT, WORKBENCH_ROOT, update_alpha_registry
from .leakage_audit import leakage_audit_is_required, leakage_audit_path, write_pending_leakage_audit
from .postmortem import postmortem_evidence_path, write_sharpe_anomaly_postmortem
from .positive_controls import build_positive_control_summary, write_positive_control_summary
from .promotion import (
    current_project_stage,
    evaluate_quant_publication_assessment,
    load_publication_contract,
    promotion_decision_path,
    publication_threshold,
    sharpe_anomaly_details,
    sha256_json,
    sha256_path,
    write_promotion_decisions_for_manifest,
)
from .reproducibility import (
    QUANT_DATASET_MANIFEST_CONTRACT_VERSION,
    QUANT_FEATURE_MANIFEST_CONTRACT_VERSION,
    resolve_reproducibility_tuple,
)
from .research_health import build_research_quality_summary, write_research_quality_summary
from .validation_contract import VALIDATION_CONTRACT_VERSION, validation_contract_missing_sections
from .legacy_surface import LEGACY_QUANT_SURFACE_EXIT_CODE, legacy_surface_summary


ROOT = Path(__file__).resolve().parents[3]
REPO_HEALTH_SUMMARY_CONTRACT_VERSION = "quant_repo_health_summary.v1"
REPO_HEALTH_INCIDENT_CONTRACT_VERSION = "quant_repo_health_incident.v1"
REPO_HEALTH_ARTIFACT_FAMILY = "quant_repo_health_guard"
REPO_HEALTH_CHILD_SUMMARY_CONTRACT_VERSION = "quant_repo_health_guard_child_summary.v1"

AUTO_REPAIRABLE_CODES = {
    "alpha_registry_drift",
    "alpha_registry_missing",
    "bridge_summary_contract_violation",
    "bridge_summary_missing",
    "daily_alpha_manifest_drift",
    "daily_alpha_manifest_missing",
    "leakage_audit_missing",
    "positive_control_summary_drift",
    "positive_control_summary_missing",
    "promotion_decision_drift",
    "promotion_decision_missing",
    "research_quality_summary_drift",
    "research_quality_summary_missing",
    "sharpe_anomaly_postmortem_missing",
}
INCIDENT_ONLY_CODES = {
    "compileall_failed",
    "config_json_parse_failed",
    "disk_integrity_failed",
    "gitignore_whitelist_drift",
    "legacy_status_alias_drift",
    "runtime_ownership_doc_drift",
    "single_asset_pipeline_regression",
    "threshold_provenance_drift",
    "reproducibility_contract_drift",
    "validation_contract_drift",
}
QUARANTINE_ONLY_CODES = {
    "positive_control_marginal",
    "research_quality_warning",
    "sharpe_anomaly_detected",
}
RUNTIME_DOC_PATHS = (
    "PROJECT_STATE.md",
    "PROJECT_INSTRUCTIONS.md",
    "CANONICAL_RUNBOOK.md",
    "docs/README_FOR_AGENT.md",
    "docs/agents/OWNER_AGENT_ARCHITECTURE.md",
)
REQUIRED_GITIGNORE_LINES = (
    "!artifacts/quant_research/assessments/",
    "!artifacts/quant_research/bridge_exports/",
    "!artifacts/quant_research/cycles/**/research_quality_summary.json",
    "!artifacts/quant_research/governance/daily_alpha_manifests/",
    "!artifacts/quant_research/governance/leakage_audits/",
    "!artifacts/quant_research/governance/promotion_decisions/",
    "!artifacts/quant_research/ops/",
    "!artifacts/quant_research/ops/**/",
    "!artifacts/quant_research/ops/**/*.json",
    "!artifacts/quant_research/registry/alpha_registry.json",
)
FORBIDDEN_STATUS_PATTERNS = (
    "".join(["entry", '.get("', "status", '")']),
    "".join(["experiment", '.get("', "status", '")']),
    "".join(["alpha_card", '.get("', "status", '")']),
    "".join(['.get("', "governance_status", '")']),
)


def repo_health_summary_path(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "ops" / "repo_health" / as_of / "repo_health_summary.json"


def positive_control_summary_path(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "assessments" / "positive_controls" / as_of / "positive_control_summary.json"


def incidents_root(*, artifacts_root: Path) -> Path:
    return artifacts_root / "ops" / "incidents"


def classify_repo_health_finding(code: str) -> str:
    if code in AUTO_REPAIRABLE_CODES:
        return "auto_repairable"
    if code in QUARANTINE_ONLY_CODES:
        return "quarantine_only"
    return "incident_only"


def run_quant_repo_health_guard(
    *,
    as_of: str,
    repo_root: Path | None = None,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
    now_utc: str | None = None,
) -> tuple[int, dict[str, Any]]:
    return LEGACY_QUANT_SURFACE_EXIT_CODE, legacy_surface_summary(
        operation="repo_health_guard",
        as_of=as_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
    )
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    generated_at_utc = now_utc or utc_now()
    findings: list[dict[str, Any]] = []
    repaired_paths: list[str] = []
    incidents: list[dict[str, Any]] = []
    repair_actions: list[str] = []

    findings.extend(scan_repo_health_source_contracts(repo_root=resolved_repo_root))
    blocking_source_findings = [item for item in findings if bool(item["blocking"])]
    if blocking_source_findings:
        incidents.extend(
            write_repo_health_incidents(
                artifacts_root=resolved_artifacts_root,
                findings=blocking_source_findings,
                generated_at_utc=generated_at_utc,
                auto_repair_attempted=False,
                repair_succeeded=False,
            )
        )
        summary = _write_repo_health_summary(
            artifacts_root=resolved_artifacts_root,
            as_of=as_of,
            generated_at_utc=generated_at_utc,
            findings=findings,
            repair_status="failed",
            repair_action_count=0,
            repaired_paths=repaired_paths,
            incident_paths=[item["incident_path"] for item in incidents],
            input_watermarks=_input_watermarks(artifacts_root=resolved_artifacts_root, as_of=as_of),
            upstream_versions=_upstream_versions(as_of=as_of),
            positive_control_view=_read_positive_control_view(
                artifacts_root=resolved_artifacts_root,
                as_of=as_of,
            ),
        )
        return 1, summary

    repairable_findings = scan_repo_health_artifact_drift(
        as_of=as_of,
        repo_root=resolved_repo_root,
        artifacts_root=resolved_artifacts_root,
        workbench_root=resolved_workbench_root,
    )
    findings.extend(repairable_findings)

    auto_repair_candidates = [item for item in repairable_findings if item["classification"] == "auto_repairable"]
    if auto_repair_candidates:
        repair_actions, repaired_paths = repair_quant_repo_artifacts(
            as_of=as_of,
            repo_root=resolved_repo_root,
            artifacts_root=resolved_artifacts_root,
            workbench_root=resolved_workbench_root,
            findings=auto_repair_candidates,
            now_utc=generated_at_utc,
        )

    post_repair_findings = scan_repo_health_artifact_drift(
        as_of=as_of,
        repo_root=resolved_repo_root,
        artifacts_root=resolved_artifacts_root,
        workbench_root=resolved_workbench_root,
    )
    remaining_blockers = [
        item
        for item in post_repair_findings
        if item["classification"] in {"auto_repairable", "incident_only"} and bool(item["blocking"])
    ]
    anomaly_findings = build_repo_health_anomaly_findings(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
    )
    findings.extend(
        item
        for item in anomaly_findings
        if item["code"] not in {finding["code"] for finding in findings if finding.get("scope") == item.get("scope")}
    )
    if remaining_blockers:
        incidents.extend(
            write_repo_health_incidents(
                artifacts_root=resolved_artifacts_root,
                findings=remaining_blockers,
                generated_at_utc=generated_at_utc,
                auto_repair_attempted=bool(auto_repair_candidates),
                repair_succeeded=False,
            )
        )
    blocking_anomaly_findings = [item for item in anomaly_findings if bool(item["blocking"])]
    if blocking_anomaly_findings:
        incidents.extend(
            write_repo_health_incidents(
                artifacts_root=resolved_artifacts_root,
                findings=blocking_anomaly_findings,
                generated_at_utc=generated_at_utc,
                auto_repair_attempted=False,
                repair_succeeded=False,
            )
        )
    warning_findings = [item for item in anomaly_findings if not bool(item["blocking"])]
    if warning_findings:
        incidents.extend(
            write_repo_health_incidents(
                artifacts_root=resolved_artifacts_root,
                findings=warning_findings,
                generated_at_utc=generated_at_utc,
                auto_repair_attempted=False,
                repair_succeeded=True,
            )
        )

    all_blockers = remaining_blockers + blocking_anomaly_findings
    if all_blockers:
        findings.extend(remaining_blockers)
        exit_code = 1
        repair_status = "failed"
    elif auto_repair_candidates:
        exit_code = 0
        repair_status = "repaired"
    else:
        exit_code = 0
        repair_status = "not_needed"

    final_findings = _materialize_final_findings(
        findings=_dedupe_findings(findings),
        remaining_blockers=all_blockers,
    )
    summary = _write_repo_health_summary(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        generated_at_utc=generated_at_utc,
        findings=final_findings,
        repair_status=repair_status,
        repair_action_count=len(repair_actions),
        repaired_paths=repaired_paths,
        incident_paths=[item["incident_path"] for item in incidents],
        input_watermarks=_input_watermarks(artifacts_root=resolved_artifacts_root, as_of=as_of),
        upstream_versions=_upstream_versions(as_of=as_of),
        positive_control_view=_read_positive_control_view(
            artifacts_root=resolved_artifacts_root,
            as_of=as_of,
        ),
    )
    summary["repair_actions"] = repair_actions
    return exit_code, summary


def scan_repo_health_source_contracts(*, repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(_scan_compileall(repo_root=repo_root))
    findings.extend(_scan_disk_integrity(repo_root=repo_root))
    findings.extend(_scan_json_parse(repo_root=repo_root))
    findings.extend(_scan_runtime_ownership_docs(repo_root=repo_root))
    findings.extend(_scan_gitignore(repo_root=repo_root))
    findings.extend(_scan_threshold_provenance(repo_root=repo_root))
    findings.extend(_scan_quant_status_aliases(repo_root=repo_root))
    return findings


def scan_repo_health_artifact_drift(
    *,
    as_of: str,
    repo_root: Path,
    artifacts_root: Path,
    workbench_root: Path,
) -> list[dict[str, Any]]:
    del workbench_root  # reserved for future queue-aware repair policies
    findings: list[dict[str, Any]] = []
    findings.extend(
        _scan_positive_control_summary(
            as_of=as_of,
            repo_root=repo_root,
            artifacts_root=artifacts_root,
        )
    )
    experiments = _load_canonical_experiments(artifacts_root=artifacts_root, as_of=as_of)
    manifest_path = daily_alpha_manifest_path(artifacts_root=artifacts_root, as_of=as_of)
    expected_manifest_entries = _expected_manifest_entries_from_experiments(experiments=experiments)
    if not manifest_path.exists():
        findings.append(
            _finding(
                code="daily_alpha_manifest_missing",
                scope=f"daily_manifest:{as_of}",
                message=f"daily alpha manifest is missing for as_of={as_of}",
                evidence_paths=[portable_path(manifest_path, repo_root=repo_root)],
            )
        )
    else:
        try:
            manifest = read_json(manifest_path)
        except Exception:
            findings.append(
                _finding(
                    code="daily_alpha_manifest_drift",
                    scope=f"daily_manifest:{as_of}",
                    message=f"daily alpha manifest is unreadable or does not match canonical experiment set for as_of={as_of}",
                    evidence_paths=[portable_path(manifest_path, repo_root=repo_root)],
                )
            )
        else:
            actual_entries = sorted(
                [dict(item) for item in manifest.get("entries", []) if isinstance(item, dict)],
                key=lambda item: str(item.get("experiment_id") or ""),
            )
            if sha256_json(actual_entries) != sha256_json(expected_manifest_entries):
                findings.append(
                    _finding(
                        code="daily_alpha_manifest_drift",
                        scope=f"daily_manifest:{as_of}",
                        message=f"daily alpha manifest does not match canonical experiment set for as_of={as_of}",
                        evidence_paths=[portable_path(manifest_path, repo_root=repo_root)],
                    )
                )

    try:
        strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    except FileNotFoundError:
        findings.append(
            _finding(
                code="strategy_library_missing",
                scope=f"strategy_library:{as_of}",
                message=f"strategy library is missing while evaluating repo health for as_of={as_of}",
                evidence_paths=[portable_path(artifacts_root / 'governance' / 'strategy_library.json', repo_root=repo_root)],
                recommended_manual_action="Restore the strategy library before running repo health guard again.",
            )
        )
        return findings
    except Exception as exc:
        findings.append(
            _finding(
                code="strategy_library_unreadable",
                scope=f"strategy_library:{as_of}",
                message=f"strategy library is unreadable while evaluating repo health for as_of={as_of}: {exc}",
                evidence_paths=[portable_path(artifacts_root / "governance" / "strategy_library.json", repo_root=repo_root)],
                recommended_manual_action="Repair the tracked strategy library before running repo health guard again.",
            )
        )
        return findings
    strategy_entries = {
        str(entry.get("strategy_id")): {
            **entry,
            "strategy_library_path": str(strategy_library["path"]),
        }
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }

    publication_contract = load_publication_contract()
    anomaly_threshold = float(publication_threshold(publication_contract, "sharpe_anomaly_quarantine_threshold", 5.0))
    for experiment in experiments:
        alpha_card = dict(experiment["alpha_card"])
        validation_report = dict(experiment.get("validation_report") or {})
        alpha_id = str(alpha_card.get("experiment_id") or "").strip()
        strategy_id = str(alpha_card.get("strategy_id") or "").strip()
        strategy_entry = strategy_entries.get(strategy_id)
        decision_path = promotion_decision_path(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
        validation_contract_problems: list[str] = []
        missing_sections = (
            validation_contract_missing_sections(validation_report)
            if validation_report
            else [
                "split_integrity",
                "feature_admission",
                "reproducibility",
                "walk_forward_assessment",
                "execution_stress",
                "regime_holdout",
            ]
        )
        if missing_sections:
            validation_contract_problems.append(
                "validation_report missing required sections: " + ", ".join(missing_sections)
            )
        alpha_validation_contract = dict(alpha_card.get("validation_contract") or {})
        report_validation_contract = dict(validation_report.get("validation_contract") or {})
        experiment_spec = dict(experiment.get("experiment_spec") or {})
        if str(report_validation_contract.get("contract_version") or "") not in {"", VALIDATION_CONTRACT_VERSION}:
            validation_contract_problems.append(
                f"validation_report.validation_contract.contract_version={report_validation_contract.get('contract_version')} is stale"
            )
        if str(alpha_validation_contract.get("contract_version") or "") not in {"", VALIDATION_CONTRACT_VERSION}:
            validation_contract_problems.append(
                f"alpha_card.validation_contract.contract_version={alpha_validation_contract.get('contract_version')} is stale"
            )
        current_contract_present = any(
            str(item.get("contract_version") or "") == VALIDATION_CONTRACT_VERSION
            for item in (alpha_validation_contract, report_validation_contract)
        )
        if current_contract_present:
            split_integrity = dict(validation_report.get("split_integrity") or {})
            feature_admission = dict(validation_report.get("feature_admission") or {})
            reproducibility = dict(validation_report.get("reproducibility") or {})
            execution_stress = dict(validation_report.get("execution_stress") or {})
            alpha_reproducibility = dict(alpha_card.get("reproducibility") or {})
            spec_reproducibility = dict(experiment_spec.get("reproducibility") or {})
            alpha_feature_policy = dict(alpha_card.get("feature_admission_policy") or {})
            report_feature_policy = dict(validation_report.get("feature_admission_policy") or {})
            spec_feature_policy = dict(experiment_spec.get("feature_admission_policy") or {})
            alpha_execution_cost_model = dict(alpha_card.get("execution_cost_model") or {})
            report_execution_cost_model = dict(validation_report.get("execution_cost_model") or {})
            spec_execution_cost_model = dict(experiment_spec.get("execution_cost_model") or {})
            if not dict(alpha_card.get("split_realization_contract") or {}):
                validation_contract_problems.append("alpha_card.split_realization_contract is missing for current validation contract")
            if not dict(validation_report.get("split_realization_contract") or {}):
                validation_contract_problems.append(
                    "validation_report.split_realization_contract is missing for current validation contract"
                )
            if not dict(split_integrity.get("split_realization_contract") or {}):
                validation_contract_problems.append(
                    "validation_report.split_integrity.split_realization_contract is missing for current validation contract"
                )
            if "split_boundary_contamination_total" not in split_integrity:
                validation_contract_problems.append(
                    "validation_report.split_integrity.split_boundary_contamination_total is missing"
                )
            elif int(split_integrity.get("split_boundary_contamination_total") or 0) != 0:
                validation_contract_problems.append(
                    "validation_report.split_integrity.split_boundary_contamination_total must equal 0"
                )
            if "walk_forward_boundary_contamination_total" not in split_integrity:
                validation_contract_problems.append(
                    "validation_report.split_integrity.walk_forward_boundary_contamination_total is missing"
                )
            elif int(split_integrity.get("walk_forward_boundary_contamination_total") or 0) != 0:
                validation_contract_problems.append(
                    "validation_report.split_integrity.walk_forward_boundary_contamination_total must equal 0"
                )
            if not alpha_feature_policy:
                validation_contract_problems.append("alpha_card.feature_admission_policy is missing for current validation contract")
            elif str(alpha_feature_policy.get("contract_version") or "") != FEATURE_ADMISSION_POLICY_VERSION:
                validation_contract_problems.append(
                    f"alpha_card.feature_admission_policy.contract_version={alpha_feature_policy.get('contract_version')} is stale"
                )
            if not report_feature_policy:
                validation_contract_problems.append("validation_report.feature_admission_policy is missing for current validation contract")
            elif str(report_feature_policy.get("contract_version") or "") != FEATURE_ADMISSION_POLICY_VERSION:
                validation_contract_problems.append(
                    f"validation_report.feature_admission_policy.contract_version={report_feature_policy.get('contract_version')} is stale"
                )
            if not spec_feature_policy:
                validation_contract_problems.append("experiment_spec.feature_admission_policy is missing for current validation contract")
            elif str(spec_feature_policy.get("contract_version") or "") != FEATURE_ADMISSION_POLICY_VERSION:
                validation_contract_problems.append(
                    f"experiment_spec.feature_admission_policy.contract_version={spec_feature_policy.get('contract_version')} is stale"
                )
            for payload_name, payload_value in (
                ("alpha_card.execution_cost_model", alpha_execution_cost_model),
                ("validation_report.execution_cost_model", report_execution_cost_model),
                ("experiment_spec.execution_cost_model", spec_execution_cost_model),
            ):
                if not payload_value:
                    validation_contract_problems.append(f"{payload_name} is missing for current validation contract")
                elif str(payload_value.get("contract_version") or "") != EXECUTION_COST_MODEL_VERSION:
                    validation_contract_problems.append(
                        f"{payload_name}.contract_version={payload_value.get('contract_version')} is stale"
                    )
            execution_stress_model = dict(execution_stress.get("execution_cost_model") or {})
            if not execution_stress_model:
                validation_contract_problems.append(
                    "validation_report.execution_stress.execution_cost_model is missing for current validation contract"
                )
            elif str(execution_stress_model.get("contract_version") or "") != EXECUTION_COST_MODEL_VERSION:
                validation_contract_problems.append(
                    "validation_report.execution_stress.execution_cost_model.contract_version is stale"
                )
            for field_name in (
                "latency_bars",
                "max_trade_participation_rate",
                "max_inventory_participation_rate",
                "max_participation_rate",
            ):
                if field_name not in execution_stress:
                    validation_contract_problems.append(
                        f"validation_report.execution_stress.{field_name} is missing"
                    )
            if not feature_admission:
                validation_contract_problems.append("validation_report.feature_admission is missing for current validation contract")
            else:
                if not dict(feature_admission.get("feature_admission_policy") or {}):
                    validation_contract_problems.append(
                        "validation_report.feature_admission.feature_admission_policy is missing"
                    )
                if not bool(feature_admission.get("passed")):
                    validation_contract_problems.append("validation_report.feature_admission.passed must be true")
                if list(feature_admission.get("banned_proxy_columns_present") or []):
                    validation_contract_problems.append(
                        "validation_report.feature_admission.banned_proxy_columns_present must be empty"
                    )
                if list(feature_admission.get("unknown_numeric_columns_present") or []):
                    validation_contract_problems.append(
                        "validation_report.feature_admission.unknown_numeric_columns_present must be empty"
                    )
                if list(feature_admission.get("selected_feature_columns_outside_manifest") or []):
                    validation_contract_problems.append(
                        "validation_report.feature_admission.selected_feature_columns_outside_manifest must be empty"
                    )
            if not alpha_reproducibility:
                validation_contract_problems.append("alpha_card.reproducibility is missing for current validation contract")
            if not spec_reproducibility:
                validation_contract_problems.append("experiment_spec.reproducibility is missing for current validation contract")
            if not reproducibility:
                validation_contract_problems.append("validation_report.reproducibility is missing for current validation contract")
            else:
                if not bool(reproducibility.get("passed")):
                    validation_contract_problems.append("validation_report.reproducibility.passed must be true")
                for field_name in (
                    "source_commit_sha",
                    "dataset_fingerprint",
                    "feature_hash",
                    "dataset_manifest_path",
                    "feature_manifest_path",
                ):
                    if not str(reproducibility.get(field_name) or "").strip():
                        validation_contract_problems.append(
                            f"validation_report.reproducibility.{field_name} must be non-empty"
                        )
            alpha_repro_tuple = resolve_reproducibility_tuple(alpha_card)
            report_repro_tuple = resolve_reproducibility_tuple(validation_report)
            spec_repro_tuple = resolve_reproducibility_tuple(experiment_spec)
            if alpha_repro_tuple != report_repro_tuple or spec_repro_tuple != report_repro_tuple:
                validation_contract_problems.append(
                    "alpha_card/validation_report/experiment_spec reproducibility fields must match exactly"
                )
            dataset_manifest_path = report_repro_tuple[3]
            feature_manifest_path = report_repro_tuple[4]
            if dataset_manifest_path:
                resolved_dataset_manifest_path = resolve_portable_path(dataset_manifest_path, repo_root=ROOT)
                if not resolved_dataset_manifest_path.exists():
                    validation_contract_problems.append(
                        "reproducibility dataset_manifest_path does not exist"
                    )
                else:
                    dataset_manifest = read_json(resolved_dataset_manifest_path)
                    if str(dataset_manifest.get("contract_version") or "") != QUANT_DATASET_MANIFEST_CONTRACT_VERSION:
                        validation_contract_problems.append(
                            f"dataset_manifest.contract_version={dataset_manifest.get('contract_version')} is stale"
                        )
                    if not str(dataset_manifest.get("source_commit_sha") or "").strip():
                        validation_contract_problems.append("dataset_manifest.source_commit_sha must be non-empty")
                    if not str(dataset_manifest.get("dataset_panel_sha256") or "").strip():
                        validation_contract_problems.append("dataset_manifest.dataset_panel_sha256 must be non-empty")
                    if not str(dataset_manifest.get("dataset_fingerprint") or "").strip():
                        validation_contract_problems.append("dataset_manifest.dataset_fingerprint must be non-empty")
                    elif str(dataset_manifest.get("dataset_fingerprint") or "").strip() != report_repro_tuple[1]:
                        validation_contract_problems.append(
                            "dataset_manifest.dataset_fingerprint must match experiment reproducibility"
                        )
            if feature_manifest_path:
                resolved_feature_manifest_path = resolve_portable_path(feature_manifest_path, repo_root=ROOT)
                if not resolved_feature_manifest_path.exists():
                    validation_contract_problems.append(
                        "reproducibility feature_manifest_path does not exist"
                    )
                else:
                    feature_manifest = read_json(resolved_feature_manifest_path)
                    if str(feature_manifest.get("contract_version") or "") != QUANT_FEATURE_MANIFEST_CONTRACT_VERSION:
                        validation_contract_problems.append(
                            f"feature_manifest.contract_version={feature_manifest.get('contract_version')} is stale"
                        )
                    if not str(feature_manifest.get("source_commit_sha") or "").strip():
                        validation_contract_problems.append("feature_manifest.source_commit_sha must be non-empty")
                    if not str(feature_manifest.get("feature_matrix_sha256") or "").strip():
                        validation_contract_problems.append("feature_manifest.feature_matrix_sha256 must be non-empty")
                    if not str(feature_manifest.get("feature_hash") or "").strip():
                        validation_contract_problems.append("feature_manifest.feature_hash must be non-empty")
                    elif str(feature_manifest.get("feature_hash") or "").strip() != report_repro_tuple[2]:
                        validation_contract_problems.append(
                            "feature_manifest.feature_hash must match experiment reproducibility"
                        )
                    if not str(feature_manifest.get("dataset_fingerprint") or "").strip():
                        validation_contract_problems.append("feature_manifest.dataset_fingerprint must be non-empty")
                    elif str(feature_manifest.get("dataset_fingerprint") or "").strip() != report_repro_tuple[1]:
                        validation_contract_problems.append(
                            "feature_manifest.dataset_fingerprint must match experiment reproducibility"
                        )
            numeric_feature_columns = [
                str(item).strip()
                for item in list(experiment_spec.get("numeric_feature_columns") or [])
                if str(item).strip()
            ]
            selected_feature_columns = [
                str(item).strip()
                for item in list(experiment_spec.get("feature_columns") or [])
                if str(item).strip()
            ]
            if not selected_feature_columns:
                validation_contract_problems.append("experiment_spec.feature_columns is missing for current validation contract")
            elif not set(selected_feature_columns).issubset(set(numeric_feature_columns)):
                validation_contract_problems.append(
                    "experiment_spec.feature_columns must be a subset of experiment_spec.numeric_feature_columns"
                )
            for payload_name, metrics_payload in (
                ("validation_report.validation_metrics", dict(validation_report.get("validation_metrics") or {})),
                ("validation_report.test_metrics", dict(validation_report.get("test_metrics") or {})),
                ("alpha_card.validation_metrics", dict(alpha_card.get("validation_metrics") or {})),
                ("alpha_card.test_metrics", dict(alpha_card.get("test_metrics") or {})),
            ):
                for field_name in (
                    "gross_return_before_costs",
                    "fee_cost_return",
                    "slippage_cost_return",
                    "funding_cost_return",
                    "borrow_cost_return",
                    "latency_bars",
                    "execution_venue",
                    "trade_notional_usd_total",
                    "max_trade_participation_rate",
                    "max_inventory_participation_rate",
                    "capacity_breach_count",
                ):
                    if field_name not in metrics_payload:
                        validation_contract_problems.append(f"{payload_name}.{field_name} is missing")
            for window_index, window in enumerate(list(validation_report.get("walk_forward", {}).get("windows") or [])):
                if not isinstance(window, dict):
                    continue
                for field_name in (
                    "gross_return_before_costs",
                    "fee_cost_return",
                    "slippage_cost_return",
                    "funding_cost_return",
                    "borrow_cost_return",
                    "latency_bars",
                    "execution_venue",
                    "trade_notional_usd_total",
                    "max_trade_participation_rate",
                    "max_inventory_participation_rate",
                    "capacity_breach_count",
                    "stress_max_trade_participation_rate",
                    "stress_max_inventory_participation_rate",
                    "stress_capacity_breach_count",
                ):
                    if field_name not in window:
                        validation_contract_problems.append(
                            f"validation_report.walk_forward.windows[{window_index}].{field_name} is missing"
                        )
            serialized_payloads = json.dumps(
                {"alpha_card": alpha_card, "validation_report": validation_report},
                sort_keys=True,
                default=str,
            )
            if "needs_rerun_after_overlap_fix" in serialized_payloads:
                validation_contract_problems.append(
                    "current validation contract artifacts must not contain needs_rerun_after_overlap_fix"
                )
        if sha256_json(_comparable_validation_contract_summary(alpha_validation_contract)) != sha256_json(
            _comparable_validation_contract_summary(report_validation_contract)
        ):
            validation_contract_problems.append("alpha_card.validation_contract summary does not match validation_report")
        if validation_contract_problems:
            findings.append(
                _finding(
                    code=(
                        "reproducibility_contract_drift"
                        if any("reproduc" in problem or "manifest." in problem for problem in validation_contract_problems)
                        else "validation_contract_drift"
                    ),
                    scope=f"validation_contract:{alpha_id}",
                    message=f"validation contract evidence drifted for alpha_id={alpha_id}: {' | '.join(validation_contract_problems)}",
                    evidence_paths=[portable_path(Path(str(experiment["alpha_card_path"])), repo_root=repo_root)],
                )
            )
        if not decision_path.exists():
            findings.append(
                _finding(
                    code="promotion_decision_missing",
                    scope=f"promotion_decision:{alpha_id}",
                    message=f"promotion decision is missing for alpha_id={alpha_id}",
                    evidence_paths=[portable_path(decision_path, repo_root=repo_root)],
                )
            )
        else:
            try:
                decision = read_json(decision_path)
            except Exception:
                findings.append(
                    _finding(
                        code="promotion_decision_drift",
                        scope=f"promotion_decision:{alpha_id}",
                        message=f"promotion decision is unreadable for alpha_id={alpha_id}",
                        evidence_paths=[portable_path(decision_path, repo_root=repo_root)],
                    )
                )
            else:
                decision_validation_contract = dict(dict(decision.get("metrics_snapshot") or {}).get("validation_contract") or {})
                if decision_validation_contract and sha256_json(_comparable_validation_contract_summary(decision_validation_contract)) != sha256_json(
                    _comparable_validation_contract_summary(alpha_validation_contract)
                ):
                    findings.append(
                        _finding(
                            code="validation_contract_drift",
                            scope=f"validation_contract:{alpha_id}",
                            message=f"promotion decision still references stale validation contract summary for alpha_id={alpha_id}",
                            evidence_paths=[portable_path(decision_path, repo_root=repo_root)],
                        )
                    )
                if _promotion_decision_has_drift(
                    decision=decision,
                    alpha_card=alpha_card,
                    alpha_card_path=Path(str(experiment["alpha_card_path"])),
                    strategy_entry=strategy_entry,
                    strategy_library_path=Path(str(strategy_library["path"])),
                    artifacts_root=artifacts_root,
                ):
                    findings.append(
                        _finding(
                            code="promotion_decision_drift",
                            scope=f"promotion_decision:{alpha_id}",
                            message=f"promotion decision is stale relative to current alpha card or strategy library for alpha_id={alpha_id}",
                            evidence_paths=[portable_path(decision_path, repo_root=repo_root)],
                        )
                    )

        assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            artifacts_root=artifacts_root,
        )
        blockers = list(assessment.get("quality_blockers") or [])
        if leakage_audit_is_required(alpha_card=alpha_card, quality_blockers=blockers):
            audit_path = leakage_audit_path(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
            if not audit_path.exists():
                findings.append(
                    _finding(
                        code="leakage_audit_missing",
                        scope=f"leakage_audit:{alpha_id}",
                        message=f"pending leakage audit is missing for alpha_id={alpha_id}",
                        evidence_paths=[portable_path(audit_path, repo_root=repo_root)],
                    )
                )
        anomaly = sharpe_anomaly_details(
            validation_metrics=dict(alpha_card.get("validation_metrics") or {}),
            test_metrics=dict(alpha_card.get("test_metrics") or {}),
            walk_forward=dict(alpha_card.get("walk_forward") or {}),
            threshold=anomaly_threshold,
        )
        if anomaly is not None and str(alpha_card.get("shape") or "") == "single_asset":
            evidence_path = postmortem_evidence_path(artifacts_root=artifacts_root, alpha_id=alpha_id)
            if not evidence_path.exists():
                findings.append(
                    _finding(
                        code="sharpe_anomaly_postmortem_missing",
                        scope=f"sharpe_postmortem:{alpha_id}",
                        message=f"Sharpe anomaly postmortem evidence is missing for alpha_id={alpha_id}",
                        evidence_paths=[portable_path(evidence_path, repo_root=repo_root)],
                    )
                )

    registry_path = artifacts_root / "registry" / "alpha_registry.json"
    expected_registry_ids = {str(item["experiment_id"]) for item in expected_manifest_entries}
    if not registry_path.exists():
        findings.append(
            _finding(
                code="alpha_registry_missing",
                scope=f"alpha_registry:{as_of}",
                message=f"alpha registry is missing for as_of={as_of}",
                evidence_paths=[portable_path(registry_path, repo_root=repo_root)],
            )
        )
    else:
        try:
            registry = read_json(registry_path)
        except Exception:
            findings.append(
                _finding(
                    code="alpha_registry_drift",
                    scope=f"alpha_registry:{as_of}",
                    message=f"alpha registry is unreadable for as_of={as_of}",
                    evidence_paths=[portable_path(registry_path, repo_root=repo_root)],
                )
            )
        else:
            registry_ids = {
                str(entry.get("experiment_id") or "")
                for entry in registry.get("entries", [])
                if isinstance(entry, dict) and str(entry.get("as_of") or "") == as_of
            }
            if registry_ids != expected_registry_ids:
                findings.append(
                    _finding(
                        code="alpha_registry_drift",
                        scope=f"alpha_registry:{as_of}",
                        message=f"alpha registry entries for as_of={as_of} do not match canonical experiment ids",
                        evidence_paths=[portable_path(registry_path, repo_root=repo_root)],
                    )
                )

    quality_path = artifacts_root / "cycles" / as_of / "research_quality_summary.json"
    expected_quality = build_research_quality_summary(
        experiments=experiments,
        artifacts_root=artifacts_root,
        scope="daily_cycle",
        as_of=as_of,
        canonical_universe_count=len(expected_manifest_entries),
    )
    if not quality_path.exists():
        findings.append(
            _finding(
                code="research_quality_summary_missing",
                scope=f"research_quality:{as_of}",
                message=f"research quality summary is missing for as_of={as_of}",
                evidence_paths=[portable_path(quality_path, repo_root=repo_root)],
            )
        )
    else:
        try:
            current_quality = read_json(quality_path)
        except Exception:
            findings.append(
                _finding(
                    code="research_quality_summary_drift",
                    scope=f"research_quality:{as_of}",
                    message=f"research quality summary is unreadable for as_of={as_of}",
                    evidence_paths=[portable_path(quality_path, repo_root=repo_root)],
                )
            )
        else:
            comparable_current = _comparable_quality_payload(current_quality)
            comparable_expected = _comparable_quality_payload(expected_quality)
            if sha256_json(comparable_current) != sha256_json(comparable_expected):
                findings.append(
                    _finding(
                        code="research_quality_summary_drift",
                        scope=f"research_quality:{as_of}",
                        message=f"research quality summary is stale relative to current experiments for as_of={as_of}",
                        evidence_paths=[portable_path(quality_path, repo_root=repo_root)],
                    )
                )

    summary_path = artifacts_root / "bridge_exports" / as_of / "bridge_summary.json"
    current_stage = current_project_stage()
    archive_only_stages = {str(item) for item in publication_contract.get("archive_only_stages", [])}
    bridge_classification = "auto_repairable" if current_stage in archive_only_stages else "incident_only"
    if not summary_path.exists():
        findings.append(
            _finding(
                code="bridge_summary_missing",
                scope=f"bridge_summary:{as_of}",
                message=f"bridge summary is missing for as_of={as_of}",
                classification=bridge_classification,
                evidence_paths=[portable_path(summary_path, repo_root=repo_root)],
            )
        )
    else:
        try:
            blockers = verify_bridge_summary_contract(
                summary_path=summary_path,
                artifacts_root=artifacts_root,
            )
        except Exception as exc:
            blockers = [f"bridge summary unreadable: {exc}"]
        if blockers:
            findings.append(
                _finding(
                    code="bridge_summary_contract_violation",
                    scope=f"bridge_summary:{as_of}",
                    message="bridge summary contract violations detected: " + " | ".join(blockers),
                    classification=bridge_classification,
                    evidence_paths=[portable_path(summary_path, repo_root=repo_root)],
                )
            )
    return findings


def build_repo_health_anomaly_findings(*, as_of: str, artifacts_root: Path) -> list[dict[str, Any]]:
    experiments = _load_canonical_experiments(artifacts_root=artifacts_root, as_of=as_of)
    findings: list[dict[str, Any]] = []
    positive_control_path = positive_control_summary_path(artifacts_root=artifacts_root, as_of=as_of)
    if positive_control_path.exists():
        try:
            positive_control_summary = read_json(positive_control_path)
        except Exception:
            positive_control_summary = None
        if isinstance(positive_control_summary, dict):
            strong_oracle_cases = [
                case
                for case in list(positive_control_summary.get("control_cases") or [])
                if isinstance(case, dict)
                and str(case.get("control_kind") or "") == "strong_oracle"
                and str(case.get("status") or "") == "executed"
            ]
            single_asset_strong_cases = [
                case for case in strong_oracle_cases if str(case.get("shape") or "") == "single_asset"
            ]
            failed_single_asset_cases = [
                str(case.get("control_id") or "")
                for case in single_asset_strong_cases
                if not bool(case.get("raw_positive"))
            ]
            if failed_single_asset_cases:
                findings.append(
                    _finding(
                        code="single_asset_pipeline_regression",
                        scope=f"positive_controls:{as_of}",
                        message=(
                            "single-asset positive controls regressed: strong_oracle raw_positive failed for "
                            + ", ".join(failed_single_asset_cases)
                        ),
                        evidence_paths=[portable_path(positive_control_path, repo_root=ROOT)],
                        recommended_manual_action=(
                            "Repair the single-asset score-to-position-to-PnL path before trusting today's single-asset results."
                        ),
                    )
                )
            elif str(positive_control_summary.get("pipeline_health") or "") == "marginal":
                findings.append(
                    _finding(
                        code="positive_control_marginal",
                        scope=f"positive_controls:{as_of}",
                        message=(
                            "positive controls remain marginal for as_of="
                            f"{as_of}: {str(positive_control_summary.get('pipeline_health_rationale') or '').strip()}"
                        ),
                        blocking=False,
                        evidence_paths=[portable_path(positive_control_path, repo_root=ROOT)],
                        recommended_manual_action=(
                            "Treat this as weak-oracle headroom telemetry; investigate only if the marginal state persists."
                        ),
                    )
                )
    publication_contract = load_publication_contract()
    threshold = float(publication_threshold(publication_contract, "sharpe_anomaly_quarantine_threshold", 5.0))
    for experiment in experiments:
        alpha_card = dict(experiment["alpha_card"])
        alpha_id = str(alpha_card.get("experiment_id") or "").strip()
        anomaly = sharpe_anomaly_details(
            validation_metrics=dict(alpha_card.get("validation_metrics") or {}),
            test_metrics=dict(alpha_card.get("test_metrics") or {}),
            walk_forward=dict(alpha_card.get("walk_forward") or {}),
            threshold=threshold,
        )
        if anomaly is None:
            continue
        findings.append(
            _finding(
                code="sharpe_anomaly_detected",
                scope=f"alpha:{alpha_id}",
                message=(
                    f"Sharpe anomaly remains quarantined for alpha_id={alpha_id}: "
                    f"{anomaly['metric']}={anomaly['value']:.3f} exceeds threshold {threshold:.3f}"
                ),
                blocking=False,
                evidence_paths=[
                    portable_path(Path(str(experiment["alpha_card_path"])), repo_root=ROOT),
                    portable_path(postmortem_evidence_path(artifacts_root=artifacts_root, alpha_id=alpha_id), repo_root=ROOT),
                ],
                recommended_manual_action="Review the pending leakage audit and anomaly postmortem before trusting this alpha.",
            )
        )
    quality_path = artifacts_root / "cycles" / as_of / "research_quality_summary.json"
    if quality_path.exists():
        payload = read_json(quality_path)
        median_summary = dict(payload.get("cross_sectional_median_oos_sharpe") or {})
        if int(median_summary.get("count") or 0) > 0 and float(median_summary.get("median") or 0.0) <= 0.0:
            findings.append(
                _finding(
                    code="research_quality_warning",
                    scope=f"research_quality:{as_of}",
                    message=(
                        f"cross-sectional research quality remains poor for as_of={as_of}: "
                        f"median_oos_sharpe={float(median_summary.get('median') or 0.0):.4f}"
                    ),
                    blocking=False,
                    evidence_paths=[portable_path(quality_path, repo_root=ROOT)],
                    recommended_manual_action="Treat this as research-health telemetry, not a publication threshold problem.",
                )
            )
    return findings


def repair_quant_repo_artifacts(
    *,
    as_of: str,
    repo_root: Path,
    artifacts_root: Path,
    workbench_root: Path,
    findings: list[dict[str, Any]],
    now_utc: str,
) -> tuple[list[str], list[str]]:
    repairs: list[str] = []
    repaired_paths: list[str] = []
    codes = {str(item["code"]) for item in findings}

    experiments = _load_canonical_experiments(artifacts_root=artifacts_root, as_of=as_of)
    if "daily_alpha_manifest_missing" in codes or "daily_alpha_manifest_drift" in codes:
        payload = write_daily_alpha_manifest_from_artifacts(
            artifacts_root=artifacts_root,
            as_of=as_of,
        )
        repairs.append("rebuild_daily_alpha_manifest")
        repaired_paths.append(portable_path(Path(str(payload["path"])), repo_root=repo_root))

    strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    strategy_entries = {
        str(entry.get("strategy_id")): dict(entry)
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }
    if "leakage_audit_missing" in codes:
        for experiment in experiments:
            alpha_card = dict(experiment["alpha_card"])
            alpha_id = str(alpha_card.get("experiment_id") or "").strip()
            strategy_entry = strategy_entries.get(str(alpha_card.get("strategy_id") or "").strip())
            assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=strategy_entry,
                artifacts_root=artifacts_root,
            )
            blockers = list(assessment.get("quality_blockers") or [])
            if not leakage_audit_is_required(alpha_card=alpha_card, quality_blockers=blockers):
                continue
            audit = write_pending_leakage_audit(
                artifacts_root=artifacts_root,
                as_of=as_of,
                alpha_card_path=Path(str(experiment["alpha_card_path"])),
                alpha_card=alpha_card,
                quality_blockers=blockers,
                overwrite_existing_pending=True,
            )
            if audit is not None:
                repairs.append(f"write_pending_leakage_audit:{alpha_id}")
                repaired_paths.append(str(audit["leakage_audit_path"]))

    if (
        "promotion_decision_missing" in codes
        or "promotion_decision_drift" in codes
        or "leakage_audit_missing" in codes
    ):
        decisions = write_promotion_decisions_for_manifest(
            artifacts_root=artifacts_root,
            as_of=as_of,
            strategy_library=strategy_library,
        )
        repairs.append("rebuild_promotion_decisions")
        repaired_paths.extend(str(item["promotion_decision_path"]) for item in decisions)

    if "positive_control_summary_missing" in codes or "positive_control_summary_drift" in codes:
        positive_controls = write_positive_control_summary(
            as_of=as_of,
            artifacts_root=artifacts_root,
            repo_root=repo_root,
            now_utc=now_utc,
        )
        repairs.append("rebuild_positive_control_summary")
        repaired_paths.append(str(positive_controls["positive_control_summary_path"]))
        repaired_paths.append(str(positive_controls["positive_control_markdown_path"]))

    if "sharpe_anomaly_postmortem_missing" in codes:
        threshold = float(publication_threshold(load_publication_contract(), "sharpe_anomaly_quarantine_threshold", 5.0))
        for experiment in experiments:
            alpha_card = dict(experiment["alpha_card"])
            alpha_id = str(alpha_card.get("experiment_id") or "").strip()
            if str(alpha_card.get("shape") or "") != "single_asset":
                continue
            anomaly = sharpe_anomaly_details(
                validation_metrics=dict(alpha_card.get("validation_metrics") or {}),
                test_metrics=dict(alpha_card.get("test_metrics") or {}),
                walk_forward=dict(alpha_card.get("walk_forward") or {}),
                threshold=threshold,
            )
            if anomaly is None:
                continue
            result = write_sharpe_anomaly_postmortem(
                alpha_id=alpha_id,
                artifacts_root=artifacts_root,
                repo_root=repo_root,
                now_utc=now_utc,
                write_markdown=False,
            )
            repairs.append(f"write_sharpe_postmortem:{alpha_id}")
            repaired_paths.append(str(result["postmortem_evidence_path"]))

    if "alpha_registry_missing" in codes or "alpha_registry_drift" in codes:
        registry = update_alpha_registry(
            artifacts_root=artifacts_root,
            as_of=as_of,
            experiments=experiments,
        )
        repairs.append("rebuild_alpha_registry")
        repaired_paths.append(portable_path(Path(str(registry["registry_path"])), repo_root=repo_root))

    if "research_quality_summary_missing" in codes or "research_quality_summary_drift" in codes:
        quality = write_research_quality_summary(
            path=artifacts_root / "cycles" / as_of / "research_quality_summary.json",
            experiments=experiments,
            artifacts_root=artifacts_root,
            scope="daily_cycle",
            as_of=as_of,
            canonical_universe_count=len(_expected_manifest_entries_from_experiments(experiments=experiments)),
        )
        repairs.append("rebuild_research_quality_summary")
        repaired_paths.append(str(quality["research_quality_summary_path"]))

    if "bridge_summary_missing" in codes or "bridge_summary_contract_violation" in codes:
        publication_contract = load_publication_contract()
        archive_only_stages = {str(item) for item in publication_contract.get("archive_only_stages", [])}
        if current_project_stage() in archive_only_stages:
            bridge_summary = export_passed_alphas_to_workbench(
                as_of=as_of,
                artifacts_root=artifacts_root,
                workbench_root=workbench_root,
                queue="quant",
            )
            repairs.append("rebuild_bridge_exports")
            repaired_paths.append(portable_path(Path(str(bridge_summary["bridge_summary_path"])), repo_root=repo_root))

    return repairs, sorted(set(repaired_paths))


def write_repo_health_incidents(
    *,
    artifacts_root: Path,
    findings: list[dict[str, Any]],
    generated_at_utc: str,
    auto_repair_attempted: bool,
    repair_succeeded: bool,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    root = incidents_root(artifacts_root=artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    for finding in findings:
        code = str(finding["code"])
        scope_slug = _scope_slug(str(finding.get("scope") or "global"))
        timestamp = generated_at_utc.replace(":", "").replace("-", "").replace("+", "")
        path = root / f"{timestamp}__{code}__{scope_slug}.json"
        payload = {
            "contract_version": REPO_HEALTH_INCIDENT_CONTRACT_VERSION,
            "generated_at_utc": generated_at_utc,
            "severity": "warning" if not bool(finding["blocking"]) else "error",
            "code": code,
            "scope": str(finding.get("scope") or ""),
            "message": str(finding.get("message") or ""),
            "classification": str(finding.get("classification") or ""),
            "auto_repair_attempted": auto_repair_attempted,
            "repair_succeeded": repair_succeeded,
            "blocking": bool(finding["blocking"]),
            "evidence_paths": list(finding.get("evidence_paths") or []),
            "recommended_manual_action": str(finding.get("recommended_manual_action") or ""),
        }
        write_json(path, payload)
        outputs.append({"incident_path": portable_path(path, repo_root=ROOT), "code": code, "scope": payload["scope"]})
    return outputs


def _write_repo_health_summary(
    *,
    artifacts_root: Path,
    as_of: str,
    generated_at_utc: str,
    findings: list[dict[str, Any]],
    repair_status: str,
    repair_action_count: int,
    repaired_paths: list[str],
    incident_paths: list[str],
    input_watermarks: dict[str, Any],
    upstream_versions: dict[str, Any],
    positive_control_view: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "contract_version": REPO_HEALTH_SUMMARY_CONTRACT_VERSION,
        "generated_at_utc": generated_at_utc,
        "as_of": as_of,
        "status": "failed" if any(bool(item["blocking"]) for item in findings) else "passed",
        "findings": findings,
        "repair_status": repair_status,
        "repair_action_count": repair_action_count,
        "repaired_paths": repaired_paths,
        "incident_paths": incident_paths,
        "artifact_family": REPO_HEALTH_ARTIFACT_FAMILY,
        "child_contract_version": REPO_HEALTH_CHILD_SUMMARY_CONTRACT_VERSION,
        "input_watermarks": input_watermarks,
        "upstream_versions": upstream_versions,
        **positive_control_view,
        "blocking_findings": [
            {
                "code": item["code"],
                "scope": item.get("scope"),
                "message": item["message"],
            }
            for item in findings
            if bool(item["blocking"])
        ],
    }
    path = repo_health_summary_path(artifacts_root=artifacts_root, as_of=as_of)
    write_json(path, summary)
    return {
        "artifact_family": REPO_HEALTH_ARTIFACT_FAMILY,
        "contract_version": REPO_HEALTH_CHILD_SUMMARY_CONTRACT_VERSION,
        "summary_path": portable_path(path, repo_root=ROOT),
        "status": summary["status"],
        "generated_at_utc": generated_at_utc,
        "as_of": as_of,
        "findings": findings,
        "repair_status": repair_status,
        "repair_action_count": repair_action_count,
        "repaired_paths": repaired_paths,
        "incident_count": len(incident_paths),
        "incident_paths": incident_paths,
        "blocking_findings": summary["blocking_findings"],
        "input_watermarks": input_watermarks,
        "upstream_versions": upstream_versions,
        **positive_control_view,
    }


def _load_canonical_experiments(*, artifacts_root: Path, as_of: str) -> list[dict[str, Any]]:
    experiments_root = artifacts_root / "experiments"
    strategy_entries: dict[str, dict[str, Any]] = {}
    try:
        strategy_library = load_strategy_library(artifacts_root=artifacts_root)
        strategy_entries = {
            str(entry.get("strategy_id")): dict(entry)
            for entry in strategy_library.get("entries", [])
            if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
        }
    except FileNotFoundError:
        strategy_entries = {}
    experiments_by_id: dict[str, dict[str, Any]] = {}
    for alpha_card_path in sorted(experiments_root.glob("*/alpha_card.json")):
        alpha_card = read_json(alpha_card_path)
        if str(alpha_card.get("as_of") or "").strip() != as_of:
            continue
        experiment_id = str(alpha_card.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        validation_report_path = alpha_card_path.parent / "validation_report.json"
        backtest_report_path = alpha_card_path.parent / "backtest_report.json"
        experiment_spec_path = alpha_card_path.parent / "experiment_spec.json"
        validation_report = read_json(validation_report_path) if validation_report_path.exists() else {}
        experiment_spec = read_json(experiment_spec_path) if experiment_spec_path.exists() else {}
        strategy_entry = strategy_entries.get(str(alpha_card.get("strategy_id") or "").strip(), {})
        candidate = {
            "experiment_id": experiment_id,
            "strategy_id": alpha_card.get("strategy_id"),
            "alpha_card": alpha_card,
            "alpha_card_path": str(alpha_card_path),
            "validation_report": validation_report,
            "validation_report_path": str(validation_report_path),
            "backtest_report_path": str(backtest_report_path),
            "experiment_spec": experiment_spec,
            "experiment_spec_path": str(experiment_spec_path),
            "shape": alpha_card.get("shape"),
            "model_family": alpha_card.get("model_family"),
            "strategy_profile": alpha_card.get("strategy_profile"),
            "subject": alpha_card.get("subject"),
            "source": alpha_card.get("source"),
            "spec_hash": alpha_card.get("spec_hash"),
            "compiler_backend": alpha_card.get("compiler_backend"),
            "backend_mode": alpha_card.get("backend_mode"),
            "experiment_status": alpha_card.get("experiment_status"),
            "validation": alpha_card.get("validation"),
            "publication_status": alpha_card.get("publication_status"),
            "quality_summary": alpha_card.get("quality_summary"),
            "validation_metrics": alpha_card.get("validation_metrics") or validation_report.get("validation_metrics"),
            "test_metrics": alpha_card.get("test_metrics") or validation_report.get("test_metrics"),
            "walk_forward": alpha_card.get("walk_forward") or validation_report.get("walk_forward"),
            "lifecycle": strategy_entry.get("lifecycle", "active"),
            "monitoring_status": strategy_entry.get("monitoring_status", strategy_entry.get("lifecycle", "active")),
            "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_entry.get("lifecycle", "active"))),
            "promotion_state": strategy_entry.get("promotion_state", "staged"),
        }
        current = experiments_by_id.get(experiment_id)
        if current is None or _canonical_experiment_preference_key(candidate) > _canonical_experiment_preference_key(current):
            experiments_by_id[experiment_id] = candidate
    return list(experiments_by_id.values())


def _canonical_experiment_preference_key(experiment: dict[str, Any]) -> tuple[str, float, str]:
    alpha_card = dict(experiment.get("alpha_card") or {})
    alpha_card_path = Path(str(experiment.get("alpha_card_path") or ""))
    modified_time = 0.0
    if alpha_card_path.exists():
        try:
            modified_time = float(alpha_card_path.stat().st_mtime)
        except OSError:
            modified_time = 0.0
    return (
        str(alpha_card.get("generated_at_utc") or ""),
        modified_time,
        str(experiment.get("alpha_card_path") or ""),
    )


def _expected_manifest_entries_from_experiments(*, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for experiment in experiments:
        alpha_card = experiment.get("alpha_card")
        alpha_card_path = experiment.get("alpha_card_path")
        if not isinstance(alpha_card, dict) or not str(alpha_card_path or "").strip():
            continue
        entry = build_daily_alpha_manifest_entry(
            alpha_card_path=Path(str(alpha_card_path)),
            alpha_card=alpha_card,
        )
        if entry is not None:
            entries.append(entry)
    return sorted(entries, key=lambda item: str(item.get("experiment_id") or ""))


def _promotion_decision_has_drift(
    *,
    decision: dict[str, Any],
    alpha_card: dict[str, Any],
    alpha_card_path: Path,
    strategy_entry: dict[str, Any] | None,
    strategy_library_path: Path,
    artifacts_root: Path,
) -> bool:
    if strategy_entry is None:
        return True
    input_hashes = dict(decision.get("input_hashes") or {})
    expected_hashes = {
        "alpha_card_sha256": sha256_path(alpha_card_path),
        "strategy_entry_sha256": sha256_json({key: value for key, value in strategy_entry.items() if key != "strategy_library_path"}),
        "strategy_library_sha256": sha256_path(strategy_library_path),
    }
    for field_name, expected_hash in expected_hashes.items():
        if str(input_hashes.get(field_name) or "") != expected_hash:
            return True
    assessment = evaluate_quant_publication_assessment(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry,
        artifacts_root=artifacts_root,
    )
    if str(decision.get("backend_mode") or "") != str(assessment.get("backend_mode") or ""):
        return True
    expected_publication_status = (
        str(assessment.get("publication_status") or "")
        if str(decision.get("decision") or "") == "approved"
        else "blocked"
    )
    if str(decision.get("publication_status") or "") != expected_publication_status:
        return True
    if str(decision.get("validation") or "") != str(assessment.get("validation") or ""):
        return True
    if sorted(str(item) for item in decision.get("quality_blockers", [])) != sorted(str(item) for item in assessment.get("quality_blockers", [])):
        return True
    return False


def _comparable_quality_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": payload.get("scope"),
        "as_of": payload.get("as_of"),
        "canonical_universe_count": payload.get("canonical_universe_count"),
        "experiment_count": payload.get("experiment_count"),
        "experiment_status_counts": payload.get("experiment_status_counts"),
        "raw_pass_rate": payload.get("raw_pass_rate"),
        "audit_cleared_pass_rate": payload.get("audit_cleared_pass_rate"),
        "cross_sectional_median_oos_sharpe": payload.get("cross_sectional_median_oos_sharpe"),
        "walk_forward_window_count": payload.get("walk_forward_window_count"),
        "sharpe_anomaly_candidates": payload.get("sharpe_anomaly_candidates"),
    }


def _comparable_validation_contract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    blocker_codes = [
        str(item).strip()
        for item in list(payload.get("blocker_codes") or [])
        if str(item).strip()
    ]
    if not blocker_codes:
        blocker_codes = [
            str(item.get("code") or "").strip()
            for item in list(payload.get("blockers") or [])
            if isinstance(item, dict) and str(item.get("code") or "").strip()
        ]
    return {
        "contract_version": payload.get("contract_version"),
        "status": payload.get("status"),
        "required_sections_present": payload.get("required_sections_present"),
        "blocker_codes": blocker_codes,
    }


def _scan_positive_control_summary(
    *,
    as_of: str,
    repo_root: Path,
    artifacts_root: Path,
) -> list[dict[str, Any]]:
    path = positive_control_summary_path(artifacts_root=artifacts_root, as_of=as_of)
    if not path.exists():
        return [
            _finding(
                code="positive_control_summary_missing",
                scope=f"positive_controls:{as_of}",
                message=f"positive control summary is missing for as_of={as_of}",
                evidence_paths=[portable_path(path, repo_root=repo_root)],
            )
        ]
    try:
        current_summary = read_json(path)
    except Exception:
        return [
            _finding(
                code="positive_control_summary_drift",
                scope=f"positive_controls:{as_of}",
                message=f"positive control summary is unreadable for as_of={as_of}",
                evidence_paths=[portable_path(path, repo_root=repo_root)],
            )
        ]
    try:
        expected_summary = build_positive_control_summary(
            as_of=as_of,
            artifacts_root=artifacts_root,
            repo_root=repo_root,
        )
    except Exception as exc:
        return [
            _finding(
                code="positive_control_summary_drift",
                scope=f"positive_controls:{as_of}",
                message=f"positive control summary could not be rebuilt for as_of={as_of}: {exc}",
                evidence_paths=[portable_path(path, repo_root=repo_root)],
            )
        ]
    if sha256_json(_comparable_positive_control_payload(current_summary)) == sha256_json(
        _comparable_positive_control_payload(expected_summary)
    ):
        return []
    return [
        _finding(
            code="positive_control_summary_drift",
            scope=f"positive_controls:{as_of}",
            message=f"positive control summary is stale relative to current overlap-fixed inputs for as_of={as_of}",
            evidence_paths=[portable_path(path, repo_root=repo_root)],
        )
    ]


def _comparable_positive_control_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": payload.get("contract_version"),
        "evidence_family": payload.get("evidence_family"),
        "as_of": payload.get("as_of"),
        "dataset_ids": payload.get("dataset_ids"),
        "feature_set_ids": payload.get("feature_set_ids"),
        "benchmark_constraints_profile": payload.get("benchmark_constraints_profile"),
        "subject_count_by_shape": payload.get("subject_count_by_shape"),
        "control_cases": payload.get("control_cases"),
        "coverage_telemetry": payload.get("coverage_telemetry"),
        "pipeline_health": payload.get("pipeline_health"),
        "pipeline_health_rationale": payload.get("pipeline_health_rationale"),
        "lane_interpretation": payload.get("lane_interpretation"),
        "real_lane_reference": payload.get("real_lane_reference"),
    }


def _scan_compileall(*, repo_root: Path) -> list[dict[str, Any]]:
    if compileall.compile_dir(str(repo_root / "src"), quiet=1):
        return []
    return [
        _finding(
            code="compileall_failed",
            scope="src",
            message="compileall failed for src/",
            evidence_paths=["src"],
            recommended_manual_action="Restore the broken Python source files before running repo health guard again.",
        )
    ]


def _scan_disk_integrity(*, repo_root: Path) -> list[dict[str, Any]]:
    failures: list[str] = []
    targets = list((repo_root / "src").rglob("*.py")) + list((repo_root / "config").rglob("*.json"))
    for path in sorted(targets):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            failures.append(f"{portable_path(path, repo_root=repo_root)}: unable to read ({exc})")
            continue
        if b"\x00" in raw:
            failures.append(f"{portable_path(path, repo_root=repo_root)}: contains NUL byte(s)")
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            failures.append(f"{portable_path(path, repo_root=repo_root)}: UTF-8 decode failed ({exc})")
    if not failures:
        return []
    return [
        _finding(
            code="disk_integrity_failed",
            scope="src+config",
            message="disk integrity scan found source/config corruption: " + " | ".join(failures),
            evidence_paths=failures,
            recommended_manual_action="Rehydrate or restore the corrupted source/config files, then rerun the guard.",
        )
    ]


def _scan_json_parse(*, repo_root: Path) -> list[dict[str, Any]]:
    failures: list[str] = []
    for path in sorted((repo_root / "config").rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            failures.append(f"{portable_path(path, repo_root=repo_root)}: {exc}")
    if not failures:
        return []
    return [
        _finding(
            code="config_json_parse_failed",
            scope="config",
            message="config JSON parse failed: " + " | ".join(failures),
            evidence_paths=failures,
            recommended_manual_action="Fix the malformed config JSON before running repo health guard again.",
        )
    ]


def _scan_runtime_ownership_docs(*, repo_root: Path) -> list[dict[str, Any]]:
    contract_path = repo_root / "config" / "project_governance" / "runtime_ownership_contract.json"
    contract = read_json(contract_path)
    expected_phase = str(contract.get("runtime_ownership_phase") or "").strip()
    expected_enforced = str(bool(contract.get("owner_verification_enforced_in_boundary_gates"))).lower()
    contract_ref = "config/project_governance/runtime_ownership_contract.json"
    mismatches: list[str] = []
    for relative_path in RUNTIME_DOC_PATHS:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        if contract_ref not in text:
            mismatches.append(f"{relative_path}: missing machine-source contract reference")
        if relative_path in {"PROJECT_STATE.md", "docs/README_FOR_AGENT.md"}:
            if f"runtime_ownership_phase = {expected_phase}" not in text:
                mismatches.append(f"{relative_path}: missing runtime_ownership_phase = {expected_phase}")
            if f"owner_verification_enforced_in_boundary_gates = {expected_enforced}" not in text:
                mismatches.append(f"{relative_path}: missing owner_verification_enforced_in_boundary_gates = {expected_enforced}")
        if relative_path == "docs/agents/OWNER_AGENT_ARCHITECTURE.md" and f"runtime ownership phase is `{expected_phase}`" not in text:
            mismatches.append(f"{relative_path}: missing runtime ownership phase prose for {expected_phase}")
    if not mismatches:
        return []
    return [
        _finding(
            code="runtime_ownership_doc_drift",
            scope="docs",
            message="runtime ownership docs drifted from machine-source contract: " + " | ".join(mismatches),
            evidence_paths=[contract_ref, *mismatches],
            recommended_manual_action="Update the tracked docs to match runtime_ownership_contract.json.",
        )
    ]


def _scan_gitignore(*, repo_root: Path) -> list[dict[str, Any]]:
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    missing = [line for line in REQUIRED_GITIGNORE_LINES if line not in text]
    if not missing:
        return []
    return [
        _finding(
            code="gitignore_whitelist_drift",
            scope=".gitignore",
            message="critical quant artifact whitelist entries are missing from .gitignore: " + ", ".join(missing),
            evidence_paths=[".gitignore"],
            recommended_manual_action="Restore the tracked quant artifact whitelist lines in .gitignore.",
        )
    ]


def _scan_threshold_provenance(*, repo_root: Path) -> list[dict[str, Any]]:
    publication_contract = read_json(repo_root / "config" / "quant_research" / "publication_contract.json")
    provenance_path = repo_root / "config" / "quant_research" / "threshold_provenance.md"
    rows = _read_markdown_table(
        provenance_path,
        required_headers={
            "threshold_key",
            "value",
            "source_type",
            "source_reference",
            "evidence_basis",
            "review_status",
            "owner",
            "next_review_action",
        },
    )
    threshold_keys = sorted(str(key) for key in publication_contract.get("thresholds", {}).keys())
    row_keys = sorted(str(row.get("threshold_key") or "") for row in rows)
    problems: list[str] = []
    if row_keys != threshold_keys:
        problems.append(f"row_keys={row_keys} threshold_keys={threshold_keys}")
    allowed_source_types = {"literature", "empirical_distribution", "engineering_default_pending_review"}
    for row in rows:
        source_type = str(row.get("source_type") or "").strip()
        if source_type not in allowed_source_types:
            problems.append(f"{row.get('threshold_key')}: invalid source_type={source_type}")
            continue
        if not str(row.get("source_reference") or "").strip():
            problems.append(f"{row.get('threshold_key')}: missing source_reference")
        if not str(row.get("evidence_basis") or "").strip():
            problems.append(f"{row.get('threshold_key')}: missing evidence_basis")
    if not problems:
        return []
    return [
        _finding(
            code="threshold_provenance_drift",
            scope="threshold_provenance",
            message="threshold provenance is incomplete or malformed: " + " | ".join(problems),
            evidence_paths=[portable_path(provenance_path, repo_root=repo_root)],
            recommended_manual_action="Update threshold_provenance.md so every publication threshold has one valid provenance row.",
        )
    ]


def _scan_quant_status_aliases(*, repo_root: Path) -> list[dict[str, Any]]:
    offenders: list[str] = []
    for path in (repo_root / "src" / "enhengclaw" / "quant_research").rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if any(pattern in line for pattern in FORBIDDEN_STATUS_PATTERNS):
                offenders.append(f"{portable_path(path, repo_root=repo_root)}:{line_number}:{line.strip()}")
    if not offenders:
        return []
    return [
        _finding(
            code="legacy_status_alias_drift",
            scope="quant_research",
            message="quant_research source reintroduced legacy status/governance_status compatibility reads",
            evidence_paths=offenders,
            recommended_manual_action="Remove the legacy status/governance_status fallback reads from quant_research source.",
        )
    ]


def _input_watermarks(*, artifacts_root: Path, as_of: str) -> dict[str, Any]:
    watermarks: dict[str, Any] = {}
    cycle_summary_path = artifacts_root / "cycles" / as_of / "quant_cycle_summary.json"
    if cycle_summary_path.exists():
        cycle_summary = read_json(cycle_summary_path)
        watermarks["quant_research_daily_cycle_produced_at_utc"] = cycle_summary.get("produced_at_utc") or cycle_summary.get("generated_at_utc")
    manifest_path = daily_alpha_manifest_path(artifacts_root=artifacts_root, as_of=as_of)
    if manifest_path.exists():
        watermarks["daily_alpha_manifest_generated_at_utc"] = read_json(manifest_path).get("generated_at_utc")
    bridge_summary = artifacts_root / "bridge_exports" / as_of / "bridge_summary.json"
    if bridge_summary.exists():
        bridge_payload = read_json(bridge_summary)
        watermarks["bridge_summary_generated_at_utc"] = bridge_payload.get("generated_at_utc") or bridge_payload.get("produced_at_utc")
    return watermarks


def _read_positive_control_view(*, artifacts_root: Path, as_of: str) -> dict[str, Any]:
    default_view = {
        "positive_control_pipeline_health": None,
        "positive_control_rationale": None,
        "single_asset_strong_oracle_all_raw_positive": None,
        "cross_sectional_strong_oracle_all_raw_positive": None,
        "single_asset_strong_oracle_executed_count": 0,
        "single_asset_strong_oracle_skipped_count": 0,
        "single_asset_weak_oracle_executed_count": 0,
        "single_asset_weak_oracle_skipped_count": 0,
    }
    path = positive_control_summary_path(artifacts_root=artifacts_root, as_of=as_of)
    if not path.exists():
        return default_view
    try:
        payload = read_json(path)
    except Exception:
        return default_view
    all_control_cases = [
        case for case in list(payload.get("control_cases") or []) if isinstance(case, dict)
    ]
    control_cases = [
        case
        for case in all_control_cases
        if str(case.get("control_kind") or "") == "strong_oracle"
        and str(case.get("status") or "") == "executed"
    ]
    single_asset_cases = [case for case in control_cases if str(case.get("shape") or "") == "single_asset"]
    cross_sectional_cases = [case for case in control_cases if str(case.get("shape") or "") == "cross_sectional"]
    coverage_telemetry = dict(payload.get("coverage_telemetry") or {})
    single_asset_coverage = dict(coverage_telemetry.get("single_asset") or {})
    if not single_asset_coverage:
        single_asset_coverage = {
            "strong_oracle": {
                "executed_count": sum(
                    1
                    for case in all_control_cases
                    if str(case.get("shape") or "") == "single_asset"
                    and str(case.get("control_kind") or "") == "strong_oracle"
                    and str(case.get("status") or "") == "executed"
                ),
                "skipped_count": sum(
                    1
                    for case in all_control_cases
                    if str(case.get("shape") or "") == "single_asset"
                    and str(case.get("control_kind") or "") == "strong_oracle"
                    and str(case.get("status") or "").startswith("skipped")
                ),
            },
            "weak_oracle": {
                "executed_count": sum(
                    1
                    for case in all_control_cases
                    if str(case.get("shape") or "") == "single_asset"
                    and str(case.get("control_kind") or "") == "weak_oracle"
                    and str(case.get("status") or "") == "executed"
                ),
                "skipped_count": sum(
                    1
                    for case in all_control_cases
                    if str(case.get("shape") or "") == "single_asset"
                    and str(case.get("control_kind") or "") == "weak_oracle"
                    and str(case.get("status") or "").startswith("skipped")
                ),
            },
        }
    strong_coverage = dict(single_asset_coverage.get("strong_oracle") or {})
    weak_coverage = dict(single_asset_coverage.get("weak_oracle") or {})
    return {
        "positive_control_pipeline_health": payload.get("pipeline_health"),
        "positive_control_rationale": payload.get("pipeline_health_rationale"),
        "single_asset_strong_oracle_all_raw_positive": (
            all(bool(case.get("raw_positive")) for case in single_asset_cases) if single_asset_cases else None
        ),
        "cross_sectional_strong_oracle_all_raw_positive": (
            all(bool(case.get("raw_positive")) for case in cross_sectional_cases) if cross_sectional_cases else None
        ),
        "single_asset_strong_oracle_executed_count": int(strong_coverage.get("executed_count", 0) or 0),
        "single_asset_strong_oracle_skipped_count": int(strong_coverage.get("skipped_count", 0) or 0),
        "single_asset_weak_oracle_executed_count": int(weak_coverage.get("executed_count", 0) or 0),
        "single_asset_weak_oracle_skipped_count": int(weak_coverage.get("skipped_count", 0) or 0),
    }


def _upstream_versions(*, as_of: str) -> dict[str, Any]:
    publication_contract = load_publication_contract()
    archive_only_stages = {str(item) for item in publication_contract.get("archive_only_stages", [])}
    current_stage = current_project_stage()
    return {
        "as_of": as_of,
        "current_stage": current_stage,
        "auto_repair_scope": "artifacts_only",
        "archive_only_bridge_repair_enabled": current_stage in archive_only_stages,
    }


def _read_markdown_table(path: Path, *, required_headers: set[str] | None = None) -> list[dict[str, str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not (line.startswith("|") and line.endswith("|")):
            continue
        if index + 1 >= len(lines):
            continue
        separator = lines[index + 1]
        separator_body = set(separator.replace("|", "").strip())
        if not (
            separator.startswith("|")
            and separator.endswith("|")
            and separator_body <= {"-", ":", " "}
        ):
            continue
        headers = [cell.strip() for cell in line.strip("|").split("|")]
        if required_headers and not required_headers.issubset(set(headers)):
            continue
        rows: list[dict[str, str]] = []
        for row_line in lines[index + 2 :]:
            if not (row_line.startswith("|") and row_line.endswith("|")):
                break
            cells = [cell.strip() for cell in row_line.strip("|").split("|")]
            if len(cells) != len(headers):
                continue
            rows.append(dict(zip(headers, cells)))
        return rows
    return []


def _finding(
    *,
    code: str,
    scope: str,
    message: str,
    classification: str | None = None,
    blocking: bool | None = None,
    evidence_paths: list[str] | None = None,
    recommended_manual_action: str | None = None,
) -> dict[str, Any]:
    resolved_classification = classification or classify_repo_health_finding(code)
    resolved_blocking = (resolved_classification != "quarantine_only") if blocking is None else blocking
    return {
        "code": code,
        "scope": scope,
        "message": message,
        "classification": resolved_classification,
        "blocking": resolved_blocking,
        "evidence_paths": list(evidence_paths or []),
        "recommended_manual_action": recommended_manual_action or "",
    }


def _scope_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "global"


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for finding in findings:
        key = (
            str(finding.get("code") or ""),
            str(finding.get("scope") or ""),
            str(finding.get("message") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _materialize_final_findings(
    *,
    findings: list[dict[str, Any]],
    remaining_blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unresolved_keys = {
        (
            str(item.get("code") or ""),
            str(item.get("scope") or ""),
            str(item.get("message") or ""),
        )
        for item in remaining_blockers
    }
    final_findings: list[dict[str, Any]] = []
    for finding in findings:
        resolved = (
            finding.get("classification") == "auto_repairable"
            and (
                str(finding.get("code") or ""),
                str(finding.get("scope") or ""),
                str(finding.get("message") or ""),
            )
            not in unresolved_keys
        )
        item = dict(finding)
        if resolved:
            item["blocking"] = False
            item["resolved_by_guard"] = True
        final_findings.append(item)
    return final_findings
