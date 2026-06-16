# Remote Runner/Service Migration Package Review Summary

Package id: `remote-runner-service-migration-local-freeze-20260531T073901Z`

Generated at: `2026-05-31T07:39:01Z`

Scope: local-only review input for a future remote read-only precheck or remote
apply window. This package was generated without connecting to the remote host
and without changing systemd, runner, secret, trading, or accepted-evidence
state.

## Frozen Inputs

- Hash manifest:
  `PACKAGE_SHA256SUMS.txt`
- Review checklist:
  `CHECKLIST.md`
- Disabled Meridian unit drafts:
  - `systemd/meridian-alpha-mainnet-supervisor-live.service`
  - `systemd/meridian-alpha-mainnet-supervisor-live.timer`
  - `systemd/meridian-alpha-mainnet-health-monitor.service`
  - `systemd/meridian-alpha-mainnet-health-monitor.timer`
  - `systemd/meridian-alpha-mainnet-unattended-daily-policy.service`
  - `systemd/meridian-alpha-mainnet-unattended-daily-policy.timer`
- Meridian runner config draft:
  `config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- Read-only / guarded scripts:
  - `precheck_remote_readonly.sh`: read-only remote state precheck.
  - `verify_disabled_meridian_units.sh`: read-only disabled-unit verifier.
  - `rollback_meridian_units_dry_run.sh`: dry-run by default; execute mode
    requires `--confirm ROLLBACK_MERIDIAN_REMOTE_RUNNER_SERVICE_NAMES`.

## Package Intent

The package only prepares reviewable artifacts for a later, separately approved
remote window. The Meridian unit drafts point at
`/root/meridian_alpha_live_runner`; the current legacy runner root
`/root/enhengclaw_live_runner` remains the rollback and evidence baseline.

The Meridian config draft preserves the current strategy/risk intent, changes
remote runner/service identity surfaces, and adds the unattended daily policy
control gates around the existing supervisor/core-loop path:

- `/root/enhengclaw_live_runner` -> `/root/meridian_alpha_live_runner`
- `enhengclaw-mainnet-supervisor-live.timer` ->
  `meridian-alpha-mainnet-supervisor-live.timer`
- daily policy budget is proof-based: fresh no-order projected turnover
  `* 2.5`, without an operator hard-cap truncation
- daily policy bounds: `2` live cycles, `900s` approval TTL/window, and
  `max_timer_fires=2`
- daily policy timer runs at `00:20 UTC`, not immediately at `00:05 UTC`, so
  the fresh closed rebalance slot has a data-settlement buffer before approval
  generation
- fast-follow owner authorization is bound to the current budget epoch with
  `fast_follow_max_chain_depth=1`, so a reconciled reduce_first may schedule
  only one same-slot entry_second follow-up
- fast-follow runtime owner intent is scoped to `entry_second`,
  `reduce_only=false`, and the frozen target snapshot's allowed symbol/side set
- health monitor timer checks are scoped to a valid unattended approval, open
  epoch, unfinished slot, and active timer window

## Hard Gates

- Abort if any Meridian unit already exists during fresh remote precheck.
- Abort if the legacy supervisor service is currently active during fresh
  remote precheck or cutover preparation.
- Abort if the legacy no-order timer is active alongside the live timer.
- Never run legacy and Meridian live-capable supervisor timers concurrently.
- Do not enable the Meridian unattended daily policy timer without a separate
  long-running unattended approval.
- Do not move, delete, or rewrite `/root/enhengclaw_live_runner`.
- Do not migrate or hand-edit secrets in this naming window.
- Do not update `PROJECT_STATE.md` or accepted evidence from this package.
- Do not treat service renaming as live-trading authorization.

## Expected Validation

Local validation before remote use:

```powershell
python -m unittest tests.test_remote_runner_service_migration_package tests.test_document_contracts tests.test_scheduled_task_contracts -v
git diff --check
wsl bash -n scripts/remote_runner_service_migration/precheck_remote_readonly.sh
wsl bash -n scripts/remote_runner_service_migration/verify_disabled_meridian_units.sh
wsl bash -n scripts/remote_runner_service_migration/rollback_meridian_units_dry_run.sh
```

Latest local validation result for this frozen package:

- `python -m unittest tests.test_remote_runner_service_migration_package tests.test_document_contracts tests.test_scheduled_task_contracts -v`
  passed: `Ran 20 tests ... OK`.
- `wsl bash -n` passed for:
  - `precheck_remote_readonly.sh`
  - `verify_disabled_meridian_units.sh`
  - `rollback_meridian_units_dry_run.sh`
- `test_hash_manifest_matches_package_files_except_itself` passed, proving
  `PACKAGE_SHA256SUMS.txt` matches all package files except the manifest itself.
- `test_disabled_verifier_checks_only_meridian_units_for_legacy_names` passed,
  proving the disabled-unit verifier checks the Meridian files under a unit
  directory without failing merely because legacy units also exist there.

Remote validation, only inside a later approved window:

```bash
bash precheck_remote_readonly.sh
bash verify_disabled_meridian_units.sh --unit-dir /etc/systemd/system --expect-installed
```

## Operator Decision

This package is ready for local review only. The next remote action, if any,
should be a fresh serialized read-only precheck using this package as the fixed
input. Remote install, timer cutover, rollback execute mode, and cleanup each
need explicit operator approval.
