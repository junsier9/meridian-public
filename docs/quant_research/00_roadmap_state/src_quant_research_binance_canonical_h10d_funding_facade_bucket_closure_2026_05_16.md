# src quant_research binance_canonical_h10d funding facade bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: funding facade entrypoints and internal funding module identity`

## Decision

The `funding_facade_entrypoints` bucket is closed at the current
minimal-contract layer.

The bucket now has:

- a root-facade contract for the five funding entrypoints;
- an internal `_binance_canonical_funding.py` module contract that verifies
  importability, root re-export identity, delegated signatures, and tiny pure
  path/month samples;
- a post-extraction review documenting that the root facade remains the public
  surface;
- explicit exclusions for provider HTTP behavior, full sync/load behavior,
  CSV IO snapshots, funding formula behavior, funding-root relocation,
  partition naming changes beyond tiny samples, and caller counts.

No further funding-facade source movement or behavior widening should be
performed by automation without a new owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `sync_funding_cost_history(...)` | covered by funding facade contract and internal module contract | root re-export identity, signature, and excluded behavior boundaries |
| `fetch_funding_rate_rows(...)` | covered by funding facade contract and internal module contract | root re-export identity, signature, and excluded provider HTTP behavior |
| `write_funding_cost_rows(...)` | covered by funding facade contract and internal module contract | root re-export identity, signature, and excluded CSV IO snapshots |
| `load_funding_cost_daily(...)` | covered by funding facade contract and internal module contract | root re-export identity, signature, and excluded full load behavior |
| `attach_funding_cost_to_panel(...)` | covered by funding facade contract and internal module contract | root re-export identity, signature, and excluded formula behavior |

## Explicitly Separate Surfaces

The closure does not cover:

- `_funding_cost_status(...)`, which remains governed by its separate
  validation-blocker contract;
- validation pass/fail decisions;
- funding data-provider availability;
- exact funding rows, partition contents, or sync summaries;
- strategy live-readiness authorization.

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- provider HTTP behavior snapshots;
- exact CSV partition snapshots;
- full funding sync or load behavior snapshots;
- funding-root relocation;
- partition naming changes;
- validation status coupling;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active funding contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Funding facade work is treated as governance-complete at the current
  minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening the existing contracts.
