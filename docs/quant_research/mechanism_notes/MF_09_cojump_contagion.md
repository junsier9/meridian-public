# MF-09: Co-jump & contagion network

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (CEX cross-asset returns are sufficient)`

---

## Economic story

Cross-sectional models built on per-asset features lose information about
the *structure* of co-movement across the universe. Two facts matter:

1. The correlation structure in the **tail** is different from the
   correlation structure in the **center**. When one name jumps, the
   conditional distribution of other names' jumps is much heavier than the
   unconditional joint distribution would suggest. Standard rolling
   correlations underestimate this.
2. Lead-lag relationships are real and persistent. ETH does not lead BTC,
   but mid-cap alts often lag both. Lead-lag betas decay (a name that
   followed BTC in 2023 may decouple in 2025), so the *current* lead-lag
   structure is a state variable.

Concretely: when BTC realises a 3σ down move, the conditional probability
of ETH realising a same-day 2σ down move is ~70%; for a randomly chosen
top-20 alt the conditional probability is closer to 35%. The co-jump
indicator is therefore a clean systemic-shock detector. Network centrality
in the rolling correlation graph identifies which names are in the
"hub" position — these are systemic-risk receivers and tend to underperform
in risk-off episodes.

## Why this alpha persists

- **Modelling cost**: rolling correlation matrices are cheap; eigen-
  decomposition-based centrality measures and tail-aware co-jump counters
  require more careful implementation. Most teams stop at pairwise
  correlation.
- **Universe definition friction**: the network depends on the universe.
  Adding or removing a single name re-wires the graph. Stability of the
  measure across universe-rotation is a real engineering challenge.
- **Estimation noise**: short-window correlation matrices are notoriously
  noisy. Eigen-centrality requires either long windows (slow) or
  shrinkage (extra modelling).

## Required primitives

- `return_1` per asset — already in panel.
- Universe membership (`liquidity_bucket`) — already in panel.
- `realized_volatility_20` — for jump-threshold calibration.

The whole family runs on existing data; no new ingest required.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F26 | `co_jump_count_24h` (TBD) | universe-wide regime gate | 1–3 | T1 | not implemented |
| F27 | `lead_lag_beta_btc` (TBD) | + (high lag-beta = follower = momentum) | 5–10 | T1 | not implemented |
| F28 | `lead_lag_residual_strength` (TBD) | + | 5–10 | T1 | not implemented |
| F29 | `contagion_in_degree` (TBD) | − (high in-degree = systemic risk receiver) | 3–7 | T1 | not implemented |
| F30 | `eigen_centrality_drift` (TBD) | − (high centrality = un-diversifiable) | 14–30 | T1 | not implemented |

## Expected sign and half-life

F27 / F28 (lead-lag) carry positive sign — followers continue to follow.
F29 / F30 (centrality) carry negative sign — central names are the ones
that lose first when systemic stress arrives. F26 acts as a regime gate.

The half-life range is wide (1–30 days) because the family contains both
fast (co-jump) and slow (eigen-centrality) variables. Fast factors enter
the score; slow factors should be regime-gating multipliers per §G.3.

## Regime where strongest

F26 (co-jump): systemic shocks (BTC-led drawdowns ≥ 3%), the strongest
signal day. F27 / F28: trending regimes where the lead-lag persists.
F29 / F30: structural regimes (rotation, risk-off) measured at ≥ 14d
horizons.

## Failure modes

- Universe rotation — the matrix changes when names enter / exit the
  liquidity bucket. Stable measures require aligning rolling windows
  carefully.
- Jump-threshold calibration — same risk as MF-08.
- Correlation matrix noise — handled by shrinkage; an unshrunk eigen
  decomposition can produce unstable centrality even on monthly windows.

## Falsification path

- F26 IC vs forward 1d return (universe-mean) < 0.02 → retire as regime
  gate.
- F27 lead-lag-beta IC vs forward 5d return < 0.04 → retire.
- F30 eigen-centrality drift's contribution as a position-size multiplier:
  if including the multiplier does not improve regime worst sharpe by ≥
  0.20 (per §G.6 exit criterion) → retire as gate.

## Implementation status

- in `features.py`: none. The current panel-builder operates per-subject
  and does not have a `_build_universe_network_features` step.
- admitted via `feature_admission.py`: none. Once F26-F30 columns land,
  prefix `co_jump_*`, `lead_lag_*`, `contagion_*`, `eigen_*` (or exact-
  column allowlist) is required.
- present in any active manifest: none.
- report-carded: none.

Next action: W3.2 (Day 14–30) — extend `_build_feature_bundle` with a
`_build_universe_network_features` step that runs after the per-subject
loop and computes (a) BTC-anchored lead-lag betas, (b) co-jump 24h
counter, and (c) rolling 60d eigen-centrality. F30 should be wired through
a new `regime_gating.py` module rather than into the score (per §G.3).

## Cross-references

- Alpha ontology memo §B (MF-09 row), §D (Family MF-09 table).
- §G.3 factor combination rule — gating multipliers vs score components.

---

## Change log

- `2026-04-29` — initial note created from §B / §D content (W1.5).
