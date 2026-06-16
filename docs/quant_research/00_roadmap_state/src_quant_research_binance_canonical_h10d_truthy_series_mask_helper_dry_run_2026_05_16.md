# src quant_research binance_canonical_h10d truthy-series mask helper dry-run

`Status: owner-gated tiny behavior dry-run`
`Date: 2026-05-16`
`Scope: _truthy_series only`

## Decision

Approve a tiny root-local behavior contract for `_truthy_series(...)`.

Do not move source.

`_truthy_series(...)` looks like a generic utility, but it is not generic in
this module. It is a semantic eligibility-mask helper used by PIT eligibility,
risk-brake, falsification, validation, funding status, and reporting scopes.
The existing PIT and risk-brake contracts already exclude treating it as a
generic utility. This dry-run keeps that stance and approves only a small
root-local mask contract.

## Current Caller Baseline

Observed root-module callers include:

- `prepare_scored_backtest_frame(...)`;
- `add_pit_strategy_eligibility(...)`;
- `_pit_recent_data_eligible(...)`;
- `add_binance_risk_brake_columns(...)`;
- `add_core20_ablation_eligibility(...)`;
- `_decision_time_liquidity_bucket_frame(...)`;
- `_run_stratified_repeated_symbol_holdout(...)`;
- `_funding_cost_status(...)`;
- `_rank_ic_summary(...)`.

This breadth is the reason source movement is not approved.

## Approved Contract Shape

Allowed:

- assert root-facade importability;
- assert root-level symbol exists in `binance_canonical_h10d.py`;
- assert `inspect.signature`;
- assert root-surface classification still assigns `_truthy_series` to
  `pit_universe_and_eligibility`;
- assert adjacent PIT and risk-brake contracts still exclude
  `_truthy_series as a generic utility`;
- run tiny synthetic samples:
  - bool dtype with nulls fills nulls as `False`;
  - string/numeric-like values treat only `1`, `true`, `yes`, and `y` as true
    after trimming and lowercasing.

Not allowed:

- moving `_truthy_series(...)` into a generic utility module;
- changing caller behavior snapshots;
- freezing risk-brake formulas;
- freezing PIT membership snapshots;
- freezing validation metrics or report payloads;
- freezing caller counts.

## Deferred / Owner-Gated

Fresh owner approval required before:

- any source movement involving `_truthy_series(...)`;
- changing accepted truthy tokens;
- using it outside h10d root-local eligibility semantics;
- merging it with a repo-wide bool parser.

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
- A later implementation commit, if added, contains only contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this dry-run batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
