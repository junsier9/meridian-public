# Experiment 4 - Funding + OI Crowded Squeeze Failure

## Status

`stage0_watch`, not ready for canonical promotion.

The mechanism is economically plausible and the repo has the required raw
feature support, but the first broad cohort test is too weak. The only useful
signal appears after tightening to extreme crowding, and even that does not pass
same-day feature shuffle at the pre-registered Stage 0 threshold.

## Hypothesis

Pump names with positive funding, rising open interest, and weak/crowded
microstructure are more likely to suffer crowded-long liquidation during the
following holding period.

Mechanism:

- chasing longs pay funding
- OI rises as leverage accumulates
- weak orderbook/inventory support means new marginal buyers are fading
- once follow-through stalls, the later path is crowded-long unwind rather than
  continuation

## Repo Support

Current support is medium-high.

Required fields are already available in the 2026-05-02 cross-sectional feature
panel:

- `funding_zscore_20`: present, non-null fraction `1.0000`
- `oi_change_5`: present, non-null fraction `0.9954`
- `basis_zscore_20`: present, non-null fraction `1.0000`
- `pump_funding_oi_crowding_score_3d`: present, non-null fraction `0.9954`
- `coinglass_liq_intraday_concentration_24h`: present, non-null fraction
  `1.0000`
- pump context fields `distance_to_high_5` and `momentum_5`: present, non-null
  fraction `1.0000`

Important repo-native observation:

`pump_funding_oi_crowding_score_3d` is already included in the SP-K canonical
parent experiment feature set, but it has not been isolated as its own
independent alpha loop. This experiment should therefore be treated as a
short-side selection-layer candidate, not as another broad score overlay.

## Stage 0 Diagnostic

Script:

`scripts/quant_research/evaluate_funding_oi_crowded_squeeze_failure_stage0.py`

Primary artifacts:

- `artifacts/quant_research/factor_reports/2026-05-02/funding_oi_crowded_squeeze_failure_stage0.json`
- `artifacts/quant_research/factor_reports/2026-05-02/funding_oi_crowded_squeeze_failure_stage0_q90.json`
- `artifacts/quant_research/factor_reports/2026-05-02/spk_crowding_confirmation_stage0.json`

Method:

1. Use the 2026-05-02 feature panel.
2. Restrict to `liquid_perp_core_20` through the existing SP-K diagnostic helper.
3. Build a pump cohort from timestamp-relative ranks of:
   - `distance_to_high_5`
   - `momentum_5`
   - `pump_funding_oi_crowding_score_3d`
4. Build a crowding score from timestamp z-scores of:
   - `funding_zscore_20`
   - `oi_change_5`
   - `basis_zscore_20`
   - `pump_funding_oi_crowding_score_3d`
   - `coinglass_liq_intraday_concentration_24h`
5. Compare high-crowding pump names against the rest of the pump cohort on
   h3d/h5d/h10d short-side forward returns.
6. Run same-day feature shuffle on the h10d uplift.

## Results

### Broad crowding threshold

Parameters:

- pump quantile: `0.70`
- crowding quantile: `0.75`
- shuffle iterations: `200`

Result:

- verdict: `stage0_reject`
- checks passed: `2/5`
- pump rows: `6550`
- crowded rows: `2304`
- h3d short uplift: `+0.0010185780`
- h5d short uplift: `-0.0006932305`
- h10d short uplift: `+0.0004389570`
- h10d crowded short win fraction: `0.4934`
- h10d control short win fraction: `0.5012`
- same-day shuffle observed quantile: `0.575`
- same-day shuffle passed: `false`

Interpretation:

The broad candidate does not show enough short-side edge. It is not a canonical
replacement candidate.

### Extreme crowding threshold

Parameters:

- pump quantile: `0.70`
- crowding quantile: `0.90`
- shuffle iterations: `200`

Result:

- verdict: `stage0_watch`
- checks passed: `3/5`
- pump rows: `6550`
- crowded rows: `991`
- h3d short uplift: `+0.0001800826`
- h5d short uplift: `+0.0013840877`
- h10d short uplift: `+0.0039068648`
- h10d crowded short win fraction: `0.4964`
- h10d control short win fraction: `0.4988`
- same-day shuffle observed quantile: `0.870`
- same-day shuffle p95 uplift: `0.0067417242`
- same-day shuffle passed: `false`

Interpretation:

There is a weak h10d tail signal in the extreme crowding bucket, but it is not
shuffle-clean. This matches the pre-registered failure risk: the effect may only
exist in a narrow extreme subset and may be too unstable for a clean canonical
experiment without further conditioning.

## Decision

Do not add a full crowding feature family to the base score yet.

Do not run a broad canonical replacement/veto A/B yet.

Keep the experiment as `stage0_watch` only if it is narrowed into an
event-conditioned short-side rule.

## Next Executable Slice

The next version should test a narrower rule:

`SP-K + extreme crowding confirmation`

Candidate landing shape:

- preserve canonical parent longs
- preserve SP-K's short-boundary replacement architecture
- allow crowding only as a confirmation/veto on candidate short replacements
- restrict to `crowding_pct >= 0.90`
- require pump context and weakening follow-through
- do not allow crowding to perturb the full score

Minimum go-forward criteria:

- h10d short uplift positive after same-day feature shuffle with observed
  quantile at least `0.90`
- h5d and h10d uplift both positive
- crowded short win fraction at least matches control
- canonical parent paired edge positive in strict aligned-period test
- at least 70% of uplift survives +1d delay and 2x cost stress

Failure criteria:

- only the most extreme bucket works and sample count collapses
- the rule is redundant with SP-K replacement selection
- admission looks positive but mother-strategy increment remains zero or
  negative
- strict falsification fails on label shuffle, symbol shuffle, delay, or cost
  stress

## Priority

Priority should be revised from unconditional `P1` to conditional `P1-watch`.

It is worth doing after SP-K canonical hardening and MF-01, but only as a narrow
confirmation layer. The current evidence does not justify a standalone
canonical experiment.

## Follow-Up Slice: SP-K + Extreme Crowding Confirmation

Script:

`scripts/quant_research/evaluate_spk_crowding_confirmation_stage0.py`

Rule:

- preserve canonical parent longs
- start from SP-K `replace_mid_v1`
- only allow an SP-K replacement candidate when its timestamp-level crowding
  percentile is at least `0.90`
- do not perturb the full base score

Result:

- verdict: `stage0_watch`
- checks passed: `5/7`
- parent vs SP-K replacements: `575`
- parent vs SP-K+crowding-confirmed replacements: `89`
- confirmed replacement position fraction: `0.0272`
- confirmed entered h10d mean: `-0.0066398141`
- confirmed exited h10d mean: `+0.0028950529`
- SP-K entered h10d mean: `-0.0089902816`
- SP-K short basket h10d mean: `-0.0028112693`
- SP-K+crowding-confirmed short basket h10d mean: `-0.0019769083`

Interpretation:

The confirmation layer does what it was designed to do mechanically: it narrows
SP-K replacement from `575` replacements to `89` and those confirmed
replacements beat the parent exits. But it does not beat raw SP-K. The filtered
out SP-K replacements are actually stronger on h10d, and the full confirmed
short basket is weaker than the raw SP-K basket.

Decision update:

Do not create a checked-in canonical manifest for SP-K+crowding confirmation
yet. Crowding is not a good hard confirmation gate for SP-K. If this mechanism
continues, it should pivot from "confirm SP-K replacements" to one of two more
specific tests:

1. Use crowding as a `do-not-long / do-not-chase` veto rather than a short
   replacement confirmation.
2. Condition crowding on explicit failed follow-through, where the crowding
   bucket is not merely high leverage but high leverage after buyer exhaustion.
