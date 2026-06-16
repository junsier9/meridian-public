from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EVENT_STATE_COLUMNS = [
    "m3_3_event_state_hype_pressure_v1",
    "m3_3_event_state_confirmed_quality_v1",
    "m3_3_event_state_short_quality_v1",
    "m3_3_event_state_noise_ratio_v1",
    "m3_3_strict_event_state_q1_noise0_flag",
]


def _to_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def build_m3_3_news_tape(news: pd.DataFrame, *, lookback_days: int) -> pd.DataFrame:
    required = {
        "currencies",
        "research_effective_at_utc",
        "final_short_veto_flag",
        "final_repricing_type",
        "final_market_impact_direction",
        "final_market_impact_magnitude",
        "final_subject_link_strength",
        "final_is_actionable_event",
    }
    missing = sorted(required - set(news.columns))
    if missing:
        raise ValueError(f"M3.3 news artifact missing columns: {missing}")

    frame = news.copy()
    frame["event_day"] = pd.to_datetime(frame["research_effective_at_utc"], utc=True, errors="coerce").dt.floor("D")
    frame = frame.loc[frame["event_day"].notna()].copy()
    frame["currencies"] = frame["currencies"].apply(
        lambda value: list(value) if isinstance(value, (list, tuple, set, np.ndarray)) else [value]
    )
    frame = frame.explode("currencies")
    frame["subject"] = frame["currencies"].astype(str).str.upper().str.strip()
    frame = frame.loc[frame["subject"].ne("") & frame["subject"].ne("NONE")].copy()

    repricing = frame["final_repricing_type"].astype(str).str.lower()
    direction = frame["final_market_impact_direction"].astype(str).str.lower()
    magnitude = pd.to_numeric(frame["final_market_impact_magnitude"], errors="coerce").fillna(0.0)
    link_strength = pd.to_numeric(frame["final_subject_link_strength"], errors="coerce").fillna(0.0)
    actionable = _to_bool_series(frame["final_is_actionable_event"])
    short_veto = _to_bool_series(frame["final_short_veto_flag"])

    frame["event_any_actionable"] = actionable.astype(int)
    frame["event_short_veto"] = short_veto.astype(int)
    frame["event_real_repricing"] = repricing.eq("real_repricing").astype(int)
    frame["event_hype"] = repricing.eq("hype").astype(int)
    frame["event_bullish_repricing"] = (
        repricing.isin(["real_repricing", "mixed"]) & direction.eq("bullish") & (magnitude >= 2.0)
    ).astype(int)
    frame["event_confirmed_short_veto"] = (
        short_veto
        & actionable
        & repricing.isin(["real_repricing", "mixed"])
        & direction.isin(["bullish", "neutral"])
        & (link_strength >= 3.0)
    ).astype(int)

    records: list[pd.DataFrame] = []
    keep_columns = [
        "subject",
        "event_day",
        "event_any_actionable",
        "event_short_veto",
        "event_real_repricing",
        "event_hype",
        "event_bullish_repricing",
        "event_confirmed_short_veto",
        "final_subject_link_strength",
        "final_market_impact_magnitude",
    ]
    slim = frame[keep_columns].copy()
    for offset in range(max(int(lookback_days), 1)):
        expanded = slim.copy()
        expanded["date_utc"] = (expanded["event_day"] + pd.to_timedelta(offset, unit="D")).dt.date.astype(str)
        records.append(expanded)
    expanded = pd.concat(records, ignore_index=True) if records else slim.iloc[0:0].copy()

    grouped = (
        expanded.groupby(["subject", "date_utc"], as_index=False)
        .agg(
            m3_3_event_tape_any_actionable_count_10d=("event_any_actionable", "sum"),
            m3_3_event_tape_short_veto_count_10d=("event_short_veto", "sum"),
            m3_3_event_tape_real_repricing_count_10d=("event_real_repricing", "sum"),
            m3_3_event_tape_hype_count_10d=("event_hype", "sum"),
            m3_3_event_tape_bullish_repricing_count_10d=("event_bullish_repricing", "sum"),
            m3_3_event_tape_confirmed_short_veto_count_10d=("event_confirmed_short_veto", "sum"),
            m3_3_event_tape_max_subject_link_strength_10d=("final_subject_link_strength", "max"),
            m3_3_event_tape_max_market_impact_magnitude_10d=("final_market_impact_magnitude", "max"),
        )
        .copy()
    )
    for column in [column for column in grouped.columns if column.endswith("_count_10d")]:
        grouped[column.replace("_count_10d", "_flag_10d")] = (grouped[column] > 0).astype(int)
    return grouped


def add_m3_3_event_state_features(
    frame: pd.DataFrame,
    *,
    news_artifact: Path,
    lookback_days: int,
) -> pd.DataFrame:
    out = frame.copy()
    stale_columns = [
        column
        for column in out.columns
        if column.startswith("m3_3_event_tape_")
        or column.startswith("m3_3_event_state_")
        or column.startswith("m3_3_strict_event_state_")
    ]
    if stale_columns:
        out = out.drop(columns=stale_columns)
    if "date_utc" not in out.columns:
        out["date_utc"] = pd.to_datetime(out["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    tape = build_m3_3_news_tape(pd.read_parquet(news_artifact), lookback_days=lookback_days)
    out = out.merge(tape, on=["subject", "date_utc"], how="left")
    event_columns = [column for column in out.columns if column.startswith("m3_3_event_tape_")]
    for column in event_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)

    hype = pd.to_numeric(out["m3_3_event_tape_hype_count_10d"], errors="coerce").fillna(0.0)
    confirmed = pd.to_numeric(out["m3_3_event_tape_confirmed_short_veto_count_10d"], errors="coerce").fillna(0.0)
    real = pd.to_numeric(out["m3_3_event_tape_real_repricing_count_10d"], errors="coerce").fillna(0.0)
    short_veto = pd.to_numeric(out["m3_3_event_tape_short_veto_count_10d"], errors="coerce").fillna(0.0)
    any_actionable = pd.to_numeric(out["m3_3_event_tape_any_actionable_count_10d"], errors="coerce").fillna(0.0)
    max_link = pd.to_numeric(out["m3_3_event_tape_max_subject_link_strength_10d"], errors="coerce").fillna(0.0)
    max_mag = pd.to_numeric(out["m3_3_event_tape_max_market_impact_magnitude_10d"], errors="coerce").fillna(0.0)

    out["m3_3_event_state_hype_pressure_v1"] = hype.astype("float64")
    out["m3_3_event_state_confirmed_quality_v1"] = (confirmed + real + short_veto).astype("float64")
    out["m3_3_event_state_short_quality_v1"] = (
        confirmed + 0.5 * real + 0.5 * short_veto + 0.1 * max_link + 0.1 * max_mag - hype
    ).astype("float64")
    out["m3_3_event_state_noise_ratio_v1"] = (
        hype / any_actionable.replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float64")
    out["m3_3_strict_event_state_q1_noise0_flag"] = (
        out["m3_3_event_state_short_quality_v1"].ge(1.0)
        & out["m3_3_event_state_noise_ratio_v1"].le(0.0)
        & out["m3_3_event_state_hype_pressure_v1"].le(0.0)
    ).astype("int8")
    return out
