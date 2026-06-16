# Meridian Timer Handoff Apply Decision

Current decision timestamp: `2026-05-31T15:48:23Z`

This is an operator decision record plus the subsequent apply outcome for the
Meridian timer handoff. It does not authorize another timer change by itself.

Current status: `HANDOFF_COMPLETED_POST_HEALTH_FIX`.

Current approval status: `approval_received_execute_message_2026-05-31T15:48Z`.

Current apply status: `handoff_completed_meridian_timers_active`.

The completed handoff is based on the fixed Meridian service path/config
resolution, the Meridian equivalent position reference, the health-alert
proof-config fix, the post-health-fix observation-state re-prep, and the green
post-health-fix re-prep read-only precheck. Historical `operator_paused=true`
handoff-success criteria in this file are retained only as audit history and
must not be reused.

## Latest Post-Health-Fix Apply Outcome

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
  - `accepted_evidence_updated=false`
  - `orders_submitted=0`
  - `fill_count=0`
- Timer-created Meridian supervisor cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T154828478358Z-mainnet-live-supervisor`
  - status: `mainnet_live_supervisor_completed`
  - `orders_submitted=0`
  - `fill_count=0`
- Timer-created Meridian health cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T155334937841Z-mainnet-health-monitor`
  - status: `mainnet_health_monitor_passed`
  - `critical_alert_count=0`
- Final position monitor:
  - status: `passed_live_position_monitor`
  - `open_order_count=0`
  - `open_position_count=11`
- Final systemd readback:
  - active units:
    `["meridian-alpha-mainnet-supervisor-live.timer", "meridian-alpha-mainnet-health-monitor.timer"]`
  - enabled units:
    `["meridian-alpha-mainnet-supervisor-live.timer", "meridian-alpha-mainnet-health-monitor.timer"]`
  - legacy supervisor timer: `disabled` / `inactive`
  - legacy health timer: `disabled` / `inactive`
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed exactly the two Meridian timers
- Boundary:
  - This is a timer ownership handoff proof, not formal Stage 4 readiness or
    live-trading approval.
  - No live-delta arm, order submit/cancel/test, strategy/risk/capital/secrets
    change, accepted-evidence update, or `PROJECT_STATE.md` readiness update
    was attempted.
  - The next window should be post-handoff steady-state observation and
    read-only monitoring, not another handoff attempt.

## Latest Post-Reference Apply Outcome

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T140855Z-meridian-timer-handoff-post-reference-apply`
- Final apply artifact:
  `handoff_final_summary.json`
- Final rollback readback artifact:
  `rollback_final_readback_summary.json`
- Latest cycle poll artifact:
  `latest_cycle_poll_summary.json`
- Result:
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - `accepted_evidence_updated=false`
  - `orders_submitted=0`
- Fresh Meridian supervisor cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T140905083386Z-mainnet-live-supervisor`
  - status: `mainnet_live_supervisor_completed`
  - blockers: `[]`
  - `orders_submitted=0`
  - `fill_count=0`
  - `live_delta_authorized=false`
  - `live_delta_armed_at_start=false`
  - `live_delta_armed_at_finish=false`
- Fresh Meridian health cycle:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_health_monitor/20260531T141431602922Z-mainnet-health-monitor`
  - status: `mainnet_health_monitor_alerted`
  - `critical_alert_count=11`
  - `orders_submitted=0`
  - `fill_count=0`
  - `live_delta_armed_after=false`
  - auto-rearm gate: `skipped_disabled`
  - disarm record: `status=applied`
- Health-alert interpretation:
  - The newly timer-created `20260531T140905083386Z` supervisor cycle completed
    and was no-order/disarmed.
  - The health monitor evaluated the recent supervisor window with
    `recent_run_count_required=3` and included two older blocked Meridian runs:
    `20260531T124746329564Z` and `20260531T112707172721Z`.
  - The 11 critical alerts came from those older blocked runs:
    missing Meridian position reference / unexpected live positions from the
    pre-reference attempt, plus the earlier `operator_paused` run.
  - This is therefore a health-history/alert-window blocker after a clean
    post-reference supervisor cycle, not a new position-reference failure.
- Rollback readback:
  - timer list returned to `0 timers listed`
  - `active_units=[]`
  - `enabled_units=[]`
  - Meridian rollback kill-switch restored `operator_paused=true`
  - Meridian `live_delta_armed=false`
  - `open_order_count=0`
  - `open_position_count=11`
  - position monitor still selected the Meridian equivalent genesis reference

Historical decision after this post-reference attempt:
`NO_GO_UNTIL_HEALTH_ALERT_TRIAGE_AFTER_POST_REFERENCE_HANDOFF`.

This no-go was later closed by the health-alert triage/fix window, the
post-health-fix observation-state re-prep, the green post-health-fix re-prep
read-only precheck, and the successful post-health-fix handoff apply recorded
above.

Health-alert triage/fix window:

- Local artifact:
  `docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`
- Local package amended:
  `scripts/remote_runner_service_fix_window/`
- Remote apply proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_health_alert_fix_apply/20260531T151439Z-amended-handoff-observation-config-apply`
- Remote apply result:
  - `status=passed`
  - false checks: `[]`
  - installed config sha256:
    `11c5314691b10795ff40ec573c67b4e7559e76af1ba36f83ba4e554ad2ca3d1c`
  - `target_recent_run_count_1=true`
  - `timers_zero_after=true`
  - `no_active_related_units_after=true`
  - `no_enabled_related_units_after=true`
  - Meridian health service reset from `failed` to `inactive/dead/static`
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted
- Fix decision:
  - keep default live health configs at the 3-run health window
  - narrow only the Meridian handoff-observation proof config to
    `mainnet_health_monitor.recent_run_count=1`
  - keep `no_order_expected=true` and `auto_rearm_live_delta=false`
  - require a fresh serialized read-only handoff precheck before any further
    timer handoff

Post-health-fix read-only handoff precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`
- Acceptance artifact:
  `post_health_fix_precheck_acceptance.json`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - Meridian `operator_paused=true`
  - Meridian `live_delta_armed=false`
  - implicit Meridian position monitor passed
  - `open_order_count=0`
  - `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted

Post-health-fix observation-state re-prep:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`
- Acceptance artifact:
  `observation_state_reprep_acceptance.json`
- Result:
  - `status=passed`
  - false checks: `[]`
  - pre-state: Meridian `operator_paused=true`, `live_delta_armed=false`
  - post-state: Meridian `operator_paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action: `disarm-live-delta`
  - post-state timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted

Post-health-fix re-prep read-only handoff precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`
- Acceptance artifact:
  `post_health_fix_reprep_precheck_acceptance.json`
- Result:
  - `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - Meridian `operator_paused=false`
  - Meridian `live_delta_armed=false`
  - latest Meridian live-delta action: `disarm-live-delta`
  - implicit Meridian position monitor passed
  - `open_order_count=0`
  - `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `accepted_evidence_updated=false`
  - no handoff, timer enable/start, service start, live-delta arm, order path,
    accepted-evidence update, or formal readiness claim was attempted

Historical evidence basis for this apply chain:

- Fix apply proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_path_fix_apply/20260531T115517Z-meridian-service-path-fix-apply`
- Observation-state prep proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T121405Z-meridian-unpaused-disarmed-observation-state`
- Fresh post-observation-state precheck proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T123155Z-post-observation-state-readonly-precheck`
- Acceptance artifact:
  `post_observation_state_precheck_acceptance.json`
- Result:
  - `precheck_passed=true`
  - false checks: `[]`
  - `open_order_count=0`
  - `open_position_count=11`
  - legacy rollback state remained `paused=true`, `live_delta_armed=false`
  - Meridian observation state was `paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action was `disarm-live-delta`
  - all related legacy and Meridian services were inactive/dead
  - both legacy and Meridian timer families were disabled
  - no order, cancel, or order-test call was made
  - `accepted_evidence_not_updated=true`
  - `no_cutover_performed=true`

Previous position-reference-blocked apply attempt evidence:

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
- Final apply artifact:
  `handoff_final_summary.json`
- Final readback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply/final_readback/20260531T125414Z-readonly-final-readback`
- Final readback artifact:
  `final_readback_summary.json`
- Result:
  - `prestate_passed=true`
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - final timer readback: `0 timers listed`
  - final readback passed with false checks: `[]`
  - all related legacy and Meridian services were inactive/dead after rollback
  - legacy remained `paused=true`, `live_delta_armed=false`
  - Meridian rollback kill-switch restored `paused=true`,
    `live_delta_armed=false`
  - `open_order_count=0`
  - `open_position_count=11`
  - `accepted_evidence_updated=false`
- Failure reason:
  - the Meridian supervisor timer fired and wrote a fresh Meridian supervisor
    artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T124746329564Z-mainnet-live-supervisor/run_summary.json`
  - the supervisor exited `mainnet_live_supervisor_blocked`
  - blockers included:
    `no_valid_position_reference_under:/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate`
    plus 11 `unexpected_live_position:*` blockers
  - no order, fill, cancellation, or order-test side effect was observed

## Current Decision

Recommended decision: `GREEN_PRECHECK_REQUIRES_SEPARATE_OPERATOR_APPROVED_HANDOFF_WINDOW`

Current approval status: `new_operator_approval_required_for_any_timer_handoff`

Current apply status: `post_health_fix_reprep_precheck_passed_no_handoff`

The green post-observation-reprep precheck supported opening the
operator-approved apply window, and the apply window did start. The
post-reference timer-created Meridian supervisor cycle completed without order
or fill side effects, proving the position-reference and path/config blockers
were cleared for that cycle. The health monitor then alerted because its recent
run window still included two older blocked Meridian supervisor runs. Rollback
completed cleanly to zero timers, no active/enabled related units, Meridian
paused/disarmed state, zero open orders, and the same 11 open positions. The
health-alert fix apply then installed only the amended handoff-observation
config and reset the failed Meridian health service. A fresh read-only precheck
after that fix proved all surfaces except Meridian `operator_paused=true`; the
separate observation-state re-prep restored Meridian to
`operator_paused=false`, `live_delta_armed=false` with zero timers and no
active/enabled related units. The fresh serialized read-only handoff precheck
after that re-prep is now green with false checks `[]`, but this document still
does not authorize timer enablement. A separate operator-approved handoff apply
window is required for any timer ownership change.

Current blocker triage:

- Position-reference fix-window artifact:
  `docs/MERIDIAN_POSITION_REFERENCE_FIX_WINDOW.md`
- Read-only proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T130527Z-position-reference-readonly-inventory`
- Read-only triage result:
  - no timer enable/start, service start, reference copy, reference generation,
    order/cancel path, or accepted-evidence update was attempted
  - `systemd_timers.txt` listed `0 timers`
  - legacy monitor-selected reconciled delta reference had 11 positions:
    `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution`
  - that selected legacy reference matched the Meridian apply-attempt
    11-position inventory exactly
  - Meridian valid reference candidates were `0`
- Position-reference apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T133219Z-meridian-equivalent-genesis-apply`
- Position-reference apply result:
  - `status=passed`
  - false checks: `[]`
  - created Meridian reference:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`
  - explicit Meridian reference monitor passed
  - implicit Meridian-root reference monitor passed and selected the new
    Meridian reference
  - no timer handoff, timer enable/start, service start, live-delta arm,
    order submit/cancel/test, or accepted-evidence update was attempted

Post-reference read-only handoff precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135219Z-post-reference-readonly-precheck`
- Acceptance artifact:
  `post_reference_precheck_acceptance.json`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - path/config probe passed under `/root/meridian_alpha_live_runner/repo`
  - Meridian equivalent genesis reference exists and is valid
  - implicit Meridian position monitor passed and selected:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`
  - position monitor artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T135225083948Z-mainnet-position-monitor`
  - `open_order_count=0`
  - `open_position_count=11`
  - `orders_submitted=0`
  - `orders_canceled=0`
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` remained `0 timers listed`
  - all related legacy and Meridian units were inactive
  - Meridian units were loaded and disabled/static
  - live delta remained disarmed
- Blocking state:
  - Meridian `operator_paused=true`
  - Meridian `live_delta_armed=false`
  - latest Meridian operator action:
    `20260531T125107152212Z:kill-switch:20260531T124734Z-meridian-timer-handoff-observation-rollback`
  - reason:
    `rollback Meridian timer handoff after supervisor blocked on missing Meridian position reference and unexpected live positions; keep live_delta_armed=false`

Fresh rerun of the same post-reference read-only precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135612Z-post-reference-readonly-precheck-rerun`
- Acceptance artifact:
  `post_reference_precheck_acceptance.json`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - implicit Meridian position monitor passed and selected the same Meridian
    equivalent genesis reference
  - position monitor artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T135616747626Z-mainnet-position-monitor`
  - `open_order_count=0`
  - `open_position_count=11`
  - `orders_submitted=0`
  - `orders_canceled=0`
  - path/config probe passed under the Meridian repo
  - all related units were inactive
  - timer list remained `0 timers listed`
- Interpretation:
  - the position-reference fix remains valid
  - the only repeated no-go is still Meridian `operator_paused=true`
  - do not attempt timer handoff before a separate observation-state re-prep

Observation-state re-prep:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T135943Z-post-reference-observation-state-reprep`
- Acceptance artifact:
  `observation_state_reprep_acceptance.json`
- Result:
  - `status=passed`
  - false checks: `[]`
  - pre-state: Meridian `operator_paused=true`, `live_delta_armed=false`
  - post-state: Meridian `operator_paused=false`, `live_delta_armed=false`
  - latest Meridian operator action:
    `20260531T135948676935Z:resume:20260531T135948676935Z-plan_only`
  - latest Meridian live-delta action:
    `20260531T135949729031Z:disarm-live-delta:20260531T135949729031Z-plan_only`
  - post-state timer list remained `0 timers listed`
  - all related units remained inactive
  - no cutover, timer enable/start, service start, live-delta arm,
    order submit/cancel/test, or accepted-evidence update was attempted

Post-observation-reprep read-only handoff precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T140218Z-post-observation-reprep-readonly-precheck`
- Acceptance artifact:
  `post_observation_reprep_precheck_acceptance.json`
- Result:
  - `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - Meridian `operator_paused=false`
  - Meridian `live_delta_armed=false`
  - live-delta last action: `disarm-live-delta`
  - implicit Meridian position monitor passed and selected:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`
  - position monitor artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T140222598347Z-mainnet-position-monitor`
  - `open_order_count=0`
  - `open_position_count=11`
  - `orders_submitted=0`
  - `orders_canceled=0`
  - path/config probe passed under `/root/meridian_alpha_live_runner/repo`
  - all related legacy and Meridian units were inactive
  - Meridian units were loaded and disabled/static
  - timer list remained `0 timers listed`

Last attempted proof-cycle semantics:

- Legacy runner remains the rollback baseline:
  `operator_paused=true`, `live_delta_armed=false`.
- Meridian runner uses the no-live-delta observation state:
  `operator_paused=false`, `live_delta_armed=false`.
- The Meridian handoff-observation config keeps auto-rearm disabled.
- The handoff does not authorize live delta, orders, strategy changes, Binance
  permission changes, secrets changes, accepted-evidence changes, or formal
  readiness claims.

Approval phrase used for the rolled-back attempt:

```text
I approve the Meridian timer handoff apply window on root@203.0.113.10.
Scope: enable the Meridian health timer and Meridian live supervisor timer
only, using Meridian observation state operator_paused=false and
live_delta_armed=false; keep legacy timers disabled and the legacy runner as
paused/disarmed rollback baseline; do not authorize live delta, order
submission, order cancellation, order-test calls, strategy/risk/capital/secrets
changes, accepted-evidence updates, or formal readiness claims; verify one
timer-created Meridian supervisor cycle and one Meridian health-monitor cycle;
roll back to zero timers and paused/disarmed safety state if any verification
fails.
```

Do not reuse this approval phrase for another apply attempt. The
position-reference blocker is fixed, but the latest post-reference apply was
rolled back because the health monitor alerted on superseded blocked runs in
its recent-run window.

## Pre-Apply GO Conditions Satisfied

- Fixed Meridian service drop-ins are installed and verified.
- Python path/config probe resolves under `/root/meridian_alpha_live_runner/repo`.
- Fresh post-observation-state precheck passed with false checks `[]`.
- `systemctl list-timers --all 'enhengclaw-mainnet*'
  'meridian-alpha-mainnet*'` listed `0 timers`.
- Legacy live and health timers were inactive/disabled.
- Meridian live and health timers were inactive/disabled.
- Legacy and Meridian services were inactive/dead.
- Meridian service `ExecStart` used the absolute Meridian repo, venv, and
  handoff-observation config paths.
- Binance account and open-order GET reads succeeded.
- Open orders were zero.
- The expected 11 open positions were still present.
- Legacy rollback state was paused/disarmed.
- Meridian observation state was unpaused/disarmed.
- No accepted evidence path was updated.

## Current NO-GO Triggers

Any item below blocks apply and requires a fresh read-only triage:

- Fresh operator approval for a post-reference Meridian handoff apply window is
  absent.
- The Meridian runner lacks a valid position reference for the existing live
  positions.
- A timer-created Meridian supervisor cycle exits
  `mainnet_live_supervisor_blocked`.
- A Meridian health-monitor cycle exits `mainnet_health_monitor_alerted` or
  reports nonzero critical alerts that have not been separately triaged and
  accepted.
- Operator approval is absent or ambiguous.
- A fresh just-in-time pre-state check is not captured in the apply proof root.
- Any legacy or Meridian related service is active before enablement.
- Any legacy timer becomes active.
- Any Meridian timer is already active before the apply window starts.
- Open-order read fails or `open_order_count` is not zero.
- Position inventory drifts from the expected 11 without a separate inventory
  explanation.
- Meridian `live_delta_armed` is true.
- Meridian `operator_paused` is true for the proof cycle.
- Legacy rollback state is not paused/disarmed.
- Auto-rearm is not disabled in the Meridian handoff-observation config.
- The amended handoff-observation config is not installed or does not show
  `recent_run_count=1`.
- A Meridian service path resolves through `/root/enhengclaw_live_runner`.
- Any order submission, cancellation, or order-test call is attempted.
- The operator cannot complete verification within the window.

## Future Apply Boundary After Blocker Fix

When explicitly approved, the apply window may:

- Create a unique proof root under
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/`.
- Capture just-in-time pre-state evidence before enabling timers.
- Re-run the installed drop-in verifier and the path/config probe.
- Reconfirm zero timers, no active related services, zero open orders, legacy
  paused/disarmed state, and Meridian unpaused/disarmed observation state.
- Reconfirm the installed Meridian handoff-observation config has proof-only
  `recent_run_count=1`.
- Enable the Meridian health timer first.
- Enable the Meridian live supervisor timer second.
- Let timers create exactly the verification cycles.
- Capture post-enable, post-supervisor-cycle, and post-health-cycle evidence.

The apply window must not:

- Enable or start any legacy timer.
- Manually start Meridian services unless a separate service-level fallback is
  explicitly approved inside the apply transcript.
- Arm live delta.
- Submit, cancel, or test any order.
- Change strategy, capital, risk, Binance permissions, or secrets.
- Update `PROJECT_STATE.md`.
- Update accepted evidence or formal readiness claims.
- Treat a successful timer handoff as live-trading approval.

## Current Success Criteria

The future apply window may be considered successful only if all of these are
true:

- Exactly the two Meridian timers are active/waiting after enablement.
- No legacy live or health timer is active.
- Fresh supervisor and health-monitor artifacts are written under the Meridian
  runner tree.
- The supervisor cycle is not blocked by operator pause.
- The supervisor reports zero submitted orders and zero fills.
- The health monitor references `meridian-alpha-mainnet-supervisor-live.timer`.
- The health monitor observes only the latest proof supervisor cycle under the
  amended handoff-observation config.
- The health monitor has no critical alerts, or every alert is explained and
  accepted before leaving timers enabled.
- Open orders remain zero before and after the cycles.
- Meridian remains `operator_paused=false`, `live_delta_armed=false`.
- Legacy remains the paused/disarmed rollback baseline.
- No accepted evidence path or formal readiness claim is updated.

## Current Rollback Boundary

Rollback should return to the frozen safety baseline:

- Stop and disable Meridian supervisor and health timers.
- Stop Meridian supervisor and health services if they remain active after
  evidence capture.
- Record a Meridian pause/disarm or equivalent kill-switch if the window fails.
- Keep legacy timers inactive/disabled unless a separate restore window is
  approved.
- Preserve legacy paused/disarmed state.
- Verify all related services inactive/dead.
- Verify timer list returns to `0 timers` for the legacy/Meridian patterns.
- Verify open orders remain zero.
- Keep `/root/meridian_alpha_live_runner` and the apply proof root for forensic
  inspection.

## Historical Superseded Decision

## Decision

Recommended decision: `GO_TO_OPERATOR_APPROVAL`

Current approval status: `approval_pending`

Current apply status: `not_applied`

The latest read-only evidence supports opening a separate, operator-approved
apply window for the Meridian timer handoff. The evidence does not authorize
live delta, strategy changes, Binance permission changes, accepted-evidence
updates, or any broad readiness claim.

## Cutover Request Outcome

Cutover was requested after this decision record, but the mandatory pre-apply
read-only precheck blocked execution.

Pre-apply proof from `2026-05-31T11:01:09Z`:

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
  - Latest pause-state action:
    `20260531T105307555559Z:resume:20260531T105307555559Z-plan_only`
  - Reason:
    `operator requested remote arm window; clear pause before arm-only, timers remain disabled`
  - Latest live-delta action:
    `20260531T105308678526Z:arm-live-delta:20260531T105308678526Z-plan_only`
  - Reason:
    `operator requested remote arm-only; no timer start and no supervisor invocation`
- Safety state still held:
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed `0 timers`
  - all legacy and Meridian timer units were inactive/disabled
  - all legacy and Meridian services were inactive/dead
  - no related active services were observed
  - open orders remained zero
- Decision:
  - `NO_GO_FOR_CUTOVER`
  - The Meridian timers must not be enabled while operator pause is false and
    live delta is armed.
  - The next safe path is a separate re-freeze/stabilization action that records
    operator `kill-switch` or equivalent disarm/pause, then reruns the
    serialized read-only precheck before any cutover.

## Re-Freeze, Cutover Attempt, And Rollback

After the `NO_GO_FOR_CUTOVER` result, the operator approved re-freeze and
precheck before continuing cutover. That sequence completed, then the Meridian
timer handoff was attempted and rolled back.

Re-freeze proof:

- Legacy runner kill-switch proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/legacy_timer_refreeze/20260531T111154Z-operator-kill-switch-before-meridian-handoff`
- Legacy re-freeze result:
  - `refreeze_passed=true`
  - `operator_paused=true`
  - `live_delta_armed=false`
- Meridian runner state seed proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_state_refreeze/20260531T111455Z-meridian-operator-kill-switch-before-handoff`
- Meridian state seed result:
  - `refreeze_passed=true`
  - `operator_paused=true`
  - `live_delta_armed=false`

Final pre-cutover precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T111549Z-final-pre-cutover-readonly-precheck`
- Result:
  - `precheck_passed=true`
  - `legacy_operator_paused_disarmed=true`
  - `meridian_operator_paused_disarmed=true`
  - `timers_zero=true`
  - `open_order_count=0`

Cutover attempt:

- Handoff root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover`
- Apply result:
  - `handoff_applied=true`
  - Meridian health timer became active
  - Meridian supervisor timer became active
  - legacy timers stayed inactive
  - no live delta was armed

Verification result:

- Verification artifact:
  `handoff_cycle_verification.json`
- Result:
  - `verification_passed=false`
  - `rollback_required=true`
  - open orders remained zero
  - no submitted orders or fills were observed
- Failure triage:
  - Supervisor timer did fire and wrote Meridian artifacts, including:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T111641250467Z-mainnet-live-supervisor`
    and
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T112707172721Z-mainnet-live-supervisor`.
  - The supervisor exited blocked with `operator_paused`, `orders_submitted=0`,
    `fill_count=0`, and `live_delta_armed=false`.
  - The health monitor failed with `FileNotFoundError` for:
    `/root/enhengclaw_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`.
  - The traceback showed the Meridian health service script invoked from the
    Meridian tree but loaded runtime code from `/root/enhengclaw_live_runner/repo/src`,
    so the service environment still resolves part of the Python path through
    the legacy repo.

Rollback result:

- Rollback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover/rollback`
- Final rollback artifact:
  `rollback_summary_after_reset_failed.json`
- Result:
  - `rollback_passed=true`
  - `timers_zero=true`
  - legacy timers inactive/disabled
  - Meridian timers inactive/disabled
  - legacy services inactive
  - Meridian services reset to inactive/dead
  - `open_order_count=0`
- Final readback confirmed:
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed `0 timers`
  - all legacy and Meridian timer units were inactive/disabled
  - all legacy and Meridian services were inactive/dead
  - open orders remained zero

Historical decision at that point:

- `CUTOVER_ATTEMPT_ROLLED_BACK`
- Do not attempt timer handoff again until a separate fix window addresses:
  - Meridian service Python path / config resolution
  - whether the handoff acceptance should require `operator_paused=true` or use
    a distinct no-live-delta observation state
  - a corrected artifact polling rule for Meridian supervisor and health
    outputs
- Fix-window decision:
  - use an explicit Meridian no-live-delta observation state for future proof
    cycles
  - require Meridian `operator_paused=false`, `live_delta_armed=false`, and
    auto-rearm disabled in the handoff-observation config
  - keep the legacy paused/disarmed state only as a rollback baseline, not as
    the Meridian cycle-success state

## Evidence Basis

- Design review:
  `docs/MERIDIAN_TIMER_HANDOFF_CUTOVER_DESIGN_REVIEW.md`
- Latest read-only precheck proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T095720Z-design-review-readonly-precheck`
- Acceptance artifact:
  `handoff_precheck_acceptance.json`
- Fresh precheck result:
  - `precheck_passed=true`
  - `handoff_approved_for_apply=false`
  - `handoff_applied=false`
  - `no_cutover_performed=true`
  - `read_only_state_boundary=true`
  - `accepted_evidence_updated=false`
  - `open_order_count=0`
  - `open_position_count=11`

## GO Conditions Satisfied

- Package hash manifest verification passed.
- Disabled Meridian unit verifier passed.
- `systemctl list-timers --all 'enhengclaw-mainnet*'
  'meridian-alpha-mainnet*'` listed `0 timers`.
- Legacy live, health, and no-order timers were inactive/disabled.
- Meridian live and health timers were inactive/disabled.
- Legacy and Meridian services were inactive/dead.
- Meridian units referenced `/root/meridian_alpha_live_runner` only.
- Binance account and open-order reads succeeded.
- Open orders were zero.
- The 11 open positions matched the already explained inventory.
- Operator state was readable.
- `operator_paused=true`.
- `live_delta_armed=false`.
- Auto-rearm remained configured, but had no scheduled path and was blocked by
  operator pause.

## Remaining Approval Gates

The following gates remain open and must be closed before any apply action:

- [ ] Operator explicitly approves the apply window.
- [ ] Operator names the target host as `root@203.0.113.10`.
- [ ] Operator confirms scope is timer ownership handoff only.
- [ ] Operator confirms no live delta authorization is granted.
- [ ] Operator confirms rollback default is the frozen baseline:
      no legacy/Meridian timers active, operator pause retained, live delta
      disarmed, and open orders zero.
- [ ] If material time passes or any remote state changes before apply, rerun a
      fresh serialized read-only precheck.

## Approval Phrase

The following historical approval phrase is superseded by the fix-window
decision and must not be reused for a future handoff:

```text
I approve the Meridian timer handoff apply window on root@203.0.113.10.
Scope: enable the Meridian health timer and Meridian live supervisor timer,
verify one timer-created supervisor cycle and one health-monitor cycle, keep
operator pause and live_delta_armed=false, do not authorize live delta, do not
change strategy/risk/capital/secrets/accepted evidence, and roll back to the
frozen baseline if any verification fails.
```

A future handoff approval phrase must be rewritten after the fix package is
proved. It must use Meridian `operator_paused=false`,
`live_delta_armed=false`, and disabled auto-rearm for the proof cycle.

## Apply Boundary

When approved, the apply window may:

- Capture fresh rollback and forensic evidence.
- Re-run the frozen package hash check.
- Re-run the disabled Meridian unit verifier.
- Reconfirm zero timers, zero open orders, operator pause, and live delta
  disarmed before enablement.
- Enable the Meridian health timer first.
- Enable the Meridian live supervisor timer second.
- Let timers create exactly the first verification cycles.
- Capture post-enable and post-cycle evidence.

The apply window must not:

- Enable or start any legacy timer.
- Manually arm live delta.
- Submit, cancel, or test any order.
- Change strategy, capital, risk, Binance permissions, or secrets.
- Update `PROJECT_STATE.md`.
- Update accepted evidence or formal readiness claims.
- Treat a successful timer handoff as live-trading approval.

## Rollback Boundary

Rollback should return to the frozen baseline:

- Meridian timers inactive/disabled.
- Legacy live and health timers inactive/disabled.
- All related services inactive/dead.
- Operator pause retained.
- `live_delta_armed=false`.
- Open orders zero.

Restoring active legacy timers is not part of the default rollback. It requires
a separate operator decision.
