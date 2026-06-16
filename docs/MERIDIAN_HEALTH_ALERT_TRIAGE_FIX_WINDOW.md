# Meridian Health-Alert Triage/Fix Window

Current status: `POST_FIX_HANDOFF_COMPLETED`

This is a separate health-alert triage/fix window for the rolled-back
post-reference Meridian timer handoff attempt. It does not authorize timer
handoff, timer enable/start, service start, live delta, order submission,
order cancellation, order-test calls, accepted-evidence updates, or formal
readiness claims.

A later, separate operator-approved apply window used this fixed proof config
and completed the Meridian timer handoff. That later apply outcome is recorded
below for continuity; it does not expand the scope of this health-fix window.

## Scope

- Target host: `root@203.0.113.10`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Latest rolled-back handoff proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T140855Z-meridian-timer-handoff-post-reference-apply`
- Local package being amended:
  `scripts/remote_runner_service_fix_window/`

## Trigger

The post-reference apply enabled the two Meridian timers and produced a clean
timer-created supervisor cycle:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T140905083386Z-mainnet-live-supervisor`

That supervisor cycle reported:

- `status=mainnet_live_supervisor_completed`
- blockers: `[]`
- `orders_submitted=0`
- `fill_count=0`
- `live_delta_authorized=false`
- `live_delta_armed_at_start=false`
- `live_delta_armed_at_finish=false`

The health monitor then alerted:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T141431602922Z-mainnet-health-monitor`

The alerting health cycle reported:

- `status=mainnet_health_monitor_alerted`
- `critical_alert_count=11`
- `orders_submitted=0`
- `fill_count=0`
- `live_delta_armed_after=false`
- auto-rearm gate: `skipped_disabled`
- disarm record: `status=applied`

Rollback completed with false checks `[]`, `0 timers listed`, no active or
enabled related units, Meridian `operator_paused=true`,
`live_delta_armed=false`, open orders zero, and the same 11 open positions.

## Root Cause

This was not a new position-reference failure. The health monitor was following
its configured contract:

- `mainnet_health_monitor.recent_run_count=3`
- `_load_recent_supervisor_runs(...)` loads the latest N supervisor
  `run_summary.json` files from the same artifact parent.
- `_artifact_alerts(...)` then evaluates every loaded supervisor run.

During a migration handoff proof, the latest three Meridian supervisor runs
were mixed across different proof epochs:

1. `20260531T140905083386Z`: post-reference, completed, no-order/disarmed.
2. `20260531T124746329564Z`: pre-reference, blocked on missing Meridian
   position reference and 11 unexpected live positions.
3. `20260531T112707172721Z`: earlier proof, blocked on `operator_paused`.

The 11 critical alerts came from the two superseded blocked runs, not from the
post-reference supervisor cycle.

## Fix Decision

Keep the default health monitor logic and the default live timer configs
unchanged. They should continue to use a 3-run health window unless a separate
live-health policy window changes that contract.

For the Meridian handoff-observation proof config only, align the health window
with the handoff verification contract:

- The handoff verifies one timer-created Meridian supervisor cycle and one
  timer-created Meridian health-monitor cycle.
- The handoff config already uses `no_order_expected=true` and
  `auto_rearm_live_delta=false`.
- The handoff config now uses proof-only `recent_run_count=1`.

This prevents superseded blocked migration proof runs from contaminating the
post-fix handoff proof while retaining all latest-cycle safety checks:

- live delta must remain disarmed
- no live-delta execution may be requested
- orders and fills must remain zero
- open orders must remain zero
- position monitor / account reconcile must pass
- core loop must complete
- daily PnL and margin gates must remain inert/passed
- systemd timer status must be active for the intended Meridian timer

## Local Changes

Changed:

- `scripts/remote_runner_service_fix_window/config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`
  - `mainnet_health_monitor.recent_run_count: 1`
- `scripts/remote_runner_service_fix_window/README.md`
- `scripts/remote_runner_service_fix_window/CHECKLIST.md`
- `scripts/remote_runner_service_fix_window/REVIEW_SUMMARY.md`
- `scripts/remote_runner_service_fix_window/PACKAGE_SHA256SUMS.txt`
- `tests/test_remote_runner_service_fix_window.py`
- `tests/test_hv_balanced_mainnet_health_monitor.py`

The local unit test
`test_handoff_observation_can_scope_to_latest_clean_supervisor_run` proves that
with `recent_run_count=1`, a clean latest supervisor run can pass even when two
older blocked supervisor artifacts remain in the same artifact parent.

## Read-Only Remote Confirmation

Read-only confirmation after this local triage/fix window:

- The latest handoff proof root still exists.
- `handoff_final_summary.json` reports:
  - `status=rolled_back_after_health_alert`
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - `health_status=mainnet_health_monitor_alerted`
  - `health_critical_alert_count=11`
  - `orders_submitted=0`
  - `accepted_evidence_updated=false`
- `systemctl list-timers --all 'enhengclaw-mainnet*'
  'meridian-alpha-mainnet*'` listed `0 timers`.
- Meridian timer units were `loaded/inactive/dead/disabled`.
- Meridian supervisor service was `loaded/inactive/dead/static`.
- Meridian health service remained `loaded/failed/failed/static` from the
  alert exit. It was not active, and it was not reset in this local/read-only
  window.

## Remote Apply Boundary

A future remote health fix apply window may install only the amended
handoff-observation config under the Meridian repo config directory. It may
run read-only path/config probes and disabled unit verifiers.

It may also run `systemctl reset-failed` for the Meridian health service after
capturing evidence, while timers remain disabled, so the next precheck can
verify inactive/dead service state without starting anything.

It must not:

- enable or start Meridian timers
- enable or start legacy timers
- start Meridian services
- arm live delta
- submit, cancel, or test orders
- change strategy, capital, Binance permissions, or secrets
- update `PROJECT_STATE.md`
- update accepted evidence or formal readiness claims

## Remote Apply Outcome

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_health_alert_fix_apply/20260531T151439Z-amended-handoff-observation-config-apply`

Primary artifact:

`health_fix_apply_summary.json`

Result:

- `status=passed`
- false checks: `[]`
- installed target config:
  `/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`
- staged and installed config sha256:
  `11c5314691b10795ff40ec573c67b4e7559e76af1ba36f83ba4e554ad2ca3d1c`
- previous target config sha256:
  `a5871097e5f5e3069922a8579dbbab8532f0b9c9624f0bddb117ae3f4661dbdb`
- checks:
  - `staged_config_installed=true`
  - `target_recent_run_count_1=true`
  - `target_auto_rearm_false=true`
  - `target_no_order_expected_true=true`
  - `timers_zero_after=true`
  - `no_active_related_units_after=true`
  - `no_enabled_related_units_after=true`
  - `meridian_health_service_not_failed_after_reset=true`
  - `no_handoff_or_order_paths_attempted=true`
- Pre-state:
  - `0 timers listed`
  - no active or enabled related units
  - Meridian health service was `loaded/failed/failed/static` with
    `ExecMainStatus=2`
- Apply actions:
  - copied the amended handoff-observation config into the Meridian repo
  - ran `systemctl reset-failed meridian-alpha-mainnet-health-monitor.service`
- Post-state:
  - `0 timers listed`
  - no active or enabled related units
  - Meridian health service is `loaded/inactive/dead/static`,
    `Result=success`, `ExecMainStatus=0`
- Boundary:
  - `handoff_attempted=false`
  - `timer_enable_start_attempted=false`
  - `service_start_attempted=false`
  - `live_delta_arm_attempted=false`
  - `order_submit_cancel_test_attempted=false`
  - `accepted_evidence_update_attempted=false`

## Future Handoff Boundary

Before another Meridian timer handoff attempt:

1. The fresh serialized remote read-only handoff precheck after this health-fix
   apply ran at:
   `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`
2. The precheck was no-go with exactly one false check:
   `["meridian_operator_unpaused_for_proof"]`.
3. The precheck still confirmed:
   - `0 timers listed`
   - no active related services
   - open orders zero
   - the 11 open positions still recognized by the Meridian equivalent
     genesis reference
   - Meridian `live_delta_armed=false`
   - handoff-observation `recent_run_count=1`
   - auto-rearm disabled
4. Because the only no-go was Meridian `operator_paused=true` from the rollback
   kill-switch, a separate observation-state re-prep window ran at:
   `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`
5. That re-prep window passed with false checks `[]`, moved Meridian from
   `operator_paused=true`, `live_delta_armed=false` to
   `operator_paused=false`, `live_delta_armed=false`, and left `0 timers
   listed`, no active related units, and no enabled related units.
6. The fresh serialized read-only handoff precheck after the re-prep passed at:
   `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`
7. Only a separate operator-approved handoff apply window may consider timer
   enablement. This health-fix/re-prep/precheck chain did not handoff.
8. That separate apply window later ran at:
   `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T154823Z-meridian-timer-handoff-post-health-fix-apply`
   and completed with false checks `[]`.

## Post-Fix Read-Only Precheck

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`

Acceptance artifact:

`post_health_fix_precheck_acceptance.json`

Result:

- `status=no_go_readonly_precheck_failed`
- `precheck_passed=false`
- false checks: `["meridian_operator_unpaused_for_proof"]`
- `handoff_applied=false`
- `no_cutover_performed=true`
- `read_only_state_boundary=true`
- `accepted_evidence_updated=false`
- Meridian `operator_paused=true`
- Meridian `live_delta_armed=false`
- implicit Meridian position monitor passed
- `open_order_count=0`
- `open_position_count=11`
- timer list remained `0 timers listed`
- no active related units
- no enabled related units

## Observation-State Re-Prep Outcome

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`

Acceptance artifact:

`observation_state_reprep_acceptance.json`

Result:

- `status=passed`
- false checks: `[]`
- pre-state: Meridian `operator_paused=true`, `live_delta_armed=false`
- post-state: Meridian `operator_paused=false`, `live_delta_armed=false`
- latest Meridian live-delta action: `disarm-live-delta`
- post-state timer list remained `0 timers listed`
- no active related units
- no enabled related units
- no handoff, timer enable/start, service start, live-delta arm, order
  submit/cancel/test, accepted-evidence update, or formal readiness claim was
  attempted

## Subsequent Handoff Apply Outcome

This outcome belongs to the separate operator-approved handoff apply window,
not to the health-alert fix window itself.

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T154823Z-meridian-timer-handoff-post-health-fix-apply`

Primary artifact:

`handoff_final_summary.json`

Result:

- `status=handoff_completed`
- `handoff_applied=true`
- `verification_passed=true`
- `rollback_required=false`
- false checks: `[]`
- supervisor status: `mainnet_live_supervisor_completed`
- health status: `mainnet_health_monitor_passed`
- health critical alerts: `0`
- `orders_submitted=0`
- `fill_count=0`
- final position monitor status: `passed_live_position_monitor`
- `open_order_count=0`
- `open_position_count=11`
- active and enabled units:
  - `meridian-alpha-mainnet-supervisor-live.timer`
  - `meridian-alpha-mainnet-health-monitor.timer`
- legacy supervisor and health timers remained disabled/inactive
- `accepted_evidence_updated=false`

Boundary:

- The successful handoff proves the Meridian timer ownership transition under
  the proof config after the health-alert fix.
- It does not approve live-delta arming, order submission, strategy/risk/capital
  changes, accepted-evidence updates, or formal Stage 4 readiness.

## Post-Reprep Read-Only Precheck

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`

Acceptance artifact:

`post_health_fix_reprep_precheck_acceptance.json`

Result:

- `status=passed`
- `precheck_passed=true`
- false checks: `[]`
- `handoff_applied=false`
- `no_cutover_performed=true`
- `read_only_state_boundary=true`
- `accepted_evidence_updated=false`
- Meridian `operator_paused=false`
- Meridian `live_delta_armed=false`
- latest Meridian live-delta action: `disarm-live-delta`
- implicit Meridian position monitor passed
- `open_order_count=0`
- `open_position_count=11`
- handoff-observation `recent_run_count=1`
- auto-rearm disabled
- timer list remained `0 timers listed`
- no active related units
- no enabled related units
- no handoff, timer enable/start, service start, live-delta arm, order
  submit/cancel/test, accepted-evidence update, or formal readiness claim was
  attempted
