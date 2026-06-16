# Phase 5.13 Historical Legacy Completion Dry Run

`Status: read-only dry-run baseline`
`Scope: remaining P30 historical legacy root scripts`
`Date: 2026-05-13`

## Decision

Move the three remaining P30 historical legacy scripts into their existing
legacy target directories while preserving old root paths with module-compatible
shims. This completes the historical legacy remnants identified by the
completion control plan without changing historical research conclusions.

## Move Set

| old root path | new implementation path | reason |
| --- | --- | --- |
| `scripts/quant_research/phase_1c_factor_correlation_analysis.py` | `scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1c_factor_correlation_analysis.py` | Phase 1c historical factor de-correlation analysis |
| `scripts/quant_research/phase_1d_dynamic_weight_schedule.py` | `scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_dynamic_weight_schedule.py` | Phase 1d historical dynamic-weight schedule generator |
| `scripts/quant_research/run_v83_shadow_oos.py` | `scripts/quant_research/legacy_candidates/v71_v83/run_v83_shadow_oos.py` | v83 historical shadow OOS replay |

## Reference Audit

Old root paths are referenced by:

- `src/enhengclaw/quant_research/features.py`;
- `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v99.json`;
- `config/quant_research/threshold_provenance.md`;
- older governance dry-run docs.

The implementation should preserve old root compatibility rather than rewriting
these historical evidence references.

## Implementation Rules

- Move only the three scripts listed above.
- Update moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[3]` because both target directories are two levels below
  `scripts/quant_research`.
- Keep root re-export shims at all three old paths.
- Keep moved implementations cataloged as `historical` /
  `historical_do_not_start_here`.
- Catalog root shims as `supporting` / `supporting_tool` / `safe-to-move = no`.

## Expected Count Changes

Starting from Phase 5.12:

- Total script files: 243 -> 246.
- Python script files: 224 -> 227.
- Root-level count: stays 162.
- `legacy_candidates`: 7 -> 10.
- `m3_mf_spk_legacy_candidates`: 68 -> 71.
- `supporting`: 112 -> 115.
- `supporting_tool`: 132 -> 135.
- `safe-to-move = no`: 73 -> 76.
- `safe-to-move = yes`: 34 -> 32.
- `safe-to-move = yes-with-wrapper`: 136 -> 138.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\legacy_candidates\phase1_factor_weighting scripts\quant_research\legacy_candidates\v71_v83 scripts\quant_research\phase_1c_factor_correlation_analysis.py scripts\quant_research\phase_1d_dynamic_weight_schedule.py scripts\quant_research\run_v83_shadow_oos.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\phase_1c_factor_correlation_analysis.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\phase_1d_dynamic_weight_schedule.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_v83_shadow_oos.py --help
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Deferred

- h10d historical remnants outside this P30 group remain under the h10d
  owner-review boundary.
- Stage0/quarantine scripts remain deferred to alpha-stage0 directory design.
