# Phase 5.30 Tier B Evidence And Cache Root Freeze

Date: 2026-05-14

Status: catalog-only root-freeze artifact. This document does not move scripts,
rewrite imports, change scheduled manifests, or approve a wrapper implementation
plan.

Baseline: after `c62ae78 Document Phase 5.29 Tier B helper audit`.

## Decision

Two Phase 5.29 Tier B helpers are now frozen as root-boundary public paths. Their
catalog `safe-to-move` value should be `no`:

- `run_quant_derivatives_sync_evidence.py`
- `sync_coinapi_multi_venue_spot.py`

## Scope

Allowed changes in this phase:

- update the two catalog rows above from `yes-with-wrapper` to `no`;
- update the catalog `safe-to-move` summary counts;
- add this artifact to the governance index.

Forbidden changes in this phase:

- no script moves;
- no root wrappers;
- no import rewrites;
- no scheduled manifest or PowerShell runner edits;
- no README or reusable-checklist path-policy expansion.

## Catalog Contract

Expected `safe-to-move` summary after this phase:

- `safe-to-move = no`: 124
- `safe-to-move = yes`: 32
- `safe-to-move = yes-with-wrapper`: 122

No total script count, root count, category count, status count, or run-priority
count should change.

## Boundary Rationale

`run_quant_derivatives_sync_evidence.py` is a root evidence surface. It is
documented as a manual command in `docs/QUANT_RESEARCH_LAB.md`, writes by-as-of
derivatives sync evidence through runtime support, and can route through Binance
or CoinGlass via `--provider auto`. Moving it into a generic report or provider
helper directory would blur evidence generation with provider sync or
diagnostic lanes.

`sync_coinapi_multi_venue_spot.py` is a multi-venue cache writer. It is cited by
`market_data_inventory.md`, `provider_api_registry.md`, and the parallel 1h
roadmap as the root command for Coinbase, OKEX, and BYBITSPOT per-venue CoinAPI
spot caches. It is not a leaf helper and should not be absorbed into
`provider_leaf_sync_helpers/`.

## Remaining Tier B Wrapper Candidates

This phase deliberately leaves only two Phase 5.29 Tier B helpers as
`yes-with-wrapper` candidates:

- `generate_versioned_panel.py`
- `run_quant_deterministic_daily_sample.py`

They should not move together. If advanced later, each needs its own read-only
dry-run:

- feature-panel dry-run for `generate_versioned_panel.py`;
- deterministic-support dry-run for `run_quant_deterministic_daily_sample.py`.

## Verification Commands

Run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Rationale for the scheduled/runtime tests: this phase changes catalog semantics
for data-foundation evidence/cache roots even though it does not edit scheduled
manifest or runner scripts.
