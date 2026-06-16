# Tardis Deribit Options Historical Store

`Status: prepared`
`Date: 2026-06-13`
`Provider: Tardis.dev`
`Dataset: deribit/options_chain`
`Default root: E:\EnhengClawData\market_history\tardis_deribit_options_chain`

## Purpose

This store is the long-lived research cache for raw Tardis Deribit
`options_chain` daily gzip files. It is separate from the Phase 0 probe and
Phase 1 feature builder:

- probe reports verify access and schema without retaining raw vendor rows;
- builder reports stream bounded samples into feature panels without retaining
  raw vendor rows;
- this store is for deliberate raw vendor retention on the external E drive.

## Boundary

Raw vendor retention is not a validation side effect. The sync script defaults
to dry-run and requires an explicit confirmation string before downloading.

Forbidden:

- do not store raw Tardis partitions under the git checkout;
- do not commit raw Tardis partitions;
- do not print or persist the Tardis API key;
- do not treat a populated store as h10d manifest admission;
- do not mutate active h10d manifests from a data-store sync.

## Store Location

Preferred workstation root:

```powershell
E:\EnhengClawData\market_history\tardis_deribit_options_chain
```

Fallback root if E drive is absent:

```powershell
$env:LOCALAPPDATA\EnhengClaw\market_history\tardis_deribit_options_chain
```

## Directory Layout

```text
tardis_deribit_options_chain/
  raw/
    deribit/
      options_chain/
        YYYY/
          MM/
            DD/
              OPTIONS.csv.gz
  manifests/
    deribit_options_chain_manifest.json
  duckdb/
    create_tardis_deribit_options_chain_view.sql      # future
```

The raw partition path is:

```text
raw/deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz
```

## Script

The store helper is:

```powershell
python .\scripts\quant_research\provider_leaf_sync_helpers\sync_tardis_deribit_options_chain_history.py
```

Dry-run plan for a short window:

```powershell
python .\scripts\quant_research\provider_leaf_sync_helpers\sync_tardis_deribit_options_chain_history.py `
  --as-of 2026-06-13 `
  --from-date 2026-04-01 `
  --to-date 2026-04-03
```

Execute a retained raw-data sync:

```powershell
python .\scripts\quant_research\provider_leaf_sync_helpers\sync_tardis_deribit_options_chain_history.py `
  --as-of 2026-06-13 `
  --from-date 2024-01-01 `
  --to-date 2026-06-12 `
  --execute `
  --confirm-retain-raw-vendor-data I_UNDERSTAND_RAW_TARDIS_OPTIONS_CHAIN_WILL_BE_RETAINED
```

The script writes a sanitized summary to:

```text
artifacts/quant_research/factor_reports/<as-of>/tardis_deribit_options_chain_history_store_summary.json
```

In execute mode, it also writes:

```text
E:\EnhengClawData\market_history\tardis_deribit_options_chain\manifests\deribit_options_chain_manifest.json
```

## Intended Research Flow

1. Run the Phase 0 Tardis probe until it is green.
2. Run this store helper in dry-run mode over the intended research window.
3. Execute the raw sync only after explicitly accepting raw vendor retention.
4. Build a longer M3.1 options-surface panel from the retained partitions.
5. Re-run the options overlay context report card.
6. Run the preregistered h10d overlay ablation.

## Current Non-Goal

This store does not yet define a DuckDB view or a full feature-builder
integration path from raw partitions. Those are follow-up tasks after the raw
retention boundary is accepted.
