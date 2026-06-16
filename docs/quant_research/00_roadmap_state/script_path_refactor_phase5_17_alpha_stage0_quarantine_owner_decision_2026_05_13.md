# Phase 5.17 Alpha Stage-0 / Quarantine Owner Decision

`Status: owner decision baseline`
`Date: 2026-05-13`
`Scope: alpha stage-0 / quarantine script-path target and first implementation batch`

## Decision

Approve `scripts/quant_research/alpha_stage0_quarantine/` as the target
directory for alpha stage-0 and strict-falsification implementations.

Do not approve a 22-file migration. The full cluster is too import-dense for a
single low-risk batch.

Approve only the first low/low-medium implementation batch:

- `compute_stablecoin_flow_overlay_candidates.py`
- `evaluate_funding_oi_crowded_squeeze_failure_stage0.py`
- `evaluate_post_capitulation_long_replacement_stage0.py`
- `evaluate_spk_crowding_confirmation_stage0.py`

This approval is for the Phase 5.17 first-batch implementation commit.

## Why The Directory Is Approved

`alpha_stage0_quarantine/` is semantically narrow enough:

- it distinguishes stage-0 / strict-falsification implementations from
  `alpha_branch_reports/`;
- it does not imply current-roadmap admission;
- it keeps failed or quarantined research executable and discoverable;
- it avoids using `m3_mf_spk_support/` for scripts that actually run candidate
  falsification or stage-0 evidence generation.

## Why Only Four Files Are Approved First

The approved first batch has no scheduled/config strong references and no test
imports in the current review.

Reference posture:

| script | code references outside self | test imports | import rewrite needed | approval |
| --- | --- | ---: | --- | --- |
| `compute_stablecoin_flow_overlay_candidates.py` | none found | 0 | root depth only | approved |
| `evaluate_funding_oi_crowded_squeeze_failure_stage0.py` | none found | 0 | h10d helper package import | approved |
| `evaluate_post_capitulation_long_replacement_stage0.py` | none found | 0 | h10d helper package import | approved |
| `evaluate_spk_crowding_confirmation_stage0.py` | none found | 0 | h10d helper package import | approved |

The three h10d-helper users currently import
`evaluate_v6_h10d_post_pump_short_replacement` as a top-level sibling module.
When moved, they must use a package import instead:

```python
from scripts.quant_research import evaluate_v6_h10d_post_pump_short_replacement as spk_eval
```

## Required Wrapper Strategy

For all four approved scripts:

- keep old root paths as module-compatible re-export shims;
- keep root CLI compatibility;
- change moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`;
- keep implementation rows cataloged with their real quarantined/supporting
  lifecycle status;
- catalog root shims as `supporting` / `supporting_tool` / `safe-to-move = no`.

## Not Approved In The First Batch

The rest of the 22-file cluster stays root for now.

Reasons:

- M3.1 options has an active sync caller:
  `scripts/quant_research/sync_coinglass_full_stack_foundation.py`.
- M3.2 scripts import each other and are tested through root module paths.
- M3.3 event-state scripts have dense sibling imports and test imports.
- MF05/MF07/SP-K scripts include test imports, sibling imports, or h10d helper
  imports that should be handled in a separate cluster batch.
- `evaluate_spk_non_kline_confirmation_stage0.py` has a direct test import and
  should not be mixed into the first docs-only batch.

## Not Permanent Keep-Root

This review does not mark the alpha stage-0 / quarantine group as permanent
keep-root. It approves the directory and a small first migration batch.

Files not included in the first batch remain deferred, not rejected. Each
future subcluster must get a narrow implementation plan before movement.

## Implementation Verification Gate

The first implementation batch must run:

```powershell
python -m compileall -q scripts\quant_research\alpha_stage0_quarantine scripts\quant_research\compute_stablecoin_flow_overlay_candidates.py scripts\quant_research\evaluate_funding_oi_crowded_squeeze_failure_stage0.py scripts\quant_research\evaluate_post_capitulation_long_replacement_stage0.py scripts\quant_research\evaluate_spk_crowding_confirmation_stage0.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_stablecoin_flow_overlay_candidates.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_funding_oi_crowded_squeeze_failure_stage0.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_post_capitulation_long_replacement_stage0.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_spk_crowding_confirmation_stage0.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the tracked Markdown local-link checker if alpha-branch docs or
catalog links are updated.
