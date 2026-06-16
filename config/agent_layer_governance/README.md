Checked-in agent-layer governance policy lives here.

Current contracts:
- Canonical manifest path: `config/agent_layer_governance/manifest.json`
- Canonical governed-slice registry path: `config/agent_layer_governance/governed_slice_registry.json`
- Manifest contract version: `agent_layer_governance.v2`
- Registry contract version: `governed_slice_registry.v1`
- Promotion-grade slice contract version: `controlled_agent_slice_promotion.v1`

Checked-in state:
- The registry currently admits all exported agent ids:
  - `market_observer`
  - `evidence_agent`
  - `risk_signal_agent`
  - `risk_governance_agent`
  - `validation_agent`
  - `attention_allocator`
  - `research_synthesizer`
  - `research_lead`
- All eight exported slices are now source-controlled promoted `governed_agent_slice` samples.
- The checked-in manifest now allows all eight shipped governed slice ids.
- `registered_pending_promotion_controlled_slice_ids` is therefore empty in the current checked-in state.
- The checked-in repo is now broad-ready by structure:
  - `broad_agent_layer_ready = true`
  - `broad_agent_layer_enabled = false`
  - `broad_agent_layer_requested = false`
- Broad-open remains a separate future manifest flip; it is not part of the checked-in default state.

Manifest fields:
- `contract_version`
- `agent_layer_governance_enabled`
- `allowed_controlled_slice_ids`
- `broad_agent_layer_enabled`

Governed-slice registry fields:
- `contract_version`
- `admitted_controlled_slice_ids`

Evaluation rules:
- The repository defaults fail closed.
- The governed-slice registry is the declarative admission input for promotion-grade governed slice ids.
- A slice may enter the registry only when its exported definition satisfies the promotion-grade governed-slice contract:
  - `contract_version = controlled_agent_slice.v1`
  - `promotion_contract_version = controlled_agent_slice_promotion.v1`
  - `registry_admission_eligible = true`
  - `writes_to_runtime = true`
  - `slice_mode` is one of the shipped governed ingress modes
  - `canonical_runtime_boundary`, `prompt_path`, `schema`, and `tool` are all explicit
  - `max_tool_calls = 1` and `max_payloads = 1`
  - `promotion_verification_surface = canonical_verify_surface`
- `attention_allocator`, `research_synthesizer`, and `research_lead` now satisfy the promotion-grade writable contract, but they also keep an explicit secondary `operator_review_surface` for read-only inspection:
  - `surface_type = readonly_review`
  - `demo = rulebook_agent_review_demo`
- `allowed_controlled_slice_ids` may include only ids admitted by the governed-slice registry.
- The registry and manifest must both continue to cover every currently shipped governed slice id.
- Admitted ids that are not yet in `current_controlled_slice_ids` are reported as `registered_pending_promotion_controlled_slice_ids`; registry admission alone does not make them shipped governed slices.
- `broad_agent_layer_ready` is a checked-in structural signal computed from:
  - every exported agent id satisfying the promotion-grade writable contract
  - the governed-slice registry exactly matching the promotion-eligible controlled slice ids
  - the manifest still allowing every currently shipped governed slice id
- `python scripts\verify\run_broad_agent_layer_readiness.py` is the canonical runnable verify bundle that proves the checked-in broad-ready state across all pending per-agent verifies plus the existing canonical gates.
- Missing files, invalid JSON, unknown fields, bad types, duplicate ids, registry out-of-scope ids, manifest/registry mismatches, and premature broad-rollout requests all block enablement.
- `broad_agent_layer_enabled = true` is supported only when:
  - `agent_layer_governance_enabled = true`
  - `broad_agent_layer_ready = true`
  - `broad_blockers = []`
- Do not store secrets or provider credentials here.
