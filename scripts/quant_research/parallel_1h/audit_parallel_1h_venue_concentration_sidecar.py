from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "parallel_1h_venue_concentration_sidecar_audit.v1"
RESEARCH_ID = "venue_concentration_1h_sidecar_discovery"
HOUR_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    root: Path
    provider: str
    venue_claim: str
    market_type_claim: str
    trust_note: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 1A data-side audit for a 1h venue-concentration sidecar. "
            "This is a fail-closed data unlock check, not an alpha evaluator."
        )
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--max-sample-files-per-interval",
        type=int,
        default=30,
        help=(
            "Read at most this many files per source/interval for field and timestamp checks. "
            "Partition and symbol counts remain exact."
        ),
    )
    return parser


def _resolve_external_root(value: Path | None) -> Path:
    if value is not None:
        return value
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _source_specs(external_root: Path) -> list[SourceSpec]:
    market_history = external_root / "market_history"
    return [
        SourceSpec(
            source_id="coinglass_extended",
            root=market_history / "coinglass_extended",
            provider="coinglass",
            venue_claim="binance_or_provider_aggregate",
            market_type_claim="usdm_perp_extended",
            trust_note="Useful 1h derivatives fields, but not a native multi-venue volume-share feed.",
        ),
        SourceSpec(
            source_id="binance_derivatives",
            root=market_history / "binance_derivatives",
            provider="binance",
            venue_claim="binance",
            market_type_claim="usdm_perp_funding_oi",
            trust_note="Single-venue derivatives funding/OI source; cannot identify venue concentration.",
        ),
        SourceSpec(
            source_id="binance_ohlcv",
            root=market_history / "binance_ohlcv",
            provider="binance",
            venue_claim="binance",
            market_type_claim="usdm_perp_ohlcv",
            trust_note="Single-venue Binance OHLCV source; useful as base volume, not concentration.",
        ),
        SourceSpec(
            source_id="coinapi_binance_spot",
            root=market_history / "coinapi_ohlcv",
            provider="coinapi",
            venue_claim="binance",
            market_type_claim="spot_ohlcv",
            trust_note="CoinAPI spot cache for Binance; only one venue by itself.",
        ),
        SourceSpec(
            source_id="coinglass_spot_ohlcv",
            root=market_history / "coinglass_spot_ohlcv",
            provider="coinglass",
            venue_claim="binance",
            market_type_claim="spot_ohlcv",
            trust_note=(
                "Spot coverage exists, but prior strict OHLC concordance remains a separate "
                "fail-closed trust boundary."
            ),
        ),
        SourceSpec(
            source_id="coinapi_coinbase_spot",
            root=external_root / "coinapi_ohlcv_COINBASE",
            provider="coinapi",
            venue_claim="coinbase",
            market_type_claim="spot_ohlcv",
            trust_note="Per-exchange CoinAPI cache; local fill is currently daily only.",
        ),
        SourceSpec(
            source_id="coinapi_okex_spot",
            root=external_root / "coinapi_ohlcv_OKEX",
            provider="coinapi",
            venue_claim="okex",
            market_type_claim="spot_ohlcv",
            trust_note="Per-exchange CoinAPI cache; local fill is currently daily only.",
        ),
        SourceSpec(
            source_id="coinapi_bybitspot_spot",
            root=external_root / "coinapi_ohlcv_BYBITSPOT",
            provider="coinapi",
            venue_claim="bybitspot",
            market_type_claim="spot_ohlcv",
            trust_note="Per-exchange CoinAPI cache; local fill is currently daily only.",
        ),
    ]


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _iso_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat()


def _read_header(path: Path) -> list[str]:
    try:
        return list(pd.read_csv(path, nrows=0).columns)
    except Exception:
        return []


def _interval_files(root: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    if not root.exists():
        return out
    for path in root.rglob("*.csv.gz"):
        interval = path.parent.name
        out.setdefault(interval, []).append(path)
    for files in out.values():
        files.sort()
    return dict(sorted(out.items()))


def _symbol_from_file(path: Path) -> str:
    try:
        return path.parent.parent.name
    except IndexError:
        return ""


def _summarize_files(files: list[Path], *, max_sample_files: int) -> dict[str, Any]:
    symbols = sorted({_symbol_from_file(path) for path in files if _symbol_from_file(path)})
    sampled_files = files[: max(1, int(max_sample_files))]
    header_union: set[str] = set()
    exchange_values: set[str] = set()
    market_type_values: set[str] = set()
    source_values: set[str] = set()
    row_count = 0
    min_open_ms: int | None = None
    max_open_ms: int | None = None
    volume_non_null = 0
    quote_volume_non_null = 0
    candidate_multi_exchange_rows: dict[tuple[str, int], set[str]] = {}

    for path in sampled_files:
        header = _read_header(path)
        if not header:
            continue
        header_union.update(header)
        wanted = [
            column
            for column in (
                "exchange",
                "market_type",
                "source",
                "symbol",
                "open_time_ms",
                "volume",
                "quote_volume",
            )
            if column in header
        ]
        if not wanted:
            continue
        try:
            frame = pd.read_csv(path, usecols=wanted)
        except Exception:
            continue
        row_count += int(len(frame))
        if "exchange" in frame.columns:
            exchange_values.update(str(v) for v in frame["exchange"].dropna().unique().tolist())
        if "market_type" in frame.columns:
            market_type_values.update(str(v) for v in frame["market_type"].dropna().unique().tolist())
        if "source" in frame.columns:
            source_values.update(str(v) for v in frame["source"].dropna().unique().tolist())
        if "open_time_ms" in frame.columns:
            open_ms = pd.to_numeric(frame["open_time_ms"], errors="coerce").dropna()
            if not open_ms.empty:
                local_min = int(open_ms.min())
                local_max = int(open_ms.max())
                min_open_ms = local_min if min_open_ms is None else min(min_open_ms, local_min)
                max_open_ms = local_max if max_open_ms is None else max(max_open_ms, local_max)
        if "volume" in frame.columns:
            volume_non_null += int(pd.to_numeric(frame["volume"], errors="coerce").notna().sum())
        if "quote_volume" in frame.columns:
            quote_volume_non_null += int(pd.to_numeric(frame["quote_volume"], errors="coerce").notna().sum())
        if {"exchange", "symbol", "open_time_ms"}.issubset(frame.columns):
            local = frame[["exchange", "symbol", "open_time_ms"]].dropna()
            if not local.empty:
                local["open_time_ms"] = pd.to_numeric(local["open_time_ms"], errors="coerce")
                local = local.dropna()
                for row in local.itertuples(index=False):
                    key = (str(row.symbol), int(row.open_time_ms))
                    candidate_multi_exchange_rows.setdefault(key, set()).add(str(row.exchange))

    multi_exchange_bar_count = sum(1 for values in candidate_multi_exchange_rows.values() if len(values) >= 2)
    closed_bar_timestamp_check = {
        "has_open_time_ms": "open_time_ms" in header_union,
        "min_open_time_ms": min_open_ms,
        "max_open_time_ms": max_open_ms,
        "min_open_time_utc": _iso_from_ms(min_open_ms),
        "max_open_time_utc": _iso_from_ms(max_open_ms),
        "appears_hourly_aligned": None,
    }
    if min_open_ms is not None and max_open_ms is not None:
        closed_bar_timestamp_check["appears_hourly_aligned"] = bool(
            min_open_ms % HOUR_MS == 0 and max_open_ms % HOUR_MS == 0
        )

    return {
        "partition_file_count": int(len(files)),
        "sampled_file_count": int(len(sampled_files)),
        "symbol_count": int(len(symbols)),
        "symbols_sample": symbols[:12],
        "sampled_row_count": int(row_count),
        "row_count_scope": "sampled_files_only",
        "columns": sorted(header_union),
        "exchange_values": sorted(exchange_values)[:20],
        "exchange_value_count": int(len(exchange_values)),
        "market_type_values": sorted(market_type_values)[:20],
        "source_values": sorted(source_values)[:20],
        "has_volume": bool("volume" in header_union),
        "has_quote_volume": bool("quote_volume" in header_union),
        "volume_non_null_count": int(volume_non_null),
        "quote_volume_non_null_count": int(quote_volume_non_null),
        "same_source_symbol_hour_multi_exchange_bar_count": int(multi_exchange_bar_count),
        "closed_bar_timestamp_check": closed_bar_timestamp_check,
    }


def _summarize_source(spec: SourceSpec, *, max_sample_files: int) -> dict[str, Any]:
    intervals = _interval_files(spec.root)
    interval_summaries = {
        interval: _summarize_files(files, max_sample_files=max_sample_files)
        for interval, files in intervals.items()
        if interval in {"1h", "4h", "1d"}
    }
    return {
        "source_id": spec.source_id,
        "root": str(spec.root),
        "exists": bool(spec.root.exists()),
        "provider": spec.provider,
        "venue_claim": spec.venue_claim,
        "market_type_claim": spec.market_type_claim,
        "trust_note": spec.trust_note,
        "intervals_present": sorted(intervals.keys()),
        "interval_summaries": interval_summaries,
        "can_directly_build_1h_venue_share": bool(
            interval_summaries.get("1h", {}).get("same_source_symbol_hour_multi_exchange_bar_count", 0) > 0
        ),
    }


def _coinapi_group_status(source_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    coinapi_ids = [
        "coinapi_binance_spot",
        "coinapi_coinbase_spot",
        "coinapi_okex_spot",
        "coinapi_bybitspot_spot",
    ]
    interval_venues: dict[str, list[str]] = {}
    interval_symbol_counts: dict[str, dict[str, int]] = {}
    for source_id in coinapi_ids:
        summary = source_summaries.get(source_id, {})
        venue = str(summary.get("venue_claim") or source_id)
        for interval, details in (summary.get("interval_summaries") or {}).items():
            if int(details.get("sampled_row_count") or 0) <= 0:
                continue
            interval_venues.setdefault(interval, []).append(venue)
            interval_symbol_counts.setdefault(interval, {})[venue] = int(details.get("symbol_count") or 0)

    one_hour_venues = sorted(interval_venues.get("1h", []))
    daily_venues = sorted(interval_venues.get("1d", []))
    return {
        "source_group": "coinapi_spot_multi_venue",
        "venues_with_1h_rows": one_hour_venues,
        "venues_with_1d_rows": daily_venues,
        "symbol_count_by_interval_and_venue": interval_symbol_counts,
        "can_build_1h_venue_concentration": bool(len(one_hour_venues) >= 2),
        "can_build_daily_cross_venue_diagnostic": bool(len(daily_venues) >= 2),
        "blocked_reason": None
        if len(one_hour_venues) >= 2
        else "Only one local CoinAPI venue has 1h spot rows; the other per-exchange caches are daily only.",
    }


def _minimum_field_audit(
    source_summaries: dict[str, dict[str, Any]],
    coinapi_group: dict[str, Any],
) -> dict[str, Any]:
    any_1h_volume = []
    for source_id, summary in source_summaries.items():
        details = (summary.get("interval_summaries") or {}).get("1h") or {}
        if details.get("has_volume") or details.get("has_quote_volume"):
            any_1h_volume.append(source_id)
    return {
        "per_symbol_venue_volume_share": {
            "status": "missing",
            "evidence": (
                "No local source has at least two exchange-specific 1h volume legs for the same "
                "symbol-hour."
            ),
        },
        "top_venue_share": {
            "status": "missing",
            "evidence": "Requires multi-venue 1h volume shares; current 1h volume sources are single-venue.",
        },
        "venue_count": {
            "status": "blocked",
            "evidence": {
                "coinapi_venues_with_1h_rows": coinapi_group.get("venues_with_1h_rows"),
                "coinapi_venues_with_1d_rows": coinapi_group.get("venues_with_1d_rows"),
            },
        },
        "venue_missingness": {
            "status": "blocked",
            "evidence": "Can report source missingness, but not missing multi-venue shares at 1h.",
        },
        "closed_bar_timestamps": {
            "status": "available_for_bar_sources",
            "evidence": "1h sources carry open_time_ms; this is necessary but not sufficient.",
        },
        "provider_concordance_path": {
            "status": "missing_for_1h_venue_concentration",
            "evidence": (
                "Coverage can be audited, but no independent local multi-venue 1h sidecar exists "
                "to compare venue shares against."
            ),
        },
        "one_hour_volume_sources_seen": sorted(any_1h_volume),
    }


def _decision(
    source_summaries: dict[str, dict[str, Any]],
    coinapi_group: dict[str, Any],
) -> dict[str, Any]:
    direct_sources = [
        source_id
        for source_id, summary in source_summaries.items()
        if summary.get("can_directly_build_1h_venue_share")
    ]
    can_build = bool(direct_sources or coinapi_group.get("can_build_1h_venue_concentration"))
    if can_build:
        return {
            "label": "pass_data_unlock",
            "alpha_validation_status": "not_started",
            "sidecar_status": "ready_for_stage0_builder",
            "direct_sources": direct_sources,
            "fake_liquidity_retry_allowed": False,
            "alpha_rerun_allowed": False,
            "reason": (
                "Data unlock only. Build the sidecar and run separate concordance/falsification "
                "before any fake-liquidity retry."
            ),
            "h10d_promotion_state_mutation": False,
        }
    return {
        "label": "blocked",
        "alpha_validation_status": "not_started",
        "sidecar_status": "blocked_by_data",
        "fake_liquidity_retry_allowed": False,
        "alpha_rerun_allowed": False,
        "blockers": [
            "no_native_1h_multi_venue_volume_by_exchange",
            "coinglass_extended_is_not_a_multi_venue_volume_share_feed",
            "coinapi_per_exchange_side_roots_are_daily_only_except_binance",
            "provider_concordance_path_missing_for_1h_venue_shares",
            "coverage_is_not_provider_trust_or_research_validation",
        ],
        "next_recommended_step": (
            "Run native_exchange_flow_1h availability audit for cex_inflow_bait_vs_exit, "
            "or acquire/backfill per-venue 1h spot/perp volume before retrying fake liquidity."
        ),
        "h10d_promotion_state_mutation": False,
    }


def _data_quality_blockers(
    source_summaries: dict[str, dict[str, Any]],
    coinapi_group: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not coinapi_group.get("can_build_1h_venue_concentration"):
        blockers.append(
            {
                "blocker": "coinapi_multi_venue_1h_absent",
                "severity": "hard",
                "evidence": {
                    "venues_with_1h_rows": coinapi_group.get("venues_with_1h_rows"),
                    "venues_with_1d_rows": coinapi_group.get("venues_with_1d_rows"),
                },
            }
        )
    for source_id in ("coinglass_extended", "coinglass_spot_ohlcv"):
        details = (source_summaries.get(source_id, {}).get("interval_summaries") or {}).get("1h") or {}
        if details and int(details.get("exchange_value_count") or 0) <= 1:
            blockers.append(
                {
                    "blocker": f"{source_id}_single_exchange_1h",
                    "severity": "hard",
                    "evidence": {
                        "exchange_values": details.get("exchange_values"),
                        "symbol_count": details.get("symbol_count"),
                        "sampled_row_count": details.get("sampled_row_count"),
                    },
                }
            )
    blockers.append(
        {
            "blocker": "coverage_concordance_separation",
            "severity": "hard",
            "evidence": (
                "Provider coverage counts are reported here, but no venue-share concordance "
                "or alpha falsification is implied."
            ),
        }
    )
    return blockers


def _compact_source_table(source_summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id, summary in source_summaries.items():
        intervals = summary.get("interval_summaries") or {}
        one_h = intervals.get("1h") or {}
        one_d = intervals.get("1d") or {}
        rows.append(
            {
                "source_id": source_id,
                "exists": bool(summary.get("exists")),
                "provider": summary.get("provider"),
                "venue_claim": summary.get("venue_claim"),
                "1h_symbols": int(one_h.get("symbol_count") or 0),
                "1h_partitions": int(one_h.get("partition_file_count") or 0),
                "1h_sampled_rows": int(one_h.get("sampled_row_count") or 0),
                "1h_exchange_values": one_h.get("exchange_values") or [],
                "1h_has_volume": bool(one_h.get("has_volume") or one_h.get("has_quote_volume")),
                "1d_symbols": int(one_d.get("symbol_count") or 0),
                "can_directly_build_1h_venue_share": bool(
                    summary.get("can_directly_build_1h_venue_share")
                ),
            }
        )
    return rows


def _build_markdown(report: dict[str, Any]) -> str:
    decision = report["pass_fail_decision"]
    lines = [
        "# Venue Concentration 1h Sidecar Discovery",
        "",
        f"- research_id: `{report['research_id']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- decision: `{decision['label']}`",
        f"- sidecar_status: `{decision['sidecar_status']}`",
        f"- fake_liquidity_retry_allowed: `{decision['fake_liquidity_retry_allowed']}`",
        "",
        "## Source Coverage",
        "",
        "| source | provider | venue claim | 1h symbols | 1h partitions | sampled 1h rows | 1h exchanges | 1h volume | direct 1h venue share |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in report["compact_source_table"]:
        exchanges = ", ".join(row["1h_exchange_values"]) if row["1h_exchange_values"] else "none"
        lines.append(
            "| {source_id} | {provider} | {venue_claim} | {symbols} | {partitions} | {rows} | {exchanges} | {has_volume} | {direct} |".format(
                source_id=row["source_id"],
                provider=row["provider"],
                venue_claim=row["venue_claim"],
                symbols=row["1h_symbols"],
                partitions=row["1h_partitions"],
                rows=row["1h_sampled_rows"],
                exchanges=exchanges,
                has_volume=str(row["1h_has_volume"]).lower(),
                direct=str(row["can_directly_build_1h_venue_share"]).lower(),
            )
        )
    lines.extend(
        [
            "",
            "## Minimum Field Audit",
            "",
            "| field | status | evidence |",
            "| --- | --- | --- |",
        ]
    )
    for field, details in report["minimum_field_audit"].items():
        if isinstance(details, dict):
            evidence = details.get("evidence")
            status = details.get("status")
            if isinstance(evidence, dict):
                evidence_text = json.dumps(evidence, sort_keys=True)
            else:
                evidence_text = str(evidence)
        else:
            status = "observed"
            evidence_text = json.dumps(details, sort_keys=True)
        lines.append(f"| `{field}` | `{status}` | {evidence_text} |")
    lines.extend(
        [
            "",
            "## Hard Blockers",
            "",
        ]
    )
    for blocker in report["data_quality_blockers"]:
        lines.append(f"- `{blocker['blocker']}` ({blocker['severity']}): {blocker['evidence']}")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"`{decision['label']}`. This is a data-side block, not an alpha failure.",
            "",
            "Next step: "
            + str(
                decision.get(
                    "next_recommended_step",
                    "Build the sidecar first, then run a separate validation.",
                )
            ),
            "",
            "The h10d canonical parent remains read-only and was not modified.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "venue_concentration_1h_sidecar_discovery.json"
    md_path = output_dir / "venue_concentration_1h_sidecar_discovery.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_build_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    external_root = _resolve_external_root(args.external_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    specs = _source_specs(external_root)
    source_summaries = {
        spec.source_id: _summarize_source(
            spec,
            max_sample_files=int(args.max_sample_files_per_interval),
        )
        for spec in specs
    }
    coinapi_group = _coinapi_group_status(source_summaries)
    minimum_field_audit = _minimum_field_audit(source_summaries, coinapi_group)
    data_quality_blockers = _data_quality_blockers(source_summaries, coinapi_group)
    decision = _decision(source_summaries, coinapi_group)
    report: dict[str, Any] = {
        "artifact_family": "parallel_1h_alpha_mining_stage1a_data_sidecar",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "external_root": str(external_root),
        "sampling_policy": {
            "partition_file_count": "exact",
            "symbol_count": "exact_from_partition_paths",
            "field_and_timestamp_checks": "sampled",
            "max_sample_files_per_source_interval": int(args.max_sample_files_per_interval),
        },
        "data_sources_and_coverage": source_summaries,
        "compact_source_table": _compact_source_table(source_summaries),
        "coinapi_multi_venue_group_status": coinapi_group,
        "minimum_field_audit": minimum_field_audit,
        "data_quality_blockers": data_quality_blockers,
        "provider_trust_notes": [
            "Data coverage is not provider concordance.",
            "Provider concordance is not research validation.",
            "A 1h venue-concentration sidecar must be point-in-time and closed-bar aware.",
            "No fake-liquidity retry is allowed until per-venue 1h share fields exist and pass data QA.",
        ],
        "pass_fail_decision": decision,
        "next_landing_shape": {
            "if_data_is_acquired": (
                "Build symbol-hour venue share, top venue share, venue count, and missingness sidecar; "
                "then run a separate capacity-haircut parent simulator."
            ),
            "if_data_remains_absent": (
                "Move to native_exchange_flow_1h availability audit; keep fake-liquidity branch blocked."
            ),
        },
    }
    json_path, md_path = _write_report(report, output_dir)
    compact = {
        "research_id": report["research_id"],
        "json_path": str(json_path),
        "md_path": str(md_path),
        "decision": decision,
        "coinapi_multi_venue_group_status": coinapi_group,
        "compact_source_table": report["compact_source_table"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
