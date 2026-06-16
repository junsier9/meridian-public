from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_ENDPOINTS = {
    "futures_open_interest_history_usd": "oi_usd",
    "futures_funding_rate_history": "funding",
    "futures_taker_buy_sell_volume": "taker_flow",
    "futures_liquidation_history": "liquidation",
    "futures_orderbook_ask_bids_history": "orderbook",
    "futures_global_long_short_account_ratio": "global_long_short",
    "futures_top_long_short_position_ratio": "top_trader",
}

FAMILY_COLUMNS = {
    "liquidation": ["long_liquidation_usd", "short_liquidation_usd"],
    "orderbook": ["orderbook_bids_usd", "orderbook_asks_usd"],
    "taker_flow": ["taker_buy_volume_usd", "taker_sell_volume_usd"],
    "global_long_short": [
        "global_account_long_pct",
        "global_account_short_pct",
        "global_account_long_short_ratio",
    ],
    "top_trader": [
        "top_trader_long_pct",
        "top_trader_short_pct",
        "top_trader_long_short_ratio",
    ],
    "funding_oi": ["funding_rate", "open_interest", "open_interest_value"],
}

CORE_FAMILIES = [
    "funding_oi",
    "liquidation",
    "orderbook",
    "taker_flow",
    "global_long_short",
    "top_trader",
]


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    out_root: Path
    matrix_path: Path
    doc_path: Path
    market_history_root: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit CoinGlass Phase 0 readiness for provider_sidecar_h10d."
    )
    parser.add_argument(
        "--out-root",
        default="artifacts/quant_research/provider_sidecar_h10d/phase0_coverage_20260518",
        help="Output directory for Phase 0 artifacts.",
    )
    parser.add_argument(
        "--matrix-path",
        default=(
            "artifacts/quant_research/provider_sidecar_h10d/"
            "phase0_coverage_20260518/provider_smoke/coinglass_capability_matrix.json"
        ),
        help="CoinGlass endpoint capability matrix JSON from the current smoke run.",
    )
    parser.add_argument(
        "--doc-path",
        default=(
            "docs/quant_research/03_alpha_branches/"
            "provider_sidecar_h10d_phase0_coverage_2026_05_18.md"
        ),
        help="Markdown report path to write.",
    )
    parser.add_argument(
        "--market-history-root",
        default=None,
        help="Override local market history root. Defaults to %%LOCALAPPDATA%%/EnhengClaw/market_history.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def make_paths(args: argparse.Namespace) -> Paths:
    root = repo_root()
    if args.market_history_root:
        market_history_root = Path(args.market_history_root)
    else:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise RuntimeError("LOCALAPPDATA is not set; pass --market-history-root.")
        market_history_root = Path(local_appdata) / "EnhengClaw" / "market_history"
    return Paths(
        repo_root=root,
        out_root=(root / args.out_root).resolve(),
        matrix_path=(root / args.matrix_path).resolve(),
        doc_path=(root / args.doc_path).resolve(),
        market_history_root=market_history_root.resolve(),
    )


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def env_value(scope: str, name: str) -> str | None:
    if scope == "Process":
        return os.environ.get(name)
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    if scope == "User":
        hive = winreg.HKEY_CURRENT_USER
        key_path = "Environment"
    elif scope == "Machine":
        hive = winreg.HKEY_LOCAL_MACHINE
        key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    else:
        return None
    try:
        with winreg.OpenKey(hive, key_path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return None


def collect_key_scope_status() -> pd.DataFrame:
    rows = []
    for scope in ["Process", "User", "Machine"]:
        for name in ["CoinglassAPI", "COINGLASSAPI", "COINGLASS_API_KEY"]:
            value = env_value(scope, name)
            rows.append(
                {
                    "scope": scope,
                    "name": name,
                    "present": bool(value and value.strip()),
                    "length": len(value.strip()) if value and value.strip() else 0,
                }
            )
    return pd.DataFrame(rows)


def read_live_fixed20_symbols(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*symbols:\s*\[(.*?)\]\s*$", text)
    if not match:
        match = re.search(r"(?m)^\s*symbols:\s*(.*?)\s*$", text)
    if not match:
        raise RuntimeError(f"Could not find symbols in {path}")
    symbols = [item.strip().strip("'\"") for item in match.group(1).split(",")]
    return [symbol for symbol in symbols if symbol]


def ms_to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, unit="ms", utc=True).dt.strftime("%Y-%m-%d")


def normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date_utc" in out.columns:
        out["date_utc"] = pd.to_datetime(out["date_utc"], utc=True).dt.strftime("%Y-%m-%d")
        return out
    if "open_time_ms" in out.columns:
        out["date_utc"] = ms_to_date(out["open_time_ms"])
        return out
    if "timestamp_ms" in out.columns:
        out["date_utc"] = ms_to_date(out["timestamp_ms"])
        return out
    raise RuntimeError("No supported date column found.")


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def read_control_inputs(paths: Paths) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    hv_root = paths.repo_root / "artifacts" / "qr" / "hv_balanced"
    rebalance = pd.read_csv(hv_root / "aligned_period_returns.csv")
    rebalance["date_utc"] = ms_to_date(rebalance["timestamp_ms"])
    universe = pd.read_csv(hv_root / "universe_membership.csv")
    universe["date_utc"] = ms_to_date(universe["timestamp_ms"])
    positions = pd.read_csv(hv_root / "position_attribution.csv")
    positions["date_utc"] = ms_to_date(positions["decision_timestamp_ms"])
    live_symbols = read_live_fixed20_symbols(
        paths.repo_root / "config" / "live_trading" / "hv_balanced_binance_usdm_live_pilot.yaml"
    )
    return rebalance, universe, positions, live_symbols


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return normalize_date_column(pd.read_csv(path))


def read_derivatives_1d(paths: Paths, symbols: Iterable[str]) -> pd.DataFrame:
    root = paths.market_history_root / "binance_derivatives"
    frames = []
    usecols = [
        "symbol",
        "open_time_ms",
        "funding_rate",
        "open_interest",
        "open_interest_value",
    ]
    for symbol in sorted(set(symbols)):
        symbol_root = root / symbol / "1d"
        if not symbol_root.exists():
            continue
        for file_path in sorted(symbol_root.glob("*.csv.gz")):
            try:
                frame = pd.read_csv(file_path, usecols=lambda col: col in usecols)
            except Exception as exc:  # pragma: no cover - defensive audit path
                frames.append(
                    pd.DataFrame(
                        [
                            {
                                "symbol": symbol,
                                "open_time_ms": pd.NA,
                                "funding_rate": pd.NA,
                                "open_interest": pd.NA,
                                "open_interest_value": pd.NA,
                                "read_error": str(exc),
                            }
                        ]
                    )
                )
                continue
            if frame.empty:
                continue
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["symbol", "date_utc", *FAMILY_COLUMNS["funding_oi"]])
    data = pd.concat(frames, ignore_index=True)
    data = data.dropna(subset=["open_time_ms"])
    return normalize_date_column(data)


def endpoint_rows(matrix: dict) -> pd.DataFrame:
    rows = []
    for item in matrix.get("endpoints", []):
        endpoint_id = item.get("endpoint_id")
        history = item.get("history_window_observed") or {}
        rows.append(
            {
                "endpoint_id": endpoint_id,
                "required_for_phase0": endpoint_id in REQUIRED_ENDPOINTS,
                "sidecar_family": REQUIRED_ENDPOINTS.get(endpoint_id, ""),
                "status": item.get("status"),
                "classification": item.get("classification"),
                "recent_row_count": item.get("row_count"),
                "recent_first_utc": history.get("recent_first_time_utc"),
                "recent_last_utc": history.get("recent_last_time_utc"),
                "history_days": history.get("history_probe_days_back"),
                "history_row_count": history.get("history_probe_row_count"),
                "history_first_utc": history.get("history_probe_first_time_utc"),
                "history_last_utc": history.get("history_probe_last_time_utc"),
                "error": item.get("error") or "",
            }
        )
    return pd.DataFrame(rows)


def family_availability(df: pd.DataFrame, family: str) -> pd.DataFrame:
    cols = FAMILY_COLUMNS[family]
    if df.empty:
        return pd.DataFrame(columns=["symbol", "date_utc", "family", "available"])
    present_cols = [col for col in cols if col in df.columns]
    if not present_cols:
        return pd.DataFrame(columns=["symbol", "date_utc", "family", "available"])
    subset = df[["symbol", "date_utc", *present_cols]].copy()
    subset["available"] = subset[present_cols].notna().any(axis=1)
    subset = subset[subset["available"]]
    if subset.empty:
        return pd.DataFrame(columns=["symbol", "date_utc", "family", "available"])
    grouped = (
        subset.groupby(["symbol", "date_utc"], as_index=False)["available"]
        .max()
        .assign(family=family)
    )
    return grouped[["symbol", "date_utc", "family", "available"]]


def summarize_window(availability: pd.DataFrame, family: str, source_path: str) -> dict:
    if availability.empty:
        return {
            "family": family,
            "source_path": source_path,
            "row_count": 0,
            "symbol_count": 0,
            "first_date_utc": "",
            "last_date_utc": "",
        }
    return {
        "family": family,
        "source_path": source_path,
        "row_count": int(len(availability)),
        "symbol_count": int(availability["symbol"].nunique()),
        "first_date_utc": str(availability["date_utc"].min()),
        "last_date_utc": str(availability["date_utc"].max()),
    }


def symbol_coverage_rows(
    availabilities: dict[str, pd.DataFrame],
    symbols: Iterable[str],
    live_symbols: set[str],
    universe_active: pd.DataFrame,
    positions: pd.DataFrame,
) -> pd.DataFrame:
    active_counts = universe_active.groupby("symbol").size().to_dict()
    position_counts = positions.groupby("usdm_symbol").size().to_dict()
    rows = []
    for symbol in sorted(set(symbols)):
        for family, availability in availabilities.items():
            symbol_data = availability[availability["symbol"] == symbol]
            rows.append(
                {
                    "symbol": symbol,
                    "family": family,
                    "live_fixed20": symbol in live_symbols,
                    "pit_active_day_count": int(active_counts.get(symbol, 0)),
                    "position_row_count": int(position_counts.get(symbol, 0)),
                    "available_day_count": int(len(symbol_data)),
                    "first_date_utc": str(symbol_data["date_utc"].min()) if not symbol_data.empty else "",
                    "last_date_utc": str(symbol_data["date_utc"].max()) if not symbol_data.empty else "",
                }
            )
    return pd.DataFrame(rows)


def liquidity_coverage_rows(
    availabilities: dict[str, pd.DataFrame],
    universe_active: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    active = universe_active[["symbol", "date_utc", "liquidity_bucket"]].copy()
    for family, availability in availabilities.items():
        if availability.empty:
            for bucket, bucket_df in active.groupby("liquidity_bucket"):
                rows.append(
                    {
                        "family": family,
                        "liquidity_bucket": bucket,
                        "active_rows": int(len(bucket_df)),
                        "covered_rows": 0,
                        "coverage_ratio": 0.0,
                        "overlap_active_rows": 0,
                        "overlap_covered_rows": 0,
                        "overlap_coverage_ratio": 0.0,
                        "family_first_date_utc": "",
                        "family_last_date_utc": "",
                    }
                )
            continue
        family_first = str(availability["date_utc"].min())
        family_last = str(availability["date_utc"].max())
        covered_keys = availability[["symbol", "date_utc"]].drop_duplicates()
        merged = active.merge(
            covered_keys.assign(covered=True),
            on=["symbol", "date_utc"],
            how="left",
        )
        merged["covered"] = merged["covered"].map(lambda value: value is True)
        merged["in_family_window"] = (
            (merged["date_utc"] >= family_first) & (merged["date_utc"] <= family_last)
        )
        for bucket, bucket_df in merged.groupby("liquidity_bucket"):
            overlap = bucket_df[bucket_df["in_family_window"]]
            rows.append(
                {
                    "family": family,
                    "liquidity_bucket": bucket,
                    "active_rows": int(len(bucket_df)),
                    "covered_rows": int(bucket_df["covered"].sum()),
                    "coverage_ratio": float(bucket_df["covered"].mean()) if len(bucket_df) else 0.0,
                    "overlap_active_rows": int(len(overlap)),
                    "overlap_covered_rows": int(overlap["covered"].sum()),
                    "overlap_coverage_ratio": float(overlap["covered"].mean())
                    if len(overlap)
                    else 0.0,
                    "family_first_date_utc": family_first,
                    "family_last_date_utc": family_last,
                }
            )
    return pd.DataFrame(rows)


def family_rebalance_overlap_rows(
    windows: pd.DataFrame,
    rebalance_dates: list[str],
    position_dates: list[str],
) -> pd.DataFrame:
    rows = []
    for item in windows.to_dict("records"):
        first_date = item["first_date_utc"]
        last_date = item["last_date_utc"]
        if not first_date or not last_date:
            rebalance_overlap = 0
            position_overlap = 0
        else:
            rebalance_overlap = sum(first_date <= date <= last_date for date in rebalance_dates)
            position_overlap = sum(first_date <= date <= last_date for date in position_dates)
        rows.append(
            {
                "family": item["family"],
                "first_date_utc": first_date,
                "last_date_utc": last_date,
                "control_rebalance_overlap_count": int(rebalance_overlap),
                "position_decision_overlap_count": int(position_overlap),
            }
        )
    return pd.DataFrame(rows)


def pit_lag_rows(panel_paths: dict[str, Path], sample_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for family, frame in sample_frames.items():
        columns = set(frame.columns)
        explicit_available = any(
            col in columns
            for col in [
                "available_at",
                "available_at_utc",
                "available_at_ms",
                "ingested_at",
                "ingested_at_utc",
            ]
        )
        rows.append(
            {
                "family": family,
                "source_path": str(panel_paths.get(family, "")),
                "explicit_available_at_column": explicit_available,
                "timestamp_column": "date_utc" if "date_utc" in columns else "open_time_ms",
                "phase1_required_policy": (
                    "Use only rows whose provider bar close is strictly before the decision "
                    "timestamp; daily sidecars must be shifted by at least one full UTC day "
                    "unless an explicit provider available_at timestamp is added."
                ),
                "pit_status": "needs_conservative_lag_encoding"
                if not explicit_available
                else "explicit_available_at_present",
            }
        )
    return pd.DataFrame(rows)


def md_table(df: pd.DataFrame, columns: list[str], limit: int | None = None) -> str:
    if limit is not None:
        df = df.head(limit)
    if df.empty:
        return "_empty_"
    view = df[columns].copy()

    def cell(value: object) -> str:
        if pd.isna(value):
            return ""
        return str(value).replace("|", "\\|")

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in view.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(
    paths: Paths,
    summary: dict,
    endpoint_df: pd.DataFrame,
    key_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    rebalance_overlap_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
) -> None:
    paths.doc_path.parent.mkdir(parents=True, exist_ok=True)
    required_endpoint_view = endpoint_df[endpoint_df["required_for_phase0"]].copy()
    top_bucket_view = liquidity_df[
        liquidity_df["liquidity_bucket"].astype(str).str.lower().str.contains("top")
    ].copy()
    blockers = "\n".join(f"- {item}" for item in summary["blockers"])
    if not blockers:
        blockers = "- None."
    report = f"""# provider_sidecar_h10d Phase 0 CoinGlass Coverage Audit

Generated local date: 2026-05-18

## Hard Status

- `provider_sidecar_h10d_phase0_ready`: **{str(summary["provider_sidecar_h10d_phase0_ready"]).lower()}**
- `overlap_only_diagnostic_ready`: **{str(summary["overlap_only_diagnostic_ready"]).lower()}**
- Frozen control: `hv_balanced`
- Live config changed: **false**

## Decision

Phase 0 is **not promotion-ready** for a full `hv_balanced` paired h10d rerun. CoinGlass endpoint access is live and the required futures sidecar endpoint smoke passed, but the local sidecar history does not cover the full frozen-control window and the current sidecar panels do not carry an explicit provider `available_at` timestamp.

## Blockers

{blockers}

## Key / Endpoint Audit

{md_table(key_df, ["scope", "name", "present", "length"])}

Required futures endpoints:

{md_table(required_endpoint_view, ["endpoint_id", "status", "classification", "history_days", "history_row_count", "history_first_utc", "history_last_utc"])}

## Local Sidecar Windows

{md_table(windows_df, ["family", "row_count", "symbol_count", "first_date_utc", "last_date_utc"])}

Control overlap:

{md_table(rebalance_overlap_df, ["family", "control_rebalance_overlap_count", "position_decision_overlap_count"])}

## Liquidity Bucket Coverage

Top bucket only:

{md_table(top_bucket_view, ["family", "active_rows", "covered_rows", "coverage_ratio", "overlap_active_rows", "overlap_covered_rows", "overlap_coverage_ratio"])}

## Output Artifacts

- `{paths.out_root / "phase0_summary.json"}`
- `{paths.out_root / "endpoint_status.csv"}`
- `{paths.out_root / "key_scope_status.csv"}`
- `{paths.out_root / "sidecar_history_windows.csv"}`
- `{paths.out_root / "sidecar_coverage_by_symbol.csv"}`
- `{paths.out_root / "sidecar_coverage_by_liquidity_bucket.csv"}`
- `{paths.out_root / "family_rebalance_overlap.csv"}`
- `{paths.out_root / "pit_lag_policy.csv"}`
"""
    paths.doc_path.write_text(report, encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = make_paths(args)
    paths.out_root.mkdir(parents=True, exist_ok=True)

    matrix = read_json(paths.matrix_path)
    key_df = collect_key_scope_status()
    endpoint_df = endpoint_rows(matrix)

    rebalance, universe, positions, live_symbols = read_control_inputs(paths)
    universe_active = universe[bool_series(universe["universe_active"])].copy()
    universe_active["symbol"] = universe_active["usdm_symbol"]
    all_symbols = sorted(
        set(live_symbols)
        | set(universe_active["symbol"].dropna().astype(str))
        | set(positions["usdm_symbol"].dropna().astype(str))
    )

    coinglass_root = paths.repo_root / "artifacts" / "quant_research" / "coinglass"
    micro_1d_path = coinglass_root / "microstructure_panel_1d.csv.gz"
    participant_1d_path = coinglass_root / "participant_panel_1d.csv.gz"
    micro_1d = read_optional_csv(micro_1d_path)
    participant_1d = read_optional_csv(participant_1d_path)
    derivatives_1d = read_derivatives_1d(paths, all_symbols)

    family_frames = {
        "liquidation": micro_1d,
        "orderbook": micro_1d,
        "taker_flow": micro_1d,
        "global_long_short": participant_1d,
        "top_trader": participant_1d,
        "funding_oi": derivatives_1d,
    }
    family_sources = {
        "liquidation": micro_1d_path,
        "orderbook": micro_1d_path,
        "taker_flow": micro_1d_path,
        "global_long_short": participant_1d_path,
        "top_trader": participant_1d_path,
        "funding_oi": paths.market_history_root / "binance_derivatives" / "<symbol>" / "1d",
    }
    availabilities = {
        family: family_availability(frame, family) for family, frame in family_frames.items()
    }

    windows_df = pd.DataFrame(
        [
            summarize_window(
                availability,
                family,
                str(family_sources[family]),
            )
            for family, availability in availabilities.items()
        ]
    )
    symbol_df = symbol_coverage_rows(
        availabilities,
        all_symbols,
        set(live_symbols),
        universe_active,
        positions,
    )
    liquidity_df = liquidity_coverage_rows(availabilities, universe_active)
    rebalance_overlap_df = family_rebalance_overlap_rows(
        windows_df,
        sorted(rebalance["date_utc"].dropna().astype(str).unique()),
        sorted(positions["date_utc"].dropna().astype(str).unique()),
    )
    pit_df = pit_lag_rows(family_sources, family_frames)

    endpoint_required = endpoint_df[endpoint_df["required_for_phase0"]].copy()
    required_endpoint_success = (
        len(endpoint_required) == len(REQUIRED_ENDPOINTS)
        and endpoint_required["status"].eq("success").all()
        and ~endpoint_required["classification"].eq("blocked_or_short_history").any()
    )
    key_present = key_df[(key_df["present"]) & (key_df["name"].isin(["CoinglassAPI", "COINGLASSAPI"]))]
    process_key_present = not key_present[key_present["scope"].eq("Process")].empty
    user_key_present = not key_present[key_present["scope"].eq("User")].empty

    control_first = str(rebalance["date_utc"].min())
    control_last = str(rebalance["date_utc"].max())
    control_span_days = int(
        (
            pd.to_datetime(control_last, utc=True)
            - pd.to_datetime(control_first, utc=True)
        ).days
    )
    endpoint_history_days = {}
    for row in endpoint_required.to_dict("records"):
        days = row.get("history_days")
        endpoint_history_days[row["endpoint_id"]] = None if pd.isna(days) else int(days)
    endpoint_full_control_window_verified = all(
        days is not None and days >= control_span_days for days in endpoint_history_days.values()
    )
    family_full_window = {}
    family_overlap_counts = {}
    for row in windows_df.to_dict("records"):
        family = row["family"]
        first_date = row["first_date_utc"]
        last_date = row["last_date_utc"]
        full = bool(first_date and last_date and first_date <= control_first and last_date >= control_last)
        family_full_window[family] = full
        overlap = rebalance_overlap_df[
            rebalance_overlap_df["family"].eq(family)
        ]["control_rebalance_overlap_count"]
        family_overlap_counts[family] = int(overlap.iloc[0]) if not overlap.empty else 0

    live_symbol_family_gaps = []
    for family in CORE_FAMILIES:
        family_symbol_df = symbol_df[
            symbol_df["family"].eq(family) & symbol_df["live_fixed20"].eq(True)
        ]
        missing = sorted(family_symbol_df[family_symbol_df["available_day_count"].eq(0)]["symbol"])
        if missing:
            live_symbol_family_gaps.append({"family": family, "missing_live_symbols": missing})

    explicit_available_at_all = pit_df["explicit_available_at_column"].all()
    min_overlap_rebalances = min(family_overlap_counts.values()) if family_overlap_counts else 0
    live_core_covered = not live_symbol_family_gaps
    local_full_window_supported = all(family_full_window.get(family, False) for family in CORE_FAMILIES)
    provider_sidecar_h10d_phase0_ready = bool(
        process_key_present
        and required_endpoint_success
        and endpoint_full_control_window_verified
        and live_core_covered
        and local_full_window_supported
        and explicit_available_at_all
    )
    overlap_only_diagnostic_ready = bool(
        (process_key_present or user_key_present)
        and required_endpoint_success
        and live_core_covered
        and min_overlap_rebalances >= 20
    )

    blockers = []
    if not process_key_present:
        blockers.append("CoinGlass API key is not present in the current process environment.")
    if not required_endpoint_success:
        blockers.append("One or more required futures sidecar endpoints failed the current smoke audit.")
    if not endpoint_full_control_window_verified:
        blockers.append(
            f"Current endpoint smoke does not verify the full {control_span_days}-day frozen-control "
            f"history window; observed required endpoint history days: {endpoint_history_days}."
        )
    if live_symbol_family_gaps:
        blockers.append(f"Live fixed-20 symbol coverage gaps exist: {live_symbol_family_gaps}.")
    if not local_full_window_supported:
        blockers.append(
            f"Local sidecar history does not cover the full frozen-control window "
            f"{control_first} to {control_last}; family full-window flags: {family_full_window}."
        )
    if not explicit_available_at_all:
        blockers.append(
            "Local sidecar panels have no explicit provider available_at timestamp; Phase 1 must encode "
            "a conservative lag before any PIT-safe paired comparison."
        )

    summary = {
        "status_id": "provider_sidecar_h10d_phase0_ready",
        "provider_sidecar_h10d_phase0_ready": provider_sidecar_h10d_phase0_ready,
        "overlap_only_diagnostic_ready": overlap_only_diagnostic_ready,
        "generated_local_date": "2026-05-18",
        "frozen_control": "hv_balanced",
        "live_config_changed": False,
        "coinglass_matrix_path": str(paths.matrix_path),
        "endpoint_generated_at_utc": matrix.get("generated_at_utc"),
        "endpoint_count": int(len(endpoint_df)),
        "required_endpoint_success": bool(required_endpoint_success),
        "endpoint_full_control_window_verified": bool(endpoint_full_control_window_verified),
        "endpoint_history_days_observed": endpoint_history_days,
        "required_endpoints": sorted(REQUIRED_ENDPOINTS),
        "process_key_present": bool(process_key_present),
        "user_key_present": bool(user_key_present),
        "live_fixed20_count": len(live_symbols),
        "live_fixed20_symbols": live_symbols,
        "control_rebalance_count": int(rebalance["date_utc"].nunique()),
        "control_first_date_utc": control_first,
        "control_last_date_utc": control_last,
        "control_span_days": control_span_days,
        "position_decision_count": int(positions["date_utc"].nunique()),
        "pit_active_symbol_count": int(universe_active["symbol"].nunique()),
        "family_full_window_supported": family_full_window,
        "family_rebalance_overlap_counts": family_overlap_counts,
        "minimum_family_rebalance_overlap_count": int(min_overlap_rebalances),
        "live_core_covered": bool(live_core_covered),
        "live_symbol_family_gaps": live_symbol_family_gaps,
        "explicit_available_at_all_core_families": bool(explicit_available_at_all),
        "pit_lag_status": "needs_conservative_lag_encoding"
        if not explicit_available_at_all
        else "explicit_available_at_present",
        "blockers": blockers,
        "artifact_paths": {
            "summary": str(paths.out_root / "phase0_summary.json"),
            "endpoint_status": str(paths.out_root / "endpoint_status.csv"),
            "key_scope_status": str(paths.out_root / "key_scope_status.csv"),
            "sidecar_history_windows": str(paths.out_root / "sidecar_history_windows.csv"),
            "sidecar_coverage_by_symbol": str(paths.out_root / "sidecar_coverage_by_symbol.csv"),
            "sidecar_coverage_by_liquidity_bucket": str(
                paths.out_root / "sidecar_coverage_by_liquidity_bucket.csv"
            ),
            "family_rebalance_overlap": str(paths.out_root / "family_rebalance_overlap.csv"),
            "pit_lag_policy": str(paths.out_root / "pit_lag_policy.csv"),
            "report": str(paths.doc_path),
        },
    }

    key_df.to_csv(paths.out_root / "key_scope_status.csv", index=False)
    endpoint_df.to_csv(paths.out_root / "endpoint_status.csv", index=False)
    windows_df.to_csv(paths.out_root / "sidecar_history_windows.csv", index=False)
    symbol_df.to_csv(paths.out_root / "sidecar_coverage_by_symbol.csv", index=False)
    liquidity_df.to_csv(paths.out_root / "sidecar_coverage_by_liquidity_bucket.csv", index=False)
    rebalance_overlap_df.to_csv(paths.out_root / "family_rebalance_overlap.csv", index=False)
    pit_df.to_csv(paths.out_root / "pit_lag_policy.csv", index=False)
    write_json(paths.out_root / "phase0_summary.json", summary)
    write_report(
        paths,
        summary,
        endpoint_df,
        key_df,
        windows_df,
        rebalance_overlap_df,
        liquidity_df,
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
