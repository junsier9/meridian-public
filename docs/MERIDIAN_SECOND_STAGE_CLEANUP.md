# Meridian Second Stage Cleanup

Status: `SECOND_STAGE_COMPATIBILITY_CLEANUP_APPLIED`.

Cleanup date: `2026-06-05` Asia/Singapore.

This cleanup follows the compatibility-first Meridian rename closure. It does
not retire the legacy `EnhengClaw` runtime identity, Python package, environment
prefixes, external evidence roots, or rollback references.

## Actions

- Removed the ignored local build artifact directory:
  `src/enhengclaw.egg-info`.
- Removed stale tracked legacy systemd unit templates from:
  `docs/live_trading/hv_balanced_binance_usdm_pipeline/systemd/`.

The removed systemd templates were the old `enhengclaw-mainnet-*` unit files.
They are superseded by the Meridian remote-runner package under
`scripts/remote_runner_service_migration/systemd/` and the later Meridian
drop-in package under `scripts/remote_runner_service_fix_window/`.

## Retained Compatibility Surfaces

The following old-name surfaces remain intentional:

- `src/enhengclaw/` remains the supported Python runtime package.
- `src/meridian_alpha/` remains the alias package for the canonical Meridian
  identity.
- `ENHENGCLAW_*` remains a supported legacy environment prefix alongside
  `MERIDIAN_ALPHA_*`.
- Historical docs may still mention `EnhengClaw`, `enhengclaw-mainnet-*`, or
  old external paths when recording past evidence or rollback routes.

## Expected Post-Cleanup Shape

Existing tracked file paths containing the old package name should now be
limited to the supported compatibility package tree:

```powershell
git ls-files | Where-Object { Test-Path $_ } | rg -i "(^|/)enhengclaw($|/)|enhengclaw-"
```

Expected result category:

- `src/enhengclaw/...`

Any new tracked old-name path outside that compatibility package should be
treated as a review item unless it is explicitly added as historical evidence or
rollback documentation.
