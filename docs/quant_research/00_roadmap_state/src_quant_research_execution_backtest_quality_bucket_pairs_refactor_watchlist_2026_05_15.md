# execution_backtest quality_bucket_pairs Refactor Watchlist

`Status: read-only owner-gated watchlist`
`Scope: src/enhengclaw/quant_research/execution_backtest.py quality_bucket_pairs`
`Date: 2026-05-15`

## Decision

Do not refactor or split `quality_bucket_pairs` yet.

If a future source split is proposed, protect the existing behavior tests first
and treat `_cross_sectional_target_weights` plus `_scale_cross_sectional_turnover`
as factually public private surfaces. They are private by name, but currently
used by tests and by `src/enhengclaw/quant_research/binance_canonical_h10d.py`.

## Current Shape

Primary implementation surfaces:

- `execution_backtest.py:_cross_sectional_target_weights`
  - routes `pair_construction = "quality_bucket_pairs"` into
    `_cross_sectional_pair_target_weights`;
  - remains the call surface used by tests and h10d execution code.
- `execution_backtest.py:_cross_sectional_pair_target_weights`
  - builds quality anchors and quality buckets;
  - selects long/short pairs inside quality buckets;
  - applies pair count, score spread, quality floor, trend-crowding filters,
    short-quality filters, pair-strength soft caps, quality-balance scaling,
    short-leg scaling, broad-trend short scaling, and pair-switch buffering.
- `execution_backtest.py:_scale_cross_sectional_turnover`
  - preserves pair-specific turnover modes:
    `exit_first`, `pair_hold`, and `pair_project`.

Reverse dependencies observed in the read-only audit:

- `tests/test_execution_backtest.py` imports `_cross_sectional_target_weights`
  and `_scale_cross_sectional_turnover` directly.
- `src/enhengclaw/quant_research/binance_canonical_h10d.py` imports
  `_cross_sectional_target_weights` and `_scale_cross_sectional_turnover`
  directly.

## Required Behavior Tests Before Any Split

Run this group before and after any proposed refactor:

```powershell
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
```

Treat the following tests as the minimum protected watchlist.

### Pair Routing And Base Construction

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_constructs_pairs_within_quality_buckets`

### Pair Selection And Rotation

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_require_strong_second_pair`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_buffer_pair_switches`

### Pair Risk Scaling

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_cap_pair_strength`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_trend_crowded_pairs`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_trend_crowded_short_leg`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_low_quality_balance_pair`

### Short-Leg Controls

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_high_quality_short_leg`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_hard_filter_high_quality_short_leg`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_shorts_in_broad_trend`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_filter_extreme_trend_crowding`

### Turnover Modes

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_scale_cross_sectional_turnover_can_prioritize_pair_exits_before_entries`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_scale_cross_sectional_turnover_can_hold_previous_pair_when_rotation_is_capped`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_scale_cross_sectional_turnover_can_project_back_to_single_pair`

## Refactor Guardrails

A future implementation plan must:

- keep `_cross_sectional_target_weights` import-compatible, or rewrite
  `binance_canonical_h10d.py` callers in the same commit;
- keep `_scale_cross_sectional_turnover` import-compatible, or rewrite
  `binance_canonical_h10d.py` callers in the same commit;
- keep tests that import private helpers passing, unless the implementation
  plan explicitly replaces them with an equivalent facade-level test;
- avoid mixing this work with scorer-family contracts, `hypothesis_batch`
  profile normalization, or frozen benchmark v35;
- avoid exact golden-weight snapshots unless a refactor changes internals and
  owner approves the additional brittleness.

## Explicit Non-Goals

- Do not create a static contract for `quality_bucket_pairs` in this watchlist.
- Do not freeze exact pair ordering beyond the existing behavior tests.
- Do not freeze scorer formulas, alpha quality, lab dispatch, or archived
  manifest semantics.
- Do not split `execution_backtest.py` without a new implementation plan.
- Do not move pair-construction logic into `features.py` or
  `hypothesis_batch.py`.

## Reopen Conditions

Open a medium-risk implementation plan only if one of these becomes true:

- `quality_bucket_pairs` target-weight construction needs to move or split;
- `binance_canonical_h10d.py` needs a facade instead of private helper imports;
- existing pair tests become too brittle to support a safe refactor;
- owner asks for a narrower execution-surface contract;
- a runtime bug requires changing pair target-weight or turnover semantics.

## Verification Baseline

Read-only audit verification:

```powershell
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

This watchlist is documentation-only and does not change Python behavior.
