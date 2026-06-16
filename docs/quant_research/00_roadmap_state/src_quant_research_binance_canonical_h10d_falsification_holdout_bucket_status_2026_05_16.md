# src quant_research binance_canonical_h10d falsification and holdout bucket status

`Status: partial closure / owner-gated suite boundary`
`Date: 2026-05-16`
`Scope: falsification suite, decision-time liquidity bucket, stratified holdout`

## Decision

Do not close the full `falsification_and_holdout` bucket.

Supersession note: the later owner-delegated terminal batch adds a narrow
signature-plus-smoke contract for `_run_falsification_suite(...)`. It does not
approve suite-level payload snapshots, exact falsification metrics, fold
assignment freezes, strata payload schemas, or source movement.

Two lower-level surfaces are governance-complete at the current
minimal-contract layer:

- `_decision_time_liquidity_bucket_frame(...)`;
- `_run_stratified_repeated_symbol_holdout(...)` and
  `_stratified_holdout_policy(...)`.

The suite orchestrator payload and remaining stratification internals remain
owner-gated. Automation must not add a broad `_run_falsification_suite(...)`
contract, payload snapshot, or source movement without a new owner-approved
dry-run artifact.

## Current Bucket Split

| surface | state | boundary |
| --- | --- | --- |
| `_decision_time_liquidity_bucket_frame(...)` | closed at minimal-contract layer | importability, signature, and direct behavior-test presence only |
| `_run_stratified_repeated_symbol_holdout(...)` | closed at minimal-contract layer | importability, signature, and direct smoke/gate-test presence only |
| `_stratified_holdout_policy(...)` | closed at minimal-contract layer | importability, signature, and adjacent holdout test presence only |
| `_run_falsification_suite(...)` | terminal signature/smoke covered; payload owner-gated | combined time-shuffle, label-shuffle, legacy holdout, stratified holdout, liquidity bucket, and cost-stress payload orchestration remains excluded |
| `_symbol_stratification_frame(...)` | deferred / owner-gated | strata construction semantics and payload shape |
| `_stratified_two_way_subject_split(...)` | deferred / owner-gated | exact fold assignment and seeded split behavior |
| `_stratum_counts(...)` | deferred / owner-gated | strata-count payload details |

## Why This Is Not A Full Closure

The falsification suite aggregates several independently-governed tests into a
single payload consumed by validation status and reports. A broad contract would
over-freeze active falsification output, exact metric values, strata payloads,
fold assignments, and report content.

The current safe posture is therefore:

- keep `_run_falsification_suite(...)` runtime payloads root-owned and owner-gated;
- preserve small contracts around the decision-time liquidity and stratified
  holdout surfaces;
- require a fresh dry-run before adding any contract for suite-level payloads
  or remaining stratification internals.

## Already Covered By Adjacent Contracts

- decision-time liquidity bucket:
  `config/quant_research/src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.json`
- stratified holdout runner/policy:
  `config/quant_research/src_quant_research_binance_canonical_h10d_stratified_holdout_contract.json`
- validation gate consumption:
  `config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json`
- backtest execution wrapper:
  `config/quant_research/src_quant_research_binance_canonical_h10d_run_backtest_contract.json`

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- a broad or payload-expanding `_run_falsification_suite(...)` contract beyond
  the later terminal signature-plus-smoke/static contract;
- suite-level payload snapshots;
- exact time-shuffle, label-shuffle, or cost-stress metric values;
- exact legacy symbol holdout split assignments;
- exact stratified fold subject membership;
- exact strata payload schemas;
- validation report payload snapshots;
- report text snapshots;
- source movement;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the adjacent contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This status document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Covered lower-level surfaces are treated as closed at the current
  minimal-contract layer.
- Suite-level and remaining stratification internals remain explicitly
  owner-gated rather than being silently absorbed into lower-level closures.
