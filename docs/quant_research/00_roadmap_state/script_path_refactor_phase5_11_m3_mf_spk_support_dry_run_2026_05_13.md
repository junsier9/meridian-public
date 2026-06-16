# Phase 5.11 M3/MF/SP-K Support Dry Run

`Status: read-only dry-run baseline`
`Scope: first-batch m3_mf_spk_support script-path refactor`
`Date: 2026-05-13`

## Decision

Create `scripts/quant_research/m3_mf_spk_support/` for M3/MF/SP-K supporting
tools that are not default entrypoints, not stage0/quarantine implementations,
not h10d current-line diagnostics, and not data-sync pipelines.

This first batch intentionally moves only five files. It proves both old-path
CLI compatibility and root module-import compatibility before the remaining P10
support candidates are considered.

## Move Set

| old root path | new implementation path | compatibility requirement |
| --- | --- | --- |
| `scripts/quant_research/audit_mf05_venue_local_data_gate.py` | `scripts/quant_research/m3_mf_spk_support/audit_mf05_venue_local_data_gate.py` | root module import used by tests; keep root re-export shim |
| `scripts/quant_research/audit_mf07_participant_stack_r7_gate.py` | `scripts/quant_research/m3_mf_spk_support/audit_mf07_participant_stack_r7_gate.py` | root module import used by tests; keep root re-export shim |
| `scripts/quant_research/build_m3_2_feature_panel.py` | `scripts/quant_research/m3_mf_spk_support/build_m3_2_feature_panel.py` | old root CLI/doc path should continue working |
| `scripts/quant_research/evaluate_m3_3_strict_event_state_ab.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py` | sibling root imports must become package imports; old root CLI path should continue working |
| `scripts/quant_research/evaluate_post_pump_stall_cycle_increment.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_post_pump_stall_cycle_increment.py` | old root CLI/doc path should continue working |

## Reference Audit

Strong references:

- `tests/test_quant_mf05_venue_local_data_gate.py` imports
  `scripts.quant_research.audit_mf05_venue_local_data_gate`.
- `tests/test_quant_mf07_participant_stack_r7_gate.py` imports
  `scripts.quant_research.audit_mf07_participant_stack_r7_gate`.

Doc/source references:

- `docs/quant_research/03_alpha_branches/mf05_venue_local_data_gate.md`
- `docs/quant_research/03_alpha_branches/mf07_participant_stack_r7_gate.md`
- `docs/quant_research/01_data_foundation/cryptoquant_alchemy_m3_2_plan.md`
- `docs/quant_research/03_alpha_branches/m3_3_strict_event_state_stage0.md`
- `docs/quant_research/03_alpha_branches/small_cap_post_pump_short_proposal.md`
- `src/enhengclaw/quant_research/onchain_m3_2_features.py`

The implementation should preserve old root paths instead of rewriting these
docs in this batch. The catalog will show the root paths as compatibility
wrappers and the moved paths as the real implementations.

## Import Compatibility Plan

- Root wrappers for all five scripts must be module-compatible shims, not
  CLI-only wrappers.
- The wrapper pattern may dynamically re-export implementation globals so tests
  that import private helper functions continue to work.
- Moved implementations must update root discovery from
  `SCRIPT_DIR.parents[1]` to `SCRIPT_DIR.parents[2]`.
- `evaluate_m3_3_strict_event_state_ab.py` must rewrite sibling imports to
  package imports:
  - `scripts.quant_research.evaluate_m3_3_event_state_feature_stage0`
  - `scripts.quant_research.evaluate_m3_3_event_tape_spk_stage0`
  - `scripts.quant_research.evaluate_v6_h10d_post_pump_short_replacement`
- `audit_mf07_participant_stack_r7_gate.py` must rewrite its h10d evaluator
  import to package import:
  - `scripts.quant_research.evaluate_v5_h10d_post_pump_short_replacement`

## Directory Boundary

`m3_mf_spk_support/` may contain M3/MF/SP-K support tools and branch evidence
helpers. It must not contain:

- `evaluate_*_stage0.py` quarantine/falsification implementations;
- strict-falsification scripts;
- current h10d diagnostics or h10d public surfaces;
- provider probes or provider sync pipelines;
- scheduled/default entrypoints.

Stage0/quarantine scripts remain deferred to a separate target-directory
decision.

## Catalog / README Updates

Expected count changes after implementation:

- Total script files: 231 -> 236.
- Python script files: 212 -> 217.
- Root-level count: stays 162 because old paths become wrappers.
- New `m3_mf_spk_support/` count: 0 -> 5.
- `m3_mf_spk_legacy_candidates`: 56 -> 61.
- `supporting`: 100 -> 105.
- `supporting_tool`: 120 -> 125.
- `safe-to-move = no`: 61 -> 66.

Root wrapper rows should use:

- status: `supporting`;
- run priority: `supporting_tool`;
- purpose: compatibility wrapper for moved M3/MF/SP-K support implementation;
- safe-to-move: `no`.

Moved implementation rows should keep their current `supporting` /
`supporting_tool` semantics and use `safe-to-move = yes-with-wrapper`.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\m3_mf_spk_support scripts\quant_research\audit_mf05_venue_local_data_gate.py scripts\quant_research\audit_mf07_participant_stack_r7_gate.py scripts\quant_research\build_m3_2_feature_panel.py scripts\quant_research\evaluate_m3_3_strict_event_state_ab.py scripts\quant_research\evaluate_post_pump_stall_cycle_increment.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_mf05_venue_local_data_gate.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_mf07_participant_stack_r7_gate.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\build_m3_2_feature_panel.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_m3_3_strict_event_state_ab.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_post_pump_stall_cycle_increment.py --help
python -m pytest tests\test_quant_mf05_venue_local_data_gate.py tests\test_quant_mf07_participant_stack_r7_gate.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Deferred

- Remaining P10 support tools not in this first batch.
- All P35 stage0/quarantine scripts.
- Data-sync and default-entrypoint groups.
- h10d boundary scripts.
- `factor_report_card.py`.
