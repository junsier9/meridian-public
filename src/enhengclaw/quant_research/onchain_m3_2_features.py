from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .onchain_cryptoquant import resolve_onchain_cryptoquant_external_root
from .onchain_stablecoin import resolve_onchain_external_root
from .onchain_stablecoin_tron import resolve_onchain_tron_external_root
from .stablecoin_regime import build_stablecoin_regime_panel


ROOT = Path(__file__).resolve().parents[3]
M3_2_FEATURE_PANEL_CONTRACT_VERSION = "quant_m3_2_feature_panel.v1"
DEFAULT_OUT_PATH = ROOT / "artifacts" / "quant_research" / "onchain" / "m3_2_feature_panel_1d.csv"
M3_2_MF14_OVERLAY_CONTRACT_VERSION = "quant_m3_2_mf14_overlay.v1"
DEFAULT_MF14_SELL_PRESSURE_OVERLAY_ID = "alpha_ontology_regime_gating_v2_mf14_sell_pressure_v1"
DEFAULT_MF14_REBOUND_RELEASE_OVERLAY_ID = "alpha_ontology_regime_gating_v2_mf14_rebound_release_v1"
DEFAULT_MF13_TRON_FLOW_IMPULSE_OVERLAY_ID = "alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1"
_ROLLING_Z_WINDOW = 14
_MIN_PERIODS = 5
_MF14_CONFIRM_THRESHOLD = 0.75
_MF14_HARD_THRESHOLD = 1.25
_MF14_SELL_PRESSURE_CONFIRM_MULTIPLIER = 0.90
_MF14_SELL_PRESSURE_HARD_MULTIPLIER = 0.75
_MF14_REBOUND_CONFIRM_RELEASE_FLOOR = 0.95
_MF14_REBOUND_HARD_RELEASE_FLOOR = 1.00
_MF13_TRON_CONFIRM_THRESHOLD = 1.00
_MF13_TRON_HARD_THRESHOLD = 1.35
_MF13_TRON_CONFIRM_MULTIPLIER = 0.90
_MF13_TRON_HARD_MULTIPLIER = 0.75


def load_cryptoquant_supply_daily(
    external_root: Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    path = root / "stablecoin_supply_daily.csv"
    return _load_required_csv(path, "CryptoQuant stablecoin supply CSV")


def load_cryptoquant_stablecoin_exchange_flows_daily(
    external_root: Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    path = root / "stablecoin_exchange_flows_daily.csv"
    return _load_required_csv(path, "CryptoQuant stablecoin exchange-flow CSV")


def load_cryptoquant_reflexivity_exchange_flows_daily(
    external_root: Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    path = root / "reflexivity_exchange_flows_daily.csv"
    return _load_required_csv(path, "CryptoQuant reflexivity exchange-flow CSV")


def load_cryptoquant_reflexivity_market_indicators_daily(
    external_root: Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    path = root / "reflexivity_market_indicators_daily.csv"
    return _load_required_csv(path, "CryptoQuant reflexivity market-indicator CSV")


def load_tronscan_stablecoin_daily(
    external_root: Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_tron_external_root(external_root=external_root)
    path = root / "daily_aggregates.csv"
    return _load_required_csv(path, "TRON stablecoin daily aggregate CSV")


def build_m3_2_feature_panel(
    *,
    stablecoin_external_root: Path | None = None,
    cryptoquant_external_root: Path | None = None,
    tron_external_root: Path | None = None,
) -> pd.DataFrame:
    alchemy = build_stablecoin_regime_panel(external_root=stablecoin_external_root)
    if alchemy.empty:
        raise RuntimeError("Alchemy stablecoin regime panel is empty")

    supply_raw, _ = load_cryptoquant_supply_daily(external_root=cryptoquant_external_root)
    stable_flow_raw, _ = load_cryptoquant_stablecoin_exchange_flows_daily(
        external_root=cryptoquant_external_root
    )
    reflex_flow_raw, _ = load_cryptoquant_reflexivity_exchange_flows_daily(
        external_root=cryptoquant_external_root
    )
    reflex_market_raw, _ = load_cryptoquant_reflexivity_market_indicators_daily(
        external_root=cryptoquant_external_root
    )
    tron_panel = pd.DataFrame(columns=["date_utc"])
    try:
        tron_raw, _tron_path = load_tronscan_stablecoin_daily(external_root=tron_external_root)
    except FileNotFoundError:
        tron_raw = pd.DataFrame()
    else:
        tron_panel = _aggregate_tronscan_stablecoin_daily(tron_raw)

    alchemy_panel = _prepare_alchemy_panel(alchemy)
    supply_panel = _aggregate_cryptoquant_supply(supply_raw)
    stable_flow_panel = _aggregate_cryptoquant_stablecoin_exchange_flows(stable_flow_raw)
    reflex_flow_panel = _aggregate_cryptoquant_reflexivity_exchange_flows(reflex_flow_raw)
    reflex_market_panel = _aggregate_cryptoquant_reflexivity_market_indicators(reflex_market_raw)
    panel = _build_date_spine(
        [
            alchemy_panel[["date_utc"]],
            supply_panel[["date_utc"]],
            stable_flow_panel[["date_utc"]],
            reflex_flow_panel[["date_utc"]],
            reflex_market_panel[["date_utc"]],
            tron_panel[["date_utc"]],
        ]
    )

    panel = panel.merge(alchemy_panel.drop(columns=["decision_date_utc"], errors="ignore"), on="date_utc", how="left")
    panel = panel.merge(stable_flow_panel, on="date_utc", how="left")
    panel = panel.merge(reflex_flow_panel, on="date_utc", how="left")
    panel = panel.merge(reflex_market_panel, on="date_utc", how="left")
    panel = panel.merge(supply_panel, on="date_utc", how="left")
    panel = panel.merge(tron_panel, on="date_utc", how="left")
    panel = panel.sort_values("date_utc").reset_index(drop=True)

    _derive_fused_columns(panel)
    return panel


def write_m3_2_feature_panel(
    panel: pd.DataFrame,
    *,
    output_path: Path = DEFAULT_OUT_PATH,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False)
    return output_path


def summarize_m3_2_feature_panel(
    panel: pd.DataFrame,
    *,
    stablecoin_external_root: Path | None = None,
    cryptoquant_external_root: Path | None = None,
    tron_external_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": M3_2_FEATURE_PANEL_CONTRACT_VERSION,
        "row_count": int(panel.shape[0]),
        "column_count": int(panel.shape[1]),
        "start_date_utc": str(panel["date_utc"].min()) if not panel.empty else None,
        "end_date_utc": str(panel["date_utc"].max()) if not panel.empty else None,
        "decision_start_date_utc": str(panel["decision_date_utc"].min()) if not panel.empty else None,
        "decision_end_date_utc": str(panel["decision_date_utc"].max()) if not panel.empty else None,
        "alchemy_external_root": str(resolve_onchain_external_root(external_root=stablecoin_external_root)),
        "cryptoquant_external_root": str(
            resolve_onchain_cryptoquant_external_root(external_root=cryptoquant_external_root)
        ),
        "tron_external_root": str(resolve_onchain_tron_external_root(external_root=tron_external_root)),
        "output_path": str(output_path) if output_path is not None else None,
        "coverage": {
            "alchemy_signal_ready_days": int(
                pd.to_numeric(panel["alchemy_signal_ready"], errors="coerce").fillna(0).sum()
            ),
            "m3_2_panel_ready_days": int(
                pd.to_numeric(panel["m3_2_panel_ready"], errors="coerce").fillna(0).sum()
            ),
            "cryptoquant_supply_days": int(panel["cq_supply_circulating"].notna().sum())
            if "cq_supply_circulating" in panel.columns
            else 0,
            "cryptoquant_btc_reflexivity_days": int(panel["cq_btc_sopr"].notna().sum())
            if "cq_btc_sopr" in panel.columns
            else 0,
            "tronscan_tron_flow_days": int(panel["tronscan_transfer_count"].notna().sum())
            if "tronscan_transfer_count" in panel.columns
            else 0,
        },
        "latest_row_preview": panel.tail(1).to_dict(orient="records")[0] if not panel.empty else None,
    }


def load_m3_2_feature_panel(panel_path: Path = DEFAULT_OUT_PATH) -> pd.DataFrame:
    if not panel_path.exists():
        raise FileNotFoundError(
            f"M3.2 feature panel not found at {panel_path}. "
            "Run scripts/quant_research/build_m3_2_feature_panel.py first."
        )
    panel = pd.read_csv(panel_path)
    if panel.empty:
        raise RuntimeError(f"M3.2 feature panel is empty: {panel_path}")
    return panel


def build_m3_2_mf14_overlay_component_panel(
    panel: pd.DataFrame | None = None,
    *,
    panel_path: Path = DEFAULT_OUT_PATH,
) -> pd.DataFrame:
    source = load_m3_2_feature_panel(panel_path=panel_path) if panel is None else panel.copy()
    required_columns = [
        "date_utc",
        "decision_date_utc",
        "m3_2_panel_ready",
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
    ]
    missing = [column for column in required_columns if column not in source.columns]
    if missing:
        raise RuntimeError(f"M3.2 feature panel missing MF14 overlay columns: {missing}")

    frame = source[required_columns].copy()
    frame["m3_2_panel_ready"] = _as_bool(frame["m3_2_panel_ready"])
    sell_state = pd.to_numeric(frame["m3_2_btc_sell_pressure_state"], errors="coerce")
    rebound_state = pd.to_numeric(frame["m3_2_reflexive_rebound_state"], errors="coerce")

    sell_component = np.where(
        sell_state > _MF14_HARD_THRESHOLD,
        _MF14_SELL_PRESSURE_HARD_MULTIPLIER,
        np.where(
            sell_state > _MF14_CONFIRM_THRESHOLD,
            _MF14_SELL_PRESSURE_CONFIRM_MULTIPLIER,
            1.0,
        ),
    )
    rebound_release_floor = np.where(
        rebound_state > _MF14_HARD_THRESHOLD,
        _MF14_REBOUND_HARD_RELEASE_FLOOR,
        np.where(
            rebound_state > _MF14_CONFIRM_THRESHOLD,
            _MF14_REBOUND_CONFIRM_RELEASE_FLOOR,
            0.0,
        ),
    )

    frame["mf14_sell_pressure_overlay_component_v1"] = np.where(
        frame["m3_2_panel_ready"],
        sell_component,
        np.nan,
    )
    frame["mf14_rebound_release_floor_v1"] = np.where(
        frame["m3_2_panel_ready"],
        rebound_release_floor,
        np.nan,
    )
    return frame.sort_values("decision_date_utc").reset_index(drop=True)


def compute_mf14_sell_pressure_overlay_component_v1(
    panel: pd.DataFrame | None = None,
    *,
    panel_path: Path = DEFAULT_OUT_PATH,
) -> dict[str, float]:
    frame = build_m3_2_mf14_overlay_component_panel(panel=panel, panel_path=panel_path)
    ready = frame[frame["m3_2_panel_ready"] & frame["mf14_sell_pressure_overlay_component_v1"].notna()].copy()
    return {
        str(row["decision_date_utc"]): float(row["mf14_sell_pressure_overlay_component_v1"])
        for _, row in ready.iterrows()
    }


def compute_mf14_rebound_release_floor_v1(
    panel: pd.DataFrame | None = None,
    *,
    panel_path: Path = DEFAULT_OUT_PATH,
) -> dict[str, float]:
    frame = build_m3_2_mf14_overlay_component_panel(panel=panel, panel_path=panel_path)
    ready = frame[frame["m3_2_panel_ready"] & frame["mf14_rebound_release_floor_v1"].notna()].copy()
    return {
        str(row["decision_date_utc"]): float(row["mf14_rebound_release_floor_v1"])
        for _, row in ready.iterrows()
    }


def compute_mf13_tron_flow_impulse_overlay_component_v1(
    panel: pd.DataFrame | None = None,
    *,
    panel_path: Path = DEFAULT_OUT_PATH,
) -> dict[str, float]:
    source = load_m3_2_feature_panel(panel_path=panel_path) if panel is None else panel.copy()
    required_columns = [
        "decision_date_utc",
        "m3_2_panel_ready",
        "m3_2_tron_flow_impulse_state",
    ]
    missing = [column for column in required_columns if column not in source.columns]
    if missing:
        raise RuntimeError(f"M3.2 feature panel missing MF13 TRON overlay columns: {missing}")

    ready_mask = _as_bool(source["m3_2_panel_ready"])
    state = pd.to_numeric(source["m3_2_tron_flow_impulse_state"], errors="coerce")
    component = np.where(
        state > _MF13_TRON_HARD_THRESHOLD,
        _MF13_TRON_HARD_MULTIPLIER,
        np.where(
            state > _MF13_TRON_CONFIRM_THRESHOLD,
            _MF13_TRON_CONFIRM_MULTIPLIER,
            1.0,
        ),
    )
    frame = source.loc[ready_mask, ["decision_date_utc"]].copy()
    frame["mf13_tron_flow_impulse_overlay_component_v1"] = pd.Series(
        component,
        index=source.index,
        dtype="float64",
    ).loc[ready_mask].values
    return {
        str(row["decision_date_utc"]): float(row["mf13_tron_flow_impulse_overlay_component_v1"])
        for _, row in frame.iterrows()
    }


def summarize_m3_2_mf14_overlay_components(
    panel: pd.DataFrame | None = None,
    *,
    panel_path: Path = DEFAULT_OUT_PATH,
) -> dict[str, Any]:
    frame = build_m3_2_mf14_overlay_component_panel(panel=panel, panel_path=panel_path)
    ready = frame[frame["m3_2_panel_ready"]].copy()
    if ready.empty:
        return {
            "available": False,
            "contract_version": M3_2_MF14_OVERLAY_CONTRACT_VERSION,
            "reason": "no ready M3.2 panel rows available",
            "panel_path": str(panel_path),
        }
    sell = pd.to_numeric(ready["mf14_sell_pressure_overlay_component_v1"], errors="coerce")
    rebound = pd.to_numeric(ready["mf14_rebound_release_floor_v1"], errors="coerce")
    return {
        "available": True,
        "contract_version": M3_2_MF14_OVERLAY_CONTRACT_VERSION,
        "panel_path": str(panel_path),
        "decision_start_date_utc": str(ready["decision_date_utc"].min()),
        "decision_end_date_utc": str(ready["decision_date_utc"].max()),
        "ready_day_count": int(ready.shape[0]),
        "sell_pressure_component_distribution": {
            "full_size_fraction": float((sell >= 0.999).mean()),
            "soft_throttle_fraction": float((sell == _MF14_SELL_PRESSURE_CONFIRM_MULTIPLIER).mean()),
            "hard_throttle_fraction": float((sell == _MF14_SELL_PRESSURE_HARD_MULTIPLIER).mean()),
        },
        "rebound_release_distribution": {
            "inactive_fraction": float((rebound <= 1e-9).mean()),
            "soft_release_fraction": float((rebound == _MF14_REBOUND_CONFIRM_RELEASE_FLOOR).mean()),
            "full_release_fraction": float((rebound == _MF14_REBOUND_HARD_RELEASE_FLOOR).mean()),
        },
        "preview_rows": ready.tail(5)[
            [
                "date_utc",
                "decision_date_utc",
                "m3_2_btc_sell_pressure_state",
                "m3_2_reflexive_rebound_state",
                "mf14_sell_pressure_overlay_component_v1",
                "mf14_rebound_release_floor_v1",
            ]
        ].to_dict(orient="records"),
    }


def _load_required_csv(path: Path, label: str) -> tuple[pd.DataFrame, Path]:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found at {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"{label} is empty: {path}")
    return df, path


def _prepare_alchemy_panel(alchemy: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "date_utc",
        "decision_date_utc",
        "tracked_token_count",
        "total_transfer_amount",
        "total_net_issuance_amount",
        "total_exchange_netflow_amount",
        "total_whale_to_exchange_amount",
        "total_issuer_to_exchange_amount",
        "issuance_ratio",
        "velocity_log",
        "labeled_coverage_ratio",
        "exchange_netflow_ratio",
        "whale_to_exchange_ratio",
        "issuer_to_exchange_ratio",
        "issuance_ratio_z14",
        "velocity_log_z14",
        "exchange_netflow_ratio_z14",
        "whale_to_exchange_ratio_z14",
        "issuer_to_exchange_ratio_z14",
        "exchange_absorption_score_v1",
        "whale_exchange_stress_score_v1",
        "signal_ready",
    ]
    keep = [column for column in columns if column in alchemy.columns]
    panel = alchemy[keep].copy()
    rename_map = {
        column: f"alchemy_{column}"
        for column in panel.columns
        if column not in {"date_utc", "decision_date_utc"}
    }
    panel = panel.rename(columns=rename_map)
    panel["alchemy_signal_ready"] = _as_bool(panel["alchemy_signal_ready"])
    return panel


def _aggregate_tronscan_stablecoin_daily(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    numeric_columns = [
        "transfer_count",
        "transfer_amount",
        "transfer_amount_usd",
        "from_count",
        "to_count",
        "active_address_count",
        "holders_count",
        "stats_usdt_transaction_count",
        "stats_active_account_number",
        "stats_total_transaction_count",
        "transfer_count_vs_stats_delta",
    ]
    _to_numeric(data, numeric_columns)
    grouped = (
        data.groupby("date_utc", as_index=False)
        .agg(
            tronscan_tracked_token_count=("token_symbol", "nunique"),
            tronscan_transfer_count=("transfer_count", "sum"),
            tronscan_transfer_amount=("transfer_amount", "sum"),
            tronscan_transfer_amount_usd=("transfer_amount_usd", "sum"),
            tronscan_from_count=("from_count", "sum"),
            tronscan_to_count=("to_count", "sum"),
            tronscan_active_address_count=("active_address_count", "sum"),
            tronscan_holders_count=("holders_count", "sum"),
            tronscan_stats_usdt_transaction_count=("stats_usdt_transaction_count", "sum"),
            tronscan_stats_active_account_number=("stats_active_account_number", "sum"),
            tronscan_stats_total_transaction_count=("stats_total_transaction_count", "sum"),
            tronscan_transfer_count_vs_stats_delta=("transfer_count_vs_stats_delta", "mean"),
        )
        .sort_values("date_utc")
        .reset_index(drop=True)
    )
    grouped["tronscan_transfer_amount_usd_log"] = np.log1p(
        grouped["tronscan_transfer_amount_usd"].clip(lower=0.0)
    )
    grouped["tronscan_transfer_count_ratio_to_stats"] = _safe_ratio(
        grouped["tronscan_transfer_count"],
        grouped["tronscan_stats_usdt_transaction_count"],
    )
    grouped["tronscan_transfer_count_ratio_gap"] = grouped["tronscan_transfer_count_ratio_to_stats"] - 1.0
    grouped["tronscan_stats_gap_ratio"] = _safe_ratio(
        grouped["tronscan_transfer_count_vs_stats_delta"],
        grouped["tronscan_stats_usdt_transaction_count"],
    )
    grouped["tronscan_transfer_amount_usd_z14"] = _rolling_z(grouped["tronscan_transfer_amount_usd_log"])
    grouped["tronscan_transfer_count_z14"] = _rolling_z(grouped["tronscan_transfer_count"])
    grouped["tronscan_active_address_z14"] = _rolling_z(grouped["tronscan_active_address_count"])
    grouped["tronscan_transfer_count_ratio_to_stats_z14"] = _rolling_z(
        grouped["tronscan_transfer_count_ratio_gap"]
    )
    grouped["tronscan_holders_growth_7d"] = grouped["tronscan_holders_count"].pct_change(
        7,
        fill_method=None,
    )
    grouped["tronscan_holders_growth_z14"] = _rolling_z(grouped["tronscan_holders_growth_7d"])
    grouped["tronscan_stats_gap_ratio_z14"] = _rolling_z(grouped["tronscan_stats_gap_ratio"])
    return grouped


def _aggregate_cryptoquant_supply(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    _to_numeric(
        data,
        [
            "supply_total",
            "supply_circulating",
            "supply_minted",
            "supply_burned",
            "supply_issued",
            "supply_redeemed",
            "tokens_transferred_total",
            "tokens_transferred_mean",
            "addresses_active_count",
            "addresses_active_sender_count",
            "addresses_active_receiver_count",
        ],
    )
    grouped = (
        data.groupby("date_utc", as_index=False)
        .agg(
            cq_tracked_token_count=("token_id", "nunique"),
            cq_supply_total=("supply_total", "sum"),
            cq_supply_circulating=("supply_circulating", "sum"),
            cq_supply_minted=("supply_minted", "sum"),
            cq_supply_burned=("supply_burned", "sum"),
            cq_supply_issued=("supply_issued", "sum"),
            cq_supply_redeemed=("supply_redeemed", "sum"),
            cq_tokens_transferred_total=("tokens_transferred_total", "sum"),
            cq_tokens_transferred_mean=("tokens_transferred_mean", "mean"),
            cq_addresses_active_count=("addresses_active_count", "sum"),
            cq_addresses_active_sender_count=("addresses_active_sender_count", "sum"),
            cq_addresses_active_receiver_count=("addresses_active_receiver_count", "sum"),
        )
        .sort_values("date_utc")
        .reset_index(drop=True)
    )
    grouped["cq_supply_net_issued"] = grouped["cq_supply_issued"] - grouped["cq_supply_redeemed"]
    grouped["cq_supply_growth_7d"] = grouped["cq_supply_circulating"].pct_change(7, fill_method=None)
    grouped["cq_supply_net_issued_ratio"] = _safe_ratio(
        grouped["cq_supply_net_issued"],
        grouped["cq_supply_circulating"],
    )
    grouped["cq_transfer_activity_log"] = np.log1p(grouped["cq_tokens_transferred_total"].clip(lower=0.0))
    grouped["cq_supply_growth_velocity_z14"] = _rolling_z(grouped["cq_supply_growth_7d"])
    grouped["cq_supply_net_issued_ratio_z14"] = _rolling_z(grouped["cq_supply_net_issued_ratio"])
    grouped["cq_transfer_activity_z14"] = _rolling_z(grouped["cq_transfer_activity_log"])
    return grouped


def _aggregate_cryptoquant_stablecoin_exchange_flows(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    numeric_columns = [
        "reserve",
        "inflow_total",
        "outflow_total",
        "netflow_total",
        "transactions_count_inflow",
        "transactions_count_outflow",
        "addresses_count_inflow",
        "addresses_count_outflow",
    ]
    _to_numeric(data, numeric_columns)
    grouped = (
        data.groupby(["date_utc", "exchange"], as_index=False)[numeric_columns]
        .sum()
        .sort_values(["date_utc", "exchange"])
    )
    parts: list[pd.DataFrame] = []
    for exchange, exchange_frame in grouped.groupby("exchange", sort=True):
        safe_exchange = _safe_name(exchange)
        subset = exchange_frame.drop(columns=["exchange"]).copy()
        subset = subset.rename(
            columns={column: f"cq_stable_{safe_exchange}_{column}" for column in numeric_columns}
        )
        parts.append(subset)
    return _merge_frames_on_date(parts)


def _aggregate_cryptoquant_reflexivity_exchange_flows(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    numeric_columns = [
        "reserve",
        "reserve_usd",
        "inflow_total",
        "outflow_total",
        "netflow_total",
        "transactions_count_inflow",
        "transactions_count_outflow",
        "addresses_count_inflow",
        "addresses_count_outflow",
    ]
    _to_numeric(data, numeric_columns)
    grouped = (
        data.groupby(["date_utc", "asset_id", "exchange"], as_index=False)[numeric_columns]
        .sum()
        .sort_values(["date_utc", "asset_id", "exchange"])
    )
    parts: list[pd.DataFrame] = []
    for (asset_id, exchange), subset in grouped.groupby(["asset_id", "exchange"], sort=True):
        safe_name = f"cq_{_safe_name(asset_id)}_{_safe_name(exchange)}"
        frame = subset.drop(columns=["asset_id", "exchange"]).copy()
        frame = frame.rename(columns={column: f"{safe_name}_{column}" for column in numeric_columns})
        parts.append(frame)
    return _merge_frames_on_date(parts)


def _aggregate_cryptoquant_reflexivity_market_indicators(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    numeric_columns = [
        "sopr",
        "a_sopr",
        "sth_sopr",
        "lth_sopr",
        "sopr_ratio",
        "stablecoin_supply_ratio",
        "realized_price",
    ]
    _to_numeric(data, numeric_columns)
    grouped = data.groupby(["date_utc", "asset_id"], as_index=False)[numeric_columns].mean()
    parts: list[pd.DataFrame] = []
    for asset_id, subset in grouped.groupby("asset_id", sort=True):
        safe_asset = _safe_name(asset_id)
        frame = subset.drop(columns=["asset_id"]).copy()
        frame = frame.rename(columns={column: f"cq_{safe_asset}_{column}" for column in numeric_columns})
        parts.append(frame)
    return _merge_frames_on_date(parts)


def _derive_fused_columns(panel: pd.DataFrame) -> None:
    _to_numeric(
        panel,
        [
            "alchemy_exchange_absorption_score_v1",
            "alchemy_issuance_ratio_z14",
            "cq_supply_circulating",
            "cq_supply_growth_velocity_z14",
            "cq_supply_net_issued_ratio_z14",
            "cq_stable_spot_exchange_reserve",
            "cq_stable_spot_exchange_netflow_total",
            "cq_stable_derivative_exchange_reserve",
            "cq_stable_derivative_exchange_netflow_total",
            "cq_btc_spot_exchange_reserve",
            "cq_btc_spot_exchange_netflow_total",
            "cq_btc_all_exchange_reserve",
            "cq_btc_all_exchange_netflow_total",
            "cq_btc_sopr",
            "cq_btc_lth_sopr",
            "cq_btc_stablecoin_supply_ratio",
            "tronscan_transfer_count",
            "tronscan_transfer_amount_usd",
            "tronscan_transfer_count_ratio_to_stats",
            "tronscan_transfer_count_ratio_to_stats_z14",
            "tronscan_stats_gap_ratio_z14",
            "tronscan_transfer_amount_usd_z14",
            "tronscan_transfer_count_z14",
            "tronscan_active_address_z14",
            "tronscan_holders_growth_z14",
        ],
    )
    panel["decision_date_utc"] = (
        pd.to_datetime(panel["date_utc"], utc=True, errors="coerce") + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")
    panel["cq_stable_spot_exchange_reserve_ratio"] = _safe_ratio(
        panel.get("cq_stable_spot_exchange_reserve"),
        panel.get("cq_supply_circulating"),
    )
    panel["cq_stable_spot_exchange_netflow_ratio"] = _safe_ratio(
        panel.get("cq_stable_spot_exchange_netflow_total"),
        panel.get("cq_supply_circulating"),
    )
    panel["cq_stable_derivative_exchange_reserve_ratio"] = _safe_ratio(
        panel.get("cq_stable_derivative_exchange_reserve"),
        panel.get("cq_supply_circulating"),
    )
    panel["cq_stable_derivative_exchange_netflow_ratio"] = _safe_ratio(
        panel.get("cq_stable_derivative_exchange_netflow_total"),
        panel.get("cq_supply_circulating"),
    )
    panel["cq_btc_spot_exchange_netflow_ratio"] = _safe_ratio(
        panel.get("cq_btc_spot_exchange_netflow_total"),
        panel.get("cq_btc_spot_exchange_reserve"),
    )
    panel["cq_btc_all_exchange_netflow_ratio"] = _safe_ratio(
        panel.get("cq_btc_all_exchange_netflow_total"),
        panel.get("cq_btc_all_exchange_reserve"),
    )
    panel["cq_btc_sopr_gap"] = 1.0 - pd.to_numeric(panel.get("cq_btc_sopr"), errors="coerce")
    panel["cq_btc_lth_sopr_gap"] = 1.0 - pd.to_numeric(panel.get("cq_btc_lth_sopr"), errors="coerce")
    panel["cq_stable_spot_exchange_reserve_ratio_z14"] = _rolling_z(
        panel["cq_stable_spot_exchange_reserve_ratio"]
    )
    panel["cq_stable_spot_exchange_netflow_ratio_z14"] = _rolling_z(
        panel["cq_stable_spot_exchange_netflow_ratio"]
    )
    panel["cq_btc_spot_exchange_netflow_ratio_z14"] = _rolling_z(
        panel["cq_btc_spot_exchange_netflow_ratio"]
    )
    panel["cq_btc_sopr_gap_z14"] = _rolling_z(panel["cq_btc_sopr_gap"])
    panel["cq_btc_lth_sopr_gap_z14"] = _rolling_z(panel["cq_btc_lth_sopr_gap"])
    panel["cq_btc_sopr_z14"] = _rolling_z(pd.to_numeric(panel.get("cq_btc_sopr"), errors="coerce"))
    panel["cq_btc_lth_sopr_z14"] = _rolling_z(pd.to_numeric(panel.get("cq_btc_lth_sopr"), errors="coerce"))
    panel["cq_btc_ssr_z14"] = _rolling_z(
        pd.to_numeric(panel.get("cq_btc_stablecoin_supply_ratio"), errors="coerce")
    )

    neg_btc_flow = -panel["cq_btc_spot_exchange_netflow_ratio_z14"]
    panel["m3_2_stable_supply_impulse_state"] = _mean_ignore_nan(
        [
            panel["alchemy_issuance_ratio_z14"],
            panel["cq_supply_growth_velocity_z14"],
            panel["cq_supply_net_issued_ratio_z14"],
        ]
    )
    panel["m3_2_stable_dry_powder_state"] = _mean_ignore_nan(
        [
            panel["alchemy_exchange_absorption_score_v1"],
            panel["cq_stable_spot_exchange_reserve_ratio_z14"],
            panel["cq_stable_spot_exchange_netflow_ratio_z14"],
        ]
    )
    panel["m3_2_stable_btc_flow_asymmetry_state"] = _mean_ignore_nan(
        [
            panel["alchemy_exchange_absorption_score_v1"],
            panel["cq_stable_spot_exchange_netflow_ratio_z14"],
            neg_btc_flow,
        ]
    )
    panel["m3_2_btc_sell_pressure_state"] = _mean_ignore_nan(
        [
            panel["cq_btc_spot_exchange_netflow_ratio_z14"],
            panel["cq_btc_sopr_z14"],
            panel["cq_btc_lth_sopr_z14"],
        ]
    )
    panel["m3_2_reflexive_rebound_state"] = _mean_ignore_nan(
        [
            panel["cq_btc_sopr_gap_z14"],
            panel["cq_btc_lth_sopr_gap_z14"],
            panel["cq_stable_spot_exchange_netflow_ratio_z14"],
            neg_btc_flow,
        ]
    )
    panel["m3_2_tron_flow_impulse_state"] = _mean_ignore_nan(
        [
            pd.to_numeric(panel.get("tronscan_transfer_amount_usd_z14"), errors="coerce"),
            pd.to_numeric(panel.get("tronscan_transfer_count_z14"), errors="coerce"),
            pd.to_numeric(panel.get("tronscan_active_address_z14"), errors="coerce"),
            pd.to_numeric(panel.get("tronscan_holders_growth_z14"), errors="coerce"),
        ]
    )
    panel["m3_2_tron_flow_quality_state"] = _mean_ignore_nan(
        [
            -pd.to_numeric(panel.get("tronscan_transfer_count_ratio_to_stats_z14"), errors="coerce").abs(),
            -pd.to_numeric(panel.get("tronscan_stats_gap_ratio_z14"), errors="coerce").abs(),
        ]
    )
    panel["m3_2_tron_speculative_heat_state"] = _mean_ignore_nan(
        [
            pd.to_numeric(panel.get("tronscan_transfer_amount_usd_z14"), errors="coerce"),
            pd.to_numeric(panel.get("tronscan_transfer_count_z14"), errors="coerce"),
            pd.to_numeric(panel.get("tronscan_transfer_count_ratio_to_stats_z14"), errors="coerce"),
        ]
    )
    panel["m3_2_panel_ready"] = (
        _as_bool(panel.get("alchemy_signal_ready"))
        & panel["cq_supply_growth_velocity_z14"].notna()
        & panel["cq_stable_spot_exchange_netflow_ratio_z14"].notna()
        & panel["cq_btc_sopr"].notna()
    )


def _merge_frames_on_date(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=["date_utc"])
    merged = frames[0].copy()
    for frame in frames[1:]:
        merged = merged.merge(frame, on="date_utc", how="outer")
    return merged.sort_values("date_utc").reset_index(drop=True)


def _build_date_spine(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame[["date_utc"]].copy() for frame in frames if not frame.empty and "date_utc" in frame.columns]
    if not non_empty:
        return pd.DataFrame(columns=["date_utc", "decision_date_utc"])
    spine = pd.concat(non_empty, axis=0, ignore_index=True).dropna().drop_duplicates().sort_values("date_utc")
    spine = spine.reset_index(drop=True)
    spine["decision_date_utc"] = (
        pd.to_datetime(spine["date_utc"], utc=True, errors="coerce") + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")
    return spine


def _to_numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _safe_ratio(numerator: pd.Series | None, denominator: pd.Series | None) -> pd.Series:
    if numerator is None or denominator is None:
        return pd.Series(dtype="float64")
    return (
        pd.to_numeric(numerator, errors="coerce")
        / pd.to_numeric(denominator, errors="coerce").replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)


def _rolling_z(series: pd.Series) -> pd.Series:
    mean = series.rolling(_ROLLING_Z_WINDOW, min_periods=_MIN_PERIODS).mean()
    std = series.rolling(_ROLLING_Z_WINDOW, min_periods=_MIN_PERIODS).std()
    return (series - mean) / std.replace(0.0, np.nan)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in str(value).strip().lower()).strip("_")


def _as_bool(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="bool")
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _mean_ignore_nan(series_list: list[pd.Series]) -> pd.Series:
    return pd.concat(series_list, axis=1).mean(axis=1, skipna=True)
