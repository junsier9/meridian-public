# MF-05 Cross-Venue Boundary Stage 0

`Snapshot date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Artifact: artifacts/quant_research/factor_reports/2026-05-03-mf05-cross-venue-boundary-stage0/mf05_cross_venue_boundary_stage0.json`

## Question

Can the existing per-asset cross-venue spot panel help the current canonical
parent distinguish broad repricing from venue-local squeeze behavior at the
short boundary?

This test intentionally does not re-run the old `cross_venue_spot_dispersion`
score-factor admission question. That path already failed G6 / score
integration. The new question is selection-layer only:

- if high cross-venue dispersion means broad repricing, veto those shorts;
- if high cross-venue dispersion means inventory stress / venue-local
  dislocation, prefer those shorts.

## Method

The script merges `cross_venue_panel_1d.csv` into the canonical parent risk
frame and tests four one-replacement short-boundary rules:

- `veto_high_dispersion_q90`
- `select_high_dispersion_q90`
- `veto_abs_binance_premium_q90`
- `select_abs_binance_premium_q90`

All rules require at least `3` venue observations and use the in-sample q90
threshold as a Stage 0 diagnostic threshold. For selected shorts, more negative
future return is better.

## Result

Coverage is adequate for a Stage 0 boundary test:

- frame rows: `18,576`
- timestamps: `1,093`
- cross-venue row coverage: `54.4%`

| variant | changed timestamps | selected-short edge vs parent | entered h10d mean | exited h10d mean | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `select_high_dispersion_q90` | `24.9%` | `-0.001324` | `+0.004714` | `-0.011280` | `stage0_negative` |
| `select_abs_binance_premium_q90` | `24.1%` | `-0.000971` | `-0.001235` | `-0.013372` | `stage0_negative` |
| `veto_high_dispersion_q90` | `18.2%` | `-0.000592` | `+0.008718` | `-0.001219` | `stage0_negative` |
| `veto_abs_binance_premium_q90` | `17.7%` | `-0.000413` | `-0.009062` | `-0.013485` | `stage0_at_par` |

## Decision

Do not open a canonical manifest A/B for the current MF-05 boundary shapes.

Unlike M3.2, MF-05 has enough boundary transmission to matter, but the direction
is wrong. Selecting high-dispersion or high-premium shorts replaces better
shorts with weaker shorts. Vetoing them does not solve it either: the best veto
variant is only at-par and still has negative edge versus the parent.

## Next

MF-05 should remain a data lane, but the current 1d spot-dispersion / Binance
premium signals are not a viable canonical short-boundary rule. Re-open only
with a more specific event-conditioned definition, such as:

- cross-venue confirmation applied only to post-pump candidates;
- sub-day venue dispersion around the pump window;
- venue-volume migration rather than close-price dispersion.
