# src quant_research binance_canonical_h10d timestamp normalization helpers implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: h10d-local _timestamp_zscore / _timestamp_percentile_rank extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_normalization.py` and
move only the h10d-local timestamp normalization helpers into it:

- `_timestamp_zscore`
- `_timestamp_percentile_rank`

Keep `binance_canonical_h10d.py` as the root facade through explicit imports.

## Approved Move Set

Move these names into `_binance_canonical_normalization.py` and import them
back into `binance_canonical_h10d.py`:

- `_timestamp_zscore`
- `_timestamp_percentile_rank`

## Root Facade Must Keep

Existing internal and ad hoc callers may continue to access:

- `binance_canonical_h10d._timestamp_zscore`
- `binance_canonical_h10d._timestamp_percentile_rank`

## Explicit Deferred Surfaces

Do not move or change:

- `src/enhengclaw/quant_research/features.py`;
- `features.py` same-name timestamp helpers;
- `score_binance_ohlcv_core_alpha(...)`;
- feature weights;
- feature subset selection;
- `_partition_month`;
- funding month-key helpers;
- validation metrics;
- risk-brake logic.

## Compatibility Strategy

- Keep signatures and tiny behavior samples aligned with
  `config/quant_research/src_quant_research_binance_canonical_h10d_timestamp_normalization_helpers_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new helper module.
- Keep the helper module dependency-light: `numpy` and `pandas` only.
- Keep the extraction h10d-local; do not reuse or redirect `features.py`.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_normalization.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_features_utility_helpers.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `_timestamp_zscore.__module__` and `_timestamp_percentile_rank.__module__`
  point at `_binance_canonical_normalization`.
- Root facade attribute access still works from `binance_canonical_h10d.py`.
- `features.py` remains untouched.
- Static timestamp normalization contract stays green.
- No artifact paths are staged or committed.
