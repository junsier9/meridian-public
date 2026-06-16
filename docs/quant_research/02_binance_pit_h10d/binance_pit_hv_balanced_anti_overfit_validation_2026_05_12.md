# Binance PIT HV Balanced Anti-Overfit Validation

`Frozen strategy: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget`
`Status: passed_diagnostic_freeze`
`Config SHA256: 9867437bc74733d46f1a4292c84bbdf4f09c6c49f4862a0616d95ebc43f31938`

## Freeze

- Decision: freeze as a research candidate, not live-approved.
- No tuning allowed on features, feature weights, PIT universe, costs, high-vol thresholds, soft-budget thresholds, holdout gates, or bucket gates.
- Frozen config: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\config\quant_research\binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json`
- Frozen manifest: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\anti_overfit_hv_balanced_20260512\frozen_strategy_manifest.json`

## Core Metrics

| Variant | Status | Base net | Sharpe | Max DD | Stress net | Holdout | Min fold | Median fold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pruned3 | passed | 2.704409 | 1.056 | 0.357654 | 2.671102 | 13/16 | -0.360083 | 0.366199 |
| hv_base | passed | 3.509528 | 1.296 | 0.285178 | 3.469171 | 13/16 | -0.280978 | 0.549423 |
| hv_tail | passed | 3.400482 | 1.285 | 0.283569 | 3.360634 | 13/16 | -0.288272 | 0.548533 |
| hv_mild | passed | 3.361901 | 1.282 | 0.282072 | 3.322109 | 13/16 | -0.277899 | 0.552644 |
| hv_balanced | passed | 3.241191 | 1.270 | 0.279320 | 3.202118 | 13/16 | -0.264864 | 0.553959 |
| combined_v1 | passed | 1.461132 | 1.013 | 0.210697 | 1.444297 | 12/16 | -0.390415 | 0.380289 |

## Parameter Neighborhood

| Variant | Start DD | Full DD | Floor | Passed | Net vs HV base | DD vs HV base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hv_tail | 0.15 | 0.30 | 0.85 | True | -0.109046 | -0.001610 |
| hv_mild | 0.12 | 0.28 | 0.85 | True | -0.147626 | -0.003106 |
| hv_balanced | 0.10 | 0.25 | 0.80 | True | -0.268337 | -0.005859 |

Interpretation: `hv_balanced` is not an isolated pass. Tail, mild, and balanced variants all pass; stronger budgets trade return for lower drawdown smoothly.

## Forward-Style Segments

These are chronological diagnostics, not clean external OOS. They reduce but do not eliminate reuse-of-history risk.

| Variant | Segment | Periods | Net | Sharpe | Max DD |
| --- | --- | ---: | ---: | ---: | ---: |
| hv_base | early_2021_2022 | 61 | 0.809707 | 1.527 | 0.171513 |
| hv_base | middle_2023_2024 | 73 | 0.366073 | 0.727 | 0.285178 |
| hv_base | late_2025_2026 | 49 | 0.824102 | 1.886 | 0.146403 |
| hv_tail | early_2021_2022 | 61 | 0.805640 | 1.523 | 0.171705 |
| hv_tail | middle_2023_2024 | 73 | 0.336042 | 0.693 | 0.283569 |
| hv_tail | late_2025_2026 | 49 | 0.824102 | 1.886 | 0.146403 |
| hv_mild | early_2021_2022 | 61 | 0.801613 | 1.520 | 0.171882 |
| hv_mild | middle_2023_2024 | 73 | 0.330411 | 0.688 | 0.282072 |
| hv_mild | late_2025_2026 | 49 | 0.819820 | 1.882 | 0.146403 |
| hv_balanced | early_2021_2022 | 61 | 0.792422 | 1.512 | 0.172221 |
| hv_balanced | middle_2023_2024 | 73 | 0.305919 | 0.661 | 0.279320 |
| hv_balanced | late_2025_2026 | 49 | 0.811888 | 1.872 | 0.146617 |
| combined_v1 | early_2021_2022 | 61 | 0.155988 | 0.553 | 0.210697 |
| combined_v1 | middle_2023_2024 | 73 | 0.466192 | 1.038 | 0.133884 |
| combined_v1 | late_2025_2026 | 49 | 0.452081 | 1.548 | 0.126467 |

## Throttle Audit

- throttled periods: `48`
- min multiplier: `0.800000`
- average multiplier on throttled periods: `0.913745`
- selected base net: `3.241191`
- selected max DD: `0.279320`

## Decision

`hv_balanced` is frozen as the current Binance-only research candidate. This package supports freeze, not live approval.

Residual risk remains because the same five-year history has been inspected repeatedly. The next honest evidence must come from a frozen paper/shadow run or a truly future OOS slice.
