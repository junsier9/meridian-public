# src quant_research binance_canonical_h10d daily feature-panel owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-16`
`Scope: _daily_bars_to_feature_panel only`

## Decision

Do not write a contract for `_daily_bars_to_feature_panel(...)` in this batch.

Do not move source.

This helper is the next boundary after the pure in-memory contracts for
`aggregate_1m_klines(...)`, `_intraday_realized_vol_by_day(...)`, and
`_settlement_premium_by_day(...)`, but it is no longer a pure helper. It owns
daily panel schema assembly and calls `add_binance_ohlcv_core_features(...)`,
which creates active feature columns and target labels.

## Current Boundary

`_daily_bars_to_feature_panel(...)` currently:

- maps symbol to subject through `symbol_to_subject(...)`;
- derives `timestamp_ms` and `date_utc`;
- copies daily OHLCV bars into spot/perp-aligned columns;
- sets execution-eligibility columns;
- joins `_intraday_realized_vol_by_day(...)` output;
- joins `_settlement_premium_by_day(...)` output;
- calls `add_binance_ohlcv_core_features(...)`.

The first two joined helper surfaces are now safe to reference from the new
intraday/settlement contract, but the final call into
`add_binance_ohlcv_core_features(...)` keeps this function behavior-sensitive.

## Risk Classification

| surface | risk | reason |
| --- | --- | --- |
| daily schema assembly | medium | It defines the daily h10d panel columns consumed by scoring and execution tests. |
| intraday/settlement joins | low/medium | The helper inputs are now governed, but merge semantics still affect downstream columns. |
| execution eligibility defaults | medium | These defaults feed execution/backtest behavior. |
| `add_binance_ohlcv_core_features(...)` call | high | It creates active feature columns, rolling features, and target labels. |

## Approved Future Contract Shape

A future contract may be considered only if it remains smaller than the full
feature-panel behavior:

- assert root-facade importability and signature;
- assert classification under `archive_data_foundation_and_feature_panel`;
- use a tiny synthetic daily/4h/1h input;
- assert only essential identity columns and presence of joined diagnostic
  columns;
- avoid checking full rolling feature outputs;
- avoid checking target label values;
- avoid freezing full schema ordering.

## Not Approved

Do not:

- move `_daily_bars_to_feature_panel(...)` into a new module;
- freeze `add_binance_ohlcv_core_features(...)` behavior through this helper;
- freeze target horizon construction;
- freeze score outputs;
- freeze full panel schemas or all column ordering;
- combine this with `build_symbol_feature_frame(...)` or
  `build_binance_canonical_dataset(...)`.

## Deferred / Owner-Gated

Fresh owner approval required before:

- any contract for `_daily_bars_to_feature_panel(...)`;
- any contract for `add_binance_ohlcv_core_features(...)`;
- any split of feature-panel schema assembly into a new module;
- any source movement in the data-foundation bucket.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No contract JSON is added in this dry-run batch.
- No production source moves in this dry-run batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
