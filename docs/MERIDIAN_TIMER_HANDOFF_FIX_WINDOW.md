# Meridian Timer Handoff Fix Window

This is the fix-window design, package review, and remote apply summary. The
remote apply did not enable, start, or cut over any timer.

## Status

- Status: `PATH_CONFIG_FIX_APPLIED_AND_LATER_HANDOFF_COMPLETED`
- Fix package:
  `scripts/remote_runner_service_fix_window/`
- Hash manifest:
  `scripts/remote_runner_service_fix_window/PACKAGE_SHA256SUMS.txt`
- Previous failed handoff root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T111635Z-meridian-timer-handoff-cutover`
- Previous rollback result:
  `rollback_summary_after_reset_failed.json` reported timers zero, related
  services inactive/dead, and open orders zero.
- Remote fix apply proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_path_fix_apply/20260531T115517Z-meridian-service-path-fix-apply`
- Remote fix apply summary:
  `fix_apply_summary.json`
- Remote fix apply result:
  - `fix_apply_passed=true`
  - package hash verification passed
  - static and installed drop-in verifiers passed
  - handoff-observation config installed under the Meridian repo
  - service drop-ins installed under `/etc/systemd/system`
  - `systemctl daemon-reload` completed
  - read-only Python path probe passed
  - `config_module_file` resolved to
    `/root/meridian_alpha_live_runner/repo/src/enhengclaw/live_trading/config.py`
  - `config_root` resolved to `/root/meridian_alpha_live_runner/repo`
  - `loaded_config_path` resolved to the Meridian handoff-observation config
  - final readback listed `0 timers`
  - related legacy and Meridian services were inactive/dead
  - Meridian timers remained disabled
  - `cutover_attempted=false`
  - `accepted_evidence_updated=false`
  - `live_delta_armed_or_order_action_attempted=false`

The remote apply changed only the Meridian handoff-observation config and the
two Meridian service path drop-ins. It did not enable or start any timer.

Later windows then completed the remaining handoff chain:

- Position-reference fix:
  `docs/MERIDIAN_POSITION_REFERENCE_FIX_WINDOW.md`
- Health-alert proof-config fix:
  `docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`
- Final handoff decision and outcome:
  `docs/MERIDIAN_TIMER_HANDOFF_APPLY_DECISION.md`
- Completed handoff proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T154823Z-meridian-timer-handoff-post-health-fix-apply`
- Completed handoff result:
  `status=handoff_completed`, `verification_passed=true`,
  `rollback_required=false`, false checks `[]`, health critical alerts `0`,
  open orders `0`, and the same 11 open positions recognized.
- Boundary:
  the later handoff enabled the Meridian supervisor and health timers only; it
  did not arm live delta, submit/cancel/test orders, update accepted evidence,
  update `PROJECT_STATE.md`, or approve formal live-trading readiness.

Post-fix serialized read-only precheck:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T120447Z-post-fix-readonly-precheck`
- Acceptance artifact:
  `post_fix_precheck_acceptance.json`
- Result:
  - `precheck_passed=false`
  - only false check after account parser correction:
    `meridian_no_live_delta_observation_state_ready=false`
  - fix summary input passed
  - installed drop-in verifier passed
  - Python path/config probe passed
  - `config_module_file` and `config_root` resolved under
    `/root/meridian_alpha_live_runner/repo`
  - timer list remained `0 timers listed`
  - no related legacy or Meridian service was active
  - legacy and Meridian timers remained disabled
  - Meridian service `ExecStart` used `/usr/bin/env`,
    `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src`, and the absolute
    Meridian handoff-observation config path
  - account and open-order GET reads succeeded
  - `open_order_count=0`
  - `open_position_count=11`
  - no order, cancel, or order-test call was made
  - `accepted_evidence_not_updated=true`
  - `no_cutover_performed=true`
- Blocking state:
  - legacy rollback state is correctly paused/disarmed
  - Meridian runner state is still `paused=true`, `live_delta_armed=false`
  - Meridian latest live-delta action is `disarm-live-delta`
  - the remaining blocker is the pause bit, because the future proof cycle
    requires Meridian `operator_paused=false` with `live_delta_armed=false`

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
  - Meridian `resume` action recorded:
    `20260531T122058369994Z:resume:20260531T122058359406Z-meridian-observation-state-prep`
  - Meridian `disarm-live-delta` action recorded:
    `20260531T122058377227Z:disarm-live-delta:20260531T122058359406Z-meridian-observation-state-prep`
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
  - timer list remained `0 timers listed`
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

Operator-approved handoff apply attempt:

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
  - Meridian health timer and supervisor timer were enabled
  - the Meridian supervisor timer fired and wrote a fresh Meridian supervisor
    artifact under the Meridian runner tree
  - verification failed because the supervisor exited
    `mainnet_live_supervisor_blocked`
  - failure blocker:
    `no_valid_position_reference_under:/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate`
  - the same cycle saw 11 `unexpected_live_position:*` blockers matching the
    known open-position inventory
  - `orders_submitted=0`
  - `fill_count=0`
  - `open_order_count=0`
  - `live_delta_armed=false`
  - `rollback_required=true`
  - `rollback_passed=true`
  - rollback false checks: `[]`
  - final readback listed `0 timers`
  - final readback passed with false checks: `[]`
  - all related legacy and Meridian services were inactive/dead after rollback
  - Meridian rollback kill-switch restored `paused=true`,
    `live_delta_armed=false`
  - `accepted_evidence_updated=false`

## Problem 1: Python Path And Config Resolution

The rolled-back handoff attempt proved that the Meridian health service could
start from the Meridian tree while importing runtime code from the legacy tree:

- script path:
  `/root/meridian_alpha_live_runner/repo/scripts/live_trading/run_hv_balanced_mainnet_health_monitor.py`
- imported runtime code:
  `/root/enhengclaw_live_runner/repo/src/enhengclaw/...`
- failed config resolution:
  `/root/enhengclaw_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml`

Root cause:

- the service used relative script paths and relative `--config` paths
- the Meridian venv was intentionally symlinked to the legacy venv for the
  first migration proof
- `enhengclaw.live_trading.config.ROOT` is computed from the imported module
  file, so a legacy import root makes relative config/artifact paths resolve
  under the legacy repo

Fix package decision:

- install systemd service drop-ins, not replacement base units
- clear each service `ExecStart`
- invoke scripts by absolute Meridian repo paths
- pass the config by absolute Meridian repo path
- run the child process through:
  `PYTHONPATH=/root/meridian_alpha_live_runner/repo/src`
- keep `with-live-env` as the environment wrapper, but override Python path
  after the wrapper using `/usr/bin/env`

The package includes a read-only probe that imports
`enhengclaw.live_trading.config`, prints the module file and resolved root, and
fails unless both resolve to `/root/meridian_alpha_live_runner/repo`.

## Problem 2: Handoff Acceptance Semantics

The previous handoff design required `operator_paused=true` during the proof
cycle. That is incompatible with a successful supervisor/health proof:

- `mainnet_live_supervisor` treats operator pause as a hard blocker
- a paused supervisor writes `mainnet_live_supervisor_blocked`
- the health monitor then reports critical supervisor-status alerts

Decision:

Future Meridian handoff proof should use an explicit no-live-delta observation
state, not `operator_paused=true`, for the Meridian runner.

Required Meridian proof state:

- `operator_paused=false`
- `live_delta_armed=false`
- latest live-delta action is `disarm-live-delta`
- auto-rearm is disabled in the handoff-observation config
- supervisor completes with no order/fill side effects
- health monitor passes with no critical alerts
- open orders remain zero before and after the cycle
- accepted evidence remains unchanged

The legacy runner may remain paused/disarmed as the rollback baseline. The
unpaused requirement applies only to the Meridian proof cycle.

## Package Contents

- Path drop-ins:
  - `systemd-dropins/meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf`
  - `systemd-dropins/meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf`
- Handoff-observation config:
  - `config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml`
- Read-only and rollback helpers:
  - `precheck_meridian_path_resolution_readonly.sh`
  - `verify_meridian_path_dropins.sh`
  - `rollback_meridian_path_dropins_dry_run.sh`
- Review files:
  - `README.md`
  - `CHECKLIST.md`
  - `REVIEW_SUMMARY.md`
  - `PACKAGE_SHA256SUMS.txt`

## Future Remote Fix Apply Boundary

A future remote fix apply window may:

- stage the handoff-observation config under the Meridian repo config directory
- install only the two service drop-ins
- run `systemctl daemon-reload`
- run the read-only verifier
- run the read-only Python path/config probe
- confirm timers remain disabled/inactive

It must not:

- enable or start Meridian timers
- enable or start legacy timers
- arm live delta
- submit, cancel, or test orders
- change strategy, capital, Binance permissions, or secrets
- update `PROJECT_STATE.md`
- update accepted evidence or formal readiness claims

## Cutover Gate

Do not reopen a Meridian timer cutover window until all of these are true:

- the fix package hashes are reviewed
- the drop-ins are applied in a separate approved fix window
- the read-only Python path probe proves imports resolve from the Meridian repo
- the no-live-delta observation semantics are accepted
- a fresh serialized remote precheck passes after the fix

The first three fix gates above are now satisfied by proof root
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_path_fix_apply/20260531T115517Z-meridian-service-path-fix-apply`.
The fresh serialized remote precheck after this fix was run and correctly
returned no-go before the Meridian runner was moved into the
unpaused/no-live-delta observation state. The observation-state preparation
window has now passed, and the fresh serialized read-only precheck after that
state change is green at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T123155Z-post-observation-state-readonly-precheck`.
No timer was enabled or started by that precheck.

The subsequent operator-approved handoff apply attempt proved the service
path/config fix under timer execution, but rolled back because the Meridian
runner did not have the position-reference evidence needed to reconcile the
existing 11 live positions. That position-reference blocker was later fixed by
creating and verifying a Meridian-root equivalent genesis reference.

A later post-reference apply at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff/20260531T140855Z-meridian-timer-handoff-post-reference-apply`
proved a clean timer-created Meridian supervisor cycle with zero orders and
zero fills, then rolled back because the health monitor alerted on older
blocked Meridian supervisor runs still present in its recent-run window.
Rollback returned to `0 timers listed`, no active/enabled related units,
Meridian paused/disarmed state, open orders zero, and the same 11 open
positions. Another handoff attempt is no-go until a separate health-alert
triage/fix window explains that recent-run window behavior and a fresh
serialized read-only precheck passes.

The separate health-alert triage/fix window is recorded in
`docs/MERIDIAN_HEALTH_ALERT_TRIAGE_FIX_WINDOW.md`. It concluded that the health
monitor followed its configured 3-run contract, while the handoff proof contract
requires exactly one timer-created supervisor cycle plus one health cycle. The
local package now narrows only the Meridian handoff-observation proof config to
`mainnet_health_monitor.recent_run_count=1`; default live timer configs keep
their 3-run health window.

Remote health-fix apply later passed at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_health_alert_fix_apply/20260531T151439Z-amended-handoff-observation-config-apply`.
It installed only the amended handoff-observation config, reset the failed
Meridian health service, and ended with `0 timers listed`, no active or enabled
related units, and no handoff/order paths attempted.

A fresh post-health-fix read-only handoff precheck then ran at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T152923Z-post-health-fix-readonly-precheck-rerun`.
It was no-go with exactly one false check:
`meridian_operator_unpaused_for_proof`. The same precheck confirmed the
Meridian position reference still selected the 11 existing live positions, open
orders remained zero, timers remained zero, and no active/enabled related units
were present.

Because that only no-go was the expected rollback pause state, the separate
post-health-fix observation-state re-prep ran at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_observation_state_prep/20260531T153056Z-post-health-fix-observation-state-reprep`.
It passed with false checks `[]`, restored Meridian to
`operator_paused=false`, `live_delta_armed=false`, recorded the latest
live-delta action as `disarm-live-delta`, and still left timers zero with no
active/enabled related units.

The fresh post-reprep read-only handoff precheck then passed at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T153913Z-post-health-fix-reprep-readonly-precheck`.
It had false checks `[]`, observed Meridian `operator_paused=false` and
`live_delta_armed=false`, confirmed the implicit Meridian position monitor
passed with open orders zero and 11 open positions, and left timers zero with
no active/enabled related units. It did not handoff, enable/start timers, start
services, arm live delta, touch order paths, or update accepted evidence. A
separate operator-approved handoff apply window is still required for any timer
ownership change.
