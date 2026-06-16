# Meridian Position Reference Fix Window

Current status: `APPLY_PASSED_POSITION_MONITOR_VERIFIED`

This is a separate fix-window record for the Meridian position-reference
blocker discovered during the rolled-back timer handoff attempt. It does not
authorize timer handoff, live delta, order submission, order cancellation,
order-test calls, accepted-evidence updates, or formal readiness claims.

## Scope

- Target host: `root@203.0.113.10`
- Legacy runner root: `/root/enhengclaw_live_runner`
- Meridian runner root: `/root/meridian_alpha_live_runner`
- Legacy artifact parent:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate`
- Meridian artifact parent:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate`

Goal:

- Make the Meridian runner able to reconcile the existing 11 live positions
  using a valid reference under the Meridian runner root.

Non-goals:

- Do not enable or start Meridian timers.
- Do not restore or start legacy timers.
- Do not arm live delta.
- Do not submit, cancel, or test orders.
- Do not change strategy, capital, risk, Binance permissions, or secrets.
- Do not update `PROJECT_STATE.md`, accepted evidence, or formal readiness
  claims.

## Trigger

The operator-approved Meridian timer handoff attempt wrote a fresh Meridian
supervisor artifact:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_live_supervisor/20260531T124746329564Z-mainnet-live-supervisor/run_summary.json`

That supervisor exited `mainnet_live_supervisor_blocked`.

Blockers included:

- `no_valid_position_reference_under:/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate`
- `unexpected_live_position:AAVEUSDT:-6.4`
- `unexpected_live_position:APTUSDT:-278.5`
- `unexpected_live_position:ARBUSDT:-5150.6`
- `unexpected_live_position:BCHUSDT:-0.581`
- `unexpected_live_position:BNBUSDT:1.1`
- `unexpected_live_position:BTCUSDT:0.012`
- `unexpected_live_position:DOGEUSDT:876.0`
- `unexpected_live_position:ETHUSDT:0.305`
- `unexpected_live_position:FILUSDT:-366.3`
- `unexpected_live_position:UNIUSDT:-261.0`
- `unexpected_live_position:XRPUSDT:197.4`

No order, fill, cancellation, or order-test side effect was observed in the
rolled-back timer handoff attempt.

## Position Reference Contract

`src/enhengclaw/live_trading/live_position_monitor.py` resolves a reference in
this order:

1. Explicit `--reference-run`, if supplied and the path exists.
2. `artifact_root/*-mainnet-single-run` with
   `status == mainnet_single_run_orders_submitted`.
3. `artifact_root.parent/mainnet_delta_execution/*-mainnet-delta-execution`
   with:
   - `run_summary.json.status == mainnet_delta_orders_submitted`
   - `run_summary.json.reconciliation_status == reconciled`
   - `reconciliation.json.status == reconciled`
4. `artifact_root.parent/position_reference/*-genesis-snapshot` with
   `run_summary.json.status` equal to `mainnet_position_genesis_snapshot` or
   `position_genesis_snapshot`.

If no candidate is found, the monitor emits:

`no_valid_position_reference_under:<artifact_root.parent>`

If a live nonzero position is absent from the selected reference, the monitor
emits:

`unexpected_live_position:<symbol>:<amount>`

## Read-Only Inventory

Proof root:

`/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T130527Z-position-reference-readonly-inventory`

Primary artifact:

`position_reference_inventory.json`

Boundary captured by the artifact:

- `timer_enable_start_attempted=false`
- `service_start_attempted=false`
- `reference_copy_attempted=false`
- `reference_generation_attempted=false`
- `accepted_evidence_update_attempted=false`
- `order_or_cancel_attempted=false`

Systemd readback:

- `systemd_timers.txt` listed `0 timers`.
- The filtered systemd unit list contained no active Meridian or legacy timer
  family.
- Historical failed fast-follow service units were visible but no timer handoff
  path was active.

Legacy reference surface:

- Valid candidate count: `128`
- Monitor-selected reference:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution`
- Selected kind: `mainnet_delta_execution`
- Selected position count: `11`
- Selected reference matched the Meridian apply-attempt live-position blockers
  exactly:
  - missing from expected: `[]`
  - extra expected: `[]`
  - mismatches: `[]`

Selected legacy reference hashes:

- `run_summary.json`:
  `06358b761278adfb0c4f1ae9e2d081b1befb6869969f7a5693b30483b092763a`
- `reconciliation.json`:
  `6cb75e48a600afbe2f4ef0bd061509427bb0acd68920e502f1215686511a7edf`
- `account_after.json`:
  `af8377d57d88f7d0d183ac73e6491a8cf491db696e2fe6b065c6b7cadca4fe8c`

Meridian reference surface:

- Valid candidate count: `0`
- Monitor-selected reference: `null`
- Latest Meridian position monitor:
  `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T124746403012Z-mainnet-position-monitor`
- Latest Meridian position monitor status:
  `blocked_live_position_monitor`
- Latest Meridian position monitor blockers included the same missing-reference
  blocker and the same 11 `unexpected_live_position:*` entries.

## Fix Options

### Option A: Migrate Legacy Delta Reference Into Meridian Root

Copy the selected legacy reconciled delta-execution reference into the
Meridian artifact parent under `mainnet_delta_execution/`, preserving the
source files and hashes.

Pros:

- Minimal semantic transformation.
- Uses the exact reference the legacy monitor currently selects.

Cons:

- Copies a legacy run tree into the Meridian tree.
- May preserve legacy absolute paths inside non-consumed metadata.
- Less explicit as a Meridian-named baseline.

### Option B: Generate Meridian Equivalent Genesis Reference

Create a new Meridian-root genesis snapshot under:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/<UTC>-meridian-equivalent-genesis-snapshot`

The directory name must end with `-genesis-snapshot`.

Required files:

- `run_summary.json`
  - `status = mainnet_position_genesis_snapshot`
  - source reference path and hashes
  - account inventory timestamp
  - position count
  - no-order/no-timer boundary fields
- `reference_positions.csv`
  - columns: `symbol,expected_position_amt`
  - exactly the 11 expected positions
- `genesis_snapshot.json`
  - same 11 positions
  - source reference and live-read provenance
- `provenance.json`
  - legacy selected reference path and hashes
  - read-only inventory proof root
  - operator approval identifier for this future fix window
- `manifest.sha256`
  - hashes for the newly generated files

Pros:

- Gives Meridian its own explicit reference root.
- Avoids copying an entire legacy run tree.
- Keeps the legacy delta execution as provenance rather than runtime input.
- Matches the existing monitor contract for genesis snapshots.

Cons:

- Requires a fresh read-only account inventory at apply time.
- Must fail closed if account positions drift from the 11-position inventory
  without a new explanation.

Recommended path: `Option B`.

## Recommended Apply Window

This design was reviewed and then applied in a separate operator-approved
position-reference window. The apply outcome is recorded below.

Precheck:

- Reconfirm `systemctl list-timers --all 'enhengclaw-mainnet*'
  'meridian-alpha-mainnet*'` lists `0 timers`.
- Reconfirm all related legacy and Meridian services are inactive/dead.
- Reconfirm open orders are zero.
- Reconfirm live delta is disarmed.
- Reconfirm no auto-rearm path is active.
- Re-read current live positions from read-only Binance endpoints.
- Re-read the legacy selected reference and hashes.
- Require the current 11 live positions to match the selected legacy reference
  exactly, or stop and write a no-go artifact.

Apply:

- Create exactly one new Meridian-root directory ending
  `-meridian-equivalent-genesis-snapshot`.
- Write `run_summary.json`, `reference_positions.csv`,
  `genesis_snapshot.json`, `provenance.json`, and `manifest.sha256`.
- Do not copy the old legacy run directory.
- Do not update any accepted evidence path.
- Do not enable or start timers.
- Do not start supervisor or health services.
- Do not submit, cancel, or test orders.

Verify:

- Run the Meridian position monitor with explicit `--reference-run` pointing
  to the new genesis snapshot.
- Run the Meridian position monitor again without `--reference-run`, proving
  implicit resolution from the Meridian root.
- Require both monitor runs to exit `passed_live_position_monitor`.
- Require both summaries to have:
  - no `no_valid_position_reference_under:*`
  - no `unexpected_live_position:*`
  - no `position_mismatch:*`
  - `open_order_count=0`
  - `open_position_count=11`
- Reconfirm `0 timers listed` after verification.
- Reconfirm accepted evidence was not updated.

Success artifact:

- A fix-window proof root under:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/`
- A final `position_reference_fix_acceptance.json` with all checks true.

## Rollback

Rollback only touches the newly created Meridian genesis snapshot directory.

If the reference is created but verification fails:

- Move the new directory out of the monitor search path, for example to:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/<window>/rejected_reference/<name>`
- Preserve the rejected files for review.
- Re-run the Meridian position-reference inventory and require the failed
  reference no longer appears as a valid monitor candidate.
- Reconfirm `0 timers listed`.
- Reconfirm open orders remain zero.
- Reconfirm accepted evidence was not updated.

The rollback must not modify the legacy reference, legacy runner root, strategy
config, accepted evidence, or any systemd timer/service enablement.

## Apply Outcome

Design review result:

- `design_review_passed_no_hard_blockers`
- The review found no path that would turn this reference fix into an implicit
  timer handoff.
- The apply window was limited to a Meridian-root equivalent genesis reference
  plus position-monitor verification.

Initial no-apply proof:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T133053Z-meridian-equivalent-genesis-apply`
- Result:
  - `status=failed_no_apply`
  - no Meridian reference was created
  - no rollback was needed
  - the legacy-reference monitor itself passed
  - failure cause was an apply-driver validation bug that treated numeric
    zero fields as absent

Successful apply proof:

- Proof root:
  `/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/20260531T133219Z-meridian-equivalent-genesis-apply`
- Acceptance artifact:
  `position_reference_fix_acceptance.json`
- Executed apply driver:
  `apply_driver.executed.py`
- Executed apply driver sha256:
  `0c61ed95dd78a5ebcdba4f0411bf9b608fb0288d3aa444e7b971b31193cc36a5`
- Acceptance artifact sha256:
  `f5969079a912ac81ce505f8a73a640d0e321f02e502520698cae9ad6b34e6758`
- Result:
  - `status=passed`
  - `passed=true`
  - false checks: `[]`
  - rollback attempted: `false`
  - `project_state_unchanged=true`
  - pre-apply timers zero: `true`
  - post-verify timers zero: `true`
  - timer handoff attempted: `false`
  - timer enable/start attempted: `false`
  - service start attempted: `false`
  - live-delta arm attempted: `false`
  - order submit/cancel/test attempted: `false`
  - accepted-evidence update attempted: `false`

Created Meridian reference:

`/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`

Reference summary:

- `run_summary.json.status=mainnet_position_genesis_snapshot`
- `position_count=11`
- source reference kind: `mainnet_delta_execution`
- source reference:
  `/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/20260531T073949118198Z-mainnet-delta-execution`
- source file hashes:
  - `run_summary.json`:
    `06358b761278adfb0c4f1ae9e2d081b1befb6869969f7a5693b30483b092763a`
  - `reconciliation.json`:
    `6cb75e48a600afbe2f4ef0bd061509427bb0acd68920e502f1215686511a7edf`
  - `account_after.json`:
    `af8377d57d88f7d0d183ac73e6491a8cf491db696e2fe6b065c6b7cadca4fe8c`

Reference manifest:

- `genesis_snapshot.json`:
  `008d67cc93283172ded36fd2689e4692da025a83868bffa3c170289da40fa4c0`
- `provenance.json`:
  `8ef3dd2d9c9aad2e0ed34288c0c7af7de1ea64e40ecf4234846fc44ddced0905`
- `reference_positions.csv`:
  `cd587ec9ef601be66a2e95cdddd83eb46748e73b112c819647d845624a6f9b01`
- `run_summary.json`:
  `a815a3e93eb45f3a541456410e6f23ce3b668978a85ce760ad98a778d1deb8b1`

Position-monitor verification:

- Fresh precheck with explicit legacy reference:
  - artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T133222721761Z-mainnet-position-monitor`
  - status: `passed_live_position_monitor`
- Explicit Meridian reference monitor:
  - artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T133224579338Z-mainnet-position-monitor`
  - status: `passed_live_position_monitor`
- Implicit Meridian-root reference monitor:
  - artifact:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_monitor/20260531T133226319012Z-mainnet-position-monitor`
  - status: `passed_live_position_monitor`
  - selected reference:
    `/root/meridian_alpha_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/position_reference/20260531T133219Z-meridian-equivalent-genesis-snapshot`

## Go/No-Go

Go only if all items are true:

- The operator explicitly approves this position-reference fix apply window.
- The fresh live-position inventory still has the expected 11 positions, or a
  separate inventory triage explains any drift before apply.
- Open orders are zero.
- The selected legacy reference remains readable and hash-checked.
- The current live positions match the selected reference exactly.
- The new Meridian genesis reference is written under the Meridian artifact
  parent only.
- Explicit and implicit Meridian position-monitor runs both pass.
- No timer or service is enabled or started.
- No order, cancel, or order-test call is attempted.
- No accepted evidence path or formal readiness claim is updated.

No-go if any item is true:

- Current positions drift from the selected legacy reference without a separate
  explanation.
- Any open order exists.
- Account or open-order read fails.
- Meridian position monitor still emits `no_valid_position_reference_under:*`.
- Meridian position monitor emits any `unexpected_live_position:*` or
  `position_mismatch:*`.
- Any related timer becomes active.
- Any accepted evidence path changes.

## Next Boundary

The position-reference blocker is fixed for the current 11-position inventory.
A fresh serialized remote read-only handoff precheck was run after this new
Meridian reference was present. It confirmed the reference and position monitor
path, but returned no-go because the Meridian runner remains
`operator_paused=true` after the rollback kill-switch. Do not attempt another
Meridian timer handoff until a separate observation-state preparation restores
Meridian `operator_paused=false`, `live_delta_armed=false`, and a new
serialized read-only handoff precheck passes.

A fresh rerun at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T135612Z-post-reference-readonly-precheck-rerun`
confirmed the same state: the Meridian reference and implicit position monitor
still pass, open orders remain zero, 11 open positions are recognized, timers
remain zero, and the only false check is still
`meridian_operator_unpaused_for_proof`.

After a separate observation-state re-prep, a fresh read-only handoff precheck
at
`/root/meridian_alpha_live_runner/proof_artifacts/meridian_timer_handoff_precheck/20260531T140218Z-post-observation-reprep-readonly-precheck`
passed with false checks `[]`. The Meridian reference still resolved
implicitly, open orders remained zero, 11 open positions were recognized,
timers remained zero, and no cutover or timer enable/start was attempted.
