# Meridian Post-Entry-Second Review / Proof-Driver Fix Window

Current status: `REVIEWED_NO_REARM`.

This window reviewed the 4 fills created by the operator-approved Meridian
`entry_second` live-delta attempt and fixed the local proof-driver field
contract. It did not re-arm live delta, enable or start timers, submit orders,
cancel orders, or update accepted evidence.

## Scope

- Target host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Review target supervisor:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T161938384510Z-mainnet-live-supervisor`
- Review target delta execution:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T161959646526Z-mainnet-delta-execution`
- Live-capable health summary:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T162417788675Z-mainnet-health-monitor`

## Delta Execution Review

The selected delta execution summary is internally consistent:

- status: `mainnet_delta_orders_submitted`
- execution stage: `entry_second`
- stage gate: `passed`
- blockers: `[]`
- planned delta orders: `4`
- submitted orders: `4`
- fills: `4`
- reconciliation status: `reconciled`

The 4 filled rows were all `entry_second` / `increase_same_side` non-reduce
orders:

| symbol | side | filled quantity | average price | notional USDT |
| --- | --- | ---: | ---: | ---: |
| APTUSDT | SELL | 8.3 | 0.9214 | 7.64762 |
| ARBUSDT | SELL | 98.9 | 0.1007 | 9.95923 |
| FILUSDT | SELL | 12.0 | 0.932 | 11.184 |
| UNIUSDT | SELL | 5.0 | 2.981 | 14.905 |

The preflight, daily realized PnL gate, local state health, account setting
preparation, and reconciliation artifacts all had empty blockers.

## Position Drift Review

The before/after account probe and reconciliation artifacts agree on the
position surface:

- before open orders: `0`
- after open orders: `0`
- before open positions: `11`
- after open positions: `11`
- expected positions in reconciliation: `11`
- redacted open positions in reconciliation: `11`
- reconciliation blockers: `[]`

The latest observed position monitor after the rollback/stabilization sequence
was:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T165128676087Z-mainnet-position-monitor`

- status: `passed_live_position_monitor`
- read-only: `true`
- blockers: `[]`
- open orders: `0`
- open positions: `11`
- orders submitted: `0`
- operator recommendation: `HOLD_MANUAL_MONITOR`

## Health Summary Field Shape

The proof-driver failure was confirmed as a local check-shape bug. The health
monitor writes the timer name under:

`systemd_timer_status.timer_name`

It does not write either:

- top-level `systemd_timer_name`
- `systemd_timer_status.systemd_timer_name`

The reviewed live-capable health summary had:

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- warning alerts: `0`
- `no_order_expected=false`
- `live_delta_armed_after=true`
- `orders_submitted=0`
- `fill_count=0`
- `systemd_timer_status.status=ok`
- `systemd_timer_status.timer_name=meridian-alpha-mainnet-supervisor-live.timer`

The latest no-live-delta health summary after stabilization had:

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- `no_order_expected=true`
- `live_delta_armed_after=false`
- `auto_rearm_gate.status=skipped_disabled`
- `systemd_timer_status.timer_name=meridian-alpha-mainnet-supervisor-live.timer`

## Proof-Driver Fix

The local fix package now includes:

`scripts/remote_runner_service_fix_window/proof_driver_checks.py`

The post-arm health check now derives `health_timer_name_meridian` from
`systemd_timer_status.timer_name`, with a legacy top-level fallback only when
the nested timer status is absent. The helper also preserves zero-valued fields
such as `orders_submitted=0`, `fill_count=0`, and `open_order_count=0`. It also
supports a `prearm-baseline` mode for the disarmed/no-order precheck before any
future authorization attempt.

Expected post-arm health checks are:

- `health_passed`
- `health_zero_critical`
- `health_live_capable_mode`
- `health_live_delta_still_armed`
- `health_no_orders_from_monitor`
- `health_no_fills_from_monitor`
- `health_timer_status_ok`
- `health_timer_name_meridian`
- `health_supervisor_open_orders_zero`

## Current Safe State

The latest reviewed Meridian supervisor run was:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T165128568634Z-mainnet-live-supervisor`

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=false`
- `live_delta_armed_at_finish=false`
- `live_delta_authorized=false`
- `orders_submitted=0`
- `fill_count=0`
- cycle status: `cycle_observed_no_order`

Systemd state at review time:

- `meridian-alpha-mainnet-supervisor-live.timer`: active/waiting, enabled
- `meridian-alpha-mainnet-health-monitor.timer`: active/waiting, enabled
- `meridian-alpha-mainnet-supervisor-live.service`: inactive/dead
- `meridian-alpha-mainnet-health-monitor.service`: inactive/dead

Only the Meridian path drop-ins were present under the Meridian service drop-in
directories. The live-capable `20-meridian-live-delta-config.conf` drop-ins
were not present.

## Decision

Do not re-arm live delta from this review window.

The post-entry-second execution and drift evidence are clean, and the health
monitor itself passed. The remaining blocker was the proof-driver field
contract, which has now been fixed locally but has not been exercised as a
fresh serialized remote authorization proof.

The next valid gate is a separate operator-approved proof-driver/precheck
window that uses this fixed health check and still starts from
`live_delta_armed=false`, no open orders, no in-flight service, and a fresh
read-only position monitor. Only after that gate is green should a separate
operator-approved re-arm window be considered.
