# Phase 5.27 Supporting Data-Foundation Helper Owner-Gated Watchlist

Date: 2026-05-14

Status: read-only watchlist artifact. This document does not move scripts,
rewrite imports, change catalog counts, change scheduled manifests, or approve
an implementation plan.

Baseline: after `7e05b2b Document Phase 5.26 data foundation root freeze`.

## Purpose

Phase 5.26 permanently froze the seven data-foundation default entrypoints at
root and changed their catalog `safe-to-move` value to `no`. The remaining
supporting data-foundation helpers are not default entrypoints, but they are
also not a clean low-risk movement batch.

This watchlist records the owner-gated posture for the remaining supporting
helpers so the data-sync/root-boundary lane can stay closed unless a specific
future subset is approved.

## Non-Movement Guarantee

No scripts are moved by this artifact.

No `scripts/`, `src/`, `config/`, `tests/`, or artifact-output paths are
changed by this artifact.

No catalog row is changed by this artifact. The remaining supporting helpers
retain their current catalog posture until the owner explicitly approves a
separate freeze or wrapper plan.

## Scope

The watchlist covers the 11 supporting data-foundation helper roots that Phase
5.26 left as owner-gated `future-wrapper-only` candidates:

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

The four Phase 5.25 leaf provider helpers are out of scope because they already
moved under `provider_leaf_sync_helpers/` with root wrappers:

- `sync_cryptoquant_reflexivity_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_okx_funding_history.py`
- `sync_tronscan_stablecoin_tron.py`

## Evidence Inputs

This watchlist is based on:

- Phase 5.24 leaf-only data-sync helper dry-run;
- Phase 5.26 data-foundation default entrypoint root freeze;
- `quant_research_script_catalog.md` rows for the remaining helper roots;
- `config/scheduled_tasks/manifest.json` scan, which found no direct manifest
  row for these 11 helpers;
- repo reference scan across `docs`, `config`, `scripts`, and `tests`.

Important caller findings:

- `run_quant_stablecoin_ethereum_backfill.py` is invoked by the root scheduled
  PowerShell runner `run_openclaw_quant_stablecoin_ethereum_backfill_runner.ps1`.
- `run_quant_stablecoin_ethereum_backfill.py` imports
  `backfill_stablecoin_history.py` by root module name.
- `run_quant_deribit_options_chain_snapshot_cycle.py` hard-calls
  `sync_deribit_options_chain.py` through a sibling path.
- `docs/QUANT_RESEARCH_LAB.md` presents
  `run_quant_derivatives_sync_evidence.py` as a manual command.
- `market_data_inventory.md`, `provider_api_registry.md`, and
  `threshold_provenance.md` use several of these root paths as data-foundation
  evidence anchors.

## Watchlist Tiers

### Tier A: Keep-Root Likely

These helpers are not default entrypoints, but their root path is close enough
to active data-foundation operation that movement should not be planned. If the
owner wants more closure later, the safer action is a root-freeze follow-up that
changes catalog `safe-to-move` to `no`, not a move.

| helper | recommended posture | reason |
| --- | --- | --- |
| `run_quant_stablecoin_ethereum_backfill.py` | keep-root likely | Production stablecoin backfill wrapper; invoked by `run_openclaw_quant_stablecoin_ethereum_backfill_runner.ps1`; writes dated backfill reports and refreshes the stablecoin overlay candidate. |
| `backfill_stablecoin_history.py` | keep-root likely with caller lock | Imported by `run_quant_stablecoin_ethereum_backfill.py` using the root module name; movement requires an active-caller import redesign. |
| `sync_alchemy_stablecoin_ethereum.py` | keep-root likely | Active M3.2 Ethereum stablecoin bootstrap/refresh surface referenced by market inventory and threshold provenance. |
| `sync_binance_derivatives_history.py` | keep-root likely | Coinglass/Binance derivatives foundation writer; inventory says it is direct-invocation and auto-runs as part of cycle prep. |
| `sync_deribit_dvol_history.py` | keep-root likely | Active Deribit DVOL materialization path used by multiplier-overlay work and inventory guidance. |
| `sync_deribit_options_chain.py` | keep-root likely with caller lock | Hard-called by `run_quant_deribit_options_chain_snapshot_cycle.py` through a root sibling path; threshold provenance treats it as the shipped daily snapshot pipeline. |
| `sync_ethereum_address_labels.py` | keep-root likely | Address-label substrate for stablecoin sync/backfill; referenced by inventory and threshold provenance as a root materialization surface. |

Do not write an implementation plan for Tier A without a new owner-approved
boundary redesign. The next low-risk action for this tier, if any, is a
catalog-only root-freeze decision.

### Tier B: Future-Wrapper-Only Watchlist

These helpers look mechanically more wrapperable than Tier A, but they are not
leaf provider sync helpers. Any future move must keep the old root CLI path and
must choose a more specific target than `provider_leaf_sync_helpers/`.

| helper | possible future posture | reason |
| --- | --- | --- |
| `generate_versioned_panel.py` | future wrapper only after feature-panel dry-run | Feature panel materializer that writes versioned panel artifacts; it is not a provider sync helper. |
| `run_quant_derivatives_sync_evidence.py` | future wrapper only after evidence-writer dry-run | Manual evidence command in `docs/QUANT_RESEARCH_LAB.md`; may route through Binance or CoinGlass via `--provider auto`. |
| `run_quant_deterministic_daily_sample.py` | future wrapper only after research-support dry-run | Deterministic sample/support utility, not a data-sync pipeline; tests focus the underlying package function. |
| `sync_coinapi_multi_venue_spot.py` | future wrapper only after multi-venue cache dry-run | Broader per-venue CoinAPI cache writer with roadmap command examples; not as leaf-like as the Phase 5.25 provider helpers. |

Do not move Tier B as a mixed batch. Each possible target directory needs a
separate read-only dry-run because the helpers belong to different semantic
families.

### Tier C: Owner Approval Required Before Any Plan

Every helper in scope is owner-gated. A future implementation plan may start
only after the owner explicitly approves:

- the exact helper subset;
- the exact target directory;
- whether the old root path remains a CLI wrapper or a module-compatible shim;
- the caller/import rewrite strategy;
- the verification commands.

This owner gate applies to both Tier A and Tier B.

## Disallowed Targets

Do not move any of the 11 helpers into:

- `provider_leaf_sync_helpers/`, unless a future dry-run proves the target is a
  true leaf provider helper with no default, scheduled, active-caller, or
  evidence-boundary role;
- `provider_probes/`, because these are not capability probes;
- `provider_diagnostics/`, because they write or materialize foundation data
  rather than merely diagnose existing provider artifacts;
- `coinglass_diagnostics/` or `coinglass_quarantine/`, because this would blur
  provider foundation with CoinGlass diagnostics or R-lane falsification;
- `maintenance/`, because these are active data/research support surfaces, not
  remediation scripts.

## Recommended Closure

The data-sync/root-boundary lane should remain closed for implementation work.

Recommended next owner decision:

1. leave all 11 supporting helpers root-level for now;
2. optionally approve a catalog-only root-freeze for Tier A;
3. only later consider a narrow Tier B read-only dry-run, one semantic family at
   a time.

No movement should be approved from this watchlist alone.

## Verification Commands

For this read-only artifact, run:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

If a future change touches catalog rows, scheduled runners, or README path
policy, also run:

```powershell
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
```
