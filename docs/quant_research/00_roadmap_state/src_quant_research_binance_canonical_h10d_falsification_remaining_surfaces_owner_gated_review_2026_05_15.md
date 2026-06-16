# src quant_research binance_canonical_h10d falsification remaining surfaces owner-gated review

`Status: owner-gated review baseline`
`Date: 2026-05-15`
`Scope: time shuffle / label shuffle / legacy symbol holdout / cost stress`

## Decision

Do not add more falsification-suite contracts in the next automatic batch.

The remaining `_run_falsification_suite(...)` surfaces are not low-risk
standalone helpers. They either depend on `_run_backtest(...)` outputs, random
permutation behavior, or already-covered identity/reporting contracts. Adding
another static contract here would mostly freeze payload shape while leaving the
real research risk untouched.

This review closes the current falsification-suite contract pass:

- decision-time liquidity-bucket filtering is covered by a narrow contract;
- stratified holdout has a direct smoke test and a narrow runner/policy
  signature contract;
- `_rank_ic_summary(...)` is already covered by the reporting metric sanitation
  contract;
- `_stable_int(...)` holdout bucket identity is already covered by the
  hash/identity contract;
- remaining time/label shuffle, legacy holdout metrics, and cost stress stay
  owner-gated.

## Surface Matrix

| surface | current implementation | existing protection | decision |
| --- | --- | --- | --- |
| Time shuffle | Per-subject score permutation with deterministic RNG seed, then `_run_backtest(..., scenario="base")`. | No direct contract; broad backtest metrics intentionally excluded elsewhere. | Keep owner-gated; do not snapshot metrics. |
| Label shuffle | Permutes `target_execution_forward_return`, then calls `_rank_ic_summary(...)`. | `_rank_ic_summary(...)` behavior is covered by `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json`. | Keep permutation behavior owner-gated; no duplicate rank-IC contract. |
| Legacy symbol holdout | `_stable_int(subject) % 2` assigns `holdout_a` / `holdout_b`, then `_run_backtest(...)`; role is diagnostic. | `_stable_int(...)` bucket identity contract plus `test_falsification_suite_marks_legacy_holdout_diagnostic`. | Keep historical diagnostic; do not promote back to hard gate. |
| Cost stress | `_run_backtest(..., scenario="stress")`, stripped of periods. | Validation-status contract consumes stress gate outputs; backtest metrics are excluded from current static contracts. | Keep owner-gated; future audit belongs to `_run_backtest(...)`, not falsification suite. |

## Existing Contracts That Already Cover Nearby Risk

- `src_quant_research_binance_canonical_h10d_decision_time_liquidity_bucket_contract.json`
  protects the decision-time bucket helper signature and direct test presence.
- `src_quant_research_binance_canonical_h10d_stratified_holdout_contract.json`
  protects the stratified holdout runner/policy signature and smoke-test
  presence.
- `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract.json`
  protects `_rank_ic_summary(...)` on a tiny behavior sample.
- `src_quant_research_binance_canonical_h10d_hash_identity_contract.json`
  protects `_stable_int(...)` identity and representative holdout buckets.
- `src_quant_research_binance_canonical_h10d_validation_status_contract.json`
  protects hard-gate aggregation while keeping `_run_falsification_suite(...)`
  deferred.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `_run_falsification_suite(...)`;
- time-shuffle metric payloads;
- label-shuffle permutation payloads;
- legacy symbol-holdout backtest metrics;
- cost-stress backtest metrics;
- `_run_backtest(...)`;
- exact falsification output payload schemas;
- exact random permutation output values;
- promotion or live-readiness decisions.

## Future Path

The next automatic governance pass should leave `_run_falsification_suite(...)`
alone and choose one of these instead:

1. `_run_backtest(...)` owner-gated dry-run, because cost stress and holdout
   metrics both depend on it.
2. Report-rendering consumer dry-run for `_binance_canonical_reporting.py`, if
   report schema stability becomes more important than validation internals.
3. Stop the falsification line here and move to a different oversized module
   boundary.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This review is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No `src/enhengclaw/quant_research` files move or change.
- No new falsification-suite contract JSON is introduced from this review.
- No checked-in artifact paths are staged.
