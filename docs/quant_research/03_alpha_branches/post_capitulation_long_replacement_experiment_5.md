# Experiment 5 - Post-Capitulation Long Replacement

## Status

`stage0_reject` for canonical long-boundary replacement.

The repo has enough liquidation and orderbook support to test the idea, but the
first executable slice does not support replacing canonical parent long slots.
The post-capitulation rebound signal raises the rebound-score composition of
the long basket, yet it replaces better parent longs with weaker forward-return
names.

## Hypothesis

After forced liquidation selling exhausts, names with restored bid support
should have better rebound continuation odds. If the canonical parent selects a
weaker long near the top boundary, a post-capitulation rebound candidate should
be able to replace it.

Mechanism:

- liquidation cascade reflects forced selling, not always deteriorating
  fundamentals
- once selling pressure clears, bid replenishment signals renewed support
- rebound continuation should be visible at the long boundary, not necessarily
  as a broad global score overlay

## Repo Support

Current support is medium-high after merging the raw feature panel columns back
into the Stage 0 frame.

Feature availability on the 2026-05-02 feature panel:

- `liq_cascade_recency_score_5d`: present, non-null fraction `1.0000`
- `liq_cascade_signed_intensity_24h`: present, non-null fraction `1.0000`
- `coinglass_liq_intraday_concentration_24h`: present, non-null fraction
  `1.0000`
- `ob_bid_replenishment_ratio_1d`: present, non-null fraction `0.6522`
- `coinglass_orderbook_imb_persistence_24h`: present, non-null fraction
  `1.0000`

Implementation note:

The existing risk-frame helper does not preserve the two raw cascade columns by
default. The Stage 0 runner explicitly merges them back from
`features.csv.gz` before scoring, so the reported results are full-signal
results, not orderbook-only results.

## Stage 0 Diagnostic

Script:

`scripts/quant_research/evaluate_post_capitulation_long_replacement_stage0.py`

Primary artifacts:

- `artifacts/quant_research/factor_reports/2026-05-02/post_capitulation_long_replacement_stage0.json`
- `artifacts/quant_research/factor_reports/2026-05-02/post_capitulation_long_replacement_stage0_q90.json`

Method:

1. Use the 2026-05-02 cross-sectional feature panel.
2. Restrict to the same liquid perp core universe via the existing SP-K
   diagnostic helper.
3. Merge raw cascade columns back into the risk frame.
4. Build `post_capitulation_rebound_score_v1` from timestamp z-scores:
   - `liq_cascade_recency_score_5d`
   - `liq_cascade_signed_intensity_24h`
   - `coinglass_liq_intraday_concentration_24h`
   - `ob_bid_replenishment_ratio_1d`
   - `coinglass_orderbook_imb_persistence_24h`
5. Preserve the canonical parent score.
6. Only inspect the top-6 long pool.
7. Replace at most one top-3 parent long when a non-selected pool candidate has
   a high rebound percentile and the selected parent long does not.
8. Compare entered versus exited long names and full long-basket h10d behavior.

## Results

### 75% signal threshold

Parameters:

- replacement pool size: `6`
- signal quantile: `0.75`

Result:

- verdict: `stage0_reject`
- checks passed: `1/6`
- replacements: `396`
- replacement position fraction: `0.1209`
- entered h10d mean: `-0.0041390989`
- exited h10d mean: `+0.0042802541`
- entered h10d hit fraction: `0.4369`
- exited h10d hit fraction: `0.5379`
- parent long basket h10d mean: `+0.0077995870`
- replacement long basket h10d mean: `+0.0067854258`
- parent long basket hit fraction: `0.5499`
- replacement long basket hit fraction: `0.5376`

Interpretation:

The replacement rule actively hurts the parent long boundary. It increases
rebound-score purity, but the selected high-rebound names have worse realized
h10d returns than the canonical parent longs they replace.

### 90% signal threshold

Parameters:

- replacement pool size: `6`
- signal quantile: `0.90`

Result:

- verdict: `stage0_reject`
- checks passed: `2/6`
- replacements: `178`
- replacement position fraction: `0.0543`
- entered h10d mean: `+0.0002419654`
- exited h10d mean: `+0.0033071981`
- entered h10d hit fraction: `0.4663`
- exited h10d hit fraction: `0.5506`
- parent long basket h10d mean: `+0.0077995870`
- replacement long basket h10d mean: `+0.0076324440`
- parent long basket hit fraction: `0.5499`
- replacement long basket hit fraction: `0.5453`

Interpretation:

The extreme-threshold rule is less harmful but still does not improve the
canonical long basket. It is not manifest-ready.

## Decision

Do not promote this as a canonical long-boundary replacement experiment.

Do not run WF/falsification for this exact replacement rule yet.

The current evidence says the canonical parent is already selecting better long
names than the simple post-capitulation rebound ranker, even when the rebound
ranker is restricted to top-boundary candidates.

## Pivot

The mechanism should not be discarded, but its landing shape should change.

Recommended next test:

`post-capitulation rebound sleeve / long add-on`

Rationale:

- The signal may identify rebound names, but not names better than the current
  canonical top-3 long slots.
- Replacing parent longs is too expensive in opportunity cost.
- A more natural landing shape is a separate rebound sleeve activated only when
  the parent has weak or sparse long conviction, or a `do-not-short` veto after
  liquidation release.

Minimum evidence required before returning to canonical replacement:

- entered long h10d mean must exceed exited parent long h10d mean
- entered h10d hit rate must match or exceed exited hit rate
- full long basket must improve either next-horizon mean or hit rate
- extreme liquidation days cannot account for most of the uplift
- orderbook-ablation must reduce the edge, proving bid replenishment matters

## Priority

Revise from unconditional `P1` to `P1-reframed`.

The liquidation/cascade data support is mature, but this exact long-boundary
replacement shape failed Stage 0. The next useful slice is not a stricter
replacement threshold; it is a different landing shape.
