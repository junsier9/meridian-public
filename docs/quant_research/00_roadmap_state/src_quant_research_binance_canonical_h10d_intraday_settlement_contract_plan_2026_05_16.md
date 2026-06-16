# src quant_research binance_canonical_h10d intraday/settlement contract plan

`Status: narrow implementation plan`
`Date: 2026-05-16`
`Scope: _intraday_realized_vol_by_day and _settlement_premium_by_day only`

## Decision

Approve one tiny static behavior contract for two deterministic in-memory
feature-panel support helpers:

- `_intraday_realized_vol_by_day`
- `_settlement_premium_by_day`

Do not move source.

This is the second approved implementation slice from the broader
`archive_data_foundation_and_feature_panel` bucket, after
`aggregate_1m_klines(...)`.

## Why This Slice Is Allowed

Both helpers are deterministic and operate on already-loaded DataFrames. They
do not read archive files, call provider APIs, attach funding data, select PIT
universes, or write artifacts.

The contract must stay synthetic and in-memory.

Important sample-design detail:

- `_intraday_realized_vol_by_day(...)` requires a prior 4h close before the
  target day to produce six non-null 4h log returns for that day.
- `_settlement_premium_by_day(...)` requires a prior 1h close before the first
  target day, and its public output is a 60-day rolling premium with
  `min_periods=60`.

## Contract Shape

Allowed:

- assert root-facade importability;
- assert root-level symbols exist in `binance_canonical_h10d.py`;
- assert `inspect.signature` for both helpers;
- assert the root-surface classification contract still assigns both helpers to
  `archive_data_foundation_and_feature_panel`;
- assert empty-frame schema for both helpers;
- run a tiny 4h synthetic sample where the target day has six complete log
  returns;
- run a 60-day 1h synthetic sample where settlement-window returns differ from
  other hourly returns by a known constant.

Not allowed:

- freezing full feature-panel schemas;
- freezing `add_binance_ohlcv_core_features(...)`;
- freezing score outputs;
- freezing target labels;
- freezing local archive path layout;
- freezing funding attachment behavior;
- moving either helper into a new module.

## Explicit Deferred Surfaces

Still owner-gated:

- `_daily_bars_to_feature_panel(...)`;
- `add_binance_ohlcv_core_features(...)`;
- `build_symbol_feature_frame(...)`;
- `build_binance_canonical_dataset(...)`;
- PIT universe selection;
- funding attachment;
- target horizon construction;
- score-surface formulas.

## Implementation Files

Allowed files:

- `config/quant_research/src_quant_research_binance_canonical_h10d_intraday_settlement_contract.json`
- `tests/test_static_contracts.py`

The implementation commit should not edit production source.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This plan is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The implementation commit contains only contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this implementation batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
