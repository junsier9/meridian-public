# Phase 5.8 H10D Diagnostics Root-Level Dry-Run

`Status: read-only dry-run`
`Date: 2026-05-13`
`Scope: 24 h10d/root candidates from the remaining root-level script refactor inventory`
`Baseline commit: 4cc4eb8 Phase 5.7 provider diagnostics script path refactor`

## Decision

Do not move h10d diagnostics in this phase.

This dry-run only classifies the 24 h10d/root candidates from
`script_path_refactor_remaining_root_dry_run_2026_05_13.md` into four
mutually exclusive buckets:

- `current-line`
- `historical-only`
- `module-import-dependent`
- `wrapper-safe`

The purpose is to avoid treating current Binance PIT h10d entrypoints,
historical A/B modules, and CoinGlass h10d parent evidence scripts as one
generic utility cleanup batch.

## Classification Rules

- `current-line`: active or default-entrypoint h10d/Binance PIT scripts. These
  stay at root for now, even when a wrapper could technically preserve CLI
  compatibility.
- `module-import-dependent`: a script is imported by another repo script, or it
  imports sibling root h10d scripts by bare module name. A CLI-only wrapper is
  not sufficient for these.
- `historical-only`: historical evidence scripts that are not current-line and
  do not have the standard `main(argv)` wrapper shape. They need an explicit
  wrapper strategy before any move.
- `wrapper-safe`: historical scripts with no discovered sibling module import
  dependency and a `main(argv)` / `parse_args(argv)` CLI contract. These are the
  only plausible low-risk h10d move candidates, but this dry-run does not move
  them.

## Summary

| bucket | count | move posture |
| --- | ---: | --- |
| `current-line` | 7 | keep root; defer any path change |
| `module-import-dependent` | 8 | defer; requires package import rewrite or root re-export shim |
| `historical-only` | 2 | defer; no standard `main(argv)` wrapper shape |
| `wrapper-safe` | 7 | possible later batch after target directory approval |

## Current-Line

`Count: 7`
`Decision: do not move`

These are active/default h10d or Binance PIT scripts. Even if a wrapper could
preserve CLI compatibility, keeping the root path stable is the lowest-risk
choice while h10d remains the current roadmap line.

| script | catalog status | evidence | dry-run decision |
| --- | --- | --- | --- |
| `analyze_binance_pit_drawdown_attribution.py` | `active` / `default_entrypoint` | default entrypoint in README and catalog | keep root |
| `build_binance_hv_balanced_anti_overfit_package.py` | `active` / `default_entrypoint` | default entrypoint; also uses `main()` not `main(argv)` | keep root |
| `run_binance_canonical_h10d_validation.py` | `active` / `default_entrypoint` | current h10d validation docs call this exact root path | keep root |
| `run_baseline_alpha_proof.py` | `active` / `supporting_tool` | active baseline proof runner | keep root |
| `run_baseline_alpha_survival.py` | `active` / `supporting_tool` | active deterministic survival runner | keep root |
| `run_binance_spot_concordance_baseline.py` | `active` / `supporting_tool` | active Binance spot concordance support tool | keep root |
| `validate_baseline_alpha_confidence.py` | `active` / `supporting_tool` | referenced by baseline confidence docs and previous dry-runs | keep root |

## Module-Import-Dependent

`Count: 8`
`Decision: do not move without package import rewrite or root re-export shim`

These scripts participate in a root-level h10d module graph. Moving any of
them with only a CLI wrapper would preserve `python script.py ...` but could
break in-repo imports or sibling bare imports.

| script | dependency evidence | required move strategy |
| --- | --- | --- |
| `evaluate_v5_h10d_post_pump_short_replacement.py` | imports `evaluate_v6_h10d_post_pump_short_replacement`; is imported by multiple stage0/audit scripts | package import rewrite across callers before move |
| `evaluate_v6_h10d_mf01_narrow_ab.py` | imports `evaluate_v6_h10d_post_pump_short_replacement` and `evaluate_v6_h10d_orderbook_short_replacement` by bare module name | rewrite internal imports before move |
| `evaluate_v6_h10d_orderbook_short_replacement.py` | imported by `evaluate_v6_h10d_mf01_narrow_ab.py`; imports h10d base module | package import rewrite; keep root wrapper if moved |
| `evaluate_v6_h10d_post_pump_news_veto_ab.py` | imported by selected-short exposure/news veto scripts; imports h10d base module | package import rewrite; keep root wrapper if moved |
| `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py` | imports `evaluate_v6_h10d_post_pump_news_veto_ab` and h10d base module | rewrite internal imports before move |
| `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py` | imports `evaluate_v6_h10d_post_pump_news_veto_ab` and h10d base module | rewrite internal imports before move |
| `evaluate_v6_h10d_post_pump_short_replacement.py` | imported by many h10d/stage0 scripts as the base evaluation module | root re-export shim or broad package import rewrite |
| `run_coinglass_h10d_parent_frozen_reset_strict.py` | imported by `run_coinglass_r1a_top_liquidity_ex_trx_strict.py` | package import rewrite before move |

## Historical-Only

`Count: 2`
`Decision: defer`

These are historical CoinGlass h10d parent evidence scripts. They are not
current-line entrypoints and do not show a sibling module import dependency,
but they also do not expose the standard `main(argv)` wrapper contract.

| script | evidence | blocker |
| --- | --- | --- |
| `audit_coinglass_h10d_parent_blocker_attribution.py` | historical; only staging-plan doc reference found | `main()`/`main() -> None` shape; wrapper must call without forwarded argv |
| `audit_coinglass_h10d_parent_fast_reject_stages.py` | historical; only staging-plan doc reference found | `main()` parses `sys.argv` internally; wrapper needs explicit strategy |

## Wrapper-Safe

`Count: 7`
`Decision: possible later low-risk batch, not now`

These scripts have no discovered sibling module import dependency and expose
`main(argv)` with `parse_args(argv)`. They are the cleanest candidates if a
future `h10d_diagnostics/` or `historical_h10d_diagnostics/` directory is
approved.

| script | evidence | possible target |
| --- | --- | --- |
| `combine_alpha_ontology_h10d_overlay_ablation_partials.py` | historical; no non-catalog refs found; `main(argv)` | historical h10d diagnostics |
| `compare_alpha_ontology_h10d_fixed_set.py` | historical; no non-catalog refs found; `main(argv)` | historical h10d diagnostics |
| `compare_alpha_ontology_h10d_overlay_ablation.py` | historical; no non-catalog refs found; `main(argv)` | historical h10d diagnostics |
| `evaluate_v6_h10d_post_pump_short_overlay.py` | historical; doc reference from SP-K proposal; no sibling import dependency | historical h10d diagnostics |
| `audit_coinglass_h10d_parent_drift.py` | historical; staging-plan doc reference only; `main(argv)` | CoinGlass h10d historical diagnostics |
| `audit_coinglass_h10d_parent_rebaseline.py` | historical; staging-plan doc reference only; `main(argv)` | CoinGlass h10d historical diagnostics |
| `audit_coinglass_h10d_parent_strict_cycle_probe.py` | historical; staging-plan doc reference only; `main(argv)` | CoinGlass h10d historical diagnostics |

## Deferred Risks

- Do not move any `current-line` script before deciding whether h10d default
  entrypoints should remain root-only public paths.
- Do not batch `module-import-dependent` scripts with simple wrapper-safe
  scripts. They need import rewrites or root re-export shims.
- Do not place historical h10d diagnostics into `report_writers/`,
  `provider_diagnostics/`, or `alpha_branch_reports/`. Their semantics are
  h10d evidence, not generic report writing or provider validation.
- Do not treat the CoinGlass h10d parent scripts as provider diagnostics just
  because their artifacts live under CoinGlass directories. They are h10d
  parent evidence scripts.

## Recommended Next Step

If continuing script-path cleanup, use a separate implementation plan for the
7 `wrapper-safe` historical h10d diagnostics. The plan must first choose a
specific target directory name and confirm that the directory contract does not
blur current h10d entrypoints with historical h10d evidence.

Suggested target options:

- `scripts/quant_research/h10d_diagnostics/`
- `scripts/quant_research/historical_h10d_diagnostics/`

Prefer the second name if the first batch contains only historical evidence
scripts.

## Verification For This Dry-Run

This dry-run changes only documentation. Run:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Also run the local Markdown link checker because this document must be indexed
by the governance contract.
