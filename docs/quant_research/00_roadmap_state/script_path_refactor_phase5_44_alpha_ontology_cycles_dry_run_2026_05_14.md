# Phase 5.44 Alpha Ontology Cycles Dry-Run

`Status: read-only dry-run baseline`
`Date: 2026-05-14`
`Scope: alpha ontology cycle support trio under scripts/quant_research root`

## Decision

No script move is approved by this artifact.

Create `scripts/quant_research/alpha_ontology_cycles/` only if the next
implementation is explicitly scoped to alpha-ontology non-default cycle support.
The directory is justified, but it must not become a generic alpha ontology,
factor-weight, report-writer, h10d, or M3/MF/SP-K drawer.

Recommended first implementation, if approved:

1. Move only the two one-off cycle runners into
   `scripts/quant_research/alpha_ontology_cycles/`.
2. Keep the old root paths as compatibility wrappers because current support
   scripts call the old root path via subprocess and one historical diagnostic
   imports a helper from the horizon runner's root module path.
3. Defer `compute_alpha_ontology_v3_weights.py` until the owner decides whether
   checked-in config generation belongs behind the same cycle-support wrapper
   boundary or should stay root as a public config materializer.

## Evidence Commands

Read-only commands used for this review:

```powershell
git status --short
rg -n "compute_alpha_ontology_v3_weights|run_alpha_ontology_horizon_cycle_oneoff|run_alpha_ontology_v1_cycle_oneoff|alpha_ontology_v3_weights|alpha ontology|alpha_ontology" config docs scripts src tests -g "!artifacts/**"
rg -n "run_alpha_ontology_horizon_cycle_oneoff\.py|run_alpha_ontology_v1_cycle_oneoff\.py|compute_alpha_ontology_v3_weights\.py" scripts src tests config docs -g "!artifacts/**"
rg -l "run_alpha_ontology_horizon_cycle_oneoff\.py" scripts -g "!artifacts/**"
rg -l "run_alpha_ontology_v1_cycle_oneoff\.py" scripts -g "!artifacts/**"
rg -l "compute_alpha_ontology_v3_weights\.py" scripts src tests -g "!artifacts/**"
python scripts\quant_research\compute_alpha_ontology_v3_weights.py --help
python scripts\quant_research\run_alpha_ontology_horizon_cycle_oneoff.py --help
python scripts\quant_research\run_alpha_ontology_v1_cycle_oneoff.py --help
```

Current worktree boundary at review time: only local untracked generated
artifacts under `artifacts/quant_research/2026-05-14...` plus this governance
artifact work. Generated artifacts remain outside versioned governance.

## Script Inventory

| script | current catalog stance | role | hard references | artifact/config outputs | risk | dry-run recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py` | `utilities_and_reports` / `supporting` / `supporting_tool` / `yes-with-wrapper` | Horizon-flexible one-off runner for non-default alpha-ontology hypothesis-batch cycles. Monkey-patches `hypothesis_batch` manifest/horizon constants and, for h10d, `validation_contract` path/version constants. | 11 script files reference the old root path as a subprocess target; `historical_h10d_diagnostics/audit_coinglass_h10d_parent_rebaseline.py` imports `_patch_hypothesis_batch_for_variant` from the old root module path; docs and `threshold_provenance.md` describe the behavior. | Hypothesis-batch cycle artifacts under `artifacts/quant_research/hypothesis_batches/...` and experiment artifacts under `artifacts/quant_research/experiments/...`. | high | Eligible for `alpha_ontology_cycles/` only with a root compatibility wrapper that also re-exports `_patch_hypothesis_batch_for_variant`. |
| `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py` | `utilities_and_reports` / `deprecated_candidate` / `historical_do_not_start_here` / `yes-with-wrapper` | Historical v1/lsk3 one-off runner. Monkey-patches `hypothesis_batch` manifest constants for replay/evidence. | No script import callers found. `threshold_provenance.md` documents it heavily. `run_alpha_ontology_horizon_cycle_oneoff.py` docstring names it as the variant it extends. | Historical hypothesis-batch and experiment artifacts. | medium | Eligible for the same directory, but keep catalog historical/do-not-start-here semantics. |
| `scripts/quant_research/compute_alpha_ontology_v3_weights.py` | `utilities_and_reports` / `supporting` / `supporting_tool` / `yes-with-wrapper` | Deterministic Bayesian-IR weight materializer for alpha-ontology v3 score weights. | No script import callers found. `src/enhengclaw/quant_research/features.py` points users to the root path when the checked-in weights file is missing. `threshold_provenance.md` records it as the generator for `config/quant_research/alpha_ontology_v3_weights.json`. | Writes checked-in config by default: `config/quant_research/alpha_ontology_v3_weights.json`. | medium-high | Deferred from the first move. It is related to alpha-ontology cycles but is a config materializer, not a cycle runner. |

## Caller Compatibility

`run_alpha_ontology_horizon_cycle_oneoff.py` is the load-bearing compatibility
path. The following scripts reference the root path by filename, not by package
import:

- `scripts/quant_research/evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_short_replacement.py`
- `scripts/quant_research/historical_h10d_diagnostics/evaluate_v6_h10d_post_pump_short_overlay.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_mf13_tron_cross_sectional_gate_increment.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_mf14_cross_sectional_gate_increment.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_mf13_tron_regime_gate_ab.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_stablecoin_flow_interaction_cycle_increment.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_post_pump_stall_cycle_increment.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_mf14_regime_gate_ab.py`
- `scripts/quant_research/m3_mf_spk_support/evaluate_stablecoin_overlay_cycle_increment.py`

One root-module import was also found:

- `scripts/quant_research/historical_h10d_diagnostics/audit_coinglass_h10d_parent_rebaseline.py`
  imports `_patch_hypothesis_batch_for_variant` from
  `scripts.quant_research.run_alpha_ontology_horizon_cycle_oneoff`.

Implication: a future implementation can avoid caller rewrites only if the old
root path remains an executable wrapper that forwards argv to the moved
implementation and the horizon root wrapper also re-exports
`_patch_hypothesis_batch_for_variant`. If the root wrapper is not executable
through subprocess, the M3/MF/SP-K support surface breaks. If it does not
re-export the helper, the historical h10d parent rebaseline diagnostic breaks.

## Directory Boundary

Allowed in `alpha_ontology_cycles/`:

- non-default alpha-ontology hypothesis-batch cycle runners;
- process-local monkey-patch runners that intentionally override manifest,
  horizon, or validation-contract constants for one-off evidence collection;
- implementation files whose old root paths remain compatibility wrappers.

Not allowed in `alpha_ontology_cycles/`:

- default research-cycle entrypoints such as `run_quant_hypothesis_batch_cycle.py`
  or `run_quant_research_cycle.py`;
- active h10d proof, guard, or baseline validation surfaces;
- M3/MF/SP-K support scripts, stage-0/quarantine scripts, or historical h10d
  diagnostics;
- provider sync, provider diagnostics, scheduled runners, or data-foundation
  default entrypoints;
- generic alpha reports, factor report-card authority, or report writers;
- checked-in config materializers unless separately approved.

## Wrapper Strategy

If implementation is approved for the two runners:

- keep root wrappers at:
  - `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py`
  - `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py`
- wrappers should be thin `runpy.run_module(..., run_name="__main__")` or
  direct `main(sys.argv[1:])` forwarders;
- the horizon wrapper must also re-export `_patch_hypothesis_batch_for_variant`
  from the moved implementation for the historical h10d parent rebaseline
  diagnostic;
- moved implementations must recompute `ROOT` correctly from the deeper
  directory, likely `SCRIPT_DIR.parents[2]` instead of `SCRIPT_DIR.parents[1]`;
- catalog rows for wrappers must stay `supporting_tool` and `safe-to-move = no`;
- moved implementation rows should preserve lifecycle semantics:
  - horizon runner: `supporting` / `supporting_tool`;
  - v1 runner: `deprecated_candidate` / `historical_do_not_start_here`.

If `compute_alpha_ontology_v3_weights.py` is later approved:

- keep the root path as the documented config-generation entrypoint;
- preserve `--out` behavior exactly, especially the default checked-in config
  path;
- update `src/enhengclaw/quant_research/features.py` user-facing path guidance
  only if the root wrapper is no longer the recommended visible path;
- run an explicit `--print-only` smoke to avoid rewriting config during
  compatibility tests.

## Required Link And Doc Updates For A Future Move

For the two-runner move:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `config/quant_research/threshold_provenance.md`
- `docs/quant_research/00_roadmap_state/algorithm_choices.md`
- `docs/quant_research/00_roadmap_state/data_utilization_roadmap.md`
- any dry-run or owner-review artifact that still lists the old paths as
  root implementation paths

For `compute_alpha_ontology_v3_weights.py`, additionally inspect and possibly
update:

- `src/enhengclaw/quant_research/features.py`
- `config/quant_research/threshold_provenance.md`
- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`

## Validation Commands For A Future Implementation

Minimum implementation validation:

```powershell
python scripts\quant_research\run_alpha_ontology_horizon_cycle_oneoff.py --help
python scripts\quant_research\run_alpha_ontology_v1_cycle_oneoff.py --help
python -B -c "from scripts.quant_research.run_alpha_ontology_horizon_cycle_oneoff import _patch_hypothesis_batch_for_variant; print(_patch_hypothesis_batch_for_variant.__name__)"
python -B -c "import scripts.quant_research.alpha_ontology_cycles.run_alpha_ontology_horizon_cycle_oneoff as m; print(m.ROOT); print(m.SRC); print(m._HORIZON_CONTRACT_PATHS[10])"
python -m compileall scripts\quant_research\run_alpha_ontology_horizon_cycle_oneoff.py scripts\quant_research\run_alpha_ontology_v1_cycle_oneoff.py scripts\quant_research\alpha_ontology_cycles
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -q
git diff --check
```

If `compute_alpha_ontology_v3_weights.py` is included later, add:

```powershell
python scripts\quant_research\compute_alpha_ontology_v3_weights.py --help
python scripts\quant_research\compute_alpha_ontology_v3_weights.py --print-only
python -m compileall scripts\quant_research\compute_alpha_ontology_v3_weights.py
```

Use `--print-only` for smoke validation so the test does not rewrite
`config/quant_research/alpha_ontology_v3_weights.json`.

## Deferred

- `compute_alpha_ontology_v3_weights.py` remains deferred from the first
  implementation batch because it writes checked-in config and is not a cycle
  runner.
- Do not move the active public research-cycle defaults.
- Do not move M3/MF/SP-K callers as part of this phase; root wrapper
  compatibility is the intended strategy for them.
- Do not create a broader `alpha_ontology/`, `cycle_tools/`, or `support/`
  directory.

## Recommended Next Step

Write a Phase 5.45 implementation plan for only the two one-off runners, with
`compute_alpha_ontology_v3_weights.py` explicitly deferred unless the owner
approves adding config materializers to `alpha_ontology_cycles/`.
