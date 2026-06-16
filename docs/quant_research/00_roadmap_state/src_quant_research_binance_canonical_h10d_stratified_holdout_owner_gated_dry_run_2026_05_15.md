# src quant_research binance_canonical_h10d stratified holdout owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _run_stratified_repeated_symbol_holdout / stratified holdout policy / validation gate consumption`

## Decision

Do not move source and do not add an import/signature contract yet.

The stratified repeated symbol holdout is now a current-line hard validation
gate, not a historical diagnostic. It is more sensitive than the
decision-time liquidity-bucket helper because it owns both split construction
and the evidence summary consumed by `_validation_status(...)`. A signature-only
contract would be too weak to protect the important behavior, while a broad
payload snapshot would freeze active research logic too early.

The next safe automation step, if approved, is a tiny behavior-smoke test for
the direct stratified holdout surface before any contract JSON is added.

## Boundary Map

| surface | functions / fields | current role | risk |
| --- | --- | --- | --- |
| Holdout runner | `_run_stratified_repeated_symbol_holdout(...)` | Builds repeated two-way subject folds, runs base backtests, and summarizes positive/gap-free evidence. | very high |
| Policy resolver | `_stratified_holdout_policy(...)` | Resolves repeat count, seed, min positive fraction, gap-free requirement, and stratification columns from config/gates. | high |
| Subject strata | `_symbol_stratification_frame(...)` | Builds subject-level liquidity, major/alt, listing-age, and volume buckets. | very high |
| Splitter | `_stratified_two_way_subject_split(...)` | Produces deterministic two-way fold assignment within strata. | high |
| Validation consumer | `_validation_status(...)` | Treats stratified positive fraction and gap-free count as hard gates. | already contract-covered |
| Report consumer | `_binance_canonical_reporting.py` | Reads stratified holdout summary/gate fields for report text. | payload-sensitive |

## Existing Behavior Test Baseline

Current direct/adjacent tests:

- `test_falsification_suite_marks_legacy_holdout_diagnostic`
- `test_validation_status_uses_stratified_holdout_as_hard_gate`
- `test_validation_status_fails_when_stratified_holdout_has_gaps`

These tests prove the current hard-gate role and legacy-vs-stratified
separation. They do not directly protect:

- disabled/empty return shape;
- policy precedence between `stratified_symbol_holdout` and
  `validation_gates`;
- deterministic two-way split stability for a small fixture;
- subject-strata construction boundaries;
- report-consumer payload expectations.

## Recommended Next Test Before Contract

Add one tiny behavior smoke before a contract:

- build a small multi-subject fixture with `stratified_holdout_repeat_count = 1`;
- call `_run_stratified_repeated_symbol_holdout(...)` directly;
- assert `summary.status == "ok"`;
- assert `summary.fold_count == 2`;
- assert each fold has a non-empty `subjects` list;
- assert `policy.min_positive_fraction` and `policy.require_gap_free` reflect
  the configured validation gates.

This would protect the direct surface without freezing net-return values,
backtest metrics, exact strata payloads, or report text.

## Existing Adjacent Contracts

Do not duplicate these surfaces:

- `_validation_status(...)` is covered by
  `src_quant_research_binance_canonical_h10d_validation_status_contract.json`;
- `_decision_time_liquidity_bucket_frame(...)` is covered separately by
  `src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.json`;
- `_stable_hash(...)` / `_stable_int(...)` identity is covered by
  `src_quant_research_binance_canonical_h10d_hash_identity_contract.json`.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `_run_stratified_repeated_symbol_holdout(...)`;
- `_stratified_holdout_policy(...)`;
- `_symbol_stratification_frame(...)`;
- `_stratified_two_way_subject_split(...)`;
- `_stratum_counts(...)`;
- exact fold subject membership;
- exact backtest metric values;
- exact strata payload schemas;
- report text output;
- validation promotion status;
- live-readiness authorization.

## Allowed Future Contract Shape

Only after the direct behavior smoke exists:

- a contract JSON may freeze root importability/signature for
  `_run_stratified_repeated_symbol_holdout(...)` and
  `_stratified_holdout_policy(...)`;
- the static test may require the behavior-smoke test name to remain present;
- the contract must explicitly exclude exact fold assignment, net-return values,
  full payload schemas, report text, and source migration.

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
- No stratified holdout contract JSON is introduced in this docs-only commit.
- No checked-in artifact paths are staged.
