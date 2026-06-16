# Meridian Re-Arm Apply Window

Current status: `PASSED_REARM_LEFT_ARMED`.

Current remote-state addendum:
`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`.

That addendum is the current point-in-time remote state as of
`2026-06-01T13:39:52.963565Z`. It records that the Meridian runner remained
live-capable and armed after the health monitor auto-rearmed live delta at
`2026-06-01T06:53:05.653450Z`, and that a later timer-created delta execution
submitted and filled one `entry_second` order. This document remains the
historical record of the operator-approved 2026-05-31 re-arm apply window.

This records the operator-approved Meridian live-delta re-arm apply window. The
window did re-arm live delta and left the Meridian runner armed. It did not
manually start supervisor or health services; execution evidence came from the
existing systemd timers.

## Scope

- Target host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_live_delta_rearm/20260531T171735Z-operator-approved-rearm`
- Live-capable config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- Handoff-observation config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`

## Fresh Precheck

The apply driver first ran a fresh serialized precheck and wrote:

`rearm_precheck.json`

Precheck result:

- status: `passed`
- `operator_paused=false`
- `live_delta_armed=false`
- latest live-delta action: `disarm-live-delta`
- fresh position monitor passed
- open orders: `0`
- open positions: `11`
- no Meridian service in flight
- Meridian timers active/enabled
- legacy timers inactive/disabled
- no `20-meridian-live-delta-config.conf` drop-in present before apply
- latest health passed with critical alerts `0`

## Apply

The apply step wrote reversible live-capable drop-ins:

- `/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.service.d/20-meridian-live-delta-config.conf`
- `/etc/systemd/system/meridian-alpha-mainnet-health-monitor.service.d/20-meridian-live-delta-config.conf`

It then ran `systemctl daemon-reload` and recorded:

- action: `arm-live-delta`
- run id: `20260531T171738942510Z-plan_only`
- status: `operator_live_delta_armed`
- operator state after arm: `live_delta_armed=true`, `paused=false`

The initial apply summary reported `effective_config_live_capable=false`, but
that was a driver check-shape false negative: it inspected `systemctl cat`,
which includes both the older 10 drop-in and the newer 20 drop-in. The final
verification wrote `rearm_effective_execstart_correction.json`; `systemctl show
-p ExecStart` confirmed both effective service commands used the live-capable
Meridian remote-runner config.

## Timer-Created Execution

The first arm-after supervisor cycle was timer-created:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T172246574478Z-mainnet-live-supervisor/run_summary.json`

Result:

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=true`
- `live_delta_armed_at_finish=true`
- `live_delta_authorized=true`
- `orders_submitted=2`
- `fill_count=2`

The associated delta execution was:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T172309876791Z-mainnet-delta-execution/run_summary.json`

Result:

- status: `mainnet_delta_orders_submitted`
- execution stage: `entry_second`
- planned delta orders: `2`
- submitted orders: `2`
- fills: `2`
- reconciliation status: `reconciled`
- blockers: `[]`

Filled rows:

| symbol | side | quantity | average price | notional USDT |
| --- | --- | ---: | ---: | ---: |
| AAVEUSDT | SELL | 0.1 | 81.21 | 8.121 |
| BNBUSDT | BUY | 0.01 | 713.18 | 7.1318 |

## Post-Execution Position Monitor

Read-only position monitor after the 2 fills:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T172412306280Z-mainnet-position-monitor/run_summary.json`

Result:

- status: `passed_live_position_monitor`
- read-only: `true`
- blockers: `[]`
- open orders: `0`
- open positions: `11`
- orders submitted: `0`
- reference run:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T172309876791Z-mainnet-delta-execution`

## Post-Arm Health

Timer-created health after the 2-fill supervisor:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T173207780606Z-mainnet-health-monitor/run_summary.json`

Result:

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- warning alerts: `0`
- `no_order_expected=false`
- `live_delta_armed_after=true`
- health monitor `orders_submitted=0`
- health monitor `fill_count=0`
- `recent_run_count_observed=3`
- `systemd_timer_status.status=ok`
- `systemd_timer_status.timer_name=meridian-alpha-mainnet-supervisor-live.timer`

The fixed local driver passed against this health summary:

```powershell
ssh root@203.0.113.10 "cat /root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T173207780606Z-mainnet-health-monitor/run_summary.json" |
  python scripts\remote_runner_service_fix_window\proof_driver_checks.py --health-summary - --mode post-arm
```

## Latest State Captured

Final remote verification wrote:

`rearm_final_verification.json`

Status:

- `passed_rearm_left_armed`

Latest captured supervisor after the post-arm health tick:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T173255390604Z-mainnet-live-supervisor/run_summary.json`

Result:

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=true`
- `live_delta_armed_at_finish=true`
- `live_delta_authorized=false`
- `orders_submitted=0`
- `fill_count=0`

Latest captured position monitor:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T173255521764Z-mainnet-position-monitor/run_summary.json`

Result:

- status: `passed_live_position_monitor`
- read-only: `true`
- open orders: `0`
- open positions: `11`
- reference run:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T172309876791Z-mainnet-delta-execution`

Services at final capture:

- Meridian supervisor service: inactive/dead, `Result=success`
- Meridian health service: inactive/dead, `Result=success`

## Current Boundary

This window intentionally left live delta armed. Future timer-created
supervisor cycles may continue to evaluate and execute live-capable deltas until
an operator or health monitor records `disarm-live-delta` or removes the
live-capable 20 drop-ins.

This window does not update `PROJECT_STATE.md` accepted evidence and does not
change the checked-in Stage 1 project state.
