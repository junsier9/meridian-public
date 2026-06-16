# Worktree Staging Plan 2026-05-07

`Workspace: <repo root>`

This plan separates the current dirty worktree into reviewable staging
packages. It is intentionally conservative: do not use `git add .`; stage by
path or by hunk only after each package is reviewed.

## Current Snapshot

- Tracked modified files: 36.
- Untracked files reported by git: 681.
- Largest untracked area: `artifacts/quant_research` run outputs.
- Many `artifacts/quant_research` paths are governed by `.gitignore`
  exceptions, so some experiment cards are visible to git while most detailed
  reports remain local/ignored.

## Execution Status

As of 2026-05-07, Package A was staged first. The follow-up execution treats
Packages B-F as versionable source/config/doc/test packages after focused
validation, while Package G remains local-only. The practical staging boundary
is now:

- Stage non-artifact source/config/docs/tests, including package files that
  were missing from the initial inventory but are required by the same
  CoinGlass, onchain/M3.x, Deribit/options, event-tape, or h10d governance
  lanes.
- Do not bulk-stage `artifacts/**`.
- Do not stage `.claude/**` or `src/enhengclaw/quant_research/.claude/**`.

## Package A: R-1 Strict Gate

Purpose: make the R-1 h10d parent fail closed on measured blocker attribution,
while keeping missing statistical-falsification tests separate from measured
cost/delay failures.

Recommended action: stage after review.

Files:

- `src/enhengclaw/quant_research/alpha_experiment_reporter.py`
- `src/enhengclaw/quant_research/promotion.py`
- `config/quant_research/promotion_gate_h10d.json`
- `scripts/quant_research/assert_h10d_promotion_evidence.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_blocker_attribution.py`
- `tests/test_quant_alpha_experiment_reporter.py`

Local-only evidence:

- `artifacts/quant_research/reports/coinglass_h10d_parent_symbol_bucket_strict_gate_2026-05-07.md`
- `artifacts/quant_research/coinglass/coinglass_h10d_parent_symbol_bucket_strict_gate_2026-05-07.json`
- `artifacts/quant_research/reports/coinglass_h10d_parent_blocker_attribution_2026-05-07.md`
- `artifacts/quant_research/coinglass/coinglass_h10d_parent_blocker_attribution_2026-05-07.json`

Decision:

- Code/config/test should be versioned.
- Generated reports should stay local unless a governance rule requires a
  forced evidence commit.
- `src/enhengclaw/quant_research/promotion.py` already contains broader h10d
  evidence-guard work, so review its full diff before staging.

Suggested validation:

```powershell
python -m pytest .\tests\test_quant_alpha_experiment_reporter.py -q
python .\scripts\quant_research\assert_h10d_promotion_evidence.py --alpha-card .\artifacts\quant_research\coinglass\h10d_parent_frozen_reset_strict_2026-05-04_2026-05-06_01\experiments\2026-05-04-xs_alpha_ontology_v5_rw_bridg-325b6d02b7fe\alpha_card.json
```

The second command is expected to fail closed.

## Package B: CoinGlass Data Stack

Purpose: provider integration, spot OHLCV coverage/concordance, OI provenance,
and reset reporting.

Recommended action: stage after Package A, but only as a coherent provider
stack. Do not mix with M3/onchain or Deribit.

Files:

- `src/enhengclaw/quant_research/coinglass_capability_matrix.py`
- `src/enhengclaw/quant_research/coinglass_oi_provenance.py`
- `src/enhengclaw/quant_research/coinglass_spot_ohlcv.py`
- `scripts/quant_research/run_coinglass_capability_matrix.py`
- `scripts/quant_research/run_quant_coinglass_spot_sync.py`
- `scripts/quant_research/validate_coinglass_spot_overlap.py`
- `scripts/quant_research/validate_coinglass_spot_strict_concordance.py`
- `scripts/quant_research/write_coinglass_coverage_reset_report.py`
- `scripts/quant_research/write_coinglass_spot_concordance_quarantine.py`
- `scripts/quant_research/sync_coinglass_oi_provenance_sidecar.py`
- `scripts/quant_research/audit_coinglass_dataset_feature_smoke.py`
- `scripts/quant_research/audit_coinglass_oi_compiler_integration.py`
- `scripts/quant_research/audit_coinglass_oi_provenance.py`
- `scripts/quant_research/run_coinglass_h10d_parent_frozen_reset_strict.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_drift.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_fast_reject_stages.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_rebaseline.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_strict_cycle_probe.py`
- `tests/test_coinglass_capability_matrix.py`
- `tests/test_coinglass_oi_provenance.py`
- `tests/test_coinglass_spot_ohlcv.py`
- `docs/quant_research/01_data_foundation/coinglass_full_stack_data_research_roadmap.md`

Decision:

- Provider code, validators, sync scripts, tests, and roadmap should be
  versioned after a focused review.
- Full data caches and generated report outputs should stay local.
- The roadmap also contains the 2026-05-07 R-1 update. Since the file is
  untracked, it cannot be cleanly hunk-staged from git's perspective without
  staging the full roadmap. Treat it as part of the CoinGlass documentation
  package.

## Package C: Onchain / M3.x / Stablecoin

Purpose: CryptoQuant/Alchemy/stablecoin/on-chain sidecars and M3.2/M3.3
Stage 0 research lanes.

Recommended action: hold until Package A and B are reviewed. This is a separate
research branch/package.

Files:

- `src/enhengclaw/quant_research/onchain_address_labels.py`
- `src/enhengclaw/quant_research/onchain_cryptoquant.py`
- `src/enhengclaw/quant_research/onchain_m3_2_features.py`
- `src/enhengclaw/quant_research/onchain_stablecoin.py`
- `src/enhengclaw/quant_research/onchain_stablecoin_tron.py`
- `src/enhengclaw/quant_research/stablecoin_regime.py`
- `config/quant_research/onchain_address_labels/ethereum_seed_labels.csv`
- `scripts/quant_research/backfill_stablecoin_history.py`
- `scripts/quant_research/build_m3_2_feature_panel.py`
- `scripts/quant_research/compute_m3_2_admission_report.py`
- `scripts/quant_research/compute_stablecoin_flow_overlay_candidates.py`
- `scripts/quant_research/compute_stablecoin_issuance_velocity_overlay_candidate.py`
- `scripts/quant_research/evaluate_m3_2_boundary_activation_falsification.py`
- `scripts/quant_research/evaluate_m3_2_boundary_activation_stage0.py`
- `scripts/quant_research/evaluate_m3_2_canonical_parent_stage0.py`
- `scripts/quant_research/evaluate_m3_3_event_state_feature_stage0.py`
- `scripts/quant_research/evaluate_m3_3_event_tape_spk_stage0.py`
- `scripts/quant_research/evaluate_m3_3_hype_chatter_gate_stage0.py`
- `scripts/quant_research/evaluate_m3_3_mf01_confirmation_stage0.py`
- `scripts/quant_research/evaluate_m3_3_robustness_v2_stage0.py`
- `scripts/quant_research/evaluate_m3_3_strict_event_state_ab.py`
- `scripts/quant_research/evaluate_m3_3_strict_event_state_stage0.py`
- `scripts/quant_research/probe_cryptoquant_stablecoin_tokens.py`
- `scripts/quant_research/run_quant_cryptoquant_m3_2_sync_cycle.py`
- `scripts/quant_research/run_quant_stablecoin_ethereum_backfill.py`
- `scripts/quant_research/run_quant_stablecoin_ethereum_sync_cycle.py`
- `scripts/quant_research/sync_alchemy_stablecoin_ethereum.py`
- `scripts/quant_research/sync_cryptoquant_reflexivity_history.py`
- `scripts/quant_research/sync_cryptoquant_stablecoin_history.py`
- `scripts/quant_research/sync_tronscan_stablecoin_tron.py`
- `docs/quant_research/01_data_foundation/cryptoquant_alchemy_m3_2_plan.md`
- `docs/quant_research/03_alpha_branches/m3_2_boundary_activation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_2_canonical_parent_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_event_state_feature_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_event_tape_spk_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_hype_chatter_gate_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_mf01_confirmation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_robustness_v2_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_3_strict_event_state_stage0.md`
- `tests/test_onchain_cryptoquant.py`
- `tests/test_onchain_m3_2_features.py`
- `tests/test_onchain_stablecoin.py`
- `tests/test_onchain_stablecoin_tron.py`
- `tests/test_quant_m3_2_boundary_activation_falsification.py`
- `tests/test_quant_m3_2_boundary_activation_stage0.py`
- `tests/test_quant_m3_2_canonical_parent_stage0.py`
- `tests/test_quant_m3_3_event_state_feature_stage0.py`
- `tests/test_quant_m3_3_event_tape_spk_stage0.py`
- `tests/test_quant_m3_3_hype_chatter_gate_stage0.py`
- `tests/test_quant_m3_3_mf01_confirmation_stage0.py`
- `tests/test_quant_m3_3_robustness_v2.py`
- `tests/test_quant_m3_3_robustness_v2_stage0.py`
- `tests/test_quant_m3_3_strict_event_state_scorer.py`
- `tests/test_quant_m3_3_strict_event_state_stage0.py`
- `tests/test_stablecoin_flow_interaction_scores.py`

Decision:

- Version only after running the focused onchain/M3 test slice.
- Keep synced raw data and generated feature panels local.
- Do not combine with CoinGlass provider changes unless a test proves a direct
  dependency.

## Package D: Deribit / Options

Purpose: Deribit options-chain sync, authenticated capability probe, and
scheduled task runner.

Recommended action: separate staging package after Package B or C.

Files:

- `scripts/quant_research/probe_deribit_authenticated_historical_capability.py`
- `scripts/quant_research/sync_deribit_options_chain.py`
- `scripts/quant_research/register_openclaw_quant_deribit_options_chain_snapshot_task.ps1`
- `scripts/quant_research/run_openclaw_quant_deribit_options_chain_snapshot_runner.ps1`
- `scripts/quant_research/run_quant_deribit_options_chain_snapshot_cycle.py`
- `config/scheduled_tasks/manifest.json`

Decision:

- Stage scripts and manifest together only after confirming no local secrets or
  machine-specific paths are embedded.
- Generated option-chain snapshots remain local.

## Package E: Event Tape / MF05 / MF07 / News Dataset

Purpose: event-tape, participant disagreement, cross-venue stress, and
cryptonews dataset processing/review work.

Recommended action: hold. This is a separate research package, not part of
CoinGlass R-1.

Files include:

- `src/enhengclaw/quant_research/event_tape.py`
- `src/enhengclaw/quant_research/label_builder.py`
- `src/enhengclaw/quant_research/research_dataset_builder.py`
- `scripts/quant_research/evaluate_mf05_cross_venue_boundary_stage0.py`
- `scripts/quant_research/evaluate_mf05_cross_venue_spk_stage0.py`
- `scripts/quant_research/evaluate_mf07_participant_disagreement_spk_stage0.py`
- `scripts/quant_research/evaluate_mf07_subday_participant_pivot_stage0.py`
- `scripts/quant_research/process_cryptonewsdataset_llm.py`
- `scripts/quant_research/review_cryptonewsdataset_strong_model.py`
- `docs/quant_research/03_alpha_branches/event_tape_narrative_research_plan.md`
- `docs/quant_research/03_alpha_branches/mf05_cross_venue_boundary_stage0.md`
- `docs/quant_research/03_alpha_branches/mf05_cross_venue_spk_stage0.md`
- `docs/quant_research/03_alpha_branches/mf07_participant_disagreement_spk_stage0.md`
- `docs/quant_research/03_alpha_branches/mf07_subday_participant_pivot_stage0.md`
- related tests under `tests/test_quant_event_tape.py`,
  `tests/test_quant_mf05_*`, `tests/test_quant_mf07_*`,
  `tests/test_quant_cryptonewsdataset_*`, `tests/test_quant_label_builder.py`,
  and `tests/test_quant_research_dataset_builder.py`.

Decision:

- Hold until the package has its own validation run and summary.

## Package F: Cross-Cutting Core / Governance

Purpose: large tracked framework changes that are not cleanly attributable to
one of the requested research packages.

Recommended action: hold and audit separately before any staging.

Tracked files currently include:

- `.env.example`
- `CANONICAL_RUNBOOK.md`
- `PROJECT_STATE.md`
- `config/quant_research/threshold_provenance.md`
- `config/quant_research/validation_contract_h10d.json`
- `docs/quant_research/00_roadmap_state/data_utilization_roadmap.md`
- `docs/quant_research/00_roadmap_state/factor_audit_trail.md`
- `docs/quant_research/01_data_foundation/market_data_inventory.md`
- `scripts/quant_research/compute_subday_funding_factor_report.py`
- `scripts/quant_research/diagnose_shadow_vs_cycle.py`
- `scripts/quant_research/factor_report_card.py`
- `scripts/verify/run_local_integrity_gates.py`
- `src/enhengclaw/quant_research/deterministic_core.py`
- `src/enhengclaw/quant_research/execution_backtest.py`
- `src/enhengclaw/quant_research/falsification_audit.py`
- `src/enhengclaw/quant_research/feature_admission.py`
- `src/enhengclaw/quant_research/features.py`
- `src/enhengclaw/quant_research/governance.py`
- `src/enhengclaw/quant_research/hypothesis_batch.py`
- `src/enhengclaw/quant_research/lab.py`
- `src/enhengclaw/quant_research/market_data.py`
- `src/enhengclaw/quant_research/multiplier_overlay.py`
- `src/enhengclaw/quant_research/regime_gating.py`
- `src/enhengclaw/quant_research/shadow_oos.py`
- `src/enhengclaw/quant_research/shadow_proposals.py`
- `src/enhengclaw/quant_research/subday_funding_features.py`
- `tests/test_quant_hypothesis_batch.py`
- `tests/test_quant_research_core.py`

Decision:

- Do not stage these as a side effect of Package A.
- Review them as a separate "core quant framework" package because the diff is
  large and can change research semantics.

## Package G: Generated Artifacts

Purpose: local evidence and run outputs.

Recommended action: local-only by default.

Examples:

- `artifacts/quant_research/cycles/2026-04-30/` through
  `artifacts/quant_research/cycles/2026-05-07/`
- `artifacts/quant_research/experiments/**`
- `artifacts/quant_research/coinglass/**`
- `artifacts/quant_research/reports/**`
- `.claude/worktrees/**`
- `src/enhengclaw/quant_research/.claude/worktrees/**`

Decision:

- Do not stage bulk artifacts.
- Only force-add a report/card when it is explicitly required as a durable
  evidence artifact.
- Never stage `.claude/worktrees/**`.

## Recommended Order

1. Package A: R-1 strict gate.
2. Package B: CoinGlass provider/data stack.
3. Package D: Deribit/options, if still needed operationally.
4. Package C: onchain/M3.x/stablecoin.
5. Package E: event tape/MF/news dataset.
6. Package F: cross-cutting core/governance.
7. Package G: generated artifacts only by explicit exception.

## Staging Commands Template

Use path-explicit staging. Example for Package A:

```powershell
git add -- src/enhengclaw/quant_research/alpha_experiment_reporter.py `
  src/enhengclaw/quant_research/promotion.py `
  config/quant_research/promotion_gate_h10d.json `
  scripts/quant_research/assert_h10d_promotion_evidence.py `
  scripts/quant_research/audit_coinglass_h10d_parent_blocker_attribution.py `
  tests/test_quant_alpha_experiment_reporter.py
git diff --cached --stat
git diff --cached --check
python -m pytest .\tests\test_quant_alpha_experiment_reporter.py -q
```

For generated reports, do not force-add unless explicitly needed:

```powershell
git add -f -- artifacts/quant_research/reports/<exact-report>.md
```

## Stop Rules

- Stop if a package requires hidden dependencies from another package.
- Stop if a file belongs to two packages and cannot be hunk-staged safely.
- Stop if `git diff --cached --check` finds whitespace or line-ending issues
  that are not already expected.
- Stop if package tests fail.
- Stop if an artifact path contains secrets, local credentials, or
  machine-specific paths that should not become repo state.
