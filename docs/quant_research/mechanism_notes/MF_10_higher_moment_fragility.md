# MF-10: Realized higher-moment fragility

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: active`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1`

---

## Economic story

Crypto returns are *structurally* fat-tailed and asymmetric. Daily and 5-day
distributions show kurtosis well above the gaussian baseline and skew that
varies systematically with regime. Higher-moment factors capture two
mechanisms that are invisible to standard volatility z-scores:

1. **Asymmetric tail pricing**: the 30-day ratio of conditional std on
   negative-return days to that on positive-return days measures the
   asymmetry directly. When the ratio is high, downside moves are priced as
   more extreme than upside — this is the realised analogue of the
   put-skew premium and tends to mean-revert upward (the asymmetric premium
   compresses).
2. **Vol-of-vol mean reversion**: realised volatility is itself a noisy
   process. Periods of high vol-of-vol (the rolling std of 20-day RV)
   command a risk premium; the premium compresses over the following
   2–4 weeks.

Range-based measures (high-low / close, normalised by 60-day mean) capture
intra-day extremes that close-only RV misses. A 60-day z-score of this
normalised range is a clean *fragility* indicator that fires before a vol
regime change.

The W1.3 cards confirm the economic intuition: F33 (downside-upside vol
ratio) is the strongest W1.1 candidate, passing 9/11 gates with full
regime sign-consistency. F35 (vol-of-vol) is slow but stable; F31 / F32
(realised skew / kurt) carry directional signal but fail G6 against the
v91 baseline as currently parameterised.

## Why this alpha persists

- **Higher-moment estimators are noisy**: 20-bar skew and kurt have wide
  sampling distributions; teams that test on short windows reject them
  prematurely.
- **Asymmetry pricing requires a thoughtful conditional-std estimator**:
  naive one-line implementations of "downside vol" via dividing series into
  positive and negative subsets and computing std lose signal because of
  small-sample noise. F33's `min_periods=5` choice is load-bearing.
- **Mean reversion of risk premium is slow**: 14–30 day half-lives are
  longer than typical rebalance horizons, so factor-decay aware tests on
  5-day forward returns under-reward the family.

## Required primitives

- `return_1` — derived in `features.py` from `spot_close` percent change.
- `realized_volatility_20` — derived in `features.py`; load-bearing for F33
  / F35 / F36.
- `spot_high`, `spot_low`, `spot_close` — for F36 normalised range.

All primitives are in the panel; no new ingest required.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F31 | `realized_skew_20_xs_z` | + (negative skew = downside priced in → upward revert) | 7–14 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC −0.013) |
| F32 | `realized_kurt_20_xs_z` | cond | 5–10 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC −0.001) |
| F33 | `downside_upside_vol_ratio_30` | − (downside premium compresses upward) | 7–14 | T1 | **W1.1 implemented**, **admitted**, **in active manifest** (`xs_alpha_ontology_v1`); 9/11 gates |
| F34 | `jump_intensity_proxy` (TBD) | cond | 3–5 | T1 | not implemented |
| F35 | `vol_of_vol_60` | − (vol-of-vol high = premium high) | 14–30 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC +0.008) |
| F36 | `abnormal_range_z_60` | cond | 3–5 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC +0.011) |

## Expected sign and half-life

F33 is the empirically strongest factor in the family with positive IC
(0.031) and full regime sign-consistency. The doc's a-priori sign for F33
is negative (downside vol high → premium compresses upward → buy), and
because the v_alpha_v1 manifest applies a +0.10 weight to the column with
the underlying interpretation being "high downside-upside ratio →
mean-revert", the realised IC sign is consistent with the doc's
prediction.

## Regime where strongest

F33: regime-agnostic (regime same-sign 100% in W1.3 — the strongest
property of the family). F35: vol-of-vol extremes (high or low). F36:
range-expansion regimes. F31 / F32: tail-driven regimes where realised
moments materially deviate from the rolling baseline.

## Failure modes

- Single-outlier domination — kurtosis especially is sensitive to one large
  bar. F32's residual IC is essentially zero for this reason on the current
  panel.
- Sparse moment estimates — 20-bar windows are short for the 4th-moment
  estimator. F32 is the most fragile factor in the family.
- Vol-regime structural shift — if realised vol level structurally changes
  (e.g. major leverage regulation), the 60-day rolling baseline takes 60
  days to catch up; F35 is suspended during that catch-up.

## Falsification path

- F33: rolling 60d residual IC drops below 0.02 for 90 consecutive days →
  retire. (Direct trigger in the `xs_alpha_ontology_v1` manifest's
  `falsification_conditions`.)
- F35 / F36: rolling 60d residual IC stays below 0.02 for 90 days → retire
  (slow-variable; evaluation cadence is monthly).
- Family-level: if combined residual IC (F33 + F35 + F36 orthogonal to v91)
  collapses to < 0.02 for 60 days → revisit half-life parameter choices
  before retiring; the family signal is real but parameter-sensitive.

## Implementation status

- in `features.py`: F31 (`realized_skew_20_raw` + `_xs_z`), F32
  (`realized_kurt_20_raw` + `_xs_z`), F33 (`downside_upside_vol_ratio_30`),
  F35 (`vol_of_vol_60`), F36 (`abnormal_range_z_60`) all from W1.1.
- admitted via `feature_admission.py`: F31 and F32 via W1.2 prefix
  (`realized_skew_*`, `realized_kurt_*`); F33, F35, F36 via exact-column
  allowlist.
- present in any active manifest: F33 in
  `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json` with
  weight +0.10. F35 / F36 are admitted but not in the manifest because
  they failed G6 in W1.3.
- report-carded: see
  `artifacts/quant_research/factor_reports/2026-04-29/F3{1,2,3,5,6}_*.{json,txt}`.

Next action: implement F34 (`jump_intensity_proxy`) — the only blueprint
not yet built. It is conceptually orthogonal to F33 (intra-day jump rather
than inter-day asymmetry) and should be tested in the v_alpha_v2
manifest expansion alongside any cross-validation of F35 / F36 on a
post-W1.4 cycle's residuals.

## Cross-references

- Alpha ontology memo §B (MF-10 row), §D (Family MF-10 table), §F top-20
  prioritisation (F31 at #5, F33 at #10, F35 at #16).
- Active manifest:
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json`
  (F33 entry).
- Threshold provenance log: `config/quant_research/threshold_provenance.md`
  W1.3 / W1.4 entry.

---

## Change log

- `2026-04-29` — initial note created from §B / §D content (W1.5). Status
  set to `active` because F33 is in the live manifest.
