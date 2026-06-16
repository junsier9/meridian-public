from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .coinapi_spot_sync import run_quant_coinapi_spot_sync
from .contracts import QuantUniverseCandidate, portable_path, utc_now, write_json
from .data_readiness import (
    CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
    CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
    CROSS_SECTIONAL_SPOT_BLOCKER,
    DISCOVERY_DERIVATIVES_BLOCKER,
    SINGLE_ASSET_SPOT_BLOCKER,
)
from .runtime_support import run_quant_derivatives_sync_cycle, write_quant_derivatives_sync_summary_for_as_of


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_FAMILY = "quant_gap_remediation"
CONTRACT_VERSION = "quant_gap_remediation.v1"
EXECUTION_GAP_PATTERN = re.compile(r"^(?P<subject>[^:]+):\s*missing\s+(?P<detail>.+)$", re.IGNORECASE)
MAX_GAP_REMEDIATION_ATTEMPTS = 1


def build_gap_remediation_plan(
    *,
    as_of: str,
    experiments: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> dict[str, Any]:
    strategy_by_id = {
        str(entry.get("strategy_id") or "").strip(): dict(entry)
        for entry in strategies
        if str(entry.get("strategy_id") or "").strip()
    }
    candidate_by_subject = {
        str(candidate.subject).strip().upper(): candidate
        for candidate in universe_candidates
    }
    all_spot_symbols = sorted(
        {
            str(candidate.spot_symbol).strip().upper()
            for candidate in universe_candidates
            if str(candidate.spot_symbol).strip()
        }
    )
    all_perp_symbols = sorted(
        {
            str(candidate.usdm_symbol).strip().upper()
            for candidate in universe_candidates
            if str(candidate.usdm_symbol).strip()
        }
    )
    affected_strategy_ids: set[str] = set()
    spot_subjects: set[str] = set()
    perp_subjects: set[str] = set()
    resolvable_blockers: list[dict[str, Any]] = []
    ignored_blockers: list[dict[str, Any]] = []

    for experiment in experiments:
        strategy_id = str(experiment.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        strategy_entry = strategy_by_id.get(strategy_id, {})
        strategy_candidates = _strategy_candidates(
            strategy_entry=strategy_entry,
            universe_candidates=universe_candidates,
            candidate_by_subject=candidate_by_subject,
            experiment=experiment,
        )
        blockers = _collect_gap_blockers(experiment)
        if not blockers:
            continue
        for blocker in blockers:
            remediation = _classify_blocker(
                blocker=blocker,
                strategy_id=strategy_id,
                strategy_entry=strategy_entry,
                strategy_candidates=strategy_candidates,
                candidate_by_subject=candidate_by_subject,
            )
            if remediation is None:
                ignored_blockers.append(
                    {
                        "strategy_id": strategy_id,
                        "blocker": blocker,
                    }
                )
                continue
            affected_strategy_ids.add(strategy_id)
            spot_subjects.update(remediation["spot_subjects"])
            perp_subjects.update(remediation["perp_subjects"])
            resolvable_blockers.append(
                {
                    "strategy_id": strategy_id,
                    "blocker": blocker,
                    "spot_subjects": sorted(remediation["spot_subjects"]),
                    "perp_subjects": sorted(remediation["perp_subjects"]),
                }
            )

    spot_symbols = sorted(
        {
            str(candidate_by_subject[subject].spot_symbol).strip().upper()
            for subject in spot_subjects
            if subject in candidate_by_subject and str(candidate_by_subject[subject].spot_symbol).strip()
        }
    )
    perp_symbols = sorted(
        {
            str(candidate_by_subject[subject].usdm_symbol).strip().upper()
            for subject in perp_subjects
            if subject in candidate_by_subject and str(candidate_by_subject[subject].usdm_symbol).strip()
        }
    )

    return {
        "as_of": as_of,
        "contract_version": CONTRACT_VERSION,
        "attempt_count_max": MAX_GAP_REMEDIATION_ATTEMPTS,
        "attempted": False,
        "should_attempt": bool(affected_strategy_ids and (spot_symbols or perp_symbols)),
        "affected_strategy_ids": sorted(affected_strategy_ids),
        "spot_subjects": sorted(spot_subjects),
        "perp_subjects": sorted(perp_subjects),
        "spot_symbols": spot_symbols,
        "perp_symbols": perp_symbols,
        "universe_spot_symbols": all_spot_symbols,
        "universe_perp_symbols": all_perp_symbols,
        "resolvable_blockers": resolvable_blockers,
        "ignored_blockers": ignored_blockers,
    }


def execute_gap_remediation_backfill(
    *,
    as_of: str,
    plan: dict[str, Any],
    quant_input_root: Path,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
) -> dict[str, Any]:
    spot_symbols = [str(item).strip().upper() for item in list(plan.get("spot_symbols") or []) if str(item).strip()]
    perp_symbols = [str(item).strip().upper() for item in list(plan.get("perp_symbols") or []) if str(item).strip()]
    universe_perp_symbols = [
        str(item).strip().upper()
        for item in list(plan.get("universe_perp_symbols") or [])
        if str(item).strip()
    ]
    summary: dict[str, Any] = {
        "attempted": bool(plan.get("should_attempt")),
        "rerun_strategy_ids": list(plan.get("affected_strategy_ids") or []),
        "spot_backfill": {
            "attempted": bool(spot_symbols),
            "spot_symbols": spot_symbols,
            "status": "skipped" if not spot_symbols else "pending",
        },
        "derivatives_backfill": {
            "attempted": bool(perp_symbols),
            "symbols": perp_symbols,
            "status": "skipped" if not perp_symbols else "pending",
            "rebuilt_archive_summary_path": None,
        },
    }
    if not summary["attempted"]:
        return summary

    if spot_symbols:
        try:
            spot_summary = run_quant_coinapi_spot_sync(
                as_of=as_of,
                mode="bootstrap",
                quant_input_root=quant_input_root,
                external_root=spot_ohlcv_external_root,
                spot_symbols=spot_symbols,
            )
            summary["spot_backfill"]["status"] = str(spot_summary.get("status") or "success")
            summary["spot_backfill"]["summary"] = spot_summary
        except Exception as exc:
            summary["spot_backfill"]["status"] = "error"
            summary["spot_backfill"]["error"] = str(exc)

    if perp_symbols:
        try:
            derivatives_summary = run_quant_derivatives_sync_cycle(
                as_of=as_of,
                quant_input_root=quant_input_root,
                derivatives_external_root=derivatives_external_root,
                mode="bootstrap",
                intervals=("4h", "1d"),
                symbols=perp_symbols,
            )
            summary["derivatives_backfill"]["status"] = str(derivatives_summary.get("status") or "success")
            summary["derivatives_backfill"]["summary"] = derivatives_summary
            if universe_perp_symbols:
                _, rebuilt_archive_path = write_quant_derivatives_sync_summary_for_as_of(
                    as_of=as_of,
                    symbols=universe_perp_symbols,
                    intervals=("4h", "1d"),
                    derivatives_external_root=derivatives_external_root,
                )
                summary["derivatives_backfill"]["rebuilt_archive_summary_path"] = portable_path(
                    Path(str(rebuilt_archive_path)),
                    repo_root=ROOT,
                )
        except Exception as exc:
            summary["derivatives_backfill"]["status"] = "error"
            summary["derivatives_backfill"]["error"] = str(exc)

    return summary


def write_gap_remediation_summary(
    *,
    path: Path,
    as_of: str,
    plan: dict[str, Any],
    execution: dict[str, Any],
    rerun: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "plan": plan,
            "execution": execution,
            "rerun": rerun,
            "attempted": bool(plan.get("should_attempt")),
            "status": _remediation_status(execution=execution, rerun=rerun),
        },
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    write_json(path, payload)
    payload["path"] = portable_path(path, repo_root=ROOT)
    return payload


def _remediation_status(*, execution: dict[str, Any], rerun: dict[str, Any]) -> str:
    if not execution.get("attempted"):
        return "skipped"
    if rerun.get("error"):
        return "error"
    if rerun.get("attempted"):
        return "success"
    if execution_failed(execution):
        return "partial"
    return "no_rerun"


def execution_failed(execution: dict[str, Any]) -> bool:
    for lane in ("spot_backfill", "derivatives_backfill"):
        lane_payload = dict(execution.get(lane) or {})
        if lane_payload.get("attempted") and str(lane_payload.get("status") or "").strip().lower() == "error":
            return True
    return False


def _collect_gap_blockers(experiment: dict[str, Any]) -> list[str]:
    blockers = {
        str(item).strip()
        for item in list(experiment.get("data_gap_blockers") or [])
        if str(item).strip()
    }
    validation_codes = {
        str(item).strip()
        for item in list(experiment.get("validation_blocker_codes") or [])
        if str(item).strip()
    }
    for code in (
        CROSS_SECTIONAL_SPOT_BLOCKER,
        CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
        CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
        SINGLE_ASSET_SPOT_BLOCKER,
        DISCOVERY_DERIVATIVES_BLOCKER,
    ):
        if code in validation_codes:
            blockers.add(code)
    return sorted(blockers)


def _classify_blocker(
    *,
    blocker: str,
    strategy_id: str,
    strategy_entry: dict[str, Any],
    strategy_candidates: list[QuantUniverseCandidate],
    candidate_by_subject: dict[str, QuantUniverseCandidate],
) -> dict[str, set[str]] | None:
    if blocker in {
        CROSS_SECTIONAL_SPOT_BLOCKER,
        CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
        CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
        SINGLE_ASSET_SPOT_BLOCKER,
    }:
        return {
            "spot_subjects": {candidate.subject for candidate in strategy_candidates if candidate.spot_symbol},
            "perp_subjects": set(),
        }
    if blocker == DISCOVERY_DERIVATIVES_BLOCKER:
        return {
            "spot_subjects": set(),
            "perp_subjects": {candidate.subject for candidate in strategy_candidates if candidate.usdm_symbol},
        }
    match = EXECUTION_GAP_PATTERN.match(blocker)
    if not match:
        return None
    subject = str(match.group("subject") or "").strip().upper()
    detail = str(match.group("detail") or "").strip().lower()
    candidate = candidate_by_subject.get(subject)
    if candidate is None:
        return None
    if any(token in detail for token in ("trade liquidity proxy", "open_interest_value", "perp_close")):
        if not candidate.usdm_symbol:
            return None
        return {
            "spot_subjects": set(),
            "perp_subjects": {candidate.subject},
        }
    if "spot" in detail:
        return {
            "spot_subjects": {candidate.subject},
            "perp_subjects": set(),
        }
    return None


def _strategy_candidates(
    *,
    strategy_entry: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    candidate_by_subject: dict[str, QuantUniverseCandidate],
    experiment: dict[str, Any],
) -> list[QuantUniverseCandidate]:
    shape = str(strategy_entry.get("shape") or experiment.get("shape") or "").strip()
    subject = str(strategy_entry.get("subject") or experiment.get("subject") or "").strip().upper()
    if shape == "single_asset" and subject:
        candidate = candidate_by_subject.get(subject)
        return [candidate] if candidate is not None else []
    filtered = list(universe_candidates)
    universe_filter = dict(strategy_entry.get("universe_filter") or experiment.get("universe_filter") or {})
    asset_buckets = {
        str(item).strip()
        for item in list(universe_filter.get("liquidity_buckets") or [])
        if str(item).strip()
    }
    if asset_buckets:
        filtered = [candidate for candidate in filtered if str(candidate.liquidity_bucket or "").strip() in asset_buckets]
    subjects = {
        str(item).strip().upper()
        for item in list(universe_filter.get("subjects") or [])
        if str(item).strip()
    }
    if subjects:
        filtered = [candidate for candidate in filtered if candidate.subject in subjects]
    return filtered
