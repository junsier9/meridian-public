# Phase 5.35 Report Writers Batch 2 Dry-Run

`Status: read-only dry-run baseline`
`Date: 2026-05-14`
`Scope: established-directory low-risk batch after Phase 5.34`
`Target directory under review: scripts/quant_research/report_writers/`

## Phase 5.34 Post-Commit Review

Baseline commit reviewed: `c801e01 Move deterministic daily sample behind wrapper`.

Findings:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py` is a thin
  root CLI wrapper. It only restores `ROOT` and `SRC` on `sys.path`, imports
  `main` from `scripts.quant_research.deterministic_support`, and forwards
  `sys.argv[1:]`.
- `scripts/quant_research/deterministic_support/run_quant_deterministic_daily_sample.py`
  preserves the original CLI parser and updates repository-root discovery to
  the new script depth.
- No data-foundation provider sync, scheduled entrypoint, feature-panel, report
  writer, h10d, alpha stage-0, or public research-cycle semantics were pulled
  into `deterministic_support/`.
- `tests/test_static_contracts.py` passed after the Phase 5.34 commit.

Residual risk: low. The only residual risk is external callers relying on file
identity rather than the root CLI path; the public root path remains available.

## Selection Method

Per `script_path_refactor_checklist.md` section 2b, this phase switches from
single-file migrations to a small batch because `report_writers/` already has:

- an approved directory admission rule;
- a successful first-batch wrapper migration;
- existing catalog and README semantics for moved implementations plus root
  compatibility wrappers.

The batch size is capped at 3 because this pass is the first reuse of the new
batch-sizing rule after Phase 5.34.

## Low-Risk Batch

Move these implementation files to `scripts/quant_research/report_writers/` and
keep root CLI wrappers:

| script | caller/config/scheduled scan | target rationale | wrapper strategy |
| --- | --- | --- | --- |
| `scripts/quant_research/compute_stablecoin_issuance_velocity_overlay_candidate.py` | no Python caller, no config or scheduled hard reference; references are governance docs/catalog only | overlay candidate summary writer; report evidence rather than data sync or provider probing | thin root wrapper forwarding `sys.argv[1:]` to moved `main(argv)` |
| `scripts/quant_research/diagnose_shadow_vs_cycle.py` | no Python caller, no config or scheduled hard reference; `threshold_provenance.md` cites the public root CLI path | diagnostic evidence writer for a known shadow-vs-cycle report gap | thin root wrapper preserving old no-arg CLI behavior; moved implementation keeps no-arg `main()` |
| `scripts/quant_research/validate_week_2_exit.py` | no Python caller, no config or scheduled hard reference; `threshold_provenance.md` cites the public root CLI path | admission/exit-gate report writer; writes equivalent report evidence under `artifacts/quant_research/week_2_exit_validation/...` | thin root wrapper forwarding `sys.argv[1:]` to moved `main(argv)` |

## Explicitly Deferred Nearby Candidates

| script | reason |
| --- | --- |
| `scripts/quant_research/run_quant_ohlcv_lane_ab.py` | data-foundation lane comparison runner, not clearly a report writer; keep for a later data-foundation diagnostics decision. |
| `scripts/quant_research/factor_report_card.py` | already called out as deferred in the Phase 5.4 report-writer pass; higher centrality and broader references. |
| `scripts/quant_research/compute_alpha_ontology_v3_weights.py` | writes config-like weights and is named by package-level guidance; do not classify as a plain report writer without a separate dry-run. |
| `scripts/quant_research/export_passed_alphas_to_workbench.py` | exporter/workbench boundary, not a factor-report writer. Needs its own target decision if moved. |
| `scripts/quant_research/run_alpha_ontology_*_cycle_oneoff.py` | one-off cycle runners with inter-script dependency risk; not a low-risk report-writer batch. |
| `scripts/quant_research/run_quantagent_shadow_proposal_cycle.py` | test and agent-cycle semantics need a separate caller/compatibility review. |
| h10d `evaluate_v6_h10d_post_pump_*` scripts | module-import-dependent h10d cluster; not a low-risk `historical_h10d_diagnostics/` or `report_writers/` batch. |

## Required Implementation Updates

- Move only the three selected `.py` implementation files.
- Create three root compatibility wrappers.
- Patch moved `ROOT` discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`.
- Keep `threshold_provenance.md` public command references unchanged because
  root wrappers preserve those paths.
- Update `quant_research_script_catalog.md` with one wrapper row and one moved
  implementation row for each target.
- Update README counts and Path Policy.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\report_writers scripts\quant_research\compute_stablecoin_issuance_velocity_overlay_candidate.py scripts\quant_research\diagnose_shadow_vs_cycle.py scripts\quant_research\validate_week_2_exit.py
python scripts\quant_research\compute_stablecoin_issuance_velocity_overlay_candidate.py --help
python scripts\quant_research\validate_week_2_exit.py --help
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

For `diagnose_shadow_vs_cycle.py`, use compile/import validation rather than
`--help`; the legacy script had no argparse surface and reads historical v83
artifacts when executed.

## Decision

Approved for a separate Phase 5.35 implementation commit:

- move the three selected report/evidence writer implementations;
- keep all three root CLI paths;
- do not touch `run_quant_ohlcv_lane_ab.py`, `factor_report_card.py`,
  alpha-ontology cycle runners, or h10d module-import-dependent scripts in this
  phase.
