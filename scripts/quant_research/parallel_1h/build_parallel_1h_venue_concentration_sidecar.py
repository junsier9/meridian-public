from __future__ import annotations

import argparse
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
HOUR_MS = 60 * 60 * 1000
CONTRACT_VERSION = "parallel_1h_venue_concentration_sidecar_builder.v1"
RESEARCH_ID = "venue_concentration_1h_sidecar"
DEFAULT_TOP30_BASES: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "DOGE",
    "ZEC",
    "BNB",
    "TAO",
    "TRX",
    "ADA",
    "PEPE",
    "PAXG",
    "SUI",
    "LINK",
    "AVAX",
    "LTC",
    "FET",
    "NEAR",
    "ENA",
    "AAVE",
    "WLD",
    "TON",
    "PENGU",
    "TRUMP",
    "KITE",
    "UNI",
    "DASH",
    "XPL",
    "BCH",
    "ASTER",
)
VENUES: tuple[str, ...] = ("binance", "coinbase", "okex", "bybitspot")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a pre-concordance 1h venue concentration sidecar from local "
            "CoinAPI per-exchange spot OHLCV caches."
        )
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--subjects", default=",".join(DEFAULT_TOP30_BASES))
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser


def _resolve_external_root(value: Path | None) -> Path:
    if value is not None:
        return value
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _venue_root(external_root: Path, venue: str) -> Path:
    if venue == "binance":
        return external_root / "market_history" / "coinapi_ohlcv"
    if venue == "coinbase":
        return external_root / "coinapi_ohlcv_COINBASE"
    if venue == "okex":
        return external_root / "coinapi_ohlcv_OKEX"
    if venue == "bybitspot":
        return external_root / "coinapi_ohlcv_BYBITSPOT"
    raise ValueError(f"unknown venue {venue!r}")


def _parse_subjects(text: str) -> list[str]:
    values = [item.strip().upper() for item in str(text or "").split(",") if item.strip()]
    return values or list(DEFAULT_TOP30_BASES)


def _load_venue_symbol(
    *,
    external_root: Path,
    venue: str,
    symbol: str,
    interval: str,
    generated_at_ms: int,
) -> pd.DataFrame:
    folder = _venue_root(external_root, venue) / "spot" / symbol / interval
    if not folder.exists():
        return pd.DataFrame()
    paths = sorted(folder.glob("*.csv.gz"))
    if not paths:
        return pd.DataFrame()
    wanted = [
        "symbol",
        "interval",
        "open_time_ms",
        "close_time_ms",
        "close",
        "volume",
        "quote_volume",
        "source",
    ]
    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            header = pd.read_csv(path, nrows=0).columns
            usecols = [column for column in wanted if column in set(header)]
            if "open_time_ms" not in usecols:
                continue
            frame = pd.read_csv(path, usecols=usecols)
        except Exception:
            continue
        if frame.empty:
            continue
        frame["venue"] = venue
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["open_time_ms"] = pd.to_numeric(out["open_time_ms"], errors="coerce")
    out["close_time_ms"] = pd.to_numeric(out.get("close_time_ms"), errors="coerce")
    out["quote_volume"] = pd.to_numeric(out.get("quote_volume"), errors="coerce")
    out["volume"] = pd.to_numeric(out.get("volume"), errors="coerce")
    out["close"] = pd.to_numeric(out.get("close"), errors="coerce")
    out = out.dropna(subset=["open_time_ms"])
    out["open_time_ms"] = out["open_time_ms"].astype("int64")
    if "close_time_ms" in out.columns:
        out = out.loc[out["close_time_ms"].fillna(0).le(generated_at_ms)].copy()
    out = out.drop_duplicates(["open_time_ms", "venue"], keep="last")
    out["subject"] = symbol.removesuffix("USDT")
    out["symbol"] = symbol
    out["quote_volume_usd"] = out["quote_volume"]
    return out[
        [
            "subject",
            "symbol",
            "open_time_ms",
            "close_time_ms",
            "venue",
            "close",
            "volume",
            "quote_volume_usd",
            "source",
        ]
    ]


def _load_raw(
    *,
    external_root: Path,
    subjects: list[str],
    interval: str,
    generated_at_ms: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    availability: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        symbol = f"{subject}USDT"
        availability[subject] = {}
        for venue in VENUES:
            frame = _load_venue_symbol(
                external_root=external_root,
                venue=venue,
                symbol=symbol,
                interval=interval,
                generated_at_ms=generated_at_ms,
            )
            availability[subject][venue] = {
                "row_count": int(len(frame)),
                "has_rows": bool(not frame.empty),
                "min_open_time_ms": int(frame["open_time_ms"].min()) if not frame.empty else None,
                "max_open_time_ms": int(frame["open_time_ms"].max()) if not frame.empty else None,
            }
            if not frame.empty:
                frames.append(frame)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return raw, availability


def _expected_venue_count_by_subject(availability: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        subject: int(sum(1 for venue in VENUES if details.get(venue, {}).get("has_rows")))
        for subject, details in availability.items()
    }


def _build_sidecar(raw: pd.DataFrame, availability: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    expected_count = _expected_venue_count_by_subject(availability)
    local = raw.copy()
    local["quote_volume_usd"] = pd.to_numeric(local["quote_volume_usd"], errors="coerce")
    local = local.loc[local["quote_volume_usd"].fillna(0.0).gt(0.0)].copy()
    if local.empty:
        return pd.DataFrame()
    total = (
        local.groupby(["subject", "symbol", "open_time_ms"], as_index=False)["quote_volume_usd"]
        .sum()
        .rename(columns={"quote_volume_usd": "total_quote_volume_usd"})
    )
    with_total = local.merge(total, on=["subject", "symbol", "open_time_ms"], how="left")
    with_total["venue_quote_volume_share"] = (
        with_total["quote_volume_usd"] / with_total["total_quote_volume_usd"].replace(0.0, np.nan)
    )

    rows: list[dict[str, Any]] = []
    for key, group in with_total.groupby(["subject", "symbol", "open_time_ms"], sort=True):
        subject, symbol, open_time_ms = key
        shares = group.set_index("venue")["venue_quote_volume_share"].astype(float)
        volumes = group.set_index("venue")["quote_volume_usd"].astype(float)
        closes = group.set_index("venue")["close"].astype(float)
        observed_venues = sorted(shares.index.astype(str).tolist())
        top_venue = str(shares.idxmax()) if not shares.empty else None
        close_time_ms = int(group["close_time_ms"].dropna().max()) if group["close_time_ms"].notna().any() else None
        row: dict[str, Any] = {
            "subject": subject,
            "symbol": symbol,
            "timestamp_ms": int(open_time_ms),
            "open_time_ms": int(open_time_ms),
            "close_time_ms": close_time_ms,
            "date_hour_utc": datetime.fromtimestamp(int(open_time_ms) / 1000, tz=timezone.utc).isoformat(),
            "configured_venue_count": int(len(VENUES)),
            "locally_listed_venue_count": int(expected_count.get(str(subject), 0)),
            "observed_venue_count": int(len(observed_venues)),
            "missing_listed_venue_count": int(max(expected_count.get(str(subject), 0) - len(observed_venues), 0)),
            "observed_venues": ",".join(observed_venues),
            "total_quote_volume_usd": float(group["total_quote_volume_usd"].iloc[0]),
            "top_venue": top_venue,
            "top_venue_quote_volume_share": float(shares.max()) if not shares.empty else np.nan,
            "venue_share_hhi": float((shares**2).sum()) if not shares.empty else np.nan,
            "non_binance_quote_volume_share": float(1.0 - shares.get("binance", 0.0)),
            "binance_quote_volume_share": float(shares.get("binance", np.nan)),
            "coinbase_quote_volume_share": float(shares.get("coinbase", np.nan)),
            "okex_quote_volume_share": float(shares.get("okex", np.nan)),
            "bybitspot_quote_volume_share": float(shares.get("bybitspot", np.nan)),
            "binance_close": float(closes.get("binance", np.nan)),
            "coinbase_close": float(closes.get("coinbase", np.nan)),
            "okex_close": float(closes.get("okex", np.nan)),
            "bybitspot_close": float(closes.get("bybitspot", np.nan)),
            "data_trust_status": "pre_concordance",
            "research_validation_status": "not_started",
        }
        for venue in VENUES:
            row[f"{venue}_quote_volume_usd"] = float(volumes.get(venue, np.nan))
        rows.append(row)
    sidecar = pd.DataFrame(rows)
    return sidecar.sort_values(["subject", "open_time_ms"]).reset_index(drop=True)


def _coverage_summary(sidecar: pd.DataFrame, raw: pd.DataFrame, availability: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if sidecar.empty:
        return {"row_count": 0, "subject_count": 0}
    by_subject: dict[str, Any] = {}
    for subject, group in sidecar.groupby("subject"):
        by_subject[str(subject)] = {
            "row_count": int(len(group)),
            "min_open_time_ms": int(group["open_time_ms"].min()),
            "max_open_time_ms": int(group["open_time_ms"].max()),
            "min_open_time_utc": datetime.fromtimestamp(
                int(group["open_time_ms"].min()) / 1000, tz=timezone.utc
            ).isoformat(),
            "max_open_time_utc": datetime.fromtimestamp(
                int(group["open_time_ms"].max()) / 1000, tz=timezone.utc
            ).isoformat(),
            "mean_observed_venue_count": float(group["observed_venue_count"].mean()),
            "min_observed_venue_count": int(group["observed_venue_count"].min()),
            "max_observed_venue_count": int(group["observed_venue_count"].max()),
            "mean_top_venue_share": float(group["top_venue_quote_volume_share"].mean()),
            "top_venue_counts": {
                str(k): int(v) for k, v in group["top_venue"].value_counts(dropna=False).items()
            },
        }
    return {
        "row_count": int(len(sidecar)),
        "subject_count": int(sidecar["subject"].nunique()),
        "raw_venue_row_count": int(len(raw)),
        "min_open_time_ms": int(sidecar["open_time_ms"].min()),
        "max_open_time_ms": int(sidecar["open_time_ms"].max()),
        "min_open_time_utc": datetime.fromtimestamp(
            int(sidecar["open_time_ms"].min()) / 1000, tz=timezone.utc
        ).isoformat(),
        "max_open_time_utc": datetime.fromtimestamp(
            int(sidecar["open_time_ms"].max()) / 1000, tz=timezone.utc
        ).isoformat(),
        "venue_row_count": {
            str(k): int(v) for k, v in raw["venue"].value_counts().sort_index().items()
        },
        "sidecar_rows_by_observed_venue_count": {
            str(k): int(v) for k, v in sidecar["observed_venue_count"].value_counts().sort_index().items()
        },
        "availability_by_subject": availability,
        "by_subject": by_subject,
    }


def _write_outputs(
    *,
    sidecar: pd.DataFrame,
    report: dict[str, Any],
    output_dir: Path,
    report_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / "venue_concentration_1h_sidecar.csv.gz"
    report_path = report_dir / "venue_concentration_1h_sidecar_build_report.json"
    with gzip.open(sidecar_path, "wt", encoding="utf-8", newline="") as handle:
        sidecar.to_csv(handle, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return sidecar_path, report_path


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    generated_at = datetime.now(tz=timezone.utc)
    generated_at_ms = int(generated_at.timestamp() * 1000)
    external_root = _resolve_external_root(args.external_root)
    subjects = _parse_subjects(args.subjects)
    raw, availability = _load_raw(
        external_root=external_root,
        subjects=subjects,
        interval=str(args.interval),
        generated_at_ms=generated_at_ms,
    )
    sidecar = _build_sidecar(raw, availability)
    coverage = _coverage_summary(sidecar, raw, availability)
    output_dir = args.output_dir or (
        ROOT / "artifacts" / "quant_research" / "sidecars" / "venue_concentration_1h"
    )
    report_dir = args.report_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    decision = {
        "label": "pass_data_unlock" if not sidecar.empty else "blocked",
        "sidecar_build_status": "built_pre_concordance" if not sidecar.empty else "blocked_by_data",
        "alpha_validation_status": "not_started",
        "provider_concordance_status": "not_started",
        "fake_liquidity_retry_allowed": False,
        "alpha_rerun_allowed": False,
        "h10d_promotion_state_mutation": False,
        "reason": (
            "Raw 1h venue volume can now be transformed into venue concentration fields, "
            "but this sidecar is pre-concordance and cannot be used for admission yet."
        )
        if not sidecar.empty
        else "No sidecar rows could be built.",
    }
    report: dict[str, Any] = {
        "artifact_family": "parallel_1h_alpha_mining_data_sidecar",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": generated_at.isoformat(),
        "as_of": str(args.as_of),
        "external_root": str(external_root),
        "interval": str(args.interval),
        "subjects": subjects,
        "venues": list(VENUES),
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "feature_definitions": {
            "top_venue_quote_volume_share": "max venue quote_volume_usd / total venue quote_volume_usd per symbol-hour",
            "venue_share_hhi": "sum of squared venue quote-volume shares per symbol-hour",
            "observed_venue_count": "venues with positive local CoinAPI quote volume at the symbol-hour",
            "missing_listed_venue_count": "venues with local 1h history for the symbol but no positive row at the hour",
            "non_binance_quote_volume_share": "1 - Binance quote-volume share when Binance is observed",
        },
        "coverage_summary": coverage,
        "data_quality_boundaries": [
            "CoinAPI coverage is a data unlock, not provider concordance.",
            "CoinGlass spot strict OHLC mismatch remains a separate fail-closed boundary.",
            "Native exchange API concordance should be run before any alpha rerun.",
            "The sidecar is spot-volume based; perp venue concentration and depth require separate sidecars.",
        ],
        "pass_fail_decision": decision,
        "next_landing_shape": {
            "next_required_step": "Run venue-volume concordance against native OKX/Bybit/Binance samples.",
            "allowed_research_after_concordance": "retry fake-liquidity capacity haircut as selector/exposure layer only",
        },
    }
    sidecar_path, report_path = _write_outputs(
        sidecar=sidecar,
        report=report,
        output_dir=output_dir,
        report_dir=report_dir,
    )
    compact = {
        "research_id": RESEARCH_ID,
        "sidecar_path": str(sidecar_path),
        "report_path": str(report_path),
        "row_count": coverage.get("row_count"),
        "subject_count": coverage.get("subject_count"),
        "min_open_time_utc": coverage.get("min_open_time_utc"),
        "max_open_time_utc": coverage.get("max_open_time_utc"),
        "venue_row_count": coverage.get("venue_row_count"),
        "sidecar_rows_by_observed_venue_count": coverage.get("sidecar_rows_by_observed_venue_count"),
        "pass_fail_decision": decision,
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
