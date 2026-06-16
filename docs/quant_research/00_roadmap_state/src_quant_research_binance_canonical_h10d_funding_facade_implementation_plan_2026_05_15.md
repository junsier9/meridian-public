# src quant_research binance_canonical_h10d funding facade implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: binance_canonical_h10d funding-only helper extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_funding.py` and move
only funding-specific constants/helpers into it. Keep
`binance_canonical_h10d.py` as the root facade for existing import paths and
keep the funding entrypoints in the root module.

This implementation is allowed because the prior static contract now freezes
importability and `inspect.signature` for the candidate helper surface, and the
existing funding behavior smoke covers sync/write/load/attach behavior.

## Approved Move Set

Move these names into `_binance_canonical_funding.py` and import them back into
`binance_canonical_h10d.py`:

- `DEFAULT_FUNDING_COST_ROOT`
- `_funding_columns`
- `funding_symbol_root`
- `funding_partition_path`
- `funding_symbol_manifest_path`
- `funding_sync_summary_path`
- `_read_funding_partition`
- `_dedupe_funding_rows`
- `_http_get_json`
- `_resolve_funding_root`
- `_month_key_from_ms`
- `_month_start_ms`
- `_month_end_ms`

`DEFAULT_FUNDING_COST_ROOT` is included with the helper batch so
`_resolve_funding_root` does not import from the root facade and create a
circular dependency.

## Root Facade Must Keep

The following entrypoints remain defined in `binance_canonical_h10d.py`:

- `sync_funding_cost_history`
- `fetch_funding_rate_rows`
- `write_funding_cost_rows`
- `load_funding_cost_daily`
- `attach_funding_cost_to_panel`

The root module must continue to expose all moved helper names via explicit
imports so existing internal tests and any ad hoc imports stay compatible.

## Explicit Deferred Surfaces

Do not move these in this implementation:

- `_partition_month`, because it is still shared by kline archive partition
  scanning and funding partition filtering.
- `_parse_date`, `_date_to_ms`, `_ms_to_date`, and `_date_utc_series`, because
  they cross PIT freeze, feature build, attribution, and report surfaces.
- `_write_json`, `_frame_or_empty`, and `_write_universe_membership`, because
  they are artifact/report writers.
- Funding entrypoints listed above; only helpers move.

## Compatibility Strategy

- Keep function signatures identical to
  `config/quant_research/src_quant_research_binance_canonical_h10d_funding_facade_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new helper module.
- Use a funding-local default market type for dedupe rows instead of importing
  root `MARKET_TYPE`, avoiding circular imports while preserving the current
  literal value `usdm_perp`.
- Keep provider HTTP behavior delegated to `enhengclaw.utils.binance_http`.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_funding.py
python -m pytest tests\test_binance_canonical_h10d.py -k funding -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `binance_canonical_h10d._http_get_json.__module__` and peer helpers may point
  at `_binance_canonical_funding`, but root attribute access must still work.
- Funding sync/write/load/attach tests remain green.
- Static contract count remains green and continues to exclude source-migration
  approval from behavior semantics.
- No artifact paths are staged or committed.
