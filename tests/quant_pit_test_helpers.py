from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from enhengclaw.quant_research.contracts import (
    PIT_SELECTION_METRIC,
    PIT_SELECTION_WINDOW_BARS,
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
    liquidity_bucket_for_rank,
    utc_now,
)

_AUTO = object()


def pit_selection_policy(*, target_candidate_count: int = 100) -> dict[str, Any]:
    return {
        "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
        "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
        "selection_market_type": "spot",
        "selection_interval": "1d",
        "selection_metric": PIT_SELECTION_METRIC,
        "selection_window_bars": PIT_SELECTION_WINDOW_BARS,
        "selection_cutoff_rule": "as_of_uses_fully_closed_bars_through_d_minus_1",
        "tie_breakers": [
            "rolling_mean_quote_volume_usd_30d_desc",
            "subject_asc",
        ],
        "eligibility_requirements": [
            "valid_subject_symbol",
            "valid_spot_symbol",
            "non_stablecoin",
            "non_pegged_asset",
            "local_spot_1d_history_present",
            "minimum_30_closed_spot_1d_bars",
        ],
        "target_candidate_count": int(target_candidate_count),
    }


def pit_candidate(
    subject: str,
    rank: int,
    *,
    spot_symbol: str | None = None,
    usdm_symbol: str | None | object = _AUTO,
    selection_score: float | None = None,
    rolling_mean_quote_volume_usd_30d: float | None = None,
    listing_age_days_as_of: int = 500,
    first_spot_bar_utc: str = "2024-01-01T00:00:00Z",
    first_perp_bar_utc: str | None = "2024-01-01T00:00:00Z",
    selection_window_start_utc: str = "2026-03-21T00:00:00Z",
    selection_window_end_utc: str = "2026-04-19T23:59:59Z",
    is_stablecoin: bool = False,
    is_pegged_asset: bool = False,
    field_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_subject = str(subject).strip().upper()
    normalized_spot_symbol = str(spot_symbol or f"{normalized_subject}USDT").strip().upper()
    if usdm_symbol is _AUTO:
        normalized_usdm_symbol = normalized_spot_symbol
    elif usdm_symbol:
        normalized_usdm_symbol = str(usdm_symbol).strip().upper()
    else:
        normalized_usdm_symbol = None
    resolved_selection_score = float(selection_score if selection_score is not None else max(1.0, 1_000.0 - rank))
    resolved_mean = float(
        rolling_mean_quote_volume_usd_30d
        if rolling_mean_quote_volume_usd_30d is not None
        else resolved_selection_score
    )
    if normalized_usdm_symbol is None:
        first_perp_bar_utc = None
    return {
        "subject": normalized_subject,
        "spot_symbol": normalized_spot_symbol,
        "usdm_symbol": normalized_usdm_symbol,
        "selection_rank": int(rank),
        "selection_score": resolved_selection_score,
        "selection_metric": PIT_SELECTION_METRIC,
        "selection_window_start_utc": selection_window_start_utc,
        "selection_window_end_utc": selection_window_end_utc,
        "rolling_median_quote_volume_usd_30d": resolved_selection_score,
        "rolling_mean_quote_volume_usd_30d": resolved_mean,
        "listing_age_days_as_of": int(listing_age_days_as_of),
        "first_spot_bar_utc": first_spot_bar_utc,
        "first_perp_bar_utc": first_perp_bar_utc,
        "liquidity_bucket": str(liquidity_bucket_for_rank(rank)),
        "is_stablecoin": bool(is_stablecoin),
        "is_pegged_asset": bool(is_pegged_asset),
        "field_provenance": dict(
            field_provenance
            or {
                "fixture": {
                    "source": "unit_test_fixture",
                    "subject": normalized_subject,
                }
            }
        ),
    }


def pit_universe_payload(
    *,
    as_of: str,
    candidates: Iterable[dict[str, Any]],
    generated_at_utc: str | None = None,
    selection_policy: dict[str, Any] | None = None,
    candidate_count_target: int = 100,
    top100_complete: bool | None = None,
    input_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_list = list(candidates)
    target = int(candidate_count_target)
    return {
        "as_of": as_of,
        "generated_at_utc": generated_at_utc or utc_now(),
        "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
        "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
        "selection_policy": dict(selection_policy or pit_selection_policy(target_candidate_count=target)),
        "candidate_count_target": target,
        "candidate_count_effective": len(candidate_list),
        "top100_complete": bool(len(candidate_list) >= target if top100_complete is None else top100_complete),
        "input_provenance": dict(
            input_provenance
            or {
                "mode": "unit_test_fixture",
                "selection_end_utc": f"{as_of}T00:00:00Z",
            }
        ),
        "candidates": candidate_list,
    }


def write_pit_quant_input(
    *,
    root: Path,
    as_of: str,
    candidates: Iterable[dict[str, Any]],
    filename: str | None = None,
    payload_overrides: dict[str, Any] | None = None,
) -> Path:
    payload = pit_universe_payload(as_of=as_of, candidates=candidates)
    if payload_overrides:
        payload.update(payload_overrides)
    path = root / (filename or f"pit-liquidity-top100-{as_of}.quant_universe.json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
