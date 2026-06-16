# src quant_research binance_canonical_h10d backtest and gap-policy bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: _run_backtest and selected-path gap policy helpers`

## Decision

The `backtest_and_gap_policy` bucket is closed at the current minimal-contract
layer.

The bucket now has:

- a signature and smoke-test-presence contract for `_run_backtest(...)`;
- a direct wrapper smoke that checks base/stress scenario and period shape
  without freezing metric values;
- an owner decision approving a narrow selected-path gap-policy contract;
- a synthetic parser smoke for `_subjects_from_data_gap_blockers(...)`;
- a signature and behavior-test-presence contract for the three gap-policy
  helpers;
- explicit exclusions for source movement, exact metrics, exact blocker
  strings, exact audit schemas, real excluded-subject snapshots, validation
  status, report text, and caller counts.

No further `backtest_and_gap_policy` automation should widen behavior coverage
or move source without a new owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `_run_backtest(...)` | covered by run-backtest static contract | importability, signature, and direct smoke-test presence only |
| `apply_selected_path_gap_symbol_exclusion(...)` | covered by gap-policy static contract | importability, signature, and required behavior-test presence only |
| `_execution_data_gap_blockers_for_frame(...)` | covered by gap-policy static contract | importability, signature, and required behavior-test presence only |
| `_subjects_from_data_gap_blockers(...)` | covered by gap-policy static contract and parser smoke | importability, signature, and tiny synthetic parser behavior only |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source extraction from `binance_canonical_h10d.py`;
- exact portfolio or execution metric values;
- exact data-gap blocker strings;
- real artifact excluded-subject snapshots;
- exact gap-policy audit payload schemas;
- validation pass/fail or promotion status;
- report text snapshots;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- `backtest_and_gap_policy` work is treated as governance-complete at the
  current minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening the existing contracts.
