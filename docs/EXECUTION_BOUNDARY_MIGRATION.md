# Execution Boundary Migration

This note freezes the post-refactor execution surface.

## Canonical Surface Kept

- Runtime kernel: `RuntimeOrchestrator.run_new`
- Canonical source-backed lane: `ProviderSnapshotRunner.run_once`
- Controller-visible source description: `ProviderSourceSpec`
- Runtime tuning surface: `RuntimeExecutionProfile`
- Current high-level callers on the canonical lane:
  - `PilotRunner`
  - `BatchPilotRunner`
  - `ShadowPromotionRunner`
  - `ShadowAdmissionRunner`
  - `ContributionLedger`

## Retired Controller Surface

These APIs are kept only as blocked retirement surface and must not be used by new callers, tests, docs, or commands.

- `RuntimeOrchestrator.collect_adapter_batches`
- `RuntimeOrchestrator.run_new_from_adapters`
- `RuntimeOrchestrator.continue_existing_from_adapters`
- `RuntimeOrchestrator.collect_provider_batches`
- `RuntimeOrchestrator.run_new_from_provider_bindings`
- `RuntimeOrchestrator.continue_existing_from_provider_bindings`
- Controller-visible `ProviderRuntimeBinding` execution as the primary path

Retirement enforcement:

- `scripts/verify/phase4_legacy_api_retirement.py` asserts these controller calls stay blocked
- `scripts/verify/phase5_owner_verification_boundary.py` asserts owner verification is required before governed writes may finalize
- `scripts/verify/run_boundary_gates.py` includes the retirement gate, owner-verification boundary gate, and canonical-lane verification

## Promoted Commands

These are the public replay/operator smoke commands.

- `python examples\\pilot_runner_demo.py --symbol AIX --scope spot+perp`
- `python examples\\batch_pilot_runner_demo.py AIX BTC ETH --scope spot+perp`

Both commands:

- default to a self-provisioned temporary execution permit via `execution_testbed()`
- can use `--execution-permit <path>` when an external permit/trust-root pair is already available
- exercise the canonical `provider/snapshot -> runtime -> artifact` lane without `runtime_worker_harness`

## Archived Or Non-Canonical Surface

These files may still be useful for low-level kernel work or historical reference, but they are not the operator path.

- `examples/legacy/*`
- `examples/runtime_demo.py`
- `examples/runtime_batch_demo.py`
- `examples/scenario_cases.py`
- `examples/snapshot_adapter_demo.py`

Tests and verification were moved off the old controller surface:

- `tests/test_pilot_runner.py`
- `tests/test_batch_pilot_runner.py`
- `tests/test_runtime_ops_report.py`
- `tests/test_shadow_promotion.py`
- `tests/test_shadow_admission.py`
- `tests/test_shadow_contribution.py`
- `tests/test_agent_ingress_firewall.py`
- `tests/test_downstream_runtime_gate.py`

The legacy surface now survives only as retirement assertions, not as an executable happy path.
