# Quant Agent Prompting

## Purpose

This repo uses a two-stage OpenAI lane for weekly quant proposal discovery:

1. `selector` chooses up to 12 proposal intents.
2. `compiler` turns shortlisted intents into full `proposal_spec` JSON for deterministic evaluation.

The OpenAI lane is proposal-only. It does not run backtests, score experiments, or bypass governance. All evaluation, leakage checks, overlap checks, promotion, and bridge decisions remain deterministic.

## Shadow Lane

The active shadow lane is no longer OpenAI-driven. It is now a deterministic ETH-only grid search over the checked-in baseline:

- Base strategy: `core-eth-conservative-trend-following-single-asset`
- Search mode: `deterministic_grid`
- Active write roots:
  - `artifacts/quant_research/shadow_grid/<as_of>/...`
  - `artifacts/quant_research/cycles/<as_of>/eth_shadow_grid_daily_sample.json`
  - `artifacts/quant_research/cycles/<as_of>/eth_shadow_survival.json`
  - `artifacts/quant_research/shadow_candidates/<as_of>/shadow_candidate_list.json`
- Active gate:
  - same-day `hard_gate_passed && better_than_baseline`
  - then `5` adjacent `as_of` survived before candidate admission

The shadow lane no longer requires API keys, prompts, transcripts, or model output. OpenAI prompt rules now apply only to the legacy weekly proposal lane described below.

## Stage Design

### Selector

- Goal: return at most 12 `proposal_intents`.
- Envelope rule: emit exactly one `candidate_payloads` object and place all intents inside its `proposal_intents` array.
- Allowed output fields:
  - `search_action`
  - `base_strategy_id`
  - `subject`
  - `family_id_hint`
  - `priority_score`
  - `complexity_tier`
  - `required_patch_kind`
  - `risk_tags`
  - `auto_bridge_requested`
  - `why_now`
- Hard rules:
  - JSON only.
  - No Markdown fences.
  - No runnable code.
  - No full proposal specs.
  - `required_patch_kind` is a hard downstream requirement.
  - Do not emit `new_model_family` or `new_feature_family` intents unless the compiler can supply a non-empty registry patch.
  - Prefer `parameter_tune`, `feature_variant`, or `universe_variant` when no valid registry patch can be specified.

### Compiler

- Goal: compile shortlisted intents into full `proposal_spec` JSON.
- Hard rules:
  - JSON only.
  - No Markdown fences.
  - No runnable code.
  - Emit exactly one `candidate_payloads` object and place all compiled proposals inside its `proposals` array.
  - At most one proposal per selector intent.
  - Do not emit `new_model_family` or `new_feature_family` proposals unless the matching registry patch is non-empty.
  - `new_model_family` must include `family_registry_patch`.
  - `new_feature_family` must include `feature_registry_patch`.
  - Use only allowed engine templates and feature transforms from governance.

Minimal patch examples:

- `family_registry_patch`:
  - `{"families":[{"family_id":"adaptive_tree_stack","engine_template":"tree_ensemble","allowed_shapes":["single_asset"],"hyperparameters":{"max_depth":4}}]}`
- `feature_registry_patch`:
  - `{"families":[{"family_id":"adaptive_momentum_bundle","transforms":[{"transform":"ema","source":"close","window":21}]}]}`

## Context Sources

The prompt builder may read from:

- strategy library excerpt
- recent alpha registry excerpt
- universe excerpt
- recent weekly summary excerpt
- recent bridge suppressed excerpt
- registry snapshot excerpt
- strategy catalog payload

## Deterministic Budgeting

The request builder enforces hard request-body budgets:

- `selector`: 14,000 chars
- `compiler`: 16,000 chars

Trim order is fixed:

1. `strategy_library` discovery entries
2. `recent_alpha_registry_excerpt`
3. `universe_excerpt`
4. `recent_bridge_suppressed_excerpt`

If a stage still exceeds budget after deterministic trimming, the stage does not call OpenAI and returns `blocked_context_budget_exceeded`.

## Structured Output Contract

The OpenAI-compatible request uses:

- `response_format={"type":"json_object"}`
- `max_completion_tokens`
  - selector: `1200`
  - compiler: `2500`

If the backend rejects `response_format` with `HTTP 400` and an unsupported-parameter style message, the client retries once without `response_format`. Other failures do not retry automatically.

## Summary Fields

`agent_proposal_summary.json` records both stages:

- `selector`
- `compiler`

Each stage captures:

- `status`
- `blocked_reason`
- `request_body_chars`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `latency_ms`
- `retry_count`
- `fallback_without_response_format`
- `budget_status`

`weekly_governance_summary.json` adds:

- `selector_usage`
- `compiler_usage`
- `prompt_budget_status`
- `response_format_fallback_count`

## Live Smoke

Use one real weekly run as the final acceptance check.

Pass criteria:

- both `selector` and `compiler` make real OpenAI calls
- both stages record non-zero token usage
- `agent_proposal_summary.status` is not `degraded_no_api`
- `agent_proposal_summary.status` is not `degraded_transport_error`
- `parse_success_rate > 0`

Proposal quarantine is acceptable. JSON-format, response-format, and transport failures are not.
