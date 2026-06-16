from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .contracts import LIQUIDITY_BUCKETS, STRATEGY_PROFILES, read_json
from .data_readiness import (
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
    SINGLE_ASSET_DATASET_PROFILE,
    normalize_dataset_profile,
)


CONTROL_BASELINE_LANE = "control_baseline"
HYPOTHESIS_RESEARCH_LANES = (
    "hypothesis_factor",
    "hypothesis_portfolio",
    "hypothesis_model",
)
HYPOTHESIS_MODEL_LANE = "hypothesis_model"
HYPOTHESIS_MODEL_FAMILIES = {"ranking_scorer", "logistic_regression"}
LIQUID_PERP_CORE_20_PRESET = "liquid_perp_core_20"
LIQUID_PERP_TIER2_20_PRESET = "liquid_perp_tier2_20"
LIQUID_PERP_CORE_30_PRESET = "liquid_perp_core_30"
DERIVATIVES_THESIS_FEATURE_COLUMNS = (
    "funding_rate",
    "funding_zscore_20",
    "basis_proxy",
    "basis_zscore_20",
    "oi_change_5",
    "perp_quote_volume_usd",
    "coinglass_taker_imbalance_5d_sum",
    "coinglass_global_account_long_pct",
    "coinglass_liquidation_imbalance_24h",
    "coinglass_top_trader_long_pct",
    "coinglass_top_trader_long_pct_smooth_5",
    "coinglass_top_trader_long_pct_smooth_20",
    "coinglass_top_trader_long_pct_smooth_60",
    "coinglass_liq_intraday_concentration_24h",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "coinglass_top_trader_intraday_volatility_24h",
    "coinglass_orderbook_imb_persistence_24h",
    "quality_funding_oi",
    "funding_crowding_basis",
    "stress_liq_conc_iv",
    "crowd_obi_abs_funding",
    "crowd_tt_signal",
    "disp_taker_imb_xs",
    "unwind_liq_dh",
    "crowd_basis_oi_signed",
    "crowd_abs_basis_oi",
    "crowd_funding_obi_signed",
    "disagree_tt_retail",
    "unwind_liq_imb_xs",
)
DETERMINISTIC_STRATEGY_MANIFEST_CONTRACT_VERSION = "quant_deterministic_strategy_manifest.v1"
DETERMINISTIC_STRATEGY_MANIFEST_PATH = Path(__file__).with_name("deterministic_strategy_manifest.json")
DETERMINISTIC_STRATEGY_SOURCE = "deterministic_core"
DETERMINISTIC_SELECTION_LANE = "deterministic_manifest"
DETERMINISTIC_THESIS_REQUIRED_FEATURE_COLUMNS: dict[str, tuple[str, ...]] = {
    "trend_following": ("momentum_6", "momentum_24", "ema_slope_6_18", "basis_proxy"),
    "mean_reversion": ("range_position_20", "basis_zscore_20"),
    "breakout_continuation": ("distance_to_high_20", "momentum_3", "quote_volume_expansion", "funding_zscore_20"),
    "breakout_volatility_expansion": (
        "distance_to_high_20",
        "momentum_3",
        "quote_volume_expansion",
        "realized_volatility_20",
        "atr_proxy_20",
    ),
    "relative_strength_cross_section": ("relative_strength_20", "momentum_5", "quote_volume_expansion"),
    "ranking_scorer": ("relative_strength_20", "quote_volume_expansion", "realized_volatility_20"),
    "carry_funding": ("funding_zscore_20", "basis_zscore_20", "oi_change_5"),
    "basis_divergence": ("basis_zscore_20", "funding_zscore_20", "oi_change_5"),
    "volatility_expansion": ("realized_volatility_20", "atr_proxy_20", "quote_volume_expansion", "momentum_3"),
    "event_drift": ("event_flag_count", "narrative_tag_count", "momentum_6", "relative_strength_20"),
}
DETERMINISTIC_THESIS_MARKET_MECHANISMS: dict[str, str] = {
    "trend_following": "persistent directional continuation after liquid market confirmation",
    "mean_reversion": "short-horizon reversion after local extension in liquid names",
    "breakout_continuation": "post-breakout continuation supported by participation expansion",
    "breakout_volatility_expansion": "spot breakouts persist when volatility and participation expand together",
    "relative_strength_cross_section": "relative-strength sorting across the liquid universe",
    "ranking_scorer": "composite ranking over liquid-universe quality and momentum features",
    "carry_funding": "funding and basis dislocations mean revert after crowding extremes",
    "basis_divergence": "basis dislocations compress after stretched derivative positioning",
    "volatility_expansion": "range expansion persists when realized volatility and participation co-move",
    "event_drift": "event-driven drift persists while narrative and momentum remain aligned",
}
DETERMINISTIC_THESIS_DIRECTIONAL_CLAIMS: dict[str, str] = {
    "trend_following": "increase exposure when momentum and slope features stay positive",
    "mean_reversion": "fade local extension when range positioning implies reversion",
    "breakout_continuation": "follow confirmed breakouts when volume expansion stays supportive",
    "breakout_volatility_expansion": "add spot exposure only when breakout proximity, volume expansion, and volatility expansion align",
    "relative_strength_cross_section": "own the stronger cohort and avoid the weaker cohort",
    "ranking_scorer": "rank liquid names by composite score and rebalance into the top cohort",
    "carry_funding": "lean against crowded carry and basis extremes",
    "basis_divergence": "trade toward basis normalization after extreme divergence",
    "volatility_expansion": "participate when volatility expansion aligns with follow-through",
    "event_drift": "stay with event-linked drift while the signal remains persistent",
}
DETERMINISTIC_INTENDED_HOLDING_HORIZON_BARS: dict[str, int] = {
    "trend_following": 6,
    "mean_reversion": 6,
    "breakout_continuation": 6,
    "breakout_volatility_expansion": 6,
    "relative_strength_cross_section": 6,
    "ranking_scorer": 6,
    "carry_funding": 6,
    "basis_divergence": 6,
    "volatility_expansion": 6,
    "event_drift": 6,
}


def strategy_lifecycle(strategy_entry: dict[str, Any]) -> str:
    return str(strategy_entry.get("lifecycle") or "active").strip() or "active"


def feature_group_for_column(column: str) -> str | None:
    if column in {
        "news_short_veto_mini_flag",
        "news_short_veto_adjudicated_flag",
        "news_short_veto_adjudicated_do_not_fill_multiplier",
        "news_short_veto_adjudicated_reduced_exposure_multiplier",
    }:
        return "events"
    if column.startswith("m3_3_event_state_") or column.startswith("m3_3_strict_event_state_"):
        return "events"
    if column.startswith("distance_to_") or column == "range_position_20":
        return "structure"
    # Alpha Ontology W1.1 — abnormal_range_z_* is a 60-bar z-score of
    # (high - low) / close; semantically a structure / range factor.
    if column.startswith("abnormal_range_z_"):
        return "structure"
    if (
        column == "atr_proxy_20"
        or column.startswith("realized_volatility_")
        or column.startswith("intraday_realized_vol_")
    ):
        return "volatility"
    # Alpha Ontology W1.1 — MF-10 higher-moment fragility factors are
    # volatility-family by construction (skew / kurt / vol-of-vol /
    # asymmetric vol ratio).
    if (
        column.startswith("realized_skew_")
        or column.startswith("realized_kurt_")
        or column.startswith("vol_of_vol_")
        or column.startswith("downside_upside_vol_ratio_")
    ):
        return "volatility"
    # Alpha Ontology W3.1 — MF-08 state-machine factors derived from vol /
    # funding / OI shocks; no event__ tape involved.
    if column in {"vol_shock_impulse_phase", "shock_co_occurrence_index"}:
        return "volatility"
    if column in {"funding_flip_decay_phase", "oi_shock_decay_phase"}:
        return "derivatives"
    # Alpha Ontology W3.2 — MF-09 co-jump & contagion network factors.
    # Universe-wide / BTC-anchored structural measures; volatility group.
    if column in {
        "co_jump_count_3d",
        "lead_lag_beta_btc",
        "lead_lag_residual_strength",
        "contagion_in_degree",
    }:
        return "volatility"
    # Alpha Ontology W3.3 — MF-11 liquidity migration / universe rotation.
    # F41/F42 are quote-volume-share derived (volume); F44 is dispersion of
    # returns (volatility); F45 is idiosyncratic R^2 share (volatility).
    if column in {"quote_share_change_30d", "universe_rank_velocity_10"}:
        return "volume"
    if column in {"dispersion_of_returns", "idiosyncratic_share"}:
        return "volatility"
    if column in {"quote_volume_expansion", "liquidity_stress_qv_iv", "stress_abs_basis_qv"}:
        return "volume"
    # Alpha Ontology W1.1 — MF-06 reflexive-flow factors operate on quote
    # volume / flow imbalance. Group as volume.
    if (
        column.startswith("qv_acceleration_")
        or column.startswith("absorption_")
        or column.startswith("flow_persistence_")
        or column.startswith("capitulation_amplification_")
    ):
        return "volume"
    if (
        column.startswith("momentum_")
        or column.startswith("ema_slope_")
        or column.startswith("sma_slope_")
        or column in {"return_1"}
        or column.startswith("relative_strength")
    ):
        return "trend"
    if column in DERIVATIVES_THESIS_FEATURE_COLUMNS:
        return "derivatives"
    # Alpha Ontology W1.1 — MF-04 carry-residual factors and basis derivatives.
    if (
        column.startswith("funding_basis_residual_")
        or column.startswith("basis_velocity_")
        or column.startswith("basis_carry_")
    ):
        return "derivatives"
    # M2.2 F08 — funding microstructure (skew/kurt of funding_rate per subject)
    if column.startswith("funding_term_"):
        return "derivatives"
    # M2.3 F62 — settlement-cycle premium (pre-settlement-hour drift)
    if column.startswith("settlement_cycle_"):
        return "derivatives"
    # M2.4 F-triangle — Funding-OI-Basis 3-equation residual
    if column.startswith("triangle_residual_") or column.startswith("triangle_r2_"):
        return "derivatives"
    # SP-A liq cascade — per-subject 1h liq-to-OI z-score, daily aggregated
    if column.startswith("liq_cascade_"):
        return "derivatives"
    # SP-B partial — 1h Coinglass microstructure (top trader / taker / disagreement)
    if (
        column.startswith("top_global_disagreement_")
        or column.startswith("top_trader_velocity_")
        or column.startswith("taker_skew_")
    ):
        return "derivatives"
    # SP-F sub-day funding microstructure — per-subject 4h-grain funding rate
    # sequence aggregated to daily F1 (intraday dispersion) / F2 (sign flip
    # count) / F3 (sub-day skew). funding_intraday_dispersion_30d is the
    # score-admissible winner (G6 vs lsk3+F08 = +0.040 t=+7.24 at h10d).
    if (
        column.startswith("funding_intraday_dispersion_")
        or column.startswith("funding_sign_flip_count_")
        or column == "funding_term_skew_30d_4h"
    ):
        return "derivatives"
    if (
        column.startswith("pump_exhaustion_")
        or column.startswith("pump_funding_oi_crowding_")
        or column.startswith("post_pump_stall_")
    ):
        return "derivatives"
    # MF-01 orderbook / inventory-transfer boundary selectors are derived from
    # CoinGlass 1h orderbook and taker-flow state, then aggregated to daily.
    # They are used as short-boundary replacement scores rather than global
    # base-score factors, but the data lineage is still derivative microstructure.
    if column in {
        "boundary_fragile_orderbook_score",
        "pump_bid_replenishment_failure_score",
        "mf01_short_boundary_combo_score",
        "boundary_fragile_orderbook_flag",
        "pump_bid_replenishment_failure_flag",
        "mf01_spk_confirmation_flag",
        "mf01_spk_confirmation_score",
        "mf01_spk_selected_short_veto_flag",
        "mf01_post_cascade_guardrail_flag",
    }:
        return "derivatives"
    if column in {
        "selection_rank",
        "listing_age_days_as_of",
        "rolling_median_quote_volume_usd_30d",
        "stablecoin_flow_signal_ready",
        "stablecoin_labeled_coverage_ratio",
        "stablecoin_exchange_netflow_ratio",
        "stablecoin_whale_to_exchange_ratio",
        "stablecoin_issuance_ratio_z14",
        "stablecoin_velocity_log_z14",
        "stablecoin_exchange_absorption_score_v1",
        "stablecoin_whale_exchange_stress_score_v1",
        "m3_2_panel_ready",
        "m3_2_stable_supply_impulse_state",
        "m3_2_stable_dry_powder_state",
        "m3_2_stable_btc_flow_asymmetry_state",
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
        "m3_2_tron_flow_impulse_state",
        "m3_2_tron_flow_quality_state",
        "m3_2_tron_speculative_heat_state",
    }:
        return "core_context"
    return None


def select_feature_columns(*, numeric_feature_columns: list[str], feature_groups: Iterable[str]) -> list[str]:
    allowed = {str(group).strip() for group in feature_groups if str(group).strip()}
    return [column for column in numeric_feature_columns if feature_group_for_column(column) in allowed]


def _build_deterministic_thesis_profile(
    *,
    strategy_id: str,
    shape: str,
    dataset_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any],
    model_family: str,
    feature_groups: list[str],
    profile_constraints: dict[str, Any],
    requires_derivatives_features: bool,
) -> dict[str, Any]:
    allowed_feature_groups = {str(group).strip() for group in feature_groups if str(group).strip()}
    required_feature_columns = [
        column
        for column in DETERMINISTIC_THESIS_REQUIRED_FEATURE_COLUMNS.get(model_family, ())
        if feature_group_for_column(column) in allowed_feature_groups
    ]
    thesis_family = f"deterministic_{model_family}"
    return {
        "thesis_id": strategy_id,
        "thesis_family": thesis_family,
        "market_mechanism": DETERMINISTIC_THESIS_MARKET_MECHANISMS.get(
            model_family,
            "deterministic baseline hypothesis",
        ),
        "directional_claim": DETERMINISTIC_THESIS_DIRECTIONAL_CLAIMS.get(
            model_family,
            "trade only when the deterministic baseline score remains aligned with the hypothesis",
        ),
        "universe_rule": {"subject": subject} if shape == "single_asset" else dict(universe_filter),
        "dataset_profile": dataset_profile,
        "execution_venue": "spot" if bool(profile_constraints.get("spot_only")) else "spot_or_perp",
        "requires_derivatives_features": requires_derivatives_features,
        "minimum_executable_history_days": 180,
        "minimum_executable_coverage_ratio": 1.0 if shape == "single_asset" else 0.85,
        "required_feature_columns": required_feature_columns,
        "factor_formula": " + ".join(required_feature_columns) if required_feature_columns else model_family,
        "intended_holding_horizon_bars": int(
            DETERMINISTIC_INTENDED_HOLDING_HORIZON_BARS.get(model_family, 6)
        ),
        "falsification_conditions": [
            "validation_return_negative",
            "walk_forward_median_oos_sharpe_non_positive",
            "regime_holdout_failed",
        ],
    }


def load_deterministic_strategy_manifest(*, path: Path | None = None) -> dict[str, Any]:
    manifest_path = (path or DETERMINISTIC_STRATEGY_MANIFEST_PATH).expanduser().resolve()
    payload = read_json(manifest_path)
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != DETERMINISTIC_STRATEGY_MANIFEST_CONTRACT_VERSION:
        raise ValueError(
            "deterministic strategy manifest contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("deterministic strategy manifest must contain a non-empty entries list")
    normalized_entries = [_normalize_manifest_entry(entry, index=index) for index, entry in enumerate(entries)]
    return {
        "path": str(manifest_path),
        "contract_version": contract_version,
        "selection_policy": str(payload.get("selection_policy") or "checked_in_manifest_order_enabled_only"),
        "entries": normalized_entries,
    }


def _normalize_manifest_entry(entry: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"deterministic strategy manifest entry {index} must be an object")
    strategy_id = str(entry.get("strategy_id") or "").strip()
    shape = str(entry.get("shape") or "").strip()
    model_family = str(entry.get("model_family") or "").strip()
    strategy_profile = str(entry.get("strategy_profile") or "").strip()
    if not strategy_id or not shape or not model_family or not strategy_profile:
        raise ValueError(f"deterministic strategy manifest entry {index} is missing required fields")
    if strategy_profile not in STRATEGY_PROFILES:
        raise ValueError(f"unsupported strategy_profile in deterministic manifest: {strategy_profile}")
    if shape not in {"single_asset", "cross_sectional"}:
        raise ValueError(f"unsupported shape in deterministic manifest: {shape}")
    subject = str(entry.get("subject") or "").strip().upper() or None
    universe_filter = dict(entry.get("universe_filter") or {})
    if shape == "single_asset" and not subject:
        raise ValueError(f"single_asset deterministic strategy {strategy_id} must define subject")
    if shape == "cross_sectional" and subject:
        raise ValueError(f"cross_sectional deterministic strategy {strategy_id} must not define subject")
    feature_groups = [str(item).strip() for item in list(entry.get("feature_groups") or []) if str(item).strip()]
    if not feature_groups:
        raise ValueError(f"deterministic strategy {strategy_id} must define feature_groups")
    dataset_profile = normalize_dataset_profile(
        shape=shape,
        dataset_profile=str(entry.get("dataset_profile") or "").strip() or None,
    )
    profile_constraints = _normalize_profile_constraints(
        profile_constraints=dict(entry.get("profile_constraints") or {}),
        strategy_id=strategy_id,
    )
    expected_spec_hash = compute_strategy_spec_hash(
        shape=shape,
        dataset_profile=dataset_profile,
        strategy_profile=strategy_profile,
        subject=subject,
        universe_filter=universe_filter,
        model_family=model_family,
        feature_groups=feature_groups,
        profile_constraints=profile_constraints,
    )
    observed_spec_hash = str(entry.get("spec_hash") or "").strip()
    if observed_spec_hash != expected_spec_hash:
        raise ValueError(
            f"deterministic strategy {strategy_id} spec_hash mismatch: "
            f"{observed_spec_hash or 'missing'} != {expected_spec_hash}"
        )
    requires_derivatives_features = bool(
        "derivatives" in feature_groups or model_family in {"carry_funding", "basis_divergence", "event_drift"}
    )
    thesis_profile = _build_deterministic_thesis_profile(
        strategy_id=strategy_id,
        shape=shape,
        dataset_profile=dataset_profile,
        subject=subject,
        universe_filter=universe_filter,
        model_family=model_family,
        feature_groups=feature_groups,
        profile_constraints=profile_constraints,
        requires_derivatives_features=requires_derivatives_features,
    )
    return {
        "strategy_id": strategy_id,
        "enabled": bool(entry.get("enabled", True)),
        "shape": shape,
        "dataset_profile": dataset_profile,
        "subject": subject,
        "universe_filter": universe_filter,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "feature_groups": feature_groups,
        "profile_constraints": profile_constraints,
        "spec_hash": expected_spec_hash,
        "source": DETERMINISTIC_STRATEGY_SOURCE,
        "research_lane": CONTROL_BASELINE_LANE,
        "lifecycle": "active",
        "monitoring_status": "active",
        "selection_lane": DETERMINISTIC_SELECTION_LANE,
        "promotion_state": "frozen_core",
        "promotion_eligibility": "ineligible",
        "family_id": model_family,
        "feature_family_ids": [],
        "requires_derivatives_features": requires_derivatives_features,
        "daily_executable": bool(entry.get("enabled", True)),
        "thesis_family": thesis_profile["thesis_family"],
        "thesis_profile": thesis_profile,
        "proposal_origin": DETERMINISTIC_STRATEGY_SOURCE,
        "search_action": "deterministic_manifest",
        "registry_snapshot_id": None,
        "published_via": "not_published",
        "model_overlay_ready": False,
    }


def _normalize_profile_constraints(*, profile_constraints: dict[str, Any], strategy_id: str) -> dict[str, Any]:
    allowed_buckets = [str(item).strip() for item in list(profile_constraints.get("allowed_liquidity_buckets") or [])]
    if not allowed_buckets:
        raise ValueError(f"deterministic strategy {strategy_id} must define allowed_liquidity_buckets")
    invalid_buckets = sorted(set(allowed_buckets) - set(LIQUIDITY_BUCKETS))
    if invalid_buckets:
        raise ValueError(
            f"deterministic strategy {strategy_id} has unsupported allowed_liquidity_buckets: {invalid_buckets}"
        )
    return {
        "allowed_liquidity_buckets": sorted(set(allowed_buckets)),
        "spot_only": bool(profile_constraints.get("spot_only", False)),
        "short_allowed": bool(profile_constraints.get("short_allowed", False)),
        "long_only": bool(profile_constraints.get("long_only", False)),
        "max_gross_leverage": float(profile_constraints.get("max_gross_leverage", 1.0) or 1.0),
        "long_leverage": float(profile_constraints.get("long_leverage", 1.0) or 1.0),
        "short_leverage": float(profile_constraints.get("short_leverage", 0.0) or 0.0),
        "max_turnover_per_rebalance": float(profile_constraints.get("max_turnover_per_rebalance", 1.0) or 1.0),
    }


def compute_strategy_spec_hash(
    *,
    shape: str,
    dataset_profile: str | None,
    strategy_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    model_family: str,
    feature_groups: Iterable[str],
    profile_constraints: dict[str, Any],
) -> str:
    payload = {
        "shape": str(shape),
        "dataset_profile": normalize_dataset_profile(shape=shape, dataset_profile=dataset_profile),
        "strategy_profile": str(strategy_profile),
        "subject": None if subject is None else str(subject).upper(),
        "universe_filter": _json_ready(universe_filter or {}),
        "model_family": str(model_family),
        "feature_groups": [str(item) for item in feature_groups],
        "profile_constraints": _json_ready(profile_constraints),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_ready(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): _json_ready(value) for key, value in sorted(payload.items(), key=lambda item: str(item[0]))}
    if isinstance(payload, (list, tuple)):
        return [_json_ready(value) for value in payload]
    return payload
