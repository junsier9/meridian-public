# Meridian Remote Runner/Service Fix Window

This local package fixes the two blockers found by the rolled-back Meridian
timer handoff attempt. It is an input for a future remote fix apply window only.
It does not authorize timer cutover, live delta, Binance order activity, secret
migration, or accepted-evidence updates.

## Scope

- Target host: `root@203.0.113.10`
- Legacy runner root: `/root/enhengclaw_live_runner`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Failed handoff proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover`
- Rollback result:
  `rollback_summary_after_reset_failed.json` reported timers zero, services
  inactive/dead, and open orders zero.

## Root Cause

The prior Meridian service drafts used the Meridian working directory but still
left Python path and config resolution partly implicit:

- service `ExecStart` used relative script paths
- service `ExecStart` used relative `--config` paths
- the Meridian venv was symlinked to the legacy venv
- runtime imports resolved `enhengclaw.live_trading.config` from
  `/root/enhengclaw_live_runner/repo/src`
- the health monitor then resolved the Meridian config name under the legacy
  repo root and failed with `FileNotFoundError`

The fix is to install disabled service drop-ins that make path resolution
explicit for the child Python process after `with-live-env` loads the live
environment.

## Package Contents

- `systemd-dropins/meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf`
- `systemd-dropins/meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf`
- `config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`
- `precheck_meridian_path_resolution_readonly.sh`
- `verify_meridian_path_dropins.sh`
- `rollback_meridian_path_dropins_dry_run.sh`
- `proof_driver_checks.py`
- `CHECKLIST.md`
- `REVIEW_SUMMARY.md`
- `PACKAGE_SHA256SUMS.txt`

## Fix Strategy

The service drop-ins:

- clear the original relative `ExecStart`
- invoke scripts by absolute Meridian repo paths
- pass an absolute Meridian handoff-observation config path
- force `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src`
- set `VIRTUAL_ENV` and `PATH` to the Meridian runner venv
- avoid `/root/enhengclaw_live_runner` in the effective Meridian service
  command

The handoff-observation config keeps strategy, capital, and account surfaces
aligned with the previous Meridian draft, but changes the handoff acceptance
mode to no-live-delta observation:

- `mainnet_live_supervisor.allow_live_delta_when_armed: false`
- `mainnet_live_supervisor.allow_multiphase_live_delta: false`
- `mainnet_health_monitor.no_order_expected: true`
- `mainnet_health_monitor.recent_run_count: 1`
- `mainnet_health_monitor.auto_rearm_live_delta: false`

This means a future proof cycle can run unpaused and complete the no-order core
loop, while still failing closed if live delta is armed or any order/fill path
appears.

The `recent_run_count: 1` setting is deliberate and proof-only. The handoff
window verifies one timer-created supervisor cycle plus one health-monitor
cycle. Using the default 3-run health window during a migration proof can make
the health monitor count superseded blocked Meridian proof runs from before the
path, observation-state, and position-reference fixes. The default live timer
configs keep their 3-run health window.

## Post-Entry-Second Proof-Driver Fix

The operator-approved live-delta attempt reached `entry_second` once and
recorded 4 fills, then rolled back because the local proof driver looked for a
nonexistent top-level `systemd_timer_name` in the health summary.

The health monitor writes timer evidence under
`systemd_timer_status.timer_name`. `proof_driver_checks.py` is the local helper
for future proof drivers and validates the post-arm health summary against that
field shape while preserving zero-valued count fields. It also supports a
`prearm-baseline` mode for fresh disarmed/no-order prechecks.

## Acceptance Decision

Future Meridian handoff verification should no longer require
`operator_paused=true` on the Meridian runner during the proof cycle. That state
prevents the supervisor cycle from completing and makes the health monitor fail.

The required Meridian proof state is:

- `operator_paused=false`
- `live_delta_armed=false`
- latest live-delta action is `disarm-live-delta`
- auto-rearm is disabled for the handoff-observation config
- supervisor status is `mainnet_live_supervisor_completed`
- health status is `mainnet_health_monitor_passed`
- health monitor observes exactly the latest proof supervisor run
- `orders_submitted=0`
- `fill_count=0`
- open orders remain zero before and after the cycle
- legacy timers remain inactive/disabled
- no accepted evidence or formal readiness claim is updated

The legacy runner may remain paused/disarmed as the rollback baseline. The
unpaused requirement applies only to the Meridian runner proof cycle.

## Non-Goals

- Do not enable or start Meridian timers in this fix window.
- Do not re-enable legacy timers.
- Do not arm live delta.
- Do not submit, cancel, or test orders.
- Do not change strategy, capital, Binance permissions, or secrets.
- Do not update `PROJECT_STATE.md` accepted evidence.
- Do not treat this package as handoff approval.

## Intended Review Flow

1. Review the path drop-ins and no-live-delta observation config.
2. Run local static tests:

```powershell
python -m unittest tests.test_remote_runner_service_fix_window -v
```

3. In a future approved remote fix window, run the read-only precheck first:

```bash
bash precheck_meridian_path_resolution_readonly.sh
```

4. Install only the drop-ins and handoff-observation config, with timers still
   disabled.
5. Run the disabled/read-only verifier:

```bash
bash verify_meridian_path_dropins.sh --dropin-root /etc/systemd/system --expect-installed
```

6. Stop. Do not attempt cutover until the path-resolution proof and the
   no-live-delta observation semantics are separately accepted.
