from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONTRACT_VERSION = "mf05_venue_local_data_gate.v1"
DEFAULT_AS_OF = "2026-05-07"
DEFAULT_SIDECAR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "sidecars"
    / "venue_concentration_1h"
    / "venue_concentration_1h_sidecar.csv.gz"
)
DEFAULT_REPORT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-mf05-venue-local-data-gate"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "R-5 MF-05 data-admission gate for the 1h venue-concentration sidecar. "
            "This audits provider trust before any venue-local alpha rerun."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--sidecar-path", type=Path, default=DEFAULT_SIDECAR)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--volume-median-threshold", type=float, default=0.05)
    parser.add_argument("--volume-p95-threshold", type=float, default=0.25)
    parser.add_argument("--close-p95-threshold", type=float, default=0.002)
    parser.add_argument("--min-common-row-fraction", type=float, default=0.80)
    return parser


def _resolve_external_root(value: Path | None) -> Path:
    if value is not None:
        return value
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _summarize_sidecar(sidecar: pd.DataFrame) -> dict[str, Any]:
    if sidecar.empty:
        return {"row_count": 0}
    trust_counts = (
        sidecar.get("data_trust_status", pd.Series(dtype="object")).fillna("missing").astype(str).value_counts()
    )
    validation_counts = (
        sidecar.get("research_validation_status", pd.Series(dtype="object"))
        .fillna("missing")
        .astype(str)
        .value_counts()
    )
    observed = pd.to_numeric(sidecar.get("observed_venue_count"), errors="coerce")
    out = {
        "row_count": int(len(sidecar)),
        "subject_count": int(sidecar["subject"].astype(str).nunique()) if "subject" in sidecar.columns else 0,
        "min_timestamp_ms": int(pd.to_numeric(sidecar["timestamp_ms"], errors="coerce").min())
        if "timestamp_ms" in sidecar.columns
        else None,
        "max_timestamp_ms": int(pd.to_numeric(sidecar["timestamp_ms"], errors="coerce").max())
        if "timestamp_ms" in sidecar.columns
        else None,
        "data_trust_status_counts": {str(k): int(v) for k, v in trust_counts.items()},
        "research_validation_status_counts": {str(k): int(v) for k, v in validation_counts.items()},
        "observed_venue_count_distribution": {
            str(int(k)): int(v) for k, v in observed.dropna().astype(int).value_counts().sort_index().items()
        },
        "multi_venue_row_fraction": float(observed.ge(2).mean()) if len(observed) else 0.0,
        "three_plus_venue_row_fraction": float(observed.ge(3).mean()) if len(observed) else 0.0,
        "four_venue_row_fraction": float(observed.ge(4).mean()) if len(observed) else 0.0,
    }
    if "top_venue" in sidecar.columns:
        counts = sidecar["top_venue"].fillna("missing").astype(str).value_counts()
        out["top_venue_counts"] = {str(k): int(v) for k, v in counts.items()}
    return out


def _load_ohlcv_folder(folder: Path) -> pd.DataFrame:
    if not folder.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    wanted = ["open_time_ms", "close_time_ms", "close", "quote_volume", "source"]
    for path in sorted(folder.glob("*.csv.gz")):
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
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["open_time_ms"] = pd.to_numeric(out["open_time_ms"], errors="coerce")
    out["close"] = pd.to_numeric(out.get("close"), errors="coerce")
    out["quote_volume"] = pd.to_numeric(out.get("quote_volume"), errors="coerce")
    out = out.dropna(subset=["open_time_ms"]).copy()
    out["open_time_ms"] = out["open_time_ms"].astype("int64")
    return out.drop_duplicates("open_time_ms", keep="last")


def _binance_native_folder(external_root: Path, symbol: str) -> Path:
    return external_root / "market_history" / "binance_ohlcv" / "spot" / symbol / "1h"


def _coinapi_binance_folder(external_root: Path, symbol: str) -> Path:
    return external_root / "market_history" / "coinapi_ohlcv" / "spot" / symbol / "1h"


def _compare_symbol(native: pd.DataFrame, coinapi: pd.DataFrame) -> pd.DataFrame:
    if native.empty or coinapi.empty:
        return pd.DataFrame()
    left = native[["open_time_ms", "close", "quote_volume"]].rename(
        columns={"close": "native_close", "quote_volume": "native_quote_volume"}
    )
    right = coinapi[["open_time_ms", "close", "quote_volume"]].rename(
        columns={"close": "coinapi_close", "quote_volume": "coinapi_quote_volume"}
    )
    merged = left.merge(right, on="open_time_ms", how="inner")
    if merged.empty:
        return merged
    close_denom = merged["native_close"].abs().replace(0.0, np.nan)
    volume_denom = merged["native_quote_volume"].abs().replace(0.0, np.nan)
    merged["close_abs_pct_diff"] = (merged["native_close"] - merged["coinapi_close"]).abs() / close_denom
    merged["quote_volume_abs_pct_diff"] = (
        (merged["native_quote_volume"] - merged["coinapi_quote_volume"]).abs() / volume_denom
    )
    return merged


def _safe_quantile(series: pd.Series, q: float) -> float | None:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    return float(values.quantile(float(q)))


def _safe_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    return float(values.mean())


def _binance_concordance(
    *,
    external_root: Path,
    subjects: list[str],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    by_subject: list[dict[str, Any]] = []
    all_rows: list[pd.DataFrame] = []
    for subject in subjects:
        symbol = f"{subject.upper()}USDT"
        native = _load_ohlcv_folder(_binance_native_folder(external_root, symbol))
        coinapi = _load_ohlcv_folder(_coinapi_binance_folder(external_root, symbol))
        common = _compare_symbol(native, coinapi)
        if not common.empty:
            local = common.copy()
            local["subject"] = subject
            all_rows.append(local)
        native_count = int(len(native))
        coinapi_count = int(len(coinapi))
        common_count = int(len(common))
        by_subject.append(
            {
                "subject": subject,
                "native_row_count": native_count,
                "coinapi_row_count": coinapi_count,
                "common_row_count": common_count,
                "common_vs_native_fraction": float(common_count / native_count) if native_count else 0.0,
                "close_abs_pct_diff_median": _safe_quantile(common.get("close_abs_pct_diff", pd.Series(dtype=float)), 0.5)
                if not common.empty
                else None,
                "close_abs_pct_diff_p95": _safe_quantile(common.get("close_abs_pct_diff", pd.Series(dtype=float)), 0.95)
                if not common.empty
                else None,
                "quote_volume_abs_pct_diff_median": _safe_quantile(
                    common.get("quote_volume_abs_pct_diff", pd.Series(dtype=float)),
                    0.5,
                )
                if not common.empty
                else None,
                "quote_volume_abs_pct_diff_p95": _safe_quantile(
                    common.get("quote_volume_abs_pct_diff", pd.Series(dtype=float)),
                    0.95,
                )
                if not common.empty
                else None,
            }
        )
    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    native_total = sum(row["native_row_count"] for row in by_subject)
    common_total = int(len(combined))
    summary = {
        "subject_count": int(len(subjects)),
        "native_total_rows": int(native_total),
        "common_row_count": common_total,
        "common_vs_native_fraction": float(common_total / native_total) if native_total else 0.0,
        "close_abs_pct_diff_mean": _safe_mean(combined.get("close_abs_pct_diff", pd.Series(dtype=float))),
        "close_abs_pct_diff_median": _safe_quantile(combined.get("close_abs_pct_diff", pd.Series(dtype=float)), 0.5),
        "close_abs_pct_diff_p95": _safe_quantile(combined.get("close_abs_pct_diff", pd.Series(dtype=float)), 0.95),
        "quote_volume_abs_pct_diff_mean": _safe_mean(
            combined.get("quote_volume_abs_pct_diff", pd.Series(dtype=float))
        ),
        "quote_volume_abs_pct_diff_median": _safe_quantile(
            combined.get("quote_volume_abs_pct_diff", pd.Series(dtype=float)),
            0.5,
        ),
        "quote_volume_abs_pct_diff_p95": _safe_quantile(
            combined.get("quote_volume_abs_pct_diff", pd.Series(dtype=float)),
            0.95,
        ),
    }
    checks = {
        "common_row_fraction_passed": summary["common_vs_native_fraction"] >= thresholds["min_common_row_fraction"],
        "close_p95_passed": (
            summary["close_abs_pct_diff_p95"] is not None
            and summary["close_abs_pct_diff_p95"] <= thresholds["close_p95_threshold"]
        ),
        "quote_volume_median_passed": (
            summary["quote_volume_abs_pct_diff_median"] is not None
            and summary["quote_volume_abs_pct_diff_median"] <= thresholds["volume_median_threshold"]
        ),
        "quote_volume_p95_passed": (
            summary["quote_volume_abs_pct_diff_p95"] is not None
            and summary["quote_volume_abs_pct_diff_p95"] <= thresholds["volume_p95_threshold"]
        ),
    }
    return {
        "thresholds": thresholds,
        "summary": summary,
        "checks": checks,
        "passed": bool(all(checks.values())),
        "by_subject": by_subject,
    }


def _native_multivenue_availability(external_root: Path) -> dict[str, Any]:
    candidates = {
        "okx_native": external_root / "market_history" / "okx",
        "bybit_native": external_root / "market_history" / "bybit",
        "coinbase_native": external_root / "market_history" / "coinbase",
        "coinapi_okex": external_root / "coinapi_ohlcv_OKEX",
        "coinapi_bybitspot": external_root / "coinapi_ohlcv_BYBITSPOT",
        "coinapi_coinbase": external_root / "coinapi_ohlcv_COINBASE",
    }
    return {
        label: {
            "path": str(path),
            "exists": bool(path.exists()),
            "role": "native_concordance_source" if "native" in label else "sidecar_input_source",
        }
        for label, path in candidates.items()
    }


def _decision(
    *,
    sidecar_summary: dict[str, Any],
    binance_concordance: dict[str, Any],
    native_multivenue: dict[str, Any],
) -> dict[str, Any]:
    trust_counts = sidecar_summary.get("data_trust_status_counts", {})
    validation_counts = sidecar_summary.get("research_validation_status_counts", {})
    native_sources = [
        label
        for label, payload in native_multivenue.items()
        if payload.get("role") == "native_concordance_source" and payload.get("exists")
    ]
    blockers: list[str] = []
    if trust_counts.get("pre_concordance", 0) == sidecar_summary.get("row_count", 0):
        blockers.append("sidecar_rows_pre_concordance")
    if validation_counts.get("not_started", 0) == sidecar_summary.get("row_count", 0):
        blockers.append("sidecar_research_validation_not_started")
    if not binance_concordance.get("passed"):
        blockers.append("binance_coinapi_volume_concordance_failed")
    if not native_sources:
        blockers.append("missing_native_okx_bybit_coinbase_concordance_sources")
    return {
        "label": "blocked_for_alpha_rerun" if blockers else "pass_data_gate",
        "alpha_rerun_allowed": not blockers,
        "mf05_stage0_allowed": not blockers,
        "blocker_codes": blockers,
        "native_multivenue_concordance_sources": native_sources,
        "reason": (
            "Venue concentration sidecar is not admissible for MF-05 alpha rerun until provider "
            "concordance and native multi-venue checks pass."
            if blockers
            else "Venue concentration sidecar passed the current data gate."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    sidecar_path = Path(args.sidecar_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mf05_venue_local_data_gate.json"
    sidecar = pd.read_csv(sidecar_path)
    subjects = sorted(sidecar["subject"].dropna().astype(str).str.upper().unique().tolist())
    external_root = _resolve_external_root(args.external_root)
    thresholds = {
        "volume_median_threshold": float(args.volume_median_threshold),
        "volume_p95_threshold": float(args.volume_p95_threshold),
        "close_p95_threshold": float(args.close_p95_threshold),
        "min_common_row_fraction": float(args.min_common_row_fraction),
    }
    sidecar_summary = _summarize_sidecar(sidecar)
    binance_concordance = _binance_concordance(
        external_root=external_root,
        subjects=subjects,
        thresholds=thresholds,
    )
    native_multivenue = _native_multivenue_availability(external_root)
    decision = _decision(
        sidecar_summary=sidecar_summary,
        binance_concordance=binance_concordance,
        native_multivenue=native_multivenue,
    )
    report = {
        "artifact_family": "mf05_venue_local_data_gate",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "sidecar_path": str(sidecar_path),
        "external_root": str(external_root),
        "sidecar_summary": sidecar_summary,
        "binance_coinapi_concordance": binance_concordance,
        "native_multivenue_availability": native_multivenue,
        "decision": decision,
    }
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote MF-05 venue-local data gate report to {output_path}")
    print(
        json.dumps(
            {
                "decision": decision,
                "sidecar_rows": sidecar_summary.get("row_count"),
                "multi_venue_row_fraction": sidecar_summary.get("multi_venue_row_fraction"),
                "binance_volume_median_abs_pct_diff": binance_concordance["summary"].get(
                    "quote_volume_abs_pct_diff_median"
                ),
                "binance_volume_p95_abs_pct_diff": binance_concordance["summary"].get(
                    "quote_volume_abs_pct_diff_p95"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
