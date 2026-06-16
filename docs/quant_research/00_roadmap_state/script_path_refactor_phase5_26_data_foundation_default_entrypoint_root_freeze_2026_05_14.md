# Phase 5.26 Data-Foundation Default Entrypoint Root Freeze

Date: 2026-05-14

Status: owner decision closure artifact. This document freezes the
data-foundation default entrypoints as permanent root-boundary public paths. It
does not move scripts, rewrite imports, change scheduled manifests, or approve a
new implementation plan.

Decision owner action: Phase 5.26 path 1 from
`script_path_refactor_phase5_26_remaining_root_boundary_owner_gated_review_2026_05_14.md`
is approved.

## Decision

The following data-foundation default entrypoints are permanently keep-root:

- `run_quant_coinapi_spot_sync.py`
- `run_quant_cryptoquant_m3_2_sync_cycle.py`
- `run_quant_deribit_options_chain_snapshot_cycle.py`
- `run_quant_derivatives_sync_cycle.py`
- `run_quant_stablecoin_ethereum_sync_cycle.py`
- `run_quant_universe_freeze.py`
- `run_quant_universe_input_producer.py`

Their root paths are the operational contract for data-foundation refresh,
universe preparation, and scheduled or manual substrate repair. They are not
normal Phase 5.x helper-cleanup candidates.

## Catalog Contract

The catalog should mark the seven paths above as:

- `status = active`
- `run priority = default_entrypoint`
- `safe-to-move = no`

This deliberately differs from supporting data-foundation helpers, which may
remain `yes-with-wrapper` but are still owner-gated before any implementation
plan.

The expected catalog summary after this decision is:

- `safe-to-move = no`: 115
- `safe-to-move = yes`: 32
- `safe-to-move = yes-with-wrapper`: 131

No total script count, root count, category count, status count, or run-priority
count should change.

## Boundary Rules

- Do not move these default entrypoints into `provider_leaf_sync_helpers/`,
  `provider_diagnostics/`, `provider_probes/`, a generic data-sync directory, or
  a utility directory.
- Do not replace them with thin wrappers as part of normal helper cleanup.
- Do not treat `safe-to-move = no` as deprecation. These are current active
  entrypoints.
- A future redesign may refactor internals only after a separate owner-approved
  boundary plan, and the root path must remain callable.

## What Remains Future-Wrapper Only

This decision does not freeze every data-foundation helper. The following
supporting helpers remain owner-gated and may only be considered through a
future wrapper-preserving dry-run:

- `backfill_stablecoin_history.py`
- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_stablecoin_ethereum_backfill.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_binance_derivatives_history.py`
- `sync_coinapi_multi_venue_spot.py`
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`

Do not start an implementation plan for these helpers without explicit owner
approval of the exact subset and target directory.

## Closure Criteria

Data-sync/root-boundary governance is considered closed when:

- the seven default entrypoint catalog rows say `safe-to-move = no`;
- the README Path Policy says data-foundation default entrypoints are permanent
  root-boundary public paths;
- the reusable checklist blocks default data refresh entrypoints from normal
  provider/helper directory admission;
- this artifact is indexed by the governance index;
- static contracts pass.

## Verification Commands

Run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Rationale for the scheduled/runtime test: this change touches the script
catalog and README path policy around default data-refresh paths, even though no
scheduled manifest or runner is changed.

## Stop Condition

Autonomous Phase 5.x movement remains stopped for the data-sync/root-boundary
lane. Further movement in data-foundation space requires one of:

1. owner approval for a named supporting-helper dry-run;
2. owner approval for a boundary-preserving internal redesign;
3. a decision to leave the remaining supporting helpers root-level indefinitely.
