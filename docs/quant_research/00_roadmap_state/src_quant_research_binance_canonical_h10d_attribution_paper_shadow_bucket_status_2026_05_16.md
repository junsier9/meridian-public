# src quant_research binance_canonical_h10d attribution and paper-shadow bucket status

`Status: partial closure / owner-gated runner boundary`
`Date: 2026-05-16`
`Scope: attribution runners, paper-shadow ledger, and tiny helpers`

## Decision

Do not close the full `attribution_and_paper_shadow` bucket.

Supersession note: the later owner-delegated terminal batch adds a narrow
signature-plus-smoke contract for the attribution runners and paper-shadow
ledger builder. It does not approve ledger schema snapshots, exact attribution
metrics, JSON-record payload freezes, or source movement.

Two tiny helper surfaces are governance-complete at the current
minimal-contract layer:

- `_row_float(...)`;
- `_paper_shadow_action(...)`.

The high-level attribution runner payloads, paper-shadow ledger schemas, empty
payload schemas, aggregation formulas, and JSON-record helper remain
owner-gated. Automation must not add broad runner contracts, ledger schema
snapshots, metric snapshots, or source movement without a fresh
owner-approved dry-run artifact.

## Current Bucket Split

| surface | state | boundary |
| --- | --- | --- |
| `_row_float(...)` | closed at minimal-contract layer | importability, signature, and tiny synthetic value-coercion samples only |
| `_paper_shadow_action(...)` | closed at minimal-contract layer | importability, signature, and tiny synthetic action-transition samples only |
| `compute_position_attribution(...)` | terminal signature/smoke covered; payload owner-gated | execution-path, funding-cost, attribution metric, and summary payload behavior remain excluded |
| `compute_factor_leave_one_out_attribution(...)` | terminal signature/smoke covered; payload owner-gated | rescoring, backtest deltas, rank-IC deltas, and attribution aggregation remain excluded |
| `build_paper_shadow_execution_ledger(...)` | terminal signature/smoke covered; payload owner-gated | paper-shadow ledger schema, costs, capacity, and data-gap blocker behavior remain excluded |
| empty payload helpers | deferred / owner-gated | fallback report/artifact schema shapes |
| aggregation helpers | deferred / owner-gated | side/year/symbol summaries, factor deltas, ledger summary, and JSON-record payloads |
| `_apply_short_position_multiplier(...)` | deferred / owner-gated | adjacent to risk-brake formula behavior and execution target weights |

## Already Covered By Adjacent Contracts

- tiny helper contract:
  `config/quant_research/src_quant_research_binance_canonical_h10d_paper_shadow_tiny_helpers_contract.json`
- backtest/gap-policy contracts:
  contracts for `_run_backtest(...)` and selected-path gap policy;
- funding contracts:
  funding facade and funding-status contracts;
- artifact helper contracts:
  artifact helper/module identity contracts.

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for this bucket;
- broad contracts for attribution runners beyond terminal signature/smoke coverage;
- broad contracts for the paper-shadow ledger builder beyond terminal signature/smoke coverage;
- exact attribution metric snapshots;
- exact factor leave-one-out deltas;
- paper-shadow ledger schema snapshots;
- empty payload schema snapshots;
- full validation report payload snapshots;
- `_apply_short_position_multiplier(...)` behavior;
- `_records(...)` JSON payload behavior;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active tiny-helper contract:

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
- Tiny helper work is treated as closed at the current minimal-contract layer.
- Runner, ledger, aggregation, and schema-bearing surfaces remain explicitly
  owner-gated rather than being silently absorbed into the helper contract.
