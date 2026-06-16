# Phase 5.28 Tier A Data-Foundation Helper Root Freeze

Date: 2026-05-14

Status: catalog-only root-freeze artifact. This document does not move scripts,
rewrite imports, change scheduled manifests, or approve a wrapper implementation
plan.

Baseline: after `dfbf567 Document Phase 5.27 data foundation helper watchlist`.

## Decision

The Phase 5.27 Tier A supporting data-foundation helpers are now frozen as
root-boundary public paths. Their catalog `safe-to-move` value should be `no`.

Frozen Tier A helpers:

- `run_quant_stablecoin_ethereum_backfill.py`
- `backfill_stablecoin_history.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_binance_derivatives_history.py`
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`

## Scope

Allowed changes in this phase:

- update the seven catalog rows above from `yes-with-wrapper` to `no`;
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

- `safe-to-move = no`: 122
- `safe-to-move = yes`: 32
- `safe-to-move = yes-with-wrapper`: 124

No total script count, root count, category count, status count, or run-priority
count should change.

## Boundary Rationale

These helpers are supporting tools rather than default entrypoints, but each
sits on an active data-foundation boundary:

- stablecoin backfill has a PowerShell runner and imports
  `backfill_stablecoin_history.py` by root module name;
- Alchemy stablecoin sync, Binance derivatives sync, Deribit DVOL sync, Deribit
  options-chain sync, and Ethereum address labels are data substrate
  materialization surfaces cited by inventory or provenance docs;
- `sync_deribit_options_chain.py` is hard-called by
  `run_quant_deribit_options_chain_snapshot_cycle.py` through a sibling root
  path.

Freezing them as `safe-to-move = no` avoids treating active data substrate
surfaces as cleanup candidates.

## Still Owner-Gated

This phase does not approve movement for the Phase 5.27 Tier B watchlist:

- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `sync_coinapi_multi_venue_spot.py`

Those remain `future-wrapper-only` candidates and require a separate dry-run
before any implementation plan.

## Verification Commands

Run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Rationale for the scheduled/runtime tests: this phase changes catalog semantics
for scheduler-adjacent data-foundation helper paths even though it does not edit
the scheduled manifest or runner scripts.
