# Phase 5.42 Autonomous Script-Path Refactor Closure

`Status: autonomous phase closed`
`Date: 2026-05-14`
`Scope: scripts/quant_research remaining root boundary`

## Decision

The autonomous Phase 5.x script-path refactor is closed.

After Phase 5.41, there is no remaining low-risk or medium-low-risk 3-8 script
batch with:

- an approved target directory;
- no scheduled/config hard reference;
- no active root-module import or monkeypatch dependency;
- wrapper-compatible public CLI semantics;
- no expansion of current h10d, data-foundation, CoinGlass, or factor-report
  boundaries.

Do not continue automatic root cleanup by inventing a generic `utility/`
directory or by stretching existing directory meanings.

## Current Worktree Boundary

`git status --short` after Phase 5.41 showed only local untracked generated
artifacts under `artifacts/quant_research/...`. Those remain outside the
versioned script-path governance commits.

## Remaining Root `yes-with-wrapper` Boundary

The remaining root `safe-to-move = yes-with-wrapper` scripts are owner-gated or
high-risk. They are not autonomous batch candidates.

### Canonical h10d active/default/public guard

- `analyze_binance_pit_drawdown_attribution.py`
- `assert_h10d_promotion_evidence.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`

Reason: active h10d validation, public guard, or current Binance PIT hardening
surface. These require owner approval before any directory split.

### Historical h10d module-dependent

- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`

Reason: root-module import dependencies remain. A CLI-only wrapper is not
sufficient; any future move needs a package-import or re-export compatibility
plan.

### CoinGlass h10d parent historical / strict surfaces

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`

Reason: these sit at the CoinGlass h10d-parent evidence boundary. They should
not be absorbed by provider diagnostics, CoinGlass diagnostics, or current h10d
directories without a dedicated owner-approved plan.

### CoinGlass sync/default/data-foundation boundary

- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

Reason: data-foundation and CoinGlass sync/default public surfaces. Do not move
them under provider probes, provider diagnostics, or helper directories without
a data-foundation boundary redesign.

### Alpha ontology cycle/weights

- `compute_alpha_ontology_v3_weights.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`

Reason: ontology/cycle semantics, root path constants, and cycle-runner
dependencies. Any future move needs a dedicated ontology dry-run and caller
rewrite plan.

### Factor report card

- `factor_report_card.py`

Reason: central factor-admission/report-card surface. It is not a generic
report writer until a dedicated review proves that moving it will not blur the
factor-report authority boundary.

### Research-cycle default/manual/scheduler-adjacent surfaces

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

Reason: default/manual research-cycle and scheduler-adjacent public paths. They
are not cleanup candidates.

## Closed Autonomous Buckets

The following formerly ambiguous utility bucket is now closed:

- `bootstrap_quant_runtime.py`: Phase 5.37 permanent root-freeze.
- `run_quantagent_shadow_proposal_cycle.py`: Phase 5.37 permanent root-freeze.
- `run_quant_ohlcv_lane_ab.py`: Phase 5.39 moved to
  `data_lane_diagnostics/` behind a root wrapper.
- `export_passed_alphas_to_workbench.py`: Phase 5.41 permanent root-freeze.

## Stop Rule

Future movement of any remaining root `yes-with-wrapper` script requires one of
these:

- explicit owner approval for the named script or cluster;
- a new dry-run artifact proving that its boundary has changed;
- a new target-directory admission rule that does not broaden existing
  directories.

Until then, the correct posture is to preserve the root path and rely on the
catalog to distinguish public boundary, historical evidence, current entrypoint,
and owner-gated candidate.

## Verification

Recommended validation for this closure artifact:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```
