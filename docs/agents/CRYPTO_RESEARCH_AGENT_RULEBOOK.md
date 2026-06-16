# Crypto Research Agent Rulebook

This document is the canonical local reference for the final agent rules discussed during system design.

It exists for one purpose:

- give future agent builders a stable, repo-local rulebook
- make clear which rules are already implemented in code
- prevent future agents from bypassing the runtime/state/publish boundaries

This file is descriptive and normative for agent construction.
It does not replace the executable rule engine in `src/enhengclaw/core` and `src/enhengclaw/orchestration`.

## 1. System First Principle

The system is not a collection of free-form agents that each decide what matters.

The system is:

- `research object` centered
- `thesis driven`
- `state constrained`
- `risk gated`
- `cadence controlled`

Every future agent must operate inside those constraints.

## 2. Agent Team Model

The intended team model is:

1. `Signal Intake Agent`
   - only ingests and normalizes raw signals
   - does not create final conclusions

2. `Attention Allocator`
   - decides whether an object deserves research budget
   - does not publish research

3. `Evidence Agent`
   - gathers supporting or opposing evidence for an existing research object / thesis
   - does not bypass object resolution

4. `Research Synthesizer`
   - assembles claims into theses
   - does not publish if runtime state does not allow it

5. `Validation Agent`
   - checks thesis strength, conflict, and decision stability
   - does not override publish gate

6. `Risk & Governance Agent`
   - evaluates risk, restriction, and blocking conditions
   - can suppress publishability
   - cannot silently promote a thesis

7. `Research Lead`
   - orchestrates stage order
   - does not bypass state machine, publish gate, or provider selection

## 3. Research Object Rules

All work must attach to a `ResearchObject`.

Future agents must not directly operate on raw signals as independent decision units.

A valid research flow is:

`signal -> claim -> conflict grouping -> attention/state update -> thesis -> publish gate`

Agents may enrich signals, claims, conflicts, or theses.
Agents may not skip the object boundary.

## 4. Claim and Evidence Rules

### Claim rules

Claims are the smallest decision-bearing units.

Claims must carry:

- type
- direction
- scope
- time horizon
- source family
- evidence references
- confidence
- status

Claim statuses are governed by the runtime and include at least:

- `grounded`
- `supported`
- `contested`
- `promoted`
- `invalidated`

### Evidence rules

Evidence quality is hierarchical and must remain explicit.

The effective evidence ladder is:

- `E1`
- `E2`
- `E3`
- `E4`
- `E5`

Future agents may add evidence, but may not silently upgrade evidence level without preserving the underlying source basis.

## 5. Claim-Level Conflict Grouping

Conflict must be grouped before thesis promotion.

Claims belong to the same conflict group only when they overlap on:

- `object_id`
- `subject`
- `scope`
- `time_horizon`
- semantic predicate dimension

Anchor eligibility is constrained by conflict severity:

- `high/critical unresolved` claims cannot be used as thesis anchors
- `medium unresolved` claims cannot be used as thesis anchors
- only clean or resolved claim groups may supply stable anchors

Future agents must not construct publishable theses from unresolved anchor conflicts.

## 6. Thesis Rules

The system works around theses, not around isolated signals.

### Thesis types

At minimum, the system supports:

- `descriptive`
- `predictive`
- `risk`
- `counter`

### Thesis constraints

- a thesis must be built from claims, not directly from raw signals
- a thesis may have anchor claims and supporting claims
- a thesis may be challenged by an opposing thesis
- predictive theses are the strictest and require the strongest publish gate

### Working thesis model

For each `object_id + scope + time_horizon`, the system may have:

- one `working primary thesis`
- zero or one `working opposing thesis`

Agents must act around these working theses.
They must not free-roam the signal pool once the working thesis pair exists.

## 7. Thesis Priority Rules

Working thesis selection is mandatory.

At any moment the runtime works around:

- the highest-priority valid primary thesis
- and, when needed, the most relevant opposing thesis

Risk thesis may preempt direction thesis when risk conditions are strong enough.

This is especially important in:

- `restricted` risk state
- `high/critical` thesis conflict
- evidence-complete but not publish-safe situations

Future agents must not override working thesis selection with ad hoc prompt logic.

## 8. Attention Rules

Attention is a control surface, not a UI score.

Attention determines:

- whether an object advances
- whether it remains in monitoring
- whether it deserves resource allocation
- whether it can continue to consume high-cost investigation slots

Agents may produce inputs that affect attention.
Agents may not set attention directly outside the runtime rule path.

## 9. State Machine Rules

The runtime state machine is the primary behavior boundary.

Core states:

- `candidate`
- `screened`
- `active_research`
- `evidence_complete`
- `publish_ready`
- `published`
- `monitoring`
- `archived`
- `blocked`

### State invariants

- `screened` is not an empty state
- single-cycle multi-hop forward transitions are forbidden
- `blocked` is a special exception path
- publish gate must not be called outside `publish_ready`

Future agents must not:

- trigger thesis building in forbidden states
- trigger thesis selection in forbidden states
- trigger claim promotion outside `evidence_complete`
- trigger publish semantics before `publish_ready`

## 10. Risk State Rules

Risk state is independent and must remain explicit.

Core values:

- `normal`
- `caution`
- `restricted`
- `blocked`

### Behavioral meaning

- `normal`: ordinary runtime behavior allowed
- `caution`: publish still possible if other gates pass
- `restricted`: no bullish publish; object may continue in restricted monitoring
- `blocked`: fail closed for normal runtime progression

Future agents must not interpret `restricted` as safe-to-publish.

## 11. Restricted Monitoring Rules

`restricted monitoring` is a real operating mode:

- `processing_state = monitoring`
- `risk_state = restricted`

Behavior in this mode:

- publish is not allowed
- deep investigation is not newly assigned
- targeted refresh and conflict work are allowed
- speculative or challenged theses may remain visible
- risk thesis may remain active

This mode is intentionally "continue running, but constrained".

## 12. Publish Gate Rules

Publish gate is the only legal path to a publish decision.

It may output only:

- `publish`
- `monitoring`
- `blocked`
- `archived`

### Critical boundary

No future agent may directly set publish semantics by itself.

It must go through:

- valid processing state
- valid thesis state
- valid risk state
- valid conflict state
- valid evidence status

### Predictive thesis publish rules

Predictive theses are intentionally strict.

They require, in final form:

- repeated working-primary stability
- multiple promoted claims
- multi-source anchor support
- fresh anchor evidence
- low or no unresolved thesis conflict
- risk state no worse than `caution`
- high enough attention

If these are not satisfied, the correct output is not publish.

## 13. Cadence Rules

Cadence determines how the object is reviewed after a run.

Different end states must produce different cadence outputs.

At minimum, the runtime distinguishes cadence for:

- `published`
- `monitoring`
- `restricted monitoring`
- `blocked`

Future agents must not invent their own hidden cadence.
They may request review, but runtime cadence remains authoritative.

## 14. Resource Allocation Rules

Resource allocation must be tied to:

- attention tier
- conflict severity
- current state
- risk profile

The system recognizes slot-level competition such as:

- deep investigation
- conflict resolution
- publish evaluation
- monitoring

Future agents must not claim deep/conflict/publish resources without passing through allocator logic.

## 15. Failure and Governance Rules

The system is designed to fail closed on dangerous ambiguity.

Examples:

- blocked provider selection
- invalid payload rejected at provider/adapter boundary
- runtime unavailable under default provider selection
- retired provider not eligible for silent fallback

This principle also applies to future agents:

- no silent retired-provider fallback
- no silent debug override
- no silent state bypass

## 16. What Future Agents Are Allowed To Do

Future agents may:

- submit new normalized signals
- enrich claim evidence
- request reassessment of attention, conflict, or risk
- propose theses through allowed runtime stages
- produce structured summaries around existing runtime outputs

Future agents may not:

- publish outside publish gate
- change runtime state directly
- bypass claim grouping
- bypass thesis selection
- force retired providers into normal runtime
- use debug override as normal operation

## 17. Implementation Map

The executable rule engine is already implemented across these files:

### Core rule engine

- `src/enhengclaw/core/research_object.py`
- `src/enhengclaw/core/state_machine.py`
- `src/enhengclaw/core/claims.py`
- `src/enhengclaw/core/conflicts.py`
- `src/enhengclaw/core/thesis.py`
- `src/enhengclaw/core/runtime_rules.py`
- `src/enhengclaw/core/attention.py`
- `src/enhengclaw/core/publish_gate.py`
- `src/enhengclaw/core/cadence.py`
- `src/enhengclaw/core/resources.py`
- `src/enhengclaw/core/session.py`

### Runtime boundary enforcement

- `src/enhengclaw/orchestration/runtime_runner.py`
- `src/enhengclaw/orchestration/runtime.py`

### Provider governance

- `src/enhengclaw/governance/provider_selection.py`
- `src/enhengclaw/governance/provider_portfolio.py`
- `src/enhengclaw/governance/shadow_mode.py`
- `src/enhengclaw/governance/shadow_promotion.py`
- `src/enhengclaw/governance/shadow_admission.py`
- `src/enhengclaw/governance/shadow_contribution.py`

### Operational review layer

- `src/enhengclaw/ops/runtime_ops.py`
- `src/enhengclaw/ops/daily_review.py`
- `src/enhengclaw/ops/weekly_review.py`
- `src/enhengclaw/ops/drift_inspector.py`
- `src/enhengclaw/ops/golden_corpus.py`

### Existing agent entrypoints

These are not the full multi-agent team yet, but they are current starting points:

- `src/enhengclaw/agents/definitions/market_observer.py`
- `src/enhengclaw/agents/schemas/market_observer.py`
- `src/enhengclaw/agents/tools/runtime_signal_intake.py`

## 18. Current Status

Current repo status is:

- the runtime rule engine exists in code
- provider/runtime governance exists in code
- operator review flow exists in code/docs
- the full multi-agent research team is not yet fully implemented as separate production agents
- this document is now the canonical local reference for that future build-out

## 19. Build Guidance

When building the next agents, use this sequence:

1. bind the agent to one allowed stage of the pipeline
2. define what structured input it may read
3. define what structured output it may emit
4. make sure output re-enters through runtime boundaries, not ad hoc code paths
5. verify the agent cannot bypass:
   - provider selection
   - claim grouping
   - thesis priority
   - publish gate
   - cadence

If a future agent design requires bypassing one of those layers, treat that as a design bug until proven otherwise.
