# Meridian Remote Live State 2026-06-01

Current status: `REMOTE_LIVE_CAPABLE_ARMED_AFTER_AUTO_REARM`.

Snapshot time: `2026-06-01T13:39:52.963565Z`
(`2026-06-01 21:39:52` Asia/Singapore).

This is a read-only documentation refresh against
`root@203.0.113.10`. It records the effective remote state observed at the
snapshot time. It did not stop timers, edit files, arm or disarm live delta, or
submit any order.

This addendum supersedes older Meridian window documents only for the question
"what is the current remote live-runner state?" It does not rewrite the outcome
of those historical windows.

## Non-Claims

- This does not update accepted evidence in `PROJECT_STATE.md`.
- This does not move the checked-in repository beyond
  `stage_1_research_readiness_only`.
- This does not approve formal Stage 4 automated execution readiness.
- This does not assert that auto-rearm is the desired target state.
- This does not make the old closure hash manifest a fresh proof package.

## Effective Systemd State

Observed host:

- hostname: `enhengclaw-binance-runner-sgp1`
- runner root: `/root/meridian_alpha_live_runner`
- deployed repo-like root: `/root/meridian_alpha_live_runner/repo`

Active Meridian timers:

- `meridian-alpha-mainnet-supervisor-live.timer`
  - `ActiveState=active`
  - `SubState=waiting`
  - `UnitFileState=enabled`
  - last trigger: `Mon 2026-06-01 13:37:47 UTC`
- `meridian-alpha-mainnet-health-monitor.timer`
  - `ActiveState=active`
  - `SubState=waiting`
  - `UnitFileState=enabled`
  - last trigger: `Mon 2026-06-01 13:38:57 UTC`

Legacy timers:

- `enhengclaw-mainnet-supervisor-live.timer`
  - `ActiveState=inactive`
  - `SubState=dead`
  - `UnitFileState=disabled`
- `enhengclaw-mainnet-health-monitor.timer`
  - `ActiveState=inactive`
  - `SubState=dead`
  - `UnitFileState=disabled`

Installed Meridian service drop-ins:

- `/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf`
- `/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.service.d/20-meridian-live-delta-config.conf`
- `/etc/systemd/system/meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf`
- `/etc/systemd/system/meridian-alpha-mainnet-health-monitor.service.d/20-meridian-live-delta-config.conf`

The effective supervisor and health service `ExecStart` commands use the
live-capable Meridian remote-runner config:

`/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`

They are not using the handoff-observation config as the effective runtime
config at this snapshot.

## Effective Live Strategy Identity

The effective remote runtime config lineage is the `hv_balanced` live line, not
the later `hv_tail_only` research challenger.

Current live strategy label:

```text
v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget
```

Current live strategy namespace:

```text
hv_balanced_binance_usdm_live_2x_full_balance_candidate
```

Current live config lineage:

```text
config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml
```

The latest Binance-only PIT research challenger,
`v5_binance_pit_top_mid_h10d_pruned3_hv_tail_only_soft_budget`, is not the
documented effective remote live config in this snapshot.

## Operator State

SQLite state DB:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3`

Observed rows:

- `paused=false`
  - last action:
    `20260531T153057346850Z:resume:20260531T153057346850Z-plan_only`
- `live_delta_armed=true`
  - last action:
    `20260601T065305653450Z:arm-live-delta:20260601T065304780397Z-mainnet-health-monitor`
  - action type: `arm-live-delta`
  - reason: `auto rearm after 3 clean supervisor/health runs`
  - updated at: `2026-06-01T06:53:05.653450Z`

This means the current armed state came from the health monitor auto-rearm path,
not from the original operator re-arm apply action on 2026-05-31.

## Latest Artifacts

Latest health monitor:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260601T133857762791Z-mainnet-health-monitor/run_summary.json`

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- warning alerts: `0`
- `no_order_expected=false`
- `live_delta_armed_after=true`
- auto-rearm gate:
  - `enabled=true`
  - `status=skipped_already_armed`
  - operator state: `paused=false`, `live_delta_armed=true`
- health monitor submitted `0` orders and recorded `0` fills.

Latest supervisor:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260601T133748529632Z-mainnet-live-supervisor/run_summary.json`

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- `live_delta_armed_at_start=true`
- `live_delta_armed_at_finish=true`
- `live_delta_authorized=false`
- orders submitted: `0`
- fills: `0`

Latest core loop:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_core_loop/20260601T133748578751Z-mainnet-core-loop/run_summary.json`

- status: `mainnet_core_loop_completed`
- blockers: `[]`
- orders submitted: `0`
- fills: `0`

Latest delta execution:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260601T132749591563Z-mainnet-delta-execution/run_summary.json`

- status: `mainnet_delta_orders_submitted`
- execution stage: `entry_second`
- planned delta orders: `1`
- fills: `1`
- reconciliation status: `reconciled`
- blockers: `[]`

## Auto-Rearm Chain

Earlier on 2026-06-01, a live-capable supervisor cycle hit a Binance rejection:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260601T055907970206Z-mainnet-delta-execution/run_summary.json`

- status: `mainnet_delta_reconcile_required`
- execution stage: `entry_second`
- planned delta orders: `1`
- blockers:
  - `mainnet_delta_order_rejected:XRPUSDT:http_400:-4164`

The associated supervisor and core-loop artifacts also carried the rejection:

- supervisor:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260601T055846683487Z-mainnet-live-supervisor/run_summary.json`
- core loop:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_core_loop/20260601T055846719531Z-mainnet-core-loop/run_summary.json`

The latest auto-rearm evidence observed earlier in the same audit showed:

- last disarm:
  `20260601T062218207241Z:disarm-live-delta:20260601T062217805323Z-mainnet-health-monitor`
- auto-rearm action:
  `20260601T065305653450Z:arm-live-delta:20260601T065304780397Z-mainnet-health-monitor`
- auto-rearm gate status: `auto_rearmed`
- clean supervisor run IDs:
  - `20260601T065139317050Z-mainnet-live-supervisor`
  - `20260601T064058337244Z-mainnet-live-supervisor`
  - `20260601T063010548727Z-mainnet-live-supervisor`
- recoverable disarm gate alert codes:
  - `core_loop_not_completed`
  - `supervisor_run_blockers`
  - `supervisor_run_not_completed`
- recoverable disarm gate blockers: `[]`

The important operational point is that the health monitor did not preserve the
XRPUSDT `-4164` rejection as a hard non-recoverable auto-rearm reason. After
three clean supervisor runs and the minimum disarm age, it re-armed live delta.

## Local/Remote Config Mapping

The remote deployed root is not a Git checkout, so current remote code identity
is established by file hash comparison rather than `git rev-parse`.

The following remote file hashes matched the local files at the time of the
audit:

- `src/enhengclaw/live_trading/mainnet_health_monitor.py`
  - `81193e06a424ee2d5fe8a9a7cc9905ee427437ffa3b2f6c183cc67cef80cb0c7`
- `src/enhengclaw/live_trading/mainnet_live_supervisor.py`
  - `e248ebc103ffb8265bbfc426e23e40abc651ed754991fb0ddeca98e40f9fd76a`
- `src/enhengclaw/live_trading/mainnet_delta_execution_runner.py`
  - `47285c7ab85b2457df6c5416077a97df907fbeb7e1da4df516ed27cd9857a83a`
- `src/enhengclaw/live_trading/execution_planner.py`
  - `808e631c9813614d506f4fab1bf12697ee0e2d480248606c52623b31854b1ece`
- `src/enhengclaw/live_trading/live_risk_controls.py`
  - `1c16688e268d96382a60b87e763d9ab0191e030bc93696e55a96f96b9f8eccd8`
- live-capable remote-runner config:
  - `d70981fe9450a72b76f1cb42eb43996956d7add7aa07260670c05ed02ce63977`
- handoff-observation config:
  - `11c5314691b10795ff40ec573c67b4e7559e76af1ba36f83ba4e554ad2ca3d1c`

The local top-level `config/live_trading/` directory does not contain the
Meridian remote-runner and handoff-observation YAMLs. Locally they live under:

- `scripts/remote_runner_service_migration/config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- `scripts/remote_runner_service_fix_window/config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`

## Current Boundary

At this snapshot, the remote state is live-capable and armed. The no-order /
disarmed handoff-observation state is not the effective remote state.

The safest documentation interpretation is:

- current remote fact: `REMOTE_LIVE_CAPABLE_ARMED_AFTER_AUTO_REARM`
- current roadmap fact: checked-in `PROJECT_STATE.md` still stays at
  `stage_1_research_readiness_only`
- unresolved mismatch: auto-rearm can re-arm after clean runs even when the
  preceding failure chain included an exchange rejection such as
  `mainnet_delta_order_rejected:XRPUSDT:http_400:-4164`
- recommended repair, if the operator wants fail-closed observation:
  explicitly pin the remote runner back to no-order/disarmed and patch
  auto-rearm hard-block logic before allowing further automatic recovery.
