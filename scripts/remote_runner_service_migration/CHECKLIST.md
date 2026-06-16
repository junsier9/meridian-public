# Remote Runner/Service Migration Review Checklist

This checklist is for review only until the operator explicitly opens a remote
apply window.

## Pre-Apply Review

- [ ] Confirm the target is still `root@203.0.113.10`.
- [ ] Confirm `root@203.0.113.11` behavior is understood before relying on
      the reserved endpoint.
- [ ] Confirm the current remote live timer config is still
      `hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml`.
- [ ] Confirm the Meridian config draft keeps the live strategy unchanged while
      adding only the unattended daily policy gates around the existing
      supervisor/core-loop path.
- [ ] Confirm the unattended daily policy budget is proof-based: fresh
      no-order projected turnover `* 2.5`, without an operator hard-cap
      truncation.
- [ ] Confirm the unattended daily policy bounds are explicit: `2` live cycles,
      `900s` approval TTL/window, and `max_timer_fires=2`.
- [ ] Confirm the unattended daily policy timer fires at `00:20 UTC`, leaving a
      data-settlement buffer after the UTC rebalance close before fresh approval
      generation.
- [ ] Confirm fast-follow is authorized only for the same fresh slot under the
      current budget epoch, with `fast_follow_max_chain_depth=1`.
- [ ] Confirm fast-follow owner intent allows only `entry_second`,
      `reduce_only=false`, and the frozen target snapshot's allowed
      symbol/side set.
- [ ] Confirm no strategy authorization, Binance permission, capital, or risk
      setting is changed by this package.
- [ ] Confirm the secret-handling decision is explicit. Default for this window:
      do not migrate secrets.
- [ ] Confirm rollback evidence capture location before any remote apply.

## Fresh Remote Precheck Gates

- [ ] `precheck_remote_readonly.sh` exits `0`.
- [ ] Legacy supervisor and health timers are active/waiting.
- [ ] Legacy supervisor and health services are not currently active.
- [ ] Meridian units are absent before install.
- [ ] `/root/enhengclaw_live_runner` exists.
- [ ] `/root/meridian_alpha_live_runner` is absent before apply.
- [ ] Latest legacy supervisor and health artifacts are fresh enough for the
      operator's migration window.

Abort if any fresh precheck gate fails.

## Disabled Install Gates

- [ ] `/root/meridian_alpha_live_runner` is staged without moving legacy files.
- [ ] The Meridian config draft is staged under the Meridian repo tree.
- [ ] The six Meridian unit files are installed but not enabled.
- [ ] `systemctl daemon-reload` has completed.
- [ ] `systemd-analyze verify` passes for the four Meridian unit files.
- [ ] `verify_disabled_meridian_units.sh --expect-installed` exits `0`.
- [ ] Legacy timers are still the only active timers.

Abort if any disabled install gate fails.

## Cutover Gates

- [ ] Operator explicitly approves cutover.
- [ ] Legacy supervisor service is not active at the cutover instant.
- [ ] Legacy and Meridian live-capable supervisor timers will not overlap.
- [ ] Meridian health timer uses active-unattended-epoch scoped timer checks.
- [ ] Meridian unattended daily policy timer is enabled only after a separate
      explicit long-running unattended approval.
- [ ] Meridian supervisor timer is controlled by the daily policy service, not
      enabled as an always-on order loop.
- [ ] If reduce_first succeeds and reconciles, the same-slot fast-follow may run
      one entry_second follow-up; otherwise the daily policy must cleanup/hold.
- [ ] One Meridian supervisor cycle writes fresh artifacts.
- [ ] One Meridian health-monitor cycle writes fresh artifacts.
- [ ] Health monitor references
      `meridian-alpha-mainnet-supervisor-live.timer`.
- [ ] Legacy supervisor and health timers are inactive/disabled after cutover.

## Rollback Checklist

Rollback immediately if:

- [ ] Meridian unit verification fails.
- [ ] Meridian runner cannot load its environment without ad hoc secret edits.
- [ ] Meridian proof artifacts are missing or malformed.
- [ ] Post-cutover supervisor or health-monitor cycle fails.
- [ ] Both legacy and Meridian live-capable supervisor timers become active.
- [ ] Any unexpected order/fill/open-order signal appears during verification.

Rollback actions:

- [ ] Capture `systemctl status` and `journalctl -u ... -n 80` for Meridian
      units.
- [ ] Stop and disable Meridian supervisor and health timers.
- [ ] Stop and disable Meridian unattended daily policy timer.
- [ ] Restore legacy unit files from captured rollback copies if modified.
- [ ] Run `systemctl daemon-reload`.
- [ ] Enable/start legacy health timer.
- [ ] Enable/start legacy supervisor timer.
- [ ] Confirm legacy timers are active/waiting.
- [ ] Confirm Meridian timers are inactive/disabled.
- [ ] Keep `/root/meridian_alpha_live_runner` for forensic inspection until
      cleanup is explicitly approved.

