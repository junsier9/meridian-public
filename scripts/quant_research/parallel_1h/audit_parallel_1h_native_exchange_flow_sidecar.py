from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime, timedelta
import gzip
import json
import os
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from enhengclaw.quant_research.onchain_cryptoquant import (  # type: ignore
        _cryptoquant_get_json,
        _resolve_cryptoquant_api_token,
    )
except Exception:  # pragma: no cover - provider probe is optional.
    _cryptoquant_get_json = None
    _resolve_cryptoquant_api_token = None


CONTRACT_VERSION = "parallel_1h_native_exchange_flow_availability_audit.v1"
RESEARCH_ID = "native_exchange_flow_1h_availability_audit"
DEFAULT_REPORT_DIR = Path(
    "artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0"
)

FLOW_FIELDS = (
    "inflow_total",
    "outflow_total",
    "netflow_total",
    "exchange_inflow_amount",
    "exchange_outflow_amount",
    "exchange_netflow_amount",
    "whale_to_exchange_amount",
    "whale_from_exchange_usd",
    "whale_to_exchange_usd",
    "exchange_transfer_total_usd",
    "exchange_netflow_type2_minus_type1_usd",
)
NATIVE_REQUIRED_FIELDS = (
    "timestamp_ms",
    "subject",
    "asset_id",
    "exchange",
    "inflow_total",
    "outflow_total",
    "netflow_total",
    "source",
)


def _localappdata_root() -> Path:
    local = str(os.environ.get("LOCALAPPDATA", "")).strip()
    if local:
        return Path(local) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _source_specs() -> list[dict[str, Any]]:
    base = _localappdata_root()
    return [
        {
            "source_id": "cryptoquant_stablecoin_exchange_flows_daily",
            "path": base / "onchain_cryptoquant" / "stablecoin_exchange_flows_daily.csv",
            "provider": "CryptoQuant",
            "expected_granularity": "day",
            "scope": "stablecoin_token_exchange_scope",
            "notes": "Stablecoin token exchange-flow history; useful macro context, not per-symbol small-coin inflow.",
        },
        {
            "source_id": "cryptoquant_reflexivity_exchange_flows_daily",
            "path": base / "onchain_cryptoquant" / "reflexivity_exchange_flows_daily.csv",
            "provider": "CryptoQuant",
            "expected_granularity": "day",
            "scope": "btc_eth_exchange_scope",
            "notes": "BTC/ETH exchange-flow history only; not the post-pump alt universe.",
        },
        {
            "source_id": "alchemy_stablecoin_ethereum_daily_aggregates",
            "path": base / "onchain_stablecoin_ethereum" / "daily_aggregates.csv",
            "provider": "Alchemy/local labels",
            "expected_granularity": "day",
            "scope": "stablecoin_ethereum_aggregate",
            "notes": "Daily Ethereum stablecoin aggregates with optional exchange-label fields.",
        },
        {
            "source_id": "alchemy_stablecoin_tron_daily_aggregates",
            "path": base / "onchain_stablecoin_tron" / "daily_aggregates.csv",
            "provider": "Tron/local labels",
            "expected_granularity": "day",
            "scope": "stablecoin_tron_aggregate",
            "notes": "Daily Tron stablecoin aggregates; not PIT 1h symbol-level exchange flow.",
        },
        {
            "source_id": "coinglass_exchange_transfers_1d",
            "path": ROOT / "artifacts" / "quant_research" / "coinglass" / "exchange_transfers_1d.csv.gz",
            "provider": "CoinGlass",
            "expected_granularity": "day",
            "scope": "chain_exchange_transfer_aggregate",
            "notes": "Daily transfer aggregate with PIT lag, but direction semantics are raw/unverified.",
        },
        {
            "source_id": "coinglass_whale_transfers_1d",
            "path": ROOT / "artifacts" / "quant_research" / "coinglass" / "whale_transfers_1d.csv.gz",
            "provider": "CoinGlass",
            "expected_granularity": "day",
            "scope": "whale_transfer_aggregate",
            "notes": "Daily whale transfer aggregate; exchange direction is not a native per-symbol 1h inflow sidecar.",
        },
        {
            "source_id": "coinglass_microstructure_panel_1h",
            "path": ROOT / "artifacts" / "quant_research" / "coinglass" / "microstructure_panel_1h.csv.gz",
            "provider": "CoinGlass extended",
            "expected_granularity": "1h",
            "scope": "per_symbol_derivatives_microstructure",
            "notes": "1h liquidation/orderbook/taker/account panel; no exchange inflow/outflow/netflow fields.",
        },
        {
            "source_id": "coinglass_participant_panel_1h",
            "path": ROOT / "artifacts" / "quant_research" / "coinglass" / "participant_panel_1h.csv.gz",
            "provider": "CoinGlass extended",
            "expected_granularity": "1h",
            "scope": "per_symbol_participant_taker",
            "notes": "1h account/taker panel; no on-chain exchange inflow/outflow/netflow fields.",
        },
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit whether a native PIT 1h exchange-flow sidecar exists for the parallel 1h CEX-inflow lane."
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--probe-cryptoquant-hourly", action="store_true")
    parser.add_argument("--probe-days", type=int, default=2)
    return parser


def _open_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _non_empty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _sorted_limited(values: set[str], limit: int = 24) -> list[str]:
    return sorted(values)[:limit]


def _audit_csv_source(spec: dict[str, Any]) -> dict[str, Any]:
    path = Path(spec["path"])
    out: dict[str, Any] = {
        "source_id": spec["source_id"],
        "provider": spec["provider"],
        "path": str(path),
        "expected_granularity": spec["expected_granularity"],
        "scope": spec["scope"],
        "notes": spec["notes"],
        "exists": path.exists(),
    }
    if not path.exists():
        out.update({"status": "missing", "row_count": 0})
        return out

    row_count = 0
    fieldnames: list[str] = []
    read_error: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    timestamp_min: int | None = None
    timestamp_max: int | None = None
    uniques: dict[str, set[str]] = {
        key: set()
        for key in (
            "window",
            "interval",
            "subject",
            "symbol",
            "asset_id",
            "token_id",
            "exchange",
            "source",
            "pit_policy",
            "exchange_transfer_direction_semantics",
        )
    }
    non_null_counts = {field: 0 for field in FLOW_FIELDS}
    try:
        with _open_csv(path) as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            for row in reader:
                row_count += 1
                date_value = str(row.get("date_utc") or row.get("date") or "").strip()
                if date_value:
                    date_min = date_value if date_min is None else min(date_min, date_value)
                    date_max = date_value if date_max is None else max(date_max, date_value)
                for ts_field in ("timestamp_ms", "open_time_ms", "source_event_timestamp_min_utc"):
                    value = row.get(ts_field)
                    if not _non_empty(value):
                        continue
                    try:
                        if ts_field.endswith("_utc"):
                            continue
                        ts_int = int(float(str(value)))
                    except ValueError:
                        continue
                    timestamp_min = ts_int if timestamp_min is None else min(timestamp_min, ts_int)
                    timestamp_max = ts_int if timestamp_max is None else max(timestamp_max, ts_int)
                for key in uniques:
                    value = row.get(key)
                    if _non_empty(value) and len(uniques[key]) < 200:
                        uniques[key].add(str(value).strip())
                for field in FLOW_FIELDS:
                    if _non_empty(row.get(field)):
                        non_null_counts[field] += 1
    except (EOFError, UnicodeError, csv.Error) as exc:
        read_error = f"{type(exc).__name__}: {exc}"

    interval_values = uniques["interval"]
    window_values = uniques["window"]
    expected_1h_with_timestamp = (
        str(spec.get("expected_granularity")) == "1h"
        and any(field in fieldnames for field in ("timestamp_ms", "open_time_ms"))
    )
    is_1h = (
        "1h" in interval_values
        or "hour" in window_values
        or "1h" in window_values
        or expected_1h_with_timestamp
    )
    has_inflow_outflow_netflow = all(
        field in fieldnames
        for field in ("inflow_total", "outflow_total", "netflow_total")
    )
    has_any_flow_field = any(field in fieldnames for field in FLOW_FIELDS)
    has_asset_scope = any(field in fieldnames for field in ("subject", "symbol", "asset_id", "token_id"))
    has_pit = any(field in fieldnames for field in ("pit_lag_days", "pit_policy", "timestamp_ms", "open_time_ms"))
    direction_semantics = _sorted_limited(uniques["exchange_transfer_direction_semantics"])
    raw_direction_unverified = "raw_transfer_type_unverified" in direction_semantics
    native_ready = (
        row_count > 0
        and is_1h
        and has_inflow_outflow_netflow
        and has_asset_scope
        and has_pit
        and not raw_direction_unverified
        and read_error is None
    )
    out.update(
        {
            "status": "ok",
            "read_error": read_error,
            "row_count": row_count,
            "field_count": len(fieldnames),
            "fields": fieldnames,
            "date_min_utc": date_min,
            "date_max_utc": date_max,
            "timestamp_min_ms": timestamp_min,
            "timestamp_max_ms": timestamp_max,
            "unique_values": {key: _sorted_limited(value) for key, value in uniques.items() if value},
            "unique_counts": {key: len(value) for key, value in uniques.items() if value},
            "flow_field_non_null_counts": {
                key: value for key, value in non_null_counts.items() if value > 0
            },
            "readiness": {
                "is_1h_grid": is_1h,
                "has_any_flow_field": has_any_flow_field,
                "has_inflow_outflow_netflow": has_inflow_outflow_netflow,
                "has_asset_or_symbol_scope": has_asset_scope,
                "has_pit_timestamp_or_policy": has_pit,
                "raw_direction_unverified": raw_direction_unverified,
                "native_1h_exchange_flow_sidecar_ready": native_ready,
                "read_error_blocks_trust": read_error is not None,
            },
            "missing_native_required_fields": [
                field for field in NATIVE_REQUIRED_FIELDS if field not in fieldnames
            ],
        }
    )
    return out


def _cryptoquant_hourly_probe(probe_days: int) -> dict[str, Any]:
    if _resolve_cryptoquant_api_token is None or _cryptoquant_get_json is None:
        return {"status": "skipped", "reason": "cryptoquant_helpers_unavailable"}
    probes = [
        {
            "probe_id": "btc_all_exchange_inflow_hour",
            "path": "/btc/exchange-flows/inflow",
            "params": {"exchange": "all_exchange"},
            "scope": "btc",
        },
        {
            "probe_id": "eth_all_exchange_inflow_hour",
            "path": "/eth/exchange-flows/inflow",
            "params": {"exchange": "all_exchange"},
            "scope": "eth",
        },
        {
            "probe_id": "stablecoin_usdt_eth_all_exchange_inflow_hour",
            "path": "/stablecoin/exchange-flows/inflow",
            "params": {"token": "usdt_eth", "exchange": "all_exchange"},
            "scope": "stablecoin_usdt_eth",
        },
        {
            "probe_id": "sol_all_exchange_inflow_hour",
            "path": "/sol/exchange-flows/inflow",
            "params": {"exchange": "all_exchange"},
            "scope": "sol",
        },
        {
            "probe_id": "pendle_all_exchange_inflow_hour",
            "path": "/pendle/exchange-flows/inflow",
            "params": {"exchange": "all_exchange"},
            "scope": "pendle",
        },
    ]
    try:
        token = _resolve_cryptoquant_api_token()
    except Exception as exc:  # noqa: BLE001
        return {"status": "skipped", "reason": f"api_token_unavailable: {exc}"}

    end_date = datetime.now(UTC).date() - timedelta(days=1)
    start_date = end_date - timedelta(days=max(int(probe_days), 1) - 1)
    rows: list[dict[str, Any]] = []
    for probe in probes:
        params = dict(probe["params"])
        params.update(
            {
                "window": "hour",
                "from": start_date.strftime("%Y%m%d"),
                "to": end_date.strftime("%Y%m%d"),
                "limit": 200,
                "format": "json",
            }
        )
        row = {
            "probe_id": probe["probe_id"],
            "scope": probe["scope"],
            "path": probe["path"],
            "window": "hour",
        }
        try:
            payload = _cryptoquant_get_json(access_token=token, path=str(probe["path"]), params=params)
            data = list(dict(payload.get("result") or {}).get("data") or [])
            sample = data[0] if data and isinstance(data[0], dict) else {}
            row.update(
                {
                    "status": "ok",
                    "row_count": len(data),
                    "sample_keys": sorted(sample.keys()),
                    "has_datetime_field": "datetime" in sample,
                    "has_date_field": "date" in sample,
                }
            )
        except Exception as exc:  # noqa: BLE001
            row.update({"status": "error", "error": str(exc)[:500]})
        rows.append(row)
    return {
        "status": "complete",
        "probe_start_date_utc": start_date.isoformat(),
        "probe_end_date_utc": end_date.isoformat(),
        "rows": rows,
    }


def _decision(source_audits: list[dict[str, Any]], provider_probe: dict[str, Any]) -> dict[str, Any]:
    ready_sources = [
        item["source_id"]
        for item in source_audits
        if item.get("readiness", {}).get("native_1h_exchange_flow_sidecar_ready")
    ]
    daily_flow_sources = [
        item["source_id"]
        for item in source_audits
        if item.get("readiness", {}).get("has_any_flow_field")
        and not item.get("readiness", {}).get("is_1h_grid")
    ]
    one_hour_nonflow_sources = [
        item["source_id"]
        for item in source_audits
        if item.get("readiness", {}).get("is_1h_grid")
        and not item.get("readiness", {}).get("has_any_flow_field")
    ]
    blockers: list[str] = []
    if not ready_sources:
        blockers.append("no_local_native_pit_1h_exchange_inflow_outflow_netflow_sidecar")
    if daily_flow_sources:
        blockers.append("available_exchange_flow_sources_are_daily_not_1h")
    if one_hour_nonflow_sources:
        blockers.append("available_1h_panels_are_microstructure_not_exchange_flow")
    blockers.append("no_symbol_level_altcoin_exchange_flow_coverage_for_post_pump_universe")
    blockers.append("cex_inflow_bait_vs_exit_stage0_remains_blocked_until_sidecar_exists")

    return {
        "label": "blocked",
        "decision_rule": (
            "Stage 1A passes only if a local or provider-backed sidecar has PIT 1h timestamps, "
            "per-symbol or per-asset scope, inflow/outflow/netflow fields, source/provider provenance, "
            "and delay-ready observed timestamps. Daily or macro-only flow does not unlock Stage 0."
        ),
        "ready_sources": ready_sources,
        "blockers": blockers,
        "stage0_allowed": False,
        "h10d_promotion_state_mutation": False,
        "alpha_admission_allowed": False,
        "provider_probe_status": provider_probe.get("status"),
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Native Exchange Flow 1h Availability Audit",
        "",
        f"Generated at UTC: `{report['generated_at_utc']}`",
        f"Decision: `{report['pass_fail_decision']['label']}`",
        "",
        "## Boundary",
        "",
        "- This is a Stage 1A data-sidecar audit, not alpha validation.",
        "- h10d canonical parent status: `not_modified`.",
        "- `cex_inflow_bait_vs_exit_stage0_1h` remains blocked unless a PIT 1h exchange-flow sidecar exists.",
        "",
        "## Source Summary",
        "",
        "| source | rows | grid | flow fields | ready | key blocker |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for item in report["source_audits"]:
        readiness = item.get("readiness", {})
        blocker = "ok"
        if not readiness.get("is_1h_grid"):
            blocker = "daily_not_1h"
        elif not readiness.get("has_any_flow_field"):
            blocker = "no_exchange_flow_fields"
        elif readiness.get("raw_direction_unverified"):
            blocker = "raw_direction_unverified"
        elif not readiness.get("has_inflow_outflow_netflow"):
            blocker = "missing_inflow_outflow_netflow"
        lines.append(
            "| `{source}` | {rows} | `{grid}` | `{flow}` | `{ready}` | `{blocker}` |".format(
                source=item["source_id"],
                rows=item.get("row_count", 0),
                grid="1h" if readiness.get("is_1h_grid") else item.get("expected_granularity"),
                flow=readiness.get("has_any_flow_field"),
                ready=readiness.get("native_1h_exchange_flow_sidecar_ready"),
                blocker=blocker,
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Label: `{report['pass_fail_decision']['label']}`",
            f"- Blockers: `{', '.join(report['pass_fail_decision']['blockers'])}`",
            f"- Next landing shape: `{report['next_landing_shape']}`",
        ]
    )
    probe = report.get("cryptoquant_hourly_provider_probe", {})
    if probe:
        lines.extend(["", "## Provider Probe", "", f"- Status: `{probe.get('status')}`"])
        for row in probe.get("rows", []):
            lines.append(
                "- `{probe_id}`: `{status}`, rows `{row_count}`".format(
                    probe_id=row.get("probe_id"),
                    status=row.get("status"),
                    row_count=row.get("row_count", ""),
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(*, probe_cryptoquant_hourly: bool, probe_days: int) -> dict[str, Any]:
    source_audits = [_audit_csv_source(spec) for spec in _source_specs()]
    provider_probe = (
        _cryptoquant_hourly_probe(probe_days=probe_days)
        if probe_cryptoquant_hourly
        else {"status": "skipped", "reason": "not_requested"}
    )
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage1a_data_sidecar_audit",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "as_of": "2026-05-07",
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "research_target": {
            "unlocks": "cex_inflow_bait_vs_exit_stage0_1h",
            "required_sidecar": "native_exchange_flow_1h",
            "required_fields": list(NATIVE_REQUIRED_FIELDS),
            "required_delay_tests": ["+1h", "+6h", "+24h"],
        },
        "source_audits": source_audits,
        "cryptoquant_hourly_provider_probe": provider_probe,
        "pass_fail_decision": _decision(source_audits, provider_probe),
        "next_landing_shape": (
            "provider_capability_probe_and_backfill_plan_for_native_exchange_flow_1h; "
            "do not run cex_inflow_bait_vs_exit Stage 0 until the sidecar passes coverage, latency, "
            "direction-semantics, and no-leakage checks"
        ),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        probe_cryptoquant_hourly=bool(args.probe_cryptoquant_hourly),
        probe_days=int(args.probe_days),
    )
    json_path = report_dir / f"{RESEARCH_ID}.json"
    md_path = report_dir / f"{RESEARCH_ID}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _write_markdown(report, md_path)
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "label": report["pass_fail_decision"]["label"],
                "blockers": report["pass_fail_decision"]["blockers"],
                "stage0_allowed": report["pass_fail_decision"]["stage0_allowed"],
                "provider_probe_status": report["pass_fail_decision"]["provider_probe_status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
