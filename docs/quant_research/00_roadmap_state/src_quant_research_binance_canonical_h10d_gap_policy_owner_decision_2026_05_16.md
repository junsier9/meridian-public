# src quant_research binance_canonical_h10d selected-path gap policy owner decision

`Status: owner decision baseline`
`Date: 2026-05-16`
`Scope: selected-path gap policy helpers`

## Decision

Approve one minimal follow-up contract path for selected-path gap policy:

- add one tiny synthetic parser smoke for
  `_subjects_from_data_gap_blockers(...)`;
- add one import/signature-only static contract for:
  - `apply_selected_path_gap_symbol_exclusion(...)`;
  - `_execution_data_gap_blockers_for_frame(...)`;
  - `_subjects_from_data_gap_blockers(...)`;
- require the existing full-symbol exclusion behavior test to remain present;
- require the new parser smoke test to remain present.

This approval does not authorize source movement, exact blocker-string
snapshots, real artifact excluded-subject snapshots, validation status freezes,
or execution metric freezes.

## Why A Tiny Parser Smoke Is Acceptable

`_subjects_from_data_gap_blockers(...)` is the only helper in this bucket whose
behavior is small enough to check directly without freezing the broader
execution policy. A synthetic parser smoke can verify that canonical
`SUBJECT: missing ...` messages still produce subjects while unrelated messages
are ignored.

The smoke must stay synthetic. It must not use real validation artifact
blockers as golden strings.

## Approved Contract Shape

The contract may freeze only:

- source module and root path;
- root-level symbol presence;
- `inspect.signature` shape for the three helpers;
- presence of:
  - `test_selected_path_gap_policy_excludes_entire_gap_symbols`;
  - the new parser smoke test;
- explicit exclusion of source movement, `_run_backtest(...)` behavior,
  execution-backtest behavior, exact blocker strings, exact audit schemas,
  exact excluded-subject sets, validation status, report text, execution
  metrics, and caller counts.

## Still Deferred

The following remain owner-gated:

- moving these helpers out of `binance_canonical_h10d.py`;
- freezing exact gap-policy audit payloads;
- freezing exact blocker-string text produced by `execution_backtest.py`;
- freezing real excluded-subject sets from artifacts;
- changing default `execution_gap_policy` behavior in strategy configs.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This owner decision is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The parser smoke and contract implementation are committed separately from
  this docs-only baseline.
- No `src/enhengclaw/quant_research` source file moves or behavior changes.
