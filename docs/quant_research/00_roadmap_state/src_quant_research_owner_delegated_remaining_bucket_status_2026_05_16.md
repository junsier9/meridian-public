# src quant_research owner-delegated remaining bucket status

`Status: terminal automation rollup`
`Date: 2026-05-16`
`Scope: src/enhengclaw/quant_research governance after owner-delegated contract batch`

## Decision

The src governance work is terminal for autonomous cleanup at the current
evidence level.

This does not mean every runtime surface is moved, split, or frozen. It means
every reviewed surface is now in one of three durable states:

1. closed at a minimal static or smoke-contract layer;
2. status-only / monitor-only because the existing contract is sufficient;
3. explicitly root-owned and owner-gated for any future runtime behavior,
   payload, path, or source movement change.

## Terminal Evidence Index

The terminal posture is now bound by
`config/quant_research/src_quant_research_terminal_governance_contract.json`
and checked by
`tests/test_static_contracts.py::StaticContractTests::test_quant_research_terminal_governance_contract_stays_stable`.

| evidence | role in terminal closure |
| --- | --- |
| `docs/quant_research/00_roadmap_state/src_quant_research_architecture_governance_plan_2026_05_14.md` | defines the frozen root surfaces and do-not-move boundaries |
| `docs/quant_research/00_roadmap_state/src_quant_research_binance_canonical_h10d_owner_delegated_terminal_contracts_2026_05_16.md` | closes the remaining h10d runner surfaces only at signature-plus-smoke/static layers |
| `docs/quant_research/00_roadmap_state/src_quant_research_owner_delegated_remaining_bucket_status_2026_05_16.md` | declares the terminal three-state closure and the reopen rule for future automation |
| `docs/quant_research/00_roadmap_state/src_quant_research_non_h10d_minimal_contract_closure_2026_05_16.md` | closes non-h10d surfaces only at importability, signature, identity, and compatibility layers |
| `docs/quant_research/00_roadmap_state/research_doc_governance_index.md` | keeps the terminal rollup and related governance docs discoverable |
| `tests/test_static_contracts.py` | machine-checks the composite docs/config/static-test closure and the excluded runtime surfaces |

## Closed At Minimal-Contract Layer

| area | current closure |
| --- | --- |
| h10d low-level helper buckets | artifact helpers, funding facade, gap policy helpers, PIT eligibility, reporting render/sanitation, risk-brake, score surface, time/run metadata, identity/normalization |
| h10d terminal runner coverage | `build_symbol_feature_frame(...)`, ablation/rescore signatures, attribution/paper-shadow runner signatures, and `_run_falsification_suite(...)` signature are covered by owner-delegated static/smoke contracts |
| features.py utility/scorer families | F2/F3 utility and scorer-family contracts cover importability/signature and selected existing smoke evidence only |
| manifest lifecycle | root JSON lifecycle catalog covers active, historical, quarantined, retired, and owner-gated manifest states |
| frozen benchmark v35 | identity-only contract covers archived v35 metadata without resolver reactivation |
| hypothesis/lab public compatibility | existing compatibility contracts preserve external import and patch surfaces |

## Status-Only / Monitor-Only

| area | posture |
| --- | --- |
| pair-construction | existing behavior tests and follow-up decision are sufficient; reopen only for target-weight or normalization rewrites |
| `execution_backtest.py` `quality_bucket_pairs` | watchlist only; do not refactor without dedicated behavior coverage |
| root manifests with `unknown_pending_owner` or `owner_gated_dry_run_only` | cataloged but not moved |
| features.py formula families | contract presence does not freeze formula outputs or score ordering |

## Still Owner-Gated

| area | reason |
| --- | --- |
| source movement / package layout changes | requires caller, import, script, and manifest compatibility proof |
| full data foundation and dataset build | real archive paths, daily feature schema, target labels, funding attachment, PIT universe, and manifests remain path-sensitive |
| `build_binance_canonical_dataset(...)` | crosses config defaults, symbol discovery, archive paths, funding, PIT universe, manifests, validation, and promotion surfaces |
| `run_binance_canonical_validation(...)` | owns dataset build, scoring, backtests, falsification, attribution, status, and artifact orchestration |
| `write_validation_artifacts(...)` | owns output path selection and full report package emission |
| exact ablation, attribution, backtest, falsification, or score outputs | active research semantics; no golden snapshots without a new owner decision |
| report payloads / markdown report text | output schema and prose remain runtime/reporting surfaces |
| v35 archive-aware resolver or reactivation | identity-only closure does not authorize runtime loading changes |
| live-readiness or promotion state | governance contracts do not authorize trading or promotion |

## Reopen Rule

Future automation must start from a fresh owner instruction naming the exact
runtime surface to move or freeze. A signature contract is not enough to expand
into runtime payload snapshots, artifact path contracts, source movement, or
promotion claims.

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

- This rollup is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The composite terminal governance contract is present at
  `config/quant_research/src_quant_research_terminal_governance_contract.json`.
- The h10d terminal contracts are covered by static tests.
- No `artifacts/quant_research/...` path is staged.
- The owner performs the final commit manually.
