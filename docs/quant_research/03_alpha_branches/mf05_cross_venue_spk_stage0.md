# MF-05 Cross-Venue SP-K Stage 0

`Snapshot date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Artifact: artifacts/quant_research/factor_reports/2026-05-03-mf05-cross-venue-spk-stage0/mf05_cross_venue_spk_stage0.json`

## Question

The direct MF-05 boundary test failed, but the roadmap still allowed one
plausible re-open path: use cross-venue stress only inside the `SP-K`
post-pump short-replacement problem.

This Stage 0 asks whether 1d cross-venue dispersion / Binance premium can
distinguish:

- venue-local pump candidates that should be shorted; from
- broad repricing candidates that should not be shorted.

## Method

The script merges `cross_venue_panel_1d.csv` into the canonical parent risk
frame, computes q90 flags for:

- `cross_venue_spot_dispersion`;
- absolute `cross_venue_spot_binance_premium`;
- either signal active.

It then rewires the SP-K replacement scorer through `candidate_veto_column`:

- `spk_confirm_*`: allow SP-K replacement only when the cross-venue signal is
  high;
- `spk_veto_*`: block SP-K replacement when the cross-venue signal is high.

The benchmark is raw SP-K on the canonical parent. For selected shorts, more
negative future return is better.

## Result

Input coverage is the same as the direct MF-05 boundary test:

- frame rows: `18,576`
- timestamps: `1,093`
- cross-venue row coverage: `54.4%`
- q90 dispersion threshold: `0.0010695`
- q90 absolute Binance premium threshold: `0.0008726`

| variant | changed vs raw SP-K | edge vs raw SP-K | entered vs exited edge | verdict vs raw SP-K |
| --- | ---: | ---: | ---: | --- |
| `spk_confirm_high_dispersion` | `51.97%` | `-0.001209` | `-0.006987` | `stage0_negative` |
| `spk_confirm_high_abs_premium` | `51.78%` | `-0.001279` | `-0.007420` | `stage0_negative` |
| `spk_confirm_any_cross_venue_stress` | `51.78%` | `-0.001279` | `-0.007420` | `stage0_negative` |
| `spk_veto_high_dispersion` | `0.27%` | `-0.000067` | `-0.072836` | `stage0_at_par` |
| `spk_veto_high_abs_premium` | `0.46%` | `+0.000003` | `+0.002006` | `stage0_at_par` |
| `spk_veto_any_cross_venue_stress` | `0.46%` | `+0.000003` | `+0.002006` | `stage0_at_par` |

Raw SP-K still improves the canonical parent short basket:

- parent short h10d mean: `-0.001673`
- raw SP-K short h10d mean: `-0.002781`
- raw SP-K edge versus parent: `+0.001108`

But cross-venue confirmation removes that lift. Confirmed variants revert
toward the parent basket (`~ -0.00150` to `-0.00157`) and are materially worse
than raw SP-K. Veto variants barely change raw SP-K, with only `3-5` changed
timestamps.

## Decision

Do not open a canonical manifest A/B for event-conditioned MF-05 + SP-K.

This closes the current 1d cross-venue route:

- direct MF-05 boundary rules have enough transmission but wrong direction;
- SP-K-conditioned confirmation has large transmission but worsens raw SP-K;
- SP-K-conditioned veto is too sparse to matter.

## Next

MF-05 should stay data-ready but inactive for alpha promotion. Re-open only with
new information content, not another q90 flag on the same 1d close-price panel:

- sub-day venue dislocation around the pump window;
- venue volume-share migration;
- explicit venue-local listing / liquidity-gap states.
