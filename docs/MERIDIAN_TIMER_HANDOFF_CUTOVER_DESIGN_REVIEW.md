# Meridian Timer Handoff/Cutover Design Review

This is a local design-review artifact only. It does not authorize, enable, or
start any Meridian systemd timer.

Current status: `HANDOFF_COMPLETED_POST_HEALTH_FIX`. The old
`operator_paused=true` proof semantics remain superseded. Use
`docs/MERIDIAN_TIMER_HANDOFF_FIX_WINDOW.md` and
`docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md` for the completed
post-health-fix handoff record. The original `operator_paused=true`
cycle-success requirement is no longer valid for the Meridian proof cycle.

## Scope

- Target host: `root@203.0.113.10`
- Legacy runner root: `/root/enhengclaw_live_runner`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Frozen local package input:
  `scripts/remote_runner_service_migration/`
- Remote frozen package input:
  `/root/meridian_alpha_live_runner/review_package/remote-runner-service-migration-local-freeze-20260531T073901Z`
- Latest frozen-baseline precheck proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_cutover_precheck/20260531T091118Z-frozen-baseline-readonly-precheck`

The default rollback target for any future apply window is the frozen safety
baseline: all legacy and Meridian live/health timers off, legacy operator pause
retained, Meridian paused/disarmed again if rollback is triggered, live delta
disarmed, and open orders still zero. Restoring active legacy timers is a
separate operator decision, not the default rollback.

## Latest Pre-Apply Read-Only Precheck

Fresh serialized remote precheck from `2026-05-31T09:57:20Z`:

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
- All go/no-go read-only checks were true:
  - package hash manifest verification passed
  - disabled Meridian unit verifier passed
  - `systemctl list-timers --all 'enhengclaw-mainnet*'
    'meridian-alpha-mainnet*'` listed `0 timers`
  - legacy live, health, and no-order timers were inactive/disabled
  - Meridian live and health timers were inactive/disabled
  - legacy and Meridian services were inactive/dead
  - Meridian units referenced `/root/meridian_alpha_live_runner` only
  - Binance account and open-order reads succeeded
  - open position inventory matched the previously explained 11-position set
  - operator state was readable, `paused=true`, and `live_delta_armed=false`
  - auto-rearm remained configured but had no scheduled path and was blocked
    by operator pause
- Independent readback after the precheck found no false checks and confirmed
  `0 timers listed`.
- This precheck proves the frozen baseline is still eligible for an
  operator-approved apply decision. It does not approve cutover by itself.

## Apply Decision Status

Current decision record from `2026-05-31T15:48:23Z`:

- Local artifact:
  `docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md`
- Decision:
  `HANDOFF_COMPLETED_POST_HEALTH_FIX`
- Current approval status:
  `approval_received_execute_message_2026-05-31T15:48Z`
- Current apply status:
  `handoff_completed_meridian_timers_active`
- Completed apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T154823Z-meridian-timer-handoff-post-health-fix-apply`
- Completed apply result:
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
  - `open_order_count=0`
  - `open_position_count=11`
  - active/enabled units are exactly:
    `meridian-alpha-mainnet-supervisor-live.timer` and
    `meridian-alpha-mainnet-health-monitor.timer`
  - legacy supervisor and health timers remain disabled/inactive
  - `accepted_evidence_updated=false`
- Decision boundary:
  - This completed apply supersedes the earlier position-reference-blocked and
    health-alert-blocked attempts, which remain below as audit history.
  - The successful state is timer ownership handoff only. It does not approve
    live delta, order submission, strategy/risk/capital/secrets changes,
    accepted-evidence updates, or formal readiness.
  - The next window should be post-handoff steady-state observation and
    read-only monitoring.

Position-reference fix outcome:

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T133219Z-meridian-equivalent-genesis-apply`
- Created Meridian reference:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`
- Result:
  - `status=passed`
  - false checks: `[]`
  - explicit Meridian reference monitor passed
  - implicit Meridian-root reference monitor passed
  - no timer handoff or timer enable/start was attempted

Post-reference read-only handoff precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135219Z-post-reference-readonly-precheck`
- Acceptance artifact:
  `post_reference_precheck_acceptance.json`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - implicit Meridian position monitor passed with open orders zero and 11
    open positions
  - path/config probe passed under the Meridian repo
  - all related units were inactive
  - timer list remained `0 timers listed`
  - no cutover, timer enable/start, service start, order path, or
    accepted-evidence update was attempted

Fresh rerun:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135612Z-post-reference-readonly-precheck-rerun`
- Acceptance artifact:
  `post_reference_precheck_acceptance.json`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - `precheck_passed=false`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - implicit Meridian position monitor passed with open orders zero and 11
    open positions
  - all related units stayed inactive
  - timer list stayed `0 timers listed`
  - no cutover, timer enable/start, service start, live-delta arm, order path,
    or accepted-evidence update was attempted

Observation-state re-prep and green precheck:

- Observation-state re-prep proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T135943Z-post-reference-observation-state-reprep`
- Re-prep result:
  - `status=passed`
  - false checks: `[]`
  - Meridian post-state: `operator_paused=false`, `live_delta_armed=false`
  - no timer enable/start, service start, live-delta arm, order path, or
    accepted-evidence update was attempted
- Fresh read-only handoff precheck proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T140218Z-post-observation-reprep-readonly-precheck`
- Precheck result:
  - `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - implicit Meridian position monitor passed with open orders zero and 11
    open positions
  - all related units stayed inactive
  - timer list stayed `0 timers listed`
  - no cutover, timer enable/start, service start, live-delta arm, order path,
    or accepted-evidence update was attempted

## Latest Rolled-Back Apply Outcome

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
  - timer readback returned to `0 timers listed`
  - `active_units=[]`
  - `enabled_units=[]`
  - Meridian rollback kill-switch restored `operator_paused=true`
  - Meridian `live_delta_armed=false`
  - `open_order_count=0`
  - `open_position_count=11`
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
- Failure:
  - The successful post-reference supervisor cycle was clean and no-order.
  - The health monitor used `recent_run_count_required=3` and included older
    blocked Meridian runs `20260531T124746329564Z` and
    `20260531T112707172721Z`.
  - Those superseded blocked runs produced the 11 critical alerts.
  - Next window must triage health alert semantics before any further handoff.

## Health-Alert Triage/Fix Outcome

- Local artifact:
  `docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`
- Local package amended:
  `scripts/remote_runner_service_fix_window/`
- Remote apply proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_health_alert_fix_apply/20260531T151439Z-amended-handoff-observation-config-apply`
- Decision:
  - the health monitor behaved according to its configured 3-run contract
  - default live timer configs keep the 3-run health window
  - only the Meridian handoff-observation proof config is narrowed to
    `mainnet_health_monitor.recent_run_count=1`
  - this aligns the proof config with the one-supervisor-cycle handoff
    verification contract
- Remote apply result:
  - `status=passed`
  - false checks: `[]`
  - `0 timers listed` after apply
  - no active or enabled related units after apply
  - Meridian health service reset to `loaded/inactive/dead/static`
  - no handoff or order paths were attempted
- Boundary:
  - another handoff remains no-go until a fresh read-only precheck passes

Post-health-fix read-only precheck and re-prep:

- Read-only precheck proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`
- Result:
  - `status=no_go_readonly_precheck_failed`
  - false checks: `["meridian_operator_unpaused_for_proof"]`
  - implicit Meridian position monitor passed with `open_order_count=0` and
    `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff/order paths were attempted
- Observation-state re-prep proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`
- Result:
  - `status=passed`
  - false checks: `[]`
  - Meridian restored to `operator_paused=false`, `live_delta_armed=false`
  - latest Meridian live-delta action is `disarm-live-delta`
  - timer list remained `0 timers listed`
  - no active or enabled related units
- Boundary:
  - a new fresh serialized read-only handoff precheck is required after this
    re-prep before any operator-approved handoff apply decision.
- Post-reprep read-only precheck proof:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`
- Result:
  - `status=passed`
  - `precheck_passed=true`
  - false checks: `[]`
  - Meridian `operator_paused=false`
  - Meridian `live_delta_armed=false`
  - latest Meridian live-delta action is `disarm-live-delta`
  - implicit Meridian position monitor passed with `open_order_count=0` and
    `open_position_count=11`
  - timer list remained `0 timers listed`
  - no active or enabled related units
  - no handoff/order paths were attempted
- Boundary:
  - this green precheck is an input for a separate operator-approved handoff
    apply window; it did not enable or start timers.

## Previous Position-Reference-Blocked Apply Outcome

- Apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply`
- Poll artifact:
  `polls/20260531T124921Z-poll/cycle_poll_summary.json`
- Rollback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply/rollback/20260531T125103Z-rollback-supervisor-blocked`
- Final readback root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T124734Z-meridian-timer-handoff-observation-apply/final_readback/20260531T125414Z-readonly-final-readback`
- Result:
  - `prestate_passed=true`
  - `handoff_applied=true`
  - `verification_passed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - final timer readback: `0 timers listed`
  - final readback passed with false checks: `[]`
  - all related services inactive/dead after rollback
  - open orders zero
- Failure:
  - supervisor artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T124746329564Z-mainnet-live-supervisor/run_summary.json`
  - status: `mainnet_live_supervisor_blocked`
  - blocker: missing Meridian position reference plus 11
    `unexpected_live_position:*` blockers
  - orders and fills remained zero

## Go/No-Go Checklist

All items below must be true before a future apply window may enable or start a
Meridian timer. Any false item is a no-go.

### Authorization

- [ ] The operator explicitly approves a future Meridian timer handoff apply
      window and names the target host.
- [ ] The apply window is limited to timer ownership handoff and verification.
- [ ] No strategy, capital, risk, Binance permission, secret, or live intent
      change is included.
- [ ] `PROJECT_STATE.md`, accepted evidence paths, and formal readiness claims
      are not updated by the timer handoff.
- [ ] Rollback owner and communication path are known before apply starts.

### Frozen Baseline

- [x] A fresh serialized remote precheck passes after this design review.
- [ ] Package hash verification passes for the frozen remote package.
- [ ] `verify_disabled_meridian_units.sh --expect-installed` passes.
- [ ] `systemctl list-timers --all 'enhengclaw-mainnet*'
      'meridian-alpha-mainnet*'` lists `0 timers`.
- [ ] Legacy live and health timers are `loaded/inactive/disabled`.
- [ ] Legacy live and health services are `inactive/dead`.
- [ ] Meridian live and health timers are `loaded/inactive/disabled`.
- [ ] Meridian live and health services are `loaded/inactive/dead`.
- [ ] Meridian unit files reference `/root/meridian_alpha_live_runner` only.
- [ ] No legacy and Meridian live-capable supervisor timers can overlap.

### Account And Runtime Safety

- [ ] Binance account read succeeds.
- [ ] Open-order read succeeds.
- [ ] `open_order_count=0`.
- [ ] Open positions are the expected inventory or are separately explained.
- [ ] The Meridian runner has a valid position reference, or equivalent
      reviewed Meridian-root reference, for the existing live-position
      inventory.
- [x] The Meridian position-reference fix window has produced a successful
      apply proof and the Meridian position monitor passes from its own root.
- [ ] Legacy rollback state remains paused/disarmed if that remains the chosen
      rollback baseline.
- [ ] Meridian proof state is explicitly selected as `operator_paused=false`
      and `live_delta_armed=false`.
- [ ] The Meridian handoff-observation config disables auto-rearm for the proof
      cycle.
- [ ] The Meridian handoff-observation config uses proof-only
      `recent_run_count=1`.
- [ ] There is no active supervisor or health-monitor service at apply start.

## Future Apply Steps

Do not run this section unless the operator opens a separate apply window.

1. Create a unique apply proof root under:
   `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/`
2. Capture rollback and forensic evidence before any state change:
   - UTC timestamp, hostname, kernel, user
   - package hash verification output
   - disabled Meridian unit verifier output
   - `systemctl list-timers`
   - `systemctl show` and `systemctl cat` for all legacy and Meridian units
   - last 120 journal lines for all legacy and Meridian units
   - operator state, open orders, and open positions
3. Confirm quiet window:
   - no legacy supervisor or health service active
   - no Meridian supervisor or health service active
   - no open orders
4. Recheck frozen safety state:
   - legacy rollback state still paused/disarmed
   - Meridian proof state still `operator_paused=false`
   - Meridian `live_delta_armed=false`
   - Meridian handoff-observation config still has auto-rearm disabled
   - legacy timers still inactive/disabled
   - Meridian timers still inactive/disabled
5. Enable the Meridian health timer first, then the Meridian supervisor timer:

```bash
systemctl enable --now meridian-alpha-mainnet-health-monitor.timer
systemctl enable --now meridian-alpha-mainnet-supervisor-live.timer
```

6. Do not manually start supervisor or health services unless a separate review
   has approved service-level execution. Let timer scheduling create the first
   cycles.
7. Immediately capture post-enable timer and unit state.
8. Wait for one Meridian supervisor cycle and one Meridian health-monitor cycle.
9. Capture post-cycle artifacts, journal snippets, account state, and operator
   state.

## Verification Steps

Immediate verification after timer enable:

- [ ] Exactly the two Meridian timers are active/waiting.
- [ ] No legacy live or health timer is active.
- [ ] No legacy service is active.
- [ ] Meridian service activity is only timer-created and bounded.
- [ ] Meridian unit files still reference `/root/meridian_alpha_live_runner`
      only.
- [ ] Open orders remain zero.
- [ ] Legacy rollback state remains paused/disarmed.
- [ ] Meridian remains `operator_paused=false`.
- [ ] Meridian `live_delta_armed=false`.

Cycle verification after one supervisor and one health-monitor cycle:

- [ ] A fresh Meridian supervisor artifact exists under the Meridian runner
      tree.
- [ ] The supervisor run completes without submitted orders or fills.
- [ ] A fresh Meridian health-monitor artifact exists under the Meridian runner
      tree.
- [ ] The health monitor references
      `meridian-alpha-mainnet-supervisor-live.timer`.
- [ ] Health critical alerts are zero, or any alert is explained and accepted
      before continuing.
- [ ] Open orders remain zero after both cycles.
- [ ] Open positions remain expected or separately explained.
- [ ] Legacy rollback state remains paused/disarmed after both cycles.
- [ ] Meridian remains `operator_paused=false` after both cycles.
- [ ] Meridian `live_delta_armed=false` after both cycles.
- [ ] No accepted evidence path or formal readiness claim is updated.

Retain the future apply proof root with at least:

- `handoff_acceptance.json`
- `state_before.json`
- `state_after_enable.json`
- `state_after_cycles.json`
- `open_orders_before.json`
- `open_orders_after.json`
- `open_positions_before.json`
- `open_positions_after.json`
- `timers_before.txt`
- `timers_after_enable.txt`
- `timers_after_cycles.txt`
- `unit_state_before.txt`
- `unit_state_after_enable.txt`
- `unit_state_after_cycles.txt`
- `journal_before.txt`
- `journal_after.txt`
- `rollback_checklist.md`

## Rollback Steps

Rollback is required if any verification item fails, if legacy/Meridian timer
overlap appears, if an unexpected order signal appears, or if the operator
cannot complete verification within the window.

Default rollback returns to the frozen baseline, not to active legacy timers.

1. Capture failure evidence before stopping anything:
   - `systemctl status` for Meridian and legacy units
   - `journalctl -u ... -n 120` for Meridian and legacy units
   - timer list, unit state, open orders, open positions, and operator state
2. Stop and disable Meridian timers:

```bash
systemctl stop meridian-alpha-mainnet-supervisor-live.timer meridian-alpha-mainnet-health-monitor.timer
systemctl disable meridian-alpha-mainnet-supervisor-live.timer meridian-alpha-mainnet-health-monitor.timer
```

3. If a Meridian service is still active, stop it after evidence capture:

```bash
systemctl stop meridian-alpha-mainnet-supervisor-live.service meridian-alpha-mainnet-health-monitor.service
```

4. Reload systemd and verify the frozen baseline:

```bash
systemctl daemon-reload
systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*'
```

5. Confirm:
   - `0 timers` for the legacy/Meridian patterns
   - legacy timers remain inactive/disabled
   - Meridian timers are inactive/disabled
   - all legacy and Meridian services are inactive/dead
   - open orders remain zero
   - legacy rollback state remains paused/disarmed
   - Meridian is paused/disarmed again if rollback was triggered
   - live delta remains false on both runner states
6. Keep `/root/meridian_alpha_live_runner` and the apply proof root for
   forensic review until cleanup is separately approved.
7. Do not re-enable legacy timers unless the operator opens a separate rollback
   restore window. That restore window must capture fresh state, preserve
   operator pause, and verify open orders remain zero.

## Go/No-Go Output

A future apply window should end with a machine-readable summary containing at
least:

```json
{
  "schema": "meridian_alpha.timer_handoff_go_no_go.v1",
  "handoff_approved_for_apply": false,
  "handoff_applied": false,
  "rollback_required": false,
  "legacy_timers_active": false,
  "meridian_timers_active": false,
  "legacy_operator_paused": true,
  "meridian_operator_paused": false,
  "meridian_live_delta_armed": false,
  "open_order_count": 0,
  "accepted_evidence_updated": false
}
```

Before an actual apply, `handoff_approved_for_apply` had to be set by the
operator in that future window. That later happened in the post-health-fix
apply window, whose final machine-readable result is
`status=handoff_completed`, `handoff_applied=true`,
`verification_passed=true`, `rollback_required=false`, false checks `[]`, and
`accepted_evidence_updated=false`.
