"""前置-2 ④: quantify the ONLY non-reconcilable live-vs-research factor gap —
funding_basis_residual_implied_repo_30 — on real Binance data. Evidence-only, READ-ONLY,
no orders, no live-config change.

Both pipelines compute the factor identically as (funding_30 - basis_30) / atr_proxy_20;
ONLY the basis input differs, so funding_30 cancels and the factor gap is exactly
    (basis_research_30 - basis_live_30) / atr_proxy_20
  research basis_proxy = (perp_close - spot_close) / spot_close      (lab.py:1876, CoinAPI-style spot)
  live     basis_proxy = Binance /fapi/v1/premiumIndexKlines item[4] (p10a builder:1230)

The owner uses the resulting magnitude to dispose of the gap: WAIVE the small-weight factor
(-0.0114 of 1.0) or change the live sidecar to adopt the research (perp-spot)/spot basis (now
low-cost — the spot fetch already exists, market_data.fetch_live_spot_close_frame).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
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
from enhengclaw.live_trading.market_data import klines_payload_to_frame, resolve_config_symbols  # noqa: E402
from scripts.live_trading.run_hv_balanced_12factor_p10a_pit_safe_live_feature_builder import (  # noqa: E402
    _fetch_binance_premium_index_daily,
)

DEFAULT_CONFIG = (
    "config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)


def _daily_frame(client: BinanceUsdmClient, symbol: str, *, spot: bool, limit: int) -> pd.DataFrame:
    payload = (client.spot_klines if spot else client.klines)(symbol=symbol, interval="1d", limit=limit).payload
    frame = klines_payload_to_frame(symbol=symbol, payload=payload)
    if frame.empty:
        return frame
    frame["date_utc"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True).dt.date.astype(str)
    return frame


def quantify(config: str, *, limit: int = 90) -> pd.DataFrame:
    payload = load_live_trading_config(config).payload
    symbols = resolve_config_symbols(payload, override_symbols="")
    perp = BinanceUsdmClient(base_url=BINANCE_USDM_MAINNET_BASE_URL)
    spot = BinanceUsdmClient(base_url=BINANCE_SPOT_MAINNET_BASE_URL)
    rows: list[dict] = []
    for symbol in symbols:
        try:
            perp_f = _daily_frame(perp, symbol, spot=False, limit=limit)
            spot_f = _daily_frame(spot, symbol, spot=True, limit=limit)
            prem_f = _fetch_binance_premium_index_daily(client=perp, symbol=symbol, limit=limit)
        except Exception as exc:  # network / missing pair
            rows.append({"symbol": symbol, "status": f"skip:{exc.__class__.__name__}"})
            continue
        if perp_f.empty or spot_f.empty or prem_f.empty:
            rows.append({"symbol": symbol, "status": "skip:empty"})
            continue
        merged = (
            perp_f[["date_utc", "high", "low", "close"]]
            .rename(columns={"high": "perp_high", "low": "perp_low", "close": "perp_close"})
            .merge(spot_f[["date_utc", "close"]].rename(columns={"close": "spot_close"}), on="date_utc", how="inner")
            .merge(prem_f[["date_utc", "basis_proxy"]].rename(columns={"basis_proxy": "basis_live"}), on="date_utc", how="inner")
            .sort_values("date_utc")
        )
        if len(merged) < 35:
            rows.append({"symbol": symbol, "status": "skip:short"})
            continue
        merged["basis_research"] = (merged["perp_close"] - merged["spot_close"]) / merged["spot_close"]
        atr20 = ((merged["perp_high"] - merged["perp_low"]) / merged["perp_close"].shift(1)).rolling(20).mean().iloc[-1]
        if not np.isfinite(atr20) or atr20 == 0.0:
            rows.append({"symbol": symbol, "status": "skip:atr"})
            continue
        basis_live_30 = merged["basis_live"].rolling(30).mean().iloc[-1]
        basis_research_30 = merged["basis_research"].rolling(30).mean().iloc[-1]
        rows.append(
            {
                "symbol": symbol,
                "status": "ok",
                "basis_live_30": basis_live_30,
                "basis_research_30": basis_research_30,
                "atr_proxy_20": atr20,
                # factor_research - factor_live (funding_30 cancels):
                "funding_basis_factor_gap": (basis_research_30 - basis_live_30) / atr20,
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=90)
    parser.add_argument(
        "--output-csv",
        default="artifacts/live_trading/parity_p2/funding_basis_gap_quantification.csv",
    )
    args = parser.parse_args(argv)
    frame = quantify(args.config, limit=int(args.limit))
    out = resolve_repo_path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    ok = frame.loc[frame["status"] == "ok"]
    gap = ok["funding_basis_factor_gap"].abs()
    print(f"symbols ok: {len(ok)}/{len(frame)}")
    if not ok.empty:
        print(
            "funding_basis_residual_implied_repo_30 |gap|: "
            f"max={gap.max():.4f} mean={gap.mean():.4f} median={gap.median():.4f}"
        )
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
