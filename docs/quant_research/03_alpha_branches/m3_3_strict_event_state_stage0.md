# M3.3 Strict Event-State Stage 0

`Snapshot date: 2026-05-03`
`Status: Stage 0 pass for strict selector; quarantined A/B scaffold validation and fixed-set passed; statistical falsification no-go`

## Research Question

The prior parent-independent event-state test showed a weak but correctly signed
feature seed. This stricter pass asks whether a high-quality, low-noise event
state can produce genuinely negative-return entered shorts inside the canonical
`v5_rw_bridge_no_overlay_h10d` parent boundary.

This is still Stage 0. It does not promote a strategy, but it was strong enough
to justify a formal manifest A/B scaffold.

## Implementation

New script:

[`evaluate_m3_3_strict_event_state_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_strict_event_state_stage0.py:1)

Run command:

```powershell
python scripts\quant_research\evaluate_m3_3_strict_event_state_stage0.py --as-of 2026-05-03 --target-horizon-bars 10 --event-lookback-days 10
```

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-strict-event-state-stage0/m3_3_strict_event_state_stage0.json`

## Variants

| variant | rule |
| --- | --- |
| `strict_q1_noise0` | `short_quality >= 1.0`, `noise_ratio == 0`, no hype |
| `strict_q05_noise0` | `short_quality >= 0.5`, `noise_ratio == 0`, no hype |
| `strict_q1_noise05` | `short_quality >= 1.0`, `noise_ratio <= 0.5`, hype allowed if quality dominates |

Each variant starts from the parent bottom-3 short book. It only searches inside
the parent bottom-8 boundary, prefers strict-eligible high event-quality names,
and leaves the parent selection unchanged when no strict candidate exists.

## Main Result

For short baskets, more negative forward return is better.

| variant | changed timestamps | selected delta vs parent h10d | entered h10d mean | entered - exited h10d | +1d entered h10d | +1d entered - exited |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `strict_q1_noise0` | 21.59% | -0.154% | -2.184% | -1.905% | -1.491% | -1.818% |
| `strict_q05_noise0` | 25.43% | -0.129% | -1.341% | -1.297% | -0.788% | -0.964% |
| `strict_q1_noise05` | 26.08% | -0.148% | -2.095% | -1.446% | -1.669% | -1.529% |

The strict variants clear the failure condition from the prior run: entered rows
are now negative-return shorts, not just less-bad replacements.

## Lead Variant

`strict_q1_noise0` is the cleanest lead.

- It is sparse enough to be a boundary rule, not a broad score overlay.
- It changes about `21.6%` of timestamps.
- Entered rows average `-2.18%` h10d.
- Entered rows beat exited rows by about `-1.90%` h10d.
- +1d delayed event tape still works directionally: entered `-1.49%`, entered
  minus exited `-1.82%`.

## Formal A/B Scaffold Update

New scaffold script:

[`evaluate_m3_3_strict_event_state_ab.py`](../../../scripts/quant_research/evaluate_m3_3_strict_event_state_ab.py:1)

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-strict-event-state-ab/m3_3_strict_event_state_ab.json`

The quarantined candidate is now wired as:

- candidate id: `xs_alpha_ontology_v5_rw_bridge_no_overlay_m3_3_strict_event_state_q1_noise0_h10d`
- model family: `xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0`
- landing shape: canonical parent short-boundary replacement only
- long book: unchanged
- short book: parent bottom-3 with strict event-state replacement from bottom-8

The M3.3 event-state columns are now generated inside the h10d exec-aligned
feature-set path for this scaffold. The formal run passes validation and
fixed-set paired comparison:

- rank IC mean: `0.117`
- validation Sharpe: `3.90`
- test Sharpe: `2.50`
- walk-forward median OOS Sharpe: `3.98`
- validation contract: `passed`
- experiment status: `pass`
- credible research evidence: `true`
- fixed-set comparison: `computed`
- fixed-set promotion gate: `passed`
- pairwise vs canonical parent: cumulative return diff `+0.290`, Sharpe diff
  `+0.281`, bootstrap P(candidate > parent cumulative return) `0.902`

The promotion-level alpha experiment card is still **no-go**, but the blocker
set has changed after evidence-plumbing repair. Cost and delay stress now pass;
fixed-set comparison now computes and passes. Remaining blockers are statistical
falsification blockers from the fast configured run
(`time=80`, `score=40`, `label=20` iterations):

- `time_shuffle_failed`
- `label_shuffle_failed`
- `symbol_holdout_failed`
- `liquidity_bucket_consistency_failed`

Interpretation: this is no longer a feature-pipeline or paired-comparison
blocker. It is a real research result with credible validation evidence and
positive canonical-parent paired evidence, but the mechanism attribution is not
hard enough for promotion: the edge is not sufficiently unusual versus time
shuffle, label shuffle, AVAX/UNI holdout flips negative, and the liquidity
bucket lift appears only in `top_liquidity`.

## Decision

Keep as **quarantined research evidence**, not production.

The next implementation should design a narrower M3.3 v2 that explicitly targets
the failed gates: time-shuffle robustness, label-shuffle separation,
symbol-dispersion, and liquidity-bucket consistency.

Follow-up v2 robustness diagnostics are now complete:
[`m3_3_robustness_v2_stage0.md`](m3_3_robustness_v2_stage0.md). The best
non-diagnostic rule, `v2_q2_noise0`, keeps a small positive edge but still fails
the core robustness shape: AVAX holdout remains negative and only one liquidity
bucket contributes positive edge. Do not promote v2 to manifest A/B.

## Failure Conditions

Reject the formal candidate if any of these hold:

- full strategy A/B does not improve parent net return or Sharpe,
- entered-row advantage disappears under +1d event delay,
- edge is concentrated in one or two symbols,
- strict replacements increase next-day squeeze rate materially,
- factor fails current canonical-parent falsification.
