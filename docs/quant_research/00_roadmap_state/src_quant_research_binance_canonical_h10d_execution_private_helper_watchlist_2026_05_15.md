# binance_canonical_h10d execution Private-Helper Dependency Watchlist

`Status: read-only owner-gated watchlist`
`Scope: binance_canonical_h10d.py dependency on execution_backtest.py private helpers`
`Date: 2026-05-15`

## Decision

Create a watchlist, not a static contract and not a refactor plan.

Do not split `binance_canonical_h10d.py` or `execution_backtest.py` yet. Future
source movement must first account for the fact that `binance_canonical_h10d.py`
imports several underscored helpers from `execution_backtest.py` and uses them
as compatibility surfaces.

## Current Dependency Surface

`src/enhengclaw/quant_research/binance_canonical_h10d.py` directly imports these
private helpers from `src/enhengclaw/quant_research/execution_backtest.py`:

| helper | current h10d use | risk if moved |
| --- | --- | --- |
| `_cross_sectional_target_weights` | builds raw target weights for position attribution and paper shadow ledger | high |
| `_scale_cross_sectional_turnover` | applies turnover caps and pair turnover modes before attribution/ledger rows | high |
| `_next_fill_offset` | aligns decision, fill, and exit timestamps | medium |
| `_price_path_return` | computes gross long/short contribution by held leg | medium |
| `_funding_cost_return` | carries perp funding cost into attribution/ledger | medium |
| `_borrow_cost_return` | carries borrow cost into paper ledger | medium |
| `_trade_costs` | carries fee, slippage, capacity, and data-gap blockers into paper ledger | high |

These names are private by convention but are currently cross-module
dependencies. Treat them as factually public private surfaces until a facade is
designed.

## H10D Call Sites

Main call paths:

- `compute_position_attribution`
  - uses `_next_fill_offset`;
  - calls `_cross_sectional_target_weights`;
  - applies `_apply_short_position_multiplier`;
  - calls `_scale_cross_sectional_turnover`;
  - uses `_price_path_return` and `_funding_cost_return`.
- `build_paper_shadow_execution_ledger`
  - uses `_next_fill_offset`;
  - calls `_cross_sectional_target_weights`;
  - applies `_apply_short_position_multiplier`;
  - calls `_scale_cross_sectional_turnover`;
  - uses `_trade_costs`, `_price_path_return`, `_funding_cost_return`, and
    `_borrow_cost_return`.

The h10d layer also has its own short multiplier path:

- `_apply_short_position_multiplier`
- `short_position_weight_multiplier_column`
- risk-brake columns such as `binance_risk_brake_short_multiplier`

That makes this boundary wider than `quality_bucket_pairs`: it covers h10d
attribution, paper ledger construction, cost accounting, PIT fill/exit alignment,
and short-side risk brakes.

## Required Test Baseline Before Any Refactor

Run before and after any proposed implementation that touches either module:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Protected h10d tests:

- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_attribution_exposes_short_leg_loss`
- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_factor_leave_one_out_reports_realized_metric_deltas`
- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_paper_shadow_execution_ledger_records_no_live_orders`
- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_risk_brake_columns_are_retained_without_entering_alpha_features`
- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_high_vol_rebound_brake_uses_decision_time_market_state`
- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_perp_trade_cost_can_disable_open_interest_inventory_requirement`

Protected execution tests:

- `tests/test_execution_backtest.py -k "quality_bucket_pairs or pair"`

## Refactor Guardrails

A future implementation plan must:

- either keep the seven private helper imports stable or introduce an explicit
  facade and rewrite `binance_canonical_h10d.py` in the same commit;
- prove position attribution and paper shadow ledger behavior still match the
  existing execution helper semantics;
- preserve PIT decision/fill/exit ordering;
- preserve short multiplier application before turnover scaling;
- preserve fee, slippage, funding, borrow, capacity, and data-gap blocker
  semantics;
- keep `quality_bucket_pairs` target-weight behavior under the separate
  execution watchlist;
- keep frozen benchmark v35, scorer-family contracts, and hypothesis-batch
  profile normalization out of scope.

## Explicit Non-Goals

- Do not add a static contract for these private helpers in this watchlist.
- Do not create golden output snapshots for h10d attribution or ledger rows.
- Do not rename private helpers.
- Do not move execution helpers.
- Do not change live-readiness or promotion status.
- Do not broaden this into a `binance_canonical_h10d.py` decomposition plan.

## Reopen Conditions

Open a medium-risk dry-run only if one of these becomes true:

- `execution_backtest.py` is split or its private helpers are renamed;
- `binance_canonical_h10d.py` is split into attribution, paper-ledger, or
  execution-support modules;
- a facade is proposed for execution target weights, turnover scaling, or cost
  accounting;
- tests begin failing because these private imports are no longer stable;
- owner asks to replace private imports with an explicit public execution
  support API.

## Current Recommendation

Keep this boundary in watchlist form. The current tests provide useful behavior
coverage, and the safer next step is documentation of the dependency, not a
premature static contract or source split.
