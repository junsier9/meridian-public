# Phase 5.29 Tier B Future-Wrapper Helper Audit

Date: 2026-05-14

Status: read-only audit artifact. This document does not move scripts, rewrite
imports, change catalog rows, change scheduled manifests, or approve an
implementation plan.

Baseline: after `4479c78 Freeze Phase 5.28 Tier A data foundation helpers`.

## Purpose

Phase 5.28 froze the Tier A data-foundation helper roots as `safe-to-move = no`.
Four Tier B helpers remain cataloged as `yes-with-wrapper`:

- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `sync_coinapi_multi_venue_spot.py`

This audit decides whether these four should be treated as four independent
dry-run lanes or frozen permanently at root.

## Non-Movement Guarantee

No script movement is approved by this artifact.

No root wrapper, package import rewrite, catalog count change, README path
policy change, or scheduled/config edit is made by this artifact.

## Evidence Commands

Read-only commands used:

```powershell
git status --short
git log -4 --oneline
Select-String -Path docs\quant_research\00_roadmap_state\quant_research_script_catalog.md -Pattern 'generate_versioned_panel.py|run_quant_derivatives_sync_evidence.py|run_quant_deterministic_daily_sample.py|sync_coinapi_multi_venue_spot.py'
rg -n "generate_versioned_panel|run_quant_derivatives_sync_evidence|run_quant_deterministic_daily_sample|sync_coinapi_multi_venue_spot" scripts src tests config docs -g "*.py" -g "*.ps1" -g "*.json" -g "*.md"
Get-Content scripts\quant_research\generate_versioned_panel.py
Get-Content scripts\quant_research\run_quant_derivatives_sync_evidence.py
Get-Content scripts\quant_research\run_quant_deterministic_daily_sample.py
Get-Content scripts\quant_research\sync_coinapi_multi_venue_spot.py
```

## Decision Summary

Do not move these four as one mixed batch.

Recommended posture:

| helper | decision | next action |
| --- | --- | --- |
| `generate_versioned_panel.py` | split into independent feature-panel dry-run | Phase 5.30 read-only dry-run, no movement. |
| `run_quant_derivatives_sync_evidence.py` | permanent keep-root candidate | Phase 5.30/5.31 catalog-only root-freeze if owner agrees. |
| `run_quant_deterministic_daily_sample.py` | split into independent deterministic-support dry-run | Phase 5.30 read-only dry-run, no movement. |
| `sync_coinapi_multi_venue_spot.py` | permanent keep-root candidate | Phase 5.30/5.31 catalog-only root-freeze if owner agrees. |

Reason: these helpers belong to different semantic families. A shared target
directory would create a generic data-support drawer, which Phase 5 governance
has repeatedly avoided.

## Per-Helper Findings

### `generate_versioned_panel.py`

Classification: feature-panel materializer.

Evidence:

- no non-self Python caller found in the read-only scan;
- writes `artifacts/quant_research/features/<as_of>-cross-sectional-daily-1d-h5d-features-<version>/features.csv.gz`;
- uses lab dataset and feature-set assembly helpers, not a provider sync
  pipeline;
- Phase 5.24 already classified it as a watchlist candidate rather than a
  leaf provider sync helper.

Recommendation:

- keep `yes-with-wrapper` for now;
- do not freeze root yet;
- if advanced, use a standalone feature-panel dry-run;
- possible target family, not yet approved: `feature_panel_tools/`.

Verification needed for any later implementation:

```powershell
python scripts\quant_research\generate_versioned_panel.py --help
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

### `run_quant_derivatives_sync_evidence.py`

Classification: derivatives evidence root surface.

Evidence:

- no non-self Python caller found;
- `docs/QUANT_RESEARCH_LAB.md` presents it as a manual command;
- writes a by-as-of derivatives sync summary through runtime support;
- `--provider auto` can route through Binance or CoinGlass depending on
  available data and credentials;
- semantically sits next to default derivatives sync rather than a generic
  report writer.

Recommendation:

- do not move it under a generic `report_writers/`, `provider_diagnostics/`, or
  `provider_leaf_sync_helpers/` directory;
- prefer permanent root freeze over a wrapper move;
- next safe action is catalog-only: set `safe-to-move = no` with an artifact
  explaining the evidence-surface boundary.

Verification needed for a catalog-only freeze:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

### `run_quant_deterministic_daily_sample.py`

Classification: deterministic research-support CLI.

Evidence:

- root script is a thin CLI around
  `enhengclaw.quant_research.deterministic_survival.run_quant_deterministic_daily_sample`;
- tests and `shadow_proposals.py` import the package function, not the root
  script;
- output is `artifacts/quant_research/cycles/<as_of>/deterministic_daily_sample.json`;
- the command orchestrates universe input, freeze, derivatives evidence, and
  deterministic research-cycle sampling, so it is not a provider sync helper.

Recommendation:

- keep `yes-with-wrapper` for now;
- if advanced, use a standalone deterministic-support dry-run;
- possible target family, not yet approved: `deterministic_support/`;
- root CLI wrapper must remain if moved.

Verification needed for any later implementation:

```powershell
python scripts\quant_research\run_quant_deterministic_daily_sample.py --help
python -m pytest tests\test_quant_deterministic_survival.py tests\test_quant_shadow_proposals.py -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

### `sync_coinapi_multi_venue_spot.py`

Classification: multi-venue CoinAPI cache writer.

Evidence:

- no non-self Python caller found;
- market data inventory uses this root command for Coinbase, OKEX, and
  BYBITSPOT per-venue spot caches;
- provider registry lists it under the active CoinAPI provider surface;
- the parallel 1h roadmap preserves the root command for the 2026-05-07
  venue-concentration fill;
- it writes external provider caches under
  `LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_<EXCHANGE>/spot/...`;
- it imports `scripts.market_data.coinapi_ohlcv.sync_coinapi_ohlcv`, so any
  movement would still be a provider-cache wrapper refactor, not a leaf helper
  move.

Recommendation:

- prefer permanent root freeze over a wrapper move;
- do not put it under `provider_leaf_sync_helpers/`, because it is a
  multi-venue cache writer with roadmap command examples;
- next safe action is catalog-only: set `safe-to-move = no` with an artifact
  explaining the multi-venue cache boundary.

Verification needed for a catalog-only freeze:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Directory Decision

Do not create a single directory for all four Tier B helpers.

If future movement is approved, use separate lanes:

- `feature_panel_tools/` only for feature-panel materializers such as
  `generate_versioned_panel.py`;
- `deterministic_support/` only for deterministic sample/survival support CLIs
  such as `run_quant_deterministic_daily_sample.py`.

Do not create these directories from this audit alone. Each requires its own
read-only dry-run and owner-approved implementation plan.

## Root-Freeze Decision

Two Tier B helpers should be treated as permanent keep-root candidates:

- `run_quant_derivatives_sync_evidence.py`
- `sync_coinapi_multi_venue_spot.py`

The recommended next governance step is a small catalog-only freeze for these
two roots. That would leave only two Tier B `yes-with-wrapper` candidates:

- `generate_versioned_panel.py`
- `run_quant_deterministic_daily_sample.py`

## Stop Condition

No implementation plan should be written from Phase 5.29 alone.

The next action should be one of:

1. catalog-only root-freeze for `run_quant_derivatives_sync_evidence.py` and
   `sync_coinapi_multi_venue_spot.py`;
2. feature-panel dry-run for `generate_versioned_panel.py`;
3. deterministic-support dry-run for `run_quant_deterministic_daily_sample.py`.
