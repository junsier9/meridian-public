from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from scripts.market_data.binance_ohlcv import interval_manifest_path, resolve_external_history_root

from .contracts import (
    QuantUniverseCandidate,
    pit_universe_artifact_metadata,
    portable_path,
    read_json,
    write_json,
)
from .data_readiness import resolve_default_spot_ohlcv_external_root
from .deterministic_core import load_deterministic_strategy_manifest
from .execution_cost_model import EXECUTION_COST_MODEL_VERSION, load_execution_cost_model
from .runtime_support import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
    load_quant_universe_snapshot,
    resolve_quant_input_path,
)
from .validation_contract import VALIDATION_CONTRACT_VERSION, load_validation_contract, validation_contract_blocker_codes


ROOT = Path(__file__).resolve().parents[3]
BASELINE_ALPHA_PROOF_FIXTURE_PATH = ROOT / "config" / "quant_research" / "baseline_alpha_proof_fixture.json"
BASELINE_ALPHA_PROOF_FIXTURE_CONTRACT_VERSION = "quant_baseline_alpha_proof_fixture.v1"
BASELINE_ALPHA_PROOF_CONTRACT_VERSION = "quant_baseline_alpha_proof.v1"
BASELINE_ALPHA_PROOF_TARGET = "single_asset_deterministic"
BASELINE_ALPHA_PROOF_WINNER_SELECTION_POLICY = "manifest_order_first_passing"
BASELINE_ALPHA_PROOF_ALLOWED_FALSIFICATION_STATUSES = frozenset({"cleared", "not_required"})


def load_baseline_alpha_proof_fixture(*, path: Path | None = None) -> dict[str, Any]:
    fixture_path = (path or BASELINE_ALPHA_PROOF_FIXTURE_PATH).expanduser().resolve()
    payload = read_json(fixture_path)
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != BASELINE_ALPHA_PROOF_FIXTURE_CONTRACT_VERSION:
        raise ValueError(
            "baseline alpha proof fixture contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    proof_target = str(payload.get("proof_target") or "").strip()
    if proof_target != BASELINE_ALPHA_PROOF_TARGET:
        raise ValueError(f"unsupported baseline alpha proof target: {proof_target or 'missing'}")
    strategy_ids = [
        str(item).strip()
        for item in list(payload.get("strategy_ids") or [])
        if str(item).strip()
    ]
    if not strategy_ids:
        raise ValueError("baseline alpha proof fixture must define a non-empty strategy_ids list")
    rerun_count = int(payload.get("rerun_count") or 0)
    if rerun_count < 2:
        raise ValueError("baseline alpha proof fixture rerun_count must be at least 2")
    winner_selection_policy = str(payload.get("winner_selection_policy") or "").strip()
    if winner_selection_policy != BASELINE_ALPHA_PROOF_WINNER_SELECTION_POLICY:
        raise ValueError(
            "unsupported baseline alpha proof winner_selection_policy: "
            f"{winner_selection_policy or 'missing'}"
        )
    return {
        "path": str(fixture_path),
        "contract_version": contract_version,
        "proof_target": proof_target,
        "as_of": str(payload.get("as_of") or "").strip(),
        "rerun_count": rerun_count,
        "winner_selection_policy": winner_selection_policy,
        "validation_contract_version": str(payload.get("validation_contract_version") or "").strip(),
        "execution_cost_model_version": str(payload.get("execution_cost_model_version") or "").strip(),
        "required_universe_definition_id": str(payload.get("required_universe_definition_id") or "").strip(),
        "required_universe_contract_version": str(payload.get("required_universe_contract_version") or "").strip(),
        "strategy_ids": strategy_ids,
    }


def run_baseline_alpha_proof(
    *,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    auto_detect_spot_ohlcv_external_root: bool = True,
    fixture_path: Path | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    fixture = load_baseline_alpha_proof_fixture(path=fixture_path)
    as_of = str(fixture["as_of"])
    cycle_root = resolved_artifacts_root / "cycles" / as_of
    cycle_root.mkdir(parents=True, exist_ok=True)
    proof_path = cycle_root / "baseline_alpha_proof.json"
    blockers: set[str] = set()

    resolved_spot_root = (
        resolve_default_spot_ohlcv_external_root(spot_ohlcv_external_root=spot_ohlcv_external_root)
        if auto_detect_spot_ohlcv_external_root
        else (None if spot_ohlcv_external_root is None else Path(spot_ohlcv_external_root).expanduser().resolve())
    )
    resolved_ohlcv_root = resolve_external_history_root(external_root=ohlcv_external_root)

    validation_contract = load_validation_contract()
    validation_contract_version = str(validation_contract.get("contract_version") or VALIDATION_CONTRACT_VERSION)
    execution_cost_model = load_execution_cost_model()
    execution_cost_model_version = str(execution_cost_model.get("contract_version") or EXECUTION_COST_MODEL_VERSION)
    if validation_contract_version != str(fixture["validation_contract_version"]):
        blockers.add("validation_contract_version_mismatch")
    if execution_cost_model_version != str(fixture["execution_cost_model_version"]):
        blockers.add("execution_cost_model_version_mismatch")

    strategy_manifest = load_deterministic_strategy_manifest()
    manifest_entries_by_id = {
        str(entry.get("strategy_id") or "").strip(): dict(entry)
        for entry in list(strategy_manifest.get("entries") or [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }
    pinned_entries: list[dict[str, Any]] = []
    for strategy_id in fixture["strategy_ids"]:
        entry = manifest_entries_by_id.get(strategy_id)
        if entry is None:
            blockers.add("missing_pinned_strategy_in_manifest")
            continue
        if str(entry.get("shape") or "").strip() != "single_asset":
            blockers.add("unsupported_proof_strategy_shape")
            continue
        pinned_entries.append(entry)

    quant_input_path: str | None = None
    universe_snapshot_path: str | None = None
    derivatives_sync_summary_path: str | None = None
    snapshot_candidates_by_subject: dict[str, QuantUniverseCandidate] = {}
    try:
        quant_input = resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)
        quant_input_path = str(quant_input)
    except FileNotFoundError:
        blockers.add("missing_quant_input")
    except Exception:
        blockers.add("invalid_quant_input")

    try:
        universe_snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=resolved_artifacts_root)
        universe_snapshot_path = str(universe_snapshot["path"])
        universe_metadata = pit_universe_artifact_metadata(universe_snapshot)
        if universe_metadata["universe_definition_id"] != str(fixture["required_universe_definition_id"]):
            blockers.add("universe_definition_id_mismatch")
        if universe_metadata["universe_contract_version"] != str(fixture["required_universe_contract_version"]):
            blockers.add("universe_contract_version_mismatch")
        snapshot_candidates_by_subject = {
            candidate.subject: candidate
            for candidate in (
                QuantUniverseCandidate.from_payload(item)
                for item in list(universe_snapshot.get("candidates") or [])
                if isinstance(item, dict)
            )
        }
    except FileNotFoundError:
        blockers.add("missing_universe_snapshot")
    except Exception:
        blockers.add("invalid_universe_snapshot")

    try:
        from .lab import require_derivatives_sync_summary

        _, resolved_derivatives_sync_summary_path = require_derivatives_sync_summary(
            as_of=as_of,
            derivatives_external_root=derivatives_external_root,
        )
        derivatives_sync_summary_path = str(resolved_derivatives_sync_summary_path)
    except FileNotFoundError:
        blockers.add("missing_derivatives_sync_summary")
    except Exception:
        blockers.add("invalid_derivatives_sync_summary")

    spot_manifest_checks: dict[str, dict[str, str | bool | None]] = {}
    for entry in pinned_entries:
        strategy_id = str(entry.get("strategy_id") or "").strip()
        subject = str(entry.get("subject") or "").strip().upper()
        candidate = snapshot_candidates_by_subject.get(subject)
        if candidate is None:
            blockers.add("missing_subject_in_universe_snapshot")
            spot_manifest_checks[strategy_id] = {
                "subject": subject,
                "spot_symbol": None,
                "spot_4h_manifest_path": None,
                "spot_1d_manifest_path": None,
                "spot_4h_present": False,
                "spot_1d_present": False,
            }
            continue
        manifest_4h = _resolve_spot_manifest_path(
            symbol=candidate.spot_symbol,
            interval="4h",
            fallback_root=resolved_ohlcv_root,
            spot_root=resolved_spot_root,
        )
        manifest_1d = _resolve_spot_manifest_path(
            symbol=candidate.spot_symbol,
            interval="1d",
            fallback_root=resolved_ohlcv_root,
            spot_root=resolved_spot_root,
        )
        manifest_4h_present = manifest_4h.exists()
        manifest_1d_present = manifest_1d.exists()
        if not manifest_4h_present or not manifest_1d_present:
            blockers.add("missing_spot_ohlcv_manifest")
        spot_manifest_checks[strategy_id] = {
            "subject": subject,
            "spot_symbol": candidate.spot_symbol,
            "spot_4h_manifest_path": portable_path(manifest_4h, repo_root=ROOT),
            "spot_1d_manifest_path": portable_path(manifest_1d, repo_root=ROOT),
            "spot_4h_present": manifest_4h_present,
            "spot_1d_present": manifest_1d_present,
        }

    if blockers:
        report = _build_proof_report(
            fixture=fixture,
            proof_passed=False,
            validation_contract_version=validation_contract_version,
            execution_cost_model_version=execution_cost_model_version,
            universe_definition_id=str(fixture["required_universe_definition_id"]),
            universe_contract_version=str(fixture["required_universe_contract_version"]),
            quant_input_path=quant_input_path,
            universe_snapshot_path=universe_snapshot_path,
            derivatives_sync_summary_path=derivatives_sync_summary_path,
            spot_manifest_checks=spot_manifest_checks,
            blocker_codes=sorted(blockers),
        )
        write_json(proof_path, report)
        report["baseline_alpha_proof_path"] = str(proof_path)
        return report

    cycle_results: list[dict[str, Any]] = []
    per_run_evidence: list[dict[str, dict[str, Any]]] = []
    cycle_errors: list[str] = []
    from .lab import run_quant_research_cycle

    for _ in range(int(fixture["rerun_count"])):
        try:
            summary = run_quant_research_cycle(
                as_of=as_of,
                compiler_backend="deterministic",
                artifacts_root=resolved_artifacts_root,
                quant_input_root=resolved_quant_input_root,
                workbench_root=resolved_workbench_root,
                ohlcv_external_root=ohlcv_external_root,
                spot_ohlcv_external_root=resolved_spot_root,
                derivatives_external_root=derivatives_external_root,
                auto_detect_spot_ohlcv_external_root=False,
                strategy_id_allowlist=list(fixture["strategy_ids"]),
            )
        except Exception as exc:
            cycle_errors.append(f"{type(exc).__name__}: {exc}")
            break
        cycle_results.append(summary)
        per_run_evidence.append(
            _collect_cycle_evidence(
                artifacts_root=resolved_artifacts_root,
                experiment_ids=[str(item).strip() for item in list(summary.get("experiment_ids") or []) if str(item).strip()],
            )
        )

    if cycle_errors or len(cycle_results) != int(fixture["rerun_count"]):
        blockers.update({"cycle_run_failed"})
        report = _build_proof_report(
            fixture=fixture,
            proof_passed=False,
            validation_contract_version=validation_contract_version,
            execution_cost_model_version=execution_cost_model_version,
            universe_definition_id=str(fixture["required_universe_definition_id"]),
            universe_contract_version=str(fixture["required_universe_contract_version"]),
            quant_input_path=quant_input_path,
            universe_snapshot_path=universe_snapshot_path,
            derivatives_sync_summary_path=derivatives_sync_summary_path,
            spot_manifest_checks=spot_manifest_checks,
            blocker_codes=sorted(blockers),
            cycle_results=cycle_results,
            cycle_errors=cycle_errors,
        )
        write_json(proof_path, report)
        report["baseline_alpha_proof_path"] = str(proof_path)
        return report

    run_1 = cycle_results[0]
    run_2 = cycle_results[1]
    if str(run_1.get("summary_hash") or "") != str(run_2.get("summary_hash") or ""):
        blockers.add("summary_hash_mismatch")

    per_strategy_evidence_hashes: dict[str, Any] = {}
    passing_strategy_ids: list[str] = []
    failing_strategies: list[dict[str, Any]] = []
    winner_strategy_id: str | None = None
    winner_experiment_id: str | None = None

    for strategy_id in fixture["strategy_ids"]:
        run_1_evidence = dict(per_run_evidence[0].get(strategy_id) or {})
        run_2_evidence = dict(per_run_evidence[1].get(strategy_id) or {})
        evidence_hash_consistent = (
            bool(run_1_evidence)
            and bool(run_2_evidence)
            and str(run_1_evidence.get("evidence_hash") or "") == str(run_2_evidence.get("evidence_hash") or "")
        )
        strategy_pass_blockers = _strategy_pass_blockers(
            run_1_evidence=run_1_evidence,
            run_2_evidence=run_2_evidence,
            evidence_hash_consistent=evidence_hash_consistent,
        )
        is_passing = not strategy_pass_blockers
        if is_passing:
            passing_strategy_ids.append(strategy_id)
            if winner_strategy_id is None:
                winner_strategy_id = strategy_id
                winner_experiment_id = str(run_1_evidence.get("experiment_id") or run_2_evidence.get("experiment_id") or "")
        else:
            failing_strategies.append(
                {
                    "strategy_id": strategy_id,
                    "run_1_experiment_id": run_1_evidence.get("experiment_id"),
                    "run_2_experiment_id": run_2_evidence.get("experiment_id"),
                    "run_1_validation_status": run_1_evidence.get("validation_status"),
                    "run_2_validation_status": run_2_evidence.get("validation_status"),
                    "run_1_falsification_status": run_1_evidence.get("falsification_status"),
                    "run_2_falsification_status": run_2_evidence.get("falsification_status"),
                    "run_1_credible_research_evidence": run_1_evidence.get("credible_research_evidence"),
                    "run_2_credible_research_evidence": run_2_evidence.get("credible_research_evidence"),
                    "blocker_codes": sorted(strategy_pass_blockers),
                }
            )
        per_strategy_evidence_hashes[strategy_id] = {
            "run_1": _public_evidence_summary(run_1_evidence),
            "run_2": _public_evidence_summary(run_2_evidence),
            "evidence_hash_consistent": evidence_hash_consistent,
            "passing": is_passing,
        }

    if passing_strategy_ids:
        if str(winner_strategy_id or "") != str(passing_strategy_ids[0]):
            blockers.add("winner_strategy_mismatch")
    else:
        blockers.add("no_passing_strategy")

    proof_passed = bool(passing_strategy_ids) and not blockers
    report = _build_proof_report(
        fixture=fixture,
        proof_passed=proof_passed,
        validation_contract_version=validation_contract_version,
        execution_cost_model_version=execution_cost_model_version,
        universe_definition_id=str(fixture["required_universe_definition_id"]),
        universe_contract_version=str(fixture["required_universe_contract_version"]),
        quant_input_path=quant_input_path,
        universe_snapshot_path=universe_snapshot_path,
        derivatives_sync_summary_path=derivatives_sync_summary_path,
        spot_manifest_checks=spot_manifest_checks,
        blocker_codes=sorted(blockers),
        cycle_results=cycle_results,
        per_strategy_evidence_hashes=per_strategy_evidence_hashes,
        passing_strategy_ids=passing_strategy_ids,
        failing_strategies=failing_strategies,
        winner_strategy_id=winner_strategy_id,
        winner_experiment_id=winner_experiment_id,
    )
    write_json(proof_path, report)
    report["baseline_alpha_proof_path"] = str(proof_path)
    return report


def _resolve_spot_manifest_path(
    *,
    symbol: str,
    interval: str,
    fallback_root: Path,
    spot_root: Path | None,
) -> Path:
    if spot_root is not None:
        candidate = interval_manifest_path(
            external_root=spot_root,
            market_type="spot",
            symbol=symbol,
            interval=interval,
        )
        if candidate.exists():
            return candidate
    return interval_manifest_path(
        external_root=fallback_root,
        market_type="spot",
        symbol=symbol,
        interval=interval,
    )


def _collect_cycle_evidence(
    *,
    artifacts_root: Path,
    experiment_ids: list[str],
) -> dict[str, dict[str, Any]]:
    evidence_by_strategy: dict[str, dict[str, Any]] = {}
    for experiment_id in experiment_ids:
        experiment_root = artifacts_root / "experiments" / experiment_id
        alpha_card_path = experiment_root / "alpha_card.json"
        validation_report_path = experiment_root / "validation_report.json"
        if not alpha_card_path.exists() or not validation_report_path.exists():
            continue
        alpha_card = read_json(alpha_card_path)
        validation_report = read_json(validation_report_path)
        strategy_id = str(alpha_card.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        evidence_by_strategy[strategy_id] = {
            "experiment_id": str(alpha_card.get("experiment_id") or "").strip(),
            "strategy_id": strategy_id,
            "subject": str(alpha_card.get("subject") or "").strip(),
            "model_family": str(alpha_card.get("model_family") or "").strip(),
            "strategy_profile": str(alpha_card.get("strategy_profile") or "").strip(),
            "dataset_fingerprint": str(dict(alpha_card.get("reproducibility") or {}).get("dataset_fingerprint") or "").strip(),
            "feature_hash": str(dict(alpha_card.get("reproducibility") or {}).get("feature_hash") or "").strip(),
            "split_realization_contract": dict(alpha_card.get("split_realization_contract") or {}),
            "validation_status": str(dict(validation_report.get("validation_contract") or {}).get("status") or "").strip(),
            "validation_blocker_codes": validation_contract_blocker_codes(validation_report.get("validation_contract")),
            "falsification_status": str(alpha_card.get("falsification_status") or "").strip(),
            "falsification_blocker_codes": [
                str(item).strip()
                for item in list(alpha_card.get("falsification_blocker_codes") or [])
                if str(item).strip()
            ],
            "credible_research_evidence": bool(alpha_card.get("credible_research_evidence")),
            "validation_metrics": dict(validation_report.get("validation_metrics") or alpha_card.get("validation_metrics") or {}),
            "test_metrics": dict(validation_report.get("test_metrics") or alpha_card.get("test_metrics") or {}),
            "walk_forward_assessment": dict(
                validation_report.get("walk_forward_assessment") or alpha_card.get("walk_forward_assessment") or {}
            ),
            "execution_stress": dict(validation_report.get("execution_stress") or alpha_card.get("execution_stress") or {}),
            "regime_holdout": dict(validation_report.get("regime_holdout") or alpha_card.get("regime_holdout") or {}),
        }
        evidence_by_strategy[strategy_id]["evidence_hash"] = _stable_hash(
            _canonical_evidence_payload(evidence_by_strategy[strategy_id])
        )
    return evidence_by_strategy


def _canonical_evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment_id": str(evidence.get("experiment_id") or "").strip(),
        "strategy_id": str(evidence.get("strategy_id") or "").strip(),
        "subject": str(evidence.get("subject") or "").strip(),
        "model_family": str(evidence.get("model_family") or "").strip(),
        "strategy_profile": str(evidence.get("strategy_profile") or "").strip(),
        "dataset_fingerprint": str(evidence.get("dataset_fingerprint") or "").strip(),
        "feature_hash": str(evidence.get("feature_hash") or "").strip(),
        "split_realization_contract": dict(evidence.get("split_realization_contract") or {}),
        "validation_contract_status": str(evidence.get("validation_status") or "").strip(),
        "validation_blocker_codes": sorted(
            str(item).strip()
            for item in list(evidence.get("validation_blocker_codes") or [])
            if str(item).strip()
        ),
        "falsification_status": str(evidence.get("falsification_status") or "").strip(),
        "falsification_blocker_codes": sorted(
            str(item).strip()
            for item in list(evidence.get("falsification_blocker_codes") or [])
            if str(item).strip()
        ),
        "credible_research_evidence": bool(evidence.get("credible_research_evidence")),
        "validation_metrics": dict(evidence.get("validation_metrics") or {}),
        "test_metrics": dict(evidence.get("test_metrics") or {}),
        "walk_forward_assessment": dict(evidence.get("walk_forward_assessment") or {}),
        "execution_stress": dict(evidence.get("execution_stress") or {}),
        "regime_holdout": dict(evidence.get("regime_holdout") or {}),
    }


def _public_evidence_summary(evidence: dict[str, Any]) -> dict[str, Any] | None:
    if not evidence:
        return None
    return {
        "experiment_id": evidence.get("experiment_id"),
        "evidence_hash": evidence.get("evidence_hash"),
        "validation_status": evidence.get("validation_status"),
        "validation_blocker_codes": evidence.get("validation_blocker_codes"),
        "falsification_status": evidence.get("falsification_status"),
        "falsification_blocker_codes": evidence.get("falsification_blocker_codes"),
        "credible_research_evidence": evidence.get("credible_research_evidence"),
        "execution_stress_passed": bool(dict(evidence.get("execution_stress") or {}).get("passed")),
        "regime_holdout_passed": bool(dict(evidence.get("regime_holdout") or {}).get("passed")),
    }


def _strategy_pass_blockers(
    *,
    run_1_evidence: dict[str, Any],
    run_2_evidence: dict[str, Any],
    evidence_hash_consistent: bool,
) -> set[str]:
    blockers: set[str] = set()
    if not run_1_evidence or not run_2_evidence:
        blockers.add("missing_experiment_evidence")
        return blockers
    if not evidence_hash_consistent:
        blockers.add("evidence_hash_mismatch")
    if str(run_1_evidence.get("experiment_id") or "") != str(run_2_evidence.get("experiment_id") or ""):
        blockers.add("experiment_id_mismatch")
    for evidence in (run_1_evidence, run_2_evidence):
        if str(evidence.get("validation_status") or "") != "passed":
            blockers.update(
                set(evidence.get("validation_blocker_codes") or []) or {"validation_contract_failed"}
            )
        if not bool(evidence.get("credible_research_evidence")):
            blockers.add("credible_research_evidence_failed")
        if str(evidence.get("falsification_status") or "") not in BASELINE_ALPHA_PROOF_ALLOWED_FALSIFICATION_STATUSES:
            blockers.add("falsification_not_cleared")
        if not bool(dict(evidence.get("execution_stress") or {}).get("passed")):
            blockers.add("execution_stress_failed")
        if not bool(dict(evidence.get("regime_holdout") or {}).get("passed")):
            blockers.add("regime_holdout_failed")
    return blockers


def _build_proof_report(
    *,
    fixture: dict[str, Any],
    proof_passed: bool,
    validation_contract_version: str,
    execution_cost_model_version: str,
    universe_definition_id: str,
    universe_contract_version: str,
    quant_input_path: str | None,
    universe_snapshot_path: str | None,
    derivatives_sync_summary_path: str | None,
    spot_manifest_checks: dict[str, dict[str, str | bool | None]],
    blocker_codes: list[str],
    cycle_results: list[dict[str, Any]] | None = None,
    cycle_errors: list[str] | None = None,
    per_strategy_evidence_hashes: dict[str, Any] | None = None,
    passing_strategy_ids: list[str] | None = None,
    failing_strategies: list[dict[str, Any]] | None = None,
    winner_strategy_id: str | None = None,
    winner_experiment_id: str | None = None,
) -> dict[str, Any]:
    resolved_cycle_results = list(cycle_results or [])
    run_1 = dict(resolved_cycle_results[0]) if len(resolved_cycle_results) > 0 else {}
    run_2 = dict(resolved_cycle_results[1]) if len(resolved_cycle_results) > 1 else {}
    payload = {
        "proof_target": fixture["proof_target"],
        "as_of": fixture["as_of"],
        "fixture_contract_version": fixture["contract_version"],
        "fixture_path": portable_path(Path(fixture["path"]), repo_root=ROOT),
        "strategy_ids": list(fixture["strategy_ids"]),
        "rerun_count": int(fixture["rerun_count"]),
        "winner_selection_policy": fixture["winner_selection_policy"],
        "proof_passed": bool(proof_passed),
        "blocker_codes": sorted({str(item).strip() for item in blocker_codes if str(item).strip()}),
        "validation_contract_version": validation_contract_version,
        "execution_cost_model_version": execution_cost_model_version,
        "universe_definition_id": universe_definition_id,
        "universe_contract_version": universe_contract_version,
        "quant_input_path": quant_input_path,
        "universe_snapshot_path": universe_snapshot_path,
        "derivatives_sync_summary_path": derivatives_sync_summary_path,
        "spot_manifest_checks": spot_manifest_checks,
        "run_1_summary_hash": str(run_1.get("summary_hash") or "") or None,
        "run_2_summary_hash": str(run_2.get("summary_hash") or "") or None,
        "run_1_summary_path": str(run_1.get("summary_path") or run_1.get("quant_cycle_summary_path") or "") or None,
        "run_2_summary_path": str(run_2.get("summary_path") or run_2.get("quant_cycle_summary_path") or "") or None,
        "per_strategy_evidence_hashes": dict(per_strategy_evidence_hashes or {}),
        "passing_strategy_ids": list(passing_strategy_ids or []),
        "failing_strategies": list(failing_strategies or []),
        "winner_strategy_id": str(winner_strategy_id or "") or None,
        "winner_experiment_id": str(winner_experiment_id or "") or None,
        "cycle_errors": list(cycle_errors or []),
    }
    return with_evidence_metadata(
        payload,
        evidence_family="quant_baseline_alpha_proof",
        contract_version=BASELINE_ALPHA_PROOF_CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
