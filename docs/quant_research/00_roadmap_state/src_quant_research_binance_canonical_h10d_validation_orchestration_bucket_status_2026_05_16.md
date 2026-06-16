# src quant_research binance_canonical_h10d validation orchestration bucket status

`Status: partial closure / owner-gated root boundary`
`Date: 2026-05-16`
`Scope: run_binance_canonical_validation / write_validation_artifacts / _validation_status / _funding_cost_status`

## Decision

Do not close the full `validation_orchestration_and_artifacts` bucket.

Two status helpers are governance-complete at the current minimal-contract
layer:

- `_validation_status(...)`;
- `_funding_cost_status(...)`.

The artifact helper sublayer is also governance-complete at the current
minimal-contract layer, but `write_validation_artifacts(...)` itself remains
owner-gated because it owns output path selection and full report package
emission.

`run_binance_canonical_validation(...)` remains a root boundary and must not be
contracted, moved, or split automatically.

## Current Bucket Split

| surface | state | boundary |
| --- | --- | --- |
| `_validation_status(...)` | closed at minimal-contract layer | importability, signature, and required gate-behavior test presence only |
| `_funding_cost_status(...)` | closed at minimal-contract layer | importability, signature, and direct funding-status test presence only |
| artifact helper sublayer | closed at minimal-contract layer | helper importability, root facade identity, tiny helper samples only |
| `write_validation_artifacts(...)` | deferred / owner-gated | report package orchestration, output paths, JSON/CSV/Markdown emission |
| `run_binance_canonical_validation(...)` | deferred / owner-gated root boundary | full dataset build, optional funding sync, scoring, gap policy, backtests, falsification, attribution, status, and artifact write orchestration |

## Why This Is Not A Full Closure

`run_binance_canonical_validation(...)` and `write_validation_artifacts(...)`
bind together many already-governed lower layers. A broad contract here would
either duplicate those lower-layer contracts or accidentally freeze active
research outputs such as validation payloads, artifact filenames, report text,
strategy pass/fail state, or live-readiness status.

The current safe posture is therefore:

- close small helper/status surfaces;
- keep orchestration entrypoints in root;
- require a fresh owner-approved dry-run before any facade-first split,
  signature contract, behavior smoke, or path-ownership change for either
  orchestration entrypoint.

## Already Covered By Adjacent Contracts

- `_validation_status(...)`:
  `config/quant_research/src_quant_research_binance_canonical_h10d_validation_status_contract.json`
- `_funding_cost_status(...)`:
  `config/quant_research/src_quant_research_binance_canonical_h10d_funding_cost_status_contract.json`
- artifact helper sublayer:
  `config/quant_research/src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.json`
  and
  `config/quant_research/src_quant_research_binance_canonical_artifacts_module_contract.json`
- `_run_backtest(...)` and selected-path gap policy:
  dedicated backtest/gap-policy contracts and closure docs.
- funding facade entrypoints:
  dedicated funding facade/module contracts and closure docs.

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- `run_binance_canonical_validation(...)` static contract;
- `write_validation_artifacts(...)` static contract;
- source movement for either orchestration entrypoint;
- full validation report payload snapshots;
- artifact path selection snapshots;
- Markdown report text snapshots;
- strategy pass/fail or promotion status snapshots;
- live-readiness authorization snapshots;
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
- Helper/status sublayers are treated as closed at the current
  minimal-contract layer.
- Orchestration entrypoints remain explicitly owner-gated rather than being
  silently absorbed into helper closures.
