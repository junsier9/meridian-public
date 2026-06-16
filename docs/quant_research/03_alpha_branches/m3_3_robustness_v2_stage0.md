# M3.3 Robustness V2 Stage 0

`Snapshot date: 2026-05-04`
`Status: diagnostic complete; no manifest A/B promotion`

## Research Question

M3.3 strict event-state v1 passed validation and fixed-set paired comparison, but
failed statistical falsification on time shuffle, label shuffle, symbol holdout,
and liquidity-bucket consistency. This v2 pass asks whether a narrower event
rule can keep the useful short-boundary lift while reducing those robustness
failures.

## Implementation

New diagnostic script:

[`evaluate_m3_3_robustness_v2_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_robustness_v2_stage0.py:1)

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-robustness-v2-stage0/m3_3_robustness_v2_stage0.json`

The script supports per-variant runs via `--variant-label` and writes
checkpoint artifacts so long diagnostics do not lose completed variants.

## Variants

| variant | intent |
| --- | --- |
| `v1_strict_q1_noise0` | prior lead rule, used as the local comparator |
| `v2_q15_noise0` | higher event-quality threshold |
| `v2_q2_noise0` | strictest event-quality threshold |
| `v2_q1_noise0_one_replacement` | cap replacement count at one per timestamp |
| `v2_q15_top_liquidity_only` | test whether the only working bucket should be isolated |
| `diagnostic_q1_without_avax_uni` | diagnostic upper bound only; not a valid production rule |

The shuffle proxies in this merged diagnostic were run with one iteration per
variant to complete the matrix after the full proxy scan proved too slow. Treat
shuffle pass/fail as triage, not final promotion evidence.

## Result

| variant | Stage0 pass | edge vs parent mean return | entered h10d mean | entered - exited | holdout flips | positive liquidity buckets |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| `v2_q2_noise0` | yes | `+0.052%` | `-1.77%` | `-0.72%` | `AVAX` | 1 |
| `v1_strict_q1_noise0` | no | `+0.049%` | `-2.26%` | `-0.61%` | `AVAX` | 1 |
| `v2_q15_noise0` | no | `+0.043%` | `-1.79%` | `-0.56%` | `AVAX` | 1 |
| `v2_q1_noise0_one_replacement` | no | `+0.027%` | `-1.99%` | `-0.37%` | `AVAX` | 1 |
| `diagnostic_q1_without_avax_uni` | no | `+0.013%` | `-2.27%` | `-0.22%` | `AVAX`, `DOT`, `XRP` | 1 |
| `v2_q15_top_liquidity_only` | no | `+0.010%` | `-0.91%` | `-0.21%` | `AVAX`, `NEAR` | 1 |

## Interpretation

`v2_q2_noise0` is the cleanest rule in the local search: raising quality to `2.0`
preserves a small positive parent-edge and keeps entered rows negative. But it
does not solve the real blockers. The edge still concentrates in one liquidity
bucket, and AVAX remains the recurring holdout failure.

The diagnostic `without_avax_uni` result is especially useful because it does
not improve robustness. Removing the known bad symbols simply moves the holdout
problem elsewhere. That argues against symbol blacklist overfitting.

## Decision

Do **not** open a formal manifest A/B for v2.

M3.3 should stay as quarantined research evidence. The next useful event-tape
work should change the information source or state definition, not merely tune
thresholds:

- add event-source persistence / multi-source confirmation,
- separate official repricing from repeated narrative chatter,
- require cross-day event continuation before replacement,
- or combine event state with a non-news mechanical confirmation layer such as
  MF-01 orderbook fragility.

That MF-01 confirmation branch has now been tested:
[`m3_3_mf01_confirmation_stage0.md`](m3_3_mf01_confirmation_stage0.md). It
improves row quality but is too sparse for portfolio transmission, so it should
not be promoted to manifest A/B.
