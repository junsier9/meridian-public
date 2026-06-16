# Meridian Service Fix Window Checklist

This checklist is for the path/config-resolution fix window only. It must not
be used as a timer cutover checklist.

## Pre-Apply Review

- [ ] Confirm target host is still `root@203.0.113.10`.
- [ ] Confirm rollback baseline is still timers zero, services inactive/dead,
      live delta disarmed, and open orders zero.
- [ ] Confirm the previous failure was the Meridian health monitor resolving
      runtime code through `/root/enhengclaw_live_runner/repo/src`.
- [ ] Confirm the fix package uses absolute Meridian script paths.
- [ ] Confirm the fix package uses an absolute Meridian config path.
- [ ] Confirm the child Python process receives
      `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src`.
- [ ] Confirm no service command references `/root/enhengclaw_live_runner`.
- [ ] Confirm no timer will be enabled or started in this fix window.
- [ ] Confirm `PROJECT_STATE.md` and accepted evidence paths will not be
      updated.

## Read-Only Path Probe

- [ ] `precheck_meridian_path_resolution_readonly.sh` runs without changing
      systemd state.
- [ ] The probe reports `config_module_file` under
      `/root/meridian_alpha_live_runner/repo/src`.
- [ ] The probe reports `config_root` as `/root/meridian_alpha_live_runner/repo`.
- [ ] The probe reports the resolved config path under
      `/root/meridian_alpha_live_runner/repo/config/live_trading`.
- [ ] The probe does not print secrets.

## Disabled Fix Apply Gates

- [ ] Install the handoff-observation config under the Meridian repo config
      directory.
- [ ] Install only these drop-ins:
      `meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf`
      and
      `meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf`.
- [ ] Run `systemctl daemon-reload`.
- [ ] Do not run `systemctl enable`, `systemctl start`, or timer cutover.
- [ ] Run `verify_meridian_path_dropins.sh --dropin-root /etc/systemd/system
      --expect-installed`.
- [ ] Confirm Meridian timers remain inactive/disabled.
- [ ] Confirm legacy timers remain inactive/disabled.
- [ ] Confirm all related services are inactive/dead.

## Acceptance Semantics

- [ ] Meridian handoff proof will use `operator_paused=false`.
- [ ] Meridian handoff proof will use `live_delta_armed=false`.
- [ ] The latest Meridian live-delta action is `disarm-live-delta`.
- [ ] The handoff-observation config has `auto_rearm_live_delta: false`.
- [ ] The handoff-observation config has `no_order_expected: true`.
- [ ] The handoff-observation config has proof-only `recent_run_count: 1`.
- [ ] The default live timer configs keep their 3-run health window unless a
      separate live-health policy window changes them.
- [ ] The proof must fail if any order/fill/open-order signal appears.
- [ ] The proof must fail if live delta becomes armed.
- [ ] Post-arm health proof-driver checks read
      `systemd_timer_status.timer_name`, not top-level `systemd_timer_name`.
- [ ] Fresh pre-arm baseline proof-driver checks use `prearm-baseline` mode and
      require `live_delta_armed_after=false`.
- [ ] Proof-driver integer checks preserve `0` as a valid value for
      `open_order_count`, `orders_submitted`, and `fill_count`.

## Rollback

- [ ] Capture `systemctl cat` and `systemctl show` for both Meridian services.
- [ ] Capture the verifier output and any Python path probe output.
- [ ] Remove only the two Meridian path drop-ins if rollback is needed.
- [ ] Keep the Meridian runner tree and proof artifacts for forensic review.
- [ ] Run `systemctl daemon-reload`.
- [ ] Run `systemctl reset-failed` if a service is failed.
- [ ] Confirm all legacy and Meridian timers are inactive/disabled.
- [ ] Confirm open orders remain zero.
