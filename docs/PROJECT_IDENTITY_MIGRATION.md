# Meridian Alpha Platform Identity Migration

`Meridian Alpha Platform` is the project display name. The canonical new slug is
`meridian_alpha`, and the canonical new environment prefix is `MERIDIAN_ALPHA_`.

This branch is a compatibility migration, not a destructive global replacement:

- `import meridian_alpha...` is supported as an alias for the existing
  `enhengclaw` package.
- `MERIDIAN_ALPHA_*` environment variables are read before matching
  `ENHENGCLAW_*` variables.
- Existing `ENHENGCLAW_*` variables remain supported so local secrets, scheduled
  tasks, and external launchers keep working.
- Existing `%LOCALAPPDATA%\EnhengClaw`, `C:\ProgramData\EnhengClaw\trust`,
  OpenClaw WSL workspaces, and remote runner/service names are intentionally
  preserved until the separate external-state migration below is executed.

Do not hand-edit retained evidence paths to claim readiness under the new name.
Formal readiness still comes from the current retained evidence bundle and
checked-in governance contracts.

## Closure Summary

Current closure status: `COMPATIBILITY_MIGRATION_PACKAGE_CLOSED`.

The fixed closure summary for this branch is:

`docs/MERIDIAN_MIGRATION_CLOSURE_SUMMARY.md`

The current post-closure remote live-state addendum is:

`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md`

That addendum records the point-in-time remote state as live-capable and armed
after health-monitor auto-rearm. It is an operational state record, not a
Stage 4 readiness claim and not an accepted-evidence update.

The package-level hash manifest is:

`docs/MERIDIAN_MIGRATION_CLOSURE_HASH_MANIFEST.txt`

Closure keeps the compatibility-first boundary intact: Meridian naming is
canonical for new identity surfaces and the remote runner/timer ownership
surface, while `EnhengClaw` remains a supported import, environment-variable,
external path, and retained-evidence compatibility surface. This closure does
not update accepted evidence in `PROJECT_STATE.md` and does not claim a Stage 4
or formal live-trading readiness transition.

## External State Migration Checklist

This checklist is the operator-facing migration plan for host state that lives
outside git. It must be handled as a staged migration, not as search-and-replace.

### Naming Targets

| Surface | Legacy | Meridian target |
| --- | --- | --- |
| Project display | `EnhengClaw` | `Meridian Alpha Platform` |
| Python import | `enhengclaw` | `meridian_alpha` alias, legacy kept |
| Env prefix | `ENHENGCLAW_` | `MERIDIAN_ALPHA_`, legacy kept |
| Windows app dir | `%LOCALAPPDATA%\EnhengClaw` | `%LOCALAPPDATA%\MeridianAlpha` |
| Windows trust root | `C:\ProgramData\EnhengClaw\trust` | `C:\ProgramData\MeridianAlpha\trust` |
| WSL main workspace | `/root/.openclaw/workspace-enhengclaw-main` | `/root/.openclaw/workspace-meridian-alpha-main` |
| WSL audit workspace | `/root/.openclaw/workspace-enhengclaw-audit` | `/root/.openclaw/workspace-meridian-alpha-audit` |
| Remote runner root | `/root/enhengclaw_live_runner` | `/root/meridian_alpha_live_runner` |
| Mainnet live timer | `enhengclaw-mainnet-supervisor-live.timer` | `meridian-alpha-mainnet-supervisor-live.timer` |
| Mainnet health timer | `enhengclaw-mainnet-health-monitor.timer` | `meridian-alpha-mainnet-health-monitor.timer` |

### Read-Only Inventory Snapshot

Captured on the local Windows/WSL host with read-only commands during this
branch work. This is an inventory snapshot, not a readiness claim.

| Surface | Current observation | Migration status |
| --- | --- | --- |
| Windows scheduled tasks | 16 matching `OpenClaw`/quant/research tasks; 16 disabled `Meridian Alpha ...` clones registered from the package below; all Meridian clones confirmed `Disabled` with 0 running tasks after one-shot validation. | Parallel clone registration complete; successful proofs recorded through the monitoring daily cycle; frozen/downstream-blocked proofs recorded for guarded surfaces. |
| Scheduled task actions | Matching tasks point at `C:\Users\user\Documents\Claude\Projects\EnhengClaw\...` runner scripts, except the disabled WSL keepalive task. | Keep legacy tasks and repo paths until new tasks pass scheduled-cycle windows and external roots are separately migrated. |
| WSL workspaces | `/root/.openclaw/workspace-enhengclaw-main`, `/root/.openclaw/workspace-enhengclaw-audit`, `/root/.openclaw/workspace-meridian-alpha-main`, and `/root/.openclaw/workspace-meridian-alpha-audit` exist. | Parallel workspace clone complete; Meridian wrappers use `meridian_alpha` module aliases while the repo target path remains the current Windows checkout. |
| Local retained evidence | `%LOCALAPPDATA%\EnhengClaw` exists with 25 top-level items, 39193 recursive files, about 1703.247 MB, including `openclaw_live_market_observer`, `openclaw_research_workbench`, `market_history`, `quant_research`, and runtime state. Latest observed writes during this migration were on 2026-05-31 under `quant_research` and `openclaw_research_workbench`. | Preserve as historical and compatibility evidence; the current disabled-clone proof flow still writes here. |
| New local app dir | `%LOCALAPPDATA%\MeridianAlpha` exists only because the bounded proof windows below wrote `retained_root_routing_proofs\20260531T060914Z`, `retained_root_routing_proofs\20260531T061917Z`, `programdata_trust_root_proofs\20260531T063034Z`, and `explicit_e2e_proofs\20260531T063455Z`. Current snapshot enumerated at least 19 recursive files, about 15.202 KB; local proof trust-root ACLs may deny full recursive listing. | Keep as proof artifacts only; do not treat it as the default retained evidence root. |
| ProgramData trust root | `C:\ProgramData\EnhengClaw` exists; `C:\ProgramData\EnhengClaw\trust` exists and has no recursive files in this snapshot. | Preserve as the current default trust boundary until a new trust root is generated and verified. |
| New ProgramData root | `C:\ProgramData\MeridianAlpha\trust\allowed_signers` now exists from disabled proof `20260531T063034Z` and was refreshed by explicit E2E proof `20260531T063455Z`; `default_trust_root_dir()` still resolves to `C:\ProgramData\EnhengClaw\trust`. | Provisioned as disabled proof only; no default path, scheduled task, persistent env var, or accepted-evidence path consumes it. |
| Remote service names | Read-only audit on 2026-05-31 reached `root@203.0.113.10` / `enhengclaw-binance-runner-sgp1`; a later disabled staging window created `/root/meridian_alpha_live_runner`, installed the four `meridian-alpha-mainnet-*` unit files, and left both Meridian timers disabled/inactive. After path/config, observation-state, and position-reference fix windows, a post-reference read-only precheck passed with false checks `[]`. The first post-reference apply rolled back after health alerts from superseded blocked proof runs. The remote health-alert fix apply installed only the amended Meridian handoff-observation proof config with `recent_run_count=1` and reset the failed Meridian health service. After post-health-fix observation-state re-prep and a green read-only handoff precheck, the operator-approved post-health-fix apply completed: the Meridian supervisor and health timers are active/enabled, the timer-created supervisor completed, the timer-created health monitor passed with 0 critical alerts, open orders remained 0, the same 11 open positions were recognized, legacy supervisor/health timers stayed disabled/inactive, and accepted evidence was not updated. | `HANDOFF_COMPLETED_POST_HEALTH_FIX`; Meridian timer ownership is active, but this is not formal live-trading readiness. |

### 1. Windows Scheduled Tasks

Goal: register Meridian-named tasks in parallel while leaving the existing
OpenClaw tasks available for rollback.

Read-only audit:

```powershell
Get-ScheduledTask |
  Where-Object {
    $_.TaskName -match 'EnhengClaw|OpenClaw|Quant|research|Meridian|Alpha' -or
    $_.TaskPath -match 'EnhengClaw|OpenClaw|Meridian|Alpha'
  } |
  Sort-Object TaskPath, TaskName |
  Select-Object TaskPath, TaskName, State
```

Package builder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\common\build_meridian_windows_scheduled_task_migration_package.ps1
```

The builder is repo-local and non-mutating. It exports the current matching
legacy task XML, writes disabled Meridian clone XML, and emits two operator
scripts inside the generated package:

- `register_disabled_meridian_clones.ps1`: registers only Meridian clone names
  and immediately disables them.
- `rollback_disable_meridian_clones.ps1`: disables only Meridian clone names.

The generated package is intentionally under ignored `artifacts\...` output. A
local package produced during this migration is:

`artifacts\external_state_migration\windows_scheduled_tasks\20260530T163213Z\`

Registration status:

- `register_disabled_meridian_clones.ps1` was executed after `-WhatIf` review.
- All 16 `Meridian Alpha ...` clones were registered and remain `Disabled`.
- All 16 legacy `OpenClaw ...` tasks still exist; their prior Ready/Disabled
  states were not replaced.
- The first manual proof target was
  `Meridian Alpha OpenClaw Quant Universe Input Producer`.

First manual proof:

- The Meridian clone was temporarily enabled, started once, and disabled again.
- Final clone state: `Disabled`.
- Task Scheduler result: `LastTaskResult = 0`.
- Fresh scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_universe_input_producer`
  returned `status = passed`, `summary_success = true`, and
  `summary_fresh = true`.
- Refreshed summary:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_universe_input_producer.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T17:17:01.0313413Z`.
- Fresh generated artifacts:
  - `artifacts\quant_research\_quant_inputs\pit-liquidity-top100-2026-05-31.quant_universe.json`
  - `artifacts\quant_research\cycles\2026-05-31\quant_universe_input_producer_summary.json`
- The run was successful with `candidate_count = 99`,
  `candidates_with_perp_count = 90`, `excluded_count = 1`, and
  `top100_complete = false`; that is a successful producer run with one
  excluded candidate, not a full top-100 completion proof.

Second direct-downstream manual proof:

- The next clone target was `Meridian Alpha OpenClaw Quant Universe Freeze`
  because it consumes the freshly generated universe input.
- The Meridian clone was temporarily enabled, started once, and disabled again.
- Final clone state: `Disabled`.
- Clone Task Scheduler result: `LastTaskResult = 0`.
- Fresh scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_universe_freeze`
  returned `status = passed`, `summary_success = true`, and
  `summary_fresh = true`.
- Refreshed summary:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_universe_freeze.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T17:22:25.4092654Z`.
- Fresh generated artifacts:
  - `artifacts\quant_research\universe\2026-05-31\universe_snapshot.json`
  - `artifacts\quant_research\cycles\2026-05-31\universe_freeze_summary.json`
- The run was successful with `candidate_count = 99`,
  `source_input_as_of = 2026-05-31`, `source_input_age_days = 0`, and
  `fallback_applied = false`.
- The legacy `OpenClaw Quant Universe Freeze` task was not started by this
  proof; its older Task Scheduler `LastTaskResult = 1` remains historical
  legacy state while the fresh summary now passes.

Third dependency-chain manual proof:

- The next clone target was
  `Meridian Alpha OpenClaw Quant CoinAPI Spot Sync` because it consumes the
  freshly generated quant universe input.
- The Meridian clone was temporarily enabled, started once, and disabled again.
- Final clone state: `Disabled`.
- Clone Task Scheduler result: `LastTaskResult = 0`.
- Fresh scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_coinapi_spot_sync`
  returned `status = passed`, `summary_success = true`, and
  `summary_fresh = true`.
- Refreshed summary:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_coinapi_spot_sync.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T17:30:01.2452716Z`.
- External data root:
  `%LOCALAPPDATA%\EnhengClaw\market_history\coinapi_ohlcv`.
- The run was successful with `as_of = 2026-05-31`, `mode = refresh`,
  `requested_symbol_count = 99`, `top100_symbol_count = 99`,
  `top30_intraday_symbol_count = 30`, `successful_sync_count = 129`, and
  `phase_failure_count = 0`.
- Phase details:
  - `spot_1d_4h_refresh`: 99 candidates, 99 successful syncs, 0 failures.
  - `spot_1h_refresh`: 30 candidates, 30 successful syncs, 0 failures.
- The legacy `OpenClaw Quant CoinAPI Spot Sync` task was not started by this
  proof; its older Task Scheduler `LastTaskResult = 1` remains historical
  legacy state while the fresh summary now passes.

Fourth dependency-chain manual proof:

- The next clone target was
  `Meridian Alpha OpenClaw Quant Derivatives Sync` because it consumes the
  freshly generated quant universe input and follows the market-history sync
  lane before the broader monitoring daily cycle.
- The Meridian clone was temporarily enabled, started once, and disabled again.
- Final clone state: `Disabled`.
- Clone Task Scheduler result: `LastTaskResult = 0`.
- Fresh scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_derivatives_sync`
  returned `status = passed`, `summary_success = true`, and
  `summary_fresh = true`.
- Refreshed summary:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_derivatives_sync.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T17:40:40.5681085Z`.
- External data root:
  `%LOCALAPPDATA%\EnhengClaw\market_history\binance_derivatives`.
- The run was successful with `as_of = 2026-05-31`, `mode = refresh`,
  `provider = coinglass`, `exchange = binance`, `required_symbol_count = 90`,
  `symbol_count = 90`, `intervals = 4h, 1d`, and `coverage_status = ok`.
- Latest refresh interval details:
  - `4h`: 90 symbols, 90 successful syncs, 0 warnings,
    `median_stored_coverage_days = 760.5`.
  - `1d`: 90 symbols, 90 successful syncs, 0 warnings,
    `median_stored_coverage_days = 762.0`.
- By-as-of retained summary:
  `%LOCALAPPDATA%\EnhengClaw\market_history\binance_derivatives\summaries\by_as_of\2026-05-31\sync_summary.json`
  completed successfully but retained `warning_count = 51` for provider data
  that starts after the requested 730-day window. This is a provider coverage
  caveat, not a clone registration failure.
- The legacy `OpenClaw Quant Derivatives Sync` task was not started by this
  proof; its older Task Scheduler `LastTaskResult = 1` remains historical
  legacy state while the fresh summary now passes.

Fifth dependency-chain manual proof:

- The next clone target was
  `Meridian Alpha OpenClaw Quant Monitoring Daily Cycle` because the declared
  upstream summaries were fresh for `binance_ohlcv_sync`,
  `quant_derivatives_sync`, `quant_coinapi_spot_sync`,
  `quant_universe_input_producer`, and `quant_universe_freeze`.
- The Meridian clone was temporarily enabled, started once, and disabled again
  immediately after start so the scheduled 03:45 trigger could not fire from
  the clone. The running one-shot instance was then allowed to complete.
- Final clone state: `Disabled`.
- Clone Task Scheduler result: `LastTaskResult = 0`.
- All 16 `Meridian Alpha ...` clones were confirmed `Disabled`, with 0 running
  tasks after completion.
- Fresh scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_research_daily_cycle`
  returned `status = passed`, `summary_success = true`, and
  `summary_fresh = true`.
- Refreshed summary:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_research_daily_cycle.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T18:48:30.3825943Z`.
- Fresh generated artifacts:
  - `artifacts\quant_research\cycles\2026-05-31\quant_cycle_summary.json`
  - `artifacts\quant_research\cycles\2026-05-31\quant_cycle_summary.md`
- The run was successful with `as_of = 2026-05-31`,
  `cycle_mode = deterministic_core`, `compiler_backend = deterministic`,
  `readiness_verdict = ready`, `universe_count = 99`,
  `daily_strategy_count = 4`, `experiment_count = 4`,
  `trainable_strategy_count = 2`, and `passed_experiment_count = 0`.
- Dataset and feature lanes generated for:
  - `2026-05-31-single-asset-4h`
  - `2026-05-31-cross-sectional-daily-1d`
  - `2026-05-31-cross-sectional-intraday-1h`
- Research caveats retained by the summary:
  - `aggregate_metrics.pass_rate = 0.0`.
  - `experiment_status_counts = {fail: 2, invalidated: 2}`.
  - Blocked strategy ids were
    `core-btc-balanced-mean-reversion-single-asset` and
    `core-liquidity-balanced-ranking-scorer-intraday-cross-sectional`.
  - Derivatives coverage validation retained `status = warning` and
    `warning_count = 51` from provider data that starts after the requested
    window.
- The `readiness_verdict = ready` value is the deterministic quant daily-cycle
  research verdict only. It is not live-trading approval and does not override
  the repo's Stage 1 boundary.
- The legacy `OpenClaw Quant Monitoring Daily Cycle` task was not started by
  this proof; its older Task Scheduler `LastTaskResult = 1` remains historical
  legacy state while the fresh summary now passes.

Sixth direct-downstream manual proof:

- The next clone target was `Meridian Alpha OpenClaw Quant Repo Health Guard`
  because it directly depends on the freshly refreshed
  `quant_research_daily_cycle` summary.
- Pre-run upstream evidence showed
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_research_daily_cycle.last_run_summary.json`
  was fresh and successful with
  `produced_at_utc = 2026-05-30T18:48:30.3825943Z`.
- Source inspection found the current runner is intentionally frozen before it
  invokes Python:
  `scripts\quant_research\run_openclaw_quant_repo_health_guard_runner.ps1`
  writes `runner_status=LEGACY_SURFACE_FROZEN`,
  `error_code=legacy_quant_surface_frozen`, and exits `78`.
- The Meridian clone was temporarily enabled, started once, and disabled again.
- Final clone state: `Disabled`.
- Clone Task Scheduler result: `LastTaskResult = 78`.
- All 16 `Meridian Alpha ...` clones were confirmed `Disabled`, with 0 running
  tasks after completion.
- Fresh clone log:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\repo_health_guard_logs\openclaw_quant_repo_health_guard_20260531_025649.log`
  contained:
  - `runner_status=LEGACY_SURFACE_FROZEN`
  - `error_code=legacy_quant_surface_frozen`
- Scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys quant_repo_health_guard`
  still reported `summary_not_fresh:quant_repo_health_guard`; the retained
  summary remained the old failed
  `%LOCALAPPDATA%\EnhengClaw\quant_research\quant_repo_health_guard.last_run_summary.json`
  from `2026-04-23T09:40:06.4461856Z`.
- This proof validates clone registration and rollback safety only. It does not
  validate a successful repo-health guard run because the checked-in runner is
  intentionally fail-closed on the legacy frozen surface.
- The legacy `OpenClaw Quant Repo Health Guard` task was not started by this
  proof; its older Task Scheduler `LastTaskResult = 78` remains historical
  legacy state.

Seventh downstream-blocked manual proof:

- The downstream clone targets were:
  - `Meridian Alpha OpenClaw Research Intake Cycle`, which depends on
    `quant_repo_health_guard` and `structural_research_scan`.
  - `Meridian Alpha OpenClaw Quant Exploration Daily Full Cycle`, which
    depends on `quant_repo_health_guard`.
- This was an expected fail-closed validation, not a successful downstream run,
  because the upstream `quant_repo_health_guard` summary remained unsuccessful
  under the checked-in `LEGACY_SURFACE_FROZEN` guard.
- `Meridian Alpha OpenClaw Research Intake Cycle` was temporarily enabled,
  started once, and disabled again.
- Research Intake final clone state: `Disabled`.
- Research Intake clone Task Scheduler result: `LastTaskResult = 75`.
- Research Intake wrote a fresh unsuccessful summary:
  `%LOCALAPPDATA%\EnhengClaw\openclaw_research_workbench\research_intake_cycle.last_run_summary.json`
  with `produced_at_utc = 2026-05-30T19:04:03.7502306Z`.
- Research Intake fresh log:
  `%LOCALAPPDATA%\EnhengClaw\openclaw_research_workbench\intake_runner_logs\openclaw_research_intake_runner_20260531_030403.log`
  contained:
  - `upstream_status=stale`
  - `upstream_blocker=upstream summary not successful: quant_repo_health_guard`
  - `upstream_blocker=upstream summary stale: structural_research_scan age_hours=676.984`
  - `runner_status=RETRY_UPSTREAM_NOT_READY`
- `Meridian Alpha OpenClaw Quant Exploration Daily Full Cycle` was temporarily
  enabled, started once, and disabled again.
- Quant Exploration final clone state: `Disabled`.
- Quant Exploration clone Task Scheduler result: `LastTaskResult = 78`.
- Quant Exploration fresh log:
  `%LOCALAPPDATA%\EnhengClaw\quant_research\proposal_runner_logs\openclaw_quant_strategy_proposal_runner_20260531_030456.log`
  contained:
  - `runner_status=LEGACY_SURFACE_FROZEN`
  - `error_code=legacy_quant_surface_frozen`
- All 16 `Meridian Alpha ...` clones were confirmed `Disabled`, with 0 running
  tasks after completion.
- Scheduled-task audit:
  `scripts\common\audit_openclaw_windows_host_tasks.ps1 -RequiredTaskKeys @('research_intake_cycle','quant_strategy_proposal_cycle')`
  returned `status = passed` for task presence and metadata, with expected
  warnings:
  - `summary_not_fresh:research_intake_cycle`
  - `summary_not_fresh:quant_strategy_proposal_cycle`
- This proof validates that the downstream clones do not bypass the frozen or
  stale upstream boundary. It does not validate successful Research Intake or
  Quant Exploration cycles.

Frozen-surface decision:

- Keep `LEGACY_SURFACE_FROZEN` as the safety boundary for the current
  scheduled-task clone migration package.
- Do not thaw `Repo Health Guard`, `Research Intake`, or `Quant Exploration`
  inside this clone-registration validation flow.
- A future thaw or replacement must be handled as a separate small change
  window with its own acceptance criteria:
  - `quant_repo_health_guard` writes a fresh successful summary.
  - `research_intake_cycle` no longer stops on stale upstream evidence.
  - `quant_strategy_proposal_cycle` is either intentionally kept frozen or
    replaced by a runner with explicit success/failure summaries.
  - All affected clone tasks return to `Disabled` after one-shot validation.
- Until that window exists, downstream frozen or stale summaries remain a
  deliberate stop condition, not a scheduled-task migration failure.

Windows artifact disposition:

- Keep in git:
  - This migration checklist.
  - The package builder:
    `scripts\common\build_meridian_windows_scheduled_task_migration_package.ps1`.
  - Compatibility code and tests for the project identity rename.
- Keep off-git on the operator host:
  - The generated scheduled-task migration package under
    `artifacts\external_state_migration\windows_scheduled_tasks\20260530T163213Z\`.
  - `%LOCALAPPDATA%\EnhengClaw\...` retained summaries and runner logs written
    by the one-shot validation runs.
  - Registered disabled `Meridian Alpha ...` task clones.
- Clean from the git working tree unless a later quant-research evidence window
  explicitly accepts them:
  - `artifacts\quant_research\cycles\2026-05-31\...`
  - `artifacts\quant_research\experiments\2026-05-31-...\...`
- Do not delete historical retained evidence or the ignored external migration
  package to make `git status` look clean.

Migration steps:

1. Export every matching existing task to XML before changing anything.
2. Register parallel task names with a `Meridian Alpha OpenClaw ...` prefix.
3. Keep action paths pointed at the same checked-out repo until the code rename
   is separately proven on the operator host.
4. Update only environment variables in task actions when the called script
   supports `MERIDIAN_ALPHA_*` aliases.
5. Run each new task manually once, then wait for one scheduled cycle.
6. Disable the matching legacy task only after the new task writes the expected
   success summary and no downstream task loses its input.

Success criteria:

- New task exists, is enabled only when its legacy counterpart was enabled, and
  writes a fresh retained summary under the expected external root.
- The old task remains restorable from XML.
- Scheduled-task ordering is preserved, especially the universe input producer
  before downstream quant jobs.

Rollback:

- Disable the Meridian task.
- Re-enable the exported legacy task.
- Do not delete retained evidence from either root.

### 2. WSL OpenClaw Workspaces

Goal: introduce Meridian workspace names without breaking the existing OpenClaw
wrapper tools.

Read-only audit:

```powershell
wsl.exe -d Ubuntu-24.04 --user root -- bash -lc `
  "find /root/.openclaw -maxdepth 1 -type d -name 'workspace-*' -printf '%p\n' | sort"
```

Migration steps:

1. Clone or copy the legacy workspaces to:
   - `/root/.openclaw/workspace-meridian-alpha-main`
   - `/root/.openclaw/workspace-meridian-alpha-audit`
2. Update wrapper scripts inside the new workspaces to call
   `python -m meridian_alpha.integrations.openclaw.<lane>` where supported.
3. Leave legacy wrapper scripts untouched until recorded smoke and live-gated
   smoke both pass through the new workspace paths.
4. Update repo constants such as `RECORDED_WSL_SMOKE`, `LIVE_WSL_SMOKE`, and
   `GENERIC_AUDIT_WSL` only after the new workspaces exist on the operator host.

Parallel clone status:

- The Meridian workspaces were created with parallel copies from the legacy
  workspaces:
  - `/root/.openclaw/workspace-enhengclaw-main` ->
    `/root/.openclaw/workspace-meridian-alpha-main`
  - `/root/.openclaw/workspace-enhengclaw-audit` ->
    `/root/.openclaw/workspace-meridian-alpha-audit`
- Legacy WSL workspaces were left in place and unmodified.
- The new main workspace wrapper scripts were updated to call
  `meridian_alpha.integrations.openclaw.<lane>` where supported.
- The new main workspace smoke helpers were updated to import
  `meridian_alpha.testing` and `meridian_alpha.integrations.openclaw...`.
- The new audit workspace metadata now uses
  `workspace_id = workspace-meridian-alpha-audit`.
- The WSL repo target path remains
  `/mnt/c/Users/user/Documents/Claude/Projects/EnhengClaw` because the Windows
  checkout directory has not been migrated.

WSL proof:

- From `/root/.openclaw/workspace-meridian-alpha-main`, all eight recorded
  smoke scripts returned `status = success` and `run_state = FINALIZED`:
  - `smoke_market_observer_recorded.sh`
  - `smoke_attention_allocator_recorded.sh`
  - `smoke_evidence_agent_recorded.sh`
  - `smoke_research_lead_recorded.sh`
  - `smoke_research_synthesizer_recorded.sh`
  - `smoke_risk_governance_agent_recorded.sh`
  - `smoke_risk_signal_agent_recorded.sh`
  - `smoke_validation_agent_recorded.sh`
- The recorded smoke run emitted Python `runpy` warnings for continue-existing
  lane aliases because `meridian_alpha` resolves to the legacy `enhengclaw`
  modules in `sys.modules`; the scripts still returned exit code 0.
- From `/root/.openclaw/workspace-meridian-alpha-audit`,
  `tools/audit_openclaw_response.sh` successfully audited a minimal temporary
  response JSON.
- No live-gated WSL smoke was run in this migration step.
- Repo constants that point at WSL workspace paths have not been changed yet.

Success criteria:

- Recorded smokes pass from the Meridian main workspace.
- Audit scripts pass from the Meridian audit workspace.
- Formal deployment readiness still requires explicit execution permits and the
  retained evidence bundle; WSL smoke success alone is not a readiness claim.

Rollback:

- Point constants and operator notes back to `workspace-enhengclaw-main` and
  `workspace-enhengclaw-audit`.
- Keep the Meridian workspaces disabled or archived; do not remove legacy
  workspaces until a later cleanup window.

### 3. ProgramData And LocalAppData Retained Evidence

Goal: keep historical evidence immutable while allowing new runs to write under
Meridian-named external roots.

Read-only audit:

```powershell
$roots = @(
  "$env:LOCALAPPDATA\EnhengClaw",
  "$env:LOCALAPPDATA\MeridianAlpha",
  "C:\ProgramData\EnhengClaw",
  "C:\ProgramData\MeridianAlpha",
  "C:\ProgramData\EnhengClaw\trust",
  "C:\ProgramData\MeridianAlpha\trust"
)

foreach ($root in $roots) {
  [pscustomobject]@{
    Path = $root
    Exists = Test-Path -LiteralPath $root
    LastWrite = if (Test-Path -LiteralPath $root) {
      (Get-Item -LiteralPath $root).LastWriteTime
    } else {
      $null
    }
  }
}
```

Read-only inventory result captured on 2026-05-31:

- `%LOCALAPPDATA%\EnhengClaw`: exists, directory, 25 top-level directories,
  39193 recursive files, about 1703.247 MB. Recent observed writes include:
  - `quant_research\proposal_runner_logs\openclaw_quant_strategy_proposal_runner_20260531_030456.log`
  - `openclaw_research_workbench\research_intake_cycle.last_run_summary.json`
  - `quant_research\quant_research_daily_cycle.last_run_summary.json`
  - `quant_research\quant_derivatives_sync.last_run_summary.json`
  - `market_history\binance_derivatives\last_sync_summary.json`
- `%LOCALAPPDATA%\MeridianAlpha`: does not exist.
- `C:\ProgramData\EnhengClaw`: exists with top-level directories
  `real-shadow-trust`, `trust`, and `trust_acl_test`; no recursive files were
  present in this snapshot.
- `C:\ProgramData\EnhengClaw\trust`: exists, directory, no recursive files.
  ACL inventory showed explicit non-inherited trust-root permissions, including
  a deny entry for the current user and allow entries for `SYSTEM`,
  `Administrators`, `Users`, and the current user.
- `C:\ProgramData\MeridianAlpha`: does not exist.
- `C:\ProgramData\MeridianAlpha\trust`: does not exist.

Code support check:

- Current default runtime/trust helpers still resolve legacy roots:
  `default_trust_root_dir()` resolves to `ProgramData\EnhengClaw\trust`,
  while lease registry, freeze path, runtime sessions, and default audit roots
  resolve under `%LOCALAPPDATA%\EnhengClaw`.
- OpenClaw live and research provisioning accept explicit root arguments, but
  their defaults still point at `%LOCALAPPDATA%\EnhengClaw\...` and
  `C:\ProgramData\EnhengClaw\trust`.
- Scheduled-task manifests and runner scripts still discover success summaries
  under `%LOCALAPPDATA%\EnhengClaw\...`.
- The `MERIDIAN_ALPHA_*` compatibility layer covers environment-variable
  aliases, not a complete automatic retained-root migration.

Current decision for this phase:

- Generate only a bounded `%LOCALAPPDATA%\MeridianAlpha` routing proof root,
  not a copied evidence tree and not a default-root cutover.
- Do not generate `C:\ProgramData\MeridianAlpha\trust` yet.
- Do not copy legacy retained evidence into a Meridian-named root. Historical
  evidence remains authoritative only at its original path.
- Treat Meridian-named retained roots as a separate provisioning/proof window:
  first add or prove explicit root routing across the consumer, then run a fresh
  Meridian-named evidence-producing command, then verify ACL/trust-root checks.
- Metadata repair is now complete for explicit local trust-root proofs:
  provisioning summaries distinguish `explicit_trust_root` from the default
  `readonly_programdata` mode.

Routing proof window:

- Proof id: `20260531T060914Z`.
- Producer: `python scripts\openclaw\provision_openclaw_research_inputs.py`.
- Why this producer: it provisions scheduled research workbench inputs only; it
  does not run an OpenClaw research cycle, does not call model/provider APIs,
  and does not enable or register scheduled tasks.
- Command shape:

```powershell
$ProofRoot = "$env:LOCALAPPDATA\MeridianAlpha\retained_root_routing_proofs\20260531T060914Z"
$ExternalRoot = Join-Path $ProofRoot "openclaw_research_workbench"
$TrustRoot = Join-Path $ProofRoot "trust_root_local_only"

python scripts\openclaw\provision_openclaw_research_inputs.py `
  --external-root $ExternalRoot `
  --trust-root-dir $TrustRoot `
  --expires-after-hours 1
```

- Result:
  - `status = success`
  - `workflow = scheduled_research`
  - `expires_after_hours = 1`
  - `trust_root_validation = passed`
  - `summary_path = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T060914Z\openclaw_research_workbench\provision_summary.json`
  - `retained_root = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T060914Z\openclaw_research_workbench\retained`
  - `allowed_signers_path = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T060914Z\trust_root_local_only\allowed_signers`
- Independent verification:
  - All required proof files existed: `provision_summary.json`,
    `execution_permit.json`, `owner_review.json`, `batch_approval.json`,
    signer private/public keys, `allowed_signers`, and the retained directory.
  - All required proof paths were under `%LOCALAPPDATA%\MeridianAlpha`.
  - No required proof path was under `%LOCALAPPDATA%\EnhengClaw`.
  - `C:\ProgramData\MeridianAlpha` and
    `C:\ProgramData\MeridianAlpha\trust` still did not exist.
  - Loading the generated permit with `MERIDIAN_ALPHA_TRUST_ROOT_DIR` pointing
    at the proof trust root succeeded.
- Initial caveat: this first generated summary used the inherited metadata
  labels `trust_root_mode = readonly_programdata` and
  `trust_root_override_applied = false` even though an explicit local-only
  `--trust-root-dir` was supplied. The path fields were correct, but the
  metadata label was not.

Metadata repair proof:

- Proof id: `20260531T061917Z`.
- Code change:
  - direct provisioning summaries now report
    `trust_root_mode = explicit_trust_root` and
    `trust_root_override_applied = true` when `--trust-root-dir` is supplied.
  - default trust-root provisioning still reports
    `trust_root_mode = readonly_programdata` and
    `trust_root_override_applied = false`.
  - the market-observer operator wrapper now propagates the provisioning
    summary's trust-root metadata instead of overwriting it with env-mapping
    metadata.
- Result:
  - `status = success`
  - `workflow = scheduled_research`
  - `expires_after_hours = 1`
  - `trust_root_mode = explicit_trust_root`
  - `trust_root_override_applied = true`
  - `trust_root_validation = passed`
  - `summary_path = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\provision_summary.json`
  - `retained_root = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\retained`
  - `allowed_signers_path = %LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\trust_root_local_only\allowed_signers`
- Independent verification:
  - all required proof files existed.
  - all required proof paths were under `%LOCALAPPDATA%\MeridianAlpha`.
  - no required proof path was under `%LOCALAPPDATA%\EnhengClaw`.
  - `C:\ProgramData\MeridianAlpha` and
    `C:\ProgramData\MeridianAlpha\trust` still did not exist.
  - loading the generated permit with `MERIDIAN_ALPHA_TRUST_ROOT_DIR` pointing
    at the proof trust root succeeded.

ProgramData disabled trust-root provisioning design:

- Helper:
  `python scripts\openclaw\provision_meridian_programdata_trust_root.py`.
- Default mode is plan-only. It reads the supplied signer public key and reports
  the intended target, but does not create `C:\ProgramData\MeridianAlpha\trust`.
- Apply mode requires both:
  - `--apply`
  - `--confirm-boundary I_UNDERSTAND_THIS_DOES_NOT_UPDATE_ACCEPTED_EVIDENCE`
- Default target:
  `C:\ProgramData\MeridianAlpha\trust`.
- Source signer for the first disabled proof should be a Meridian proof signer,
  for example:
  `%LOCALAPPDATA%\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\signer\execution_signer.pub`.
- Plan-only proof command already run:

```powershell
$PublicKey = "$env:LOCALAPPDATA\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\signer\execution_signer.pub"
python scripts\openclaw\provision_meridian_programdata_trust_root.py `
  --public-key-path $PublicKey
```

- Plan-only result:
  - `status = planned`
  - `target_trust_root = C:\ProgramData\MeridianAlpha\trust`
  - `allowed_signers_path = C:\ProgramData\MeridianAlpha\trust\allowed_signers`
  - `target_exists_before = false`
  - `target_existing_entries = []`
  - `apply = false`
  - `disabled_by_default = true`
  - `default_trust_root_changed = false`
  - `persistent_environment_changed = false`
  - `scheduled_tasks_updated = false`
  - `accepted_evidence_paths_updated = false`
  - `project_state_updated = false`
  - `copies_legacy_evidence = false`

Apply-window command executed:

```powershell
$PublicKey = "$env:LOCALAPPDATA\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\signer\execution_signer.pub"
$Permit = "$env:LOCALAPPDATA\MeridianAlpha\retained_root_routing_proofs\20260531T061917Z\openclaw_research_workbench\permit\execution_permit.json"

python scripts\openclaw\provision_meridian_programdata_trust_root.py `
  --public-key-path $PublicKey `
  --permit-path $Permit `
  --apply `
  --confirm-boundary I_UNDERSTAND_THIS_DOES_NOT_UPDATE_ACCEPTED_EVIDENCE
```

Apply-window result:

- Proof id: `20260531T063034Z`.
- Summary:
  `%LOCALAPPDATA%\MeridianAlpha\programdata_trust_root_proofs\20260531T063034Z\meridian_programdata_trust_root_proof_summary.json`
- Created:
  `C:\ProgramData\MeridianAlpha\trust\allowed_signers`
- Result fields:
  - `status = success`
  - `disabled_by_default = true`
  - `trust_root_mode = explicit_trust_root`
  - `trust_root_override_applied = true`
  - `trust_root_validation.status = passed`
  - `trust_root_validation.validated_with_env = MERIDIAN_ALPHA_TRUST_ROOT_DIR`
  - `trust_root_validation.permit_validation = passed`
  - `permit_id = permit-321e1801-56b4-423a-bae6-ec1174dd1285`
  - `default_trust_root_changed = false`
  - `persistent_environment_changed = false`
  - `scheduled_tasks_updated = false`
  - `accepted_evidence_paths_updated = false`
  - `project_state_updated = false`
  - `copies_legacy_evidence = false`
- Independent verification:
  - `allowed_signers` matched the Meridian proof signer public key.
  - Loading the proof permit with process-local
    `MERIDIAN_ALPHA_TRUST_ROOT_DIR=C:\ProgramData\MeridianAlpha\trust`
    succeeded.
  - `default_trust_root_dir()` still returned
    `C:\ProgramData\EnhengClaw\trust`.
  - No process, user, or machine environment variable was persisted for
    `MERIDIAN_ALPHA_TRUST_ROOT_DIR` or `ENHENGCLAW_TRUST_ROOT_DIR`.
  - No scheduled task action referenced `ProgramData\MeridianAlpha`,
    `MeridianAlpha\trust`, or `MERIDIAN_ALPHA_TRUST_ROOT_DIR`.
  - `PROJECT_STATE.md` `Current Accepted Evidence` still referenced only the
    legacy accepted evidence paths.
  - Repository-wide search outside this migration document found no
    `C:\ProgramData\MeridianAlpha\trust` accepted-evidence consumer.

Explicit LocalAppData + ProgramData E2E proof:

- Proof id: `20260531T063455Z`.
- Producer:
  `python scripts\openclaw\provision_openclaw_research_inputs.py`.
- Command shape:

```powershell
$ProofId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$ProofRoot = Join-Path $env:LOCALAPPDATA "MeridianAlpha\explicit_e2e_proofs\$ProofId"
$ExternalRoot = Join-Path $ProofRoot "openclaw_research_workbench"
$TrustRoot = "C:\ProgramData\MeridianAlpha\trust"
python scripts\openclaw\provision_openclaw_research_inputs.py `
  --external-root $ExternalRoot `
  --trust-root-dir $TrustRoot `
  --expires-after-hours 1
```

- Summary:
  `%LOCALAPPDATA%\MeridianAlpha\explicit_e2e_proofs\20260531T063455Z\openclaw_research_workbench\provision_summary.json`
- Result fields:
  - `status = success`
  - `workflow = scheduled_research`
  - `trust_root_mode = explicit_trust_root`
  - `trust_root_override_applied = true`
  - `trust_root_validation = passed`
  - `trust_root_dir = C:\ProgramData\MeridianAlpha\trust`
  - `permit_id = permit-502d4454-a9d6-499a-b612-6083f5fc1108`
  - `external_root` and `retained_root` are under
    `%LOCALAPPDATA%\MeridianAlpha\explicit_e2e_proofs\20260531T063455Z\...`
- Independent verification:
  - Required artifacts existed:
    `provision_summary.json`, `permit\execution_permit.json`,
    `permit\owner_review.json`, `permit\batch_approval.json`,
    `signer\execution_signer`, `signer\execution_signer.pub`, `retained\`,
    and `C:\ProgramData\MeridianAlpha\trust\allowed_signers`.
  - All required local proof paths stayed under the explicit
    `%LOCALAPPDATA%\MeridianAlpha\explicit_e2e_proofs\20260531T063455Z`
    root.
  - No required local proof path used `%LOCALAPPDATA%\EnhengClaw`.
  - `allowed_signers` matched this E2E proof's signer public key. This refreshed
    the disabled Meridian ProgramData trust root to the E2E proof signer; it did
    not make the path a default or accepted-evidence consumer.
  - Loading the generated permit with process-local
    `MERIDIAN_ALPHA_TRUST_ROOT_DIR=C:\ProgramData\MeridianAlpha\trust`
    succeeded while `ENHENGCLAW_TRUST_ROOT_DIR` was absent.
  - The validation process reported
    `default_trust_root_dir=C:\ProgramData\EnhengClaw\trust` and
    `resolved_allowed_signers=C:\ProgramData\MeridianAlpha\trust\allowed_signers`.
  - No user, machine, or long-lived process environment variable was persisted
    for `MERIDIAN_ALPHA_TRUST_ROOT_DIR` or `ENHENGCLAW_TRUST_ROOT_DIR`.
  - No scheduled task action referenced `ProgramData\MeridianAlpha`,
    `MeridianAlpha\trust`, or `MERIDIAN_ALPHA_TRUST_ROOT_DIR`.
  - `PROJECT_STATE.md` `Current Accepted Evidence` still referenced only the
    legacy accepted evidence paths.

ACL boundary:

- The helper reuses the existing OpenClaw trust-root publication functions.
- During publication, the target is temporarily writable only long enough to
  replace `allowed_signers`.
- After publication, the Windows ACL is locked with inheritance removed:
  `SYSTEM` and `Administrators` retain full control, the current operator user
  has read/execute on the directory and read on `allowed_signers`, and the
  current operator user receives an explicit write deny on the directory.
- Validation uses the same trust-root security check as execution permits; it
  fails closed if the runtime user can still write the trust root or
  `allowed_signers`.

Rollback boundary:

- Rollback is allowed only while this path remains disabled: no scheduled task,
  persistent env var, accepted evidence path, or formal retained bundle may
  reference `C:\ProgramData\MeridianAlpha\trust`.
- Rollback target is only `C:\ProgramData\MeridianAlpha\trust`; do not touch
  `C:\ProgramData\EnhengClaw\trust` or any `%LOCALAPPDATA%\EnhengClaw`
  retained evidence.
- Before removal, inspect the latest proof summary under
  `%LOCALAPPDATA%\MeridianAlpha\programdata_trust_root_proofs\...` and confirm
  `accepted_evidence_paths_updated = false`,
  `scheduled_tasks_updated = false`, and `persistent_environment_changed = false`.
- After removal, rerun the plan-only helper; expected rollback confirmation is
  `target_exists_before = false` and `target_existing_entries = []`.

Accepted-evidence boundary:

- Do not update `PROJECT_STATE.md`.
- Do not update the `Current Accepted Evidence` section.
- Do not claim OpenClaw deployment readiness, real-24h readiness, or broad agent
  readiness from this proof. It proves only that a disabled Meridian-named
  ProgramData trust root can be generated and validated.

Migration steps:

1. Do not move, rewrite, or rename existing retained evidence.
2. Add explicit CLI/env support for the new root before changing defaults.
3. Generate a fresh Meridian-named retained bundle under
   `%LOCALAPPDATA%\MeridianAlpha\...`.
4. Publish a new read-only trust root under `C:\ProgramData\MeridianAlpha\trust`
   only from a fresh provisioning command.
5. Run an explicit E2E proof that supplies both the Meridian LocalAppData root
   and the Meridian ProgramData trust root as explicit arguments.
6. Update `PROJECT_STATE.md` accepted evidence paths only when a new formal
   retained bundle is actually accepted by the existing evidence rules.

Success criteria:

- Historical `%LOCALAPPDATA%\EnhengClaw\...` evidence remains readable.
- New `%LOCALAPPDATA%\MeridianAlpha\...` evidence is generated by a real run,
  not by copying old verdicts.
- `C:\ProgramData\MeridianAlpha\trust` is read-only and accepted by the same
  trust-root checks as the legacy path.

Rollback:

- Use the explicit legacy retain root and trust root arguments.
- Keep both directories; never delete historical evidence to make a status page
  look clean.

### 4. Remote Runner And Service Names

Goal: migrate live-facing remote names only through a separate, operator-approved
server window. This is the highest-risk portion because timer state can affect
mainnet behavior.

Read-only remote audit to run before any migration:

```bash
systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'
systemctl list-units --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'
systemctl cat enhengclaw-mainnet-supervisor-live.service
systemctl cat enhengclaw-mainnet-health-monitor.service
ls -ld /root/enhengclaw_live_runner /root/meridian_alpha_live_runner 2>/dev/null
```

Read-only audit snapshot from 2026-05-31:

- Reachable remote endpoint:
  `root@203.0.113.10`.
- Reserved endpoint:
  `root@203.0.113.11` closed the SSH connection during this audit.
- Remote host:
  `enhengclaw-binance-runner-sgp1`.
- Active/enabled live-facing timers:
  - `enhengclaw-mainnet-supervisor-live.timer`
  - `enhengclaw-mainnet-health-monitor.timer`
- Loaded but disabled fallback timer:
  - `enhengclaw-mainnet-supervisor-noorder.timer`
- Current live service commands point at:
  - `WorkingDirectory=/root/enhengclaw_live_runner/repo`
  - `/root/enhengclaw_live_runner/bin/with-live-env`
  - `/root/enhengclaw_live_runner/venv/bin/python`
  - `config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml`
- Meridian remote units were not installed:
  - `meridian-alpha-mainnet-supervisor-live.service`
  - `meridian-alpha-mainnet-supervisor-live.timer`
  - `meridian-alpha-mainnet-health-monitor.service`
  - `meridian-alpha-mainnet-health-monitor.timer`
- Meridian runner root was absent:
  `/root/meridian_alpha_live_runner`.
- Legacy live timer was actively producing fresh artifacts during the audit.
  This means an apply window must avoid running the legacy and Meridian
  live-capable supervisor timers concurrently.
- The audit did not read Binance account state, did not call trading APIs, and
  did not update accepted evidence.

Disabled remote staging result from 2026-05-31:

- Fresh precheck at `2026-05-31T07:37:26Z` passed:
  - legacy supervisor timer active/waiting and enabled
  - legacy health timer active/waiting and enabled
  - legacy no-order timer inactive/dead and disabled
  - legacy supervisor and health oneshot services inactive/dead
  - all Meridian units absent before install
  - `/root/enhengclaw_live_runner` present
  - `/root/meridian_alpha_live_runner` absent before install
- Local package was repaired before use because the disabled-unit verifier
  originally would have scanned the whole `/etc/systemd/system` directory and
  falsely failed on legitimate legacy units. The refreshed package id is
  `remote-runner-service-migration-local-freeze-20260531T073901Z`.
- Remote staged package:
  `/root/meridian_alpha_live_runner/review_package/remote-runner-service-migration-local-freeze-20260531T073901Z`
- Remote package hash validation:
  `sha256sum -c scripts/remote_runner_service_migration/PACKAGE_SHA256SUMS.txt`
  passed for all package files.
- Runner staging:
  - `/root/meridian_alpha_live_runner/repo` created from the legacy repo with
    `artifacts` and `.git` excluded.
  - `/root/meridian_alpha_live_runner/bin/with-live-env` copied with mode
    `0700`.
  - `/root/meridian_alpha_live_runner/venv` symlinked to the existing legacy
    venv. This preserves the no-secrets-migration boundary for the disabled
    staging window.
  - Meridian config staged at
    `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`.
- Legacy unit rollback copies:
  `/root/meridian_alpha_live_runner/rollback_legacy_units/20260531T074215Z`
- Meridian units installed:
  - `/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.service`
  - `/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.timer`
  - `/etc/systemd/system/meridian-alpha-mainnet-health-monitor.service`
  - `/etc/systemd/system/meridian-alpha-mainnet-health-monitor.timer`
- Validation:
  - `systemctl daemon-reload` completed.
  - `systemd-analyze verify` passed for the four Meridian units.
  - `verify_disabled_meridian_units.sh --unit-dir /etc/systemd/system --expect-installed`
    passed.
  - `meridian-alpha-mainnet-supervisor-live.timer`:
    `LoadState=loaded`, `ActiveState=inactive`, `UnitFileState=disabled`.
  - `meridian-alpha-mainnet-health-monitor.timer`:
    `LoadState=loaded`, `ActiveState=inactive`, `UnitFileState=disabled`.
  - Legacy supervisor and health timers remained the only active timers.
- Explicitly not done:
  - no Meridian timer was enabled or started
  - no legacy timer was stopped or disabled
  - no timer cutover was performed
  - no secret path was migrated
  - no Binance API/account/order check was run in this staging step
  - no accepted evidence path or `PROJECT_STATE.md` section was updated

Meridian runner read-only/no-order proof from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/read_only_no_order/20260531T075353Z-meridian-runner-readonly-noorder-proof`
- Command executed from the Meridian runner tree:
  `/root/meridian_alpha_live_runner/bin/with-live-env /root/meridian_alpha_live_runner/venv/bin/python scripts/live_trading/run_binance_usdm_remote_readonly_preflight_standalone.py`
- Retained proof files:
  - `proof_window.json`
  - `remote_readonly_preflight_summary.json`
  - `service_activity_probe.tsv`
  - `timers_initial.txt`
  - `timers_before.txt`
  - `timers_after.txt`
  - `unit_state_initial.txt`
  - `unit_state_before.txt`
  - `unit_state_after.txt`
  - `quiet_window_wait.tsv`
- Proof-window result:
  - `proof_artifact_safe=true`
  - `proof_goal_status=passed`
  - `proof_verdict=safe_artifact_written_readonly_probe_blocked`
  - `zero_order_side_effects=true`
  - `legacy_live_overlap_sample_count=0`
  - `meridian_service_active_sample_count=0`
  - `meridian_timers_inactive_disabled_after=true`
  - `legacy_timers_active_enabled_after=true`
- The read-only Binance account probe itself returned
  `readonly_preflight_status=blocked` with blocker
  `mainnet_open_positions_exist:11`. This is expected to block any account-green
  or live-readiness claim, but it does not indicate an order side effect.
- The proof wrapper initially misclassified disabled Meridian timers because
  `systemctl is-enabled <disabled timer>` exits nonzero even while printing
  `disabled`. The original wrapper output is retained as
  `proof_window.initial_wrapper_bug.json`; `proof_window.json` was recomputed
  from the retained summary, service activity probe, and current systemd state.
- Explicitly not done in this proof:
  - no Meridian timer was enabled or started
  - no legacy timer was stopped or disabled
  - no timer cutover was performed
  - no order, cancel, or order-test endpoint was called
  - no accepted evidence path or `PROJECT_STATE.md` section was updated

Read-only account/position inventory from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/account_position_inventory/20260531T083420Z-account-position-inventory`
- Inventory artifact:
  `account_position_inventory.json`
- The inventory used the Meridian runner tree and called only signed GET
  endpoints:
  - `GET /fapi/v3/account`
  - `GET /fapi/v2/positionRisk`
  - `GET /fapi/v1/openOrders`
  - `GET /fapi/v1/accountConfig`
  - `GET /fapi/v1/positionSide/dual`
  - `GET /sapi/v1/account/apiRestrictions`
- Side-effect boundary:
  - `orders_submitted=0`
  - `orders_canceled=0`
  - `order_test_calls=0`
  - `only_http_get_endpoints=true`
- Current account summary:
  - `account_readable=true`
  - `can_trade=true`
  - `position_mode=one_way`
  - `open_order_count=0`
  - `open_position_count=11`
  - API key reading and futures permissions were readable and true.
  - API withdrawals were false.
  - API IP restriction was true.
- Expected-position basis:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution/reconciliation.json`
- Latest legacy delta execution summary:
  - `status=mainnet_delta_orders_submitted`
  - `planned_delta_order_count=1`
  - `submitted_order_count=1`
  - `fill_count=1`
  - `reduce_only_intent_count=0`
  - `non_reduce_only_intent_count=1`
  - `reconciliation_status=reconciled`
  - `blockers=[]`
- Current inventory exactly matched the latest legacy reconciliation:
  - `matches_latest_legacy_reconciliation=true`
  - `symbols_added_vs_basis=[]`
  - `symbols_missing_vs_basis=[]`
  - `quantity_mismatches=[]`
- Current reconciled positions:
  - `AAVEUSDT -6.4`
  - `APTUSDT -278.5`
  - `ARBUSDT -5150.6`
  - `BCHUSDT -0.581`
  - `BNBUSDT 1.1`
  - `BTCUSDT 0.012`
  - `DOGEUSDT 876.0`
  - `ETHUSDT 0.305`
  - `FILUSDT -366.3`
  - `UNIUSDT -261.0`
  - `XRPUSDT 197.4`
- Interpretation:
  - The 11 open positions are expected relative to the latest active legacy
    runner reconciliation, not merely the older 2026-05-23 reserve-150
    top-up baseline.
  - The inventory does not authorize cutover or new execution; it only proves
    the current positioned account state is explainable by retained legacy
    artifacts.
- New cutover blocker observed during this inventory window:
  - latest legacy health artifact:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T082649459963Z-mainnet-health-monitor/run_summary.json`
  - `status=mainnet_health_monitor_alerted`
  - `critical_alert_count=5`
  - `orders_submitted=0`
  - `fill_count=0`
  - `live_delta_armed_after=false`
  - `enhengclaw-mainnet-health-monitor.service` was `active=failed`,
    `sub=failed` after the inventory.
- Decision boundary:
  - Do not proceed to Meridian cutover design while the legacy health monitor
    is failed/alerting.
  - First run a separate read-only health-alert triage window to explain the
    five critical alerts, the failed systemd health service state, and whether
    the active legacy timer policy is still intentional.

Read-only health-alert triage from 2026-05-31:

- Failed/alerting health artifact:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T082649459963Z-mainnet-health-monitor/run_summary.json`
- Alerting health result:
  - `status=mainnet_health_monitor_alerted`
  - `critical_alert_count=5`
  - `warning_alert_count=0`
  - `orders_submitted=0`
  - `fill_count=0`
  - `live_delta_armed_after=false`
  - Telegram alert was sent.
  - `disarm-live-delta` was recorded at `2026-05-31T08:26:56.213190Z`.
- The five critical alerts all point to the same supervisor artifact:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T080005004393Z-mainnet-live-supervisor/run_summary.json`
- The alert codes were:
  - `supervisor_run_not_completed`
  - `supervisor_run_blockers`
  - `account_reconcile_not_passed`
  - `core_loop_not_completed`
  - `margin_cushion_gate_not_passed`
- Root interpretation:
  - This was one grouped fail-closed incident, not five independent trading
    failures.
  - The underlying supervisor run started with `live_delta_armed_at_start=true`
    and `execute_live_delta_requested=true`, but did not submit orders.
  - It blocked because the read-only Binance SAPI permission endpoint returned
    HTTP `502 Bad Gateway`:
    `GET /sapi/v1/account/apiRestrictions`.
  - That made API-key permissions unreadable, account reconciliation blocked,
    the core loop blocked, and margin-cushion status unavailable.
  - The health monitor then disarmed live delta and exited nonzero by design.
- Failed systemd service interpretation:
  - `enhengclaw-mainnet-health-monitor.service` was `failed` after the
    alerting run because alert exit code is configured as the service failure
    signal.
  - A later health run passed without operator mutation:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T084717798362Z-mainnet-health-monitor/run_summary.json`
  - At `2026-05-31T08:49:09Z`, the health service was
    `ActiveState=inactive`, `SubState=dead`, `Result=success`,
    `ExecMainStatus=0`.
  - The latest health run had `critical_alert_count=0`,
    `status=mainnet_health_monitor_passed`, and `live_delta_armed_after=false`.
- Current legacy timer state observed at `2026-05-31T08:49:09Z`:
  - `enhengclaw-mainnet-supervisor-live.timer` active/enabled
  - `enhengclaw-mainnet-health-monitor.timer` active/enabled
  - latest supervisor:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T084135668349Z-mainnet-live-supervisor/run_summary.json`
  - latest supervisor result:
    `status=mainnet_live_supervisor_completed`, `orders_submitted=0`,
    `fill_count=0`, `live_delta_armed_at_start=false`,
    `live_delta_armed_at_finish=false`, `blockers=[]`.
- Remaining risk:
  - `auto_rearm_live_delta` is enabled in the legacy health policy.
  - At `2026-05-31T08:49:09Z`, auto-rearm was still blocked only by
    `blocked_disarm_too_recent`.
  - The recorded gate showed `seconds_since_last_disarm=1221.585` and
    `min_seconds_since_last_disarm=1800.0`.
  - If the active legacy timers continue to produce clean supervisor and
    health runs, the health monitor may re-arm live delta after the minimum
    disarm age is satisfied.
- Decision boundary:
  - Do not start Meridian cutover design while the legacy timer policy can
    still auto-rearm live delta.
  - The next window should be an explicit, operator-approved legacy timer
    freeze/stabilization window, not a Meridian cutover window.
  - The freeze/stabilization acceptance target should prove:
    `live_delta_armed=false`, no open orders, no in-flight service, no
    auto-rearm path, and documented rollback before any Meridian timer is
    enabled.

Legacy live timer freeze/stabilization apply from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/legacy_timer_freeze/20260531T090132Z-legacy-live-timer-freeze`
- Important pre-apply finding:
  - The previously identified auto-rearm risk had already materialized before
    the freeze window.
  - `state_before.json` showed `live_delta_armed=true`.
  - The latest live-delta action was:
    `20260531T085730732551Z:arm-live-delta:20260531T085722900572Z-mainnet-health-monitor`.
  - The reason was `auto rearm after 3 clean supervisor/health runs`.
  - Open orders were still zero before the freeze.
- Apply actions performed:
  - Captured rollback unit files and `systemctl cat` output under
    `rollback_units\`.
  - Waited for a quiet window with no active legacy supervisor or health
    service.
  - Stopped and disabled:
    - `enhengclaw-mainnet-supervisor-live.timer`
    - `enhengclaw-mainnet-health-monitor.timer`
  - Recorded an operator `kill-switch` through the legacy runner:
    `/root/enhengclaw_live_runner/bin/with-live-env /root/enhengclaw_live_runner/venv/bin/python scripts/live_trading/run_hv_balanced_live.py --config config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml --operator-action kill-switch`
  - Did not enable, start, or modify any Meridian timer.
  - Did not submit, cancel, or test any order.
- Retained proof files:
  - `freeze_acceptance.json`
  - `state_before.json`
  - `state_after.json`
  - `open_orders_before.json`
  - `open_orders_after.json`
  - `timers_before.txt`
  - `timers_after.txt`
  - `unit_state_before.txt`
  - `unit_state_after.txt`
  - `operator_kill_switch_summary.json`
  - `rollback_checklist.md`
  - `rollback_units\`
- Freeze acceptance:
  - `accepted=true`
  - `legacy_timers_frozen_inactive_disabled=true`
  - `legacy_services_not_inflight=true`
  - `meridian_timers_still_disabled=true`
  - `operator_paused_by_kill_switch=true`
  - `live_delta_armed_false=true`
  - `open_order_count_zero=true`
  - `local_state_health_ok=true`
  - `auto_rearm_scheduled_path_removed=true`
  - `auto_rearm_runtime_gate_blocked_by_operator_pause=true`
  - `rollback_checklist_present=true`
- Fresh post-apply verification at `2026-05-31T09:02:13Z`:
  - `systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'`
    listed `0 timers`.
  - `enhengclaw-mainnet-supervisor-live.timer` was `inactive/disabled`.
  - `enhengclaw-mainnet-health-monitor.timer` was `inactive/disabled`.
  - `enhengclaw-mainnet-supervisor-live.service` was `inactive/dead`.
  - `enhengclaw-mainnet-health-monitor.service` was `inactive/dead`.
  - both Meridian timers remained `inactive/disabled`.
  - `operator_state.paused=true`.
  - `operator_state.live_delta_armed=false`.
  - `open_order_count=0`.
  - read-only side effects remained zero:
    `orders_submitted=0`, `orders_canceled=0`, `order_test_calls=0`,
    `only_http_get_endpoints=true`.
- Rollback boundary:
  - `rollback_checklist.md` restores only the legacy observation timers unless
    a separate operator approval explicitly re-authorizes live delta.
  - A safe rollback should `resume`, then `disarm-live-delta`, then re-enable
    the two legacy timers and verify open orders remain zero.
  - Full pre-freeze live-capable behavior is not restored by this migration
    window because the pre-freeze state included an auto-rearmed live delta.
- Decision boundary:
  - The legacy live timer surface is now frozen and stabilized for naming
    migration review.
  - Meridian cutover is still not performed.
  - The next step is a reviewed Meridian timer handoff design. A real cutover
    remains out of scope until a separately approved apply window.

Fresh read-only Meridian cutover precheck from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_cutover_precheck/20260531T091118Z-frozen-baseline-readonly-precheck`
- This was a frozen-baseline precheck only:
  - no timer cutover was performed
  - no legacy or Meridian timer was enabled, started, disabled, or stopped
  - no operator state was mutated
  - no order, cancel, or test-order endpoint was called
  - proof writes were limited to the Meridian proof-artifact root above
- Acceptance:
  - `precheck_passed=true`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `legacy_timers_frozen_inactive_disabled=true`
  - `legacy_services_not_inflight=true`
  - `operator_paused=true`
  - `live_delta_armed_false=true`
  - `open_order_count=0`
  - `open_position_count=11`
  - `auto_rearm_config_still_true=true`
  - `auto_rearm_scheduled_path_removed=true`
  - `auto_rearm_runtime_gate_blocked_by_operator_pause=true`
  - `meridian_timers_loaded_inactive_disabled=true`
  - `meridian_services_loaded_not_active=true`
  - `meridian_units_reference_meridian_root_only=true`
  - `package_hash_manifest_ok=true`
  - `disabled_meridian_unit_verifier_ok=true`
- Independent readback after the precheck confirmed:
  - `systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'`
    listed `0 timers`.
  - legacy live and health timers remained `inactive/disabled`.
  - Meridian live and health timers remained `inactive/disabled`.
  - legacy and Meridian services remained `inactive/dead`.
- Retained proof files:
  - `cutover_precheck_acceptance.json`
  - `state_and_account.json`
  - `timers.txt`
  - `units.txt`
  - `unit_state.txt`
  - legacy and Meridian `systemctl cat` captures
  - `package_sha256sum_check.txt`
  - `package_sha256sum_check.exit_code`
  - `verify_disabled_meridian_units.txt`
  - `verify_disabled_meridian_units.exit_code`
  - `runner_paths.txt`
  - `precheck.log`
- Decision boundary:
  - The frozen baseline is healthy enough to draft and review a controlled
    Meridian timer handoff window.
  - This precheck does not approve cutover and does not authorize live delta.
  - Any actual cutover still requires a fresh operator-approved apply window,
    new rollback capture, and post-apply verification.

Meridian timer handoff/cutover design review from 2026-05-31:

- Local review artifact:
  `docs/MERIDIAN_TIMER_HANDOFF_CUTOVER_DESIGN_REVIEW.md`
- This window produced only:
  - future apply steps
  - rollback steps
  - verification steps
  - go/no-go checklist
- It did not connect to the remote host.
- It did not enable, start, stop, or disable any remote timer or service.
- It did not mutate operator state, accepted evidence, secrets, strategy,
  capital, risk, or live intent.
- It intentionally did not modify the frozen remote package hash manifest.
- The default rollback target for any future handoff apply is the frozen
  baseline: all legacy and Meridian timers off, operator pause retained, live
  delta disarmed, and open orders zero. Restoring active legacy timers is a
  separate operator decision, not the default rollback.
- Decision boundary:
  - A real cutover is still not approved.
  - Before any future apply, rerun a fresh serialized remote precheck and
    require all go/no-go items in the design artifact to pass.

Fresh design-review pre-apply read-only precheck from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T095720Z-design-review-readonly-precheck`
- Acceptance artifact:
  `handoff_precheck_acceptance.json`
- Result:
  - `precheck_passed=true`
  - `handoff_approved_for_apply=false`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - `open_order_count=0`
  - `open_position_count=11`
- All design-review go/no-go read-only checks were true:
  - package hash manifest verification passed
  - disabled Meridian unit verifier passed
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed `0 timers`
  - legacy live, health, and no-order timers were inactive/disabled
  - Meridian live and health timers were inactive/disabled
  - legacy and Meridian services were inactive/dead
  - Meridian units referenced `/root/meridian_alpha_live_runner` only
  - Binance account and open-order reads succeeded
  - open position inventory matched the explained 11-position set
  - operator state was readable, `paused=true`, and `live_delta_armed=false`
  - auto-rearm remained configured but had no scheduled path and was blocked
    by operator pause
- Independent readback after the precheck confirmed:
  - no false checks in `handoff_precheck_acceptance.json`
  - `systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'`
    still listed `0 timers`
  - all legacy and Meridian timer units remained inactive/disabled
- Retained proof files:
  - `handoff_precheck_acceptance.json`
  - `state_and_account.json`
  - `timers.txt`
  - `units.txt`
  - `unit_state.txt`
  - legacy and Meridian `systemctl cat` captures
  - `package_sha256sum_check.txt`
  - `package_sha256sum_check.exit_code`
  - `verify_disabled_meridian_units.txt`
  - `verify_disabled_meridian_units.exit_code`
  - `runner_paths.txt`
  - `meridian_unit_reference_scan.txt`
  - `account_read.exit_code`
  - `precheck.log`
- Decision boundary:
  - The frozen baseline is currently green enough to justify opening a
    separate operator-approved apply window for Meridian timer handoff.
  - This precheck still does not approve cutover and does not authorize live
    delta.
  - If any time passes or any remote state changes before apply, rerun this
    serialized precheck again.

Operator-approved apply window decision record from 2026-05-31:

- Local artifact:
  `docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md`
- Recommended decision:
  `GO_TO_OPERATOR_APPROVAL`
- Current approval status:
  `approval_pending`
- Current apply status:
  `not_applied`
- Evidence basis:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T095720Z-design-review-readonly-precheck`
- Decision boundary:
  - The latest read-only evidence supports asking the operator to approve a
    separate apply window.
  - The decision record does not approve cutover by itself.
  - The apply window must not run until the operator explicitly approves the
    target host, timer-handoff scope, no-live-delta boundary, and frozen
    rollback target.

Cutover request blocked by mandatory pre-apply precheck from 2026-05-31:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T110109Z-pre-apply-readonly-precheck`
- Acceptance artifact:
  `apply_prereq_precheck_acceptance.json`
- Result:
  - `precheck_passed=false`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - `open_order_count=0`
  - `open_position_count=11`
- False checks:
  - `operator_paused=false`
  - `live_delta_armed_false=false`
  - `auto_rearm_runtime_gate_blocked_by_operator_pause=false`
- Read-only root cause:
  - latest pause-state action was
    `20260531T105307555559Z:resume:20260531T105307555559Z-plan_only`
    with reason `operator requested remote arm window; clear pause before
    arm-only, timers remain disabled`
  - latest live-delta action was
    `20260531T105308678526Z:arm-live-delta:20260531T105308678526Z-plan_only`
    with reason `operator requested remote arm-only; no timer start and no
    supervisor invocation`
- Safety state that still held:
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed `0 timers`
  - all legacy and Meridian timer units were inactive/disabled
  - all legacy and Meridian services were inactive/dead
  - no related active services were observed
  - open orders remained zero
- Decision boundary:
  - `NO_GO_FOR_CUTOVER`
  - Meridian timers must not be enabled while operator pause is false and live
    delta is armed.
  - The next safe path is a separate re-freeze/stabilization action that records
    operator `kill-switch` or equivalent disarm/pause, then reruns the
    serialized read-only precheck before any cutover.

Re-freeze, cutover attempt, and rollback from 2026-05-31:

- Legacy runner re-freeze proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/legacy_timer_refreeze/20260531T111154Z-operator-kill-switch-before-meridian-handoff`
  - `refreeze_passed=true`
  - `operator_paused=true`
  - `live_delta_armed=false`
- Meridian runner state seed proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_state_refreeze/20260531T111455Z-meridian-operator-kill-switch-before-handoff`
  - `refreeze_passed=true`
  - `operator_paused=true`
  - `live_delta_armed=false`
- Final pre-cutover read-only precheck:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T111549Z-final-pre-cutover-readonly-precheck`
  - `precheck_passed=true`
  - `legacy_operator_paused_disarmed=true`
  - `meridian_operator_paused_disarmed=true`
  - `timers_zero=true`
  - `open_order_count=0`
- Handoff attempt root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover`
  - `handoff_applied=true`
  - Meridian health timer became active
  - Meridian supervisor timer became active
  - legacy timers stayed inactive
  - no live delta was armed
- Verification outcome:
  - `handoff_cycle_verification.json` recorded
    `verification_passed=false` and `rollback_required=true`.
  - Open orders remained zero.
  - No submitted orders or fills were observed.
  - Later triage found supervisor artifacts in the Meridian tree, including:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T111641250467Z-mainnet-live-supervisor`
    and
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T112707172721Z-mainnet-live-supervisor`.
  - The supervisor exited blocked with `operator_paused`,
    `orders_submitted=0`, `fill_count=0`, and `live_delta_armed=false`.
  - The health monitor failed with `FileNotFoundError` for:
    `/root/enhengclaw_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`.
  - The traceback showed the Meridian health service script invoked from the
    Meridian tree while runtime code resolved through
    `/root/enhengclaw_live_runner/repo/src`, so the service environment still
    contains a legacy Python/config-resolution surface.
- Rollback:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover/rollback`
  - Initial rollback stopped and disabled Meridian timers but services remained
    in failed state from the failed runs.
  - `systemctl reset-failed` was then applied to restore inactive/dead service
    state.
  - Final artifact `rollback_summary_after_reset_failed.json` recorded:
    - `rollback_passed=true`
    - `timers_zero=true`
    - legacy timers inactive/disabled
    - Meridian timers inactive/disabled
    - legacy services inactive
    - Meridian services inactive/dead
    - `open_order_count=0`
  - Final readback confirmed `0 timers listed`, all related services
    inactive/dead, and open orders zero.
- Decision boundary:
  - Current state is `CUTOVER_ATTEMPT_ROLLED_BACK`.
  - Do not attempt another timer handoff until a separate fix window addresses:
    Meridian service Python path / config resolution, the paused-vs-no-live-delta
    acceptance model, and the Meridian artifact polling rule.

Draft apply window scope:

- This is a future, operator-approved server window only. Do not run these
  steps as part of the local compatibility branch.
- Local-only review package:
  `scripts/remote_runner_service_migration/`.
  It contains disabled Meridian unit drafts, a Meridian runner config draft,
  a read-only precheck script, a disabled-unit verifier, a dry-run guarded
  rollback script, a review checklist, `REVIEW_SUMMARY.md`, and
  `PACKAGE_SHA256SUMS.txt`. Creating this package does not change remote state.
- The apply window may create a parallel Meridian runner tree and disabled
  Meridian systemd units, then perform a controlled timer cutover only after
  explicit approval.
- The apply window must not change strategy authorization, live/not-live
  intent, Binance permissions, accepted evidence, or `PROJECT_STATE.md`.
- The apply window must be abandoned if the fresh read-only precheck no longer
  matches the expected timer and runner state.

Draft apply stages:

1. Capture fresh rollback evidence, read-only.
   - Use one serialized SSH session to avoid `Exceeded MaxStartups`.
   - Capture:
     - `date -u`, `hostname`, `id -un`, and `uname -a`
     - `systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'`
     - `systemctl list-unit-files --all | grep -E 'enhengclaw|meridian'`
     - `systemctl show` and `systemctl cat` for all legacy and Meridian
       candidate units
     - `stat` for `/root/enhengclaw_live_runner`,
       `/root/enhengclaw_live_runner/repo`,
       `/root/enhengclaw_live_runner/bin/with-live-env`, and
       `/root/enhengclaw_live_runner/venv/bin/python`
     - the latest supervisor, health-monitor, core-loop, and delta-execution
       artifact directories
   - Abort if any legacy service is currently `active` rather than waiting
     between oneshot runs.
   - Abort if any Meridian timer or service already exists unexpectedly.

2. Generate remote apply artifacts before installing them.
   - Render the Meridian unit files from the freshly captured remote legacy
     unit files, not from stale checked-in examples.
   - The local review package provides the first draft artifacts:
     - `systemd/meridian-alpha-mainnet-supervisor-live.service`
     - `systemd/meridian-alpha-mainnet-supervisor-live.timer`
     - `systemd/meridian-alpha-mainnet-health-monitor.service`
     - `systemd/meridian-alpha-mainnet-health-monitor.timer`
     - `config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`
   - Replace only the naming and root-path surfaces needed for the parallel
     migration:
     - `enhengclaw-mainnet-...` -> `meridian-alpha-mainnet-...`
     - `/root/enhengclaw_live_runner` -> `/root/meridian_alpha_live_runner`
   - Keep the same current strategy config unless a separate strategy window
     explicitly changes it.
   - Record SHA-256 hashes for all rendered unit files before upload.

3. Stage the parallel Meridian runner tree.
   - Create `/root/meridian_alpha_live_runner` only inside the approved apply
     window.
   - Stage `repo`, `venv`, and `bin/with-live-env` as a parallel copy or
     reproducible rebuild from the legacy runner.
   - Do not move or delete `/root/enhengclaw_live_runner`.
   - Do not hand-edit secrets. Secret handling must be one of these explicit
     choices before apply:
     - keep the new wrapper pointed at the existing reviewed secret source for
       this naming window, or
     - provision a reviewed Meridian secret path in a separate secrets window.
   - The default recommendation for this window is to avoid a secrets
     migration and prove only runner/service naming.

4. Install Meridian units disabled.
   - Install:
     - `meridian-alpha-mainnet-supervisor-live.service`
     - `meridian-alpha-mainnet-supervisor-live.timer`
     - `meridian-alpha-mainnet-health-monitor.service`
     - `meridian-alpha-mainnet-health-monitor.timer`
   - Run `systemctl daemon-reload`.
   - Run `systemd-analyze verify` on the new unit files.
   - The package verifier command shape is:
     `bash verify_disabled_meridian_units.sh --unit-dir /etc/systemd/system --expect-installed`.
   - Confirm all Meridian timers remain disabled/inactive.
   - Confirm legacy timers are still the only active timers.

5. Run disabled proof checks before cutover.
   - Confirm the Meridian service commands resolve to
     `/root/meridian_alpha_live_runner`.
   - Run a no-order or read-only observation from the Meridian runner before
     enabling any Meridian live-capable supervisor timer.
   - Store the resulting proof artifact under the Meridian runner tree and
     label it as a migration proof, not accepted evidence.

6. Cut over timers only with explicit operator approval.
   - Do not run the legacy and Meridian live-capable supervisor timers
     concurrently.
   - At a quiet point between oneshot runs:
     - stop and disable the legacy supervisor and health timers
     - enable the Meridian health timer
     - enable the Meridian supervisor timer
   - Wait for one supervisor cycle and one health-monitor cycle.
   - If either cycle fails, immediately enter rollback.

7. Post-cutover verification.
   - `systemctl list-timers` must show the Meridian supervisor and health
     timers active/waiting.
   - Legacy supervisor and health timers must be inactive/disabled.
   - Fresh artifacts must be written under
     `/root/meridian_alpha_live_runner/repo/artifacts/...`.
   - Health monitor output must reference
     `meridian-alpha-mainnet-supervisor-live.timer` as the intended timer.
   - No `PROJECT_STATE.md` accepted evidence path is updated from this window.

Rollback checklist:

- Trigger rollback immediately if:
  - Meridian unit verification fails
  - Meridian runner cannot load its environment without ad hoc secret edits
  - Meridian proof artifacts are missing or malformed
  - post-cutover supervisor or health-monitor cycle fails
  - both legacy and Meridian live-capable supervisor timers become active
  - any unexpected order/fill/open-order signal appears during verification
- Capture before rollback:
  - `systemctl status` and `journalctl -u ... -n 80` for Meridian units
  - latest Meridian proof artifact paths
  - current `systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'`
- Rollback actions:
  - stop `meridian-alpha-mainnet-supervisor-live.timer`
  - stop `meridian-alpha-mainnet-health-monitor.timer`
  - disable both Meridian timers
  - restore legacy unit files from the captured rollback copy if any legacy
    unit file was modified
  - run `systemctl daemon-reload`
  - enable and start the previous legacy timers:
    `enhengclaw-mainnet-health-monitor.timer` and
    `enhengclaw-mainnet-supervisor-live.timer`
- Rollback verification:
  - legacy supervisor and health timers are active/waiting
  - Meridian timers are inactive/disabled
  - no duplicate live-capable supervisor timer is active
  - latest legacy health monitor is fresh and reports the intended legacy timer
- Cleanup boundary:
  - keep `/root/meridian_alpha_live_runner` for forensic inspection until the
    operator approves cleanup
  - do not delete legacy runner evidence
  - do not move secrets
  - do not update accepted evidence after a rollback

High-level migration steps:

1. First capture current timer state, unit files, remote repo status, live-delta
   armed state, latest supervisor artifact, latest health artifact, and open
   orders using read-only commands.
2. Create a parallel `/root/meridian_alpha_live_runner` tree only after the
   legacy runner is confirmed reachable and backed up.
3. Install parallel disabled systemd units:
   - `meridian-alpha-mainnet-supervisor-live.service`
   - `meridian-alpha-mainnet-supervisor-live.timer`
   - `meridian-alpha-mainnet-health-monitor.service`
   - `meridian-alpha-mainnet-health-monitor.timer`
4. Run `systemd-analyze verify` on the new unit files while they are disabled.
5. Run a no-order/read-only observation from the Meridian runner before enabling
   any live-capable timer.
6. Enable the Meridian health timer first, then the Meridian supervisor timer,
   only after explicit operator approval for that server window.
7. Disable the legacy timer only after the Meridian timer writes fresh healthy
   artifacts and the health monitor observes the intended timer name.

Success criteria:

- Fresh remote artifacts prove which timer is active.
- Health monitor config and `systemd_timer_name` agree with the enabled timer.
- No-order or live-capable state is intentionally selected and recorded.
- No service rename is treated as live authorization by itself.

Rollback:

- Stop and disable Meridian timers.
- Re-enable the legacy timer units from captured unit files.
- Keep both runner trees until a later cleanup; do not move secrets by ad hoc
  shell edits.

### Migration Order

1. Keep this compatibility branch green locally.
2. Register and prove Windows scheduled tasks in parallel.
3. Clone and prove WSL OpenClaw workspaces in parallel.
4. Explicit Meridian LocalAppData routing proof and explicit trust-root metadata
   repair are complete for the scheduled research provisioning producer.
5. ProgramData Meridian trust-root apply proof and explicit LocalAppData plus
   ProgramData E2E proof are complete as disabled/new proof surfaces only; they
   are not consumed by default paths or accepted evidence.
6. Only then plan a separate remote runner/service migration window.

Remote service migration should not be bundled with the local scheduled-task
migration. The local surfaces are mostly naming and evidence-routing work; the
remote surface can change live timer behavior and needs its own read-only audit,
approval, and rollback plan.

### Meridian Timer Handoff Fix Window

Status: `PATH_CONFIG_FIX_APPLIED_AND_LATER_HANDOFF_COMPLETED`.

Local artifacts:

- `docs/MERIDIAN_TIMER_HANDOFF_FIX_WINDOW.md`
- `scripts/remote_runner_service_fix_window/`
- `scripts/remote_runner_service_fix_window/PACKAGE_SHA256SUMS.txt`

This window addresses the two blockers from the rolled-back
`20260531T111635Z-meridian-timer-handoff-cutover` attempt:

- Meridian service Python path and config resolution must be explicit. The new
  service drop-ins clear relative `ExecStart` commands, invoke scripts and
  config by absolute Meridian paths, and force
  `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src` for the child Python
  process after `with-live-env`.
- Handoff acceptance must use an explicit no-live-delta observation state for
  the Meridian runner: `operator_paused=false`, `live_delta_armed=false`,
  auto-rearm disabled, clean supervisor and health runs, and zero order/fill
  side effects. Requiring `operator_paused=true` for the Meridian proof cycle is
  invalid because the supervisor treats operator pause as a hard blocker.

The local fix package itself did not change remote state. A later approved
remote fix apply installed only the Meridian handoff-observation config and
two service path drop-ins. Do not attempt cutover again until a fresh
serialized read-only precheck passes after this fix.

Remote fix apply result:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_path_fix_apply/20260531T115517Z-meridian-service-path-fix-apply`
- Summary artifact:
  `fix_apply_summary.json`
- Result:
  - `fix_apply_passed=true`
  - package hash verification passed
  - static and installed drop-in verifiers passed
  - `systemctl daemon-reload` completed
  - handoff-observation config installed under
    `/root/meridian_alpha_live_runner/repo/config/live_trading`
  - service drop-ins installed for the Meridian supervisor and health services
  - read-only path probe proved `config_module_file` and `config_root` resolve
    under `/root/meridian_alpha_live_runner/repo`
  - final readback listed `0 timers`
  - related legacy and Meridian services were inactive/dead
  - Meridian timers remained disabled
  - `cutover_attempted=false`
  - `accepted_evidence_updated=false`
  - `live_delta_armed_or_order_action_attempted=false`

This remote fix apply did not enable or start any timer. The fresh serialized
read-only precheck after the fix has now been run, still without cutover.

Post-fix serialized read-only precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T120447Z-post-fix-readonly-precheck`
- Acceptance artifact:
  `post_fix_precheck_acceptance.json`
- Result:
  - `precheck_passed=false`
  - false check:
    `meridian_no_live_delta_observation_state_ready=false`
  - fix summary input passed
  - installed drop-in verifier passed
  - Python path/config probe passed
  - `0 timers listed`
  - no related legacy or Meridian service was active
  - legacy and Meridian timers remained disabled
  - account and open-order GET reads succeeded
  - `open_order_count=0`
  - `open_position_count=11`
  - no order, cancel, or order-test call was made
  - `accepted_evidence_not_updated=true`
  - `no_cutover_performed=true`
- Interpretation:
  - path/config resolution is fixed
  - account safety and timer quiet gates are green
  - the remaining no-go is semantic/operator state only:
    Meridian is still `paused=true`, `live_delta_armed=false`
  - this required a separate observation-state preparation window to record
    Meridian `operator_paused=false` while keeping `live_delta_armed=false`,
    without enabling or starting timers

Observation-state preparation:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T121405Z-meridian-unpaused-disarmed-observation-state`
- Acceptance artifact:
  `observation_state_prep_acceptance.json`
- Result:
  - `observation_state_ready=true`
  - false checks: `[]`
  - only the Meridian runner sqlite state was changed
  - legacy sqlite state was unchanged
  - Meridian `resume` action recorded at `2026-05-31T12:20:58.369994Z`
  - Meridian `disarm-live-delta` action recorded at
    `2026-05-31T12:20:58.377227Z`
  - Meridian `paused=false`
  - Meridian `live_delta_armed=false`
  - latest Meridian live-delta action is `disarm-live-delta`
  - timer list remained `0 timers listed` before and after
  - related legacy and Meridian services remained inactive/dead
  - legacy and Meridian timers remained disabled
  - account/open-order GET reads succeeded
  - `open_order_count=0`
  - `open_position_count=11`
  - no order, cancel, or order-test call was made
  - `accepted_evidence_not_updated=true`
  - `no_cutover_performed=true`
- Interpretation:
  - the no-live-delta observation state is now prepared
  - the next step was a fresh serialized read-only precheck after the state
    change, still without timer cutover

Post-observation-state serialized read-only precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T123155Z-post-observation-state-readonly-precheck`
- Acceptance artifact:
  `post_observation_state_precheck_acceptance.json`
- Result:
  - `precheck_passed=true`
  - false checks: `[]`
  - fix apply summary input passed
  - observation-state prep input passed
  - installed drop-in verifier passed
  - Python path/config probe passed
  - `config_module_file` and `config_root` resolved under
    `/root/meridian_alpha_live_runner/repo`
  - `0 timers listed`
  - no related legacy or Meridian service was active
  - legacy and Meridian timers remained disabled
  - Meridian services remained inactive/dead
  - Meridian service `ExecStart` used `/usr/bin/env`,
    `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src`, and the absolute
    Meridian handoff-observation config path
  - legacy rollback state remained `paused=true`, `live_delta_armed=false`
  - Meridian observation state was `paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action was `disarm-live-delta`
  - account and open-order GET reads succeeded
  - `open_order_count=0`
  - `open_position_count=11`
  - no order, cancel, or order-test call was made
  - `accepted_evidence_not_updated=true`
  - `no_cutover_performed=true`
- Interpretation:
  - the remote handoff precheck is now green for the observation-state design
  - this remains a proof-only state; no Meridian timer was enabled or started

Operator-approved apply window decision:

- Decision artifact:
  `docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md`
- Current decision timestamp:
  `2026-05-31T15:48:23Z`
- Current status:
  `HANDOFF_COMPLETED_POST_HEALTH_FIX`
- Current approval status:
  `approval_received_execute_message_2026-05-31T15:48Z`
- Current apply status:
  `handoff_completed_meridian_timers_active`
- Decision basis:
  - fixed Meridian path/config resolution
  - observation-state preparation passed
  - post-observation-reprep read-only precheck passed with false checks `[]`
- Last attempted apply semantics:
  - legacy runner remains the paused/disarmed rollback baseline
  - Meridian runner uses `operator_paused=false`, `live_delta_armed=false`
  - Meridian handoff-observation config keeps auto-rearm disabled
  - a future apply window may enable only the Meridian health timer and
    Meridian live supervisor timer
  - the window still does not authorize live delta, order submission, order
    cancellation, order-test calls, strategy/risk/capital/secrets changes,
    accepted-evidence updates, or formal readiness claims
- Boundary:
  - the first decision record is historical for the position-reference-blocked
    rolled-back attempt
  - the latest post-reference apply rolled back after the health monitor
    alerted on superseded blocked Meridian runs in its recent-run window
  - another apply requires a separate health-alert triage/fix window and a
    fresh read-only precheck

Previous operator-approved apply attempt:

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply`
- Apply-start artifact:
  `handoff_apply_start_summary.json`
- Poll artifact:
  `polls/20260531T124921Z-poll/cycle_poll_summary.json`
- Rollback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply/rollback/20260531T125103Z-rollback-supervisor-blocked`
- Rollback artifact:
  `rollback_summary.json`
- Final readback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply/final_readback/20260531T125414Z-readonly-final-readback`
- Result:
  - `prestate_passed=true`
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - final readback listed `0 timers`
  - final readback passed with false checks: `[]`
  - all related legacy and Meridian services were inactive/dead after rollback
  - legacy remained `paused=true`, `live_delta_armed=false`
  - Meridian rollback kill-switch restored `paused=true`,
    `live_delta_armed=false`
  - `open_order_count=0`
  - `open_position_count=11`
  - `accepted_evidence_updated=false`
- Failure reason:
  - the Meridian supervisor timer fired and wrote:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T124746329564Z-mainnet-live-supervisor/run_summary.json`
  - the supervisor exited `mainnet_live_supervisor_blocked`
  - blockers included missing Meridian position reference plus 11
    `unexpected_live_position:*` entries
  - no order, fill, cancellation, or order-test side effect was observed
- Historical next boundary at that point:
  - another handoff attempt was no-go at that point until the Meridian runner
    had a reviewed position-reference migration or equivalent Meridian-root
    reference for the existing live-position inventory

Meridian position-reference fix window:

- Design artifact:
  `docs/MERIDIAN_POSITION_REFERENCE_FIX_WINDOW.md`
- Current status:
  `APPLY_PASSED_POSITION_MONITOR_VERIFIED`
- Read-only proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T130527Z-position-reference-readonly-inventory`
- Inventory result:
  - no timer enable/start was attempted
  - no service start was attempted
  - no reference copy or generation was attempted
  - no order, cancel, or order-test path was attempted
  - `systemd_timers.txt` listed `0 timers`
  - legacy valid reference candidates: `128`
  - legacy monitor-selected reference:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution`
  - selected legacy reference kind: `mainnet_delta_execution`
  - selected legacy reference position count: `11`
  - selected legacy reference matched the Meridian apply-attempt 11 live
    positions exactly
  - Meridian valid reference candidates: `0`
  - Meridian latest position monitor remained blocked by the missing-reference
    surface
- Decision:
  - the separate position-reference apply window has now passed
  - another timer handoff remains no-go until a fresh serialized read-only
    handoff precheck is green after the new Meridian reference is present
- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T133219Z-meridian-equivalent-genesis-apply`
- Acceptance artifact:
  `position_reference_fix_acceptance.json`
- Apply result:
  - `status=passed`
  - false checks: `[]`
  - rollback attempted: `false`
  - precheck legacy-reference monitor passed
  - explicit Meridian reference monitor passed
  - implicit Meridian-root reference monitor passed
  - post-verify timers remained zero
  - `PROJECT_STATE.md` was unchanged on the remote runner
  - no timer handoff, timer enable/start, service start, live-delta arm,
    order submit/cancel/test, or accepted-evidence update was attempted
- Created Meridian reference:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`
  - `run_summary.json.status=mainnet_position_genesis_snapshot`
  - `position_count=11`
  - source reference:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution`
- Post-reference read-only handoff precheck:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135219Z-post-reference-readonly-precheck`
  - acceptance artifact:
    `post_reference_precheck_acceptance.json`
  - result:
    `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks:
    `["meridian_operator_unpaused_for_proof"]`
  - implicit Meridian position monitor passed and selected the new Meridian
    reference
  - `open_order_count=0`
  - `open_position_count=11`
  - path/config probe passed under the Meridian repo
  - all related units were inactive
  - timer list remained `0 timers listed`
  - no cutover, timer enable/start, service start, order submit/cancel/test,
    live-delta arm, or accepted-evidence update was attempted
  - current blocker:
    Meridian remains `operator_paused=true`, `live_delta_armed=false` after
    the rollback kill-switch
  - next boundary:
    a separate observation-state preparation must restore Meridian
    `operator_paused=false`, `live_delta_armed=false`; only then rerun a fresh
    serialized read-only handoff precheck
- Fresh rerun:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135612Z-post-reference-readonly-precheck-rerun`
  - acceptance artifact:
    `post_reference_precheck_acceptance.json`
  - result:
    `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks:
    `["meridian_operator_unpaused_for_proof"]`
  - implicit Meridian position monitor passed and selected the new Meridian
    reference
  - `open_order_count=0`
  - `open_position_count=11`
  - all related units were inactive
  - timer list remained `0 timers listed`
  - no cutover, timer enable/start, service start, live-delta arm, order path,
    or accepted-evidence update was attempted
- Observation-state re-prep:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T135943Z-post-reference-observation-state-reprep`
  - acceptance artifact:
    `observation_state_reprep_acceptance.json`
  - result:
    `status=passed`
  - false checks: `[]`
  - Meridian moved from `operator_paused=true`, `live_delta_armed=false` to
    `operator_paused=false`, `live_delta_armed=false`
  - no cutover, timer enable/start, service start, live-delta arm, order path,
    or accepted-evidence update was attempted
- Post-observation-reprep read-only handoff precheck:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T140218Z-post-observation-reprep-readonly-precheck`
  - acceptance artifact:
    `post_observation_reprep_precheck_acceptance.json`
  - result:
    `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - Meridian `operator_paused=false`
  - Meridian `live_delta_armed=false`
  - implicit Meridian position monitor passed and selected the new Meridian
    reference
  - `open_order_count=0`
  - `open_position_count=11`
  - all related units were inactive
  - timer list remained `0 timers listed`
  - no cutover, timer enable/start, service start, live-delta arm, order path,
    or accepted-evidence update was attempted
  - next boundary:
    a separate operator-approved apply window is required before any Meridian
    timer handoff

Latest post-reference operator-approved apply attempt:

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T140855Z-meridian-timer-handoff-post-reference-apply`
- Final artifacts:
  - `handoff_final_summary.json`
  - `rollback_final_readback_summary.json`
  - `latest_cycle_poll_summary.json`
- Result:
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - `accepted_evidence_updated=false`
  - `orders_submitted=0`
- Supervisor cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T140905083386Z-mainnet-live-supervisor`
  - status: `mainnet_live_supervisor_completed`
  - blockers: `[]`
  - `orders_submitted=0`
  - `fill_count=0`
  - `live_delta_authorized=false`
- Health cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T141431602922Z-mainnet-health-monitor`
  - status: `mainnet_health_monitor_alerted`
  - `critical_alert_count=11`
  - auto-rearm gate: `skipped_disabled`
  - disarm record: `status=applied`
- Rollback readback:
  - timer list returned to `0 timers listed`
  - `active_units=[]`
  - `enabled_units=[]`
  - Meridian kill-switch restored `operator_paused=true`
  - Meridian `live_delta_armed=false`
  - `open_order_count=0`
  - `open_position_count=11`
- Interpretation:
  - the post-reference supervisor cycle itself was clean and no-order
  - health alerted because its recent-run window included older blocked
    Meridian runs `20260531T124746329564Z` and `20260531T112707172721Z`
  - next boundary:
    a separate health-alert triage/fix window is required before any further
    Meridian timer handoff

Health-alert triage/fix window:

- Local artifact:
  `docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`
- Local package amended:
  `scripts/remote_runner_service_fix_window/`
- Remote apply proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_health_alert_fix_apply/20260531T151439Z-amended-handoff-observation-config-apply`
- Root interpretation:
  - the health monitor behaved according to its configured
    `recent_run_count=3` contract
  - the two older blocked supervisor runs were superseded migration proof
    artifacts from before the position-reference and observation-state fixes
  - the handoff proof contract verifies one timer-created supervisor cycle and
    one health cycle
- Fix decision:
  - default live timer configs keep their 3-run health window
  - only the Meridian handoff-observation proof config now uses
    `mainnet_health_monitor.recent_run_count=1`
  - `no_order_expected=true` and `auto_rearm_live_delta=false` remain in force
- Remote apply result:
  - `status=passed`
  - false checks: `[]`
  - installed config sha256:
    `11c5314691b10795ff40ec573c67b4e7559e76af1ba36f83ba4e554ad2ca3d1c`
  - `0 timers listed`
  - no active or enabled related units
  - Meridian health service reset to `loaded/inactive/dead/static`
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted
- Boundary:
  - do not attempt another handoff until a fresh serialized read-only precheck
    passes after this remote health-fix apply
- Post-health-fix read-only handoff precheck:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`
  - acceptance artifact:
    `post_health_fix_precheck_acceptance.json`
  - result:
    `status=no_go_readonly_precheck_failed`
  - false checks:
    `["meridian_operator_unpaused_for_proof"]`
  - Meridian `operator_paused=true`, `live_delta_armed=false`
  - implicit Meridian position monitor passed with `open_order_count=0` and
    `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted
- Post-health-fix observation-state re-prep:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`
  - acceptance artifact:
    `observation_state_reprep_acceptance.json`
  - result:
    `status=passed`
  - false checks: `[]`
  - Meridian moved from `operator_paused=true`, `live_delta_armed=false` to
    `operator_paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action: `disarm-live-delta`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted
- Current boundary:
  - run a new fresh serialized read-only handoff precheck after this re-prep
    before any operator-approved timer handoff apply decision
- Post-reprep read-only handoff precheck:
  - proof root:
    `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`
  - acceptance artifact:
    `post_health_fix_reprep_precheck_acceptance.json`
  - result:
    `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - Meridian `operator_paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action: `disarm-live-delta`
  - implicit Meridian position monitor passed with `open_order_count=0` and
    `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted
- Historical boundary before apply:
  - this green precheck was only an input to a separate operator-approved
    handoff apply window; it did not authorize or perform timer ownership
    handoff by itself

Post-health-fix operator-approved handoff apply:

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T154823Z-meridian-timer-handoff-post-health-fix-apply`
- Final apply artifact:
  `handoff_final_summary.json`
- Acceptance artifact:
  `handoff_acceptance.json`
- Final position monitor artifact:
  `final_position_monitor.parsed.json`
- Result:
  - `status=handoff_completed`
  - `handoff_applied=true`
  - `verification_passed=true`
  - `rollback_required=false`
  - `rollback_passed=null`
  - false checks: `[]`
  - supervisor status: `mainnet_live_supervisor_completed`
  - health status: `mainnet_health_monitor_passed`
  - health critical alerts: `0`
  - `orders_submitted=0`
  - `fill_count=0`
  - `open_order_count=0`
  - `open_position_count=11`
  - `accepted_evidence_updated=false`
- Timer-created cycles:
  - supervisor:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T154828478358Z-mainnet-live-supervisor`
  - health:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T155334937841Z-mainnet-health-monitor`
- Final systemd readback:
  - Meridian supervisor timer: `enabled` / `active`
  - Meridian health timer: `enabled` / `active`
  - legacy supervisor timer: `disabled` / `inactive`
  - legacy health timer: `disabled` / `inactive`
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed exactly the two Meridian timers
- Boundary:
  - this is the remote timer ownership handoff only
  - no live-delta arm, order submit/cancel/test, strategy/risk/capital/secrets
    change, accepted-evidence update, `PROJECT_STATE.md` readiness update, or
    formal Stage 4/live-trading approval was attempted
  - next migration work should be a post-handoff steady-state observation
    window and retained evidence review, not another handoff attempt

Post-handoff live-delta authorization window:

- Local artifact:
  `docs/MERIDIAN_LIVE_DELTA_AUTHORIZATION_WINDOW.md`
- First proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_live_delta_authorization/20260531T161114Z-operator-approved-live-delta-arm`
  - result: `no_go_precheck_failed`
  - no state change, drop-in install, arm, or order path was attempted
  - false check came from a proof-driver zero-preservation bug while the
    position monitor itself reported `open_order_count=0`
- Rerun proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_live_delta_authorization/20260531T161353Z-operator-approved-live-delta-arm-rerun`
- Precheck:
  - `status=passed`
  - false checks: `[]`
  - position monitor passed with `open_order_count=0` and
    `open_position_count=11`
- Apply:
  - installed reversible live-capable `20-meridian-live-delta-config.conf`
    drop-ins for the Meridian supervisor and health services
  - recorded `arm-live-delta`
  - waited for timer-created cycles; no manual service start was used
- Live-delta supervisor result:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T161938384510Z-mainnet-live-supervisor`
  - `status=mainnet_live_supervisor_completed`
  - blockers: `[]`
  - `live_delta_armed_at_start=true`
  - `live_delta_authorized=true`
  - execution stage: `entry_second`
  - `orders_submitted=4`
  - `fill_count=4`
- Live-capable health result:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T162417788675Z-mainnet-health-monitor`
  - `status=mainnet_health_monitor_passed`
  - `critical_alert_count=0`
  - `no_order_expected=false`
  - `live_delta_armed_after=true`
- Fail-closed rollback:
  - proof-driver check `health_timer_name_meridian` failed because the driver
    expected the timer name in the wrong health-summary field
  - the driver recorded `disarm-live-delta`, removed the live-capable 20-dropins,
    and returned services to the handoff-observation config
  - final state is `live_delta_armed=false`
- Post-rollback stabilization:
  - the first restored no-order health tick alerted because it saw the prior
    live-delta supervisor under `no_order_expected=true`
  - a later no-order supervisor completed with zero orders/fills, and the next
    health tick passed with `critical_alert_count=0`
  - final read-only position monitor:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T164219540237Z-mainnet-position-monitor`
    passed with `open_order_count=0`, `open_position_count=11`, blockers `[]`
- Boundary:
  - this window did execute one live-delta cycle and filled 4 `entry_second`
    orders
  - it did not leave live delta durably armed
  - do not re-arm without a separate post-entry-second review of the live
    delta execution artifact, health summary shape, position drift, and the
    proof-driver check bug
