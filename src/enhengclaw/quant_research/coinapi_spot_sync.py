from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .contracts import QuantUniverseCandidate, QuantUniverseInput, read_json, utc_now
from .runtime_support import QUANT_INPUT_ROOT, resolve_quant_input_path
from scripts.market_data.coinapi_ohlcv import (
    DEFAULT_EXCHANGE_ID,
    DEFAULT_QUOTE_ASSET,
    resolve_external_history_root,
    sync_coinapi_ohlcv,
)


ARTIFACT_FAMILY = "quant_coinapi_spot_sync"
CONTRACT_VERSION = "quant_coinapi_spot_sync.v1"
TOP_100_INTERVALS = ("1d", "4h")
TOP_30_INTERVALS = ("1h",)
TOP_30_1H_LIMIT = 30
PHASE_LOOKBACK_DAYS = {
    "spot_1d": 730,
    "spot_4h": 730,
    "spot_1h": 180,
}
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class QuantSpotSyncPlan:
    phase: str
    intervals: tuple[str, ...]
    candidates: tuple[QuantUniverseCandidate, ...]
    max_lookback_days: int | None


def run_quant_coinapi_spot_sync(
    *,
    as_of: str,
    mode: str,
    quant_input_root: Path | None = None,
    external_root: Path | None = None,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    quote_asset: str = DEFAULT_QUOTE_ASSET,
    refresh_catalog: bool = False,
    spot_symbols: tuple[str, ...] | list[str] | None = None,
    required_intervals: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    if mode not in {"refresh", "bootstrap"}:
        raise ValueError("mode must be one of: refresh, bootstrap")
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_external_root = resolve_external_history_root(external_root=external_root)
    quant_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)
    quant_input = QuantUniverseInput.from_payload(read_json(quant_input_path))
    candidates = quant_input.selected_candidates()
    if spot_symbols is not None:
        requested_symbols = {
            str(item).strip().upper()
            for item in spot_symbols
            if str(item).strip()
        }
        candidates = tuple(candidate for candidate in candidates if candidate.spot_symbol in requested_symbols)
        if not candidates:
            raise ValueError("no CoinAPI spot sync candidates matched requested spot symbols")
    explicit_intervals = tuple(
        str(item).strip()
        for item in list(required_intervals or [])
        if str(item).strip()
    )
    if explicit_intervals:
        invalid_intervals = sorted(
            set(explicit_intervals) - set(TOP_100_INTERVALS) - set(TOP_30_INTERVALS)
        )
        if invalid_intervals:
            raise ValueError(f"unsupported CoinAPI spot sync intervals: {invalid_intervals}")
    refresh_catalog_next = refresh_catalog
    phase_summaries: list[dict[str, Any]] = []
    phase_failures: list[dict[str, Any]] = []
    successful_sync_count_total = 0
    for plan in _build_sync_plans(mode=mode, candidates=candidates, explicit_intervals=explicit_intervals):
        if mode == "refresh":
            phase_summary, refresh_catalog_next, refresh_failures, successful_sync_count = _run_refresh_phase(
                plan=plan,
                external_root=resolved_external_root,
                exchange_id=exchange_id,
                quote_asset=quote_asset,
                refresh_catalog=refresh_catalog_next,
            )
            phase_summaries.append(phase_summary)
            phase_failures.extend(refresh_failures)
            successful_sync_count_total += successful_sync_count
            continue

        phase_results: list[dict[str, Any]] = []
        phase_errors: list[dict[str, Any]] = []
        phase_end = _phase_end_iso(as_of=as_of)
        for candidate in plan.candidates:
            effective_days = min(int(candidate.listing_age_days), int(plan.max_lookback_days or 0))
            try:
                phase_results.append(
                    sync_coinapi_ohlcv(
                        external_root=resolved_external_root,
                        symbols=(candidate.spot_symbol,),
                        intervals=plan.intervals,
                        mode=mode,
                        exchange_id=exchange_id,
                        quote_asset=quote_asset,
                        time_start=_phase_start_iso(as_of=as_of, lookback_days=effective_days),
                        time_end=phase_end,
                        refresh_catalog=refresh_catalog_next,
                    )
                )
                successful_sync_count_total += 1
            except Exception as exc:
                phase_errors.append(
                    _build_phase_failure(
                        phase=plan.phase,
                        candidate=candidate,
                        intervals=plan.intervals,
                        error=exc,
                    )
                )
            finally:
                refresh_catalog_next = False
        phase_summary = {
            "phase": plan.phase,
            "intervals": list(plan.intervals),
            "candidate_count": len(plan.candidates),
            "max_lookback_days": plan.max_lookback_days,
            "successful_sync_count": len(phase_results),
            "failure_count": len(phase_errors),
            "summaries": phase_results,
        }
        if phase_errors:
            phase_summary["failures"] = phase_errors
            phase_failures.extend(phase_errors)
        phase_summaries.append(phase_summary)

    if phase_failures and successful_sync_count_total == 0:
        first_failure = phase_failures[0]
        raise RuntimeError(
            "Quant CoinAPI spot sync failed for all attempted candidates; "
            f"first failure in phase {first_failure['phase']} for "
            f"{first_failure.get('symbol') or '<unknown>'}: {first_failure['error']}"
        )

    top100_symbols = [candidate.spot_symbol for candidate in candidates]
    top30_symbols = [candidate.spot_symbol for candidate in candidates[:TOP_30_1H_LIMIT]]
    summary = with_evidence_metadata(
        {
            "status": "partial_success" if phase_failures else "success",
            "success": True,
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "mode": mode,
            "quant_input_path": str(quant_input_path),
            "quant_input_as_of": quant_input.as_of,
            "external_root": str(resolved_external_root),
            "exchange_id": exchange_id,
            "quote_asset": quote_asset,
            "top100_symbol_count": len(top100_symbols),
            "top30_intraday_symbol_count": len(top30_symbols),
            "top100_symbols": top100_symbols,
            "top30_intraday_symbols": top30_symbols,
            "requested_symbol_count": len(candidates),
            "requested_symbols": [candidate.spot_symbol for candidate in candidates],
            "requested_intervals": list(explicit_intervals or (TOP_100_INTERVALS + TOP_30_INTERVALS)),
            "successful_sync_count": successful_sync_count_total,
            "phase_failure_count": len(phase_failures),
            "phase_failures": phase_failures,
            "phases": phase_summaries,
            "input_watermarks": {
                "quant_input_generated_at_utc": quant_input.generated_at_utc,
                "top100_symbol_count": len(top100_symbols),
                "top30_intraday_symbol_count": len(top30_symbols),
                "successful_sync_count": successful_sync_count_total,
                "phase_failure_count": len(phase_failures),
            },
            "upstream_versions": {
                "top30_intraday_limit": TOP_30_1H_LIMIT,
                "exchange_id": exchange_id,
                "quote_asset": quote_asset,
                "top100_intervals": list(TOP_100_INTERVALS),
                "top30_intervals": list(TOP_30_INTERVALS),
            },
        },
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    return summary


def _run_refresh_phase(
    *,
    plan: QuantSpotSyncPlan,
    external_root: Path,
    exchange_id: str,
    quote_asset: str,
    refresh_catalog: bool,
) -> tuple[dict[str, Any], bool, list[dict[str, Any]], int]:
    symbols = [candidate.spot_symbol for candidate in plan.candidates]
    try:
        batch_summary = sync_coinapi_ohlcv(
            external_root=external_root,
            symbols=symbols,
            intervals=plan.intervals,
            mode="refresh",
            exchange_id=exchange_id,
            quote_asset=quote_asset,
            refresh_catalog=refresh_catalog,
        )
        successful_sync_count = int(batch_summary.get("synced_symbol_count", 0) or 0)
        return (
            {
                "phase": plan.phase,
                "intervals": list(plan.intervals),
                "candidate_count": len(plan.candidates),
                "max_lookback_days": plan.max_lookback_days,
                "successful_sync_count": successful_sync_count,
                "failure_count": 0,
                "summary": batch_summary,
            },
            False,
            [],
            successful_sync_count,
        )
    except Exception as batch_exc:
        phase_results: list[dict[str, Any]] = []
        phase_errors: list[dict[str, Any]] = []
        for candidate in plan.candidates:
            try:
                phase_results.append(
                    sync_coinapi_ohlcv(
                        external_root=external_root,
                        symbols=(candidate.spot_symbol,),
                        intervals=plan.intervals,
                        mode="refresh",
                        exchange_id=exchange_id,
                        quote_asset=quote_asset,
                        refresh_catalog=False,
                    )
                )
            except Exception as exc:
                phase_errors.append(
                    _build_phase_failure(
                        phase=plan.phase,
                        candidate=candidate,
                        intervals=plan.intervals,
                        error=exc,
                    )
                )
        phase_summary = {
            "phase": plan.phase,
            "intervals": list(plan.intervals),
            "candidate_count": len(plan.candidates),
            "max_lookback_days": plan.max_lookback_days,
            "successful_sync_count": len(phase_results),
            "failure_count": len(phase_errors),
            "batch_attempt_failed": True,
            "batch_error": str(batch_exc),
            "summaries": phase_results,
        }
        if phase_errors:
            phase_summary["failures"] = phase_errors
        return phase_summary, False, phase_errors, len(phase_results)


def _build_phase_failure(
    *,
    phase: str,
    candidate: QuantUniverseCandidate,
    intervals: tuple[str, ...],
    error: Exception,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "subject": candidate.subject,
        "symbol": candidate.spot_symbol,
        "intervals": list(intervals),
        "listing_age_days": int(candidate.listing_age_days),
        "error": str(error),
    }


def _build_sync_plans(
    *,
    mode: str,
    candidates: tuple[QuantUniverseCandidate, ...],
    explicit_intervals: tuple[str, ...] = (),
) -> tuple[QuantSpotSyncPlan, ...]:
    if explicit_intervals:
        plans: list[QuantSpotSyncPlan] = []
        for interval in explicit_intervals:
            if mode == "refresh":
                plans.append(
                    QuantSpotSyncPlan(
                        phase=f"spot_{interval}_refresh",
                        intervals=(interval,),
                        candidates=candidates,
                        max_lookback_days=None,
                    )
                )
                continue
            plans.append(
                QuantSpotSyncPlan(
                    phase=f"spot_{interval}",
                    intervals=(interval,),
                    candidates=candidates,
                    max_lookback_days=PHASE_LOOKBACK_DAYS[f"spot_{interval}"],
                )
            )
        return tuple(plans)
    top100 = tuple(candidates[:100])
    top30 = tuple(candidates[:TOP_30_1H_LIMIT])
    if mode == "refresh":
        return (
            QuantSpotSyncPlan(
                phase="spot_1d_4h_refresh",
                intervals=TOP_100_INTERVALS,
                candidates=top100,
                max_lookback_days=None,
            ),
            QuantSpotSyncPlan(
                phase="spot_1h_refresh",
                intervals=TOP_30_INTERVALS,
                candidates=top30,
                max_lookback_days=None,
            ),
        )
    return (
        QuantSpotSyncPlan(
            phase="spot_1d",
            intervals=("1d",),
            candidates=top100,
            max_lookback_days=PHASE_LOOKBACK_DAYS["spot_1d"],
        ),
        QuantSpotSyncPlan(
            phase="spot_4h",
            intervals=("4h",),
            candidates=top100,
            max_lookback_days=PHASE_LOOKBACK_DAYS["spot_4h"],
        ),
        QuantSpotSyncPlan(
            phase="spot_1h",
            intervals=("1h",),
            candidates=top30,
            max_lookback_days=PHASE_LOOKBACK_DAYS["spot_1h"],
        ),
    )


def _phase_start_iso(*, as_of: str, lookback_days: int) -> str:
    as_of_date = date.fromisoformat(as_of)
    end_exclusive = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC) + timedelta(days=1)
    start = end_exclusive - timedelta(days=max(int(lookback_days), 1))
    return start.isoformat().replace("+00:00", "Z")


def _phase_end_iso(*, as_of: str) -> str:
    as_of_date = date.fromisoformat(as_of)
    end_exclusive = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC) + timedelta(days=1)
    return end_exclusive.isoformat().replace("+00:00", "Z")
