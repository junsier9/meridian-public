from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from .contracts import read_json
from .validation_contract import load_validation_contract, validation_contract_threshold


ROOT = Path(__file__).resolve().parents[3]
DATA_READINESS_CONTRACT_PATH = ROOT / "config" / "quant_research" / "data_readiness_contract.json"

DISCOVERY_EVENT_BLOCKER = "temporal_event_tape_missing"
DISCOVERY_DERIVATIVES_BLOCKER = "derivatives_history_gap"
SINGLE_ASSET_SPOT_BLOCKER = "single_asset_spot_history_gap"
CROSS_SECTIONAL_SPOT_BLOCKER = "cross_sectional_spot_history_gap"
CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER = "cross_sectional_daily_4h_spot_history_gap"
CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER = "cross_sectional_intraday_1h_spot_history_gap"
SINGLE_ASSET_DATASET_PROFILE = "single_asset"
CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE = "cross_sectional_daily_4h"
CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE = "cross_sectional_intraday_1h"

DATASET_PROFILE_TO_SECTION = {
    SINGLE_ASSET_DATASET_PROFILE: "single_asset",
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE: "cross_sectional_daily_4h",
    CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE: "cross_sectional_intraday_1h",
}

DATASET_PROFILE_TO_SPOT_BLOCKER = {
    SINGLE_ASSET_DATASET_PROFILE: SINGLE_ASSET_SPOT_BLOCKER,
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE: CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
    CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE: CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
}

DERIVATIVES_FIELD_FAMILY_MAP = {
    "funding_rate": "funding",
    "open_interest": "open_interest",
    "open_interest_value": "open_interest",
    "perp_close": "basis",
}


def load_data_readiness_contract() -> dict[str, Any]:
    return read_json(DATA_READINESS_CONTRACT_PATH)


def resolve_default_spot_ohlcv_external_root(*, spot_ohlcv_external_root: Path | None) -> Path | None:
    if spot_ohlcv_external_root is not None:
        return Path(spot_ohlcv_external_root).expanduser().resolve()
    localappdata = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if not localappdata:
        return None
    candidate = Path(localappdata) / "EnhengClaw" / "market_history" / "coinapi_ohlcv"
    if not candidate.exists():
        return None
    return candidate.expanduser().resolve()


def spot_provider_lane(*, spot_ohlcv_external_root: Path | None) -> str:
    return "coinapi_spot_binance_fallback" if spot_ohlcv_external_root is not None else "binance_only"


def blocked_discovery_model_families(*, contract: dict[str, Any] | None = None) -> set[str]:
    payload = contract or load_data_readiness_contract()
    return {
        str(item).strip()
        for item in list(payload.get("blocked_discovery_model_families") or [])
        if str(item).strip()
    }


def blocked_discovery_reason(*, model_family: str, contract: dict[str, Any] | None = None) -> str | None:
    normalized = str(model_family or "").strip()
    if not normalized:
        return None
    if normalized == "event_drift":
        return DISCOVERY_EVENT_BLOCKER
    if normalized in blocked_discovery_model_families(contract=contract):
        return DISCOVERY_DERIVATIVES_BLOCKER
    return None


def strategy_derivatives_fields(*, strategy_entry: dict[str, Any]) -> list[str]:
    dependencies = dict(strategy_entry.get("data_dependencies") or {})
    return [
        str(item).strip()
        for item in list(dependencies.get("derivatives_fields") or [])
        if str(item).strip()
    ]


def strategy_requires_derivatives(*, strategy_entry: dict[str, Any]) -> bool:
    return bool(strategy_derivatives_fields(strategy_entry=strategy_entry))


def required_derivatives_families(*, strategy_entry: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for field_name in strategy_derivatives_fields(strategy_entry=strategy_entry):
        family_name = DERIVATIVES_FIELD_FAMILY_MAP.get(str(field_name).strip())
        if family_name and family_name not in families:
            families.append(family_name)
    return families


def strategy_requires_temporal_event_tape(*, strategy_entry: dict[str, Any]) -> bool:
    return str(strategy_entry.get("model_family") or "").strip() == "event_drift"


def is_daily_executable_strategy(*, strategy_entry: dict[str, Any]) -> bool:
    research_lane = str(strategy_entry.get("research_lane") or "").strip()
    if research_lane == "control_baseline":
        return False
    thesis_profile = dict(strategy_entry.get("thesis_profile") or {})
    if research_lane and research_lane != "control_baseline" and not thesis_profile:
        return False
    if strategy_entry.get("daily_executable") is False:
        return False
    if blocked_discovery_reason(
        model_family=str(strategy_entry.get("model_family") or "").strip(),
    ) is not None:
        return False
    if strategy_requires_temporal_event_tape(strategy_entry=strategy_entry):
        return False
    return bool(strategy_entry.get("daily_executable", True))


def cross_sectional_subject_min(*, contract: dict[str, Any] | None = None) -> int:
    return cross_sectional_subject_min_for_profile(
        dataset_profile=CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
        contract=contract,
    )


def normalize_dataset_profile(*, shape: str, dataset_profile: str | None = None) -> str:
    normalized_profile = str(dataset_profile or "").strip()
    if normalized_profile:
        if normalized_profile not in DATASET_PROFILE_TO_SECTION:
            raise ValueError(f"unsupported quant dataset_profile: {normalized_profile}")
        return normalized_profile
    normalized_shape = str(shape or "").strip()
    if normalized_shape == "single_asset":
        return SINGLE_ASSET_DATASET_PROFILE
    if normalized_shape == "cross_sectional":
        return CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE
    raise ValueError(f"unsupported quant dataset shape: {shape!r}")


def data_readiness_section(
    *,
    shape: str,
    dataset_profile: str | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = contract or load_data_readiness_contract()
    profile = normalize_dataset_profile(shape=shape, dataset_profile=dataset_profile)
    section_name = DATASET_PROFILE_TO_SECTION[profile]
    return dict(payload.get(section_name) or {})


def dataset_required_spot_intervals(
    *,
    shape: str,
    dataset_profile: str | None = None,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    section = data_readiness_section(
        shape=shape,
        dataset_profile=dataset_profile,
        contract=contract,
    )
    return [
        str(item).strip()
        for item in list(section.get("required_spot_intervals") or [])
        if str(item).strip()
    ]


def dataset_spot_blocker(*, shape: str, dataset_profile: str | None = None) -> str:
    profile = normalize_dataset_profile(shape=shape, dataset_profile=dataset_profile)
    return DATASET_PROFILE_TO_SPOT_BLOCKER[profile]


def cross_sectional_subject_min_for_profile(
    *,
    dataset_profile: str,
    contract: dict[str, Any] | None = None,
) -> int:
    section = data_readiness_section(
        shape="cross_sectional",
        dataset_profile=dataset_profile,
        contract=contract,
    )
    try:
        return int(section.get("executable_subject_count_min") or 30)
    except (TypeError, ValueError):
        return 30


def cross_sectional_coverage_fraction_min(
    *,
    dataset_profile: str = CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    contract: dict[str, Any] | None = None,
) -> float:
    section = data_readiness_section(
        shape="cross_sectional",
        dataset_profile=dataset_profile,
        contract=contract,
    )
    try:
        return float(section.get("executable_coverage_fraction_min") or 0.85)
    except (TypeError, ValueError):
        return 0.85


def cross_sectional_daily_lane_coverage_fraction_min(
    *,
    dataset_profile: str = CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    contract: dict[str, Any] | None = None,
) -> float:
    section = data_readiness_section(
        shape="cross_sectional",
        dataset_profile=dataset_profile,
        contract=contract,
    )
    try:
        return float(
            section.get("daily_lane_coverage_fraction_min")
            or section.get("executable_coverage_fraction_min")
            or 0.85
        )
    except (TypeError, ValueError):
        return cross_sectional_coverage_fraction_min(
            dataset_profile=dataset_profile,
            contract=contract,
        )


def required_cross_sectional_subject_count(
    *,
    requested_universe_count: int,
    dataset_profile: str = CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    contract: dict[str, Any] | None = None,
) -> int:
    if requested_universe_count <= 0:
        return cross_sectional_subject_min_for_profile(
            dataset_profile=dataset_profile,
            contract=contract,
        )
    coverage_requirement = int(
        math.ceil(
            float(requested_universe_count)
            * cross_sectional_coverage_fraction_min(
                dataset_profile=dataset_profile,
                contract=contract,
            )
        )
    )
    subject_floor = min(
        cross_sectional_subject_min_for_profile(
            dataset_profile=dataset_profile,
            contract=contract,
        ),
        int(requested_universe_count),
    )
    return max(subject_floor, coverage_requirement)


def cross_sectional_daily_lane_eligible(
    *,
    subject_count: int,
    requested_universe_count: int,
    dataset_profile: str = CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    contract: dict[str, Any] | None = None,
) -> bool:
    if requested_universe_count <= 0:
        return False
    coverage_fraction = float(subject_count) / float(requested_universe_count)
    required_subject_count = required_cross_sectional_subject_count(
        requested_universe_count=requested_universe_count,
        dataset_profile=dataset_profile,
        contract=contract,
    )
    return (
        subject_count >= required_subject_count
        and coverage_fraction
        >= cross_sectional_daily_lane_coverage_fraction_min(
            dataset_profile=dataset_profile,
            contract=contract,
        )
    )


def required_walk_forward_window_count() -> int:
    validation_contract = load_validation_contract()
    return int(
        validation_contract_threshold(
            contract=validation_contract,
            section="walk_forward_assessment",
            field_name="window_count_min",
            default=10,
        )
        or 10
    )


def build_dataset_data_readiness(
    *,
    dataset_id: str,
    shape: str,
    subject_count: int,
    requested_universe_count: int,
    spot_ohlcv_external_root: Path | None,
    dataset_profile: str | None = None,
    missing_spot_symbols_by_interval: dict[str, list[str]] | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = contract or load_data_readiness_contract()
    normalized_profile = normalize_dataset_profile(shape=shape, dataset_profile=dataset_profile)
    coverage_fraction = (
        float(subject_count) / float(requested_universe_count)
        if requested_universe_count > 0
        else 0.0
    )
    data_gap_blockers: list[str] = []
    cross_subject_count = subject_count if str(shape) == "cross_sectional" else None
    coverage_fraction_min = None
    required_subject_count_min = None
    dataset_lane_ready = None
    if str(shape) == "cross_sectional":
        coverage_fraction_min = cross_sectional_coverage_fraction_min(
            dataset_profile=normalized_profile,
            contract=payload,
        )
        required_subject_count_min = required_cross_sectional_subject_count(
            requested_universe_count=requested_universe_count,
            dataset_profile=normalized_profile,
            contract=payload,
        )
        dataset_lane_ready = cross_sectional_daily_lane_eligible(
            subject_count=subject_count,
            requested_universe_count=requested_universe_count,
            dataset_profile=normalized_profile,
            contract=payload,
        )
        if (
            subject_count < int(required_subject_count_min)
            or coverage_fraction < float(coverage_fraction_min)
        ):
            data_gap_blockers.append(dataset_spot_blocker(shape=shape, dataset_profile=normalized_profile))
    section = data_readiness_section(
        shape=shape,
        dataset_profile=normalized_profile,
        contract=payload,
    )
    normalized_missing_spot_symbols_by_interval = {
        str(interval).strip(): sorted(
            {
                str(symbol).strip().upper()
                for symbol in list(symbols or [])
                if str(symbol).strip()
            }
        )
        for interval, symbols in dict(missing_spot_symbols_by_interval or {}).items()
        if str(interval).strip()
    }
    return {
        "dataset_id": dataset_id,
        "dataset_profile": normalized_profile,
        "spot_lane": spot_provider_lane(spot_ohlcv_external_root=spot_ohlcv_external_root),
        "spot_subject_coverage": {
            "requested_universe_count": int(requested_universe_count),
            "available_subject_count": int(subject_count),
            "coverage_fraction": coverage_fraction,
            "coverage_fraction_min": coverage_fraction_min,
            "required_subject_count_min": required_subject_count_min,
            "coverage_requirement_met": (
                None
                if coverage_fraction_min is None or required_subject_count_min is None
                else (
                    subject_count >= int(required_subject_count_min)
                    and coverage_fraction >= float(coverage_fraction_min)
                )
            ),
            "required_spot_intervals": list(section.get("required_spot_intervals") or []),
            "missing_spot_symbols_by_interval": normalized_missing_spot_symbols_by_interval,
        },
        "cross_sectional_executable_subject_count": cross_subject_count,
        "dataset_lane_eligible": dataset_lane_ready,
        "cross_sectional_daily_lane_eligible": (
            dataset_lane_ready if normalized_profile == CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE else None
        ),
        "cross_sectional_intraday_lane_eligible": (
            dataset_lane_ready if normalized_profile == CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE else None
        ),
        "blocked_strategy_ids": [],
        "data_gap_blockers": data_gap_blockers,
    }


def derivatives_ready_row_fraction_thresholds(
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, float]:
    payload = contract or load_data_readiness_contract()
    thresholds = dict(payload.get("derivatives_required") or {})
    return {
        "train": float(thresholds.get("train_ready_row_fraction_min") or 0.8),
        "validation": float(thresholds.get("validation_ready_row_fraction_min") or 0.8),
        "test": float(thresholds.get("test_ready_row_fraction_min") or 0.8),
    }


def evaluate_derivatives_history_gap(
    *,
    strategy_entry: dict[str, Any],
    derivatives_strategy_quality: dict[str, Any] | None,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    required_families = required_derivatives_families(strategy_entry=strategy_entry)
    if not required_families:
        return []
    thresholds = derivatives_ready_row_fraction_thresholds(contract=contract)
    blockers: list[str] = []
    quality = dict(derivatives_strategy_quality or {})
    for family_name in required_families:
        family = dict(quality.get(f"{family_name}_family") or {})
        train_ready = float(family.get("train_ready_row_fraction") or 0.0)
        validation_ready = float(family.get("validation_ready_row_fraction") or 0.0)
        test_ready = float(family.get("test_ready_row_fraction") or 0.0)
        if train_ready < float(thresholds["train"]):
            blockers.append(DISCOVERY_DERIVATIVES_BLOCKER)
        if validation_ready < float(thresholds["validation"]):
            blockers.append(DISCOVERY_DERIVATIVES_BLOCKER)
        if test_ready < float(thresholds["test"]):
            blockers.append(DISCOVERY_DERIVATIVES_BLOCKER)
    return sorted(set(blockers))
