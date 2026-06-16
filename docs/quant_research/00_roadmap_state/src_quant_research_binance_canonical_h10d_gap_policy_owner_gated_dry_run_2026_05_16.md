# src quant_research binance_canonical_h10d selected-path gap policy owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-16`
`Scope: apply_selected_path_gap_symbol_exclusion / _execution_data_gap_blockers_for_frame / _subjects_from_data_gap_blockers`

## Decision

Do not add a gap-policy static contract and do not move source in this pass.

The selected-path gap policy is not a pure helper slice. It can remove entire
subjects from the scored validation frame when the execution engine reports
missing selected fill or exit paths. That places it on the execution
admissibility boundary, not just on a formatting or wrapper boundary.

Future automation may propose a tiny import/signature-only contract only after
owner approval. It must not freeze exact blocker strings, excluded-subject sets
from real artifacts, validation status, or execution metrics.

## Boundary Map

| surface | current role | risk |
| --- | --- | --- |
| `apply_selected_path_gap_symbol_exclusion(...)` | Applies `execution_gap_policy`, iteratively drops subjects with selected-path execution blockers, and returns a cleaned frame plus audit payload. | high |
| `_execution_data_gap_blockers_for_frame(...)` | Runs `_run_backtest(...)` for base and stress scenarios and collects execution data-gap blockers. | high |
| `_subjects_from_data_gap_blockers(...)` | Parses subject ids from blocker strings shaped like `SUBJECT: missing ...`. | medium |

## Current Callers

| caller | path | role |
| --- | --- | --- |
| `run_binance_canonical_validation(...)` | `src/enhengclaw/quant_research/binance_canonical_h10d.py` | Applies the policy after scoring and stores the audit under `dataset_manifest["execution_gap_policy"]`. |
| `apply_selected_path_gap_symbol_exclusion(...)` | same module | Calls `_execution_data_gap_blockers_for_frame(...)` and `_subjects_from_data_gap_blockers(...)` during iterative subject exclusion. |
| `tests/test_binance_canonical_h10d.py` | test module | Directly tests full-symbol exclusion on a synthetic missing-exit fixture. |

No scripts currently import these helpers directly.

## Config And Artifact Surface

The policy is activated through `execution_gap_policy` in strategy config JSON
files under `config/quant_research/`. The default active mode is
`drop_selected_path_gap_symbols` in current Binance h10d strategy configs.

The audit payload may be surfaced through:

- validation dataset manifests;
- reporting render contracts that display `execution_gap_policy`;
- downstream validation blockers when residual execution data gaps remain.

These artifact/report fields are consumers of the policy result. They are not
approval to freeze exact payload text or blocker string formatting.

## Existing Test Baseline

Direct behavior coverage:

- `test_selected_path_gap_policy_excludes_entire_gap_symbols`

Adjacent/indirect coverage:

- `test_run_backtest_wrapper_smoke_keeps_scenario_and_period_shape`
- execution-backtest tests that produce or suppress `data_gap_blockers`;
- reporting render/static contracts that mention `execution_gap_policy` payload
  shape at a presentation layer.

This baseline is sufficient for an owner-gated dry-run, but not sufficient for
an automatic contract implementation.

## Required Before Any Future Contract

A future implementation plan must first decide whether to add:

- no contract, keep behavior-test coverage only;
- import/signature-only contract for the three helpers; or
- import/signature-only contract plus one tiny parser smoke for
  `_subjects_from_data_gap_blockers(...)`.

If a contract is approved, it must explicitly exclude:

- source migration;
- `_run_backtest(...)` behavior;
- `execution_backtest.backtest_cross_sectional(...)` behavior;
- exact blocker strings;
- exact excluded-subject sets;
- exact audit payload schemas;
- validation pass/fail status;
- report text output;
- execution metric values;
- caller counts.

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
- No source movement is approved.
- No static contract is introduced in this docs-only baseline.
- Future work starts from an explicit owner decision rather than being absorbed
  into the `_run_backtest(...)` contract.
