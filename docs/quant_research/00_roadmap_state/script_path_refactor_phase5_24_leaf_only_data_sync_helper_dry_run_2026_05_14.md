# Phase 5.24 Leaf-Only Data-Sync Helper Dry-Run

Date: 2026-05-14

Status: read-only dry-run artifact. No scripts are moved by this document.

Baseline: after `15e44e8 Document Phase 5.23 data-sync root boundary strategy`.

## Purpose

Phase 5.23 froze the data-sync/root-boundary keep-root strategy. This dry-run
selects a small leaf-only subset from the remaining data-sync helper bucket,
then records caller paths, config/scheduled references, and artifact output
paths before any implementation is approved.

The goal is not to move data-sync scripts yet. The goal is to find whether a
small, mechanically safe first wrapper batch exists without weakening scheduled
tasks, default entrypoints, CoinGlass full-stack sync, or h10d boundary
semantics.

## Search Scope

Candidate source bucket from Phase 5.23:

- `backfill_stablecoin_history.py`
- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_stablecoin_ethereum_backfill.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_binance_derivatives_history.py`
- `sync_coinapi_multi_venue_spot.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`
- `sync_okx_funding_history.py`
- `sync_tronscan_stablecoin_tron.py`

Read-only evidence commands used:

```powershell
git status --short
git log -3 --oneline
rg --fixed-strings <candidate> . -g "*.py" -g "*.ps1" -g "*.md" -g "*.json" -g "*.yaml" -g "*.yml" -g "*.toml"
rg --fixed-strings <candidate_without_ext> scripts src tests config -g "*.py" -g "*.ps1" -g "*.json" -g "*.yaml" -g "*.yml" -g "*.toml"
rg "argparse|ArgumentParser|output|output-dir|artifacts|external_market_data|LOCALAPPDATA|EnhengClaw|to_csv|write_text|write_bytes|open\(|Path\(|mkdir|DEFAULT|default" scripts/quant_research/<candidate>.py
rg "generate_versioned_panel|run_quant_derivatives_sync_evidence|sync_cryptoquant_reflexivity_history|sync_cryptoquant_stablecoin_history|sync_okx_funding_history|sync_tronscan_stablecoin_tron" config scripts -g "*.json" -g "*.ps1" -g "*.toml" -g "*.yaml" -g "*.yml"
```

The scheduled/config scan for the six shortlisted candidates returned no
matches.

## Shortlist Decision

Shortlist: 6 candidates.

Recommended first implementation subset, if the owner later approves movement:

- `sync_okx_funding_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_tronscan_stablecoin_tron.py`

Watchlist candidates, still leaf-like but less pure as provider-sync helpers:

- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`

No implementation is approved by this artifact. Because Phase 5.23 classifies
data-sync/data-foundation paths as owner-gated, a later implementation plan
still needs explicit owner approval.

## Shortlisted Candidate Matrix

| Candidate | Proposed posture | Caller/import surface | Config/scheduled surface | Artifact/output paths | Risk |
| --- | --- | --- | --- | --- | --- |
| `sync_okx_funding_history.py` | First-batch candidate | No non-self Python caller found. Markdown/catalog refs in provider registry and market data inventory. | None found in `config` or PowerShell scheduled surfaces. | Default `%LOCALAPPDATA%/EnhengClaw/okx_funding/<BASE>_funding_8h.csv`; custom `--output-dir`. | Low-medium |
| `sync_cryptoquant_stablecoin_history.py` | First-batch candidate | No script-level caller found. Active `run_quant_cryptoquant_m3_2_sync_cycle.py` imports `run_cryptoquant_stablecoin_sync` from `src`, not this script. Tests target the `src` function. | None found in `config` or PowerShell scheduled surfaces. | Default `%LOCALAPPDATA%/EnhengClaw/onchain_cryptoquant/stablecoin_supply_daily.csv`, `stablecoin_exchange_flows_daily.csv`, `latest_sync_summary.json`; optional `--report-path`. | Low-medium |
| `sync_cryptoquant_reflexivity_history.py` | First-batch candidate | No script-level caller found. Active `run_quant_cryptoquant_m3_2_sync_cycle.py` imports `run_cryptoquant_reflexivity_sync` from `src`, not this script. Tests target the `src` function. | None found in `config` or PowerShell scheduled surfaces. | Default `%LOCALAPPDATA%/EnhengClaw/onchain_cryptoquant/reflexivity_exchange_flows_daily.csv`, `reflexivity_market_indicators_daily.csv`, `latest_reflexivity_sync_summary.json`; optional `--report-path`. | Low-medium |
| `sync_tronscan_stablecoin_tron.py` | First-batch candidate | No script-level caller found. Tests target `run_m3_2_tron_stablecoin_sync` from `src`, not this script. Markdown refs in provider registry, market inventory, and M3.2 planning docs. | None found in `config` or PowerShell scheduled surfaces. | Default `%LOCALAPPDATA%/EnhengClaw/onchain_stablecoin_tron/daily_aggregates.csv`, `latest_sync_summary.json`; optional `--report-path`. | Low-medium |
| `generate_versioned_panel.py` | Watchlist candidate | No non-self Python caller found. It is a panel materializer using lab feature-set helpers, not a provider sync. | None found in `config` or PowerShell scheduled surfaces. | `artifacts/quant_research/features/<as_of>-cross-sectional-daily-1d-h5d-features-<version>/features.csv.gz` under `--artifacts-root`. | Medium |
| `run_quant_derivatives_sync_evidence.py` | Watchlist candidate | No non-self Python caller found, but `docs/QUANT_RESEARCH_LAB.md` presents it as a manual command. Calls runtime support to write an as-of derivatives sync summary. | None found in `config` or PowerShell scheduled surfaces. | Derivatives external root summary: `<derivatives_external_root>/summaries/by_as_of/<as_of>/sync_summary.json`; prints JSON to stdout. Provider may be Binance or CoinGlass via `--provider auto`. | Medium |

## First-Batch Wrapper Strategy If Approved Later

Target directory is not approved yet. If implementation is later approved, use
a narrow directory name that cannot be mistaken for a default sync surface. A
candidate name is:

- `scripts/quant_research/leaf_data_sync_helpers/`

Wrapper requirements:

- keep the root path for each selected script;
- root wrapper must forward `argv` unchanged;
- root wrapper should delegate with `runpy.run_path(..., run_name="__main__")`
  unless a script-specific package import is safer;
- no scheduled/config references should change because none currently point to
  these roots;
- docs and catalog links must be updated in the same implementation commit;
- README Path Policy must state that `leaf_data_sync_helpers/` is not a home for
  default sync entrypoints, scheduled surfaces, CoinGlass full-stack sync, or h10d
  validation boundaries.

## Deferred From First Batch

These paths remain deferred because the dry-run found a stronger boundary,
caller, scheduled, or semantic reason not to include them in a leaf-only first
batch.

| Deferred path | Reason |
| --- | --- |
| `backfill_stablecoin_history.py` | Imported by `run_quant_stablecoin_ethereum_backfill.py` using a root-level import. Moving it would require caller/import strategy around an active stablecoin backfill path. |
| `run_quant_stablecoin_ethereum_backfill.py` | Referenced by `scripts/quant_research/run_openclaw_quant_stablecoin_ethereum_backfill_runner.ps1`; not leaf-only. |
| `sync_alchemy_stablecoin_ethereum.py` | Active M3.2 Ethereum stablecoin bootstrap/refresh path; referenced by `stablecoin_regime.py` guidance and threshold provenance. |
| `sync_binance_derivatives_history.py` | Runtime support and tests center on the underlying Binance derivatives sync function; inventory says it auto-runs as part of cycle prep. Keep out of this leaf-only batch. |
| `sync_coinapi_multi_venue_spot.py` | Mechanically wrapperable, but broader multi-venue cache semantics and roadmap command examples make it less suitable than the selected public-provider leaf helpers. |
| `sync_deribit_dvol_history.py` | Active multiplier overlay dependency; `multiplier_overlay.py` tells users to materialize DVOL through this root path. |
| `sync_deribit_options_chain.py` | Hard-called by `run_quant_deribit_options_chain_snapshot_cycle.py` through `SYNC_SCRIPT = SCRIPT_DIR / "sync_deribit_options_chain.py"`; not leaf-only. |
| `sync_ethereum_address_labels.py` | Imported directly by `run_quant_stablecoin_ethereum_sync_cycle.py` and `run_quant_stablecoin_ethereum_backfill.py`; moving requires active-caller import rewrite. |
| `run_quant_deterministic_daily_sample.py` | Low mechanical risk but not a data-sync helper; belongs in a separate utility/research support dry-run. |

## Caller And Output Notes

### `sync_okx_funding_history.py`

- Caller surface: no non-self Python caller found.
- Config/scheduled: none found.
- Docs/catalog: `provider_api_registry.md`, `market_data_inventory.md`, script
  catalog, Phase 5.x governance docs.
- Output: `%LOCALAPPDATA%/EnhengClaw/okx_funding/<BASE>_funding_8h.csv`, or a
  custom `--output-dir`.
- Wrapper risk: CLI compatibility only; no module caller was found.

### `sync_cryptoquant_stablecoin_history.py`

- Caller surface: active cycle imports `run_cryptoquant_stablecoin_sync` from
  `src/enhengclaw/quant_research/onchain_cryptoquant.py`, not this script.
- Config/scheduled: none found.
- Docs/catalog: provider registry, market data inventory, M3.2 plan, script
  catalog, Phase 5.x governance docs.
- Output: `%LOCALAPPDATA%/EnhengClaw/onchain_cryptoquant/stablecoin_supply_daily.csv`,
  `stablecoin_exchange_flows_daily.csv`, `latest_sync_summary.json`, optional
  `--report-path`.
- Wrapper risk: CLI compatibility plus docs/catalog link updates.

### `sync_cryptoquant_reflexivity_history.py`

- Caller surface: active cycle imports `run_cryptoquant_reflexivity_sync` from
  `src/enhengclaw/quant_research/onchain_cryptoquant.py`, not this script.
- Config/scheduled: none found.
- Docs/catalog: provider registry, market data inventory, M3.2 plan, provider
  probe dry-run, script catalog, Phase 5.x governance docs.
- Output: `%LOCALAPPDATA%/EnhengClaw/onchain_cryptoquant/reflexivity_exchange_flows_daily.csv`,
  `reflexivity_market_indicators_daily.csv`, `latest_reflexivity_sync_summary.json`,
  optional `--report-path`.
- Wrapper risk: CLI compatibility plus docs/catalog link updates.

### `sync_tronscan_stablecoin_tron.py`

- Caller surface: no script-level caller found; tests cover the underlying
  `run_m3_2_tron_stablecoin_sync` function in `src`.
- Config/scheduled: none found.
- Docs/catalog: provider registry, market data inventory, M3.2 plan, script
  catalog, Phase 5.x governance docs.
- Output: `%LOCALAPPDATA%/EnhengClaw/onchain_stablecoin_tron/daily_aggregates.csv`,
  `latest_sync_summary.json`, optional `--report-path`.
- Wrapper risk: CLI compatibility plus docs/catalog link updates.

### `generate_versioned_panel.py`

- Caller surface: no non-self Python caller found.
- Config/scheduled: none found.
- Docs/catalog: Phase 2/5 governance docs and script catalog.
- Output: `artifacts/quant_research/features/<as_of>-cross-sectional-daily-1d-h5d-features-<version>/features.csv.gz`.
- Wrapper risk: medium because it is a feature panel materializer, not a pure
  provider-sync helper.

### `run_quant_derivatives_sync_evidence.py`

- Caller surface: no non-self Python caller found.
- Config/scheduled: none found.
- Docs/catalog: `docs/QUANT_RESEARCH_LAB.md`, script catalog, Phase 5.x
  governance docs.
- Output: `<derivatives_external_root>/summaries/by_as_of/<as_of>/sync_summary.json`;
  stdout JSON includes required symbols, selected provider, external root, and
  summary path.
- Wrapper risk: medium because it can write provider-specific derivatives
  summary evidence and `--provider auto` may route through CoinGlass when
  credentials are present.

## Recommended Next Gate

Approve implementation planning only for this four-file subset:

- `sync_okx_funding_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_tronscan_stablecoin_tron.py`

Keep `generate_versioned_panel.py` and `run_quant_derivatives_sync_evidence.py`
as watchlist candidates unless the owner explicitly wants a mixed
provider-sync-plus-data-foundation wrapper batch.

## Required Verification For Any Later Implementation

Minimum commands:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_onchain_cryptoquant.py tests\test_onchain_stablecoin_tron.py -q
git diff --check
```

If `run_quant_derivatives_sync_evidence.py` enters a later implementation batch,
add the narrow derivatives/runtime tests discovered by that implementation
dry-run.

If `generate_versioned_panel.py` enters a later implementation batch, add a
syntax/import smoke command with `--help` and any existing feature/lab tests
that can run without live provider credentials.
