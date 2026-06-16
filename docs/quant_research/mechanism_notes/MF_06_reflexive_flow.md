# MF-06: Reflexive flow (absorption / amplification)

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1`

---

## Economic story

The volume-price relationship has a second-order signal that gets washed out
in single-bar volume z-scores. *Absorption*: a large quote-volume burst that
moves price by less than expected given realised vol implies an inventory
sink — a market participant is accumulating against the flow without
revealing a price footprint. *Amplification* / *capitulation*: a large
adverse price move on small volume implies liquidity exhaustion — there is
no resting bid (or offer) and the few aggressive sellers (buyers) are moving
price disproportionately. Both states predict short-horizon mean reversion
in opposite directions: absorption tends to continue with the absorbing
flow's direction once accumulation completes; capitulation tends to reverse.

Flow imbalance persistence — sign(taker_imb) × sign(return) summed over
20 days — measures whether flow has been *causal* for price (concordant) or
fighting price (discordant). High concordance is a momentum-continuation
signal; sustained discordance is a divergence that historically resolves in
favour of the flow side.

## Why this alpha persists

- **Belief asymmetry**: the participant accumulating in absorption mode does
  not want to reveal intent. Hiding cost is real (split orders, dark
  routing, time fragmentation) and limits the population that exploits the
  signal.
- **Operational latency**: capitulation events are by definition seconds-
  to-minutes scale; daily- or 4h-aggregate factors capture the residue
  rather than the live cascade. Acting on the residue is harder than it
  looks because liquidity is still degraded.
- **Sparse training data**: capitulation events fire rarely (5% of bars in
  the W1.3 cards). Models that need long sample to fit the regression cannot
  rely on this family.

## Required primitives

- `quote_volume_expansion` — derived in `features.py` from
  `spot_quote_volume` rolling-20 mean.
- `return_1` — derived from `spot_close` percent change.
- `realized_volatility_20` — derived in `features.py`.
- `coinglass_taker_imbalance_5d_sum` — Coinglass directional flow series.
- `open_interest`, `oi_change_5` — for F17 leverage-build vs flow ratio.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F16 | `qv_acceleration_residual_xs` | + | 3–5 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC −0.009) |
| F17 | `oi_to_vol_ratio_anomaly` (TBD) | cond | 4–7 | T1 | not implemented |
| F18 | `flow_persistence_against_price_20` | + | 5–8 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC −0.006) |
| F19 | `absorption_score_20` | + | 4–7 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC +0.007) |
| F20 | `capitulation_amplification_event` | + | 2–4 | T1 | **W1.1 implemented**, report-carded, **G6 PASS** but **G3 FAIL** (33% same-sign); sparse-event |

## Expected sign and half-life

All of F16-F20 carry positive sign in the doc's blueprint (per §D), but the
W1.3 empirics on the current 1117-day panel produced near-zero IC for all of
them. The reflex family is the **weakest empirically** in the W1.1 batch.

## Regime where strongest

Accumulation phases for F19 (range-bound with quiet but sustained net flow);
breakout phases for F18 (concordance build-up); drawdown bottoms for F20
(capitulation event). F17 strongest during leverage-build phases (high OI
growth on low volume).

## Failure modes

- Single-day spike noise overwhelming the rolling computation — handled by
  the residualisation in F16, but residualisation is fragile when |return_1|
  has a heavy tail.
- Sparse-event sample bias for F20: with only ~5% of bars firing, even small
  bias in the trigger threshold produces large IC distortion.
- Coinglass taker-imbalance source quality variance — F18 is gated on the
  derivatives quality module's ready-flag.

## Falsification path

- For each admitted factor, rolling 60d residual IC stays below 0.02 for 90
  consecutive days → retire that factor.
- For F18 specifically: if `coinglass_taker_imbalance_5d_sum` source quality
  drops below 0.85 for 60 days → suspend F18 (data-quality-driven, not
  mechanism-driven).
- For F20 (sparse-event): rolling 90d residual IC computed on the event-only
  subset < 0.02 → retire. F20 is evaluated quarterly, not monthly.

## Implementation status

- in `features.py`: F16 (`qv_acceleration_raw` + `_residual_xs`), F18
  (`flow_persistence_against_price_20`), F19 (`absorption_score_raw` +
  `_20`), F20 (`capitulation_amplification_event`) all from W1.1.
- admitted via `feature_admission.py`: all four via W1.2 prefix
  (`qv_acceleration_*`, `flow_persistence_*`, `absorption_*`) plus F20 via
  exact-column allowlist.
- present in any active manifest: **none**. The W1.4 selection rule (G6 +
  G3 strict pass) admitted zero factors from MF-06 to
  `xs_alpha_ontology_v1`.
- report-carded: see
  `artifacts/quant_research/factor_reports/2026-04-29/F1{6,8,9}_*.{json,txt}`
  and `F20_capitulation_amplification.{json,txt}`.

Next action: do **not** rebuild the existing four with parameter sweeps —
that risks p-hacking the gate. Instead implement F17
(`oi_to_vol_ratio_anomaly`) which is conceptually orthogonal to F16-F20
(uses OI rather than quote volume); report-card it; if it also fails G6 then
demote MF-06 to `watch` and pivot effort to MF-09 / MF-11. The §G.6 exit
criterion ("combined IC uplift ≥ 0.005 vs the prior baseline") is the
binding constraint here, not factor count.

## Cross-references

- Alpha ontology memo §B (MF-06 row), §D (Family MF-06 table), §F (top-20
  prioritisation listed F19 / F18 at #2-3 a-priori, but W1.3 empirics rank
  them lower).
- Threshold provenance log: `config/quant_research/threshold_provenance.md`
  W1.3 / W1.4 entry documents the MF-06 admission gap.

---

## Change log

- `2026-04-29` — initial note created from §B / §D content (W1.5). Status
  intentionally `draft` rather than `active`: while four factors are
  implemented and admitted, none are in a live manifest and the family's
  empirical viability against v91 baseline is currently unproven.
