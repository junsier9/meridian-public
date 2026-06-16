# Phase 5.45 Alpha Ontology Cycles Implementation Plan

`Status: implementation plan`
`Date: 2026-05-14`
`Scope: two alpha-ontology one-off cycle runners`

## Decision

Approve a narrow implementation plan for the two alpha-ontology one-off cycle
runners only:

- `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py`
- `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py`

Target directory:

- `scripts/quant_research/alpha_ontology_cycles/`

This plan does not approve moving `compute_alpha_ontology_v3_weights.py`.

## Directory Contract

`alpha_ontology_cycles/` is only for non-default alpha-ontology hypothesis-batch
cycle support:

- one-off runners that process-locally override `hypothesis_batch` manifest,
  candidate, horizon, or source constants;
- one-off runners that process-locally override validation-contract paths for
  horizon-specific evidence collection;
- implementation files whose old root paths remain compatibility wrappers.

It must not contain default research-cycle entrypoints, h10d public proof or
guard surfaces, M3/MF/SP-K support scripts, stage-0/quarantine scripts,
historical h10d diagnostics, provider sync/probe/diagnostic scripts, report
writers, factor report-card authority, or checked-in config materializers.

## Move Set

Move:

- `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py`
  to
  `scripts/quant_research/alpha_ontology_cycles/run_alpha_ontology_horizon_cycle_oneoff.py`
- `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py`
  to
  `scripts/quant_research/alpha_ontology_cycles/run_alpha_ontology_v1_cycle_oneoff.py`

Do not move:

- `scripts/quant_research/compute_alpha_ontology_v3_weights.py`

## Compatibility Strategy

Keep root compatibility wrappers at the old paths:

- `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py`
- `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py`

The `v1` root wrapper can be CLI-only:

- insert `ROOT` and `SRC` into `sys.path`;
- import `main` from the moved implementation;
- forward `sys.argv[1:]`;
- exit with the moved implementation's return code.

The `horizon` root wrapper must be a thin module-compatible shim:

- insert `ROOT` and `SRC` into `sys.path`;
- import `main` and `_patch_hypothesis_batch_for_variant` from the moved
  implementation;
- forward CLI execution to `main(sys.argv[1:])`;
- keep `_patch_hypothesis_batch_for_variant` available at the old module path.

Reason: `scripts/quant_research/historical_h10d_diagnostics/audit_coinglass_h10d_parent_rebaseline.py`
imports `_patch_hypothesis_batch_for_variant` from
`scripts.quant_research.run_alpha_ontology_horizon_cycle_oneoff`.

Do not rewrite the 11 subprocess callers in this phase. Their root-path calls
remain compatible through the root wrapper.

## Implementation Edits

In both moved implementations, change root discovery from:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
```

to:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
```

Keep `ROOT` before `SRC` in `sys.path`. Do not change CLI arguments,
manifest-validation behavior, monkey-patch behavior, stdout/stderr behavior, or
exit-code behavior.

## Documentation Updates

Update:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_phase5_44_alpha_ontology_cycles_dry_run_2026_05_14.md`

Catalog semantics:

- root wrapper rows: `status = supporting`, `run priority = supporting_tool`,
  `safe-to-move = no`;
- moved horizon runner row: `status = supporting`, `run priority =
  supporting_tool`, `safe-to-move = yes-with-wrapper`;
- moved v1 runner row: `status = deprecated_candidate`, `run priority =
  historical_do_not_start_here`, `safe-to-move = yes-with-wrapper`;
- `compute_alpha_ontology_v3_weights.py` stays root and deferred.

Do not rewrite historical provenance as if old evidence originally used the new
directory. When updating lineage docs, distinguish old root commands that still
work from the current moved implementation path.

## Verification Commands

No-cycle smoke:

```powershell
python -B scripts\quant_research\run_alpha_ontology_horizon_cycle_oneoff.py --help
python -B scripts\quant_research\run_alpha_ontology_v1_cycle_oneoff.py --help
python -B scripts\quant_research\alpha_ontology_cycles\run_alpha_ontology_horizon_cycle_oneoff.py --help
python -B scripts\quant_research\alpha_ontology_cycles\run_alpha_ontology_v1_cycle_oneoff.py --help
python -B -c "from scripts.quant_research.run_alpha_ontology_horizon_cycle_oneoff import _patch_hypothesis_batch_for_variant; print(_patch_hypothesis_batch_for_variant.__name__)"
python -B -c "import scripts.quant_research.alpha_ontology_cycles.run_alpha_ontology_horizon_cycle_oneoff as m; print(m.ROOT); print(m.SRC); print(m._HORIZON_CONTRACT_PATHS[10])"
```

Static and targeted tests:

```powershell
python -m compileall scripts\quant_research\run_alpha_ontology_horizon_cycle_oneoff.py scripts\quant_research\run_alpha_ontology_v1_cycle_oneoff.py scripts\quant_research\alpha_ontology_cycles
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -q
git diff --check
```

Reference audit:

```powershell
rg -n "run_alpha_ontology_horizon_cycle_oneoff\.py|run_alpha_ontology_v1_cycle_oneoff\.py|compute_alpha_ontology_v3_weights\.py|alpha_ontology_cycles|from scripts\.quant_research\.run_alpha_ontology_horizon_cycle_oneoff" scripts src tests config docs -g "!artifacts/**"
```

## Forbidden In This Phase

- Do not move `compute_alpha_ontology_v3_weights.py`.
- Do not edit `config/quant_research/alpha_ontology_v3_weights.json`.
- Do not run an actual hypothesis-batch cycle.
- Do not generate new `artifacts/quant_research/hypothesis_batches/...` or
  `artifacts/quant_research/experiments/...` outputs.
- Do not move default research-cycle entrypoints.
- Do not move M3/MF/SP-K support callers or historical h10d diagnostics.
- Do not weaken the root-module helper import compatibility.
- Do not expand `alpha_ontology_cycles/` into a generic utility directory.

## Done Criteria

Phase 5.45 is complete only when:

- both moved implementations exist under `alpha_ontology_cycles/`;
- both old root paths remain executable;
- the horizon root shim re-exports `_patch_hypothesis_batch_for_variant`;
- moved implementations resolve `ROOT`, `SRC`, and h10d validation-contract
  paths to the repo root, not to `scripts/`;
- the 11 subprocess callers remain compatible through the root wrapper;
- catalog and README distinguish wrappers from implementations;
- `compute_alpha_ontology_v3_weights.py` remains root/deferred;
- compileall, no-cycle smoke, targeted tests, static contracts, and
  `git diff --check` pass.

## Next Step

Execute the two-runner move as an independent Phase 5.45 implementation commit
only after this plan is accepted as the migration contract.
