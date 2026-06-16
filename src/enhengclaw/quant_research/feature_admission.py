from __future__ import annotations

from typing import Any, Iterable


FEATURE_ADMISSION_POLICY_VERSION = "quant_feature_admission_policy.v1"
FEATURE_ADMISSION_ALLOWED_GROUPS = (
    "structure",
    "volatility",
    "volume",
    "trend",
    "derivatives",
    "events",
)
FEATURE_ADMISSION_COMPATIBLE_EMPTY_GROUPS = ("core_context",)
FEATURE_ADMISSION_ALLOWED_PREFIXES = (
    "distance_to_",
    "momentum_",
    "ema_slope_",
    "sma_slope_",
    "relative_strength",
    "intraday_realized_vol_",
    # Alpha Ontology W1.2 — admit MF-04 / MF-06 / MF-10 candidate factor families
    # produced by the W1.1 builder. See docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §H.1.
    "realized_skew_",
    "realized_kurt_",
    "flow_persistence_",
    "absorption_",
    "qv_acceleration_",
    "funding_basis_residual_",
    # M2.2 F08 — sub-day funding microstructure: rolling skew/kurt of
    # daily funding_rate per subject (panel-grain analog of doc's 8h
    # funding skew). See alpha_ontology §H.3 M2.2 + §D F08.
    "funding_term_",
    # M2.3 F62 — settlement-cycle premium: pre-settlement-hour drift
    # (1h log return at UTC 23/7/15 minus other hours, rolling 60d) per
    # subject. See alpha_ontology §H.3 M2.3 + §E.10.
    "settlement_cycle_",
    # M2.4 F-triangle — Funding-OI-Basis 3-equation residual (rolling 60d
    # 2-regressor OLS: funding ~ α + β1*basis + β2*oi_change_5). See
    # alpha_ontology §H.3 M2.4 + §E.11. Doc E.11 falsification PASSES
    # but standalone G1/G6 admission FAILS — registered as plumbed but
    # not score-integrated.
    "triangle_residual_",
    "triangle_r2_",
    # SP-A liquidation cascade — per-subject 1h liq_to_oi z-score, daily
    # aggregated. Doc §E.12 falsification PASSES (t=+10.75 vs 2.5σ).
    # G6 strict PASS on all 4 variants; strongest variant
    # liq_cascade_recency_score_5d (G1 IC +0.052, G6 residual +0.062).
    # See data_utilization_roadmap.md SP-A.
    "liq_cascade_",
    # SP-B partial — 1h Coinglass microstructure swarm. B3a
    # (top_trader_velocity_1h_abs_24h) passes G6 strict standalone but is
    # +0.94 per-ts spearman with liq_cascade_recency_score_5d (sibling-
    # duplicate). B2 (top_global_disagreement) and B5 (taker_skew_presettle)
    # fail G1 + G6. Plumbed for future use (horizon scan / different baselines).
    # See data_utilization_roadmap.md SP-B.
    "top_global_disagreement_",
    "top_trader_velocity_",
    "taker_skew_",
    # SP-F sub-day funding microstructure — per-subject 4h-grain funding
    # rate sequence. F1 funding_intraday_dispersion_30d is the score-
    # admissible winner: G6 vs lsk3+F08 = +0.040 t=+7.24 at h10d. F2 (sign
    # flip count) and F3 (sub-day skew) plumbed but NOT score-integrated.
    # See data_utilization_roadmap.md SP-F.
    "funding_intraday_dispersion_",
    "funding_sign_flip_count_",
    "funding_term_skew_30d_4h",
    # SP-K small-cap post-pump short family. Event-state factors built from
    # abnormal upside pump intensity and subsequent continuation failure.
    "pump_exhaustion_",
    "pump_funding_oi_crowding_",
    "post_pump_stall_",
)
FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES = (
    "event__",
    "narrative__",
)
FEATURE_ADMISSION_ALLOWED_EXACT_COLUMNS = frozenset(
    {
        "range_position_20",
        "realized_volatility_5",
        "realized_volatility_20",
        "realized_volatility_60",
        "atr_proxy_20",
        "return_1",
        "quote_volume_expansion",
        "funding_rate",
        "funding_zscore_20",
        "basis_proxy",
        "basis_zscore_20",
        "oi_change_5",
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
        "momentum_decay_5_20",
        "quality_funding_oi",
        "liquidity_stress_qv_iv",
        "funding_crowding_basis",
        # B-batch alternative factor candidates (Phase 1b extension; IC validation pending)
        "stress_liq_conc_iv",
        "crowd_obi_abs_funding",
        "crowd_tt_signal",
        "disp_taker_imb_xs",
        "unwind_liq_dh",
        "crowd_basis_oi_signed",
        "crowd_abs_basis_oi",
        "stress_abs_basis_qv",
        "crowd_funding_obi_signed",
        "disagree_tt_retail",
        "unwind_liq_imb_xs",
        # Alpha Ontology W1.2 — MF-04 / MF-10 W1.1 factors that do not match any
        # admitted prefix. IC validation pending in W1.3 factor report cards.
        "basis_velocity_3d",
        "basis_velocity_3d_xs_z",
        "basis_carry_convexity_3d",
        "capitulation_amplification_event",
        "downside_upside_vol_ratio_30",
        "vol_of_vol_60",
        "abnormal_range_z_60",
        # Alpha Ontology W3.1 — MF-08 information shock & impulse response factors.
        # State-machine "days since last event" derivations (and one universe-wide
        # co-occurrence aggregation). All four are derived from existing daily panel
        # inputs; they do NOT use the event__/narrative__ excluded prefixes (which
        # are reserved for curated event-tape ingest).
        "vol_shock_impulse_phase",
        "funding_flip_decay_phase",
        "oi_shock_decay_phase",
        "shock_co_occurrence_index",
        # Alpha Ontology W3.2 — MF-09 co-jump & contagion network factors.
        # Cross-asset structural derivations: F26 universe shock cluster count,
        # F27 BTC-anchored lead-lag rolling beta, F28 BTC-stripped residual
        # cumulative strength, F29 per-subject co-jump exposure rolling mean.
        "co_jump_count_3d",
        "lead_lag_beta_btc",
        "lead_lag_residual_strength",
        "contagion_in_degree",
        # Alpha Ontology W3.3 — MF-11 liquidity migration & universe rotation.
        # F41 quote share change, F42 rank velocity, F44 dispersion (universe),
        # F45 idiosyncratic variance share (1 - R^2 vs BTC).
        "quote_share_change_30d",
        "universe_rank_velocity_10",
        "dispersion_of_returns",
        "idiosyncratic_share",
        # M3.2 Phase 2 stablecoin flow context. These are universe-wide
        # PIT-safe daily state variables merged onto the cross-sectional
        # panel by decision date and used only as interaction context in the
        # score layer, not as standalone per-subject alpha factors.
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
        # M3.3 / SP-K news-veto overlays. These are PIT-safe daily flags
        # derived from the curated research-effective event/news layer and
        # consumed only as boundary rules in score selection.
        "news_short_veto_mini_flag",
        "news_short_veto_adjudicated_flag",
        "news_short_veto_adjudicated_do_not_fill_multiplier",
        "news_short_veto_adjudicated_reduced_exposure_multiplier",
        "boundary_fragile_orderbook_score",
        "pump_bid_replenishment_failure_score",
        "mf01_short_boundary_combo_score",
        "boundary_fragile_orderbook_flag",
        "pump_bid_replenishment_failure_flag",
        "mf01_spk_confirmation_flag",
        "mf01_spk_confirmation_score",
        "mf01_spk_selected_short_veto_flag",
        "mf01_post_cascade_guardrail_flag",
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "m3_3_strict_event_state_q1_noise0_flag",
    }
)
FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_COLUMNS = frozenset(
    {
        "timestamp_ms",
        "open_time_ms",
        "close_time_ms",
        "daily_open_time_ms",
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "perp_close",
        "daily_close",
        "selection_rank",
        "selection_score",
        "rolling_median_quote_volume_usd_30d",
        "rolling_mean_quote_volume_usd_30d",
        "market_cap_rank",
        "market_cap_rank_inverse",
        "market_cap_usd",
        "listing_age_days",
        "listing_age_days_as_of",
        "ema_fast",
        "ema_slow",
        "sma_20",
        "sma_60",
        "spot_volume",
        "spot_quote_volume",
        "perp_volume",
        "perp_quote_volume_usd",
        "daily_quote_volume",
        "intraday_quote_volume_4h",
        "intraday_quote_volume_1d",
        "quote_volume_24h_usd",
        "open_interest",
        "open_interest_value",
        "funding_sample_count",
        "has_perp",
        "has_perp_as_of",
        "perp_executable_start_ms",
        "perp_execution_eligible",
        "event_flag_count",
        "narrative_tag_count",
    }
)


def build_feature_admission_policy() -> dict[str, Any]:
    return {
        "contract_version": FEATURE_ADMISSION_POLICY_VERSION,
        "mode": "strict_allowlist",
        "unknown_numeric_default": "reject",
        "generated_feature_columns_default": "reject",
        "allowed_feature_groups": list(FEATURE_ADMISSION_ALLOWED_GROUPS),
        "compatible_empty_feature_groups": list(FEATURE_ADMISSION_COMPATIBLE_EMPTY_GROUPS),
        "allowed_exact_columns": sorted(FEATURE_ADMISSION_ALLOWED_EXACT_COLUMNS),
        "allowed_prefixes": list(FEATURE_ADMISSION_ALLOWED_PREFIXES),
        "explicitly_excluded_columns": sorted(FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_COLUMNS),
    }


def classify_feature_manifest_columns(columns: Iterable[str]) -> dict[str, Any]:
    available_numeric_columns: list[str] = []
    numeric_feature_columns: list[str] = []
    excluded_numeric_columns: list[str] = []
    unknown_numeric_columns: list[str] = []
    seen: set[str] = set()
    for raw_column in columns:
        column = str(raw_column).strip()
        if not column or column in seen:
            continue
        seen.add(column)
        available_numeric_columns.append(column)
        status = feature_admission_status(column)
        if status == "admitted":
            numeric_feature_columns.append(column)
        else:
            excluded_numeric_columns.append(column)
            if status == "unknown":
                unknown_numeric_columns.append(column)
    return {
        "feature_admission_policy": build_feature_admission_policy(),
        "available_numeric_columns": sorted(available_numeric_columns),
        "numeric_feature_columns": sorted(numeric_feature_columns),
        "excluded_numeric_columns": sorted(excluded_numeric_columns),
        "unknown_numeric_columns": sorted(unknown_numeric_columns),
    }


def build_feature_admission_section(
    *,
    feature_admission_policy: dict[str, Any] | None,
    available_numeric_columns: Iterable[str],
    numeric_feature_columns: Iterable[str],
    excluded_numeric_columns: Iterable[str],
    selected_feature_columns: Iterable[str],
    generated_feature_columns: Iterable[str] | None = None,
    selected_feature_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_policy = dict(feature_admission_policy or {})
    available = _normalized_unique_columns(available_numeric_columns)
    admitted = _normalized_unique_columns(numeric_feature_columns)
    excluded = _normalized_unique_columns(excluded_numeric_columns)
    selected = _normalized_unique_columns(selected_feature_columns)
    generated = _normalized_unique_columns(generated_feature_columns or [])
    resolved_selected_feature_quality = dict(selected_feature_quality or {})
    selected_quality_features = dict(resolved_selected_feature_quality.get("features") or {})
    admitted_set = set(admitted)
    banned_proxy_columns_present = [
        column
        for column in selected
        if feature_admission_status(column) == "explicitly_excluded"
    ]
    unknown_numeric_columns_present = [
        column
        for column in selected
        if feature_admission_status(column) == "unknown" or column in generated
    ]
    selected_feature_columns_outside_manifest = [
        column for column in selected if column not in admitted_set
    ]
    selected_feature_columns_missing_quality = [
        column for column in selected if column not in selected_quality_features
    ]
    selected_feature_columns_not_fully_sourced = [
        column
        for column in selected
        if column in selected_quality_features
        and (
            selected_quality_features[column].get("row_source_fraction") is None
            or float(selected_quality_features[column].get("row_source_fraction") or 0.0) < 1.0
        )
    ]
    selected_feature_columns_not_fully_ready = [
        column
        for column in selected
        if column in selected_quality_features
        and (
            selected_quality_features[column].get("row_ready_fraction") is None
            or float(selected_quality_features[column].get("row_ready_fraction") or 0.0) < 1.0
        )
    ]
    passed = (
        bool(resolved_policy)
        and bool(selected)
        and not banned_proxy_columns_present
        and not unknown_numeric_columns_present
        and not selected_feature_columns_outside_manifest
    )
    return {
        "feature_admission_policy": resolved_policy,
        "available_numeric_columns": available,
        "numeric_feature_columns": admitted,
        "selected_feature_columns": selected,
        "excluded_feature_columns": sorted(dict.fromkeys(excluded + generated)),
        "banned_proxy_columns_present": banned_proxy_columns_present,
        "unknown_numeric_columns_present": unknown_numeric_columns_present,
        "selected_feature_columns_outside_manifest": selected_feature_columns_outside_manifest,
        "selected_feature_quality": resolved_selected_feature_quality,
        "selected_feature_columns_missing_quality": selected_feature_columns_missing_quality,
        "selected_feature_columns_not_fully_sourced": selected_feature_columns_not_fully_sourced,
        "selected_feature_columns_not_fully_ready": selected_feature_columns_not_fully_ready,
        "passed": passed,
    }


def feature_admission_status(column: str) -> str:
    normalized = str(column or "").strip()
    if not normalized:
        return "unknown"
    if normalized in FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_COLUMNS:
        return "explicitly_excluded"
    if any(normalized.startswith(prefix) for prefix in FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES):
        return "explicitly_excluded"
    if normalized in FEATURE_ADMISSION_ALLOWED_EXACT_COLUMNS:
        return "admitted"
    if any(normalized.startswith(prefix) for prefix in FEATURE_ADMISSION_ALLOWED_PREFIXES):
        return "admitted"
    return "unknown"


def is_model_admissible_numeric_column(column: str) -> bool:
    return feature_admission_status(column) == "admitted"


def _normalized_unique_columns(columns: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_column in columns:
        column = str(raw_column).strip()
        if not column or column in seen:
            continue
        seen.add(column)
        normalized.append(column)
    return sorted(normalized)
