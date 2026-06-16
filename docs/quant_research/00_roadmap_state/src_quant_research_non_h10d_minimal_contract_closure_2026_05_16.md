# src quant_research non-h10d minimal contract closure

`Status: docs-only minimal closure`
`Date: 2026-05-16`
`Scope: non-binance_canonical_h10d src/enhengclaw/quant_research governance surfaces`

## Decision

Non-h10d src governance is closed at the current minimal-contract layer.

This closure does not approve source movement, scorer formula freezing,
manifest movement, runtime resolver changes, pair target-weight rewrites,
sidecar merge contracts, or alpha-quality claims.

## Closed At Current Layer

| surface | evidence | closure boundary |
| --- | --- | --- |
| `features.py` utility helpers | `src_quant_research_features_utility_compatibility_contract.json` | importability and direct import compatibility only |
| F2 raw scorer shims | `src_quant_research_features_f2_raw_scorer_shim_compatibility_contract.json` | importability/signature only; no scorer formula snapshots |
| F3-A/F3-B scorer families | `src_quant_research_features_f3a_v11_stablecoin_flow_scorer_family_contract.json`, `src_quant_research_features_f3b1_relative_value_spread_scorer_family_contract.json`, `src_quant_research_features_f3b2_residualized_pair_book_scorer_family_contract.json`, `src_quant_research_features_f3b3a_pair_book_v1_v12_scorer_family_contract.json`, `src_quant_research_features_f3b3b_pair_book_v16_v24_alias_scorer_family_contract.json` | importability/signature and named smoke-test presence only |
| manifest lifecycle | `src_quant_research_manifest_lifecycle_catalog.json` | root JSON lifecycle classification only; no manifest movement |
| frozen benchmark v35 | `src_quant_research_frozen_benchmark_v35_identity_contract.json` | identity-only closure; no resolver bridge or runtime reactivation |
| `hypothesis_batch.py` public compatibility | `src_quant_research_hypothesis_batch_compatibility_contract.json` | external scripts/tests compatibility scan only |
| `lab.py` public compatibility | `src_quant_research_lab_compatibility_contract.json` | external scripts/tests compatibility scan only |

## Status-Only / Watchlist

| surface | status |
| --- | --- |
| pair-construction normalization | behavior tests exist; reopen only for normalization or pair allowlist rewrites |
| `execution_backtest.py` `quality_bucket_pairs` | watchlist only; no target-weight logic movement |
| archived manifest references | cataloged but not moved |
| root manifests with owner-gated lifecycle states | classified but left in place |

## Still Owner-Gated

Automation must not expand this closure into:

- splitting `features.py`;
- freezing scorer formula outputs or complete score ordering;
- changing `lab.py` registry or dispatch semantics;
- changing `hypothesis_batch.py` manifest loading or root constants;
- moving root manifests or archived manifest paths;
- restoring v35 into the runtime root;
- adding an archive-aware v35 resolver bridge;
- moving pair-construction target-weight logic;
- freezing sidecar merge behavior;
- claiming alpha quality, promotion readiness, or live readiness.

## Reopen Rule

Future work needs a new owner instruction naming the exact behavior to freeze
or the exact source movement to attempt. Existing import/signature contracts are
not sufficient permission to refactor implementation layout.

## Validation Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -q
python -m pytest tests\test_execution_backtest.py -q
git diff --check
git status --short
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No `src/**` implementation file changes are made in this batch.
- Future non-h10d source movement starts from a fresh dry-run rather than this
  closure document.
