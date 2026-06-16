# Phase 5.19 M3 High-Risk Dry-Run

`Status: read-only high-risk dry-run`
`Date: 2026-05-13`
`Scope: M3.1 / M3.2 / M3.3 root stage-0 and falsification scripts`

This artifact is a movement plan only. It does not approve or execute script
moves. The goal is to make the M3 dependency shape explicit before deciding
whether any subset should enter `alpha_stage0_quarantine/`.

## Decision

- No scripts moved in Phase 5.19.
- M3 remains a high-risk migration family because the clusters contain
  cross-script imports, test imports, branch-report links, and at least one
  active data-foundation caller.
- `alpha_stage0_quarantine/` is still the right semantic destination only for
  M3 scripts that are branch-specific stage-0, falsification, or sidecar
  evidence writers.
- M3 current/default entrypoints, scheduled surfaces, guards, and data-sync
  pipelines must stay out of `alpha_stage0_quarantine/`.
- First implementation candidate, if owner-approved: M3.2 as a single
  boundary/sidecar batch. It has dense internal imports but no direct
  non-test active caller found in this scan.
- M3.1 should not move before choosing the caller strategy for
  `sync_coinglass_full_stack_foundation.py`.
- M3.3 should move last, if at all, because it is the widest event-state
  dependency hub and already interacts with `m3_mf_spk_support/`.

## Non-Movement Guarantee

Phase 5.19 is read-only by design:

- Do not move scripts.
- Do not add root wrappers.
- Do not rewrite imports.
- Do not rewrite test imports.
- Do not rewrite command examples.
- Only this dry-run artifact and the governance index may change.

## Target Directory Boundary

Candidate destination, if later approved:

- `scripts/quant_research/alpha_stage0_quarantine/`

The directory may contain branch-specific stage-0 evaluators, falsification
writers, and branch evidence utilities that are not default runtime entrypoints.
It must not absorb:

- h10d current-line diagnostics.
- historical h10d diagnostics.
- provider probes or provider sync pipelines.
- scheduled entrypoints.
- data-sync pipelines.
- default guards, promotion guards, or baseline parent surfaces.
- broad M3 orchestration that should remain discoverable as a current line.

## Candidate Inventory

| Cluster | Candidate scripts | Internal imports | Non-test callers found | Direct tests found | Docs links found | Risk | Dry-run outcome |
|---|---|---|---|---|---|---|---|
| M3.1 options regime | `audit_m3_1_options_regime_stage0.py`; `evaluate_m3_1_options_volume_shock_veto_falsification.py` | Veto imports audit; audit imports h10d SP-K parent | `scripts/quant_research/sync_coinglass_full_stack_foundation.py` imports audit symbols | 2 | M3.1 branch docs plus historical worktree plan | High | Defer implementation until caller strategy is chosen |
| M3.2 boundary activation | `evaluate_m3_2_boundary_activation_stage0.py`; `evaluate_m3_2_boundary_activation_falsification.py`; `evaluate_m3_2_canonical_parent_stage0.py`; `evaluate_m3_2_etf_onchain_sidecar_falsification.py` | Falsification imports stage0; ETF/onchain sidecar imports stage0 and falsification; stage0/canonical parent import h10d SP-K parent | None outside tests/docs found | 4 | M3.2 branch docs plus historical worktree plan | Medium-high | Best first candidate if owner approves one high-risk batch |
| M3.3 event state | `evaluate_m3_3_event_tape_spk_stage0.py`; `evaluate_m3_3_event_state_feature_stage0.py`; `evaluate_m3_3_strict_event_state_stage0.py`; `evaluate_m3_3_robustness_v2_stage0.py`; `evaluate_m3_3_mf01_confirmation_stage0.py`; `evaluate_m3_3_hype_chatter_gate_stage0.py` | Feature/strict/robustness/MF01/hype depend on event tape and strict/event features; several import h10d SP-K parent | `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py` imports event tape and event features | 5 found; no dedicated hype test found | M3.3 branch docs plus MF01 retest docs and historical worktree plan | High | Move last, only as one coherent event-state batch |

## Import Rewrite Plan

### M3.1

If approved later, move both scripts together:

- `scripts/quant_research/audit_m3_1_options_regime_stage0.py`
- `scripts/quant_research/evaluate_m3_1_options_volume_shock_veto_falsification.py`

Implementation import rewrites:

- In moved `audit_m3_1_options_regime_stage0.py`, rewrite the h10d parent import
  to package form:
  - from `import evaluate_v5_h10d_post_pump_short_replacement as v5_eval`
  - to `from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_eval`
- In moved `evaluate_m3_1_options_volume_shock_veto_falsification.py`, rewrite
  the stage0 import:
  - from `import audit_m3_1_options_regime_stage0 as stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import audit_m3_1_options_regime_stage0 as stage0`

Caller strategy:

- `sync_coinglass_full_stack_foundation.py` is an active data-foundation caller.
- Preferred first move strategy: keep that caller importing the root shim so the
  data foundation surface does not change in the same commit.
- Optional follow-up strategy: rewrite the caller to the moved package path only
  after import smoke and its own tests pass.
- The root shim for `audit_m3_1_options_regime_stage0.py` must re-export public
  symbols because the sync pipeline imports named functions/classes.

### M3.2

If approved later, move all four scripts together:

- `scripts/quant_research/evaluate_m3_2_boundary_activation_stage0.py`
- `scripts/quant_research/evaluate_m3_2_boundary_activation_falsification.py`
- `scripts/quant_research/evaluate_m3_2_canonical_parent_stage0.py`
- `scripts/quant_research/evaluate_m3_2_etf_onchain_sidecar_falsification.py`

Implementation import rewrites:

- In moved `evaluate_m3_2_boundary_activation_stage0.py`, rewrite h10d parent
  import to package form.
- In moved `evaluate_m3_2_boundary_activation_falsification.py`, rewrite:
  - from `import evaluate_m3_2_boundary_activation_stage0 as stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0`
- In moved `evaluate_m3_2_canonical_parent_stage0.py`, rewrite h10d parent
  import to package form.
- In moved `evaluate_m3_2_etf_onchain_sidecar_falsification.py`, rewrite:
  - from `import evaluate_m3_2_boundary_activation_falsification as hardgate`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_falsification as hardgate`
  - from `import evaluate_m3_2_boundary_activation_stage0 as stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0`

Caller strategy:

- No direct non-test active caller was found in this scan.
- Root shims are still required for test compatibility, historical commands,
  and repo-local imports that may not be covered by text search.
- Tests can be rewritten to moved package imports later, but the first
  implementation should keep tests green through root shims.

### M3.3

If approved later, move all six event-state scripts together:

- `scripts/quant_research/evaluate_m3_3_event_tape_spk_stage0.py`
- `scripts/quant_research/evaluate_m3_3_event_state_feature_stage0.py`
- `scripts/quant_research/evaluate_m3_3_strict_event_state_stage0.py`
- `scripts/quant_research/evaluate_m3_3_robustness_v2_stage0.py`
- `scripts/quant_research/evaluate_m3_3_mf01_confirmation_stage0.py`
- `scripts/quant_research/evaluate_m3_3_hype_chatter_gate_stage0.py`

Implementation import rewrites:

- In moved `evaluate_m3_3_event_tape_spk_stage0.py`, rewrite h10d parent import
  to package form.
- In moved `evaluate_m3_3_event_state_feature_stage0.py`, rewrite:
  - from `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - h10d parent import to package form.
- In moved `evaluate_m3_3_strict_event_state_stage0.py`, rewrite:
  - from `import evaluate_m3_3_event_state_feature_stage0 as feature_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_state_feature_stage0 as feature_stage0`
  - from `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
- In moved `evaluate_m3_3_robustness_v2_stage0.py`, rewrite:
  - from `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - from `import evaluate_m3_3_strict_event_state_stage0 as strict_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_strict_event_state_stage0 as strict_stage0`
- In moved `evaluate_m3_3_mf01_confirmation_stage0.py`, rewrite:
  - from `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - from `import evaluate_m3_3_strict_event_state_stage0 as strict_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_strict_event_state_stage0 as strict_stage0`
- In moved `evaluate_m3_3_hype_chatter_gate_stage0.py`, rewrite:
  - from `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
  - h10d parent import to package form.

Caller strategy:

- `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
  imports M3.3 event tape and event-state features.
- Preferred strategy if M3.3 moves: rewrite that support caller to moved
  package imports in the same implementation commit, while root shims preserve
  old CLI/import compatibility.
- Do not move `m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py` again;
  it is already in a support directory with a root shim.

## Root Shim Contract

Every moved implementation must keep a same-name root shim under
`scripts/quant_research/`.

Required shim properties:

- Thin wrapper only.
- Uses package import or `runpy.run_module` against the moved implementation.
- Preserves old root CLI invocation:
  - `python scripts/quant_research/<script>.py --help`
- Preserves old module import:
  - `import scripts.quant_research.<script_stem>`
- Re-exports public symbols when existing callers import named functions,
  classes, or constants.
- Does not duplicate business logic.
- Does not create a second artifact output policy.

## Docs Link Strategy

Direct branch-report links that should be considered during implementation:

- `docs/quant_research/03_alpha_branches/m3_1_options_regime_r8_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md`
- `docs/quant_research/03_alpha_branches/m3_2_boundary_activation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_2_full_stack_boundary_falsification.md`
- `docs/quant_research/03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md`
- `docs/quant_research/03_alpha_branches/m3_3_event_tape_spk_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_event_state_feature_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_strict_event_state_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_robustness_v2_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_mf01_confirmation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_hype_chatter_gate_stage0.md`
- `docs/quant_research/03_alpha_branches/mf01_orderbook_inventory_r6_retest.md`

Update rule:

- Clickable implementation links should point to the moved implementation path.
- Command examples can continue using the root wrapper path when the command is
  meant to be the stable user-facing CLI.
- Historical planning docs, especially old worktree staging plans, should not be
  churned just because root wrappers now exist. They remain historical evidence
  unless they contain broken links after a move.
- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`,
  `scripts/quant_research/README.md`, and any owner-review queue must be
  synchronized if a cluster moves.

## Validation Commands

Run after any later implementation batch.

Common validation:

```powershell
python -m compileall scripts\quant_research\alpha_stage0_quarantine scripts\quant_research -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
python -m pytest tests\test_markdown_links.py -q
git diff --check
```

M3.1 targeted validation:

```powershell
python -m pytest tests\test_quant_m3_1_options_regime_stage0.py tests\test_quant_m3_1_options_volume_shock_veto_falsification.py -q
python scripts\quant_research\audit_m3_1_options_regime_stage0.py --help
python scripts\quant_research\evaluate_m3_1_options_volume_shock_veto_falsification.py --help
@'
from importlib import import_module
import_module("scripts.quant_research.sync_coinglass_full_stack_foundation")
import_module("scripts.quant_research.audit_m3_1_options_regime_stage0")
import_module("scripts.quant_research.evaluate_m3_1_options_volume_shock_veto_falsification")
'@ | python -
```

M3.2 targeted validation:

```powershell
python -m pytest tests\test_quant_m3_2_boundary_activation_stage0.py tests\test_quant_m3_2_boundary_activation_falsification.py tests\test_quant_m3_2_canonical_parent_stage0.py tests\test_quant_m3_2_etf_onchain_sidecar_falsification.py -q
python scripts\quant_research\evaluate_m3_2_boundary_activation_stage0.py --help
python scripts\quant_research\evaluate_m3_2_boundary_activation_falsification.py --help
python scripts\quant_research\evaluate_m3_2_canonical_parent_stage0.py --help
python scripts\quant_research\evaluate_m3_2_etf_onchain_sidecar_falsification.py --help
@'
from importlib import import_module
for name in [
    "scripts.quant_research.evaluate_m3_2_boundary_activation_stage0",
    "scripts.quant_research.evaluate_m3_2_boundary_activation_falsification",
    "scripts.quant_research.evaluate_m3_2_canonical_parent_stage0",
    "scripts.quant_research.evaluate_m3_2_etf_onchain_sidecar_falsification",
]:
    import_module(name)
'@ | python -
```

M3.3 targeted validation:

```powershell
python -m pytest tests\test_quant_m3_3_event_tape_spk_stage0.py tests\test_quant_m3_3_event_state_feature_stage0.py tests\test_quant_m3_3_strict_event_state_stage0.py tests\test_quant_m3_3_robustness_v2_stage0.py tests\test_quant_m3_3_mf01_confirmation_stage0.py -q
python scripts\quant_research\evaluate_m3_3_event_tape_spk_stage0.py --help
python scripts\quant_research\evaluate_m3_3_event_state_feature_stage0.py --help
python scripts\quant_research\evaluate_m3_3_strict_event_state_stage0.py --help
python scripts\quant_research\evaluate_m3_3_robustness_v2_stage0.py --help
python scripts\quant_research\evaluate_m3_3_mf01_confirmation_stage0.py --help
python scripts\quant_research\evaluate_m3_3_hype_chatter_gate_stage0.py --help
@'
from importlib import import_module
for name in [
    "scripts.quant_research.evaluate_m3_3_event_tape_spk_stage0",
    "scripts.quant_research.evaluate_m3_3_event_state_feature_stage0",
    "scripts.quant_research.evaluate_m3_3_strict_event_state_stage0",
    "scripts.quant_research.evaluate_m3_3_robustness_v2_stage0",
    "scripts.quant_research.evaluate_m3_3_mf01_confirmation_stage0",
    "scripts.quant_research.evaluate_m3_3_hype_chatter_gate_stage0",
    "scripts.quant_research.m3_mf_spk_support.evaluate_m3_3_strict_event_state_ab",
]:
    import_module(name)
'@ | python -
```

## Deferred And Owner-Gated Items

Implementation is deferred until the owner explicitly approves one of these:

1. Move only M3.2 as the first high-risk batch.
2. Move M3.1 with the active sync caller kept on the root shim.
3. Move M3.1 with the active sync caller rewritten to the moved package path.
4. Move M3.3 as a complete event-state batch and rewrite the support caller.
5. Permanently keep all M3 scripts at root and document that decision in the
   owner-review queue.

Do not split M3.3 into one-off single-file moves. The event tape, event-state
feature, strict event-state, robustness, MF01 confirmation, and hype gate scripts
share too many assumptions for piecemeal movement to be low risk.

## Recommended Next Gate

Ask owner approval for M3.2 only. If approved, write a Phase 5.20 implementation
plan for the four M3.2 scripts with root shims and package import rewrites before
moving files.
