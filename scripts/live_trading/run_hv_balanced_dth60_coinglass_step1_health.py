from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path  # noqa: E402
from enhengclaw.live_trading.market_data import resolve_config_symbols  # noqa: E402


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_step1_health.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/step1_coinglass_api_health"
)
BASE_URL = "https://open-api-v4.coinglass.com/api"
EXCHANGE = "Binance"
TOP_TRADER_ENDPOINT_ID = "futures_top_long_short_position_ratio"
TOP_TRADER_PATH = "/futures/top-long-short-position-ratio/history"
SUPPORTED_PAIRS_PATH = "/futures/supported-exchange-pairs"
SUBSCRIPTION_PATH = "/user/account/subscription"
API_KEY_NAMES = ("CoinglassAPI", "COINGLASS_API_KEY", "COINGLASSAPI")


@dataclass(frozen=True, slots=True)
class KeyResolution:
    present: bool
    source: str
    value: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Step 1 read-only CoinGlass health check for the hv_balanced DTH60 "
            "q90/top20 candidate. Writes evidence only; never changes live config."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--freshness-seconds", type=int, default=36 * 3600)
    parser.add_argument("--request-sleep-seconds", type=float, default=0.12)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in materialized:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)


def resolve_api_key(*, base_env: dict[str, str] | None = None) -> KeyResolution:
    env = os.environ if base_env is None else base_env
    for name in API_KEY_NAMES:
        value = str(env.get(name) or "").strip()
        if value:
            return KeyResolution(True, f"env:{name}", value)
    if base_env is not None:
        return KeyResolution(False, "", "")
    if os.name != "nt":
        return KeyResolution(False, "", "")
    try:
        import winreg
    except ImportError:
        return KeyResolution(False, "", "")
    for hive_name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
        for name in API_KEY_NAMES:
            try:
                with winreg.OpenKey(hive, "Environment") as key:
                    value, _ = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            value = str(value or "").strip()
            if value:
                return KeyResolution(True, f"registry:{hive_name}\\Environment:{name}", value)
    return KeyResolution(False, "", "")


def http_get_json(url: str, *, api_key: str, timeout_seconds: float) -> Any:
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def payload_rows(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, dict)]
    return []


def provider_ok(payload: Any, rows: list[dict[str, Any]] | None = None) -> bool:
    if not isinstance(payload, dict):
        return False
    code = str(payload.get("code") or "").strip().lower()
    msg = str(payload.get("msg") or "").strip().lower()
    return code in {"0", "200", "success"} or msg == "success" or bool(rows)


def parse_time_ms(value: Any) -> int | None:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric < 10_000_000_000:
        numeric *= 1000
    return numeric


def latest_provider_time(rows: list[dict[str, Any]]) -> datetime | None:
    candidates: list[int] = []
    for row in rows:
        for key in ("time", "timestamp", "timestamp_ms", "t"):
            parsed = parse_time_ms(row.get(key))
            if parsed is not None:
                candidates.append(parsed)
                break
    if not candidates:
        return None
    return datetime.fromtimestamp(max(candidates) / 1000.0, tz=UTC)


def supported_pairs_from_payload(payload: Any) -> set[str]:
    supported: set[str] = set()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return supported
    for item in data:
        if isinstance(item, str):
            supported.add(item.strip().upper())
            continue
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if str(key).strip().lower() == EXCHANGE.lower() and isinstance(value, list):
                for instrument in value:
                    if isinstance(instrument, str):
                        supported.add(instrument.strip().upper())
                    elif isinstance(instrument, dict):
                        for id_key in ("instrument_id", "symbol", "instrumentId"):
                            instrument_id = str(instrument.get(id_key) or "").strip().upper()
                            if instrument_id:
                                supported.add(instrument_id)
                                break
            elif key in {"instrument_id", "symbol", "instrumentId"}:
                instrument_id = str(value or "").strip().upper()
                if instrument_id:
                    supported.add(instrument_id)
    return supported


def run_step1_health(
    args: argparse.Namespace,
    *,
    http_get_json_fn: Callable[[str, str, float], Any] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    live_config = load_live_trading_config(args.config)
    symbols = resolve_config_symbols(live_config.payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_repo_path(str(args.output_root))
        if str(getattr(args, "output_root", "") or "").strip()
        else resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    key = resolve_api_key(base_env=base_env)
    request_rows: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    http_get = http_get_json_fn or (lambda url, api_key, timeout: http_get_json(url, api_key=api_key, timeout_seconds=timeout))

    def call(endpoint_id: str, path: str, params: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
        requested_at = now()
        url = f"{BASE_URL}{path}?{urlencode(params)}" if params else f"{BASE_URL}{path}"
        row: dict[str, Any] = {
            "endpoint_id": endpoint_id,
            "path": path,
            "params": json.dumps(params, sort_keys=True),
            "requested_at_utc": iso_z(requested_at),
            "received_at_utc": "",
            "latency_ms": "",
            "status": "skipped",
            "row_count": "",
            "error_type": "",
            "error_message": "",
        }
        if not key.present:
            row["error_message"] = "CoinGlass API key missing"
            request_rows.append(row)
            return None, row
        try:
            payload = http_get(str(url), key.value, float(args.request_timeout_seconds))
            received_at = now()
            rows = payload_rows(payload)
            row.update(
                {
                    "received_at_utc": iso_z(received_at),
                    "latency_ms": round((received_at - requested_at).total_seconds() * 1000.0, 3),
                    "status": "success" if provider_ok(payload, rows) else "provider_error",
                    "row_count": len(rows),
                    "error_message": "" if provider_ok(payload, rows) else f"provider_code={dict(payload or {}).get('code')}",
                }
            )
            request_rows.append(row)
            return payload, row
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            received_at = now()
            row.update(
                {
                    "received_at_utc": iso_z(received_at),
                    "latency_ms": round((received_at - requested_at).total_seconds() * 1000.0, 3),
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                }
            )
            request_rows.append(row)
            return None, row

    if not key.present:
        blockers.append("coinglass_api_key_missing")

    subscription_payload, subscription_request = call("user_account_subscription", SUBSCRIPTION_PATH, {})
    subscription_ok = subscription_request["status"] == "success"
    if key.present and not subscription_ok:
        warnings.append("subscription_endpoint_not_confirmed")

    pairs_payload, pairs_request = call("futures_supported_exchange_pairs", SUPPORTED_PAIRS_PATH, {"exchange": EXCHANGE})
    supported_pairs = supported_pairs_from_payload(pairs_payload)
    missing_supported = sorted(symbol for symbol in symbols if supported_pairs and symbol not in supported_pairs)
    if pairs_request["status"] != "success":
        blockers.append("supported_pairs_endpoint_failed")
    elif missing_supported:
        blockers.append("live_symbol_not_supported_by_coinglass")

    for symbol in symbols:
        params = {
            "exchange": EXCHANGE,
            "symbol": symbol,
            "interval": str(args.interval),
            "limit": int(args.limit),
        }
        payload, request_row = call(TOP_TRADER_ENDPOINT_ID, TOP_TRADER_PATH, params)
        rows = payload_rows(payload)
        latest = latest_provider_time(rows)
        age_seconds = (now() - latest).total_seconds() if latest is not None else None
        ready = (
            request_row["status"] == "success"
            and bool(rows)
            and latest is not None
            and age_seconds is not None
            and age_seconds <= int(args.freshness_seconds)
        )
        if request_row["status"] != "success":
            blockers.append(f"{symbol}:top_trader_request_failed")
        elif not rows:
            blockers.append(f"{symbol}:top_trader_empty")
        elif latest is None:
            blockers.append(f"{symbol}:top_trader_missing_provider_timestamp")
        elif age_seconds is not None and age_seconds > int(args.freshness_seconds):
            blockers.append(f"{symbol}:top_trader_stale")
        observations.append(
            {
                "symbol": symbol,
                "provider": "coinglass",
                "exchange": EXCHANGE,
                "factor_id": "coinglass_top_trader_long_pct_smooth_5",
                "endpoint_id": TOP_TRADER_ENDPOINT_ID,
                "interval": str(args.interval),
                "row_count": len(rows),
                "latest_provider_time_utc": iso_z(latest) if latest else "",
                "provider_age_seconds": round(age_seconds, 3) if age_seconds is not None else "",
                "freshness_seconds": int(args.freshness_seconds),
                "readiness": "ready" if ready else "blocked",
                "request_status": request_row["status"],
            }
        )
        if float(args.request_sleep_seconds) > 0:
            time.sleep(float(args.request_sleep_seconds))

    ready_symbols = [row["symbol"] for row in observations if row["readiness"] == "ready"]
    request_status_counts: dict[str, int] = {}
    for row in request_rows:
        status = str(row["status"])
        request_status_counts[status] = request_status_counts.get(status, 0) + 1
    blockers = sorted(set(blockers))
    warnings = sorted(set(warnings))
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": iso_z(now()),
        "started_at_utc": iso_z(started_at),
        "config_path": str(live_config.path),
        "output_root": str(output_root),
        "applied_to_live": False,
        "live_config_changed": False,
        "exchange_order_submission": "disabled",
        "operator_state_changed": False,
        "timer_state_changed": False,
        "api_key_present": key.present,
        "api_key_source": key.source,
        "provider": "coinglass",
        "exchange": EXCHANGE,
        "required_factor_id": "coinglass_top_trader_long_pct_smooth_5",
        "required_endpoint_id": TOP_TRADER_ENDPOINT_ID,
        "required_endpoint_path": TOP_TRADER_PATH,
        "interval": str(args.interval),
        "limit": int(args.limit),
        "freshness_seconds": int(args.freshness_seconds),
        "requested_symbol_count": len(symbols),
        "ready_symbol_count": len(ready_symbols),
        "ready_symbols": ready_symbols,
        "missing_supported_symbols": missing_supported,
        "subscription_endpoint_confirmed": subscription_ok,
        "supported_pairs_endpoint_confirmed": pairs_request["status"] == "success",
        "request_status_counts": request_status_counts,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "requests_csv": str(output_root / "coinglass_requests.csv"),
            "observations_csv": str(output_root / "top_trader_observations.csv"),
        },
    }
    write_csv(output_root / "coinglass_requests.csv", request_rows)
    write_csv(output_root / "top_trader_observations.csv", observations)
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_step1_health(parse_args(argv))
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
