# Phase 5.18 Post-Series Review

`Status: post-series review decision`
`Date: 2026-05-13`
`Scope: alpha_stage0_quarantine/ semantics after Phase 5.18a-d`

## Decision

`scripts/quant_research/alpha_stage0_quarantine/` did not swallow the M3
dense dependency cluster.

Phase 5.18a-d moved only the MF05, SP-K, and MF07 stage-0/quarantine scripts
that had explicit subcluster approval in the Phase 5.18 dry-run. The remaining
M3.1, M3.2, and M3.3 scripts still sit at root and remain classified as
owner-review candidates.

M3 should not be marked permanent keep-root. It is semantically a stage-0 /
strict-falsification family and can still fit `alpha_stage0_quarantine/`.
However, it is now a high-risk migration surface. The next step is a dedicated
high-risk dry-run, not an implementation move.

## Series Boundary Check

Phase 5.18 moved:

- Phase 5.18a: MF05 cross-venue pair;
- Phase 5.18b: SP-K non-kline confirmation;
- Phase 5.18c: MF07 subday participant pivot;
- Phase 5.18d: MF07 participant-disagreement dependent pair.

Current directory contents under `alpha_stage0_quarantine/` are:

- `compute_stablecoin_flow_overlay_candidates.py`;
- `evaluate_funding_oi_crowded_squeeze_failure_stage0.py`;
- `evaluate_mf05_cross_venue_boundary_stage0.py`;
- `evaluate_mf05_cross_venue_spk_stage0.py`;
- `evaluate_mf07_etf_onchain_transition_falsification.py`;
- `evaluate_mf07_participant_disagreement_spk_stage0.py`;
- `evaluate_mf07_subday_participant_pivot_stage0.py`;
- `evaluate_post_capitulation_long_replacement_stage0.py`;
- `evaluate_spk_crowding_confirmation_stage0.py`;
- `evaluate_spk_non_kline_confirmation_stage0.py`.

No `m3_1`, `m3_2`, or `m3_3` implementation is present in that directory.

## Catalog And Queue State

After Phase 5.18d:

- total script catalog coverage is 262 scripts;
- Python scripts total 243;
- root-level scripts remain 162;
- root compatibility wrappers total 73;
- `alpha_stage0_quarantine/` contains 10 implementation scripts;
- remaining root implementations with `safe-to-move != no` total 70;
- the alpha stage-0 owner-review queue contains 12 scripts, all M3.

The root wrappers for moved Phase 5.18 scripts are cataloged as
`supporting` / `supporting_tool` / `safe-to-move = no`. The moved
implementations keep their `quarantined` / `quarantined_falsification`
semantics.

## Remaining M3 Risk Map

| cluster | scripts | current dependency shape | decision |
| --- | --- | --- | --- |
| M3.1 options | `audit_m3_1_options_regime_stage0.py`, `evaluate_m3_1_options_volume_shock_veto_falsification.py` | `evaluate_m3_1_options_volume_shock_veto_falsification.py` imports `audit_m3_1_options_regime_stage0.py`; `sync_coinglass_full_stack_foundation.py` imports `scripts.quant_research.audit_m3_1_options_regime_stage0`; tests import root module paths. | high-risk dry-run only; not permanent keep-root |
| M3.2 boundary / sidecar | `evaluate_m3_2_boundary_activation_stage0.py`, `evaluate_m3_2_boundary_activation_falsification.py`, `evaluate_m3_2_canonical_parent_stage0.py`, `evaluate_m3_2_etf_onchain_sidecar_falsification.py` | Falsification imports boundary stage0; ETF/on-chain sidecar imports both boundary stage0 and boundary falsification; tests import root module paths; h10d helper imports remain root-facing. | high-risk dry-run only; not permanent keep-root |
| M3.3 event-state | `evaluate_m3_3_event_tape_spk_stage0.py`, `evaluate_m3_3_event_state_feature_stage0.py`, `evaluate_m3_3_strict_event_state_stage0.py`, `evaluate_m3_3_robustness_v2_stage0.py`, `evaluate_m3_3_mf01_confirmation_stage0.py`, `evaluate_m3_3_hype_chatter_gate_stage0.py` | Event tape is a hub; event-state, strict-state, robustness, MF01, and hype scripts import sibling modules; `m3_mf_spk_support/evaluate_m3_3_strict_event_state_ab.py` imports root M3.3 modules; tests import root module paths. | high-risk dry-run only; not permanent keep-root |

## Why Not Permanent Keep-Root

Permanent keep-root would imply the scripts are public/default surfaces or
semantically outside the quarantine directory. That is not true here:

- the catalog already classifies these scripts as `quarantined` /
  `quarantined_falsification`;
- the scripts are research evidence generators, not scheduled PowerShell
  surfaces or default h10d/data entrypoints;
- the path risk is import topology, not wrong target-directory semantics;
- root module-compatible shims have already proved workable for Phase 5.17 and
  Phase 5.18.

## Why High-Risk Dry-Run First

The M3 cluster is materially riskier than MF05/MF07/SP-K because:

- M3.1 has an active sync caller, not only tests;
- M3.2 has a multi-script falsification/sidecar chain;
- M3.3 has the densest sibling graph and an already-moved support script that
  imports root M3.3 modules;
- many docs link directly to root implementation paths;
- every moved script would need a root module-compatible shim to preserve tests
  and caller imports.

## Required Dry-Run Contract

The next artifact should be a read-only M3 high-risk dry-run. It must not move
files. It should classify implementation options by cluster:

1. M3.1 options plus active sync caller handling.
2. M3.2 boundary/sidecar chain.
3. M3.3 event-state dependency graph.

The dry-run must specify:

- exact import rewrites for moved implementations;
- whether external package callers should be rewritten or left to root shims;
- Markdown links that would need updates;
- root shim expectations for each candidate;
- cluster-specific test commands;
- static/runtime/scheduled validation commands;
- explicit owner-review gate before any implementation commit.

## Red Lines

- Do not move any M3 file during the dry-run.
- Do not split a dependent pair or graph hub without proving import safety.
- Do not move h10d helper modules in the same batch.
- Do not place M3 scripts under `m3_mf_spk_support/`; these are stage-0 /
  strict-falsification implementations, not support helpers.
- Do not treat M3 migration as low-risk cleanup.

## Minimum Verification For Any Future M3 Implementation

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine <old-root-shims>
python -m pytest tests\test_quant_m3_1_options_regime_stage0.py tests\test_quant_m3_1_options_volume_shock_veto_falsification.py -q
python -m pytest tests\test_quant_m3_2_boundary_activation_stage0.py tests\test_quant_m3_2_boundary_activation_falsification.py tests\test_quant_m3_2_canonical_parent_stage0.py tests\test_quant_m3_2_etf_onchain_sidecar_falsification.py -q
python -m pytest tests\test_quant_m3_3_event_tape_spk_stage0.py tests\test_quant_m3_3_event_state_feature_stage0.py tests\test_quant_m3_3_strict_event_state_stage0.py tests\test_quant_m3_3_robustness_v2_stage0.py tests\test_quant_m3_3_mf01_confirmation_stage0.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Markdown link checks should also be run after any implementation that updates
root script paths in docs.
