# Phase 5.22 M3.3 Event-State Dry-Run And Implementation Plan

`Status: read-only high-risk dry-run and implementation plan`
`Date: 2026-05-13`
`Baseline commit: 330215d Phase 5.21 M3.1 options script path refactor`
`Scope: six M3.3 event-state stage-0 / falsification scripts`

This artifact is a plan only. It does not move scripts, add wrappers, rewrite
imports, rewrite tests, or change script catalog counts.

## Decision

If the M3.3 event-state family is migrated, move the six scripts as one coherent
Phase 5.22 implementation batch:

- `scripts/quant_research/evaluate_m3_3_event_tape_spk_stage0.py`
- `scripts/quant_research/evaluate_m3_3_event_state_feature_stage0.py`
- `scripts/quant_research/evaluate_m3_3_strict_event_state_stage0.py`
- `scripts/quant_research/evaluate_m3_3_robustness_v2_stage0.py`
- `scripts/quant_research/evaluate_m3_3_mf01_confirmation_stage0.py`
- `scripts/quant_research/evaluate_m3_3_hype_chatter_gate_stage0.py`

Do not split these into one-off moves. Event tape is the base event data
contract; event-state features and strict rows form the middle layer; robustness,
MF01, and hype are downstream diagnostics that assume the same event tape and
strict semantics. A partial move would create mixed root/package imports around
the same event-state contract and would raise compatibility risk without
reducing semantic ambiguity.

Target directory if approved:

- `scripts/quant_research/alpha_stage0_quarantine/`

The directory boundary remains narrow: this is for owner-approved alpha
stage-0, strict falsification, and quarantined branch evidence scripts only. It
does not approve moving h10d parents, data-sync pipelines, current-line guards,
scheduled surfaces, or the already-moved M3/MF/SP-K support scaffold.

## Non-Movement Guarantee

This Phase 5.22 dry-run does not:

- move any `.py` file;
- add root shims;
- update catalog counts;
- update README path policy;
- rewrite direct branch-report implementation links;
- rewrite historical worktree staging references.

Only this planning artifact and the governance index are expected to change.

## Dependency Order

| Order | Script | Current root imports | Downstream users found | Migration posture |
|---:|---|---|---|---|
| 1 | `evaluate_m3_3_event_tape_spk_stage0.py` | `evaluate_v5_h10d_post_pump_short_replacement`; `enhengclaw.quant_research.features` | all five sibling scripts; `m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`; one direct test | base of the batch; move first and rewrite h10d parent to package import |
| 2 | `evaluate_m3_3_event_state_feature_stage0.py` | `evaluate_m3_3_event_tape_spk_stage0`; `evaluate_v5_h10d_post_pump_short_replacement`; features | strict event-state; support A/B scaffold; one direct test | move after event tape; rewrite sibling and h10d parent imports |
| 3 | `evaluate_m3_3_strict_event_state_stage0.py` | `evaluate_m3_3_event_state_feature_stage0`; `evaluate_m3_3_event_tape_spk_stage0`; features | robustness; MF01; one direct test | move after event-state feature; rewrite both sibling imports |
| 4 | `evaluate_m3_3_robustness_v2_stage0.py` | `evaluate_m3_3_event_tape_spk_stage0`; `evaluate_m3_3_strict_event_state_stage0`; features | one direct test | downstream diagnostic; move in same batch after strict |
| 5 | `evaluate_m3_3_mf01_confirmation_stage0.py` | `evaluate_m3_3_event_tape_spk_stage0`; `evaluate_m3_3_strict_event_state_stage0`; features | one direct test; MF01 retest doc reference | downstream confirmation diagnostic; move in same batch after strict |
| 6 | `evaluate_m3_3_hype_chatter_gate_stage0.py` | `evaluate_m3_3_event_tape_spk_stage0`; `evaluate_v5_h10d_post_pump_short_replacement`; features | no dedicated test found | downstream hype gate; move in same batch so event tape import semantics stay unified |

## Whole-Batch Requirement

M3.3 does not have to move because of Phase 5.22. But if it moves, it should
move whole.

Rationale:

- `event_tape` is a shared tape-construction and event-merge API, not a leaf.
- `event_state_feature` depends on `event_tape` and is itself imported by the
  strict selector and support A/B scaffold.
- `strict_event_state` depends on both upstream layers and is imported by
  robustness and MF01 confirmation.
- `robustness`, `MF01`, and `hype` are not default entrypoints; they are
  downstream diagnostics whose value comes from the same quarantined event-state
  branch context.
- `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
  imports event tape and event-state feature modules directly today, so it must
  be handled in the same implementation commit.
- Five tests import root module paths for private helpers. Root module-compatible
  shims are required even if later tests are rewritten to package imports.

The only acceptable alternative to a whole-batch move is a documented owner
decision to keep the six root implementations permanently. A two-step split
such as event tape/state/strict first and downstream diagnostics later is
technically possible, but it is not recommended because it leaves mixed import
forms around one event-state contract.

## External References Found

Direct tests:

- `tests/test_quant_m3_3_event_tape_spk_stage0.py`
- `tests/test_quant_m3_3_event_state_feature_stage0.py`
- `tests/test_quant_m3_3_strict_event_state_stage0.py`
- `tests/test_quant_m3_3_robustness_v2_stage0.py`
- `tests/test_quant_m3_3_mf01_confirmation_stage0.py`

No dedicated `hype_chatter_gate` test was found in this scan.

Non-test script caller:

- `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
  imports:
  - `from scripts.quant_research import evaluate_m3_3_event_state_feature_stage0 as event_features`
  - `from scripts.quant_research import evaluate_m3_3_event_tape_spk_stage0 as event_tape`

Docs with direct implementation links or command examples:

- `docs/quant_research/03_alpha_branches/m3_3_event_tape_spk_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_event_state_feature_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_strict_event_state_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_robustness_v2_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_mf01_confirmation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_hype_chatter_gate_stage0.md`
- `docs/quant_research/03_alpha_branches/mf01_orderbook_inventory_r6_retest.md`

No scheduled/config references were found by a targeted search over PowerShell,
JSON, YAML, TOML, INI, BAT, and CMD files. Historical planning docs still mention
old root paths; they should not be churned unless a link checker reports a
broken source-doc link after implementation.

## Implementation Plan If Approved

1. Move the six implementations into
   `scripts/quant_research/alpha_stage0_quarantine/`.
2. Replace each old root implementation with a thin module-compatible shim.
   The shim must re-export public attributes and preserve:
   - `python scripts/quant_research/<script>.py --help`
   - `import scripts.quant_research.<script_stem>`
3. In moved `evaluate_m3_3_event_tape_spk_stage0.py`, rewrite:
   - `import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`
   - to `from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`
4. In moved `evaluate_m3_3_event_state_feature_stage0.py`, rewrite:
   - `import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
   - to `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_3_event_tape_spk_stage0 as event_stage0`
   - `import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`
   - to `from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`
5. In moved `evaluate_m3_3_strict_event_state_stage0.py`, rewrite both sibling
   imports to package imports from `scripts.quant_research.alpha_stage0_quarantine`.
6. In moved `evaluate_m3_3_robustness_v2_stage0.py`, rewrite event tape and
   strict imports to package imports from `scripts.quant_research.alpha_stage0_quarantine`.
7. In moved `evaluate_m3_3_mf01_confirmation_stage0.py`, rewrite event tape and
   strict imports to package imports from `scripts.quant_research.alpha_stage0_quarantine`.
8. In moved `evaluate_m3_3_hype_chatter_gate_stage0.py`, rewrite:
   - event tape import to package import from `scripts.quant_research.alpha_stage0_quarantine`
   - h10d parent import to package import from `scripts.quant_research`
9. Rewrite
   `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
   to import event tape and event-state features from
   `scripts.quant_research.alpha_stage0_quarantine`.
10. Update direct implementation links in the six M3.3 branch docs to the moved
    implementation paths; leave command examples on root wrapper paths.
11. Update `mf01_orderbook_inventory_r6_retest.md` if it references the moved
    MF01 implementation path as source code rather than a stable command.
12. Synchronize:
    - `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
    - `scripts/quant_research/README.md`
    - `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`
    - `docs/quant_research/00_roadmap_state/script_path_refactor_remaining_owner_review_queue_2026_05_13.md`

## Expected Catalog Delta If Implemented

Starting from Phase 5.21:

- total catalog coverage: 268 script files;
- Python script files: 249;
- root-level files: 162;
- root compatibility wrappers: 79;
- `alpha_stage0_quarantine/`: 16 files;
- remaining root implementation files with `safe-to-move != no`: 64.

After a whole-batch M3.3 implementation:

- total catalog coverage should become 274 script files;
- Python script files should become 255;
- root-level files should remain 162 because six root implementations become
  six root shims;
- root compatibility wrappers should become 85;
- `alpha_stage0_quarantine/` should become 22 files;
- remaining root implementation files with `safe-to-move != no` should fall to
  58;
- `m3_mf_spk_legacy_candidates` catalog rows should increase by six because
  each moved implementation gets a new moved-path row while the old root path
  remains as a shim row.

These are planning counts only. Recompute them during implementation rather
than editing by hand from this document.

## Validation Commands

Run after any future implementation commit:

```powershell
python -m compileall scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\m3_mf_spk_support scripts\quant_research -q
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
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_event_tape_spk_stage0",
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_event_state_feature_stage0",
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_strict_event_state_stage0",
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_robustness_v2_stage0",
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_mf01_confirmation_stage0",
    "scripts.quant_research.alpha_stage0_quarantine.evaluate_m3_3_hype_chatter_gate_stage0",
    "scripts.quant_research.m3_mf_spk_support.evaluate_m3_3_strict_event_state_ab",
]:
    import_module(name)
'@ | python -
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
python -m pytest tests\test_markdown_links.py -q
git diff --check
```

## Completion Criteria

A future Phase 5.22 implementation is complete only if:

- all six old root paths are thin module-compatible shims;
- all six moved implementations live under `alpha_stage0_quarantine/`;
- moved sibling imports use package imports, not `sys.path`-dependent root
  sibling imports;
- h10d parent imports use package imports from `scripts.quant_research`;
- the M3/MF/SP-K support caller imports moved event tape and event-state feature
  implementations directly;
- direct implementation links in current branch docs point to moved paths;
- command examples remain stable on root wrapper paths;
- catalog and README counts are recomputed and internally consistent;
- `alpha_stage0_quarantine/` remains explicitly limited to stage-0/quarantine
  evidence and does not absorb M3/MF support, h10d parents, data-sync surfaces,
  guards, or scheduled/default entrypoints.

## Deferred

Keep deferred unless separately approved:

- moving `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py`
  again;
- moving h10d parent scripts used by M3.3;
- moving any CoinGlass/data-sync/provider-sync surfaces;
- rewriting tests to moved package imports as part of the first compatibility
  move;
- creating a broader `event_state/` or `m3/` directory that would blur the
  existing `alpha_stage0_quarantine/` boundary.

## Recommended Next Gate

Ask owner approval for the whole six-script Phase 5.22 M3.3 implementation
batch. If not approved, mark the six M3.3 event-state implementations as
permanent keep-root in the owner-review queue.
