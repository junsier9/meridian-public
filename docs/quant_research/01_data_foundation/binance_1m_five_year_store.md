# Binance 1m Five-Year Research Store

Purpose: build a reusable local research store from Binance public archive
`1m` kline files, restricted to symbols that have a complete five-year monthly
history window.

This is a Binance-canonical OHLCV store only. It does not backfill CoinGlass
orderbook, liquidation, top-trader, or OI sidecars.

## Default Window

The default discovery window is the latest 60 complete monthly archive files.
On 2026-05-09 this means:

- start month: `2021-05`
- end month: `2026-04`
- required files per market/symbol: `60`

The current calendar month is intentionally excluded because Binance monthly
archive files are complete only after the month closes.

## Store Location

Default local root:

```powershell
$env:LOCALAPPDATA\EnhengClaw\market_history\binance_1m_five_year
```

Current external-drive root on this workstation:

```powershell
E:\EnhengClawData\market_history\binance_1m_five_year
```

Large downloaded data should stay outside git. The store layout is:

```text
data/
  spot/
    BTCUSDT/
      1m/
        2021-05.parquet
        ...
  usdm_perp/
    BTCUSDT/
      1m/
        2021-05.parquet
        ...
discovery/
  latest_five_year_1m_coverage.json
  latest_five_year_1m_coverage.csv
duckdb/
  create_binance_1m_view.sql
last_download_summary.json
```

## Commands

Discover currently active USDT symbols with complete five-year `1m` archive
coverage:

```powershell
python .\scripts\market_data\build_binance_1m_research_store.py discover --external-root E:\EnhengClawData\market_history\binance_1m_five_year --markets spot,usdm_perp
```

Smoke-download only the first eligible symbol:

```powershell
python .\scripts\market_data\build_binance_1m_research_store.py download --external-root E:\EnhengClawData\market_history\binance_1m_five_year --max-symbols 1 --format parquet
```

Download all eligible symbols from the latest discovery summary:

```powershell
python .\scripts\market_data\build_binance_1m_research_store.py download --external-root E:\EnhengClawData\market_history\binance_1m_five_year --format parquet
```

Write the DuckDB view SQL after parquet partitions exist:

```powershell
python .\scripts\market_data\build_binance_1m_research_store.py write-duckdb-view --external-root E:\EnhengClawData\market_history\binance_1m_five_year
```

DuckDB query pattern:

```sql
.read E:/EnhengClawData/market_history/binance_1m_five_year/duckdb/create_binance_1m_view.sql

SELECT market_type, symbol, min(open_time_ms), max(open_time_ms), count(*) AS row_count
FROM binance_1m_klines
GROUP BY 1, 2;
```

## Current Size Estimate

Discovery on 2026-05-09 found `209` eligible market-symbol combinations for
the `2021-05` to `2026-04` window:

- `spot`: `131`
- `usdm_perp`: `78`
- archive zip payload: about `15.8 GiB`
- estimated parquet store: about `26.3 GiB`
- practical disk allowance: `30-40 GiB`

## Validation Outputs

`last_download_summary.json` includes partition-level continuity checks:

- `expected_minute_count`
- `missing_open_time_count`
- `duplicate_open_time_count`
- `outside_month_open_time_count`
- first / last open timestamp

The eligibility gate proves that all required monthly archive files exist. The
continuity check then tells the researcher whether Binance's archived file has
minute gaps inside an otherwise present month.

## Boundary

Use this store for long-horizon OHLCV research: returns, volatility, trend,
reversal, volume, realized liquidity, and forward labels.

Do not treat it as proof for strategies whose core alpha depends on short-window
sidecars such as CoinGlass minute liquidation or orderbook history. Those need
separate sidecar coverage and falsification.
