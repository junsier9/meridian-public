"""前置-1: dump a REAL Binance daily panel for the dth60 overlay shock-threshold builder.

Read-only, evidence-only (no orders, no live-config change). Fetches perp + spot daily klines for
the LIVE universe and writes a panel carrying a SPOT-derived return_1 so the phase2b builder derives
the q90 thresholds from the SAME shock series the live gauge computes
(augment_panel_with_overlay_shock_gauges is research-defined on spot_close). Without a precomputed
return_1 the builder's normalize_panel would fall back to perp_close and mis-source the thresholds.

Output columns: timestamp_ms, date_utc, subject, usdm_symbol, perp_close, spot_close, return_1.
A symbol with no spot pair is skipped (fail-closed; never perp-substituted for the gauge series).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.binance_usdm_client import (  # noqa: E402
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
)
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path  # noqa: E402
from enhengclaw.live_trading.market_data import (  # noqa: E402
    klines_payload_to_frame,
    resolve_config_symbols,
    symbol_to_subject,
)

DEFAULT_CONFIG = (
    "config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)


def _daily(client: BinanceUsdmClient, symbol: str, *, spot: bool, limit: int) -> pd.DataFrame:
    payload = (client.spot_klines if spot else client.klines)(symbol=symbol, interval="1d", limit=limit).payload
    frame = klines_payload_to_frame(symbol=symbol, payload=payload)
    if frame.empty:
        return frame
    frame["timestamp_ms"] = pd.to_numeric(frame["open_time_ms"], errors="coerce").astype("int64")
    frame["date_utc"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    return frame


def build_panel(config: str, *, limit: int = 120) -> tuple[pd.DataFrame, list[str]]:
    payload = load_live_trading_config(config).payload
    symbols = resolve_config_symbols(payload, override_symbols="")
    perp = BinanceUsdmClient(base_url=BINANCE_USDM_MAINNET_BASE_URL)
    spot = BinanceUsdmClient(base_url=BINANCE_SPOT_MAINNET_BASE_URL)
    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    for symbol in symbols:
        try:
            perp_f = _daily(perp, symbol, spot=False, limit=limit)
            spot_f = _daily(spot, symbol, spot=True, limit=limit)
        except Exception:
            skipped.append(symbol)
            continue
        if perp_f.empty or spot_f.empty:
            skipped.append(symbol)
            continue
        merged = perp_f[["timestamp_ms", "date_utc", "close"]].rename(columns={"close": "perp_close"}).merge(
            spot_f[["date_utc", "close"]].rename(columns={"close": "spot_close"}), on="date_utc", how="inner"
        )
        if merged.empty:
            skipped.append(symbol)
            continue
        merged = merged.sort_values("timestamp_ms")
        merged["subject"] = symbol_to_subject(symbol)
        merged["usdm_symbol"] = symbol
        # SPOT-derived return_1, same default pct_change as features.py / the live gauge.
        merged["return_1"] = merged["spot_close"].pct_change()
        frames.append(merged[["timestamp_ms", "date_utc", "subject", "usdm_symbol", "perp_close", "spot_close", "return_1"]])
    panel = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return panel, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--output-csv", default="artifacts/live_trading/shock_real_panel/real_input_panel.csv")
    args = parser.parse_args(argv)
    panel, skipped = build_panel(args.config, limit=int(args.limit))
    out = resolve_repo_path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)
    distinct_dates = int(panel["date_utc"].nunique()) if not panel.empty else 0
    subjects = int(panel["subject"].nunique()) if not panel.empty else 0
    print(f"panel rows={len(panel)} subjects={subjects} distinct_dates={distinct_dates} skipped={skipped}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
