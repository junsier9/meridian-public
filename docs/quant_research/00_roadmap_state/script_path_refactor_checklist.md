# Script Path Refactor Checklist

`Status: reusable governance checklist`
`Scope: scripts/quant_research path refactors`
`Owner: quant_research_maintainer`

Use this checklist before moving quant-research scripts or splitting a script
lane into a subdirectory. It turns the Phase 5 parallel 1h migration pattern
into a reusable, fail-closed contract.

## When To Use

Use this checklist for any change that moves, renames, wraps, or retires a
`.py` or `.ps1` file under `scripts/quant_research`.

Do not use it as approval to move scheduled-task entrypoints or active public
paths. Those paths require a dry-run and an explicit compatibility decision.

## Checklist

### 1. Dry-run inventory

- Start from a clean or understood worktree with `git status --short`.
- Search path references across `config`, `docs`, `scripts`, `src`, and `tests`.
- Check scheduled manifests, PowerShell runners, imports, subprocess calls,
  README entries, catalog rows, and roadmap references.
- Classify each target as implementation, public entrypoint, scheduled surface,
  compatibility wrapper, historical evidence, or deferred.
- Record blockers before moving files.

### 2. Move design

- Define the destination directory and the exact moved script list.
- Decide which old paths need wrappers before the move.
- Keep scheduled-task surfaces at their public paths unless the scheduled
  manifest and runner contract are updated in the same change.
- Keep research semantics on the implementation row, not on the wrapper row.
- Mark uncertain paths as deferred rather than guessing.

### 2a. Directory admission

- Use `parallel_1h/` only for the separate 1h manipulation/mechanical-flow
  lane.
- Use `legacy_candidates/` only for historical or rejected branch evidence.
- Use `maintenance/` only for remediation, cleanup, contract repair,
  backfill repair, historical invalidation, or migration-support scripts.
- Use `provider_probes/` only for provider capability probes: API coverage,
  credential/capability checks, historical-depth feasibility, free-vs-paid data
  path probes, and provider decision evidence.
- Use `provider_diagnostics/` only for provider validation, provenance,
  concordance, and dataset smoke diagnostics whose main job is checking already
  synced provider artifacts or writing diagnostic evidence.
- Use `provider_leaf_sync_helpers/` only for leaf provider sync helpers with no
  scheduled/config hard reference, no default-entrypoint role, and no active
  script-level caller. Keep this narrower than provider sync pipelines.
- Data-foundation default entrypoints are permanent root-boundary public paths.
  Do not move them into provider directories or split them behind wrappers under
  the normal Phase 5.x helper-cleanup flow.
- Use `feature_panel_tools/` only for cross-sectional feature-panel
  materializers or panel-only feature build helpers that write canonical
  `artifacts/quant_research/features/.../features.csv.gz` outputs.
- Use `deterministic_support/` only for deterministic sample, survival,
  longitudinal-selection, or cycle-support CLIs that delegate to package
  functions and write deterministic cycle evidence under
  `artifacts/quant_research/cycles/...`.
- Use `data_lane_diagnostics/` only for data-lane A/B diagnostics that run
  lane-local quant cycles or benchmark coverage comparisons, such as OHLCV lane
  comparison runners.
- Use `alpha_ontology_cycles/` only for non-default alpha-ontology one-off
  hypothesis-batch cycle runners that process-locally override manifest,
  horizon, candidate, or validation-contract constants.
- Use `report_writers/` only for utility factor-report, admission-report,
  overlay diagnostic, and audit writers whose main job is producing
  `artifacts/quant_research/factor_reports/...` or equivalent report evidence.
- Use `alpha_branch_reports/` only for branch-specific report, event-study,
  admission-report, universe-headroom, or sidecar-review evidence writers whose
  authority is an alpha-branch document under `docs/quant_research/03_alpha_branches`.
- Use `historical_h10d_diagnostics/` only for superseded or historical h10d
  diagnostic implementations whose outputs remain useful as evidence but should
  not be current roadmap starting points.
- Use `h10d_current_diagnostics/` only for active support tools that explain,
  audit, or lifecycle-check the current h10d/lsk3 evidence chain and are not
  default entrypoints, config-defined guards, public baseline validation
  surfaces, module-import-dependent evaluators, or historical evidence.
- Use `m3_mf_spk_support/` only for M3/MF/SP-K branch-support helpers that are
  not stage0/quarantine implementations, strict-falsification scripts, h10d
  surfaces, provider probes, data-sync pipelines, scheduled surfaces, or
  default entrypoints.
- Use `news_dataset_processors/` only for crypto-news dataset ingestion,
  LLM-structuring, or adjudication utilities. Do not use it for raw market-data
  sync pipelines, provider probes, scheduled runners, or default research
  cycles.
- Use `coinglass_diagnostics/` only for CoinGlass capability, coverage, or
  reset-report diagnostics. Do not use it for CoinGlass sync/default
  entrypoints, quarantine scripts, provider-generic diagnostics already covered
  by `provider_diagnostics/`, or h10d-parent historical scripts.
- Use `coinglass_quarantine/` only for CoinGlass R-lane strict-validation or
  spot-concordance quarantine implementations. Do not use it for CoinGlass
  sync/default entrypoints, diagnostics, provider probes, data-foundation
  refresh pipelines, or h10d-parent historical scripts.
- Use `alpha_stage0_quarantine/` only for alpha stage-0 or strict-falsification
  implementations that are quarantined or not admitted to the current
  roadmap. Do not use it for branch reports, utility report writers, support
  helpers, data-sync pipelines, h10d current-line surfaces, scheduled
  entrypoints, or default research-cycle entrypoints.
- Phase 5.20 admits only the four-script M3.2 boundary/sidecar subcluster into
  `alpha_stage0_quarantine/`; this does not approve M3.1 or M3.3 movement.
- Phase 5.21 admits only the two-script M3.1 options subcluster into
  `alpha_stage0_quarantine/`; keep the active CoinGlass full-stack sync caller
  on the root shim unless a separate data-foundation refactor is approved.
- Phase 5.22 admits only the six-script M3.3 event-state subcluster into
  `alpha_stage0_quarantine/`; keep it as one event tape/event-state/strict
  batch with module-compatible root shims and a package-import rewrite for the
  M3/MF/SP-K support A/B caller. This does not approve broader M3/MF movement.
- Do not use `maintenance/` for factor reports, provider capability probes,
  data enrichment, scheduled wrappers, or current default entrypoints.
- Do not move h10d current-line diagnostics, stage0 or quarantine evaluators,
  provider probes, data-sync pipelines, scheduled surfaces, or current default
  entrypoints into `report_writers/`; those need their own dry-run and target
  directory decision.
- Do not move `evaluate_*_stage0.py`, strict-falsification scripts, h10d
  current-line diagnostics, provider probes, data-sync pipelines, scheduled
  surfaces, or current default entrypoints into `alpha_branch_reports/`.
- Do not move current h10d default entrypoints, active h10d hardening scripts,
  or module-import-dependent h10d evaluators into `historical_h10d_diagnostics/`
  without a dedicated dry-run and import compatibility plan.
- Do not move current h10d diagnostic/support tools into
  `historical_h10d_diagnostics/`; use `h10d_current_diagnostics/` only after a
  dedicated dry-run proves they are not public entrypoints or guards.
- If a moved script is imported as a module by another root script, preserve
  module-level compatibility with a package-import rewrite or a root re-export
  shim; a CLI-only wrapper is not sufficient.
- For alpha-branch event-study writers with a known in-repo diagnostic caller,
  prefer rewriting the caller to the moved package path plus keeping only a
  thin root CLI wrapper. Use a root re-export shim only when external module
  import compatibility is explicitly required.
- Do not move provider sync pipelines, scheduled provider runners, or data
  refresh entrypoints into `provider_probes/`; those need a separate dry-run.
- Do not move provider sync pipelines, scheduled provider runners, data refresh
  entrypoints, or provider capability probes into `provider_diagnostics/`.
- Do not move provider capability probes, scheduled provider runners, default
  data refresh entrypoints, CoinGlass full-stack sync, or h10d boundaries into
  `provider_leaf_sync_helpers/`.
- Do not treat data-foundation default entrypoints as future-wrapper candidates
  without a new owner-approved boundary redesign. Keep their root paths as the
  operational contract.
- Do not move provider sync, provider diagnostics, report writers, h10d
  surfaces, alpha stage-0/quarantine scripts, scheduled entrypoints, default
  entrypoints, or M3/MF/SP-K support scripts into `feature_panel_tools/`.
- Do not move provider sync, provider diagnostics, feature-panel materializers,
  report writers, h10d surfaces, alpha stage-0/quarantine scripts, scheduled
  entrypoints, default entrypoints, or public research-cycle entrypoints into
  `deterministic_support/`.
- Do not move provider probes, provider diagnostics, data-sync pipelines,
  default entrypoints, or report writers into `data_lane_diagnostics/`.
- Do not move checked-in config materializers, default research-cycle
  entrypoints, M3/MF/SP-K support scripts, h10d proof/guard surfaces, report
  writers, provider tools, or generic alpha utilities into
  `alpha_ontology_cycles/`.
- Do not move CoinGlass sync/default entrypoints, CoinGlass diagnostics,
  provider probes, or h10d-parent historical scripts into
  `coinglass_quarantine/`.
- Do not move an entire stage-0 cluster into `alpha_stage0_quarantine/` in one
  batch when tests, active callers, or sibling imports use root module paths;
  split by subcluster and preserve module-compatible root shims.
- If a utility script is diagnostic, exporter, report writer, or dataset
  processor rather than maintenance, dry-run a more specific target directory
  instead of defaulting it into `maintenance/`.

### 2b. Batch sizing

- Use single-script dry-run, plan, and implementation for the first member of a
  new target directory or when the target directory boundary is still being
  defined.
- After a target directory has an approved admission rule and at least one
  successful wrapper migration, group later low-risk scripts by the same target
  directory, wrapper style, and risk class.
- Prefer batches of 3-8 scripts for established directories when no
  scheduled/config hard reference, active root-script import, or semantic
  boundary expansion is present.
- Keep medium/high-risk outliers as single-script or dependent-pair phases.

### 3. Implementation rules

- Move only the intended scripts for the current phase.
- Rewrite repo-root discovery so moved scripts still resolve the same project
  root from their new depth.
- Rewrite intra-repo imports to package-style imports when possible.
- For compatibility wrappers, preserve the old CLI path and keep wrapper logic
  minimal. Forward `sys.argv[1:]` when the moved implementation exposes
  `main(argv)`; use `runpy.run_module(..., run_name="__main__")` when the
  moved implementation parses `sys.argv` internally from a no-arg `main()`.
- When tests or callers import private helper functions from the old root
  module path, use a root re-export shim and keep the implementation in the new
  package path.
- Do not delete historical scripts in a path-refactor commit.

### 4. Catalog and README semantics

- Keep one catalog row per `.py` or `.ps1` file.
- Catalog compatibility wrappers as `status = supporting` and
  `run priority = supporting_tool`.
- Catalog moved implementations with their real research lifecycle status.
- Keep `safe-to-move = no` for public wrappers and scheduled entrypoints.
- Update summary counts and README counts in the same change.

### 5. Verification

- Run `python -m compileall -q` on moved implementation directories and wrapper
  files.
- Smoke each wrapper from outside the repo cwd with an absolute path and
  `--help` or an equivalent non-mutating command.
- Run `python -m pytest tests\test_static_contracts.py -q`.
- If scheduled manifests, runners, or script catalogs changed, run
  `python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q`.
- Run Markdown link checking when docs or paths were changed.
- Run `git diff --check`.

### 6. Commit boundary

- Keep dry-run artifacts, script moves, and catalog semantics in separate
  commits when the risk profile differs.
- The commit summary should name the moved lane and whether wrappers were kept.
- The final review should explicitly state which public paths still work.

## Minimum Done Criteria

- The catalog covers every script file exactly once.
- Old public CLI paths either still work through wrappers or are documented as
  intentionally retired.
- Summary counts do not count wrappers as research implementations.
- Static contracts pass.
- Any deferred move has a named blocker.
