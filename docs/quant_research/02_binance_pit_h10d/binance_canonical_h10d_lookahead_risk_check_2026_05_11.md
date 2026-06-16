# Binance-Canonical H10D Lookahead Risk Check

`Strategy: v5_binance_ohlcv_core_h10d`
`Run: lrisk_1k`
`Reference capital: 1000 USD`
`Universe mode: rolling_quote_volume`
`Question: does the frozen 2026-04-30 core20 filter create real survivorship/lookahead risk?`

## Decision

Yes, the risk is real.

The frozen `2026-04-30` core20 membership filter is not just a theoretical concern. It changes historical candidate selection and materially improves the diagnostic ablation relative to pure point-in-time liquidity-only alternatives.

However, the result is not entirely dependent on the lookahead filter. Fully PIT variants remain positive after variant-specific gap cleaning, so the useful signal direction appears real enough to continue research. The current frozen-core20 diagnostic still cannot be used as promotion evidence.

## Test Design

All variants were rebuilt from the same Binance-only scored frame and each variant received its own selected-path gap exclusion.

| Variant | Long eligibility | Short eligibility | Future membership used? |
| --- | --- | --- | --- |
| `frozen_current` | frozen 2026 core20 | frozen 2026 non-core + `mid_liquidity` | yes |
| `pit_top_mid` | PIT `top_liquidity` | PIT `mid_liquidity` | no |
| `pit_active_mid` | PIT rolling active universe | PIT `mid_liquidity` | no |
| `frozen_long_pit_short` | frozen 2026 core20 | PIT `mid_liquidity` | long side only |
| `pit_long_frozen_short` | PIT `top_liquidity` | frozen 2026 non-core + `mid_liquidity` | short side only |
| `core20_short_disabled` | PIT rolling active universe | frozen 2026 non-core | short side only |

## Headline Results

| Variant | Base net | Sharpe | Stress net | Max DD | Max participation | Gap-clean excluded |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `frozen_current` | 10.101955 | 1.763 | 10.011808 | 0.311 | 0.000071 | LTC, ONE, XRP |
| `pit_top_mid` | 4.959062 | 1.347 | 4.906573 | 0.304 | 0.000024 | NEAR, ONE, XRP |
| `pit_active_mid` | 6.949735 | 1.519 | 6.877213 | 0.305 | 0.000024 | LTC, NEAR, ONE, XRP |
| `frozen_long_pit_short` | 6.552415 | 1.488 | 6.484683 | 0.305 | 0.000024 | LTC, NEAR, ONE, XRP |
| `pit_long_frozen_short` | 7.550407 | 1.579 | 7.482125 | 0.343 | 0.000071 | ONE, XRP |
| `core20_short_disabled` | 7.353625 | 1.533 | 7.289825 | 0.396 | 0.000071 | LTC, MANA, ONE, SAND, XRP |

## Selection Impact

The frozen-core long filter changes the historical long book depending on the PIT comparator:

| Comparison | Changed decisions | Changed rate | Long selection Jaccard | Differing long selections |
| --- | ---: | ---: | ---: | ---: |
| frozen current vs PIT top-liquidity long | 97 / 176 | 55.1% | 0.674 | 103 each side |
| frozen current vs PIT active-universe long | 10 / 176 | 5.7% | 0.963 | 10 each side |

Interpretation: if "PIT core" means rolling top-liquidity/top-rank, frozen 2026 core20 materially changes historical long selection. If "PIT core" means the full rolling active top20 universe, the long-side selection change is small because most chosen long names already overlap the future core20.

The larger lookahead effect is on the short side. Excluding future core20 names from the short sleeve is a future-known classification and removes the toxic core20 short bucket that earlier attribution identified.

## By-Year Check

| Variant | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `frozen_current` | 0.265904 | 1.167105 | 0.049157 | 0.961567 | 0.840160 | 0.068610 |
| `pit_top_mid` | 0.324554 | 0.863062 | -0.038435 | 0.481650 | 0.485120 | 0.141288 |
| `pit_active_mid` | 0.250982 | 1.258358 | 0.081719 | 0.435916 | 0.609098 | 0.125856 |

The pure PIT variants remain positive overall, but the frozen current variant is smoother and much stronger. That spread is enough to confirm the frozen reference list is affecting the conclusion.

## Conclusion

The survivorship/lookahead risk is real and material. The frozen core20 diagnostic should stay labeled as diagnostic only.

The research direction is still alive because pure PIT variants remain positive after variant-specific gap cleaning. The next valid test should define the liveable split entirely with PIT rules, for example:

- long: rolling top-liquidity/top-rank only;
- short: rolling mid-liquidity only;
- no 2026 membership list in either sleeve;
- variant-specific selected-path gap exclusion before reporting pass/fail.

## Source Artifacts

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\lrisk_1k\analysis.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\lrisk_1k\cmp_frozen_pit_top.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\lrisk_1k\cmp_frozen_pit_active.csv`
