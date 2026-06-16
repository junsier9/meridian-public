# Meridian Migration Closure Summary

Status: `COMPATIBILITY_MIGRATION_PACKAGE_CLOSED`.

Closure date: `2026-06-01` Asia/Singapore.

Post-closure remote-state addendum:
`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`.

The addendum supersedes this closure summary only for the current
point-in-time remote live-runner state. This closure summary remains the fixed
compatibility migration package record and does not become a fresh Stage 4 or
accepted-evidence update.

This document closes the compatibility-first rename package for
`Meridian Alpha Platform`. It summarizes the checked-in package, remote proof
windows, retained boundaries, rollback surfaces, and hash manifests that should
be treated as the fixed review input for any later cutover or cleanup work.

## Scope

This closure covers the compatibility migration from `EnhengClaw` to
`Meridian Alpha Platform`:

- display name: `Meridian Alpha Platform`
- canonical slug: `meridian_alpha`
- canonical environment prefix: `MERIDIAN_ALPHA_`
- legacy compatibility identity: `EnhengClaw`
- legacy environment prefix: `ENHENGCLAW_`

The package is not a destructive global replacement. The Python package name,
legacy environment variables, legacy retained evidence roots, and legacy
operator surfaces remain supported compatibility surfaces unless a future,
separate migration window retires them.

## Package Contents

Primary docs:

- `docs/PROJECT_IDENTITY_MIGRATION.md`
- `docs/MERIDIAN_TIMER_HANDOFF_CUTOVER_DESIGN_REVIEW.md`
- `docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md`
- `docs/MERIDIAN_TIMER_HANDOFF_FIX_WINDOW.md`
- `docs/MERIDIAN_POSITION_REFERENCE_FIX_WINDOW.md`
- `docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`
- `docs/MERIDIAN_LIVE_DELTA_AUTHORIZATION_WINDOW.md`
- `docs/MERIDIAN_POST_ENTRY_SECOND_REVIEW_PROOF_DRIVER_FIX_WINDOW.md`
- `docs/MERIDIAN_PROOF_DRIVER_PRECHECK_WINDOW.md`
- `docs/MERIDIAN_REARM_APPLY_WINDOW.md`
- `docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`

Local migration packages and proof tooling:

- `scripts/common/build_meridian_windows_scheduled_task_migration_package.ps1`
- `scripts/openclaw/provision_meridian_programdata_trust_root.py`
- `scripts/remote_runner_service_migration/`
- `scripts/remote_runner_service_fix_window/`

Compatibility code and tests:

- `src/enhengclaw/compat/`
- `src/meridian_alpha/`
- `tests/test_project_identity_compat.py`
- `tests/test_meridian_programdata_trust_root.py`
- `tests/test_remote_runner_service_migration_package.py`
- `tests/test_remote_runner_service_fix_window.py`

Live-runner compatibility and daily-PnL removal support:

- live-trading entrypoints now resolve compatible `MERIDIAN_ALPHA_*` and
  `ENHENGCLAW_*` environment names through the compatibility helper.
- `daily_realized_pnl_gate` is intentionally represented as a non-blocking
  removed marker in the current live loop and delta execution path.
- health monitoring treats `removed`, `disabled`, `not_applicable`, `passed`,
  and an empty daily-PnL status as inert for this retired gate.

## Closed External State Windows

Windows scheduled tasks:

- Disabled `Meridian Alpha ...` parallel clones were generated and registered.
- Clone validation was performed by temporary enable/start/disable windows.
- The first validated target was
  `Meridian Alpha OpenClaw Quant Universe Input Producer`.
- Dependency-chain validation covered Universe Freeze, CoinAPI Spot Sync,
  Monitoring Daily Cycle, and Repo Health Guard.
- `LEGACY_SURFACE_FROZEN` remains an intentional safety boundary.
- The Meridian scheduled-task clones remain disabled parallel migration
  surfaces, not replacements for the legacy tasks.

WSL workspace and retained-root routing:

- Meridian WSL workspace wrappers were proved in parallel.
- `%LOCALAPPDATA%\MeridianAlpha` exists only because bounded proof windows wrote
  retained-root routing proofs.
- `C:\ProgramData\MeridianAlpha\trust\allowed_signers` exists as a disabled
  proof-only trust root.
- `default_trust_root_dir()` still resolves to
  `C:\ProgramData\EnhengClaw\trust`.
- No accepted evidence path was updated to consume the Meridian ProgramData
  trust root.

Remote runner and service names:

- Remote host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- active timer names:
  - `meridian-alpha-mainnet-supervisor-live.timer`
  - `meridian-alpha-mainnet-health-monitor.timer`
- legacy timer names:
  - `enhengclaw-mainnet-supervisor-live.timer`
  - `enhengclaw-mainnet-health-monitor.timer`
- latest readback observed Meridian timers enabled and active while legacy
  timers remained disabled and inactive.

Remote ownership handoff was completed only after separate fix windows for:

- Meridian Python path and config resolution
- position-reference equivalence under the Meridian root
- health-alert recent-run counting
- observation-state re-prep
- proof-driver health-summary shape
- post-entry-second review

## Latest Remote Readback

Latest read-only remote snapshot used for closure:

- snapshot time: `2026-05-31T19:09:36Z`
- host: `root@203.0.113.10`
- runner root: `/root/meridian_alpha_live_runner`
- supervisor timer: `enabled`, `active`, `waiting`
- health timer: `enabled`, `active`, `waiting`
- supervisor service: `inactive`, `dead`, `Result=success`
- health service: `inactive`, `dead`, `Result=success`
- legacy supervisor timer: `disabled`, `inactive`
- legacy no-order timer: `disabled`, `inactive`

Latest supervisor artifact:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T190549686994Z-mainnet-live-supervisor/run_summary.json`

- status: `mainnet_live_supervisor_completed`
- blockers: `[]`
- config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
- live delta armed at start: `true`
- live delta armed at finish: `true`
- live delta authorized: `false`
- core loop status: `mainnet_core_loop_completed`
- core loop execution requested: `true`
- orders submitted: `0`
- fills: `0`
- open orders: `0`
- margin cushion: `passed`
- `daily_realized_pnl_gate.status=removed`
- `daily_realized_pnl_gate.enforcement=disabled`

Latest core-loop artifact:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_core_loop/20260531T190549722745Z-mainnet-core-loop/run_summary.json`

- status: `mainnet_core_loop_completed`
- blockers: `[]`
- orders submitted: `0`
- fills: `0`

Latest health artifact:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T190543192562Z-mainnet-health-monitor/run_summary.json`

- status: `mainnet_health_monitor_passed`
- critical alerts: `0`
- warning alerts: `0`
- `no_order_expected=false`
- `live_delta_armed_after=true`

SQLite operator state:

- state DB:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3`
- `paused=false`
- `live_delta_armed=true`
- latest live-delta action:
  `arm-live-delta` at `2026-05-31T17:17:38.942510Z`

## Post-Closure Remote State Refresh

A later read-only refresh is recorded in:

`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`

That refresh observed:

- snapshot time: `2026-06-01T13:39:52.963565Z`
- Meridian supervisor and health timers still active/enabled
- legacy timers still inactive/disabled
- effective Meridian supervisor and health services still using the
  live-capable `meridian_remote_runner.yaml` through `20-meridian-live-delta-config.conf`
- SQLite `paused=false`
- SQLite `live_delta_armed=true`
- latest live-delta action:
  `20260601T065305653450Z:arm-live-delta:20260601T065304780397Z-mainnet-health-monitor`
- latest health monitor:
  `20260601T133857762791Z-mainnet-health-monitor`, status
  `mainnet_health_monitor_passed`, `no_order_expected=false`,
  `live_delta_armed_after=true`
- latest supervisor:
  `20260601T133748529632Z-mainnet-live-supervisor`, status
  `mainnet_live_supervisor_completed`, armed at start and finish, zero
  orders/fills
- latest delta execution:
  `20260601T132749591563Z-mainnet-delta-execution`, status
  `mainnet_delta_orders_submitted`, `entry_second`, one planned delta order,
  one fill, reconciled
- effective live strategy lineage:
  `v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget` through the
  `hv_balanced_binance_usdm_live_2x_full_balance_candidate` runtime namespace

This means the current remote state is live-capable and armed after
health-monitor auto-rearm. It is not the no-order/disarmed handoff-observation
state.

## Daily-PnL Removal Proof

Daily realized PnL gate removal deploy/proof window:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_daily_pnl_gate_removal/20260531T175905Z-daily-pnl-gate-removal-deploy-proof`

Final local summary:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_daily_pnl_gate_removal/20260531T175905Z-daily-pnl-gate-removal-deploy-proof/final_verify/acceptance_summary.txt`

Acceptance result:

- status: `passed`
- latest supervisor:
  `20260531T180416380467Z-mainnet-live-supervisor`
- latest supervisor status: `mainnet_live_supervisor_completed`
- latest supervisor gate status: `removed`
- latest supervisor gate enforcement: `disabled`
- latest supervisor orders/fills: `0/0`
- latest core loop:
  `20260531T180416410890Z-mainnet-core-loop`
- latest core-loop status: `mainnet_core_loop_completed`
- latest health:
  `20260531T180751271958Z-mainnet-health-monitor`
- latest health status: `mainnet_health_monitor_passed`
- critical/warning alerts: `0/0`

The remote virtual environment did not include `pytest`; the proof window used
`python -m unittest` for selected tests and passed them.

## Hash Manifests

Closure package hash manifest:

- `docs/MERIDIAN_MIGRATION_CLOSURE_HASH_MANIFEST.txt`

Package-local manifests:

- `scripts/remote_runner_service_migration/PACKAGE_SHA256SUMS.txt`
- `scripts/remote_runner_service_fix_window/PACKAGE_SHA256SUMS.txt`

The closure manifest intentionally excludes itself to avoid self-referential
hash churn. It includes the closure summary, migration docs, proof scripts,
remote package drafts, compatibility code, and focused tests that constitute
the fixed review input for this closure commit.

## Rollback Surfaces

Windows scheduled tasks:

- Use the generated package rollback script to disable Meridian clone names.
- Legacy OpenClaw tasks were never replaced by the disabled-clone package.

ProgramData trust proof:

- Meridian ProgramData trust root remains proof-only.
- The current default trust root remains the legacy
  `C:\ProgramData\EnhengClaw\trust` boundary.

Remote runner/service:

- Remote package rollback scripts are retained under
  `scripts/remote_runner_service_migration/` and
  `scripts/remote_runner_service_fix_window/`.
- Remote proof windows also retained backups under their proof roots, including
  daily-PnL removal backup source:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_daily_pnl_gate_removal/20260531T175905Z-daily-pnl-gate-removal-deploy-proof/backup`
- Live delta can be paused/disarmed through the existing SQLite operator-state
  controls and health-monitor disarm path.

## Explicit Non-Claims

This closure does not claim:

- a destructive global rename is complete
- `EnhengClaw` can be removed from import paths, environment variables, task
  names, external paths, or retained evidence paths
- accepted evidence in `PROJECT_STATE.md` was updated
- the checked-in repository moved beyond
  `stage_1_research_readiness_only`
- formal Stage 4 or broad automated execution readiness
- default consumption of `C:\ProgramData\MeridianAlpha\trust`
- replacement of Windows scheduled tasks by their Meridian clone names

The durable state after this closure is compatibility-first: Meridian naming is
canonical for new identity surfaces and remote timer ownership, while legacy
`EnhengClaw` compatibility remains an explicit support boundary.
