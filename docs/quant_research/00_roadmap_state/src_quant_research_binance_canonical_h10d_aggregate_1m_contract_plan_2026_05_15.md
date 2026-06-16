# src quant_research binance_canonical_h10d aggregate_1m contract plan

`Status: narrow implementation plan`
`Date: 2026-05-15`
`Scope: aggregate_1m_klines only`

## Decision

Approve one tiny static behavior contract for `aggregate_1m_klines(...)`.

Do not move source.

This is the only approved implementation slice from the broader
`archive_data_foundation_and_feature_panel` bucket. It is intentionally smaller
than `build_symbol_feature_frame(...)`, `_daily_bars_to_feature_panel(...)`, or
`build_binance_canonical_dataset(...)`.

## Why This Slice Is Allowed

`aggregate_1m_klines(...)` is deterministic and does not read files or call
provider APIs. Existing unit tests already cover complete and incomplete
1-hour minute buckets.

The contract should preserve only:

- root-facade importability;
- `inspect.signature`;
- classification under `archive_data_foundation_and_feature_panel`;
- a synthetic complete 60-minute to 1-hour aggregation sample;
- a synthetic incomplete-bucket sample for `drop_incomplete=True` and
  `drop_incomplete=False`;
- unsupported interval rejection.

## Explicit Non-Goals

Do not freeze:

- full OHLCV aggregation schemas;
- all interval behavior;
- local archive path discovery;
- parquet or csv.gz reader behavior;
- `build_symbol_feature_frame(...)`;
- `_daily_bars_to_feature_panel(...)`;
- `build_binance_canonical_dataset(...)`;
- feature formulas or target labels;
- funding attachment;
- PIT universe selection.

## Contract Shape

Allowed files:

- `config/quant_research/src_quant_research_binance_canonical_h10d_aggregate_1m_contract.json`
- `tests/test_static_contracts.py`

The test should build a synthetic 60-row minute frame in memory. It should not
read or write archive partitions.

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
