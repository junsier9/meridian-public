# Phase 5.18 MF05 / MF07 / SP-K Alpha Stage-0 Dry-Run

`Status: read-only dry-run decision artifact`
`Date: 2026-05-13`
`Scope: remaining MF05, MF07, and SP-K alpha stage-0/quarantine scripts`

## Decision

`scripts/quant_research/alpha_stage0_quarantine/` remains the correct target
directory for these scripts, but the remaining MF05/MF07/SP-K scripts should
move in small dependency-aware batches.

Do not touch the M3.1, M3.2, or M3.3 dense dependency clusters in this phase.

Recommended implementation order:

1. Phase 5.18a: move the two MF05 scripts together.
2. Phase 5.18b: move `evaluate_spk_non_kline_confirmation_stage0.py` as a
   single-script SP-K batch.
3. Phase 5.18c: move `evaluate_mf07_subday_participant_pivot_stage0.py` as a
   single-script MF07 subday batch.
4. Phase 5.18d: move the MF07 participant-disagreement pair together:
   `evaluate_mf07_participant_disagreement_spk_stage0.py` and
   `evaluate_mf07_etf_onchain_transition_falsification.py`.

The first implementation commit should be Phase 5.18a only. It is the cleanest
next batch because the two MF05 scripts have no sibling dependency between
them and only require h10d-helper package-import rewrites plus root shims.

## Candidate Audit

Read-only search command:

```powershell
rg -n "<candidate stem>" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
```

| script | direct tests | scheduled/config refs | sibling script dependency | h10d helper import | dry-run decision |
| --- | ---: | ---: | --- | --- | --- |
| `evaluate_mf05_cross_venue_boundary_stage0.py` | 1 | 0 | none | `evaluate_v5_h10d_post_pump_short_replacement` | approve Phase 5.18a |
| `evaluate_mf05_cross_venue_spk_stage0.py` | 1 | 0 | none | `evaluate_v5_h10d_post_pump_short_replacement` | approve Phase 5.18a |
| `evaluate_spk_non_kline_confirmation_stage0.py` | 1 | 0 | none | `evaluate_v6_h10d_post_pump_short_replacement` | approve Phase 5.18b |
| `evaluate_mf07_subday_participant_pivot_stage0.py` | 1 | 0 | none | `evaluate_v5_h10d_post_pump_short_replacement` | approve Phase 5.18c |
| `evaluate_mf07_participant_disagreement_spk_stage0.py` | 1 | 0 | imported by ETF/on-chain transition | `evaluate_v5_h10d_post_pump_short_replacement` | approve only with dependent pair |
| `evaluate_mf07_etf_onchain_transition_falsification.py` | 1 | 0 | imports participant-disagreement script | none directly | approve only with participant-disagreement pair |

## Compatibility Requirements

All six candidates are imported by tests from the old root module path, often
for private helper functions. A CLI-only wrapper is not sufficient.

Every implementation batch must keep root module-compatible shims:

```python
_IMPL = import_module("scripts.quant_research.alpha_stage0_quarantine.<module>")
globals().update(
    {
        name: getattr(_IMPL, name)
        for name in dir(_IMPL)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
```

Wrapper expectations:

- old root CLI path still works;
- tests importing `scripts.quant_research.<old_module>` still see helper
  functions/classes from the moved implementation;
- root shim is cataloged as `supporting` / `supporting_tool` /
  `safe-to-move = no`;
- moved implementation keeps `quarantined` / `quarantined_falsification`.

## Required Import Rewrites

For MF05, MF07 subday, and MF07 participant-disagreement scripts, rewrite the
top-level h10d helper import after movement:

```python
from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk
```

For SP-K non-kline, rewrite:

```python
from scripts.quant_research import evaluate_v6_h10d_post_pump_short_replacement as spk_eval
```

For the MF07 pair, rewrite the dependent import inside
`evaluate_mf07_etf_onchain_transition_falsification.py`:

```python
from scripts.quant_research.alpha_stage0_quarantine import (
    evaluate_mf07_participant_disagreement_spk_stage0 as mf07_stage0,
)
```

## Batch Plan

### Phase 5.18a - MF05 Pair

Move:

- `evaluate_mf05_cross_venue_boundary_stage0.py`
- `evaluate_mf05_cross_venue_spk_stage0.py`

Why first:

- no direct sibling dependency;
- no scheduled/config references;
- tests import root module paths, but root re-export shims cover that;
- both expose `main(argv)` and can use the standard wrapper pattern.

Required validation:

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\evaluate_mf05_cross_venue_boundary_stage0.py scripts\quant_research\evaluate_mf05_cross_venue_spk_stage0.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf05_cross_venue_boundary_stage0.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf05_cross_venue_spk_stage0.py --help
Pop-Location

python -m pytest tests\test_quant_mf05_cross_venue_boundary_stage0.py tests\test_quant_mf05_cross_venue_spk_stage0.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

### Phase 5.18b - SP-K Non-Kline

Move:

- `evaluate_spk_non_kline_confirmation_stage0.py`

Why separate:

- SP-K semantics are broader than MF05;
- direct test import exists;
- only one h10d helper import must be rewritten.

Required validation:

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\evaluate_spk_non_kline_confirmation_stage0.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_spk_non_kline_confirmation_stage0.py --help
python -m pytest tests\test_quant_spk_non_kline_confirmation_stage0.py -q
```

Also run the shared static/runtime/link/diff checks.

### Phase 5.18c - MF07 Subday

Move:

- `evaluate_mf07_subday_participant_pivot_stage0.py`

Why separate:

- it is MF07, but not a dependency of the ETF/on-chain transition script;
- it reads subday participant context and should not be hidden inside the
  participant-disagreement pair.

Required validation:

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\evaluate_mf07_subday_participant_pivot_stage0.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf07_subday_participant_pivot_stage0.py --help
python -m pytest tests\test_quant_mf07_subday_participant_pivot_stage0.py -q
```

Also run the shared static/runtime/link/diff checks.

### Phase 5.18d - MF07 Participant Pair

Move together:

- `evaluate_mf07_participant_disagreement_spk_stage0.py`
- `evaluate_mf07_etf_onchain_transition_falsification.py`

Why together:

- the ETF/on-chain transition script imports participant-disagreement helpers;
- moving only one of the pair would leave an avoidable root sibling dependency;
- both have direct tests.

Required validation:

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\evaluate_mf07_participant_disagreement_spk_stage0.py scripts\quant_research\evaluate_mf07_etf_onchain_transition_falsification.py
python -m pytest tests\test_quant_mf07_participant_disagreement_spk_stage0.py tests\test_quant_mf07_etf_onchain_transition_falsification.py -q
```

Also run wrapper `--help` smoke for both old root paths and the shared
static/runtime/link/diff checks.

## Explicitly Deferred

Do not include these in Phase 5.18:

- M3.1:
  - `audit_m3_1_options_regime_stage0.py`
  - `evaluate_m3_1_options_volume_shock_veto_falsification.py`
- M3.2:
  - `evaluate_m3_2_boundary_activation_stage0.py`
  - `evaluate_m3_2_boundary_activation_falsification.py`
  - `evaluate_m3_2_canonical_parent_stage0.py`
  - `evaluate_m3_2_etf_onchain_sidecar_falsification.py`
- M3.3:
  - `evaluate_m3_3_event_tape_spk_stage0.py`
  - `evaluate_m3_3_event_state_feature_stage0.py`
  - `evaluate_m3_3_strict_event_state_stage0.py`
  - `evaluate_m3_3_robustness_v2_stage0.py`
  - `evaluate_m3_3_mf01_confirmation_stage0.py`
  - `evaluate_m3_3_hype_chatter_gate_stage0.py`

These remain deferred because they have denser sibling dependencies, active
caller pressure, or a larger test/import surface.

## Completion Criteria

For any implementation batch:

- catalog total count and directory counts match actual files;
- README coverage and path policy are updated;
- remaining owner-review queue count decreases only by the moved
  implementations;
- root shims stay thin and module-compatible;
- no scheduled/config paths change;
- no M3.1/M3.2/M3.3 files move.
