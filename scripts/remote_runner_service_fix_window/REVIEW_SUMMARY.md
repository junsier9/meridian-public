# Meridian Service Fix Window Review Summary

## Decision

Use an explicit no-live-delta observation state for future Meridian handoff
acceptance:

- Meridian runner `operator_paused=false`
- Meridian runner `live_delta_armed=false`
- handoff-observation config disables auto-rearm
- handoff-observation config uses proof-only `recent_run_count: 1`
- one timer-created supervisor cycle and one health monitor cycle must both
  complete cleanly
- order, fill, live-delta, and open-order counts must remain zero

`operator_paused=true` is no longer a valid handoff success criterion for the
Meridian proof cycle because the supervisor treats it as a hard blocker.

## Service Fix

The service fix is delivered as systemd service drop-ins instead of replacing
the frozen base unit files. The drop-ins override only `ExecStart` and force the
runtime command to resolve through the Meridian runner tree:

- `/root/meridian_alpha_live_runner/repo/src` is first on `PYTHONPATH`
- scripts are invoked by absolute Meridian paths
- config is invoked by an absolute Meridian path
- the effective service command avoids `/root/enhengclaw_live_runner`

## Why A Handoff-Observation Config Exists

The original Meridian config draft was live-capable and left
`auto_rearm_live_delta: true`. That is too broad for the next proof because the
operator explicitly wants no live delta during handoff validation.

The handoff-observation config keeps the existing strategy/capital/account
surfaces but makes the proof boundary explicit:

- supervisor refuses live delta even if state is accidentally armed
- health monitor expects no-order behavior
- health monitor evaluates only the latest proof supervisor run, so superseded
  blocked Meridian runs from earlier migration attempts do not contaminate the
  proof window
- health monitor does not auto-rearm live delta

The default live timer configurations still use a 3-run health window. This
package narrows only the Meridian handoff-observation proof config.

## Review Verdict

This package is suitable as a fixed input for a future remote fix apply window,
provided the operator approves that window separately. It is not suitable as a
timer cutover package by itself.

## Post-Entry-Second Review Addendum

The 2026-05-31 live-delta authorization attempt reached one timer-created
`entry_second` supervisor run with 4 submitted orders and 4 fills, then rolled
back because the proof driver checked the wrong health-summary timer field.
The health monitor summary shape is `systemd_timer_status.timer_name`, not
top-level `systemd_timer_name`.

The local package now includes `proof_driver_checks.py` so future
authorization proof drivers can validate:

- health status passed
- zero critical alerts
- live-capable health mode when post-arm
- live delta still armed during post-arm health verification
- health monitor itself submitted zero orders and zero fills
- nested systemd timer status is `ok`
- nested timer name is `meridian-alpha-mainnet-supervisor-live.timer`
- supervisor runs observed by health have zero open orders

This addendum still does not approve a re-arm. Re-arm requires a separate
operator-approved window after a fresh serialized precheck.

The helper also supports a `prearm-baseline` mode for the disarmed/no-order
state immediately before any future authorization attempt.

Required next gate before any future cutover design resumes:

1. Apply the drop-ins and config with timers still disabled.
2. Prove Python imports and config resolution come from the Meridian runner.
3. Prove no default path or accepted evidence was updated.
4. Only then open a new cutover precheck/design window.
