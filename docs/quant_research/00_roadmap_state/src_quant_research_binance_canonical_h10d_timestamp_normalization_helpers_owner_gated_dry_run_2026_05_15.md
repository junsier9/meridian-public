# src quant_research binance_canonical_h10d timestamp normalization helpers owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _timestamp_zscore / _timestamp_percentile_rank`

## Decision

Approve a narrow contract-first facade extraction for the h10d-local timestamp
normalization helpers:

- `_timestamp_zscore`
- `_timestamp_percentile_rank`

Do not treat these as shared `features.py` helpers. `features.py` has same-name
private helpers with different behavior and a separate compatibility contract
surface. This batch must keep the extraction local to `binance_canonical_h10d`.

## Caller Baseline

Internal callers in `binance_canonical_h10d.py`:

- `score_binance_ohlcv_core_alpha(...)`

Observed behavior:

- `_timestamp_zscore(...)` coerces values with `pd.to_numeric`, groups by
  timestamp, uses population standard deviation (`ddof=0`), replaces infinite
  output with `NaN`, fills missing values with `0.0`, and returns `float64`.
- `_timestamp_percentile_rank(...)` coerces values with `pd.to_numeric`, fills
  missing values with `0.0`, ranks within timestamp groups with average
  percentile rank, fills missing ranks with `0.5`, and returns `float64`.

## Boundary With `features.py`

`src/enhengclaw/quant_research/features.py` also defines:

- `_timestamp_zscore`
- `_timestamp_percentile_rank`

Those helpers are not part of this implementation because:

- they are already covered by `tests/test_quant_features_utility_helpers.py`;
- they use a different z-score standard deviation behavior;
- they are heavily used by many scorer families;
- merging the two surfaces would over-freeze formula behavior and expand this
  h10d facade extraction into `features.py`.

## Explicit Deferred Surfaces

Do not move or change:

- `features.py` timestamp helpers;
- `_partition_month`;
- funding month-key helpers;
- `score_binance_ohlcv_core_alpha(...)`;
- feature weights or alpha scoring formulas;
- feature subset selection;
- risk-brake logic;
- validation metrics.

## Required Contract Before Movement

Before implementation, add a minimal static contract that freezes only:

- root-facade importability;
- `inspect.signature` shape;
- a tiny `_timestamp_zscore` behavior sample for grouped population z-score and
  constant-group zero fill;
- a tiny `_timestamp_percentile_rank` behavior sample for grouped average
  percentile rank.

The contract must explicitly exclude:

- `features.py` helper behavior;
- full alpha formula behavior;
- scorer output snapshots;
- feature weights;
- backtest metrics;
- validation pass/fail status;
- caller counts.

## Approved Next Automation

If the contract is green, the next automated implementation may:

1. create `src/enhengclaw/quant_research/_binance_canonical_normalization.py`;
2. move only `_timestamp_zscore` and `_timestamp_percentile_rank` there;
3. import both names back into `binance_canonical_h10d.py`;
4. keep `score_binance_ohlcv_core_alpha(...)` in the root facade.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_features_utility_helpers.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- The dry-run baseline is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- `features.py` remains untouched.
- `_partition_month` remains deferred.
- No artifact paths are staged or committed.
