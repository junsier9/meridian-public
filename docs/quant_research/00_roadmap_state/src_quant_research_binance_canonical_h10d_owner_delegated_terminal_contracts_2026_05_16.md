# src quant_research binance_canonical_h10d owner-delegated terminal contracts

`Status: owner-delegated terminal governance batch`
`Date: 2026-05-16`
`Scope: remaining binance_canonical_h10d contract coverage after helper closures`

## Decision

This batch treats the user instruction on 2026-05-16 as a one-time
owner-delegated governance authorization for narrow static contracts only.

It does not simulate or fabricate owner approval for source movement, runtime
payload freezing, report golden snapshots, local artifact snapshots, live
readiness, or alpha-quality claims.

The terminal governance posture is:

- every root surface is classified by the root-surface contract;
- low-level helper surfaces that already had narrow contracts stay closed;
- selected remaining runner/entrypoint surfaces receive signature-plus-smoke
  contracts;
- broad runtime semantics remain root-owned and explicitly excluded.

## New Terminal Contract Layer

| contract | surface | terminal boundary |
| --- | --- | --- |
| `src_quant_research_binance_canonical_h10d_symbol_feature_builder_contract.json` | `build_symbol_feature_frame(...)` | root-facade signature and synthetic archive-smoke test presence only |
| `src_quant_research_binance_canonical_h10d_ablation_rescore_contract.json` | ablation/rescore bucket | signatures for the bucket plus existing ablation smoke-test presence |
| `src_quant_research_binance_canonical_h10d_attribution_runner_contract.json` | attribution runners and paper-shadow ledger builder | signatures plus existing runner/ledger behavior-test presence |
| `src_quant_research_binance_canonical_h10d_falsification_suite_contract.json` | `_run_falsification_suite(...)` | signature plus existing suite-smoke test presence |

## Still Not Approved

The following remain out of scope even after this terminal contract batch:

- source movement or package layout changes;
- real local archive scans or artifact snapshots;
- full daily feature-panel schema freezes;
- feature formula, score formula, ablation metric, attribution metric, or
  falsification metric snapshots;
- exact period-return, ledger, strata, validation report, or markdown report
  payload snapshots;
- `build_binance_canonical_dataset(...)` runtime behavior contracts;
- `run_binance_canonical_validation(...)` behavior contracts;
- `write_validation_artifacts(...)` behavior or path-selection contracts;
- strategy promotion or live-readiness authorization.

## Completion Rule

After this batch, governance is considered terminal for autonomous cleanup:

- a surface is either closed at a minimal static/smoke contract layer, or
  explicitly retained as a root-owned runtime boundary;
- further movement requires a new human owner instruction naming the exact
  runtime behavior to freeze or move;
- automation must not convert excluded runtime semantics into closure just
  because a signature contract exists.

## Validation Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
git status --short
```

## Completion Criteria

- This terminal status document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- All four new contracts are covered by `tests/test_static_contracts.py`.
- Existing untracked `artifacts/quant_research/...` paths remain unstaged.
- No commit is created by automation; the owner keeps final commit control.
