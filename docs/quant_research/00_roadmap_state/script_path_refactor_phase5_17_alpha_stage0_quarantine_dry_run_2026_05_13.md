# Phase 5.17 Alpha Stage-0 / Quarantine Dry-Run

`Status: read-only owner-review baseline`
`Date: 2026-05-13`
`Scope: remaining M3/MF/SP-K stage-0 and strict-falsification scripts at scripts/quant_research root`

## Decision

Do not move the alpha stage-0 / quarantine cluster autonomously.

The natural target directory is likely:

- `scripts/quant_research/alpha_stage0_quarantine/`

That name is clearer than `alpha_stage0/` because it preserves the fail-closed
meaning: these are preregistered or quarantined falsification implementations,
not admitted branch reports and not current default entrypoints.

Implementation should wait for owner review because this cluster has three
compatibility pressures:

- tests import root module paths and private helpers;
- scripts import each other through sibling root imports;
- `sync_coinglass_full_stack_foundation.py` imports the M3.1 options stage-0
  script as an active package dependency.

## Candidate Set

| script | subcluster | risk driver | dry-run posture |
| --- | --- | --- | --- |
| `audit_m3_1_options_regime_stage0.py` | M3.1 options | test import, sibling caller, active sync caller | owner review |
| `evaluate_m3_1_options_volume_shock_veto_falsification.py` | M3.1 options | imports M3.1 stage0, test import | owner review |
| `evaluate_m3_2_boundary_activation_stage0.py` | M3.2 boundary | sibling callers, tests import helpers | owner review |
| `evaluate_m3_2_boundary_activation_falsification.py` | M3.2 boundary | imports boundary stage0, test import | owner review |
| `evaluate_m3_2_canonical_parent_stage0.py` | M3.2 parent | h10d helper import, test import | owner review |
| `evaluate_m3_2_etf_onchain_sidecar_falsification.py` | M3.2 sidecar | imports two M3.2 scripts, test import | owner review |
| `evaluate_m3_3_event_tape_spk_stage0.py` | M3.3 event tape | heavily imported by M3.3 siblings, test import | owner review |
| `evaluate_m3_3_event_state_feature_stage0.py` | M3.3 event state | imports event tape and h10d helper, test import | owner review |
| `evaluate_m3_3_strict_event_state_stage0.py` | M3.3 strict state | imports event tape/state, downstream sibling imports | owner review |
| `evaluate_m3_3_robustness_v2_stage0.py` | M3.3 robustness | imports event tape and strict state, test import | owner review |
| `evaluate_m3_3_mf01_confirmation_stage0.py` | M3.3 MF01 | imports event tape and strict state, test import | owner review |
| `evaluate_m3_3_hype_chatter_gate_stage0.py` | M3.3 hype gate | imports event tape and h10d helper | owner review |
| `evaluate_mf05_cross_venue_boundary_stage0.py` | MF05 | h10d helper import, test import | owner review |
| `evaluate_mf05_cross_venue_spk_stage0.py` | MF05/SP-K | h10d helper import, test import | owner review |
| `evaluate_mf07_participant_disagreement_spk_stage0.py` | MF07/SP-K | h10d helper import, sibling caller, test import | owner review |
| `evaluate_mf07_etf_onchain_transition_falsification.py` | MF07 ETF/on-chain | imports MF07 disagreement stage0, test import | owner review |
| `evaluate_mf07_subday_participant_pivot_stage0.py` | MF07 subday | h10d helper import, test import | owner review |
| `evaluate_funding_oi_crowded_squeeze_failure_stage0.py` | funding/OI | h10d v6 helper import | owner review |
| `evaluate_post_capitulation_long_replacement_stage0.py` | post-capitulation | h10d v6 helper import | owner review |
| `evaluate_spk_crowding_confirmation_stage0.py` | SP-K | h10d v6 helper import | owner review |
| `evaluate_spk_non_kline_confirmation_stage0.py` | SP-K | h10d v6 helper import, test import | owner review |
| `compute_stablecoin_flow_overlay_candidates.py` | stablecoin overlay | docs-only references, but same quarantine semantics | owner review |

## Reference / Import Findings

Read-only checks:

```powershell
rg -n "<candidate stem>" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
```

Material findings:

- No scheduled-task manifest or PowerShell runner strong references were found.
- Many tests import old root package paths such as
  `scripts.quant_research.evaluate_m3_3_event_tape_spk_stage0`.
- Several docs link directly to root script paths with line suffixes, so any
  move must update Markdown links in the same implementation commit.
- `scripts/quant_research/sync_coinglass_full_stack_foundation.py` imports:
  `scripts.quant_research.audit_m3_1_options_regime_stage0`.
- Internal sibling imports include:
  - `evaluate_m3_1_options_volume_shock_veto_falsification.py` importing
    `audit_m3_1_options_regime_stage0`;
  - `evaluate_m3_2_*` scripts importing `evaluate_m3_2_boundary_*`;
  - `evaluate_m3_3_*` scripts importing event tape, event state, and strict
    state modules;
  - `evaluate_mf07_etf_onchain_transition_falsification.py` importing
    `evaluate_mf07_participant_disagreement_spk_stage0`.
- Many scripts also import root h10d helper modules:
  `evaluate_v5_h10d_post_pump_short_replacement` and
  `evaluate_v6_h10d_post_pump_short_replacement`.

## Recommended Implementation Shape

If approved later:

1. Create `scripts/quant_research/alpha_stage0_quarantine/`.
2. Move in subclusters, not all 22 at once:
   - M3.1 options cluster;
   - M3.2 boundary/sidecar cluster;
   - M3.3 event-state cluster;
   - MF05/MF07/SP-K cluster;
   - isolated funding/OI, post-capitulation, and stablecoin overlay scripts.
3. Preserve root module compatibility through re-export shims for every moved
   script that tests or callers import.
4. Rewrite intra-cluster imports to package imports where possible.
5. Do not move h10d helper modules in the same commit.
6. Update docs that link directly to old root implementation paths.

## Required Validation If Implemented

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine
python -m pytest tests\test_quant_m3_1_options_regime_stage0.py tests\test_quant_m3_1_options_volume_shock_veto_falsification.py tests\test_quant_m3_2_boundary_activation_stage0.py tests\test_quant_m3_2_boundary_activation_falsification.py tests\test_quant_m3_2_canonical_parent_stage0.py tests\test_quant_m3_2_etf_onchain_sidecar_falsification.py tests\test_quant_m3_3_event_tape_spk_stage0.py tests\test_quant_m3_3_event_state_feature_stage0.py tests\test_quant_m3_3_strict_event_state_stage0.py tests\test_quant_m3_3_robustness_v2_stage0.py tests\test_quant_m3_3_mf01_confirmation_stage0.py tests\test_quant_mf05_cross_venue_boundary_stage0.py tests\test_quant_mf05_cross_venue_spk_stage0.py tests\test_quant_mf07_participant_disagreement_spk_stage0.py tests\test_quant_mf07_etf_onchain_transition_falsification.py tests\test_quant_mf07_subday_participant_pivot_stage0.py tests\test_quant_spk_non_kline_confirmation_stage0.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the tracked Markdown local-link checker because alpha-branch docs link
to these script paths.
