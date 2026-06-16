# src quant_research binance_canonical_h10d falsification suite owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _run_falsification_suite / stratified holdout / liquidity-bucket falsification`

## Decision

Do not move source and do not add a broad `_run_falsification_suite(...)`
contract in the next implementation batch.

The falsification suite is a high-risk research judgment surface. It combines
placebo score shuffles, label shuffles, legacy symbol holdout diagnostics,
stratified repeated symbol holdout, decision-time liquidity-bucket
falsification, and stress-cost reruns. Freezing the whole return payload would
either make future falsification improvements brittle or give false comfort
without protecting the behaviors that matter.

The next safe automation step, if any, should be a tiny contract for the
decision-time liquidity-bucket helper only:

- `_decision_time_liquidity_bucket_frame(...)` root importability/signature;
- required behavior-test presence for
  `test_liquidity_bucket_falsification_filters_decisions_not_execution_path`;
- explicit exclusion of `_run_falsification_suite(...)` payload snapshots,
  stratified-holdout formulas, shuffle metrics, and promotion decisions.

## Boundary Map

| surface | functions / fields | current role | risk |
| --- | --- | --- | --- |
| Suite orchestrator | `_run_falsification_suite(...)` | Runs all falsification branches and returns the combined payload. | very high |
| Time shuffle | deterministic RNG seed `20260510` + per-subject score permutation | Placebo score-path diagnostic. | high |
| Label shuffle | shuffled `target_execution_forward_return` + `_rank_ic_summary(...)` | Label-noise diagnostic. | high |
| Legacy symbol holdout | `_stable_int(...) % 2` split into `holdout_a` / `holdout_b` | Historical diagnostic only; no longer the hard promotion gate. | medium/high |
| Stratified holdout | `_run_stratified_repeated_symbol_holdout(...)` and helpers | Current hard validation gate via `_validation_status(...)`. | very high |
| Liquidity-bucket falsification | `_decision_time_liquidity_bucket_frame(...)` | Filters decisions by bucket while preserving the full execution path. | high but contractable |
| Cost stress | `_run_backtest(..., scenario="stress")` | Stress execution-cost rerun. | high |

## Existing Behavior Test Baseline

Current direct tests:

- `test_liquidity_bucket_falsification_filters_decisions_not_execution_path`
- `test_falsification_suite_marks_legacy_holdout_diagnostic`

Adjacent status-gate tests:

- `test_validation_status_uses_stratified_holdout_as_hard_gate`
- `test_validation_status_fails_when_stratified_holdout_has_gaps`

These tests justify a narrow helper contract for
`_decision_time_liquidity_bucket_frame(...)`. They do not justify a broad
payload contract for `_run_falsification_suite(...)` or source movement into a
new validation module.

## Current-Line Boundaries

Keep these distinctions explicit:

- legacy symbol holdout is diagnostic evidence only;
- stratified repeated symbol holdout is the current hard gate;
- decision-time liquidity bucket filtering must not truncate the execution
  path;
- cost stress remains execution/backtest behavior, not a falsification formula
  snapshot;
- validation status aggregation is already covered separately and should not be
  duplicated here.

## Existing Adjacent Contracts

Do not duplicate these surfaces:

- `_validation_status(...)` is covered by
  `src_quant_research_binance_canonical_h10d_validation_status_contract.json`;
- `_stable_hash(...)` / `_stable_int(...)` identity is covered by
  `src_quant_research_binance_canonical_h10d_hash_identity_contract.json`;
- reporting metrics, PIT eligibility, risk-brake behavior, and funding blocker
  behavior are covered by their own contracts or dry-run artifacts.

## Approved Next Automation

Allowed as the next small implementation batch:

- a contract JSON for `_decision_time_liquidity_bucket_frame(...)` only;
- a static test that checks root-facade importability and `inspect.signature`;
- a required behavior-test presence check for
  `test_liquidity_bucket_falsification_filters_decisions_not_execution_path`;
- cross-check that the validation-status contract still treats
  `_run_falsification_suite(...)`, `_run_stratified_repeated_symbol_holdout(...)`,
  and `_decision_time_liquidity_bucket_frame(...)` as deferred surfaces.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `_run_falsification_suite(...)`;
- `_run_stratified_repeated_symbol_holdout(...)`;
- `_stratified_holdout_policy(...)`;
- `_symbol_stratification_frame(...)`;
- `_stratified_two_way_subject_split(...)`;
- `_rank_ic_summary(...)`;
- `_run_backtest(...)` metrics;
- suite-level payload schemas;
- shuffle metric values;
- stratified holdout formulas and thresholds;
- legacy holdout split assignment beyond the existing hash identity contract;
- strategy promotion or live-readiness decisions.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No `src/enhengclaw/quant_research` files move or change.
- No broad falsification payload snapshot is introduced.
- No checked-in artifact paths are staged.
