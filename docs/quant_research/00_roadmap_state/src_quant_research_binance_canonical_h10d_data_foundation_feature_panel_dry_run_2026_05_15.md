# src quant_research binance_canonical_h10d data-foundation feature-panel dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: archive_data_foundation_and_feature_panel root-surface bucket`

## Decision

Do not write a new static contract for this bucket yet.

Do not move source in the next automatic batch.

This bucket is not a low-risk signature surface. It mixes local archive
aggregation, feature-panel construction, target construction, PIT universe
selection, funding-cost attachment, and dataset manifest semantics.

Covered root-defined functions:

- `aggregate_1m_klines`
- `build_binance_canonical_dataset`
- `build_symbol_feature_frame`
- `_daily_bars_to_feature_panel`
- `add_binance_ohlcv_core_features`
- `_intraday_realized_vol_by_day`
- `_settlement_premium_by_day`

## Current Caller / Dependency Baseline

Observed direct flow:

- `build_binance_canonical_dataset(...)`
  - resolves config and as-of date;
  - discovers symbols when no explicit symbol list is provided;
  - calls `build_symbol_feature_frame(...)` per symbol;
  - applies frozen or PIT universe selection;
  - attaches funding costs;
  - builds dataset, gap-audit, and feature-manifest payloads.
- `build_symbol_feature_frame(...)`
  - calls `_symbol_partition_paths(...)`;
  - reads local archive partitions through `_read_kline_path(...)`;
  - coerces kline numeric columns;
  - calls `aggregate_1m_klines(...)` for 1h, 4h, and 1d bars;
  - calls `_daily_bars_to_feature_panel(...)`.
- `_daily_bars_to_feature_panel(...)`
  - maps symbol to subject;
  - builds spot/perp aligned daily columns;
  - joins `_intraday_realized_vol_by_day(...)` and
    `_settlement_premium_by_day(...)`;
  - calls `add_binance_ohlcv_core_features(...)`.
- `add_binance_ohlcv_core_features(...)`
  - derives the active h10d feature columns and target columns;
  - is coupled to score-surface feature names and target horizons.

Observed tests:

- `tests/test_binance_canonical_h10d.py` covers `aggregate_1m_klines(...)`
  complete/incomplete bucket behavior.
- `tests/test_binance_canonical_h10d.py` covers a synthetic
  `build_symbol_feature_frame(...)` path.
- Existing archive-helper contracts explicitly exclude
  `aggregate_1m_klines`, `build_symbol_feature_frame`, and
  `build_binance_canonical_dataset` behavior.

## Risk Classification

| surface | risk | reason |
| --- | --- | --- |
| `aggregate_1m_klines` | medium | It is deterministic but controls bucket completeness and OHLCV aggregation semantics. |
| `build_symbol_feature_frame` | high | It crosses archive path discovery, partition reading, aggregation, as-of filtering, and feature-panel creation. |
| `build_binance_canonical_dataset` | high | It crosses config defaults, universe selection, funding attachment, dataset manifests, gap audits, and feature manifests. |
| `_daily_bars_to_feature_panel` | medium/high | It owns the daily panel schema and joins intraday diagnostics into score features. |
| `add_binance_ohlcv_core_features` | high | It creates active factor columns and target labels; this is score-surface adjacent. |
| `_intraday_realized_vol_by_day` | medium | Deterministic helper, but tied to 4h completeness assumptions. |
| `_settlement_premium_by_day` | medium | Deterministic helper, but tied to 1h completeness and 60d smoothing assumptions. |

## Approved Next Steps

Allowed:

- keep the existing root-surface classification contract as the current guard;
- add docs-only watchlists for sub-slices;
- add a future tiny behavior contract only after a fresh plan chooses one
  narrow sub-slice.

Candidate future sub-slices, in preferred order:

1. `aggregate_1m_klines(...)` only, because it already has focused tests and
   does not read files.
2. `_intraday_realized_vol_by_day(...)` plus `_settlement_premium_by_day(...)`,
   but only if the contract uses tiny synthetic frames and does not freeze
   score output.
3. `_daily_bars_to_feature_panel(...)`, only after the intraday helper boundary
   is stable.

Not approved:

- contracting `build_binance_canonical_dataset(...)` in one step;
- contracting `build_symbol_feature_frame(...)` before archive path and
  aggregation sub-slices are separated;
- moving any of these functions into a new module;
- freezing full dataset manifests, gap-audit schemas, feature manifests, target
  labels, or funding attachment behavior.

## Deferred / Owner-Gated

Fresh owner approval required before:

- source migration for any function in this bucket;
- any behavior contract that calls real local archive paths;
- changing local store layout assumptions;
- freezing target-horizon construction;
- changing funding attachment timing;
- mixing this bucket with PIT universe or score-surface refactors.

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
