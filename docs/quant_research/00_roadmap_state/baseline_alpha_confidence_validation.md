# Baseline Alpha Confidence Validation

`Snapshot date: 2026-05-03`
`Owner: quant_research_maintainer`
`Status: executable validation scaffold`

2026-06-03 supersession note:

- This validator remains useful as black-box evidence for the `v5_rw_bridge_no_overlay_h10d` score parent and its archived single-phase fixed-set return stream.
- It is not, by itself, the current follow-on research baseline performance claim.
- Current follow-on h10d research baseline means `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`: the same score parent plus 10-phase equal-sleeve portfolio construction.

---

## Purpose

This note validates the confidence of the current h10d baseline alpha by a
logic different from the original research process.

The original research process asks:

- which mechanism or feature can create alpha?
- can a candidate pass admission / residual / integration gates?
- should the strategy be promoted?

This validation asks a narrower black-box question:

- given the already produced fixed-set OOS return stream, does the baseline's
  observed edge survive distributional, temporal, and paired-path stress?

The target baseline is:

- `v5_rw_bridge_no_overlay_h10d`

The reference artifact is:

- `artifacts/quant_research/factor_reports/2026-05-02-v5-rw-no-overlay-fixed-set-alpha_ontology_h10d_fixed_set_comparison/aligned_period_returns.csv`

The executable validator is:

- `scripts/quant_research/validate_baseline_alpha_confidence.py`

---

## Validator Logic

The validator intentionally does not inspect factor mechanisms or feature
admission results. It consumes only aligned OOS period returns.

It checks:

1. Standalone edge quality:
   - positive OOS return sum
   - positive period win fraction
   - positive first-half and second-half returns
   - positive return after dropping the best three periods
   - positive concentration diagnostics

2. Paired path stress:
   - baseline minus each comparator has positive total return difference
   - paired edge survives first-half and second-half splits
   - paired edge survives dropping the best three delta periods
   - paired sign-test p-values are reported as diagnostics, not used as the
     only gate

3. Warning flags:
   - return stream too dependent on the largest positive periods
   - annual paired slices with non-positive edge when the year has enough
     observations to be meaningful

The current comparator set is:

- `lsk3_g_v2_h10d`
- `v5_h10d`
- `v6_h10d`
- `v5_rw_bridge_h10d`

---

## Current Readout

Command:

```powershell
python scripts\quant_research\validate_baseline_alpha_confidence.py --output-dir artifacts\quant_research\factor_reports\2026-05-03-baseline-alpha-confidence-validation
```

Output artifacts:

- `artifacts/quant_research/factor_reports/2026-05-03-baseline-alpha-confidence-validation/baseline_alpha_confidence_validation.json`
- `artifacts/quant_research/factor_reports/2026-05-03-baseline-alpha-confidence-validation/baseline_alpha_confidence_validation.md`

Headline result:

- confidence label: `high`
- checks passed: `6/6`
- primary warning: `standalone_return_is_materially_concentrated_in_top_10_positive_periods`

Important numbers:

| Diagnostic | Value |
| --- | ---: |
| OOS periods | 64 |
| OOS window | 2023-09-02 to 2026-03-30 |
| Baseline sum of period returns | 1.095707 |
| Baseline period win fraction | 0.688 |
| First-half sum | 0.586685 |
| Second-half sum | 0.509023 |
| Sum after dropping best 3 periods | 0.802034 |
| Top 10 positive periods / total sum | 0.717 |

Paired edge summary:

| Comparator | Sum diff | Win fraction | First-half diff | Second-half diff | Without best 3 diff | Sign p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lsk3_g_v2_h10d` | 0.538643 | 0.641 | 0.299031 | 0.239612 | 0.392829 | 0.0328 |
| `v5_h10d` | 0.394541 | 0.625 | 0.156718 | 0.237823 | 0.236931 | 0.0599 |
| `v6_h10d` | 0.541333 | 0.641 | 0.299031 | 0.242302 | 0.395520 | 0.0328 |
| `v5_rw_bridge_h10d` | 0.373363 | 0.656 | 0.120584 | 0.252778 | 0.253243 | 0.0169 |

---

## Interpretation

The current baseline alpha confidence is high by black-box path evidence, not
because a new research story was accepted.

The positive case:

- The standalone return stream is not a one-half artifact. Both 32-period
  halves are positive with identical 0.688 win fraction.
- The edge beats every fixed-set comparator in total paired return difference.
- The paired edge remains positive after dropping the best three delta periods.
- The no-overlay baseline beats the overlay sibling, which supports the recent
  conclusion that broad overlays are not the current alpha source.

The caution:

- The standalone return stream is meaningfully concentrated: the top 10
  positive periods explain 71.7% of the total period-return sum.
- 2023 and 2026 are short slices, so annual confidence is mostly carried by
  2024 and 2025.
- This diagnostic validates the existing return path; it does not prove that
  the economic mechanism will remain stable under a new market regime.

Working conclusion:

- Treat `v5_rw_bridge_no_overlay_h10d` as the current high-confidence h10d
  baseline parent.
- Do not promote adjacent overlays or SP-K-style modifications unless they beat
  this baseline in the same fixed-set paired-path validator.
- Next confidence upgrade should come from a falsification runner that adds
  placebo calendars, delayed labels, and cost stress, not from another mechanism
  essay.

---

## Next Validation Gates

The next empirical gates should be added in this order:

1. Calendar placebo:
   - rotate or shift OOS period labels while preserving return distribution
   - reject confidence if the real path is not in the upper tail versus placebo

2. Cost stress:
   - rerun the fixed-set comparison at higher execution cost assumptions
   - require paired edge to stay positive against `v5_rw_bridge_h10d` and
     `v6_h10d`

3. Regime stress:
   - bind each OOS period to market regime labels
   - require no single regime to explain the majority of the paired edge

4. Frozen-parent upgrade rule:
   - every new candidate must report this validator against
     `v5_rw_bridge_no_overlay_h10d`
   - candidates with positive full-OOS return but weaker paired path confidence
     remain research-only
