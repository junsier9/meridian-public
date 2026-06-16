"""Portfolio-level position multiplier from external implied-vol regime signals.

Provides a callable mapping decision-timestamp_ms -> position multiplier in
[0.2, 1.0]. Used by backtest_cross_sectional when a manifest entry's
profile_constraints declares a `position_multiplier_overlay_id` that resolves
to a registered overlay.

m7 overlay (`btc_eth_max_iv_aggressive_tanh_v1`):
    z = max(btc_dvol_z90, eth_dvol_z90)    # 90-day rolling z of daily DVOL close
    multiplier = clip(1 - tanh((z - 0.5) * 3), 0.2, 1.0)

Source data: BTC + ETH DVOL daily history synced via
    scripts/quant_research/sync_deribit_dvol_history.py
into artifacts/external_market_data/deribit_dvol/{btc,eth}_dvol_daily.csv.

Selection evidence: spike script + 10-multiplier comparison (2026-04-28),
artifacts/quant_research/shadow_oos/btc_options_spike_2026-04-26.json.
Forward-test delta worst-quarter sharpe = +0.664 (in-sample STRONG).
Reverse-test confirmed multiplier idles in calm regime (no harm).

Registry interface lets manifests pin a specific overlay id without
plumbing extra arguments through the backtest signature.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .contracts import resolve_portable_path

ROOT = Path(__file__).resolve().parents[3]
DVOL_DIR = ROOT / "artifacts" / "external_market_data" / "deribit_dvol"

MULTIPLIER_OVERLAY_CONTRACT_VERSION = "quant_position_multiplier_overlay.v1"

# m7 hyperparameters (selected from spike's 10-multiplier comparison, 2026-04-28)
ROLLING_Z_WINDOW = 90
MULTIPLIER_FLOOR = 0.2
MULTIPLIER_CEIL = 1.0
MULTIPLIER_TANH_SLOPE = 3.0
MULTIPLIER_THRESHOLD_Z = 0.5


def _load_dvol_panel() -> pd.DataFrame:
    btc_path = DVOL_DIR / "btc_dvol_daily.csv"
    eth_path = DVOL_DIR / "eth_dvol_daily.csv"
    if not btc_path.exists() or not eth_path.exists():
        raise FileNotFoundError(
            f"DVOL CSVs not found under {DVOL_DIR}. "
            "Run scripts/quant_research/sync_deribit_dvol_history.py to materialize them."
        )
    btc = pd.read_csv(btc_path)[["date_utc", "dvol_close"]].rename(columns={"dvol_close": "btc_dvol"})
    eth = pd.read_csv(eth_path)[["date_utc", "dvol_close"]].rename(columns={"dvol_close": "eth_dvol"})
    return btc.merge(eth, on="date_utc", how="outer").sort_values("date_utc").reset_index(drop=True)


def _compute_btc_eth_max_iv_aggressive_tanh_v1(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Compute the m7 overlay multiplier indexed by ISO date string.

    Dates without a valid z-score (insufficient 90-day warmup) are omitted;
    lookups fall back to multiplier=1.0 (no throttle) for missing dates.
    """
    df = _load_dvol_panel()
    btc = df["btc_dvol"]
    eth = df["eth_dvol"]
    df["btc_z90"] = (btc - btc.rolling(ROLLING_Z_WINDOW).mean()) / btc.rolling(ROLLING_Z_WINDOW).std()
    df["eth_z90"] = (eth - eth.rolling(ROLLING_Z_WINDOW).mean()) / eth.rolling(ROLLING_Z_WINDOW).std()
    df["max_iv_z90"] = df[["btc_z90", "eth_z90"]].max(axis=1)
    series = df.dropna(subset=["max_iv_z90"]).set_index("date_utc")["max_iv_z90"]

    out: dict[str, float] = {}
    for date_str, z in series.items():
        if pd.isna(z):
            continue
        mul = 1.0 - math.tanh((float(z) - MULTIPLIER_THRESHOLD_Z) * MULTIPLIER_TANH_SLOPE)
        mul = max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, mul))
        out[str(date_str)] = float(mul)
    return out


def _compute_btc_only_aggressive_tanh_v1(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """m5 variant from spike: BTC DVOL z90 only (no ETH), aggressive tanh
    threshold 0.5 slope 3 floor 0.2. Tests whether removing ETH dimension
    yields more robust production trade-off (spike showed m5 +0.54 vs m7 +0.66
    worst-quarter delta in-sample; production v97 with m7 gave only +0.24 worst
    regime delta — possible over-fit suggests simpler m5 variant).
    """
    df = _load_dvol_panel()
    btc = df["btc_dvol"]
    df["btc_z90"] = (btc - btc.rolling(ROLLING_Z_WINDOW).mean()) / btc.rolling(ROLLING_Z_WINDOW).std()
    series = df.dropna(subset=["btc_z90"]).set_index("date_utc")["btc_z90"]
    out: dict[str, float] = {}
    for date_str, z in series.items():
        if pd.isna(z):
            continue
        mul = 1.0 - math.tanh((float(z) - MULTIPLIER_THRESHOLD_Z) * MULTIPLIER_TANH_SLOPE)
        mul = max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, mul))
        out[str(date_str)] = float(mul)
    return out


def _resolve_overlay_features_artifact(overlay_context: dict[str, Any] | None = None) -> Path | None:
    context = dict(overlay_context or {})
    features_path = str(context.get("features_path") or "").strip()
    if features_path:
        return resolve_portable_path(features_path, repo_root=ROOT)
    feature_manifest_path = str(context.get("feature_manifest_path") or "").strip()
    if feature_manifest_path:
        manifest_path = resolve_portable_path(feature_manifest_path, repo_root=ROOT)
        sibling_features_path = manifest_path.with_name("features.csv.gz")
        if sibling_features_path.exists():
            return sibling_features_path
    return None


def _compute_alpha_ontology_regime_gating_v1_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Lazy wrapper: import regime_gating only at first call to avoid a hard
    import-time dependency on the cross-sectional features panel.
    """
    from .regime_gating import _compute_alpha_ontology_regime_gating_v1
    return _compute_alpha_ontology_regime_gating_v1(
        features_artifact=_resolve_overlay_features_artifact(overlay_context)
    )


def _compute_alpha_ontology_regime_gating_v2_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """v2 builder: v1 components + F55 BTC vol regime quantile + trailing
    universe mean return."""
    from .regime_gating import _compute_alpha_ontology_regime_gating_v2
    return _compute_alpha_ontology_regime_gating_v2(
        features_artifact=_resolve_overlay_features_artifact(overlay_context)
    )


def _compute_alpha_ontology_regime_gating_v3_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """v3 builder: v2 components + DVOL range z90 throttle (BTC + ETH).

    SP-G G2 component: when btc_dvol_range_z90 or eth_dvol_range_z90 enters
    vol-of-vol regime (z>1.5), throttle harder. SP-E correlation regime
    gate (doc §E.17) was DROPPED — empirically falsified per
    threshold_provenance.md SP-E section.
    """
    from .regime_gating import _compute_alpha_ontology_regime_gating_v3
    return _compute_alpha_ontology_regime_gating_v3(
        features_artifact=_resolve_overlay_features_artifact(overlay_context)
    )


def _compute_stablecoin_issuance_velocity_overlay_v1_lazy(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """M3.2 overlay builder from prior-day stablecoin issuance / velocity."""
    from .stablecoin_regime import compute_stablecoin_issuance_velocity_overlay_v1
    return compute_stablecoin_issuance_velocity_overlay_v1()


def _compute_stablecoin_issuance_velocity_overlay_v2_lazy(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """M3.2 overlay v2: default-open, contraction-only throttle."""
    from .stablecoin_regime import compute_stablecoin_issuance_velocity_overlay_v2
    return compute_stablecoin_issuance_velocity_overlay_v2()


def _compute_stablecoin_exchange_absorption_overlay_v1_lazy(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """M3.2 Phase 2 overlay: stablecoin exchange absorption / drain state."""
    from .stablecoin_regime import compute_stablecoin_exchange_absorption_overlay_v1
    return compute_stablecoin_exchange_absorption_overlay_v1()


def _compute_stablecoin_whale_to_exchange_stress_overlay_v1_lazy(
    _overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """M3.2 Phase 2 overlay: whale-to-exchange stress throttle."""
    from .stablecoin_regime import compute_stablecoin_whale_to_exchange_stress_overlay_v1
    return compute_stablecoin_whale_to_exchange_stress_overlay_v1()


def _compute_alpha_ontology_regime_gating_v2_mf14_sell_pressure_v1_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Stack MF-14 sell-pressure throttle on top of W3.5 v2 regime gating."""
    from .onchain_m3_2_features import compute_mf14_sell_pressure_overlay_component_v1

    base = _compute_alpha_ontology_regime_gating_v2_lazy(overlay_context)
    mf14 = compute_mf14_sell_pressure_overlay_component_v1()
    return _combine_overlay_tables_min(base, mf14)


def _compute_alpha_ontology_regime_gating_v2_mf14_rebound_release_v1_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Allow partial release of W3.5 v2 throttle during MF-14 rebound states."""
    from .onchain_m3_2_features import compute_mf14_rebound_release_floor_v1

    base = _compute_alpha_ontology_regime_gating_v2_lazy(overlay_context)
    mf14 = compute_mf14_rebound_release_floor_v1()
    return _combine_overlay_tables_max(base, mf14, inactive_floor=0.0)


def _compute_alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1_lazy(
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Stack TRON USDT flow-impulse throttle on top of W3.5 v2 regime gating."""
    from .onchain_m3_2_features import compute_mf13_tron_flow_impulse_overlay_component_v1

    base = _compute_alpha_ontology_regime_gating_v2_lazy(overlay_context)
    mf13 = compute_mf13_tron_flow_impulse_overlay_component_v1()
    return _combine_overlay_tables_min(base, mf13)


OVERLAY_BUILDERS: dict[str, Callable[[dict[str, Any] | None], dict[str, float]]] = {
    "btc_eth_max_iv_aggressive_tanh_v1": _compute_btc_eth_max_iv_aggressive_tanh_v1,
    "btc_only_aggressive_tanh_v1":       _compute_btc_only_aggressive_tanh_v1,
    # Alpha Ontology W3.5 — universe-wide regime-aware multiplier from
    # F49 (shock fraction) + F26 (3-day cluster count) + F44 (return
    # dispersion). See src/enhengclaw/quant_research/regime_gating.py
    # for builder body and hyperparameters.
    "alpha_ontology_regime_gating_v1":   _compute_alpha_ontology_regime_gating_v1_lazy,
    # W3.5 v2: v1 components + F55 BTC vol regime quantile + trailing
    # universe mean return. Targets sustained-vol / slow-grind regimes
    # that shock-based v1 components miss.
    "alpha_ontology_regime_gating_v2":   _compute_alpha_ontology_regime_gating_v2_lazy,
    # W3.5 v3 (SP-G): v2 components + DVOL range z90 throttle (BTC + ETH).
    # Adds vol-of-vol regime detection from Deribit DVOL OHLC. SP-E
    # correlation regime gate was DROPPED (empirically falsified).
    "alpha_ontology_regime_gating_v3":   _compute_alpha_ontology_regime_gating_v3_lazy,
    "alpha_ontology_regime_gating_v2_mf14_sell_pressure_v1":
        _compute_alpha_ontology_regime_gating_v2_mf14_sell_pressure_v1_lazy,
    "alpha_ontology_regime_gating_v2_mf14_rebound_release_v1":
        _compute_alpha_ontology_regime_gating_v2_mf14_rebound_release_v1_lazy,
    "alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1":
        _compute_alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1_lazy,
    "stablecoin_issuance_velocity_overlay_v1": _compute_stablecoin_issuance_velocity_overlay_v1_lazy,
    "stablecoin_issuance_velocity_overlay_v2": _compute_stablecoin_issuance_velocity_overlay_v2_lazy,
    "stablecoin_exchange_absorption_overlay_v1": _compute_stablecoin_exchange_absorption_overlay_v1_lazy,
    "stablecoin_whale_to_exchange_stress_overlay_v1": _compute_stablecoin_whale_to_exchange_stress_overlay_v1_lazy,
}

_LOOKUP_CACHE: dict[tuple[str, str, str, str], Callable[[int], float]] = {}


def _combine_overlay_tables_min(
    base_table: dict[str, float],
    component_table: dict[str, float],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for date_utc in sorted(set(base_table) | set(component_table)):
        base_value = float(base_table.get(date_utc, 1.0))
        component_value = float(component_table.get(date_utc, 1.0))
        out[date_utc] = min(base_value, component_value)
    return out


def _combine_overlay_tables_max(
    base_table: dict[str, float],
    component_table: dict[str, float],
    *,
    inactive_floor: float,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for date_utc in sorted(set(base_table) | set(component_table)):
        base_value = float(base_table.get(date_utc, 1.0))
        component_value = float(component_table.get(date_utc, inactive_floor))
        if component_value <= inactive_floor + 1e-12:
            out[date_utc] = base_value
        else:
            out[date_utc] = max(base_value, component_value)
    return out


def _overlay_cache_key(
    overlay_id: str,
    overlay_context: dict[str, Any] | None = None,
) -> tuple[str, str, str, str]:
    context = dict(overlay_context or {})
    return (
        overlay_id,
        str(context.get("features_path") or "").strip(),
        str(context.get("feature_manifest_path") or "").strip(),
        str(context.get("universe_snapshot_path") or "").strip(),
    )


def _make_lookup_for_overlay(
    overlay_id: str,
    overlay_context: dict[str, Any] | None = None,
) -> Callable[[int], float]:
    if overlay_id not in OVERLAY_BUILDERS:
        raise KeyError(
            f"unknown position_multiplier_overlay_id: {overlay_id!r}. "
            f"Registered: {sorted(OVERLAY_BUILDERS)}"
        )
    table = OVERLAY_BUILDERS[overlay_id](dict(overlay_context or {}))

    def _lookup(timestamp_ms: int) -> float:
        decision_date = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc).date().isoformat()
        return table.get(decision_date, 1.0)

    _lookup.__doc__ = f"Position multiplier lookup for overlay '{overlay_id}'"
    return _lookup


def position_multiplier_lookup(
    overlay_id: str | None,
    *,
    overlay_context: dict[str, Any] | None = None,
) -> Callable[[int], float] | None:
    """Public: return a cached timestamp_ms->multiplier callable, or None if overlay_id is falsy.

    Cache is process-wide so repeated backtest invocations reuse the same compiled table.
    """
    if not overlay_id:
        return None
    cache_key = _overlay_cache_key(overlay_id, overlay_context)
    if cache_key not in _LOOKUP_CACHE:
        _LOOKUP_CACHE[cache_key] = _make_lookup_for_overlay(overlay_id, overlay_context)
    return _LOOKUP_CACHE[cache_key]


def overlay_table_for_id(
    overlay_id: str,
    *,
    overlay_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    if overlay_id not in OVERLAY_BUILDERS:
        raise KeyError(
            f"unknown position_multiplier_overlay_id: {overlay_id!r}. "
            f"Registered: {sorted(OVERLAY_BUILDERS)}"
        )
    return OVERLAY_BUILDERS[overlay_id](dict(overlay_context or {}))


def list_registered_overlays() -> list[str]:
    return sorted(OVERLAY_BUILDERS)


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Inspect a registered position multiplier overlay.")
    parser.add_argument(
        "--overlay-id", default="btc_eth_max_iv_aggressive_tanh_v1",
        help="Registered overlay id (default: btc_eth_max_iv_aggressive_tanh_v1).",
    )
    parser.add_argument(
        "--probe-dates", default="2024-01-15,2024-08-05,2025-04-15,2025-09-01,2026-02-15,2026-04-15",
        help="Comma-separated YYYY-MM-DD dates to probe.",
    )
    args = parser.parse_args()

    print(f"Registered overlays: {list_registered_overlays()}")
    lookup = position_multiplier_lookup(args.overlay_id)
    if lookup is None:
        print("None overlay id -> no lookup")
        return 0

    print(f"\nProbing overlay '{args.overlay_id}':")
    print(f"  {'date':<12s} {'multiplier':>12s} {'throttle?':>10s}")
    for date_str in [d.strip() for d in args.probe_dates.split(",") if d.strip()]:
        ts_ms = int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        mul = lookup(ts_ms)
        marker = "no" if mul >= 0.99 else f"x{mul:.2f}"
        print(f"  {date_str:<12s} {mul:>12.4f} {marker:>10s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
