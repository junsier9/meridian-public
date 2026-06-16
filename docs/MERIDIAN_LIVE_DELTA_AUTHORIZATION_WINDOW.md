# Meridian Live-Delta Authorization Window

Current status: `EXECUTED_THEN_FAIL_CLOSED_DISARMED`.

Historical status note:
`EXECUTED_THEN_FAIL_CLOSED_DISARMED` is the final state of this 2026-05-31
authorization window. It is not the current remote state. The current
point-in-time remote-state addendum is
`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`, which records the later
live-capable armed state after health-monitor auto-rearm.

This records the operator-approved `live_delta` authorization attempt after
the Meridian timer handoff. It is not a formal Stage 4 readiness update and it
does not update accepted evidence or `PROJECT_STATE.md`.

## Scope

- Target host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Operator approval phrase in chat: `鎺堟潈live delta`
- Live-capable config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- Handoff-observation config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`

## First Attempt

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_live_delta_authorization/20260531T161114Z-operator-approved-live-delta-arm`

Result:

- `status=no_go_precheck_failed`
- false checks: `["open_orders_zero"]`
- no live-delta arm was attempted
- no drop-in was installed
- no order path was reached

Interpretation:

- The position monitor itself passed with `open_order_count=0`,
  `open_position_count=11`, and blockers `[]`.
- The no-go was a proof-driver zero-preservation bug: the driver evaluated
  `open_order_count=0` through a falsey fallback.

## Rerun Apply

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_live_delta_authorization/20260531T161353Z-operator-approved-live-delta-arm-rerun`

Precheck:

- `live_delta_authorization_precheck.json`
- `status=passed`
- false checks: `[]`
- Meridian timers active/enabled
- legacy supervisor/health timers disabled/inactive
- no in-flight Meridian service
- Meridian `operator_paused=false`
- Meridian `live_delta_armed=false`
- local state health OK
- position monitor passed with `open_order_count=0` and
  `open_position_count=11`

Apply actions:

- Installed reversible `20-meridian-live-delta-config.conf` drop-ins for the
  Meridian supervisor and health services.
- The drop-ins pointed both services to the live-capable Meridian remote-runner
  config.
- Ran `systemctl daemon-reload`.
- Recorded `arm-live-delta` through the normal operator action path.
- Did not manually start any service; the proof waited for timer-created
  cycles.

Arm evidence:

- `arm_operator_action.parsed.json`
- status: `operator_live_delta_armed`
- `live_delta_armed=true`
- arm action id:
  `20260531T161357500217Z:arm-live-delta:20260531T161357500217Z-plan_only`

Timer-created supervisor cycle:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T161938384510Z-mainnet-live-supervisor`

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=true`
- `live_delta_armed_at_finish=true`
- `live_delta_authorized=true`
- execution stage: `entry_second`
- `orders_submitted=4`
- `fill_count=4`
- fast-follow schedule: `skipped`, because the latest cycle was already
  `entry_second` rather than a `reduce_first` source

Timer-created health cycle:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T162417788675Z-mainnet-health-monitor`

- status: `mainnet_health_monitor_passed`
- `critical_alert_count=0`
- `no_order_expected=false`
- `live_delta_armed_after=true`
- `orders_submitted=0`
- `fill_count=0`

Rollback trigger:

- The health monitor passed, but the local proof-driver check
  `health_timer_name_meridian` failed because it expected a top-level
  `systemd_timer_name` field in the health summary.
- This was a proof-driver check-shape mismatch, not a health-monitor alert.

Fail-closed rollback:

- Recorded `disarm-live-delta` at
  `2026-05-31T16:24:23.459414Z`.
- Removed the reversible `20-meridian-live-delta-config.conf` drop-ins.
- Ran `systemctl daemon-reload`.
- Effective supervisor and health services returned to the
  handoff-observation config.
- Final position monitor passed:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T164219540237Z-mainnet-position-monitor`
  - `open_order_count=0`
  - `open_position_count=11`
  - blockers: `[]`
  - selected reference:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T161959646526Z-mainnet-delta-execution`

## Post-Rollback Stabilization

The first health tick after rollback ran before the next no-order supervisor
cycle and evaluated the just-completed live-delta supervisor under the restored
handoff-observation config:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T162930044447Z-mainnet-health-monitor`

- status: `mainnet_health_monitor_alerted`
- `critical_alert_count=3`
- `no_order_expected=true`
- `live_delta_armed_after=false`
- the health monitor recorded another `disarm-live-delta`

The next supervisor and health ticks stabilized:

- Supervisor:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T164055778965Z-mainnet-live-supervisor`
  - status: `mainnet_live_supervisor_completed`
  - blockers: `[]`
  - `live_delta_armed_at_start=false`
  - `live_delta_armed_at_finish=false`
  - `orders_submitted=0`
  - `fill_count=0`
- Health:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T163947808221Z-mainnet-health-monitor`
  - status: `mainnet_health_monitor_passed`
  - `critical_alert_count=0`
  - `live_delta_armed_after=false`

## Final State

- Meridian timer ownership remains active.
- Meridian supervisor and health timers remain enabled/active.
- Effective supervisor and health services use the handoff-observation config.
- `live_delta_armed=false`.
- `operator_paused=false`.
- Health service state recovered to inactive/success.
- Open orders are zero.
- The position monitor recognizes 11 open positions using the latest
  Meridian-root mainnet delta execution reference.
- Accepted evidence and `PROJECT_STATE.md` were not updated.

## Boundary

This window did execute live delta once: 4 `entry_second` orders were submitted
and 4 fills were recorded. It did not leave live delta durably armed.

Do not re-arm live delta from this state without a separate post-entry-second
review window. That window should inspect the `20260531T161938384510Z`
supervisor artifact, the `20260531T161959646526Z` delta execution artifact,
current position drift, health summary shape, and whether the proof-driver
`health_timer_name_meridian` check should read the timer name from the correct
health summary field before any further authorization.
