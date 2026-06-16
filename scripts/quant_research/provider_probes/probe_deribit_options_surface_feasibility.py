"""probe_deribit_options_surface_feasibility.py — M3.1 Phase 0
feasibility scan.

Probes Deribit Public REST API to assess what data is actually obtainable
free-of-charge (no auth) for the M3.1 options surface lane:
  F56 25Δ skew residual    — needs IV by 25-delta strike per expiry
  F57 IV-RV spread          — needs ATM IV + realized vol
  F58 IV term slope         — needs front + mid expiry IV
  F59 dealer gamma proxy    — needs OI by strike (CRITICAL for E.1)
  F60 vanna-charm window    — needs OI concentration at ATM

Goal: ship a Phase 0 feasibility report telling owner whether full M3.1
execution requires (a) free Public API multi-day live sync (each day
snapshot accumulates), (b) paid historical (Tardis.dev / CoinGlass /
CryptoQuant), or (c) a partial scope that fits Stage-1.

Endpoints probed (Deribit Public REST API v2):
  /public/get_volatility_index_data   — DVOL daily history (already used for SP-G)
  /public/get_book_summary_by_currency — REAL-TIME OI snapshot (no history)
  /public/get_instruments              — active instruments list
  /public/ticker                       — real-time IV per instrument
  /public/get_historical_volatility    — RV history per currency
  /public/get_funding_rate_history     — already covered by binance_derivatives
  /public/get_option_market_data       — OPTION CHAIN aggregate (real-time)

Output:
  artifacts/quant_research/factor_reports/<as-of>/m3_1_options_surface_feasibility.json

The probe runs ONLINE (requires internet); skips network calls if --offline.
Skipped probes still emit "endpoint specification" entries based on Deribit
public docs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]


CARD_CONTRACT_VERSION = "quant_m3_1_options_surface_feasibility.v1"

DERIBIT_PUBLIC_API_BASE = "https://www.deribit.com/api/v2/public"

# Endpoint specs (independent of network calls; sourced from Deribit Public API docs)
ENDPOINT_SPECS = {
    "get_volatility_index_data": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/get_volatility_index_data",
        "auth_required": False,
        "data_grain": "daily DVOL OHLC (30d ATM implied volatility index)",
        "history_depth": "from 2023-07-27 (DVOL launch)",
        "rate_limit": "~10 req/s (Public API)",
        "covers_factors": ["F57 IV-RV spread (proxy via DVOL)"],
        "limitation": "DVOL is universe-wide (BTC + ETH only); NO per-strike or per-expiry detail",
        "status_in_repo": "shipped at sync_deribit_dvol_history.py + SP-G overlay",
    },
    "get_book_summary_by_currency": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/get_book_summary_by_currency",
        "auth_required": False,
        "data_grain": "REAL-TIME snapshot — open_interest + volume + bid/ask per active instrument",
        "history_depth": "REAL-TIME ONLY — no history endpoint",
        "rate_limit": "~10 req/s",
        "covers_factors": ["F59 dealer gamma proxy (real-time OI)", "F60 vanna-charm (real-time OI)"],
        "limitation": "MUST sync daily (or sub-day) live to accumulate history; no backfill",
    },
    "get_instruments": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/get_instruments",
        "auth_required": False,
        "data_grain": "list of active option instruments per currency (BTC/ETH/SOL)",
        "history_depth": "current state only",
        "rate_limit": "~10 req/s",
        "covers_factors": ["instrument metadata (strike, expiry) needed for F56/F58/F59/F60"],
        "limitation": "snapshot only; expired instruments removed",
    },
    "ticker": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/ticker",
        "auth_required": False,
        "data_grain": "REAL-TIME mark_iv + greeks (delta/gamma/vega) per option instrument",
        "history_depth": "REAL-TIME ONLY",
        "rate_limit": "~10 req/s",
        "covers_factors": ["F56 25Δ skew (real-time IV)", "F58 IV term slope (real-time)"],
        "limitation": "must sync live + accumulate; no backfill",
    },
    "get_historical_volatility": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/get_historical_volatility",
        "auth_required": False,
        "data_grain": "daily realized volatility (annualized) per currency",
        "history_depth": "free historical access",
        "rate_limit": "~10 req/s",
        "covers_factors": ["F57 IV-RV spread (RV side)"],
        "limitation": "BTC/ETH only; daily aggregate (universe-wide)",
    },
    "get_option_market_data": {
        "url": f"{DERIBIT_PUBLIC_API_BASE}/get_option_market_data",
        "auth_required": False,
        "data_grain": "REAL-TIME aggregate option chain stats (per currency)",
        "history_depth": "REAL-TIME ONLY",
        "rate_limit": "~10 req/s",
        "covers_factors": ["F59/F60 partial (universe-wide aggregates)"],
        "limitation": "no per-strike breakdown via this endpoint",
    },
}


def probe_endpoint_online(name: str, spec: dict, params: dict | None = None) -> dict:
    """Online probe: makes a single test call and reports response shape."""
    try:
        import requests
    except ImportError:
        return {"status": "skipped", "reason": "requests not installed"}

    try:
        resp = requests.get(spec["url"], params=params or {}, timeout=15)
        if resp.status_code != 200:
            return {
                "status": "http_error",
                "http_status": resp.status_code,
                "body_excerpt": resp.text[:300],
            }
        payload = resp.json()
        if "result" not in payload:
            return {
                "status": "unexpected_shape",
                "payload_keys": list(payload.keys()),
                "body_excerpt": json.dumps(payload)[:500],
            }
        result = payload["result"]
        if isinstance(result, dict):
            sample_keys = list(result.keys())[:10]
        elif isinstance(result, list) and result:
            sample_keys = (
                list(result[0].keys())[:10] if isinstance(result[0], dict) else "primitive_list"
            )
            return {
                "status": "ok",
                "result_type": "list",
                "n_items": len(result),
                "first_item_keys": sample_keys if isinstance(sample_keys, list) else None,
                "first_item_sample": (
                    {k: result[0].get(k) for k in sample_keys[:5]}
                    if isinstance(sample_keys, list)
                    else None
                ),
            }
        else:
            sample_keys = []
        return {
            "status": "ok",
            "result_type": type(result).__name__,
            "result_keys": sample_keys,
            "result_sample": (
                {k: result.get(k) for k in sample_keys[:5]} if sample_keys else result
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "exception", "exception_type": type(exc).__name__, "exception_message": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M3.1 Deribit options surface feasibility scan.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--offline", action="store_true", help="Skip network calls; emit specs only.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== M3.1 Phase 0 Deribit feasibility scan (as-of {args.as_of}) ===")
    print(f"  mode: {'OFFLINE (specs only)' if args.offline else 'ONLINE probe'}")
    print()

    # Probe sample params per endpoint
    sample_params = {
        "get_volatility_index_data": {
            "currency": "BTC",
            "start_timestamp": int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp() * 1000),
            "end_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "resolution": 86400,
        },
        "get_book_summary_by_currency": {"currency": "BTC", "kind": "option"},
        "get_instruments": {"currency": "BTC", "kind": "option", "expired": "false"},
        "ticker": {"instrument_name": "BTC-PERPETUAL"},  # safe perp test (no strike needed)
        "get_historical_volatility": {"currency": "BTC"},
        "get_option_market_data": {"currency": "BTC"},
    }

    endpoint_results = {}
    for name, spec in ENDPOINT_SPECS.items():
        print(f"=== Probing {name} ===")
        print(f"  spec: {spec['data_grain']}")
        print(f"  history: {spec['history_depth']}")
        if args.offline:
            endpoint_results[name] = {
                "spec": spec,
                "probe_status": "offline (skipped)",
            }
            print(f"  probe_status: offline (skipped)")
        else:
            probe = probe_endpoint_online(name, spec, sample_params.get(name))
            endpoint_results[name] = {
                "spec": spec,
                "probe_result": probe,
            }
            print(f"  probe_status: {probe.get('status')}")
            if probe.get("status") == "ok":
                if "result_keys" in probe and probe["result_keys"]:
                    print(f"  sample keys: {probe['result_keys'][:6]}")
                if "n_items" in probe:
                    print(f"  n items: {probe['n_items']}")
            time.sleep(0.5)
        print()

    # Per-factor data path mapping
    print("=== Per-factor data path assessment ===")
    factor_paths = {
        "F57_iv_rv_spread": {
            "data_path": "DVOL daily (already synced) + get_historical_volatility (BTC/ETH only)",
            "stage_1_feasibility": "FEASIBLE (universe-wide gauge only — NOT cross-section score)",
            "blocker": "universe-wide constant per timestamp → G1 fails by design (same as SP-D D1, SP-E E1, SP-G DVOL)",
            "alternative": "use as overlay component (similar to SP-G v3 DVOL throttle)",
        },
        "F56_25d_skew_residual": {
            "data_path": "ticker per option instrument (mark_iv + delta) at daily snapshots",
            "stage_1_feasibility": "REQUIRES daily live sync — no historical backfill from free API",
            "blocker": "must accumulate ~60+ days of daily snapshots before factor is computable",
            "alternative": "Tardis.dev (paid) provides historical IV by strike",
        },
        "F58_iv_term_slope": {
            "data_path": "ticker per multi-expiry ATM option at daily snapshots",
            "stage_1_feasibility": "REQUIRES daily live sync (same as F56)",
            "blocker": "expiry rolls + strike interpolation complexity",
            "alternative": "Tardis.dev paid",
        },
        "F59_dealer_gamma_proxy": {
            "data_path": "get_book_summary_by_currency (real-time OI by strike) + spot price + BSM grid",
            "stage_1_feasibility": "REQUIRES daily live sync — no historical backfill",
            "blocker": "OI snapshot + BSM grid implementation effort (~3-5d)",
            "alternative": "Tardis.dev (paid) provides historical OI by strike",
        },
        "F60_vanna_charm_window": {
            "data_path": "get_book_summary_by_currency + get_instruments (expiry calendar)",
            "stage_1_feasibility": "REQUIRES daily live sync (same as F59)",
            "blocker": "OI snapshot + expiry calendar accumulation",
            "alternative": "Tardis.dev paid",
        },
    }

    for fid, info in factor_paths.items():
        print(f"  {fid}:")
        print(f"    data_path:           {info['data_path']}")
        print(f"    stage_1_feasibility: {info['stage_1_feasibility']}")
        print(f"    blocker:             {info['blocker']}")
        print(f"    alternative:         {info['alternative']}")
        print()

    # Decision matrix
    print("=== Phase 0 decision matrix ===")
    decision_options = [
        {
            "option": "A",
            "label": "Stage-1 NO-OP — defer M3.1 to Stage-2",
            "scope": "M3.1 deferred until owner decides on data source (free live-sync vs paid history)",
            "effort": "0",
            "delivers": "scoping document + decision request",
            "risk": "Day 90 出口准则 NOT YET status preserves",
        },
        {
            "option": "B",
            "label": "Build Deribit live-sync pipeline + start accumulating",
            "scope": "Ship sync_deribit_options_chain.py daily snapshot of OI + IV by strike. Accumulate 60-90 days. Then compute F56-F60. ",
            "effort": "Initial XL (~3-5d build); continuous (daily run); 60-90 days wall-clock for first usable factor",
            "delivers": "data infrastructure today; factors in 2-3 months",
            "risk": "data quality / Deribit API rate limits / instrument churn / no fast iteration",
        },
        {
            "option": "C",
            "label": "Procure Tardis.dev sample (cheap historical) + ship F59 quickly",
            "scope": "Buy Tardis.dev BTC + ETH options snapshots (~$50-200 historical sample). Build F59 dealer-gamma proxy + run admission audit.",
            "effort": "M-L (~1-2 days build + admission audit) once data is in hand",
            "delivers": "complete F59 + partial F56/F60 in 1-2 days",
            "risk": "data licensing review; vendor relationship setup; one-time cost",
        },
        {
            "option": "D (RECOMMENDED in Stage-1)",
            "label": "F57 IV-RV spread as overlay v4 candidate (Stage-1 immediate)",
            "scope": "F57 = DVOL_close - realized_volatility_60. Implement as universe-wide gauge → use as overlay v4 throttle component (similar to SP-G v3). Accept that as score factor it would G1-fail by design.",
            "effort": "S-M (~3-4h)",
            "delivers": "extends SP-G v3 DVOL overlay with IV-RV-spread gauge; tests if richer vol-regime overlay overlaps lsk3 losing days",
            "risk": "likely NEUTRAL like SP-G v3 (the underlying issue: vol regime ≠ strategy losing days)",
        },
        {
            "option": "E",
            "label": "M3.1 Phase 0 doc-only — status quo until Stage-2 transition",
            "scope": "This commit ships the feasibility scan + scoping doc. Owner reviews. No further M3.1 work in this Stage-1 cycle.",
            "effort": "0 (this commit)",
            "delivers": "informed Stage-2 decision basis; clean Stage-1 closure",
            "risk": "Day 90 出口准则 NOT YET status preserves; Stage-1 alpha exhausted",
        },
    ]

    for d in decision_options:
        print(f"  Option {d['option']}: {d['label']}")
        print(f"    scope:    {d['scope']}")
        print(f"    effort:   {d['effort']}")
        print(f"    delivers: {d['delivers']}")
        print(f"    risk:     {d['risk']}")
        print()

    print("=== Recommended Phase 0 conclusion ===")
    print("  Option E (M3.1 Phase 0 doc-only) is the most responsible Stage-1 closure.")
    print("  Rationale: M3.1 full execution requires multi-day data sync OR paid history;")
    print("  neither fits Stage-1 research lane. SP-J AT-PAR confirmed existing-panel alpha")
    print("  is exhausted. Owner-side decision needed before proceeding to Option B/C.")
    print()
    print("  Future-action: when Owner approves multi-day sync OR paid history, M3.1 Phase 1")
    print("  starts with sync_deribit_options_chain.py (Option B) OR Tardis sample purchase")
    print("  (Option C). Scoping doc archived for that decision.")
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "mode": "offline" if args.offline else "online",
        "endpoint_probes": endpoint_results,
        "per_factor_data_paths": factor_paths,
        "decision_options": decision_options,
        "recommended_option": "E",
        "recommended_rationale": (
            "Stage-1 closure — M3.1 full execution requires multi-day data sync or paid "
            "history; neither fits Stage-1. SP-J AT-PAR confirmed existing-panel alpha "
            "exhausted. Owner-side decision needed before Option B (live sync) or C "
            "(paid history)."
        ),
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "m3_1_options_surface_feasibility.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Feasibility report at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
