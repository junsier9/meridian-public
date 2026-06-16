# MF-16: Attention & narrative state machines

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T3`

---

## Economic story

Crypto markets are the most narrative-driven major asset class. A single
LLM-tagged narrative ("AI tokens", "RWA", "DePIN", "BRC-20") can pull
multi-week capital flows into a basket of names in days. The *level* of
narrative attention is volatile and noisy; the *state transitions* —
narrative entry (first detection on a name), persistence (sustained
co-mentions), spread (additional names entering the same narrative),
exhaustion (mention count decline), exit (no mentions for a window) — are
much more predictive of forward returns than the raw level.

Two state-machine factors capture most of the family's value:

1. **Narrative entry event**: the first detection of a tag on a name,
   conditional on the tag having been active in the broader universe.
   Carries 3–7 days of forward strength because attention is
   self-reinforcing on entry.
2. **Narrative concentration**: universe-wide HHI of narrative tags. When
   a single narrative dominates (high HHI), the cross-section's
   idiosyncratic alpha collapses into beta-on-narrative; when concentration
   falls, idiosyncratic alpha re-emerges.

The first factor is a per-asset state factor (positive sign, fast).
The second is a universe-wide regime factor (gating, slow).

## Why this alpha persists

- **LLM-tag pipelines are non-trivial**: producing PIT-clean narrative
  tags requires a curated tag taxonomy, an LLM that does not drift over
  time, and an anti-replay protection layer (the LLM cannot see future
  tags or future price moves when tagging the past).
- **Tag drift is a real risk**: an LLM trained in 2025 will tag 2023 data
  differently than the contemporaneously-tagged 2023 data. Defending
  against drift requires either re-tagging on rolling windows or freezing
  a tagging model for the OOS evaluation period.
- **Self-fulfilling-prophecy concern**: if our model both reads the
  narrative tag and trades on it, we create a feedback loop. Validation
  has to use leave-narrative-out cross-validation to confirm the alpha
  reproduces across narratives.

## Required primitives

- `narrative__<tag>` per-asset per-day count series — **[T3] not in
  panel**. Schema slot is reserved by `feature_admission.py` (the
  `narrative__` prefix exists in the policy structure) but is currently
  in `FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES` — column producers
  do not yet exist; the admission policy is conservatively excluding
  rather than passively allowing.
- `narrative__<tag>__intensity_score` — **[T3] not in panel**.

The whole family is gated on M3.3+ (Day 61–90+) curated event-tape +
narrative-tag pipeline.

**Admission caveat**: same as MF-08. Before any narrative-state factor
can enter a manifest, the admission policy needs an explicit `narrative__`
prefix allowlist update, paired with a PIT-clean replay audit.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F69 | `narrative_entry_event` (TBD) | + (entry = attention surge) | 3–7 | T3 | not implemented |
| F70 | `narrative_concentration` (TBD) | universe-wide regime gate | 14–30 | T3 | not implemented |

§E.7 (narrative state machine) is the corresponding frontier direction.

## Expected sign and half-life

F69 fast (3–7 days) and positive-sign at the entry event. F70 slow
(14–30 days) and used as a universe-wide gating multiplier rather than as
a score component.

## Regime where strongest

F69: hype-build phases — the first week or two after a narrative starts
appearing on social tape. F70: any regime where the universe is
narrative-dominated (one narrative captures > 30% of total tag mentions
over a 14-day window).

## Failure modes

- LLM-tag drift, see "why persists" above.
- Tag taxonomy churn — adding a new narrative tag mid-OOS-window changes
  the HHI denominator and produces an apparent regime shift that is
  artefactual.
- Self-reinforcing if the model trains on the same narrative-tagged data
  it later trades on. Validation must be carefully isolated.

## Falsification path

- §E.7 frontier line: leave-one-narrative-out cross-validation, narrative-
  conditioned alpha must be reproducible across narratives. If it is not
  → reject family (the alpha is concentrated in one or two narratives and
  is not a stable mechanism).
- F69 rolling 60d residual IC < 0.02 for 90 days on the narrative-entry
  subset → retire.
- F70 as gating multiplier: must improve regime-worst median sharpe by
  ≥ 0.20 from the v91 baseline (per §G.6) → otherwise retire from gating
  role.
- Placebo test: random-date narrative entries should produce IC within 1σ
  of zero. If random-date IC matches real-narrative IC → reject.

## Implementation status

- in `features.py`: none.
- admitted via `feature_admission.py`: none. `narrative__` prefix is in
  `FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES`.
- present in any active manifest: none.
- report-carded: none.

Next action: M3.3+ (Day 61–90+) — build the narrative-tag pipeline as a
T3 deliverable. Required components in order:
1. tag taxonomy (frozen for the OOS window),
2. LLM tagging job over historical social / news tape,
3. anti-replay timestamp validation,
4. column producers for `narrative__<tag>` series in `features.py`,
5. admission policy update (`narrative__` prefix allowlist with PIT-replay
   audit) and provenance entry,
6. F69 / F70 implementations and W1.3-style report cards.

This is the longest item in the 90-day plan and may slip to the second
quarter.

## Cross-references

- Alpha ontology memo §B (MF-16 row), §D (Family MF-16 table), §E.7
  (narrative state machine frontier direction).
- `feature_admission.py` — current `narrative__` exclusion policy.
- §A.3 line 62 — the doc memo's incorrect statement that
  `event__` / `narrative__` are admission-allowed; flagged in MF-08 too.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
