# Binance-Canonical H10D Core20 Short Filter Ablation

`Strategy: v5_binance_ohlcv_core_h10d`
`Run: 20260511Tcore20LongShortFilters-1k-v5_binance_ohlcv_core_h10d`
`Reference capital: 1000 USD`
`Universe mode: rolling_quote_volume`
`Execution gap policy: drop_selected_path_gap_symbols`

## Decision

Two requested variants were tested:

1. `core20_long_noncore_mid_short`: long sleeve restricted to the frozen 2026-04-30 core20 reference set; short sleeve restricted to non-core `mid_liquidity` names.
2. `core20_short_disabled`: core20 reference names disabled for shorts; long sleeve and non-core short sleeve otherwise unchanged.

`core20_long_noncore_mid_short` is the cleaner result: it has no fill/exit gap blockers, passes base/stress/capacity on the ablation metrics, and is positive in every calendar year. It should still be treated as diagnostic, not promotion evidence, because the long sleeve uses a frozen 2026-04-30 reference core20 set across the full history.

`core20_short_disabled` looks strong on headline return, but it is blocked by variant-specific fill/exit gaps in `MANA`. Under the fail-closed rule, that variant is not a valid strategy conclusion until rerun with variant-specific selected-path gap exclusion.

The original base strategy remains failed because the main validation gate still fails `liquidity_positive_bucket_gate`.

## Headline Metrics

| Variant | Base net | Base Sharpe | Base max DD | Stress net | Stress Sharpe | Max trade participation | Capacity breaches | Data gap blockers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| core20_long_noncore_mid_short | 9.190193 | 1.757 | 0.311 | 9.109537 | 1.751 | 0.000071 | 0 | none |
| core20_short_disabled | 5.324781 | 1.378 | 0.396 | 5.276137 | 1.372 | 0.000071 | 0 | MANA fill/exit |

## By-Year Compounded Return

| Variant | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| core20_long_noncore_mid_short | 0.123828 | 1.149920 | 0.055755 | 0.953180 | 0.903775 | 0.074333 |
| core20_short_disabled | 0.130496 | 1.083869 | -0.136075 | 0.694195 | 0.798949 | 0.019643 |

## Interpretation

The test supports the previous attribution diagnosis: the toxic sleeve is not "all shorts"; it is core20/top-liquidity shorts. Once core20 shorts are removed and the short sleeve is pushed into non-core/mid-liquidity names, the ablation improves sharply.

However, the best-looking variant is not yet a liveable promotion candidate. The frozen core20 reference set is known at `2026-04-30`, so using it across 2021-2026 can introduce survivorship/lookahead effects. The next promotion-grade test must replace the frozen core20 long filter with a point-in-time core rule, such as rolling top-liquidity/top-rank eligibility, then rerun full falsification and variant-specific gap exclusion.

## Code/Artifact Changes

- Added `long_decision_eligible_column` and `short_decision_eligible_column` support to cross-sectional target weighting.
- Added ablations:
  - `core20_long_noncore_mid_short`
  - `core20_short_disabled`
- Added the frozen 2026-04-30 `reference_core20_subjects` list to the Binance-canonical config for reproducible diagnostics.

## Verification

- `python -m pytest tests\test_execution_backtest.py tests\test_binance_canonical_h10d.py -q`
- Result: `35 passed`

## Source Artifacts

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511Tcore20LongShortFilters-1k-v5_binance_ohlcv_core_h10d\validation_report.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511Tcore20LongShortFilters-1k-v5_binance_ohlcv_core_h10d\ablation_summary.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511Tcore20LongShortFilters-1k-v5_binance_ohlcv_core_h10d\ablation_period_returns.csv`
