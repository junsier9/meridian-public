# CANONICAL_RUNBOOK.md

Any legacy draft that reintroduces `1800.0` or exit-code-only logic is obsolete and must not be used.

## Document Contract
- `README.md` is the project and developer entrypoint.
- `AGENTS.md` is the dense agent startup page.
- `CLAUDE.md` is a legacy compatibility entrypoint and must defer to `AGENTS.md` on startup-role wording.
- `PROJECT_STATE.md` is the canonical truth source for checked-in facts and accepted evidence.
- `CANONICAL_RUNBOOK.md` is the exact command and failure-routing source.

## Artifact Vocabulary
- `<ArtifactsRoot>` means the operator-supplied root for the formal real-24h bundle only.
- `RunArtifactsRoot` means a generated per-run root for owner, review, demo, and readiness flows.
- `ObjectArtifactsRoot` means a generated per-object workbench root for research and similar long-lived objects.
- Repo-local `artifacts\...` paths are examples of generated output, not required checkout state.

## Agent Slice Exception
- `READY_FOR_AGENT_LAYER` is computed from real-shadow acceptance evidence plus `config/agent_layer_governance/manifest.json` and `config/agent_layer_governance/governed_slice_registry.json`.
- `READY_FOR_BROAD_AGENT_LAYER` is computed from real-shadow acceptance evidence plus the checked-in broad-ready governance state.
- The checked-in governed-slice registry currently admits `["market_observer", "evidence_agent", "risk_signal_agent", "risk_governance_agent", "validation_agent", "attention_allocator", "research_synthesizer", "research_lead"]`.
- All eight checked-in slices are now real source-controlled promoted `governed_agent_slice` samples.
- The registry may admit only promotion-grade governed-slice candidates that satisfy `controlled_agent_slice_promotion.v1`; exported scaffold ids do not qualify.
- `registered_pending_promotion_controlled_slice_ids` represents admission-ready candidates, and it is empty in the current checked-in shipped state.
- The checked-in manifest currently allows all eight admitted slices, `broad_agent_layer_ready = true`, and `broad_agent_layer_enabled = false`.
- The checked-in owner topology contract lives at `config/agent_architecture/main_owner_manifest.json`.
- The checked-in runtime ownership contract lives at `config/project_governance/runtime_ownership_contract.json`.
- The checked-in owner-centered design note lives at `docs/agents/OWNER_AGENT_ARCHITECTURE.md`.
- Explicit owner artifacts are written under `RunArtifactsRoot\agent_owner\<run_id>\`; repo-local `artifacts\agent_owner\<run_id>\` is one generated example.
- `python scripts\verify\run_operational_readiness.py` is the canonical command to confirm that all eight governed slices are current/shipped while the broad layer remains disabled.
- `python scripts\verify\run_risk_signal_agent_pending.py`, `python scripts\verify\run_risk_governance_agent_pending.py`, `python scripts\verify\run_validation_agent_pending.py`, `python scripts\verify\run_attention_allocator_pending.py`, `python scripts\verify\run_research_synthesizer_pending.py`, and `python scripts\verify\run_research_lead_pending.py` are compatibility verify entries for the promoted public paths.
- `python scripts\verify\run_agent_architecture_contract.py` verifies the owner manifest and owner artifact contract.
- `python scripts\verify\run_rulebook_agent_review_samples.py` verifies the secondary operator-review surfaces on `risk_governance_agent`, `validation_agent`, `attention_allocator`, `research_synthesizer`, and `research_lead`.
- `python scripts\verify\run_broad_agent_layer_readiness.py` is the canonical broad-ready verification bundle.
- `python scripts\verify\run_operational_readiness.py` supports `--attempts <N>` and `--retain-root <path>` for repeated, evidence-retaining readiness verification.
- `python scripts\verify\run_broad_agent_layer_readiness.py` now embeds `python scripts\verify\run_operational_readiness.py --attempts 3` and only passes when all three operational-readiness attempts succeed.
- `python scripts\verify\run_broad_agent_layer_readiness.py` now also evaluates `config/agent_layer_governance/broad_unlock_contract.json` and writes `broad_unlock_evaluation.json`; a green result means "eligible for manual unlock", not "manifest already flipped".
- `python scripts\verify\run_evidence_freshness_contract.py` is the freshness gate for accepted evidence referenced by `PROJECT_STATE.md`.
- `python scripts\verify\run_local_integrity_gates.py` is the canonical local submit-time gate for `compileall`, JSON parsing, null-byte/disk-integrity checks, and quant bridge-summary contract checks before a commit or review handoff.
- `python scripts\verify\run_operational_readiness.py` and `python scripts\verify\run_broad_agent_layer_readiness.py` are expected to agree and to stay stably green under that repeated verification path before any further rollout work.
- The governed exception may reuse only the existing runtime ingress, execution control, and governance paths.
- The governed exception does not authorize a broad agent layer rollout, multi-agent orchestration, or new provider permissions.

## Governed Agent Canonical Commands
```powershell
python examples\governed_agent_ingress_demo.py market_observer --subject AIX --scope spot+perp --object-id market-observer-aix --observation-text "AIX still shows supportive structure with a higher low above intraday support and no immediate breakdown signal."
python examples\governed_agent_ingress_demo.py evidence_agent --subject AIX --scope spot+perp --object-id evidence-agent-aix --evidence-text "Fresh desk notes still show aggressive buyers supporting AIX after the initial breakout."
python examples\governed_agent_ingress_demo.py risk_signal_agent --subject AIX --scope spot+perp --object-id risk-signal-aix --risk-text "Fresh tape action now shows a clear invalidation risk after buyers lost the prior support shelf."
python examples\governed_agent_ingress_demo.py risk_governance_agent --subject AIX --scope spot+perp --object-id risk-governance-aix --governance-text "The object now carries a live governance suppression need because risk remains unresolved and publish should stay disabled."
python examples\governed_agent_ingress_demo.py validation_agent --subject AIX --scope spot+perp --object-id validation-agent-aix --validation-text "Validation should stay on hold because the latest thesis conflict is unresolved and the publish gate is still not legally clear."
python examples\governed_agent_ingress_demo.py attention_allocator --subject AIX --scope spot+perp --object-id attention-allocator-aix --attention-text "Keep attention elevated because the object still needs targeted monitoring around the latest conflict."
python examples\governed_agent_ingress_demo.py research_synthesizer --subject AIX --scope spot+perp --object-id research-synthesizer-aix --synthesis-text "Current bounded synthesis still leans constructive, but conflict risk remains high enough that this should stay a preview rather than a final thesis."
python examples\governed_agent_ingress_demo.py research_lead --subject AIX --scope spot+perp --object-id research-lead-aix --directive-text "Next stage should focus on a targeted refresh of the conflict evidence before any publication path is reconsidered."
```

- The shipped commands target the canonical governed ingress boundaries:
  - `market_observer` -> `runtime.run_new_from_agent_payloads`
  - `evidence_agent` -> `runtime.continue_existing_from_agent_payloads`
  - `risk_signal_agent` -> `runtime.continue_existing_from_agent_payloads`
- `market_observer` accepts raw observation input and uses a live OpenAI-compatible compiler backend by default before owner-first runtime ingress.
- `market_observer` fails closed on the public path when `ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL`, `ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME`, or `ENHENGCLAW_MARKET_OBSERVER_API_KEY` is missing.
- `market_observer --compiler-backend recorded --recorded-transcript <path>` is the canonical offline replay mode for acceptance and verify.
- `market_observer --compiler-backend deterministic` remains an explicit low-level fallback only.
- `docs\MINIMAL_MARKET_RESEARCH_WORKFLOW.md` is the canonical manual-snapshot research runbook for operators who want to use existing Skills and thesis objects without depending on real-time ingestion, 24h shadow, or OpenClaw deployment.
- That workflow intentionally reuses the shipped governed slices as a research object-management layer: `market_observer -> evidence_agent -> risk_signal_agent -> research_synthesizer -> research_lead`.
- The default v1 backend for that workflow is `--compiler-backend deterministic`, and a common repo-local `ObjectArtifactsRoot` example is `artifacts\research_workbench\<object_id>`.
- `docs\templates\market_research\watchlist_template.csv`, `cycle_snapshot_template.md`, and `pain_log_template.csv` are the canonical operator templates for running the initial `5-10` thesis pilot and deciding whether any single API class should be added next.
- `docs\EXTERNAL_OPENCLAW_RESEARCH_DEPLOYMENT.md` is the canonical scheduler-safe external research path when OpenClaw + Skills should write one normalized snapshot per cycle into the thesis workbench through the shipped OpenClaw adapter layer.
- That path intentionally stays research-only: it now runs as an upstream open-market scan plus an hourly thesis consumer, provisions one explicit external permit per cycle under `%LOCALAPPDATA%\EnhengClaw\openclaw_research_workbench`, validates against the read-only ProgramData trust root, defaults to `--compiler-backend live`, and writes cycle artifacts under `ObjectArtifactsRoot\cycles\<cycle_id>\` (a common repo-local example is `artifacts\research_workbench\<object_id>\cycles\<cycle_id>\`).
- `python scripts\openclaw\provision_openclaw_research_inputs.py`, `python scripts\openclaw\run_openclaw_research_scan.py --market-scan <MarketScanJsonPath>`, and `python scripts\openclaw\run_openclaw_research_cycle.py --snapshot <SnapshotJsonPath>` are the canonical entrypoints for that scheduled path.
- `docs\templates\market_research\openclaw_research_market_scan_template.json` and `docs\templates\market_research\openclaw_research_snapshot_template.json` are the canonical upstream contracts for external OpenClaw + Skills.
- OpenClaw deployment boundaries now exist for all eight shipped lanes, and they are still intentionally narrower than the shipped internal governed-agent surface.
- All eight shipped lanes currently have recorded OpenClaw deployment boundaries; `market_observer` remains the checked-in create-new live proof path via `python scripts\verify\run_openclaw_market_observer_smoke.py --live-smoke --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]`.
- The seven resume-only OpenClaw lanes now share an archetype-based live rollout on the hardened trust-root baseline:
  - `python scripts\verify\run_openclaw_continue_existing_live_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]`
  - `python scripts\verify\run_openclaw_review_gated_live_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]`
- The single formal OpenClaw deployment decision gate is `python scripts\verify\run_openclaw_deployment_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]`; it remains separate from `run_broad_agent_layer_readiness.py`.
- `market_observer` now also has a formal external input workflow:
  - `python scripts\openclaw\provision_market_observer_live_inputs.py`
  - `powershell -ExecutionPolicy Bypass -File scripts\openclaw\run_market_observer_deployment_gate.ps1`
- The PowerShell launcher now builds one unified child-process live env baseline for the full formal deployment bundle. In a clean session, `OPENCLAW` is enough for the default operator path: each live lane preserves any already-set dedicated `ENHENGCLAW_<LANE>_*` values, otherwise defaults `*_MODEL_BASE_URL=https://api.openai.com/v1`, defaults `*_MODEL_NAME=gpt-5.4`, and maps the lane API key from `OPENCLAW`.
- Direct `python scripts\verify\run_openclaw_deployment_readiness.py ...` invocation now applies the same unified child-process live env baseline before launching `market_observer` live and the two archetype live bundles, so the formal decision boundary stays singular even when the operator launcher is skipped.
- On the current Windows/WSL host, the hardened passing retained bundle now uses the split-root baseline: signer / permit / retained artifacts remain under `%LOCALAPPDATA%\\EnhengClaw\\openclaw_live_market_observer`, the trust-root publishes to `C:\ProgramData\EnhengClaw\trust`, and the default workflow no longer depends on `ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT=1`. The latest green operator retained bundle from that workflow is `%LOCALAPPDATA%\\EnhengClaw\\openclaw_live_market_observer\\retained\\20260417T164045Z\\`, and the latest direct clean-session formal-gate retained bundle is `%LOCALAPPDATA%\\EnhengClaw\\openclaw_live_market_observer\\retained\\direct_bundle_env_unified\\`.
- Active OpenClaw wrapper workspaces:
  - `\\wsl.localhost\Ubuntu-24.04\root\.openclaw\workspace-enhengclaw-main`
  - `\\wsl.localhost\Ubuntu-24.04\root\.openclaw\workspace-enhengclaw-audit`
- Repo-native OpenClaw adapter entrypoints:
  - `python -m enhengclaw.integrations.openclaw.market_observer`
  - `python -m enhengclaw.integrations.openclaw.evidence_agent`
  - `python -m enhengclaw.integrations.openclaw.risk_signal_agent`
  - `python -m enhengclaw.integrations.openclaw.attention_allocator`
  - `python -m enhengclaw.integrations.openclaw.research_synthesizer`
  - `python -m enhengclaw.integrations.openclaw.research_lead`
  - `python -m enhengclaw.integrations.openclaw.risk_governance_agent`
  - `python -m enhengclaw.integrations.openclaw.validation_agent`
- OpenClaw deployment requests must provide an explicit execution permit.
- OpenClaw recorded replay requests must also provide an explicit `input_id` together with `recorded_transcript_path`.
- `market_observer` remains the only create-new OpenClaw lane.
- `evidence_agent`, `risk_signal_agent`, `attention_allocator`, `research_synthesizer`, `research_lead`, `risk_governance_agent`, and `validation_agent` are resume-only on the OpenClaw boundary; they must point to an existing `object_id` and do not support `skip_seed` or auto-seed behavior.
- `evidence_agent` now accepts bounded raw evidence input, compiles against existing-object context, and uses a live OpenAI-compatible compiler backend by default before owner-first runtime ingress.
- `evidence_agent` fails closed on the public path when `ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL`, `ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME`, or `ENHENGCLAW_EVIDENCE_AGENT_API_KEY` is missing.
- `evidence_agent --compiler-backend recorded --recorded-transcript <path>` is the canonical offline replay mode for acceptance and verify.
- `evidence_agent --compiler-backend deterministic` remains an explicit low-level fallback only.
- `risk_signal_agent` now also accepts bounded raw input and runs as a shipped promoted public governed slice by default.
- `risk_governance_agent`, `validation_agent`, `attention_allocator`, `research_synthesizer`, and `research_lead` also accept bounded raw input and now run as shipped promoted public governed slices by default.
- All governed-agent demo commands self-provision a temporary permit by default.
- Use `--execution-permit <path>` when you want to run with an external permit/trust-root setup.
- Add `--require-external-permit` when the operator path must fail closed unless a caller-supplied permit is present.
- `evidence_agent` seeds and continues by default, so external single-use permits must be paired with `--skip-seed`.

## Additional Promoted Operator Samples
```powershell
python examples\governed_agent_ingress_demo.py risk_governance_agent --subject AIX --scope spot+perp --object-id risk-governance-aix --governance-text "The object now carries a live governance suppression need because risk remains unresolved and publish should stay disabled."
python examples\governed_agent_ingress_demo.py validation_agent --subject AIX --scope spot+perp --object-id validation-agent-aix --validation-text "Validation should stay on hold because the latest thesis conflict is unresolved and the publish gate is still not legally clear."
python examples\governed_agent_ingress_demo.py attention_allocator --subject AIX --scope spot+perp --object-id attention-allocator-aix --attention-text "Keep attention elevated because the object still needs targeted monitoring around the latest conflict."
python examples\governed_agent_ingress_demo.py research_synthesizer --subject AIX --scope spot+perp --object-id research-synthesizer-aix --synthesis-text "Current bounded synthesis still leans constructive, but conflict risk remains high enough that this should stay a preview rather than a final thesis."
python examples\governed_agent_ingress_demo.py research_lead --subject AIX --scope spot+perp --object-id research-lead-aix --directive-text "Next stage should focus on a targeted refresh of the conflict evidence before any publication path is reconsidered."
```

- These commands are intentionally public, run raw-input execution/compiler pipelines, and now finalize on success while still failing closed on blocked or quarantine outcomes.
- Expected state today:
  - `agent_id = risk_governance_agent | validation_agent | attention_allocator | research_synthesizer | research_lead`
  - `registered_pending_promotion_controlled_slice_ids = []`
  - `current_controlled_slice_ids = ["market_observer", "attention_allocator", "evidence_agent", "research_lead", "research_synthesizer", "risk_governance_agent", "risk_signal_agent", "validation_agent"]`
  - `broad_agent_layer_ready = true`
  - `broad_agent_layer_enabled = false`

## Secondary Operator Review Surfaces
```powershell
python examples\rulebook_agent_review_demo.py risk_governance_agent --artifacts-root artifacts\governed_demo
python examples\rulebook_agent_review_demo.py validation_agent --artifacts-root artifacts\governed_demo
python examples\rulebook_agent_review_demo.py attention_allocator --artifacts-root artifacts\governed_demo
python examples\rulebook_agent_review_demo.py research_synthesizer --artifacts-root artifacts\governed_demo
python examples\rulebook_agent_review_demo.py research_lead --artifacts-root artifacts\governed_demo
```

- These commands are secondary read-only surfaces attached to pending writable agents.
- They seed or reuse one deterministic runtime session and then return one read-only structured review without mutating the session.

## Canonical Inputs
- `<ExecutionPermitPath>`
- `<ArtifactsRoot>`
- `<TrustRootDir>`
- `<PreflightLabel>`
- `<RerunLabel>`

## Canonical Constants
- `real-24h permit margin = 86460.0` (`24h + 60s`)
- `1800.0` remains the non-real default permit margin and must never be reused as the real-24h floor
- `rerun is forbidden unless all_green = true`
- `rerun label must differ from preflight label`

## Verify Command
```powershell
python scripts\verify\run_market_observer_execution.py
python scripts\verify\run_market_observer_execution.py --live-smoke
python scripts\verify\run_openclaw_market_observer_smoke.py
python scripts\verify\run_openclaw_evidence_agent_smoke.py
python scripts\verify\run_openclaw_risk_signal_agent_smoke.py
python scripts\verify\run_openclaw_attention_allocator_smoke.py
python scripts\verify\run_openclaw_research_synthesizer_smoke.py
python scripts\verify\run_openclaw_research_lead_smoke.py
python scripts\verify\run_openclaw_risk_governance_agent_smoke.py
python scripts\verify\run_openclaw_validation_agent_smoke.py
python scripts\verify\run_evidence_agent_execution.py
python scripts\verify\run_evidence_agent_execution.py --live-smoke
python scripts\verify\run_risk_signal_agent_execution.py
python scripts\verify\run_risk_governance_agent_execution.py
python scripts\verify\run_validation_agent_execution.py
python scripts\verify\run_attention_allocator_execution.py
python scripts\verify\run_research_synthesizer_execution.py
python scripts\verify\run_research_lead_execution.py
python scripts\verify\run_governed_agent_ingress.py
python scripts\verify\run_broad_agent_layer_readiness.py
```

## Quant H10D Mainline
- Do not infer the live-running strategy from the latest research validation file. The current documented remote live fallback/frozen-config baseline is `v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget:multiphase_10_sleeve` through the Meridian `hv_balanced_binance_usdm_live_2x_full_balance_candidate` runtime namespace. The remote live scorer config also has the 12-factor `v5_rw_bridge_no_overlay_h10d` frontier plus DTH60 overlay enabled; order flow remains separately gated and current readback is disarmed (`live_delta_armed=false`, timers disabled/inactive, no open unattended budget epoch). Refresh these facts from the remote live config and operator state before changing live-status docs.
- Current canonical h10d research baseline is `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`: the score parent is `v5_rw_bridge_no_overlay_h10d` / `xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`, and the default portfolio construction is 10-phase `multiphase_equal_sleeve` with equal 0.1 sleeve weights. The machine-readable registry is `config\quant_research\active_h10d_registry.json`.
- New h10d candidates must attach to that score parent and report against the 10-phase equal-sleeve construction by default. `v6_h10d`, `regime_gating_v2`, and SP-K variants are comparator / research-only unless a new candidate based on the canonical parent passes the promotion evidence guard.
- Before any h10d candidate is called promotable, run:
```powershell
python scripts\quant_research\assert_h10d_promotion_evidence.py --alpha-card <AlphaCardPath>
```
- The guard fails unless fixed-set paired comparison is computed and passed, overlay ablation is computed and passed, and the capacity evidence inside the h10d promotion gate stays within `config\quant_research\promotion_gate_h10d.json`.
- R-1 blocker attribution is part of the promotion/falsification contract. `top_bucket_only` and `symbol_holdout_dependency` must remain independent fail-closed reasons when observed; missing statistical falsification must remain `not_measured_fail_closed` or equivalent, not a cost/delay failure.
- To refresh the R-1 blocker-attribution audit and narrow residual-lane diagnostic, run:
```powershell
python scripts\quant_research\audit_coinglass_h10d_parent_blocker_attribution.py
```
- Clean nightly h10d reruns should stay limited to the fixed set: `lsk3_g_v2_h10d`, `v5_h10d`, `v5_rw_bridge_no_overlay_h10d`, and legacy `v6_h10d`, but any current baseline performance readout must also include the 10-phase equal-sleeve construction layer. Do not sweep the historical manifest zoo for promotion decisions.

## Live Strategy-Only Remote Update Lane
- Use `docs\live_trading\hv_balanced_binance_usdm_pipeline\strategy_only_remote_update_runbook_2026_06_13.md` for future mainnet strategy-only remote updates.
- This lightweight lane is only for alpha, target-generation, universe, strategy-artifact, or strategy-config changes that do not affect order submission, execution planning, unattended controller behavior, owner intent, risk gates, systemd units, Binance permissions, leverage, margin, or account-control repair.
- Required shape: local minimal validation, commit, remote read-only precheck, archive sync, actual live config readback, systemd/operator/budget-state readback, and optional no-order proof. It must not manually fire timers, call controller `--apply`, arm live delta, or submit orders.
- If execution/risk/controller/timer/account-control code changes, do not use this lane; run the heavier validation path for the changed safety surface.

## OpenClaw Operator Path
```powershell
python scripts\openclaw\provision_market_observer_live_inputs.py
powershell -ExecutionPolicy Bypass -File scripts\openclaw\run_market_observer_deployment_gate.ps1
python scripts\verify\run_openclaw_market_observer_smoke.py
python scripts\verify\run_openclaw_market_observer_smoke.py --live-smoke --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]
python scripts\verify\run_openclaw_continue_existing_live_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]
python scripts\verify\run_openclaw_review_gated_live_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]
python scripts\verify\run_openclaw_deployment_readiness.py --execution-permit <WindowsPermitPath> [--trust-root-dir <WindowsTrustRootDir>] [--retain-root <WindowsRetainRoot>]
python scripts\verify\run_openclaw_evidence_agent_smoke.py
python scripts\verify\run_openclaw_risk_signal_agent_smoke.py
python scripts\verify\run_openclaw_attention_allocator_smoke.py
python scripts\verify\run_openclaw_research_synthesizer_smoke.py
python scripts\verify\run_openclaw_research_lead_smoke.py
python scripts\verify\run_openclaw_risk_governance_agent_smoke.py
python scripts\verify\run_openclaw_validation_agent_smoke.py
```

- `main` builds one lane-specific OpenClaw request, calls the matching repo adapter, and summarizes the response.
- `audit-review` reads the response plus owner/execution artifacts and, for review-gated lanes, also checks the stored review artifacts.
- v1 scope is still bounded external deployment only: one task maps to one lane, and there is no OpenClaw multi-lane orchestration.
- `run_openclaw_market_observer_smoke.py --live-smoke` remains the canonical single-lane OpenClaw live proof component. It only passes when `host live adapter smoke`, `workspace live smoke`, and `workspace live audit` all finalize successfully in one retained evidence root.
- `run_openclaw_continue_existing_live_readiness.py --execution-permit <WindowsPermitPath> [...]` is the canonical archetype live bundle for the five non-review resume-only lanes: `evidence_agent`, `risk_signal_agent`, `attention_allocator`, `research_synthesizer`, and `research_lead`.
- `run_openclaw_review_gated_live_readiness.py --execution-permit <WindowsPermitPath> [...]` is the canonical archetype live bundle for the two review-gated resume-only lanes: `risk_governance_agent` and `validation_agent`. It only passes when live execution finalizes and audit confirms review evidence consistency.
- `run_openclaw_deployment_readiness.py --execution-permit <WindowsPermitPath> [...]` is the only formal OpenClaw deployment go/no-go entrypoint. It now requires the eight recorded per-lane deployment smokes plus the `market_observer` live proof plus both archetype live bundles, and writes one machine-readable `bundle_summary.json`.
- `provision_market_observer_live_inputs.py` is the formal external-input provisioning step: it refreshes the persistent signer, owner review, batch approval, and execution permit under `%LOCALAPPDATA%\EnhengClaw\openclaw_live_market_observer`, then publishes the read-only trust-root to `C:\ProgramData\EnhengClaw\trust`.
- `run_market_observer_deployment_gate.ps1` is the formal operator launcher: it keeps env changes session-scoped, applies the unified child-process live env baseline for all live lanes in the bundle, prefers existing dedicated `ENHENGCLAW_<LANE>_*` overrides when present, otherwise falls back to `OPENCLAW`, does not inject `ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT=1`, and then launches `run_openclaw_deployment_readiness.py` with the fresh external permit plus the ProgramData trust-root.
- Shared baseline overrides are `OPENCLAW_BASE_URL`, `OPENCLAW_MODEL_NAME`, and `OPENCLAW_MODEL_TIMEOUT_SECONDS`; per-lane `ENHENGCLAW_<LANE>_*` values remain override-only compatibility knobs.
- This does not enable broad rollout, and `broad_agent_layer_enabled` remains `false`.
- The scheduled research path reuses the same lane env mapping model but validates only the five research lanes it actually runs: `market_observer`, `evidence_agent`, `risk_signal_agent`, `research_synthesizer`, and `research_lead`.
- `run_openclaw_research_cycle.py` is create-on-first-sight: `market_observer` runs only when the thesis object does not yet exist, while later cycles skip create-new and continue the existing object through the four resume-only research lanes.
- Every research cycle updates one per-thesis `pain_log.csv` plus workbench-level `api_gap_summary.json` / `api_gap_summary.md`; reminder thresholds stay advisory and point to only one next external API class.

## Real-Shadow Verify Command
```powershell
python scripts\verify\run_real_shadow_acceptance.py --mode verify
```

- This command is the canonical internal real-shadow verify gate.
- Readiness or unlock language in docs must not claim more than a passing run of this command proves.

## Formal Real-24h Operator Bundle
```powershell
python scripts\verify\run_real_24h_shadow_bundle.py --execution-permit <WindowsPermitPath> --artifacts-root <ArtifactsRoot> --preflight-label <PreflightLabel> --rerun-label <RerunLabel> [--trust-root-dir <WindowsTrustRootDir>]
```

- This is the formal operator bundle for `preflight-only -> rerun -> rerun verdict`.
- `scripts\run_shadow_24h.ps1` remains the low-level rerun launcher reused by the bundle, not the decision boundary.
- `exit_code = 0` is necessary but not sufficient for pass; the retained verdict files remain authoritative.
- The bundle fails closed when:
  - `<RerunLabel> == <PreflightLabel>`
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>` already exists
  - `preflight_assertions.json.all_green != true`
  - any required rerun verdict file is missing
- Wrapper-level retained evidence is written to:
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\bundle_summary.json`
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\preflight_stage.json`
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\rerun_stage.json`
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\verdict_stage.json`
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\rerun.stdout.log`
  - `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\rerun.stderr.log`

## Preflight-Only Evidence
- The bundle's preflight stage reuses the checked-in `preflight-only` helper and must write:
  - `<ArtifactsRoot>\preflight_only\<PreflightLabel>\run_config.json`
  - `<ArtifactsRoot>\preflight_only\<PreflightLabel>\preflight_result.json`
  - `<ArtifactsRoot>\preflight_only\<PreflightLabel>\provider_health_snapshot.json`
  - `<ArtifactsRoot>\preflight_only\<PreflightLabel>\preflight_assertions.json`
- `preflight_assertions.json.all_green` is the only rerun admission signal.
- The required assertion set remains the one locked in `PROJECT_STATE.md`.

## Rerun Execution
- The bundle launches rerun through:
  - `powershell -ExecutionPolicy Bypass -File scripts\run_shadow_24h.ps1`
- The rerun evidence directory remains fixed:
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>`
- `run_shadow_24h.ps1` stays reusable for low-level reruns, but it is not the formal operator command.

## Rerun Verdict Rules
- The bundle verdict reads only:
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>\go_no_go.json`
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>\soak_summary.json`
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>\provider_health_snapshot.json`
  - `<ArtifactsRoot>\soak_runs\<RerunLabel>\audit_record.json`
- The formal pass conditions remain:
  - `READY_FOR_REAL_24H_SHADOW = true`
  - `READY_FOR_BROAD_AGENT_LAYER = true`
  - `agent_layer_governance.blockers = []`
  - `broad_blockers = []`
  - `current_controlled_slice_ids` matches the shipped 8-slice list
  - `registered_pending_promotion_controlled_slice_ids = []`
  - `hard_failures = []`
  - `soft_failures = []`
  - `audit_record.status = "completed"`
  - `soak_summary.violations = []`
- Real 24h readiness claims must not exceed the latest successful full-duration rerun bundle produced by this command.

## Real-24h Failure Routing
- `preflight_assertions.json.all_green = false`
  Read `preflight_assertions.json` first, then `preflight_result.json`, then `provider_health_snapshot.json`. Stop before rerun.
- `<RerunLabel> == <PreflightLabel>`
  Treat as operator input error. Choose a new rerun label; do not overwrite evidence.
- `<ArtifactsRoot>\soak_runs\<RerunLabel>` already exists
  Treat as evidence collision. Inspect it as a past run or choose a fresh rerun label; do not reuse it for a new decision.
- rerun exit code is non-zero
  Read `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\rerun_stage.json`, then `rerun.stdout.log` and `rerun.stderr.log`, then inspect the retained verdict files if present.
- rerun exit code is zero but verdict is red
  Read `go_no_go.json`, `soak_summary.json`, `provider_health_snapshot.json`, and `audit_record.json` in that order. Exit code does not override retained evidence.
- provider preflight is red
  Read `preflight_result.json` and `provider_health_snapshot.json`; when Binance preflight failed, preserve and report the structured diagnostics fields from the retained payload.

## Current Host Validation
- Current checked host validation now includes:
  - a green real external-permit preflight-only bundle at `%LOCALAPPDATA%\EnhengClaw\real_shadow_bundle_validation\preflight_only\preflight-bundle-validation-20260418T1145Z\`
  - a short-duration wiring bundle at `%LOCALAPPDATA%\EnhengClaw\real_shadow_bundle_validation\real_24h_bundles\rerun-short-bundle-20260418T1146Z\`
- The short-duration bundle is expected to fail the formal verdict because it is below the 24h evidence window; it proves operator wiring and retained evidence shape only.
- The current operator host contract is still one Windows workstation plus WSL. Linux/macOS CI jobs validate static contracts and install contracts, not cross-platform operator deployment.
