# src quant_research binance_canonical_h10d backtest and gap-policy bucket status

`Status: partial closure / owner-gated watchlist`
`Date: 2026-05-16`
`Scope: _run_backtest / selected-path data-gap policy helpers`

## Decision

Do not close the full `backtest_and_gap_policy` bucket yet.

`_run_backtest(...)` is governance-complete at the current minimal-contract
layer: it has a direct smoke test, a signature-only/static contract, and
explicit exclusions for exact metrics, period payload values, cost values,
falsification metrics, ablation metrics, validation status, promotion status,
and source movement.

The selected-path data-gap helpers are now covered at the minimal
signature/behavior-test layer. Their runtime admissibility semantics, exact
blocker strings, artifact/report payloads, and source placement remain
owner-gated.

Supersession note: the later
`src_quant_research_binance_canonical_h10d_backtest_gap_policy_bucket_closure_2026_05_16.md`
closes the selected gap-policy helpers at a minimal contract layer. This older
status document remains valid only for its warning against source movement,
exact blocker strings, artifact/report payload snapshots, and broad execution
admissibility freezes.

## Current Bucket Split

| surface | state | boundary |
| --- | --- | --- |
| `_run_backtest(...)` | closed at minimal-contract layer | importability, signature, and direct smoke-test presence only |
| `apply_selected_path_gap_symbol_exclusion(...)` | closed at minimal-contract layer | importability, signature, and selected behavior-test presence only |
| `_execution_data_gap_blockers_for_frame(...)` | closed at minimal-contract layer | importability, signature, and selected behavior-test presence only |
| `_subjects_from_data_gap_blockers(...)` | closed at minimal-contract layer | importability, signature, and selected parser-test presence only |

## Why This Is Not A Full Closure

The gap-policy helpers decide whether selected execution-path blockers remove
entire symbols from the validation frame. That is closer to execution
admissibility than a pure wrapper handoff. A careless contract could freeze
implementation details, blocker string parsing, blocker string shapes, or
future artifact messages too early.

## Required Dry-Run Before Any Gap-Policy Contract Expansion

A future gap-policy dry-run must identify before expanding beyond the current
minimal contract:

- exact current callers;
- which behavior tests are direct versus indirect;
- whether blocker-string parsing is stable enough to freeze beyond the current
  signature/test-presence layer;
- which artifact/report strings are explicitly excluded;
- whether the safe boundary is import/signature only or a tiny structural smoke;
- validation commands that include both h10d and execution-backtest tests.

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- gap-policy source movement;
- exact data-gap blocker strings;
- exact excluded-subject sets from real artifacts;
- validation pass/fail snapshots;
- execution metric snapshots;
- report payload text snapshots;
- caller-count contracts.

## Validation Baseline

Use the same validation set as `_run_backtest` and the gap-policy behavior
tests:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This status artifact is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- `_run_backtest(...)` is treated as closed at the current minimal-contract
  layer.
- Gap-policy helpers remain explicitly deferred rather than silently included
  in the `_run_backtest(...)` closure.
