# README_FOR_AGENT.md

## What This Project Is

`Meridian Alpha Platform` is a dual-track Python codebase, formerly `EnhengClaw`:

- `Agent Control Framework`: controlled shadow ingestion, governed agent execution, OpenClaw deployment boundaries, and operator-facing verification.
- `Research & Alpha Platform`: research workbenches, quant research/governance cycles, scheduled intake, and governed promotion into human review queues.

The checked-in repository is now at `Stage 4: Automated Execution` according to `config/project_governance/project_profile.json`. That stage-contract fact does not by itself authorize broad rollout or live order flow: the current remote runner remains fail-closed unless separate owner, on-host, budget, and runtime gates are satisfied.

The two most important live-facing decision surfaces are:

- the formal real-24h bundle: `preflight-only -> rerun -> retained verdict`
- the formal OpenClaw deployment gate: recorded smokes plus bounded live proofs

This repository already has strong runtime contracts. The main risk for a new agent is not "how do I run Python," but "which retained evidence and which document actually decide readiness."

## Document Roles

- `README.md` is the human project and developer entrypoint.
- `AGENTS.md` is the dense agent startup page with red lines and evidence rules.
- `CLAUDE.md` is a legacy compatibility entrypoint and must defer to `AGENTS.md` on startup-role wording.
- `README_FOR_AGENT.md` is the explanatory onboarding guide.
- `PROJECT_STATE.md` is the canonical truth source for checked-in facts, blockers, and currently accepted evidence.
- `CANONICAL_RUNBOOK.md` is the exact command and failure-routing source.

Recommended read order for a new agent:
1. `README_FOR_AGENT.md`
2. `PROJECT_STATE.md`
3. `CANONICAL_RUNBOOK.md`
4. `README.md` when you need broader developer context

## Directory Map

- `src/enhengclaw/core`: execution control and runtime rules
- `src/enhengclaw/agents`: governed slices and review surfaces
- `src/enhengclaw/orchestration`: shadow acceptance, runtime orchestration, and readiness helpers
- `src/enhengclaw/quant_research`: research-platform pipelines, governance, promotion, and workbench export
- `scripts/verify`: formal verification and deployment gates
- `tests`: repository test suite
- `config/agent_layer_governance`: machine-readable agent-layer governance state
- `config/agent_architecture`: owner topology contract
- `config/project_governance`: project identity and stage contracts
- `config/quant_research`: validation contracts (`validation_contract.json` for h5d, `validation_contract_h10d.json` for sqrt-scaled h10d), the h10d promotion guard (`promotion_gate_h10d.json`), plus full quant research audit lineage at `threshold_provenance.md`
- `docs/agents/OWNER_AGENT_ARCHITECTURE.md`: persistent owner-control-plane design note
- `docs/quant_research/`: quant research roadmap, evidence archive, and governance indexes
  - `quant_research_roadmap_state_2026_05_12.md`: read-this-first current roadmap map. It separates the active Binance-only PIT h10d frontier from historical branch evidence.
  - `00_roadmap_state/quant_research_script_catalog.md`: script entrypoint catalog. Check it before running, moving, or adding quant-research scripts.
  - `00_roadmap_state/research_doc_governance_index.md`: static-contract index for newly added quant-research Markdown.
  - `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md`: latest active Binance-only PIT h10d validation report.
  - `01_data_foundation/`: provider registry, market-data inventory, CoinGlass/Deribit/onchain foundation docs, and data-sponsorship plans.
  - `03_alpha_branches/`: quarantined or closed alpha branch evidence. Use these as historical mechanism evidence unless the roadmap explicitly reopens a branch.
  - `04_parallel_1h/`: separate 1h manipulation/mechanical-flow lane. Do not merge it into the h10d mainline without an independently admitted survivor.
  - `05_historical_archive/`: stale evidence retained for audit history.
  - `00_roadmap_state/data_utilization_roadmap.md`, `factor_audit_trail.md`, `experiment_catalog.md`, `algorithm_choices.md`, and `alpha_ontology_and_factor_library.md`: historical spine, cross-cutting catalogs, and mechanism/factor ontology. They are not first-read current-state entrypoints unless the roadmap points back to them.
  - `mechanism_notes/MF_*.md`: per-mechanism-family deep dives for preregistration and interpretation, not promotion evidence by themselves.

## Dual-Track Rules

- The research platform may call into the governance/runtime framework.
- The framework track must not depend back on quant research, scheduled-task glue, or workbench-specific logic.
- Broad/agent/execution manifest unlocks follow `config/project_governance/stage_contract.json`; they do not auto-advance because a readiness script passes.
- Research-to-workbench export must pass through a governance-produced `promotion_decision` artifact; mutable alpha/status files alone are not sufficient export authority.
- Quant bridge publication follows `config/quant_research/publication_contract.json`: Stage 0/1 are archive-only, live backend outputs may become publishable only after promotion-decision, hash/freshness, backend-mode, validation, and bridge-contract gates pass, and deterministic outputs remain non-publishable.

## Current Owner State

- The checked-in owner topology contract exists and names exactly one owner: `rulebook_owner`.
- `config/project_governance/runtime_ownership_contract.json` is the machine source for runtime ownership phase and owner-verification enforcement.
- Current checked-in runtime ownership contract state is `runtime_ownership_phase = partial`, `owner_verification_required = true`, and `owner_verification_enforced_in_boundary_gates = true`.
- `market_observer` and `evidence_agent` are shipped write surfaces, while six compatibility delegates still share the legacy `runtime.continue_existing_from_agent_payloads` boundary. Boundary gates now enforce owner-first verification before finalization, but the owner topology is still a convergence target rather than proof that migration is complete.

## Stage Model

- `Stage 0`: sandbox/framework-only
- `Stage 1`: research/readiness only
- `Stage 2`: manual export + human review
- `Stage 3`: human-approved execution
- `Stage 4`: automated execution

Current checked-in state is `Stage 4: Automated Execution`. Stage 4 satisfies the stage-contract minimum for automated-execution review, but broad rollout and order authority still require separate manifest, owner, on-host, budget, and live-order gates and remain fail-closed until those contracts are satisfied.

## Glossary

- `preflight-only`: the admission stage that writes fixed evidence under `<ArtifactsRoot>\preflight_only\<PreflightLabel>\` and decides whether rerun may start.
- `all_green`: `preflight_assertions.json.all_green = true`; this is the only rerun admission signal.
- `rerun`: the real execution stage launched after a green preflight-only stage.
- `soak`: the retained rerun evidence bundle under `<ArtifactsRoot>\soak_runs\<RerunLabel>\`.
- `shadow`: the real-provider shadow monitoring path rather than the research-only or replay-only paths.
- `governed slice`: one bounded agent lane that writes through existing runtime ingress and governance controls.
- `rulebook_owner`: the single checked-in owner of the governed control plane.
- `review surface`: a read-only inspection lane attached to a governed slice.

## Artifact Vocabulary

- `<ArtifactsRoot>` means the operator-supplied root for the formal real-24h bundle only.
- `RunArtifactsRoot` means a generated per-run root for owner, review, demo, or readiness flows.
- `ObjectArtifactsRoot` means a generated per-object root for research workbenches and other persistent bounded objects.
- `promotion_decision artifact` means the governance-produced approval record under `RunArtifactsRoot\governance\promotion_decisions\<as_of>\` that binds an exportable alpha to hashes, freshness, and source commit metadata.

Important: repo-local `artifacts\...` paths are examples of generated output. They are not a guarantee that a fresh checkout already contains those directories.

Examples:
- Repo-local real-24h example: `artifacts\controlled_shadow_soak\soak_runs\...`
- Repo-local owner example: `artifacts\review_probe_market\agent_owner\...`
- Repo-local research example: `artifacts\research_workbench\<object_id>\...`

## Operator Host Assumption

- The current operator-facing workflow assumes one Windows workstation plus WSL.
- `%LOCALAPPDATA%` stores retained bundles and generated external inputs.
- `C:\ProgramData\EnhengClaw\trust` is the expected read-only trust-root boundary.
- Linux/macOS CI helps catch static drift and install drift, but it does not certify cross-platform operator deployment.

## Real-24h Facts That Matter

- The real-24h permit floor is `86460.0`, which means `24h + 60s`.
- `1800.0` still exists as a non-real default margin in shorter or non-real flows, but it must never become the real-24h floor.
- A rerun shell `exit_code = 0` is necessary but not sufficient for pass.
- The real decision boundary is the retained verdict bundle, not chat history and not a wrapper exit code alone.

Authoritative real-24h verdict files:
- `<ArtifactsRoot>\soak_runs\<RerunLabel>\go_no_go.json`
- `<ArtifactsRoot>\soak_runs\<RerunLabel>\soak_summary.json`
- `<ArtifactsRoot>\soak_runs\<RerunLabel>\provider_health_snapshot.json`
- `<ArtifactsRoot>\soak_runs\<RerunLabel>\audit_record.json`

## Failure Routing

When real-24h preflight is red:
1. Read `preflight_assertions.json`.
2. Identify which required assertions are false.
3. Read `preflight_result.json` for preflight stage status and provider check results.
4. Read `provider_health_snapshot.json` for retained provider health details.
5. If Binance preflight failed, preserve and report the structured Binance diagnostics fields exactly.

When `<RerunLabel> == <PreflightLabel>`:
1. Treat it as operator input error.
2. Do not overwrite evidence.
3. Choose a new rerun label and restart from the formal bundle.

When `<ArtifactsRoot>\soak_runs\<RerunLabel>` already exists:
1. Treat it as an evidence-collision failure.
2. Do not reuse or overwrite that directory for a new decision.
3. Either inspect it as a past run or choose a fresh rerun label.

When rerun exit code is non-zero:
1. Read `<ArtifactsRoot>\real_24h_bundles\<RerunLabel>\rerun_stage.json`.
2. Inspect `rerun.stdout.log` and `rerun.stderr.log`.
3. Then inspect the retained rerun verdict files if they exist.
4. Report that shell failure is red by itself and never a pass.

When rerun exit code is zero but verdict is red:
1. Read `go_no_go.json`.
2. Read `soak_summary.json`.
3. Read `provider_health_snapshot.json`.
4. Read `audit_record.json`.
5. Treat this as a verdict failure; the exit code does not override retained evidence.

## Docs Versus Retained Evidence

Use docs to answer:
- what the project is
- which files are authoritative
- what commands exist
- what the current checked-in governance state is

Use retained evidence to answer:
- whether one specific preflight was green
- whether one specific rerun passed
- whether `READY_FOR_AGENT_LAYER` or `READY_FOR_BROAD_AGENT_LAYER` was actually green for a run
- what the latest accepted live validation bundle proves
