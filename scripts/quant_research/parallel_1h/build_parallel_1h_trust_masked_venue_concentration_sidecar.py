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
CONTRACT_VERSION = "parallel_1h_trust_masked_venue_concentration_sidecar_builder.v1"
RESEARCH_ID = "trust_masked_venue_concentration_1h"
TRUSTED_VENUES: tuple[str, ...] = ("binance_direct", "okex", "bybitspot")
EXCLUDED_VENUES: tuple[str, ...] = ("coinbase",)
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a trust-masked 1h venue concentration sidecar. Binance uses "
            "the direct Binance cache, OKEX is trusted by the native-concordance "
            "sample, Bybit is fail-closed except sampled-pass symbols, and "
            "Coinbase is excluded."
        )
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--subjects", default=",".join(DEFAULT_TOP30_BASES))
    parser.add_argument("--interval", default="1h")
    parser.add_argument(
        "--bybit-policy",
        choices=("sampled_pass_only", "exclude_all", "include_all_for_debug"),
        default="sampled_pass_only",
    )
    parser.add_argument("--concordance-report", type=Path, default=None)
    parser.add_argument("--concordance-details", type=Path, default=None)
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


def _parse_subjects(text: str) -> list[str]:
    values = [item.strip().upper() for item in str(text or "").split(",") if item.strip()]
    return values or list(DEFAULT_TOP30_BASES)


def _default_report_dir(as_of: str) -> Path:
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{as_of}-parallel-1h-alpha-stage0"
    )


def _default_concordance_report(as_of: str) -> Path:
    return _default_report_dir(as_of) / "venue_volume_native_concordance_1h.json"


def _default_concordance_details(as_of: str) -> Path:
    return _default_report_dir(as_of) / "venue_volume_native_concordance_1h_details.csv.gz"


def _venue_root(external_root: Path, venue: str) -> Path:
    if venue == "binance_direct":
        return external_root / "market_history" / "binance_ohlcv"
    if venue == "okex":
        return external_root / "coinapi_ohlcv_OKEX"
    if venue == "bybitspot":
        return external_root / "coinapi_ohlcv_BYBITSPOT"
    raise ValueError(f"unknown venue {venue!r}")


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
        "exchange",
        "market_type",
        "symbol",
        "interval",
        "open_time_ms",
        "close_time_ms",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "source",
    ]
    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            header = pd.read_csv(path, nrows=0).columns
            header_set = set(header)
            usecols = [column for column in wanted if column in header_set]
            if "open_time_ms" not in usecols:
                continue
            frame = pd.read_csv(path, usecols=usecols)
        except Exception:
            continue
        if frame.empty:
            continue
        frame["venue"] = venue
        frame["source_file"] = str(path)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["open_time_ms"] = pd.to_numeric(out["open_time_ms"], errors="coerce")
    out["close_time_ms"] = pd.to_numeric(out.get("close_time_ms"), errors="coerce")
    out["quote_volume"] = pd.to_numeric(out.get("quote_volume"), errors="coerce")
    out["volume"] = pd.to_numeric(out.get("volume"), errors="coerce")
    out["close"] = pd.to_numeric(out.get("close"), errors="coerce")
    out["trade_count"] = pd.to_numeric(out.get("trade_count"), errors="coerce")
    out = out.dropna(subset=["open_time_ms"])
    out["open_time_ms"] = out["open_time_ms"].astype("int64")
    out = out.loc[out["close_time_ms"].fillna(0).le(generated_at_ms)].copy()
    out = out.drop_duplicates(["open_time_ms", "venue"], keep="last")
    out["subject"] = symbol.removesuffix("USDT")
    out["symbol"] = symbol
    out["quote_volume_usd"] = out["quote_volume"]
    if "source" not in out.columns:
        out["source"] = ""
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
            "trade_count",
            "source",
        ]
    ]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _load_bybit_trust(
    *,
    subjects: list[str],
    policy: str,
    concordance_report: Path,
    concordance_details: Path,
) -> dict[str, Any]:
    sampled: dict[str, dict[str, Any]] = {}
    report_exists = concordance_report.exists()
    details_exists = concordance_details.exists()
    if report_exists:
        payload = json.loads(concordance_report.read_text(encoding="utf-8"))
        for item in payload.get("by_venue_symbol", []):
            if item.get("venue") != "bybitspot":
                continue
            symbol = str(item.get("symbol", "")).upper()
            subject = symbol.removesuffix("USDT")
            actual_quote = item.get("actual_quote_rel_error") or {}
            base_volume = item.get("base_volume_rel_error") or {}
            status = "sampled_pass" if bool(item.get("passed")) else "sampled_fail"
            if status == "sampled_fail" and _safe_float(actual_quote.get("max")) is not None:
                if float(actual_quote.get("max")) > 0.05:
                    status = "sampled_fail_outlier"
            sampled[subject] = {
                "symbol": symbol,
                "passed": bool(item.get("passed")),
                "trust_status": status,
                "api_status": item.get("api_status"),
                "matched_rows": item.get("matched_rows"),
                "actual_quote_rel_error_p95": _safe_float(actual_quote.get("p95")),
                "actual_quote_rel_error_max": _safe_float(actual_quote.get("max")),
                "base_volume_rel_error_p95": _safe_float(base_volume.get("p95")),
                "native_quote_volume_mode": item.get("native_quote_volume_mode"),
            }

    outlier_rows: list[dict[str, Any]] = []
    if details_exists:
        try:
            details = pd.read_csv(concordance_details)
            details = details.loc[details["venue"].eq("bybitspot")].copy()
            details["subject"] = details["symbol"].astype(str).str.removesuffix("USDT")
            details["actual_quote_rel_error"] = pd.to_numeric(
                details["actual_quote_rel_error"], errors="coerce"
            )
            failed_subjects = {
                subject
                for subject, item in sampled.items()
                if not bool(item.get("passed"))
            }
            details = details.loc[details["subject"].isin(failed_subjects)].copy()
            details = details.sort_values("actual_quote_rel_error", ascending=False).head(20)
            for _, row in details.iterrows():
                outlier_rows.append(
                    {
                        "subject": str(row.get("subject")),
                        "symbol": str(row.get("symbol")),
                        "open_time_ms": int(row["open_time_ms"]),
                        "open_time_utc": datetime.fromtimestamp(
                            int(row["open_time_ms"]) / 1000, tz=timezone.utc
                        ).isoformat(),
                        "actual_quote_rel_error": _safe_float(row.get("actual_quote_rel_error")),
                        "local_quote_volume": _safe_float(row.get("quote_volume")),
                        "native_actual_quote_volume": _safe_float(
                            row.get("native_actual_quote_volume")
                        ),
                        "local_base_volume": _safe_float(row.get("local_base_volume")),
                        "native_base_volume": _safe_float(row.get("native_base_volume")),
                    }
                )
        except Exception as exc:
            outlier_rows.append({"error": f"failed_to_read_details: {exc}"})

    trust_by_subject: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        sampled_item = sampled.get(subject)
        if policy == "exclude_all":
            trusted = False
            status = "policy_exclude_all"
        elif policy == "include_all_for_debug":
            trusted = True
            status = "policy_include_all_for_debug"
        elif sampled_item is None:
            trusted = False
            status = "unsampled_fail_closed"
        else:
            trusted = bool(sampled_item.get("passed"))
            status = str(sampled_item.get("trust_status") or "sampled_fail")
        trust_by_subject[subject] = {
            "trusted_for_sidecar": trusted,
            "trust_status": status,
            "sampled_concordance": sampled_item,
        }

    return {
        "policy": policy,
        "concordance_report": str(concordance_report),
        "concordance_report_exists": report_exists,
        "concordance_details": str(concordance_details),
        "concordance_details_exists": details_exists,
        "sampled_subjects": sorted(sampled),
        "sampled_pass_subjects": sorted(
            subject for subject, item in sampled.items() if bool(item.get("passed"))
        ),
        "sampled_fail_subjects": sorted(
            subject for subject, item in sampled.items() if not bool(item.get("passed"))
        ),
        "included_subjects": sorted(
            subject
            for subject, item in trust_by_subject.items()
            if bool(item.get("trusted_for_sidecar"))
        ),
        "excluded_subjects": sorted(
            subject
            for subject, item in trust_by_subject.items()
            if not bool(item.get("trusted_for_sidecar"))
        ),
        "trust_by_subject": trust_by_subject,
        "outlier_attribution_rows": outlier_rows,
    }


def _trusted_for_subject(venue: str, subject: str, bybit_trust: dict[str, Any]) -> tuple[bool, str]:
    if venue == "binance_direct":
        return True, "direct_binance_cache_trusted"
    if venue == "okex":
        return True, "native_concordance_sample_pass_trusted"
    if venue == "bybitspot":
        entry = bybit_trust.get("trust_by_subject", {}).get(subject, {})
        return bool(entry.get("trusted_for_sidecar")), str(entry.get("trust_status") or "missing")
    raise ValueError(f"unknown venue {venue!r}")


def _load_raw(
    *,
    external_root: Path,
    subjects: list[str],
    interval: str,
    generated_at_ms: int,
    bybit_trust: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    availability: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        symbol = f"{subject}USDT"
        availability[subject] = {}
        for venue in TRUSTED_VENUES:
            frame = _load_venue_symbol(
                external_root=external_root,
                venue=venue,
                symbol=symbol,
                interval=interval,
                generated_at_ms=generated_at_ms,
            )
            trusted_allowed, trust_status = _trusted_for_subject(venue, subject, bybit_trust)
            include_rows = trusted_allowed and not frame.empty
            availability[subject][venue] = {
                "row_count": int(len(frame)),
                "has_rows": bool(not frame.empty),
                "trusted_allowed": bool(trusted_allowed),
                "included_in_sidecar": bool(include_rows),
                "trust_status": trust_status,
                "min_open_time_ms": int(frame["open_time_ms"].min()) if not frame.empty else None,
                "max_open_time_ms": int(frame["open_time_ms"].max()) if not frame.empty else None,
            }
            if include_rows:
                frame = frame.copy()
                frame["venue_trust_status"] = trust_status
                frames.append(frame)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return raw, availability


def _expected_counts(availability: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for subject, details in availability.items():
        trusted_eligible = sum(
            1 for venue in TRUSTED_VENUES if details.get(venue, {}).get("trusted_allowed")
        )
        locally_listed = sum(
            1
            for venue in TRUSTED_VENUES
            if details.get(venue, {}).get("trusted_allowed")
            and details.get(venue, {}).get("has_rows")
        )
        out[subject] = {
            "trusted_configured_venue_count": len(TRUSTED_VENUES),
            "trusted_eligible_venue_count": int(trusted_eligible),
            "trusted_locally_listed_venue_count": int(locally_listed),
        }
    return out


def _build_sidecar(
    raw: pd.DataFrame,
    availability: dict[str, dict[str, Any]],
    bybit_trust: dict[str, Any],
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    expected = _expected_counts(availability)
    local = raw.copy()
    local["quote_volume_usd"] = pd.to_numeric(local["quote_volume_usd"], errors="coerce")
    local = local.loc[local["quote_volume_usd"].fillna(0.0).gt(0.0)].copy()
    if local.empty:
        return pd.DataFrame()
    total = (
        local.groupby(["subject", "symbol", "open_time_ms"], as_index=False)["quote_volume_usd"]
        .sum()
        .rename(columns={"quote_volume_usd": "trusted_total_quote_volume_usd"})
    )
    with_total = local.merge(total, on=["subject", "symbol", "open_time_ms"], how="left")
    with_total["trusted_venue_quote_volume_share"] = (
        with_total["quote_volume_usd"]
        / with_total["trusted_total_quote_volume_usd"].replace(0.0, np.nan)
    )

    rows: list[dict[str, Any]] = []
    for key, group in with_total.groupby(["subject", "symbol", "open_time_ms"], sort=True):
        subject, symbol, open_time_ms = key
        subject = str(subject)
        shares = group.set_index("venue")["trusted_venue_quote_volume_share"].astype(float)
        volumes = group.set_index("venue")["quote_volume_usd"].astype(float)
        closes = group.set_index("venue")["close"].astype(float)
        trade_counts = group.set_index("venue")["trade_count"].astype(float)
        observed_venues = sorted(shares.index.astype(str).tolist())
        top_venue = str(shares.idxmax()) if not shares.empty else None
        close_time_ms = int(group["close_time_ms"].dropna().max()) if group["close_time_ms"].notna().any() else None
        expected_row = expected.get(subject, {})
        bybit_status = (
            bybit_trust.get("trust_by_subject", {}).get(subject, {}).get("trust_status")
            or "missing"
        )
        trusted_locally_listed = int(expected_row.get("trusted_locally_listed_venue_count", 0))
        row: dict[str, Any] = {
            "subject": subject,
            "symbol": symbol,
            "timestamp_ms": int(open_time_ms),
            "open_time_ms": int(open_time_ms),
            "close_time_ms": close_time_ms,
            "date_hour_utc": datetime.fromtimestamp(
                int(open_time_ms) / 1000, tz=timezone.utc
            ).isoformat(),
            "trusted_configured_venue_count": int(
                expected_row.get("trusted_configured_venue_count", len(TRUSTED_VENUES))
            ),
            "trusted_eligible_venue_count": int(
                expected_row.get("trusted_eligible_venue_count", 0)
            ),
            "trusted_locally_listed_venue_count": trusted_locally_listed,
            "trusted_observed_venue_count": int(len(observed_venues)),
            "trusted_missing_venue_count": int(max(trusted_locally_listed - len(observed_venues), 0)),
            "trusted_observed_venues": ",".join(observed_venues),
            "trusted_total_quote_volume_usd": float(
                group["trusted_total_quote_volume_usd"].iloc[0]
            ),
            "trusted_top_venue": top_venue,
            "trusted_top_venue_quote_volume_share": float(shares.max()) if not shares.empty else np.nan,
            "trusted_venue_share_hhi": float((shares**2).sum()) if not shares.empty else np.nan,
            "trusted_non_binance_quote_volume_share": float(1.0 - shares.get("binance_direct", 0.0)),
            "excluded_venues": ",".join(EXCLUDED_VENUES),
            "bybitspot_trust_policy": str(bybit_trust.get("policy")),
            "bybitspot_trust_status": str(bybit_status),
            "data_trust_status": "trust_masked_pre_alpha",
            "research_validation_status": "not_started",
        }
        for venue in TRUSTED_VENUES:
            row[f"{venue}_quote_volume_usd"] = float(volumes.get(venue, np.nan))
            row[f"{venue}_quote_volume_share"] = float(shares.get(venue, np.nan))
            row[f"{venue}_close"] = float(closes.get(venue, np.nan))
            row[f"{venue}_trade_count"] = float(trade_counts.get(venue, np.nan))
        rows.append(row)
    sidecar = pd.DataFrame(rows)
    return sidecar.sort_values(["subject", "open_time_ms"]).reset_index(drop=True)


def _coverage_summary(
    sidecar: pd.DataFrame,
    raw: pd.DataFrame,
    availability: dict[str, dict[str, Any]],
) -> dict[str, Any]:
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
            "mean_trusted_observed_venue_count": float(
                group["trusted_observed_venue_count"].mean()
            ),
            "min_trusted_observed_venue_count": int(
                group["trusted_observed_venue_count"].min()
            ),
            "max_trusted_observed_venue_count": int(
                group["trusted_observed_venue_count"].max()
            ),
            "mean_trusted_top_venue_share": float(
                group["trusted_top_venue_quote_volume_share"].mean()
            ),
            "trusted_top_venue_counts": {
                str(k): int(v)
                for k, v in group["trusted_top_venue"].value_counts(dropna=False).items()
            },
            "bybitspot_trust_status": str(group["bybitspot_trust_status"].iloc[0]),
        }
    return {
        "row_count": int(len(sidecar)),
        "subject_count": int(sidecar["subject"].nunique()),
        "raw_trusted_venue_row_count": int(len(raw)),
        "min_open_time_ms": int(sidecar["open_time_ms"].min()),
        "max_open_time_ms": int(sidecar["open_time_ms"].max()),
        "min_open_time_utc": datetime.fromtimestamp(
            int(sidecar["open_time_ms"].min()) / 1000, tz=timezone.utc
        ).isoformat(),
        "max_open_time_utc": datetime.fromtimestamp(
            int(sidecar["open_time_ms"].max()) / 1000, tz=timezone.utc
        ).isoformat(),
        "trusted_venue_row_count": {
            str(k): int(v) for k, v in raw["venue"].value_counts().sort_index().items()
        },
        "sidecar_rows_by_trusted_observed_venue_count": {
            str(k): int(v)
            for k, v in sidecar["trusted_observed_venue_count"].value_counts().sort_index().items()
        },
        "trusted_top_venue_counts": {
            str(k): int(v)
            for k, v in sidecar["trusted_top_venue"].value_counts(dropna=False).items()
        },
        "availability_by_subject": availability,
        "by_subject": by_subject,
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["pass_fail_decision"]
    coverage = report["coverage_summary"]
    bybit = report["provider_trust_policy"]["bybitspot"]
    lines = [
        "# Trust-Masked Venue Concentration 1h",
        "",
        f"- research_id: `{report['research_id']}`",
        f"- decision: `{decision['label']}`",
        f"- provider_concordance_status: `{decision['provider_concordance_status']}`",
        f"- alpha_rerun_allowed: `{decision['alpha_rerun_allowed']}`",
        f"- sidecar rows: `{coverage.get('row_count')}`",
        f"- subjects: `{coverage.get('subject_count')}`",
        f"- trusted venue row count: `{coverage.get('trusted_venue_row_count')}`",
        f"- observed-venue-count distribution: `{coverage.get('sidecar_rows_by_trusted_observed_venue_count')}`",
        "",
        "## Trust Mask",
        "",
        "- Binance: direct Binance cache under `market_history/binance_ohlcv/spot`; CoinAPI Binance excluded.",
        "- OKEX: included as trusted-by-sample from native concordance.",
        "- BybitSpot: included only for sampled-pass subjects under `sampled_pass_only`.",
        "- Coinbase: excluded because public candles lack native quote turnover in this audit.",
        "",
        "## Bybit Attribution",
        "",
        f"- sampled-pass subjects: `{bybit.get('sampled_pass_subjects')}`",
        f"- sampled-fail subjects: `{bybit.get('sampled_fail_subjects')}`",
        f"- included subjects: `{bybit.get('included_subjects')}`",
        f"- excluded subjects: `{bybit.get('excluded_subjects')}`",
        "",
        "Top Bybit outlier rows are stored in the JSON report.",
        "",
        "## Boundary",
        "",
        "This is a data-sidecar build, not an admitted alpha. Fake-liquidity retry remains blocked until a pre-registered Stage 0 evaluator consumes the trust-masked fields and passes falsification.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_outputs(
    *,
    sidecar: pd.DataFrame,
    report: dict[str, Any],
    output_dir: Path,
    report_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / "trust_masked_venue_concentration_1h.csv.gz"
    report_path = report_dir / "trust_masked_venue_concentration_1h_build_report.json"
    markdown_path = report_dir / "trust_masked_venue_concentration_1h_build_report.md"
    with gzip.open(sidecar_path, "wt", encoding="utf-8", newline="") as handle:
        sidecar.to_csv(handle, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _write_markdown(markdown_path, report)
    return sidecar_path, report_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    generated_at = datetime.now(tz=timezone.utc)
    generated_at_ms = int(generated_at.timestamp() * 1000)
    external_root = _resolve_external_root(args.external_root)
    subjects = _parse_subjects(args.subjects)
    report_dir = args.report_dir or _default_report_dir(str(args.as_of))
    concordance_report = args.concordance_report or _default_concordance_report(str(args.as_of))
    concordance_details = args.concordance_details or _default_concordance_details(str(args.as_of))
    bybit_trust = _load_bybit_trust(
        subjects=subjects,
        policy=str(args.bybit_policy),
        concordance_report=concordance_report,
        concordance_details=concordance_details,
    )
    raw, availability = _load_raw(
        external_root=external_root,
        subjects=subjects,
        interval=str(args.interval),
        generated_at_ms=generated_at_ms,
        bybit_trust=bybit_trust,
    )
    sidecar = _build_sidecar(raw, availability, bybit_trust)
    coverage = _coverage_summary(sidecar, raw, availability)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "sidecars"
        / "trust_masked_venue_concentration_1h"
    )
    sidecar_built = bool(not sidecar.empty)
    decision = {
        "label": "pass_data_sidecar_build" if sidecar_built else "blocked",
        "sidecar_build_status": "built_trust_masked_pre_alpha"
        if sidecar_built
        else "blocked_by_data",
        "alpha_validation_status": "not_started",
        "provider_concordance_status": "partial_pass_trust_masked"
        if sidecar_built
        else "blocked",
        "fake_liquidity_retry_allowed": False,
        "alpha_rerun_allowed": False,
        "h10d_promotion_state_mutation": False,
        "reason": (
            "Trusted data-side input exists after excluding Coinbase, replacing "
            "CoinAPI Binance with direct Binance cache, including OKEX, and "
            "fail-closing Bybit to sampled-pass symbols only. This is not alpha "
            "validation and cannot admit any rule by itself."
        )
        if sidecar_built
        else "No trust-masked sidecar rows could be built.",
        "next_landing_shape": (
            "Run a pre-registered fake-liquidity capacity Stage 0 retry using "
            "trusted_top_venue_quote_volume_share, trusted_venue_share_hhi, "
            "trusted_non_binance_quote_volume_share, and Bybit trust masks; "
            "then re-run shuffles, symbol holdout, buckets, delay robustness, "
            "funding drag, and slippage/capacity stress."
        ),
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
        "trusted_venues": list(TRUSTED_VENUES),
        "excluded_venues": list(EXCLUDED_VENUES),
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "provider_trust_policy": {
            "binance_direct": {
                "decision": "include",
                "source": str(external_root / "market_history" / "binance_ohlcv" / "spot"),
                "reason": "direct Binance cache/API lineage; replaces failed CoinAPI Binance volume leg",
            },
            "okex": {
                "decision": "include",
                "source": str(external_root / "coinapi_ohlcv_OKEX" / "spot"),
                "reason": "native exchange concordance sample passed 5/5 symbols",
            },
            "bybitspot": bybit_trust,
            "coinbase": {
                "decision": "exclude",
                "source": str(external_root / "coinapi_ohlcv_COINBASE" / "spot"),
                "reason": "public native audit lacked quote turnover and failed strict concordance",
            },
        },
        "feature_definitions": {
            "trusted_top_venue_quote_volume_share": "max trusted venue quote_volume_usd / total trusted venue quote_volume_usd per symbol-hour",
            "trusted_venue_share_hhi": "sum of squared trusted venue quote-volume shares per symbol-hour",
            "trusted_observed_venue_count": "trusted venues with positive quote volume at the symbol-hour",
            "trusted_missing_venue_count": "trusted local venues for the symbol without a positive row at the hour",
            "trusted_non_binance_quote_volume_share": "1 - direct Binance quote-volume share when direct Binance is observed",
            "bybitspot_trust_status": "sampled_pass, sampled_fail_outlier, unsampled_fail_closed, or policy status for Bybit inclusion",
        },
        "coverage_summary": coverage,
        "data_quality_boundaries": [
            "Coverage is not trustedness; trust is venue/source masked from native concordance evidence.",
            "Direct Binance replaces the failed CoinAPI Binance volume leg.",
            "OKEX is trusted by sample, not by universal proof.",
            "Bybit is not globally trusted; unsampled symbols and outlier-fail symbols are excluded.",
            "Coinbase is excluded until native quote-turnover concordance exists.",
            "This sidecar is spot-volume based and should only feed selector/exposure/capacity logic.",
        ],
        "pass_fail_decision": decision,
    }
    sidecar_path, report_path, markdown_path = _write_outputs(
        sidecar=sidecar,
        report=report,
        output_dir=output_dir,
        report_dir=report_dir,
    )
    compact = {
        "research_id": RESEARCH_ID,
        "sidecar_path": str(sidecar_path),
        "report_path": str(report_path),
        "markdown_path": str(markdown_path),
        "row_count": coverage.get("row_count"),
        "subject_count": coverage.get("subject_count"),
        "min_open_time_utc": coverage.get("min_open_time_utc"),
        "max_open_time_utc": coverage.get("max_open_time_utc"),
        "trusted_venue_row_count": coverage.get("trusted_venue_row_count"),
        "sidecar_rows_by_trusted_observed_venue_count": coverage.get(
            "sidecar_rows_by_trusted_observed_venue_count"
        ),
        "bybit_included_subjects": bybit_trust.get("included_subjects"),
        "bybit_excluded_subjects": bybit_trust.get("excluded_subjects"),
        "pass_fail_decision": decision,
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
