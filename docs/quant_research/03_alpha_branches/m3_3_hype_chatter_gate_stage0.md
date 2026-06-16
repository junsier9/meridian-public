# M3.3 Hype Chatter Gate Stage 0

`Snapshot date: 2026-05-03`
`Status: Stage 0 complete; watch only, not promotable`

## Research Question

The first M3.3 event-tape diagnostic found that `hype`-tagged SP-K entered
shorts were weaker than unflagged entered shorts. This follow-up asks whether
that observation survives conversion into an actual selection-layer gate.

Because the current SP-K canonical-parent challenger is quarantined, this is
diagnostic-only evidence. It does not create, enable, or promote a new canonical
manifest.

## Implementation

New script:

[`evaluate_m3_3_hype_chatter_gate_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_hype_chatter_gate_stage0.py:1)

Run command:

```powershell
python scripts\quant_research\evaluate_m3_3_hype_chatter_gate_stage0.py --as-of 2026-05-03 --target-horizon-bars 10 --event-lookback-days 10 --shuffle-count 0
```

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-hype-chatter-gate-stage0/m3_3_hype_chatter_gate_stage0.json`

Row artifacts:

- `hype_candidate_veto_entered_vs_spk.csv`
- `hype_candidate_veto_exited_vs_spk.csv`

## Variants

| variant | meaning |
| --- | --- |
| `parent_v5` | canonical `v5_rw_bridge_no_overlay_h10d` parent |
| `spk_no_news` | current research-only SP-K short replacement on the canonical parent |
| `spk_hype_candidate_veto` | block hype-tagged names from entering via SP-K replacement |
| `spk_hype_candidate_plus_selected_veto` | also eject already-selected hype-tagged shorts and refill from the tail |

## Main Result

For short baskets, more negative forward return is better.

| basket | hype fraction | h10d mean | h10d negative fraction | next-1d squeeze >5% |
| --- | ---: | ---: | ---: | ---: |
| parent v5 | 36.69% | -0.167% | 53.43% | 11.81% |
| SP-K no news | 33.18% | -0.278% | 54.05% | 11.42% |
| hype candidate veto | 31.47% | -0.193% | 53.80% | 11.57% |
| hype candidate + selected veto | 24.73% | -0.292% | 53.92% | 11.51% |

## Replacement Diagnostics

### Candidate Veto Only

This version is a clean reject.

- It exits 114 hype-tagged SP-K rows averaging `+0.171%` h10d.
- But the rows it enters average `+2.599%` h10d.
- Basket h10d mean worsens from `-0.278%` to `-0.193%`.
- Next-day squeeze rate also worsens from `11.42%` to `11.57%`.

The simple interpretation: blocking hype candidates leaves or inserts worse
shorts than the hype rows it removes.

### Candidate + Selected Veto

This version is better, but too weak to promote.

- Basket h10d mean improves only from `-0.278%` to `-0.292%`.
- Hype exposure falls materially from `33.18%` to `24.73%`.
- Changed rows are directionally better: entered `-0.306%` h10d versus exited
  `-0.173%`.
- But h10d negative fraction falls slightly and next-day squeeze rate rises
  slightly.

The effect survives the +1d delayed event-tape rerun directionally, where basket
h10d mean improves from `-0.278%` to `-0.365%`, but that delayed result is still
diagnostic rather than admission evidence.

## Decision

Do not promote `hype_chatter_decay_gate` yet.

Current read:

- `hype_candidate_veto`: reject.
- `hype_candidate_plus_selected_veto`: watch only.
- M3.3 remains useful as a diagnostic layer, but this gate is not strong enough
  to overcome the current SP-K quarantine.

## Next Step

Do not spend the next implementation slot on another direct SP-K news veto.

The better M3.3 continuation is to move one level upstream:

- use event tape to classify parent/SP-K short-boundary states,
- search for a parent-independent event-state feature,
- require symbol-holdout and +1d delay before any manifest candidate,
- only then revisit a full A/B cycle.

Failure condition:

If the next event-state feature cannot beat simple SP-K no-news replacement in
fixed-set short-basket diagnostics, M3.3 should remain a reporting/forensics
layer rather than a strategy gate.

## Follow-up

The parent-independent event-state feature test has now run:

[`m3_3_event_state_feature_stage0.md`](m3_3_event_state_feature_stage0.md)

Result: the composite `m3_3_event_state_short_quality_v1` has the right IC sign
and improves parent-boundary selected shorts slightly, but changed entered rows
are still positive-return shorts. Keep it as a feature seed only; do not create
a manifest candidate yet.
