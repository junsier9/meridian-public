# Meridian Proof-Driver / Precheck Window

Current status: `PASSED_NO_REARM`.

This records the operator-approved proof-driver/precheck window after the
post-`entry_second` review. The window was serialized and did not re-arm live
delta, install drop-ins, enable or start services, submit orders, cancel orders,
or update accepted evidence.

## Scope

- Target host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Local fixed driver:
  `scripts/remote_runner_service_fix_window/proof_driver_checks.py`
- Baseline requirement:
  `operator_paused=false`, `live_delta_armed=false`, open orders `0`, and no
  in-flight Meridian service.

## Fresh Baseline

The serialized remote precheck started from the current Meridian timer-owned
state:

- Meridian supervisor timer: active/waiting, enabled
- Meridian health timer: active/waiting, enabled
- Meridian supervisor service: inactive/dead, `Result=success`
- Meridian health service: inactive/dead, `Result=success`
- Legacy supervisor timer: inactive/dead, disabled
- Legacy health timer: inactive/dead, disabled
- Meridian service drop-ins present:
  - `10-meridian-path.conf`
  - `10-meridian-path.conf`
- Live-capable drop-in absent:
  `20-meridian-live-delta-config.conf`

Operator state read through the Meridian config/state store:

- `paused=false`
- `live_delta_armed=false`
- latest live-delta action: `disarm-live-delta`
- state sqlite:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3`

## Fresh Position Monitor

The window ran one fresh read-only position monitor:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T170723535314Z-mainnet-position-monitor/run_summary.json`

Result:

- status: `passed_live_position_monitor`
- read-only: `true`
- blockers: `[]`
- open orders: `0`
- open positions: `11`
- orders submitted: `0`
- operator recommendation: `HOLD_MANUAL_MONITOR`
- reference run:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T161959646526Z-mainnet-delta-execution`

## Current No-Order Supervisor / Health Evidence

Latest supervisor at precheck time:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T170158535608Z-mainnet-live-supervisor/run_summary.json`

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=false`
- `live_delta_armed_at_finish=false`
- `live_delta_authorized=false`
- `orders_submitted=0`
- `fill_count=0`
- cycle status: `cycle_observed_no_order`

Latest health at precheck time:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T170017813150Z-mainnet-health-monitor/run_summary.json`

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- warning alerts: `0`
- `no_order_expected=true`
- `live_delta_armed_after=false`
- `orders_submitted=0`
- `fill_count=0`
- `recent_run_count_observed=1`
- `recent_run_count_required=1`
- `systemd_timer_status.status=ok`
- `systemd_timer_status.timer_name=meridian-alpha-mainnet-supervisor-live.timer`

## Fixed Driver Results

The fixed driver passed against the fresh disarmed/no-order health summary:

```powershell
ssh root@203.0.113.10 "cat /root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T170017813150Z-mainnet-health-monitor/run_summary.json" |
  python scripts\remote_runner_service_fix_window\proof_driver_checks.py --health-summary - --mode prearm-baseline
```

Result:

- status: `passed`
- mode: `prearm-baseline`
- timer name: `meridian-alpha-mainnet-supervisor-live.timer`
- all checks true:
  - `health_passed`
  - `health_zero_critical`
  - `health_no_order_expected_mode`
  - `health_live_delta_disarmed`
  - `health_no_orders_from_monitor`
  - `health_no_fills_from_monitor`
  - `health_timer_status_ok`
  - `health_timer_name_meridian`
  - `health_supervisor_open_orders_zero`

The same fixed driver also passed against the historical live-capable health
summary from the prior arm attempt:

```powershell
ssh root@203.0.113.10 "cat /root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T162417788675Z-mainnet-health-monitor/run_summary.json" |
  python scripts\remote_runner_service_fix_window\proof_driver_checks.py --health-summary - --mode post-arm
```

Result:

- status: `passed`
- mode: `post-arm`
- timer name: `meridian-alpha-mainnet-supervisor-live.timer`
- all checks true, including `health_timer_name_meridian`

## Precheck Verdict

The proof-driver/precheck window is green for its limited purpose:

- fresh baseline is disarmed
- open orders are zero
- 11 existing positions are still recognized
- no Meridian service is in flight
- latest supervisor and health evidence are no-order/healthy
- the fixed proof-driver timer-name check works on both current pre-arm and
  historical post-arm health summary shapes

This is not a re-arm approval by itself. It is only the prerequisite evidence
for deciding whether to open a separate operator-approved re-arm window.

## Follow-Up

The operator subsequently approved and executed the re-arm apply window. That
later window is recorded in `docs/MERIDIAN_REARM_APPLY_WINDOW.md`.
