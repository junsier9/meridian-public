# src quant_research binance_canonical_h10d validation falsification owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: run_binance_canonical_validation / write_validation_artifacts / _run_falsification_suite / _validation_status`

## Decision

Do not move validation or falsification source code in this automation pass.

This surface is the active fail-closed research judgment layer. It binds
dataset construction, scoring, execution-gap blockers, backtests,
falsification, attribution, paper-shadow execution, ablations, funding-cost
readiness, gate aggregation, validation report payloads, and artifact path
selection. A single broad static contract would either be too weak to matter or
would freeze too much active research behavior.

The next automation step, if any, must be contract-first and split into smaller
sub-surfaces. The only immediate low-blast-radius candidate is
`_validation_status(...)` import/signature plus existing gate-test presence.

## Boundary Map

| layer | functions | current role | risk |
| --- | --- | --- | --- |
| Full validation runner | `run_binance_canonical_validation(...)` | Orchestrates dataset build, optional funding backfill, scoring, execution-gap exclusions, metrics, falsification, attribution, paper-shadow execution, ablations, status, and optional artifact writing. | very high |
| Artifact writer | `write_validation_artifacts(...)` | Owns validation output paths and writes report JSON, period returns, membership, attribution, factor attribution, paper-shadow, and ablation artifacts. | very high |
| Falsification suite | `_run_falsification_suite(...)` | Runs deterministic time shuffle, label shuffle, legacy symbol holdout diagnostics, stratified repeated holdout, liquidity-bucket tests, and cost stress. | very high |
| Status aggregation | `_validation_status(...)` | Aggregates blockers, base/stress gates, drawdown cap, participation/capacity, liquidity bucket gate, and stratified holdout gate into `blocked` / `failed` / `passed`. | high but contractable |
| Funding readiness blocker | `_funding_cost_status(...)` | Turns funding sample coverage into a blocker for live-readiness validation. | high, separate dry-run |

## Existing Behavior Test Baseline

Current unit tests already protect important pieces:

- `test_liquidity_bucket_falsification_filters_decisions_not_execution_path`
- `test_falsification_suite_marks_legacy_holdout_diagnostic`
- `test_validation_status_uses_stratified_holdout_as_hard_gate`
- `test_validation_status_fails_when_stratified_holdout_has_gaps`
- `test_validation_status_can_hard_fail_drawdown_cap`

These tests are enough to justify a future narrow `_validation_status(...)`
static contract that requires the gate tests to remain present. They are not
enough to approve moving `_run_falsification_suite(...)`,
`run_binance_canonical_validation(...)`, or `write_validation_artifacts(...)`.

## Existing Adjacent Contracts

Several neighboring surfaces are already governed and should not be duplicated:

- run-id/timestamp helpers are covered by
  `src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract.json`;
- artifact primitive helpers are covered by
  `src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.json`;
- universe-membership writer and risk-brake column projection are covered by
  `src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json`;
- reporting metric sanitation is covered by
  `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json`;
- PIT and risk-brake behavior surfaces are covered only by minimal
  signature/test-presence contracts, not broad behavior snapshots.

## Approved Next Automation

Allowed as the next small implementation batch:

- a contract JSON for `_validation_status(...)` only;
- a static test that checks root-facade importability/signature;
- required test-presence checks for the three validation-status behavior tests;
- explicit exclusions for falsification suite behavior, full validation runner
  behavior, artifact schemas, funding blocker behavior, and promotion status.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `run_binance_canonical_validation(...)`;
- `write_validation_artifacts(...)`;
- `_run_falsification_suite(...)`;
- `_run_stratified_repeated_symbol_holdout(...)`;
- `_decision_time_liquidity_bucket_frame(...)`;
- `_funding_cost_status(...)`;
- full validation report payloads;
- full falsification outputs;
- backtest metric values;
- artifact path selection;
- strategy promotion or live-readiness decisions.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No `src/enhengclaw/quant_research` files move or change.
- No validation/falsification JSON output snapshots are introduced.
- No checked-in artifact paths are staged.
