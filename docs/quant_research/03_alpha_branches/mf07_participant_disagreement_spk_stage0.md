# MF-07 Participant Disagreement SP-K Stage 0

`Snapshot date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Artifact: artifacts/quant_research/factor_reports/2026-05-03-mf07-participant-disagreement-spk-stage0/mf07_participant_disagreement_spk_stage0.json`

## Question

Plain MF-07 participant-disagreement factors previously failed as daily
aggregate score candidates. The remaining plausible re-open path was to use
participant stress only inside the `SP-K` post-pump short-replacement problem.

This Stage 0 asks whether top-trader versus global-account disagreement can
distinguish:

- crowded / fragile pump candidates that should be shorted; from
- pump candidates where SP-K replacement should be blocked.

## Method

The script evaluates MF-07 flags inside the canonical parent risk frame:

- low 1h top-trader/global-account rolling correlation, q10;
- high absolute top-trader versus global long-percent gap, q90;
- high absolute top-trader 1h velocity, q90;
- any of the above participant-stress flags.

It then rewires the SP-K replacement scorer through `candidate_veto_column`:

- `spk_confirm_*`: allow SP-K replacement only when the MF-07 stress flag is
  active;
- `spk_veto_*`: block SP-K replacement when the MF-07 stress flag is active.

The benchmark is raw SP-K on the canonical parent. For selected shorts, more
negative future return is better.

## Result

Input coverage:

- selected-short rows: `3,279`
- timestamps: `1,093`
- absolute top-trader/global gap coverage: `99.63%`
- top/global correlation coverage: `53.21%`
- top-trader velocity coverage: `53.81%`
- q10 top/global correlation threshold: `-0.46798`
- q90 absolute top-trader/global gap threshold: `21.4998`
- q90 top-trader velocity threshold: `1.23979`
- any participant-stress flag fraction: `19.63%`

Raw SP-K still improves the canonical parent short basket:

- parent short h10d mean: `-0.001673`
- raw SP-K short h10d mean: `-0.002781`
- raw SP-K edge versus parent: `+0.001108`

MF-07 does not improve raw SP-K:

| variant | changed vs raw SP-K | edge vs raw SP-K | entered vs exited edge | verdict vs raw SP-K |
| --- | ---: | ---: | ---: | --- |
| `spk_confirm_any_mf07_stress` | `45.38%` | `-0.001160` | `-0.007662` | `stage0_negative` |
| `spk_confirm_high_abs_tt_retail_gap` | `45.65%` | `-0.000789` | `-0.005180` | `stage0_negative` |
| `spk_confirm_high_tt_velocity` | `51.97%` | `-0.001479` | `-0.008550` | `stage0_negative` |
| `spk_confirm_low_top_global_corr` | `52.06%` | `-0.001106` | `-0.006383` | `stage0_negative` |
| `spk_veto_any_mf07_stress` | `6.86%` | `+0.000047` | `+0.002113` | `stage0_at_par` |
| `spk_veto_high_abs_tt_retail_gap` | `6.59%` | `-0.000252` | `-0.011682` | `stage0_at_par` |
| `spk_veto_high_tt_velocity` | `0.27%` | `+0.000299` | `+0.323997` | `stage0_at_par` |
| `spk_veto_low_top_global_corr` | `0.18%` | `-0.000012` | `-0.018792` | `stage0_at_par` |

The confirmation variants transmit strongly, but in the wrong direction: they
change about `45-52%` of raw SP-K timestamps and worsen the SP-K short basket
by roughly `8-15 bps`.

The veto variants do not clear the bar either. The only non-tiny positive
variant, `spk_veto_any_mf07_stress`, improves raw SP-K by only `+0.000047`
while changing `6.86%` of timestamps. The top-trader-velocity veto has a larger
reported edge, but it changes only `3` timestamps and is not usable evidence.

## Decision

Do not open a canonical manifest A/B for event-conditioned MF-07 + SP-K.

This closes the current MF-07 route:

- plain daily aggregate MF-07 failed earlier admission / score use;
- SP-K-conditioned confirmation has large transmission but worsens raw SP-K;
- SP-K-conditioned veto is either at-par or too sparse.

## Next

MF-07 should remain inactive for alpha promotion on the current daily panel.
Re-open only if the feature definition changes materially, for example:

- sub-day participant pivot timing around the pump window;
- lead-lag between top-trader movement and global-account catch-up;
- event-state interaction where participant disagreement is measured as a
  transition, not a daily level.
