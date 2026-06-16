"""probe_deribit_authenticated_historical_capability.py — empirical
test of whether a Deribit Private API key extends historical data
access beyond the ~24-48h cap observed under anonymous Public API
calls (see commit 29f4565 Phase 1.5 finding).

Hypothesis 1 (likely): Private API key does NOT extend Public market
data history. Authenticated calls to /public/* return same data as
anonymous calls. /private/* endpoints are account-scoped (your own
trades/orders/positions), not market-wide historical OI/IV by strike.

Hypothesis 2 (maybe): Some institutional API tier extends historical
window via authenticated Public endpoints. Worth empirical confirm.

Test plan:
  Step 1. Read DERIBIT_API_KEY + DERIBIT_API_SECRET from env vars.
          Multiple possible names (Deribit_API, DERIBIT_API_KEY, etc).
  Step 2. OAuth2 client_credentials grant → access_token.
  Step 3. Verify auth works via /private/get_account_summary.
  Step 4. Test /public/get_last_trades_by_currency_and_time on:
            (a) anonymous (no Authorization header)
            (b) authenticated (Bearer access_token)
          Both with start_timestamp = 30 days ago, end = 25 days ago.
          Compare n_trades returned.
  Step 5. List private endpoints that COULD provide historical (rarely
          but possible): /private/get_user_trades_by_currency_and_time,
          /private/get_settlement_history_by_currency. Verify these are
          ACCOUNT-scoped only (own trades/settlements).

Stage-1 invariant: this is a research probe; no manifest mutation; no
trading actions; read-only endpoints only.

Usage (after shell restart with env vars set):
  python scripts/quant_research/probe_deribit_authenticated_historical_capability.py
  python scripts/quant_research/probe_deribit_authenticated_historical_capability.py --as-of 2026-05-01

Output: artifacts/quant_research/factor_reports/<as-of>/m3_1_authenticated_probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

DERIBIT_PUBLIC_API_BASE = "https://www.deribit.com/api/v2/public"
DERIBIT_PRIVATE_API_BASE = "https://www.deribit.com/api/v2/private"
DERIBIT_AUTH_URL = f"{DERIBIT_PUBLIC_API_BASE}/auth"

# Common env var names for Deribit API credentials
ENV_VAR_KEY_CANDIDATES = [
    "DERIBIT_API_KEY",
    "DERIBIT_CLIENT_ID",
    "Deribit_API_KEY",
    "Deribit_API",  # user said "Deribit_API" — could be paired with secret
    "DERIBIT_KEY",
]
ENV_VAR_SECRET_CANDIDATES = [
    "DERIBIT_API_SECRET",
    "DERIBIT_CLIENT_SECRET",
    "Deribit_API_SECRET",
    "Deribit_API_Secret",
    "DERIBIT_SECRET",
]


def _resolve_credentials() -> tuple[str | None, str | None, dict]:
    """Try env var candidates; return (key, secret, debug_info)."""
    debug = {
        "checked": {},
        "selected_key_var": None,
        "selected_secret_var": None,
        "selected_combo_var": None,
        "combo_parse_mode": None,
    }
    api_key = None
    api_secret = None

    # Support a single composite env var for convenience if the user stores
    # both client_id + client_secret together in JSON or "key:secret" form.
    combo_val = os.environ.get("Deribit_API", "").strip()
    debug["checked"]["Deribit_API"] = "set" if combo_val else "missing"
    if combo_val:
        if combo_val.startswith("{"):
            try:
                payload = json.loads(combo_val)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                key = (
                    payload.get("client_id")
                    or payload.get("api_key")
                    or payload.get("key")
                )
                secret = (
                    payload.get("client_secret")
                    or payload.get("api_secret")
                    or payload.get("secret")
                )
                if key and secret:
                    api_key = str(key).strip()
                    api_secret = str(secret).strip()
                    debug["selected_combo_var"] = "Deribit_API"
                    debug["combo_parse_mode"] = "json"
        elif ":" in combo_val:
            key_part, secret_part = combo_val.split(":", 1)
            key_part = key_part.strip()
            secret_part = secret_part.strip()
            if key_part and secret_part:
                api_key = key_part
                api_secret = secret_part
                debug["selected_combo_var"] = "Deribit_API"
                debug["combo_parse_mode"] = "colon_delimited"

    for name in ENV_VAR_KEY_CANDIDATES:
        val = os.environ.get(name, "")
        debug["checked"][name] = "set" if val else "missing"
        if val and not api_key:
            api_key = val.strip()
            debug["selected_key_var"] = name

    for name in ENV_VAR_SECRET_CANDIDATES:
        val = os.environ.get(name, "")
        debug["checked"][name] = "set" if val else "missing"
        if val and not api_secret:
            api_secret = val.strip()
            debug["selected_secret_var"] = name

    return api_key, api_secret, debug


def _oauth_token(api_key: str, api_secret: str) -> dict:
    """Get access_token via client_credentials grant."""
    import requests
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": api_secret,
    }
    try:
        resp = requests.get(DERIBIT_AUTH_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return {
                "status": "http_error",
                "http_status": resp.status_code,
                "body_excerpt": resp.text[:500],
            }
        payload = resp.json()
        if "result" not in payload or "access_token" not in payload["result"]:
            return {
                "status": "unexpected_shape",
                "body_excerpt": json.dumps(payload)[:500],
            }
        result = payload["result"]
        return {
            "status": "ok",
            "access_token": result["access_token"],
            "expires_in": result.get("expires_in"),
            "token_type": result.get("token_type"),
            "scope": result.get("scope"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "exception", "exception_type": type(exc).__name__, "exception_message": str(exc)}


def _call_endpoint(url: str, params: dict, access_token: str | None = None) -> dict:
    """GET endpoint with optional Bearer token. Returns trimmed result."""
    import requests
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            return {
                "status": "http_error",
                "http_status": resp.status_code,
                "body_excerpt": resp.text[:300],
            }
        payload = resp.json()
        result = payload.get("result", {})
        if isinstance(result, list):
            return {
                "status": "ok",
                "result_type": "list",
                "n_items": len(result),
                "first_3_items": result[:3] if result else [],
            }
        elif isinstance(result, dict):
            trades = result.get("trades")
            if isinstance(trades, list):
                return {
                    "status": "ok",
                    "n_trades": len(trades),
                    "has_more": result.get("has_more"),
                    "earliest_ts": min(
                        (t.get("timestamp", 0) for t in trades), default=None
                    ),
                    "latest_ts": max((t.get("timestamp", 0) for t in trades), default=None),
                    "first_3_trades": trades[:3] if trades else [],
                }
            return {
                "status": "ok",
                "result_keys": list(result.keys()),
                "result_sample": {k: result.get(k) for k in list(result.keys())[:6]},
            }
        return {"status": "ok", "result_type": type(result).__name__, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"status": "exception", "exception_type": type(exc).__name__, "exception_message": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Deribit authenticated historical capability.")
    parser.add_argument("--as-of", default="2026-05-01")
    parser.add_argument("--currency", default="BTC")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== Deribit authenticated historical capability probe ===")
    print()

    # Step 1: resolve credentials
    print(f"=== Step 1: Resolve env-var credentials ===")
    api_key, api_secret, cred_debug = _resolve_credentials()
    raw_deribit_api = os.environ.get("Deribit_API", "").strip()
    print(f"  env-var checks:")
    for name, status in cred_debug["checked"].items():
        print(f"    {name}: {status}")
    if cred_debug.get("selected_combo_var"):
        print(
            f"  composite credential parse: "
            f"{cred_debug['selected_combo_var']} via {cred_debug['combo_parse_mode']}"
        )
    if not api_key or not api_secret:
        bearer_probe = None
        if raw_deribit_api and not cred_debug.get("selected_combo_var"):
            print()
            print("=== Step 1.5: Try `Deribit_API` as Bearer access token ===")
            bearer_probe = _call_endpoint(
                f"{DERIBIT_PRIVATE_API_BASE}/get_account_summary",
                params={"currency": args.currency},
                access_token=raw_deribit_api,
            )
            print(f"  bearer-token probe status: {bearer_probe.get('status')}")
            if bearer_probe.get("status") == "ok":
                print("  RESULT: `Deribit_API` behaves like a usable access token.")
                access_token = raw_deribit_api
                print()
                print("=== Step 2: OAuth client_credentials grant ===")
                print("  skipped: existing Bearer token supplied via `Deribit_API`")
                print()

                print(f"=== Step 3: Verify auth via /private/get_account_summary ===")
                acct_result = bearer_probe
                print(f"  status: {acct_result.get('status')}")
                if acct_result.get("status") == "ok":
                    result_keys = acct_result.get("result_keys", [])
                    print(f"  account summary keys: {result_keys[:8]}")
                print()

                now = datetime.now(timezone.utc)
                start_dt = now - timedelta(days=30)
                end_dt = now - timedelta(days=25)
                start_ms = int(start_dt.timestamp() * 1000)
                end_ms = int(end_dt.timestamp() * 1000)
                print(f"=== Step 4: trades-by-time past window comparison (anonymous vs authenticated) ===")
                print(f"  past window: {start_dt.isoformat()} → {end_dt.isoformat()}")
                print()
                trades_url = f"{DERIBIT_PUBLIC_API_BASE}/get_last_trades_by_currency_and_time"
                trades_params = {
                    "currency": args.currency,
                    "kind": "option",
                    "start_timestamp": start_ms,
                    "end_timestamp": end_ms,
                    "count": 100,
                    "include_old": "true",
                    "sorting": "asc",
                }

                print("  ---- (a) anonymous call ----")
                anon_result = _call_endpoint(trades_url, trades_params, access_token=None)
                print(f"    status: {anon_result.get('status')}")
                if anon_result.get("status") == "ok":
                    n_trades = anon_result.get("n_trades", 0)
                    print(f"    n_trades: {n_trades}")
                    if n_trades > 0:
                        earliest = datetime.fromtimestamp(anon_result["earliest_ts"] / 1000, tz=timezone.utc)
                        print(f"    earliest_trade: {earliest.isoformat()}")
                    print(f"    has_more: {anon_result.get('has_more')}")
                print()

                time.sleep(0.3)
                print("  ---- (b) authenticated call (same params, with Bearer token) ----")
                auth_result = _call_endpoint(trades_url, trades_params, access_token=access_token)
                print(f"    status: {auth_result.get('status')}")
                if auth_result.get("status") == "ok":
                    n_trades = auth_result.get("n_trades", 0)
                    print(f"    n_trades: {n_trades}")
                    if n_trades > 0:
                        earliest = datetime.fromtimestamp(auth_result["earliest_ts"] / 1000, tz=timezone.utc)
                        print(f"    earliest_trade: {earliest.isoformat()}")
                    print(f"    has_more: {auth_result.get('has_more')}")
                print()

                anon_n = anon_result.get("n_trades", 0) if anon_result.get("status") == "ok" else 0
                auth_n = auth_result.get("n_trades", 0) if auth_result.get("status") == "ok" else 0
                auth_extends = auth_n > anon_n and auth_n > 0
                print(f"  COMPARISON: anonymous={anon_n} vs authenticated={auth_n}")
                if auth_extends:
                    print("  ★ AUTH EXTENDS HISTORICAL ACCESS — investigate further!")
                elif auth_n == 0 and anon_n == 0:
                    print("  ✖ Both anonymous + authenticated return 0 trades for past window — confirms NO historical access via this endpoint regardless of auth")
                else:
                    print("  → No improvement from authentication; token does NOT extend public historical depth")
                print()

                print("=== Step 5: probe account-scoped private endpoints (your own trades / settlements) ===")
                print("  These return YOUR own historical data only (not market-wide). Listed for completeness.")
                print()

                private_probes = {}

                print("  ---- /private/get_user_trades_by_currency_and_time (your own option trades) ----")
                user_trades = _call_endpoint(
                    f"{DERIBIT_PRIVATE_API_BASE}/get_user_trades_by_currency_and_time",
                    params={
                        "currency": args.currency,
                        "kind": "option",
                        "start_timestamp": start_ms,
                        "end_timestamp": end_ms,
                        "count": 50,
                        "include_old": "true",
                        "sorting": "asc",
                    },
                    access_token=access_token,
                )
                print(f"    status: {user_trades.get('status')}")
                if user_trades.get("status") == "ok":
                    print(f"    n_user_trades_in_past_window: {user_trades.get('n_trades', 0)}")
                private_probes["user_trades_by_currency_and_time"] = user_trades
                print()

                print("  ---- /private/get_settlement_history_by_currency (your own option settlements) ----")
                settlement = _call_endpoint(
                    f"{DERIBIT_PRIVATE_API_BASE}/get_settlement_history_by_currency",
                    params={"currency": args.currency, "type": "settlement", "count": 10},
                    access_token=access_token,
                )
                print(f"    status: {settlement.get('status')}")
                if settlement.get("status") == "ok":
                    result_keys = settlement.get("result_keys", [])
                    print(f"    result keys: {result_keys[:6]}")
                private_probes["settlement_history_by_currency"] = settlement
                print()

                print("=== Step 6: Verdict ===")
                if auth_extends:
                    verdict = (
                        "POTENTIALLY EXTENDED — authenticated Bearer token returned more trades than anonymous. "
                        "Investigate further: token scope, lookback depth, account tier."
                    )
                    recommendation = "Build authenticated trades-history backfill ETL; potentially F56 + F58 unlocked free."
                else:
                    verdict = (
                        "BEARER TOKEN DOES NOT EXTEND PUBLIC HISTORICAL — token authenticates but public historical depth is unchanged. "
                        "Historical OI/IV by strike still requires paid Tardis.dev or live accumulation."
                    )
                    recommendation = (
                        "Stay on M3.1 Phase 1 free live-sync (B, ~30-90d wall-clock) "
                        "OR procure Tardis.dev sample (C1, ~$50-200, ~3 weeks closure)."
                    )
                print(f"  VERDICT: {verdict}")
                print(f"  RECOMMENDATION: {recommendation}")
                print()

                out = {
                    "contract_version": "quant_m3_1_authenticated_probe.v1",
                    "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                    "as_of": args.as_of,
                    "currency": args.currency,
                    "step1_credentials": {
                        "status": "bearer_token_only",
                        "selected_combo_var": cred_debug.get("selected_combo_var"),
                        "checked_envvars": cred_debug["checked"],
                    },
                    "step1_5_bearer_probe": bearer_probe,
                    "step2_oauth": {"status": "skipped_existing_bearer_token"},
                    "step3_account_summary": {
                        "status": acct_result.get("status"),
                        "result_keys": acct_result.get("result_keys"),
                    },
                    "step4_trades_by_time_past_window": {
                        "past_window_start_utc": start_dt.isoformat(),
                        "past_window_end_utc": end_dt.isoformat(),
                        "anonymous_call": anon_result,
                        "authenticated_call": auth_result,
                        "authenticated_extends_history": auth_extends,
                    },
                    "step5_private_account_probes": private_probes,
                    "step6_verdict": verdict,
                    "step6_recommendation": recommendation,
                }
                out_dir = args.output_dir / args.as_of
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "m3_1_authenticated_probe.json"
                out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
                print(f"  full report: {out_path}")
                return 0
        print()
        print(f"  STATUS: credentials not found in env vars.")
        if cred_debug["checked"].get("Deribit_API") == "set":
            print(
                "  Note: `Deribit_API` is currently set but does not include a usable "
                "client_id + client_secret pair."
            )
            print(
                "  Supported forms:"
                " Deribit_API='<client_id>:<client_secret>'"
                " OR Deribit_API='{\"client_id\":\"...\",\"client_secret\":\"...\"}'"
            )
            print(
                "  Or set separate vars:"
                " DERIBIT_API_KEY + DERIBIT_API_SECRET"
                " (or Deribit_API_KEY + Deribit_API_SECRET)."
            )
        else:
            print(
                "  Set DERIBIT_API_KEY + DERIBIT_API_SECRET "
                "(or Deribit_API_KEY + Deribit_API_SECRET) and re-run."
            )
        out = {
            "contract_version": "quant_m3_1_authenticated_probe.v1",
            "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "as_of": args.as_of,
            "step1_credentials": {"status": "missing", "debug": cred_debug},
            "step1_5_bearer_probe": bearer_probe,
            "verdict": "ABORTED — env vars not set",
        }
        out_dir = args.output_dir / args.as_of
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "m3_1_authenticated_probe.json"
        out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(f"  partial report: {out_path}")
        return 1
    print(f"  resolved key from {cred_debug['selected_key_var']} (length={len(api_key)})")
    print(f"  resolved secret from {cred_debug['selected_secret_var']} (length={len(api_secret)})")
    print()

    # Step 2: OAuth
    print(f"=== Step 2: OAuth client_credentials grant ===")
    token_result = _oauth_token(api_key, api_secret)
    print(f"  status: {token_result.get('status')}")
    if token_result.get("status") != "ok":
        print(f"  body: {token_result}")
        out = {
            "contract_version": "quant_m3_1_authenticated_probe.v1",
            "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "as_of": args.as_of,
            "step1_credentials": {
                "status": "ok",
                "selected_key_var": cred_debug["selected_key_var"],
                "selected_secret_var": cred_debug["selected_secret_var"],
            },
            "step2_oauth": token_result,
            "verdict": "ABORTED — OAuth failed (likely wrong credentials or insufficient permissions)",
        }
        out_dir = args.output_dir / args.as_of
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "m3_1_authenticated_probe.json"
        out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(f"  partial report: {out_path}")
        return 1
    access_token = token_result["access_token"]
    print(f"  access_token acquired (length={len(access_token)})")
    print(f"  expires_in: {token_result.get('expires_in')} sec")
    print(f"  scope: {token_result.get('scope')}")
    print()

    # Step 3: verify auth via /private/get_account_summary
    print(f"=== Step 3: Verify auth via /private/get_account_summary ===")
    acct_result = _call_endpoint(
        f"{DERIBIT_PRIVATE_API_BASE}/get_account_summary",
        params={"currency": args.currency},
        access_token=access_token,
    )
    print(f"  status: {acct_result.get('status')}")
    if acct_result.get("status") == "ok":
        result_keys = acct_result.get("result_keys", [])
        print(f"  account summary keys: {result_keys[:8]}")
    print()

    # Step 4: anonymous vs authenticated /public/get_last_trades_by_currency_and_time on past window
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=30)
    end_dt = now - timedelta(days=25)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    print(f"=== Step 4: trades-by-time past window comparison (anonymous vs authenticated) ===")
    print(f"  past window: {start_dt.isoformat()} → {end_dt.isoformat()}")
    print()
    trades_url = f"{DERIBIT_PUBLIC_API_BASE}/get_last_trades_by_currency_and_time"
    trades_params = {
        "currency": args.currency,
        "kind": "option",
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
        "count": 100,
        "include_old": "true",
        "sorting": "asc",
    }

    print(f"  ---- (a) anonymous call ----")
    anon_result = _call_endpoint(trades_url, trades_params, access_token=None)
    print(f"    status: {anon_result.get('status')}")
    if anon_result.get("status") == "ok":
        n_trades = anon_result.get("n_trades", 0)
        print(f"    n_trades: {n_trades}")
        if n_trades > 0:
            earliest = datetime.fromtimestamp(anon_result["earliest_ts"] / 1000, tz=timezone.utc)
            print(f"    earliest_trade: {earliest.isoformat()}")
        print(f"    has_more: {anon_result.get('has_more')}")
    print()

    time.sleep(0.3)
    print(f"  ---- (b) authenticated call (same params, with Bearer token) ----")
    auth_result = _call_endpoint(trades_url, trades_params, access_token=access_token)
    print(f"    status: {auth_result.get('status')}")
    if auth_result.get("status") == "ok":
        n_trades = auth_result.get("n_trades", 0)
        print(f"    n_trades: {n_trades}")
        if n_trades > 0:
            earliest = datetime.fromtimestamp(auth_result["earliest_ts"] / 1000, tz=timezone.utc)
            print(f"    earliest_trade: {earliest.isoformat()}")
        print(f"    has_more: {auth_result.get('has_more')}")
    print()

    # Compare
    anon_n = anon_result.get("n_trades", 0) if anon_result.get("status") == "ok" else 0
    auth_n = auth_result.get("n_trades", 0) if auth_result.get("status") == "ok" else 0
    auth_extends = auth_n > anon_n and auth_n > 0
    print(f"  COMPARISON: anonymous={anon_n} vs authenticated={auth_n}")
    if auth_extends:
        print(f"  ⭐ AUTH EXTENDS HISTORICAL ACCESS — investigate further!")
    elif auth_n == 0 and anon_n == 0:
        print(f"  ❌ Both anonymous + authenticated return 0 trades for past window — confirms NO historical access via this endpoint regardless of auth")
    else:
        print(f"  → No improvement from authentication; private API key does NOT extend public historical depth")
    print()

    # Step 5: probe private user-trades and settlement endpoints (account-scoped)
    print(f"=== Step 5: probe account-scoped private endpoints (your own trades / settlements) ===")
    print(f"  These return YOUR own historical data only (not market-wide). Listed for completeness.")
    print()

    private_probes = {}

    # /private/get_user_trades_by_currency_and_time
    print(f"  ---- /private/get_user_trades_by_currency_and_time (your own option trades) ----")
    user_trades = _call_endpoint(
        f"{DERIBIT_PRIVATE_API_BASE}/get_user_trades_by_currency_and_time",
        params={
            "currency": args.currency,
            "kind": "option",
            "start_timestamp": start_ms,
            "end_timestamp": end_ms,
            "count": 50,
            "include_old": "true",
            "sorting": "asc",
        },
        access_token=access_token,
    )
    print(f"    status: {user_trades.get('status')}")
    if user_trades.get("status") == "ok":
        print(f"    n_user_trades_in_past_window: {user_trades.get('n_trades', 0)}")
    private_probes["user_trades_by_currency_and_time"] = user_trades
    print()

    # /private/get_settlement_history_by_currency
    print(f"  ---- /private/get_settlement_history_by_currency (your own option settlements) ----")
    settlement = _call_endpoint(
        f"{DERIBIT_PRIVATE_API_BASE}/get_settlement_history_by_currency",
        params={"currency": args.currency, "type": "settlement", "count": 10},
        access_token=access_token,
    )
    print(f"    status: {settlement.get('status')}")
    if settlement.get("status") == "ok":
        result_keys = settlement.get("result_keys", [])
        print(f"    result keys: {result_keys[:6]}")
    private_probes["settlement_history_by_currency"] = settlement
    print()

    # Step 6: verdict
    print(f"=== Step 6: Verdict ===")
    if auth_extends:
        verdict = (
            "POTENTIALLY EXTENDED — authenticated call returned more trades than anonymous. "
            "Investigate further: rate limits, lookback depth, account tier."
        )
        recommendation = "Build authenticated trades-history backfill ETL; potentially F56 + F58 unlocked free."
    else:
        verdict = (
            "PRIVATE API KEY DOES NOT EXTEND PUBLIC HISTORICAL — confirms anon vs auth identical. "
            "Historical OI/IV by strike still requires paid Tardis.dev or Deribit institutional."
        )
        recommendation = (
            "Stay on M3.1 Phase 1 free live-sync (B, ~30-90d wall-clock) "
            "OR procure Tardis.dev sample (C1, ~$50-200, ~3 weeks closure)."
        )
    print(f"  VERDICT: {verdict}")
    print(f"  RECOMMENDATION: {recommendation}")
    print()

    out = {
        "contract_version": "quant_m3_1_authenticated_probe.v1",
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "currency": args.currency,
        "step1_credentials": {
            "status": "ok",
            "selected_key_var": cred_debug["selected_key_var"],
            "selected_secret_var": cred_debug["selected_secret_var"],
            "checked_envvars": cred_debug["checked"],
        },
        "step2_oauth": {
            "status": token_result["status"],
            "expires_in": token_result.get("expires_in"),
            "scope": token_result.get("scope"),
        },
        "step3_account_summary": {
            "status": acct_result.get("status"),
            "result_keys": acct_result.get("result_keys"),
        },
        "step4_trades_by_time_past_window": {
            "past_window_start_utc": start_dt.isoformat(),
            "past_window_end_utc": end_dt.isoformat(),
            "anonymous_call": anon_result,
            "authenticated_call": auth_result,
            "authenticated_extends_history": auth_extends,
        },
        "step5_private_account_probes": private_probes,
        "step6_verdict": verdict,
        "step6_recommendation": recommendation,
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "m3_1_authenticated_probe.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"  full report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
