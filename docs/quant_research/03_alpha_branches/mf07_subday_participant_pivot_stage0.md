# MF-07 Sub-Day Participant Pivot Stage 0

`Snapshot date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Artifact: artifacts/quant_research/factor_reports/2026-05-03-mf07-subday-participant-pivot-stage0/mf07_subday_participant_pivot_stage0.json`

## Question

Daily MF-07 participant disagreement failed both as a broad factor and as an
SP-K confirmation layer. The remaining plausible hypothesis was that the daily
panel destroys timing information: top traders may fade, lead, or refuse a
global-account chase inside the 1h window before the daily selection point.

This Stage 0 asks whether raw 1h participant movement can improve SP-K
short-boundary replacement on the canonical parent.

## Method

For each canonical parent subject/date, the script reads the local raw
`coinglass_extended/*USDT/1h/*.csv.gz` cache and computes prior-window
participant pivots using only bars before the daily timestamp:

- `top_trader_long_pct` delta over `6h` and `24h`;
- `global_account_long_pct` delta over `6h` and `24h`;
- global-minus-top `24h` delta as a retail-chase / top-fade proxy;
- top-minus-global `24h` delta as a top-trader-leads proxy.

It then evaluates SP-K with `candidate_veto_column`:

- `spk_confirm_*`: allow SP-K replacement only when the sub-day pivot is active;
- `spk_veto_*`: block SP-K replacement when the sub-day pivot is active.

The benchmark is raw SP-K on `v5_rw_bridge_no_overlay_h10d`. For selected
shorts, more negative future return is better.

## Result

Input coverage:

- selected frame rows: `18,576`
- timestamps: `1,093`
- subjects loaded from raw 1h cache: `17 / 17`
- 24h participant-pivot coverage: `65.16%`
- `global_delta_24h_q75`: `1.5200`
- `top_delta_24h_q25`: `-1.0400`
- `retail_minus_top_delta_24h_q90`: `4.0800`
- `top_minus_retail_delta_24h_q90`: `3.9970`

Raw SP-K still improves the canonical parent short basket:

- parent short h10d mean: `-0.001673`
- raw SP-K short h10d mean: `-0.002781`
- raw SP-K edge versus parent: `+0.001108`

Sub-day MF-07 does not improve raw SP-K:

| variant | changed vs raw SP-K | edge vs raw SP-K | entered vs exited edge | verdict vs raw SP-K |
| --- | ---: | ---: | ---: | --- |
| `spk_confirm_retail_chase_top_fade` | `49.95%` | `-0.001109` | `-0.006670` | `stage0_negative` |
| `spk_confirm_retail_outpaces_top` | `49.22%` | `-0.001197` | `-0.007311` | `stage0_negative` |
| `spk_confirm_fast_retail_chase_top_fade` | `49.41%` | `-0.000895` | `-0.005444` | `stage0_negative` |
| `spk_confirm_top_leads_retail` | `50.59%` | `-0.000990` | `-0.005867` | `stage0_negative` |
| `spk_confirm_any_retail_pivot` | `46.39%` | `-0.001083` | `-0.007023` | `stage0_negative` |
| `spk_veto_retail_chase_top_fade` | `2.29%` | `+0.000002` | `+0.000256` | `stage0_at_par` |
| `spk_veto_retail_outpaces_top` | `3.02%` | `+0.000144` | `+0.014140` | `stage0_at_par` |
| `spk_veto_fast_retail_chase_top_fade` | `2.84%` | `-0.000195` | `-0.020471` | `stage0_at_par` |
| `spk_veto_top_leads_retail` | `1.65%` | `-0.000079` | `-0.015101` | `stage0_at_par` |
| `spk_veto_any_retail_pivot` | `5.86%` | `-0.000199` | `-0.010093` | `stage0_at_par` |

The confirmation variants transmit, but they transmit in the wrong direction:
they change roughly half of raw SP-K timestamps and worsen the short basket by
about `9-12 bps`.

The veto variants are not promotable either. The only positive edge,
`spk_veto_retail_outpaces_top`, improves raw SP-K by only `+0.000144` and
changes just `3.02%` of timestamps.

## Decision

Do not open a canonical manifest A/B for sub-day MF-07 participant pivots.

This closes the current MF-07 promotion route:

- broad daily MF-07 failed;
- SP-K-conditioned daily MF-07 failed;
- raw 1h participant-pivot MF-07 still fails as an SP-K confirmation layer and
  is too sparse as a veto.

## Next

MF-07 should remain research-only until there is a materially different
participant-state definition. The next executable alpha search should not spend
another slot on top-trader/global-account daily or 1h threshold flags.

Priority should move to a different information source or landing shape:

- discrete M3.2 on-chain / stablecoin boundary activation;
- options-surface / dealer-gamma once enough snapshots or paid history exist;
- sub-day venue stress only if raw venue-local state data is available.
