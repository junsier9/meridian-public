from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any


FAPI_BASE_URL = "https://fapi.binance.com"
SAPI_BASE_URL = "https://api.binance.com"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Standalone Binance USD-M mainnet read-only preflight for remote runner hosts."
    )
    parser.add_argument("--api-key-env", default="Trade")
    parser.add_argument("--api-secret-env", default="Secret_Key")
    parser.add_argument("--api-key-b64-env", default="")
    parser.add_argument("--api-secret-b64-env", default="")
    parser.add_argument("--expected-egress-ip", default="")
    args = parser.parse_args(argv)
    summary = run_preflight(
        api_key_env=str(args.api_key_env),
        api_secret_env=str(args.api_secret_env),
        api_key_b64_env=str(args.api_key_b64_env or "").strip(),
        api_secret_b64_env=str(args.api_secret_b64_env or "").strip(),
        expected_egress_ip=str(args.expected_egress_ip or "").strip(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "passed_read_only_account_probe" else 2


def run_preflight(
    *,
    api_key_env: str,
    api_secret_env: str,
    api_key_b64_env: str = "",
    api_secret_b64_env: str = "",
    expected_egress_ip: str = "",
) -> dict[str, Any]:
    started = datetime.now(UTC)
    api_key = _env_secret(api_key_env, b64_env=api_key_b64_env)
    api_secret = _env_secret(api_secret_env, b64_env=api_secret_b64_env)
    blockers: list[str] = []
    if not api_key:
        blockers.append(f"missing_api_key_env:{api_key_env}")
    if not api_secret:
        blockers.append(f"missing_api_secret_env:{api_secret_env}")
    if blockers:
        return _summary(
            started=started,
            status="blocked",
            blockers=blockers,
            api_key_env=api_key_env,
            api_secret_env=api_secret_env,
            api_key=api_key,
            api_secret=api_secret,
            expected_egress_ip=expected_egress_ip,
            endpoint_results={},
        )

    endpoint_results = {
        "account_information_v3": _signed_get(
            FAPI_BASE_URL,
            "/fapi/v3/account",
            api_key=api_key,
            api_secret=api_secret,
        ),
        "account_config": _signed_get(
            FAPI_BASE_URL,
            "/fapi/v1/accountConfig",
            api_key=api_key,
            api_secret=api_secret,
        ),
        "position_mode": _signed_get(
            FAPI_BASE_URL,
            "/fapi/v1/positionSide/dual",
            api_key=api_key,
            api_secret=api_secret,
        ),
        "open_orders": _signed_get(
            FAPI_BASE_URL,
            "/fapi/v1/openOrders",
            api_key=api_key,
            api_secret=api_secret,
        ),
        "exchange_info": _public_get(FAPI_BASE_URL, "/fapi/v1/exchangeInfo"),
        "api_key_permissions": _signed_get(
            SAPI_BASE_URL,
            "/sapi/v1/account/apiRestrictions",
            api_key=api_key,
            api_secret=api_secret,
        ),
    }
    for name, item in endpoint_results.items():
        if item.get("status") != "ok":
            blockers.append(
                f"read_only_endpoint_failed:{name}:{item.get('status_code', item.get('error_type'))}:{str(item.get('error', ''))[:160]}"
            )

    account = _payload(endpoint_results, "account_information_v3", {})
    account_config = _payload(endpoint_results, "account_config", {})
    position_mode_payload = _payload(endpoint_results, "position_mode", {})
    open_orders_payload = _payload(endpoint_results, "open_orders", [])
    key_permissions_payload = _payload(endpoint_results, "api_key_permissions", {})
    positions = [dict(item) for item in list(account.get("positions") or []) if isinstance(item, dict)]
    open_positions = [
        {
            "symbol": str(item.get("symbol") or ""),
            "positionSide": str(item.get("positionSide") or ""),
            "positionAmt": _float(item.get("positionAmt")),
        }
        for item in positions
        if abs(_float(item.get("positionAmt"))) > 1e-12
    ]
    open_orders = [dict(item) for item in list(open_orders_payload or []) if isinstance(item, dict)]
    can_trade = _optional_bool(account_config.get("canTrade"))
    if can_trade is None:
        can_trade = _optional_bool(account.get("canTrade"))
    dual_side = _optional_bool(position_mode_payload.get("dualSidePosition"))
    if dual_side is None:
        dual_side = _optional_bool(account_config.get("dualSidePosition"))
    position_mode = "hedge" if dual_side is True else "one_way" if dual_side is False else None
    key_permissions = {
        "api_key_permissions_readable": bool(key_permissions_payload),
        "ip_restrict": _optional_bool(key_permissions_payload.get("ipRestrict")),
        "enable_reading": _optional_bool(key_permissions_payload.get("enableReading")),
        "enable_withdrawals": _optional_bool(key_permissions_payload.get("enableWithdrawals")),
        "enable_internal_transfer": _optional_bool(key_permissions_payload.get("enableInternalTransfer")),
        "enable_margin": _optional_bool(key_permissions_payload.get("enableMargin")),
        "enable_futures": _optional_bool(key_permissions_payload.get("enableFutures")),
        "permits_universal_transfer": _optional_bool(key_permissions_payload.get("permitsUniversalTransfer")),
        "enable_spot_and_margin_trading": _optional_bool(key_permissions_payload.get("enableSpotAndMarginTrading")),
        "enable_european_options": _optional_bool(key_permissions_payload.get("enableEuropeanOptions")),
        "trading_authority_expiration_time": key_permissions_payload.get("tradingAuthorityExpirationTime"),
    }
    egress_ip = _public_ip()
    if expected_egress_ip and egress_ip != expected_egress_ip:
        blockers.append(f"egress_ip_mismatch:expected={expected_egress_ip}:actual={egress_ip}")
    if can_trade is not True:
        blockers.append(f"account_config_canTrade_not_true:{can_trade}")
    if position_mode != "one_way":
        blockers.append(f"position_mode_mismatch:expected=one_way:actual={position_mode}")
    if open_orders:
        blockers.append(f"mainnet_open_orders_exist:{len(open_orders)}")
    if open_positions:
        blockers.append(f"mainnet_open_positions_exist:{len(open_positions)}")
    if key_permissions["api_key_permissions_readable"] is not True:
        blockers.append("api_key_permissions_unreadable")
    if key_permissions["enable_reading"] is not True:
        blockers.append(f"api_key_enableReading_not_true:{key_permissions['enable_reading']}")
    if key_permissions["enable_futures"] is not True:
        blockers.append(f"api_key_enableFutures_not_true:{key_permissions['enable_futures']}")
    if key_permissions["enable_withdrawals"] is not False:
        blockers.append(f"api_key_enableWithdrawals_not_false:{key_permissions['enable_withdrawals']}")
    if key_permissions["ip_restrict"] is not True:
        blockers.append(f"api_key_ipRestrict_not_true:{key_permissions['ip_restrict']}")

    status = "passed_read_only_account_probe" if not blockers else "blocked"
    return {
        **_summary(
            started=started,
            status=status,
            blockers=blockers,
            api_key_env=api_key_env,
            api_secret_env=api_secret_env,
            api_key=api_key,
            api_secret=api_secret,
            expected_egress_ip=expected_egress_ip,
            endpoint_results=endpoint_results,
        ),
        "account_readable": bool(account),
        "can_trade": can_trade,
        "position_mode": position_mode,
        "open_order_count": len(open_orders),
        "open_position_count": len(open_positions),
        "api_key_permissions": key_permissions,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }


def _signed_get(base_url: str, path: str, *, api_key: str, api_secret: str) -> dict[str, Any]:
    params = {
        "recvWindow": "5000",
        "timestamp": str(int(time.time() * 1000)),
    }
    query = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{base_url.rstrip('/')}{path}?{query}&signature={signature}"
    request = urllib.request.Request(
        url,
        headers={"X-MBX-APIKEY": api_key, "User-Agent": "EnhengClaw/remote-readonly-preflight"},
    )
    return _request_json(request=request, path=path, base_url=base_url)


def _public_get(base_url: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"User-Agent": "EnhengClaw/remote-readonly-preflight"},
    )
    return _request_json(request=request, path=path, base_url=base_url)


def _request_json(*, request: urllib.request.Request, path: str, base_url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return {
                "base_url": base_url,
                "path": path,
                "status": "ok",
                "status_code": int(response.status),
                "payload": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as exc:
        return {
            "base_url": base_url,
            "path": path,
            "status": "failed",
            "status_code": int(exc.code),
            "error": exc.read().decode("utf-8", errors="replace"),
        }
    except Exception as exc:
        return {
            "base_url": base_url,
            "path": path,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _summary(
    *,
    started: datetime,
    status: str,
    blockers: list[str],
    api_key_env: str,
    api_secret_env: str,
    api_key: str,
    api_secret: str,
    expected_egress_ip: str,
    endpoint_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": f"{started.strftime('%Y%m%dT%H%M%SZ')}-remote-mainnet-readonly-preflight",
        "environment": "mainnet",
        "execution_host": "remote_runner",
        "egress_ip": _public_ip(),
        "expected_egress_ip": expected_egress_ip,
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "credential_probe": {
            "api_key_env": api_key_env,
            "api_secret_env": api_secret_env,
            "api_key_present": bool(api_key),
            "api_secret_present": bool(api_secret),
            "api_key_length": len(api_key),
            "api_secret_length": len(api_secret),
        },
        "endpoint_results": {
            name: {key: item.get(key) for key in ("base_url", "path", "status", "status_code", "error_type", "error") if key in item}
            for name, item in endpoint_results.items()
        },
    }


def _payload(endpoint_results: dict[str, dict[str, Any]], name: str, default: Any) -> Any:
    item = endpoint_results.get(name) or {}
    return item.get("payload", default) if item.get("status") == "ok" else default


def _env_secret(name: str, *, b64_env: str = "") -> str:
    if b64_env:
        encoded = os.environ.get(b64_env, "").strip()
        if encoded:
            return base64.b64decode(encoded.encode("utf-8")).decode("utf-8").strip()
    return os.environ.get(name, "").strip()


def _public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return "unavailable"


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if value in {0, 1}:
        return bool(value)
    return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
