# Meridian Remote Runner/Service Migration Package

This is a local review package for a future remote apply window. It must not be
treated as authorization to change the remote runner, systemd state, Binance
permissions, live/not-live intent, or accepted evidence.

Current observed baseline from the 2026-05-31 read-only audit:

- Reachable remote endpoint: `root@203.0.113.10`.
- Remote host: `enhengclaw-binance-runner-sgp1`.
- Active/enabled legacy timers:
  - `enhengclaw-mainnet-supervisor-live.timer`
  - `enhengclaw-mainnet-health-monitor.timer`
- Disabled legacy fallback timer:
  - `enhengclaw-mainnet-supervisor-noorder.timer`
- Missing Meridian runner root:
  - `/root/meridian_alpha_live_runner`
- Missing Meridian units:
  - `meridian-alpha-mainnet-supervisor-live.service`
  - `meridian-alpha-mainnet-supervisor-live.timer`
  - `meridian-alpha-mainnet-health-monitor.service`
  - `meridian-alpha-mainnet-health-monitor.timer`
  - `meridian-alpha-mainnet-unattended-daily-policy.service`
  - `meridian-alpha-mainnet-unattended-daily-policy.timer`

## Package Contents

- `systemd/meridian-alpha-mainnet-supervisor-live.service`
- `systemd/meridian-alpha-mainnet-supervisor-live.timer`
- `systemd/meridian-alpha-mainnet-health-monitor.service`
- `systemd/meridian-alpha-mainnet-health-monitor.timer`
- `systemd/meridian-alpha-mainnet-unattended-daily-policy.service`
- `systemd/meridian-alpha-mainnet-unattended-daily-policy.timer`
- `config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- `precheck_remote_readonly.sh`
- `verify_disabled_meridian_units.sh`
- `rollback_meridian_units_dry_run.sh`
- `CHECKLIST.md`
- `REVIEW_SUMMARY.md`
- `PACKAGE_SHA256SUMS.txt`

## Hard Boundaries

- Do not run legacy and Meridian live-capable supervisor timers concurrently.
- Do not move or delete `/root/enhengclaw_live_runner`.
- Do not hand-edit secrets.
- Do not update `PROJECT_STATE.md` or accepted evidence from this package.
- Do not treat service renaming as strategy authorization.
- Do not run rollback in execute mode unless the operator explicitly confirms
  the rollback window.

## Intended Review Flow

1. Review the unit drafts and Meridian config draft locally.
2. Review `REVIEW_SUMMARY.md` and `PACKAGE_SHA256SUMS.txt`.
3. Run local static tests from the repo:

```powershell
python -m unittest tests.test_remote_runner_service_migration_package -v
```

4. In a future approved remote window, run the precheck script on the remote
   host before any install:

```bash
bash precheck_remote_readonly.sh
```

5. If and only if precheck passes, stage the runner tree and install the unit
   drafts disabled.
6. Run the disabled-unit verifier on the remote host:

```bash
bash verify_disabled_meridian_units.sh --unit-dir /etc/systemd/system --expect-installed
```

7. Cut over timers only after a separate explicit operator approval.

The unattended daily policy timer is a separate future approval surface. If it is
enabled in a later window, it is intended to run the daily policy service at
`00:20 UTC`, after the UTC rebalance close has had a short data-settlement
buffer; that service creates a fresh no-order proof,
owner-approval record, and small budget epoch, opens the supervisor timer only
inside the approved window, allows one reconciled reduce_first to schedule one
same-slot entry_second fast-follow, then terminal-cleans up after success or
failure.
