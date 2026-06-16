from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata
from scripts.market_data.binance_ohlcv import resolve_external_history_root

from .contracts import QuantUniverseInput, read_json, sha256_canonical_json, utc_now, write_json
from .deterministic_core import load_deterministic_strategy_manifest
from .experiment_status import EXPERIMENT_STATUS_QUARANTINED
from .runtime_support import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
    resolve_quant_input_path,
    run_quant_universe_freeze,
    write_quant_derivatives_sync_summary_for_as_of,
)
from .universe_input_producer import run_quant_universe_input_producer
from .validation_contract import validation_contract_blocker_codes


ROOT = Path(__file__).resolve().parents[3]
DAILY_SAMPLE_CONTRACT_VERSION = "quant_deterministic_daily_sample.v1"
BASELINE_ALPHA_SURVIVAL_CONTRACT_VERSION = "quant_baseline_alpha_survival.v1"
SURVIVAL_WINDOW_DAYS_DEFAULT = 5
SURVIVAL_OUTCOME_SURVIVED = "survived"
SURVIVAL_OUTCOME_FAILED = "failed"
SURVIVAL_OUTCOME_BLOCKED = "blocked"
SURVIVAL_OUTCOME_MISSING = "missing_sample"
BLOCKED_BEFORE_EXPERIMENTS_PREFIX = "deterministic quant core blocked before experiments:"


def run_quant_deterministic_daily_sample(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    perp_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    resolved_spot_root = _resolve_spot_root(spot_ohlcv_external_root=spot_ohlcv_external_root)
    resolved_perp_root = resolve_external_history_root(external_root=perp_ohlcv_external_root)
    cycle_root = resolved_artifacts_root / "cycles" / as_of
    cycle_root.mkdir(parents=True, exist_ok=True)
    sample_path = cycle_root / "deterministic_daily_sample.json"
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)

    strategy_manifest = load_deterministic_strategy_manifest()
    eligible_entries = _eligible_single_asset_entries(strategy_manifest=strategy_manifest)
    eligible_strategy_ids = [str(entry["strategy_id"]) for entry in eligible_entries]
    eligible_strategy_spec_hashes = {
        str(entry["strategy_id"]): str(entry["spec_hash"])
        for entry in eligible_entries
    }

    producer_summary = run_quant_universe_input_producer(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        quant_input_root=resolved_quant_input_root,
        spot_ohlcv_external_root=resolved_spot_root,
        perp_ohlcv_external_root=resolved_perp_root,
    )
    freeze_summary = run_quant_universe_freeze(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        quant_input_root=resolved_quant_input_root,
    )
    derivatives_sync_summary, derivatives_sync_summary_path = _write_derivatives_evidence_for_as_of(
        as_of=as_of,
        quant_input_root=resolved_quant_input_root,
        derivatives_external_root=derivatives_external_root,
    )

    cycle_summary: dict[str, Any] | None = None
    cycle_error_message: str | None = None
    strategy_samples: list[dict[str, Any]]
    from .lab import run_quant_research_cycle

    try:
        cycle_summary = run_quant_research_cycle(
            as_of=as_of,
            compiler_backend="deterministic",
            artifacts_root=resolved_artifacts_root,
            quant_input_root=resolved_quant_input_root,
            workbench_root=resolved_workbench_root,
            ohlcv_external_root=resolved_perp_root,
            spot_ohlcv_external_root=resolved_spot_root,
            derivatives_external_root=derivatives_external_root,
            auto_detect_spot_ohlcv_external_root=False,
            auto_api_gap_backfill=True,
        )
    except RuntimeError as exc:
        cycle_error_message = str(exc)
        if not _is_blocked_before_experiments_error(cycle_error_message):
            raise
        blocker_codes = _blocked_before_experiments_blockers(cycle_error_message)
        strategy_samples = [
            _blocked_strategy_sample(
                strategy_entry=entry,
                blocker_codes=blocker_codes,
                as_of=as_of,
                reason="cycle_blocked_before_experiments",
            )
            for entry in eligible_entries
        ]
    else:
        strategy_samples = _strategy_samples_from_cycle(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
            eligible_entries=eligible_entries,
            cycle_summary=cycle_summary,
        )

    outcome_counts = _count_strategy_outcomes(strategy_samples)
    sample_payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_deterministic_daily_sample",
        "contract_version": DAILY_SAMPLE_CONTRACT_VERSION,
        "strategy_manifest_path": str(strategy_manifest["path"]),
        "strategy_manifest_contract_version": str(strategy_manifest["contract_version"]),
        "eligible_strategy_ids": eligible_strategy_ids,
        "eligible_strategy_spec_hashes": eligible_strategy_spec_hashes,
        "quant_input_path": str(producer_summary.get("quant_input_path") or resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)),
        "quant_universe_input_producer_summary_path": str(producer_summary.get("quant_universe_input_producer_summary_path") or ""),
        "universe_snapshot_path": str(freeze_summary.get("universe_snapshot_path") or ""),
        "universe_freeze_summary_path": str(freeze_summary.get("universe_freeze_summary_path") or ""),
        "derivatives_sync_summary_path": str(derivatives_sync_summary_path),
        "derivatives_sync_status": str(derivatives_sync_summary.get("status") or ""),
        "cycle_summary_path": None if cycle_summary is None else str(cycle_summary.get("summary_path") or cycle_summary.get("quant_cycle_summary_path") or ""),
        "cycle_status": "blocked_before_experiments" if cycle_summary is None else str(cycle_summary.get("status") or ""),
        "cycle_error_message": cycle_error_message,
        "spot_history_root": str(resolved_spot_root),
        "perp_history_root": str(resolved_perp_root),
        "strategy_outcome_counts": outcome_counts,
        "strategy_samples": strategy_samples,
    }
    sample_payload["sample_hash"] = _stable_payload_hash(sample_payload)
    sample = with_evidence_metadata(
        sample_payload,
        evidence_family="quant_deterministic_daily_sample",
        contract_version=DAILY_SAMPLE_CONTRACT_VERSION,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    write_json(sample_path, sample)
    sample["deterministic_daily_sample_path"] = str(sample_path)
    return sample


def run_baseline_alpha_survival(
    *,
    date_from: str,
    date_to: str,
    survival_window_days: int = SURVIVAL_WINDOW_DAYS_DEFAULT,
    artifacts_root: Path | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    if survival_window_days <= 0:
        raise ValueError("survival_window_days must be positive")
    start_date = date.fromisoformat(date_from)
    end_date = date.fromisoformat(date_to)
    if end_date < start_date:
        raise ValueError("date_to must be on or after date_from")

    strategy_manifest = load_deterministic_strategy_manifest()
    eligible_entries = _eligible_single_asset_entries(strategy_manifest=strategy_manifest)
    eligible_strategy_ids = [str(entry["strategy_id"]) for entry in eligible_entries]
    eligible_strategy_spec_hashes = {
        str(entry["strategy_id"]): str(entry["spec_hash"])
        for entry in eligible_entries
    }

    daily_samples_by_date: dict[str, dict[str, Any] | None] = {}
    for current in _date_range(start_date, end_date):
        as_of = current.isoformat()
        daily_samples_by_date[as_of] = _load_daily_sample_if_valid(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
        )

    per_strategy: dict[str, Any] = {}
    alpha_like_strategy_ids: list[str] = []
    for entry in eligible_entries:
        strategy_id = str(entry["strategy_id"])
        expected_spec_hash = eligible_strategy_spec_hashes[strategy_id]
        daily_outcomes: list[dict[str, Any]] = []
        breaker_dates: list[str] = []
        current_streak = 0
        max_streak = 0
        previous_date: date | None = None

        for current in _date_range(start_date, end_date):
            as_of = current.isoformat()
            sample = daily_samples_by_date.get(as_of)
            outcome_payload = _daily_outcome_from_sample(
                strategy_id=strategy_id,
                as_of=as_of,
                sample=sample,
                expected_spec_hash=expected_spec_hash,
            )
            daily_outcomes.append(outcome_payload)
            outcome = str(outcome_payload["outcome"])
            if outcome == SURVIVAL_OUTCOME_SURVIVED:
                if previous_date is not None and current == previous_date + timedelta(days=1) and current_streak > 0:
                    current_streak += 1
                else:
                    current_streak = 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 0
                breaker_dates.append(as_of)
            previous_date = current

        if current_streak >= survival_window_days:
            alpha_like_strategy_ids.append(strategy_id)
        per_strategy[strategy_id] = {
            "strategy_id": strategy_id,
            "subject": str(entry.get("subject") or "").strip().upper(),
            "spec_hash": expected_spec_hash,
            "current_consecutive_survival_streak": current_streak,
            "max_consecutive_survival_streak": max_streak,
            "daily_outcomes": daily_outcomes,
            "breaker_dates": breaker_dates,
        }

    report_payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "date_from": date_from,
        "date_to": date_to,
        "artifact_family": "quant_baseline_alpha_survival",
        "contract_version": BASELINE_ALPHA_SURVIVAL_CONTRACT_VERSION,
        "survival_window_days": int(survival_window_days),
        "strategy_manifest_path": str(strategy_manifest["path"]),
        "strategy_manifest_contract_version": str(strategy_manifest["contract_version"]),
        "eligible_strategy_ids": eligible_strategy_ids,
        "eligible_strategy_spec_hashes": eligible_strategy_spec_hashes,
        "alpha_like_strategy_ids": alpha_like_strategy_ids,
        "started_looking_like_alpha": bool(alpha_like_strategy_ids),
        "per_strategy": per_strategy,
    }
    report_payload["survival_hash"] = _stable_payload_hash(report_payload)
    report = with_evidence_metadata(
        report_payload,
        evidence_family="quant_baseline_alpha_survival",
        contract_version=BASELINE_ALPHA_SURVIVAL_CONTRACT_VERSION,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    output_path = resolved_artifacts_root / "cycles" / date_to / "baseline_alpha_survival.json"
    write_json(output_path, report)
    report["baseline_alpha_survival_path"] = str(output_path)
    return report


def _resolve_spot_root(*, spot_ohlcv_external_root: Path | None) -> Path:
    from .data_readiness import resolve_default_spot_ohlcv_external_root

    resolved = resolve_default_spot_ohlcv_external_root(
        spot_ohlcv_external_root=spot_ohlcv_external_root,
    )
    if resolved is None:
        raise FileNotFoundError(
            "CoinAPI spot OHLCV root not found; provide spot_ohlcv_external_root explicitly"
        )
    return resolved.expanduser().resolve()


def _eligible_single_asset_entries(*, strategy_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(entry)
        for entry in list(strategy_manifest.get("entries") or [])
        if isinstance(entry, dict)
        and bool(entry.get("enabled"))
        and str(entry.get("shape") or "").strip() == "single_asset"
    ]


def _write_derivatives_evidence_for_as_of(
    *,
    as_of: str,
    quant_input_root: Path,
    derivatives_external_root: Path | None,
) -> tuple[dict[str, Any], Path]:
    universe_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=quant_input_root)
    universe_input = QuantUniverseInput.from_payload(read_json(universe_input_path))
    symbols = sorted(
        {
            str(candidate.usdm_symbol)
            for candidate in universe_input.selected_candidates()
            if candidate.usdm_symbol
        }
    )
    if not symbols:
        raise RuntimeError(f"no usdm symbols resolved for deterministic daily sample as_of={as_of}")
    return write_quant_derivatives_sync_summary_for_as_of(
        as_of=as_of,
        symbols=symbols,
        intervals=("4h", "1d"),
        derivatives_external_root=derivatives_external_root,
    )


def _is_blocked_before_experiments_error(message: str | None) -> bool:
    return str(message or "").strip().startswith(BLOCKED_BEFORE_EXPERIMENTS_PREFIX)


def _blocked_before_experiments_blockers(message: str | None) -> list[str]:
    normalized = str(message or "").strip()
    if not _is_blocked_before_experiments_error(normalized):
        return []
    payload = normalized[len(BLOCKED_BEFORE_EXPERIMENTS_PREFIX):].strip()
    return [item.strip() for item in payload.split(",") if item.strip()]


def _strategy_samples_from_cycle(
    *,
    as_of: str,
    artifacts_root: Path,
    eligible_entries: list[dict[str, Any]],
    cycle_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    experiment_ids = [
        str(item).strip()
        for item in list(cycle_summary.get("experiment_ids") or [])
        if str(item).strip()
    ]
    experiments_by_strategy_id = {
        strategy_id: payload
        for strategy_id, payload in (
            _load_experiment_payload(experiment_id=experiment_id, artifacts_root=artifacts_root)
            for experiment_id in experiment_ids
        )
        if strategy_id
    }
    blocked_strategy_ids = {
        str(item).strip()
        for item in list(cycle_summary.get("blocked_strategy_ids") or [])
        if str(item).strip()
    }
    cycle_blockers = [
        str(item).strip()
        for item in list(cycle_summary.get("data_gap_blockers") or [])
        if str(item).strip()
    ]
    samples: list[dict[str, Any]] = []
    for entry in eligible_entries:
        strategy_id = str(entry["strategy_id"])
        experiment = experiments_by_strategy_id.get(strategy_id)
        if experiment is None:
            if strategy_id in blocked_strategy_ids:
                samples.append(
                    _blocked_strategy_sample(
                        strategy_entry=entry,
                        blocker_codes=cycle_blockers,
                        as_of=as_of,
                        reason="cycle_selection_blocked",
                    )
                )
                continue
            samples.append(
                _missing_strategy_sample(
                    strategy_entry=entry,
                    as_of=as_of,
                    reason="missing_experiment_evidence",
                )
            )
            continue
        samples.append(
            _strategy_sample_from_experiment(
                strategy_entry=entry,
                experiment=experiment,
                cycle_blocked=strategy_id in blocked_strategy_ids,
            )
        )
    return samples


def _load_experiment_payload(
    *,
    experiment_id: str,
    artifacts_root: Path,
) -> tuple[str | None, dict[str, Any]]:
    resolved_paths = resolve_experiment_artifact_paths(
        experiment_id=experiment_id,
        artifacts_root=artifacts_root,
    )
    if resolved_paths is None:
        return None, {}
    experiment_root, alpha_card_path, validation_report_path = resolved_paths
    alpha_card = dict(read_json(alpha_card_path))
    validation_report = dict(read_json(validation_report_path))
    strategy_id = str(alpha_card.get("strategy_id") or validation_report.get("strategy_id") or "").strip()
    return strategy_id or None, {
        "experiment_id": experiment_id,
        "alpha_card": alpha_card,
        "validation_report": validation_report,
        "experiment_root": str(experiment_root),
        "alpha_card_path": str(alpha_card_path),
        "validation_report_path": str(validation_report_path),
    }


def resolve_experiment_artifact_paths(
    *,
    experiment_id: str,
    artifacts_root: Path,
) -> tuple[Path, Path, Path] | None:
    experiments_root = artifacts_root / "experiments"
    if not experiments_root.exists():
        return None
    candidate_roots = [
        experiments_root / str(experiment_id).strip(),
        experiments_root / _experiment_directory_name(experiment_id),
    ]
    seen_roots: set[Path] = set()
    for experiment_root in candidate_roots:
        resolved_root = experiment_root.resolve()
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        resolved_paths = _validate_experiment_root(experiment_root=experiment_root)
        if resolved_paths is not None:
            return resolved_paths

    for experiment_root in experiments_root.iterdir():
        if not experiment_root.is_dir():
            continue
        resolved_paths = _validate_experiment_root(experiment_root=experiment_root)
        if resolved_paths is None:
            continue
        _, alpha_card_path, validation_report_path = resolved_paths
        try:
            alpha_card = dict(read_json(alpha_card_path))
        except Exception:
            continue
        candidate_experiment_id = str(alpha_card.get("experiment_id") or "").strip()
        if candidate_experiment_id == str(experiment_id).strip():
            return resolved_paths
        candidate_strategy_id = str(alpha_card.get("strategy_id") or "").strip()
        if not candidate_strategy_id:
            try:
                validation_report = dict(read_json(validation_report_path))
            except Exception:
                continue
            candidate_strategy_id = str(validation_report.get("strategy_id") or "").strip()
        as_of, strategy_id = _split_experiment_identity(experiment_id)
        candidate_as_of, _ = _split_experiment_identity(candidate_experiment_id)
        if as_of and strategy_id and candidate_as_of == as_of and candidate_strategy_id == strategy_id:
            return resolved_paths
    return None


def _validate_experiment_root(*, experiment_root: Path) -> tuple[Path, Path, Path] | None:
    alpha_card_path = experiment_root / "alpha_card.json"
    validation_report_path = experiment_root / "validation_report.json"
    if not alpha_card_path.exists() or not validation_report_path.exists():
        return None
    return experiment_root, alpha_card_path, validation_report_path


def _split_experiment_identity(experiment_id: str) -> tuple[str, str]:
    normalized = str(experiment_id).strip()
    if len(normalized) <= 11 or normalized[10] != "-":
        return "", ""
    return normalized[:10], normalized[11:]


def _experiment_directory_name(experiment_id: str) -> str:
    normalized = str(experiment_id).strip()
    if len(normalized) <= 64:
        return normalized
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    prefix = normalized[:40].rstrip("-")
    return f"{prefix}-{digest}"


def _strategy_sample_from_experiment(
    *,
    strategy_entry: dict[str, Any],
    experiment: dict[str, Any],
    cycle_blocked: bool,
) -> dict[str, Any]:
    alpha_card = dict(experiment.get("alpha_card") or {})
    validation_report = dict(experiment.get("validation_report") or {})
    validation_contract = dict(
        validation_report.get("validation_contract")
        or alpha_card.get("validation_contract")
        or {}
    )
    execution_stress = dict(validation_report.get("execution_stress") or alpha_card.get("execution_stress") or {})
    regime_holdout = dict(validation_report.get("regime_holdout") or alpha_card.get("regime_holdout") or {})
    data_gap_blockers = _ordered_unique_strings(
        list(alpha_card.get("data_gap_blockers") or [])
        + list(validation_report.get("data_gap_blockers") or [])
    )
    validation_blockers = _ordered_unique_strings(
        list(validation_contract_blocker_codes(validation_contract))
        + list(validation_report.get("validation_blocker_codes") or [])
        + list(alpha_card.get("validation_blocker_codes") or [])
    )
    falsification_blockers = _ordered_unique_strings(
        list(alpha_card.get("falsification_blocker_codes") or [])
        + list(validation_report.get("falsification_blocker_codes") or [])
    )
    blocker_codes = _ordered_unique_strings(data_gap_blockers + validation_blockers + falsification_blockers)
    validation_status = str(validation_contract.get("status") or "").strip()
    falsification_status = str(
        alpha_card.get("falsification_status")
        or validation_report.get("falsification_status")
        or "not_required"
    ).strip()
    credible_research_evidence = bool(
        alpha_card.get("credible_research_evidence", validation_report.get("credible_research_evidence", False))
    )
    execution_stress_passed = bool(execution_stress.get("passed"))
    regime_holdout_passed = bool(regime_holdout.get("passed"))
    survived = (
        validation_status == "passed"
        and credible_research_evidence
        and falsification_status in {"cleared", "not_required"}
        and execution_stress_passed
        and regime_holdout_passed
    )
    if survived:
        outcome = SURVIVAL_OUTCOME_SURVIVED
        reason = "all_survival_gates_passed"
    elif data_gap_blockers or validation_status == "incomplete" or cycle_blocked:
        outcome = SURVIVAL_OUTCOME_BLOCKED
        reason = "data_gap_or_readiness_blocked"
    else:
        outcome = SURVIVAL_OUTCOME_FAILED
        reason = "research_validation_failed"
    return {
        "strategy_id": str(strategy_entry["strategy_id"]),
        "subject": str(strategy_entry.get("subject") or "").strip().upper(),
        "spec_hash": str(strategy_entry.get("spec_hash") or "").strip(),
        "outcome": outcome,
        "reason": reason,
        "experiment_id": str(experiment.get("experiment_id") or ""),
        "experiment_status": str(alpha_card.get("experiment_status") or "").strip(),
        "validation": str(alpha_card.get("validation") or validation_report.get("validation") or "").strip(),
        "publication_status": str(alpha_card.get("publication_status") or "").strip(),
        "validation_contract_status": validation_status,
        "validation_blocker_codes": validation_blockers,
        "falsification_status": falsification_status,
        "falsification_blocker_codes": falsification_blockers,
        "credible_research_evidence": credible_research_evidence,
        "execution_stress_passed": execution_stress_passed,
        "regime_holdout_passed": regime_holdout_passed,
        "blocker_codes": blocker_codes,
        "data_gap_blockers": data_gap_blockers,
    }


def _blocked_strategy_sample(
    *,
    strategy_entry: dict[str, Any],
    blocker_codes: list[str],
    as_of: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "strategy_id": str(strategy_entry["strategy_id"]),
        "subject": str(strategy_entry.get("subject") or "").strip().upper(),
        "spec_hash": str(strategy_entry.get("spec_hash") or "").strip(),
        "outcome": SURVIVAL_OUTCOME_BLOCKED,
        "reason": reason,
        "as_of": as_of,
        "experiment_id": None,
        "experiment_status": None,
        "validation": None,
        "publication_status": None,
        "validation_contract_status": None,
        "validation_blocker_codes": list(blocker_codes),
        "falsification_status": None,
        "falsification_blocker_codes": [],
        "credible_research_evidence": False,
        "execution_stress_passed": False,
        "regime_holdout_passed": False,
        "blocker_codes": list(blocker_codes),
        "data_gap_blockers": list(blocker_codes),
    }


def _missing_strategy_sample(
    *,
    strategy_entry: dict[str, Any],
    as_of: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "strategy_id": str(strategy_entry["strategy_id"]),
        "subject": str(strategy_entry.get("subject") or "").strip().upper(),
        "spec_hash": str(strategy_entry.get("spec_hash") or "").strip(),
        "outcome": SURVIVAL_OUTCOME_MISSING,
        "reason": reason,
        "as_of": as_of,
        "experiment_id": None,
        "experiment_status": None,
        "validation": None,
        "publication_status": None,
        "validation_contract_status": None,
        "validation_blocker_codes": [],
        "falsification_status": None,
        "falsification_blocker_codes": [],
        "credible_research_evidence": False,
        "execution_stress_passed": False,
        "regime_holdout_passed": False,
        "blocker_codes": [],
        "data_gap_blockers": [],
    }


def _count_strategy_outcomes(strategy_samples: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {
        SURVIVAL_OUTCOME_SURVIVED: 0,
        SURVIVAL_OUTCOME_FAILED: 0,
        SURVIVAL_OUTCOME_BLOCKED: 0,
        SURVIVAL_OUTCOME_MISSING: 0,
    }
    for sample in strategy_samples:
        outcome = str(sample.get("outcome") or "").strip()
        if outcome not in counts:
            counts[outcome] = 0
        counts[outcome] += 1
    return counts


def _load_daily_sample_if_valid(*, as_of: str, artifacts_root: Path) -> dict[str, Any] | None:
    path = artifacts_root / "cycles" / as_of / "deterministic_daily_sample.json"
    if not path.exists():
        return None
    try:
        payload = dict(read_json(path))
    except Exception:
        return None
    if str(payload.get("contract_version") or "").strip() != DAILY_SAMPLE_CONTRACT_VERSION:
        return None
    payload["path"] = str(path)
    return payload


def _daily_outcome_from_sample(
    *,
    strategy_id: str,
    as_of: str,
    sample: dict[str, Any] | None,
    expected_spec_hash: str,
) -> dict[str, Any]:
    if sample is None:
        return {
            "as_of": as_of,
            "outcome": SURVIVAL_OUTCOME_MISSING,
            "reason": "missing_daily_sample_artifact",
            "blocker_codes": [],
            "experiment_id": None,
        }
    sample_by_strategy = {
        str(item.get("strategy_id") or "").strip(): dict(item)
        for item in list(sample.get("strategy_samples") or [])
        if isinstance(item, dict) and str(item.get("strategy_id") or "").strip()
    }
    strategy_sample = sample_by_strategy.get(strategy_id)
    if strategy_sample is None:
        return {
            "as_of": as_of,
            "outcome": SURVIVAL_OUTCOME_MISSING,
            "reason": "strategy_missing_from_daily_sample",
            "blocker_codes": [],
            "experiment_id": None,
        }
    if str(strategy_sample.get("spec_hash") or "").strip() != expected_spec_hash:
        return {
            "as_of": as_of,
            "outcome": SURVIVAL_OUTCOME_MISSING,
            "reason": "strategy_spec_hash_mismatch",
            "blocker_codes": list(strategy_sample.get("blocker_codes") or []),
            "experiment_id": strategy_sample.get("experiment_id"),
        }
    return {
        "as_of": as_of,
        "outcome": str(strategy_sample.get("outcome") or SURVIVAL_OUTCOME_MISSING),
        "reason": str(strategy_sample.get("reason") or "").strip(),
        "blocker_codes": _ordered_unique_strings(list(strategy_sample.get("blocker_codes") or [])),
        "experiment_id": strategy_sample.get("experiment_id"),
        "validation_contract_status": strategy_sample.get("validation_contract_status"),
        "credible_research_evidence": bool(strategy_sample.get("credible_research_evidence")),
        "falsification_status": strategy_sample.get("falsification_status"),
        "execution_stress_passed": bool(strategy_sample.get("execution_stress_passed")),
        "regime_holdout_passed": bool(strategy_sample.get("regime_holdout_passed")),
    }


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "produced_at_utc"}
    }
    return sha256_canonical_json(canonical)


def _ordered_unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)
