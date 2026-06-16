# M3.3 Event-State Feature Stage 0

`Snapshot date: 2026-05-03`
`Status: Stage 0 complete; feature seed only, not manifest-ready`

## Research Question

After direct SP-K news/hype vetoes failed to produce a promotable result, this
test moves M3.3 one layer upstream.

Question:

Can the event tape become a parent-independent state feature on the canonical
`v5_rw_bridge_no_overlay_h10d` short boundary?

This avoids relying on SP-K's quarantined replacement manifest. It tests event
state directly against the canonical parent short book and parent bottom-8
boundary.

## Implementation

New script:

[`evaluate_m3_3_event_state_feature_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_event_state_feature_stage0.py:1)

Run command:

```powershell
python scripts\quant_research\evaluate_m3_3_event_state_feature_stage0.py --as-of 2026-05-03 --target-horizon-bars 10 --event-lookback-days 10
```

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-event-state-feature-stage0/m3_3_event_state_feature_stage0.json`

Row artifacts:

- `event_quality_boundary_selected_rows.csv`
- `event_quality_boundary_entered_vs_parent.csv`
- `event_quality_boundary_exited_vs_parent.csv`

## Features

| feature | definition | intended sign |
| --- | --- | --- |
| `m3_3_event_state_hype_pressure_v1` | recent hype count | negative for short quality |
| `m3_3_event_state_confirmed_quality_v1` | confirmed + real repricing + short-veto event counts | positive for short quality |
| `m3_3_event_state_short_quality_v1` | confirmed/real/short-veto mix plus link/magnitude, minus hype | positive for short quality |
| `m3_3_event_state_noise_ratio_v1` | hype / actionable event count | negative for short quality |

For feature IC, target is short payoff: `-forward_10d_log_return`.

## Feature Evidence

| feature | all-core rank IC | positive rate | parent bottom-8 rank IC | positive rate |
| --- | ---: | ---: | ---: | ---: |
| `hype_pressure_v1` | -0.0766 | 35.27% | -0.0541 | 43.16% |
| `confirmed_quality_v1` | -0.0595 | 38.90% | -0.0509 | 43.88% |
| `noise_ratio_v1` | -0.0726 | 36.83% | -0.0725 | 43.54% |
| `short_quality_v1` | +0.0542 | 62.45% | +0.0251 | 53.35% |

The composite feature has the right sign and is directionally stable. The
individual raw components are not enough on their own.

## Boundary Selection Result

For short baskets, more negative forward return is better.

| basket | hype active | mean event quality | h10d mean | h10d negative fraction | next-1d squeeze >5% |
| --- | ---: | ---: | ---: | ---: | ---: |
| parent short book | 36.69% | -0.948 | -0.167% | 53.43% | 11.81% |
| event-quality bottom-8 selected | 19.18% | +0.960 | -0.203% | 53.40% | 11.48% |
| +1d delayed event-quality selected | 19.46% | +0.969 | -0.271% | 53.34% | 11.39% |

The event-quality selector reduces hype exposure and improves mean h10d return,
but the base improvement is small: about `-0.036%` versus parent shorts. The
delayed version looks better at `-0.103%`, but that is still diagnostic rather
than admission evidence.

## Replacement Diagnostics

Against parent shorts, event-quality boundary selection changes about `1,277`
short rows.

| changed rows | hype active | mean event quality | h10d mean | next-1d squeeze >5% |
| --- | ---: | ---: | ---: | ---: |
| entered | 30.62% | +1.397 | +0.055% | 10.96% |
| exited | 75.57% | -3.501 | +0.145% | 11.82% |
| entered - exited | -44.95% | +4.897 | -0.090% | -0.86 pp |

Changed rows improve relative to exited rows, but both sides still have positive
h10d returns. That is not enough for a tradeable short-boundary rule.

## Decision

Do not create a manifest candidate yet.

Current read:

- `m3_3_event_state_short_quality_v1`: keep as feature seed.
- direct event-quality boundary replacement: watch only.
- direct SP-K news/hype veto: no further implementation.

## Next Step

The next useful M3.3 slice should be a stricter state feature, not a broader
gate:

- require positive `short_quality_v1` and low `noise_ratio_v1`,
- restrict to parent bottom-8 / bottom-10 boundary only,
- add symbol-holdout and +1d delay as hard gates,
- only promote if changed entered rows become negative-return shorts, not merely
  "less bad" than exited rows.

Pre-registered failure condition:

If the stricter feature still cannot make entered rows negative on h10d, M3.3
should remain a diagnostics / forensics layer until richer event coverage or
social-history features exist.

## Strict Follow-up

The stricter selector pass has now run:

[`m3_3_strict_event_state_stage0.md`](m3_3_strict_event_state_stage0.md)

Result: `strict_q1_noise0` clears the previous failure condition. Entered rows
average `-2.18%` over h10d and beat exited rows by about `-1.90%`; the +1d
delay rerun remains directionally positive. This is now strong enough for a
formal manifest A/B scaffold, still not production promotion.
