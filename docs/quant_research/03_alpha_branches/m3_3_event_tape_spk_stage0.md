# M3.3 Event Tape SP-K Stage 0

`Snapshot date: 2026-05-03`
`Status: Stage 0 complete; do not promote replacement/veto yet`

## Research Question

Can the adjudicated crypto-news event tape explain SP-K short false positives on
the canonical `v5_rw_bridge_no_overlay_h10d` parent?

The first landing shape is intentionally narrow:

- build symbol-day event flags from the existing adjudicated news corpus,
- attach them to canonical daily features with a PIT-safe effective date,
- inspect SP-K `replace_mid_v1` selected shorts and entered replacement shorts,
- decide whether event tape should become a short veto, exposure gate, or a
  separate diagnostic lane.

## Inputs

- Feature panel:
  `artifacts/quant_research/features/2026-05-03-cross-sectional-daily-1d-features-v1/features.csv.gz`
- News panel:
  `artifacts/quant_research/datasets/2026-05-01-crypto-news-dataset/llm_structured_scores_adjudicated_priority_ge_8.parquet`
- Canonical parent:
  `xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`
- SP-K challenger:
  `xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d`

## Implementation

New script:

[`evaluate_m3_3_event_tape_spk_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_event_tape_spk_stage0.py:1)

Run command:

```powershell
python scripts\quant_research\evaluate_m3_3_event_tape_spk_stage0.py --as-of 2026-05-03 --target-horizon-bars 10 --event-lookback-days 10 --shuffle-count 200
```

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-event-tape-spk-stage0/m3_3_event_tape_spk_stage0.json`

Row artifacts:

- `m3_3_event_tape_symbol_day.csv.gz`
- `spk_selected_short_event_rows.csv`
- `spk_entered_short_event_rows.csv`

## Coverage

| item | value |
| --- | ---: |
| risk-frame rows | 18,576 |
| risk-frame subjects | 17 |
| risk-frame date range | 2023-04-24 to 2026-04-20 |
| news rows | 26,462 |
| news effective range | 2021-01-02 to 2025-12-03 |
| event-tape symbol-day rows | 60,774 |
| event-tape subjects | 383 |
| SP-K selected short rows | 3,279 |
| SP-K entered replacement short rows | 571 |
| SP-K entered replacement subjects | 3 |

## Results

For short rows, more negative forward return is better.

| slice | flagged rows | flagged h10d mean | unflagged h10d mean | flagged - unflagged | flagged 1d squeeze >5% | unflagged 1d squeeze >5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| selected shorts, confirmed short-veto event | 535 / 3,279 | -0.653% | -0.204% | -0.449% | 10.84% | 11.53% |
| entered SP-K shorts, confirmed short-veto event | 48 / 571 | -5.020% | -0.524% | -4.496% | 6.25% | 8.80% |
| entered SP-K shorts, short-veto event | 51 / 571 | -4.214% | -0.578% | -3.636% | 7.84% | 8.65% |
| entered SP-K shorts, real-repricing event | 52 / 571 | -4.395% | -0.553% | -3.843% | 9.62% | 8.48% |
| entered SP-K shorts, hype event | 114 / 571 | +0.171% | -1.179% | +1.350% | 11.40% | 7.88% |
| exited parent shorts, confirmed short-veto event | 90 / 571 | +1.453% | -0.595% | +2.048% | 7.78% | 11.43% |

## Interpretation

The naive prior was wrong: `confirmed` or `real_repricing` event flags are not
currently the SP-K entered-short false-positive bucket. On the canonical
v5 parent, event-confirmed SP-K entered shorts were materially better shorts
than unflagged entered shorts.

The weaker bucket is `hype`: entered shorts with recent hype tags average
`+0.171%` over the next 10 days versus `-1.179%` for unflagged entered shorts,
and their next-day `>5%` squeeze rate is higher. That is the first useful M3.3
separator from this run.

There is also an asymmetry worth preserving: event-confirmed names that the
parent shorted and SP-K exited were bad shorts (`+1.453%` next 10 days). This
means event tape may help explain why SP-K ejects some parent shorts, but it
does not justify ejecting SP-K's own event-confirmed entered shorts.

## Stage 0 Decision

M3.3 is mechanically live and worth continuing, but not as a broad
`official-event short veto`.

Current decision:

- `confirmed_event_do_not_short`: reject for SP-K entered shorts.
- `real_repricing_short_veto`: reject for SP-K entered shorts.
- `hype_chatter_decay_gate`: promote to next Stage 0 slice.
- `event_explains_parent_exits`: keep as diagnostic, not a trade rule yet.

## Next Slice

Build a narrow `M3.3-hype` challenger:

- apply only on SP-K entered replacement shorts,
- penalize or skip names with recent `final_repricing_type = hype`,
- require no change to the long book,
- compare against canonical parent and SP-K no-news with fixed-set paired
  replacement diagnostics,
- run symbol shuffle, +1d delay, and cost stress before any promotion.

Failure criterion for the next slice:

- if hype gating reduces short count but does not improve h10d short returns,
  or if the effect disappears under symbol shuffle / +1d delay, keep event tape
  as diagnostic only.

## 2026-05-03 Follow-up

The hype-gate follow-up has now run:

[`m3_3_hype_chatter_gate_stage0.md`](m3_3_hype_chatter_gate_stage0.md)

Result: the simple `hype_candidate_veto` is rejected. It removes hype-tagged
SP-K rows, but the replacement rows are worse. The broader
`candidate_plus_selected_veto` is only watch-worthy: it slightly improves basket
h10d mean, but the lift is too small and the changed-row risk profile is not
clean enough to overcome SP-K's current canonical-parent quarantine.
