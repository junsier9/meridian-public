# src quant_research binance_canonical_h10d run backtest owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _run_backtest / h10d validation base-stress execution wrapper`

## Decision

Do not move source and do not add a static contract yet.

`_run_backtest(...)` is a thin wrapper, but it is the central execution gateway
for Binance-canonical h10d validation. It binds h10d strategy config to the
shared `execution_backtest.backtest_cross_sectional(...)` engine:

- `strategy_profile` becomes cross-sectional constraints;
- `_split_contract(config)` becomes the split-realization contract;
- `resolve_execution_cost_model(scenario=...)` selects base or stress costs;
- `require_perp_inventory_open_interest` is forced to `False`;
- `reference_capital_usd`, `capacity_limits`, and `include_periods` are passed
  into the execution engine.

The wrapper is too central to freeze by output snapshot. Any contract that locks
exact return, Sharpe, drawdown, turnover, or period payload values would turn
active execution research into brittle golden files. The next safe automation
step is a tiny direct wrapper smoke test, not a contract JSON.

## Caller Map

| caller | scenario use | current role | risk |
| --- | --- | --- | --- |
| `run_binance_canonical_validation(...)` | `base`, `stress`, `include_periods=True` for base | Produces validation metrics, period returns, blockers, funding readiness context, and validation status inputs. | very high |
| `_execution_data_gap_blockers_for_frame(...)` | `base`, `stress` | Detects missing fill/exit path blockers for selected path exclusion. | high |
| `compute_factor_leave_one_out_attribution(...)` | `base`, `stress` across rescored variants | Computes realized leave-one-out performance deltas. | high |
| `run_binance_core_ablations(...)` | `base` with periods, `stress` without periods | Produces ablation summaries and period-return exports. | high |
| `_run_falsification_suite(...)` | `base`, `stress` | Feeds time shuffle, legacy holdout, stratified holdout, liquidity bucket, and cost stress outputs. | very high |

## Existing Protection

Already protected nearby surfaces:

- `execution_backtest.backtest_cross_sectional(...)` has direct tests in
  `tests/test_execution_backtest.py`.
- Reporting sanitation helpers already strip or preserve `periods` behavior in
  `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json`.
- Validation status, funding blocker, liquidity bucket, and stratified holdout
  each have narrow contracts or dry-run boundaries.

Existing h10d tests indirectly exercise `_run_backtest(...)` through:

- `test_liquidity_bucket_falsification_filters_decisions_not_execution_path`;
- `test_factor_leave_one_out_reports_realized_metric_deltas`;
- `test_ablation_runner_reports_long_only_short_disabled_and_short_veto`;
- `test_selected_path_gap_policy_excludes_entire_gap_symbols`.

These are useful but do not directly protect the wrapper handoff.

## Recommended Next Test Before Contract

Add one tiny direct smoke test before any contract JSON:

- import `_run_backtest` from `binance_canonical_h10d`;
- run the existing `_scored_price_panel(days=12)` fixture through:
  - `scenario="base", include_periods=True`;
  - `scenario="stress", include_periods=False`;
- assert stable structural facts only:
  - base metrics include a non-empty `periods` list;
  - stress metrics do not include `periods`;
  - both outputs include `net_return`, `max_drawdown`,
    `max_trade_participation_rate`, `capacity_breach_count`, and
    `data_gap_blockers`;
  - both outputs return `data_gap_blockers == []` on the clean fixture.

Do not assert exact return, Sharpe, drawdown, turnover, or cost values.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `_run_backtest(...)` source placement;
- `execution_backtest.backtest_cross_sectional(...)`;
- exact portfolio return metrics;
- exact period-return payload values;
- exact trade cost values;
- exact capacity metrics;
- exact falsification metrics;
- exact ablation metrics;
- validation pass/fail status;
- promotion or live-readiness decisions.

## Allowed Future Contract Shape

Only after the direct smoke test exists:

- a contract JSON may freeze `_run_backtest(...)` root importability and
  `inspect.signature` only;
- the static test may require the direct smoke test name to remain present;
- the contract must explicitly exclude exact output metrics, period payloads,
  cost values, source migration, and promotion decisions.

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
- No `src/enhengclaw/quant_research` files move or change.
- No `_run_backtest(...)` contract JSON is introduced in this docs-only commit.
- No checked-in artifact paths are staged.
