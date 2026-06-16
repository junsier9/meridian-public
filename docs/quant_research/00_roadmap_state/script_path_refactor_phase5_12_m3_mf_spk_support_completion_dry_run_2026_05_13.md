# Phase 5.12 M3/MF/SP-K Support Completion Dry Run

`Status: read-only dry-run baseline`
`Scope: remaining P10 m3_mf_spk_support candidates`
`Date: 2026-05-13`

## Decision

Finish the P10 M3/MF/SP-K support group by moving the remaining seven
supporting tools into `scripts/quant_research/m3_mf_spk_support/`.

This batch stays out of stage0/quarantine and out of h10d/current-line
surfaces. It also preserves old root paths with module-compatible shims even
for scripts previously marked `safe-to-move = yes`, because old paths still
appear in docs, examples, or operator muscle memory.

## Move Set

| old root path | new implementation path | notes |
| --- | --- | --- |
| `scripts/quant_research/evaluate_mf13_tron_cross_sectional_gate_increment.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_mf13_tron_cross_sectional_gate_increment.py` | support tool; old root shim retained |
| `scripts/quant_research/evaluate_mf13_tron_regime_gate_ab.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_mf13_tron_regime_gate_ab.py` | support tool; old root shim retained |
| `scripts/quant_research/evaluate_mf14_cross_sectional_gate_increment.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_mf14_cross_sectional_gate_increment.py` | support tool; old root shim retained |
| `scripts/quant_research/evaluate_mf14_regime_gate_ab.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_mf14_regime_gate_ab.py` | support tool; old root shim retained |
| `scripts/quant_research/evaluate_stablecoin_flow_interaction_cycle_increment.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_stablecoin_flow_interaction_cycle_increment.py` | support tool; old root shim retained |
| `scripts/quant_research/evaluate_stablecoin_overlay_cycle_increment.py` | `scripts/quant_research/m3_mf_spk_support/evaluate_stablecoin_overlay_cycle_increment.py` | `threshold_provenance.md` cites old root path; old root shim retained |
| `scripts/quant_research/explore_btc_options_signals.py` | `scripts/quant_research/m3_mf_spk_support/explore_btc_options_signals.py` | exploration-only support tool; old root shim retained |

## Reference Audit

No scheduled/config/test strong references were found for this batch except
`config/quant_research/threshold_provenance.md` citing
`evaluate_stablecoin_overlay_cycle_increment.py` as a diagnostic script. The
old root shim preserves that cited path.

`explore_btc_options_signals.py` contains usage examples that mention its old
root path. The old root shim preserves those examples.

## Implementation Rules

- Move all seven implementations under `m3_mf_spk_support/`.
- Update each moved implementation root discovery from
  `SCRIPT_DIR.parents[1]` to `SCRIPT_DIR.parents[2]`.
- Keep a root re-export shim at every old path.
- Do not move any `evaluate_*_stage0.py` or strict-falsification script in this
  batch.
- Do not update `threshold_provenance.md`; the old cited root path remains
  executable through the shim.

## Expected Count Changes

Starting from Phase 5.11:

- Total script files: 236 -> 243.
- Python script files: 217 -> 224.
- Root-level count: stays 162.
- `m3_mf_spk_support/`: 5 -> 12.
- `m3_mf_spk_legacy_candidates`: 61 -> 68.
- `supporting`: 105 -> 112.
- `supporting_tool`: 125 -> 132.
- `safe-to-move = no`: 66 -> 73.
- `safe-to-move = yes`: 40 -> 34.
- `safe-to-move = yes-with-wrapper`: 130 -> 136.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\m3_mf_spk_support scripts\quant_research\evaluate_mf13_tron_cross_sectional_gate_increment.py scripts\quant_research\evaluate_mf13_tron_regime_gate_ab.py scripts\quant_research\evaluate_mf14_cross_sectional_gate_increment.py scripts\quant_research\evaluate_mf14_regime_gate_ab.py scripts\quant_research\evaluate_stablecoin_flow_interaction_cycle_increment.py scripts\quant_research\evaluate_stablecoin_overlay_cycle_increment.py scripts\quant_research\explore_btc_options_signals.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf13_tron_cross_sectional_gate_increment.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf13_tron_regime_gate_ab.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf14_cross_sectional_gate_increment.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_mf14_regime_gate_ab.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_stablecoin_flow_interaction_cycle_increment.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_stablecoin_overlay_cycle_increment.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\explore_btc_options_signals.py --help
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Deferred

- Stage0/quarantine scripts remain deferred to the alpha-stage0 target decision.
- Data-sync/default entrypoints remain owner-review gated.
- h10d boundary scripts remain owner-review gated.
