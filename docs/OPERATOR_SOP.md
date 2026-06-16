# EnhengClaw Operator SOP

This SOP covers only the live execution surface after execution-boundary convergence.

## Canonical Lane

- Controller inputs are serialized `ProviderSourceSpec` values.
- Providers and adapters are materialized inside the runtime worker.
- The runtime kernel remains `RuntimeOrchestrator.run_new`.
- The maintained operator entrypoints are `PilotRunner` and `BatchPilotRunner`.
- `runtime_worker_harness` is a low-level test helper, not an operator entrypoint.

## Replay Smoke Commands

Single-symbol replay:

```powershell
cd C:\Users\user\Documents\Claude\Projects\EnhengClaw
python examples\pilot_runner_demo.py --symbol AIX --scope spot+perp
```

Batch replay:

```powershell
cd C:\Users\user\Documents\Claude\Projects\EnhengClaw
python examples\batch_pilot_runner_demo.py AIX BTC ETH --scope spot+perp
```

Both commands:

- default to a temporary self-issued execution permit via `execution_testbed()`
- accept `--execution-permit <path>` when an external permit and trust root are already configured
- write provider-selection, raw-payload, normalized-signal, runtime, and ops artifacts
- keep the batch demo under `C:\ecpb\...` by default on Windows to avoid long-path failures
- emit one batch root per symbol when the demo self-provisions permits for multiple symbols

Optional live record run:

```powershell
cd C:\Users\user\Documents\Claude\Projects\EnhengClaw
$env:ENABLE_REAL_CEX_PROVIDER='1'
python examples\batch_pilot_runner_demo.py BTC ETH --scope spot+perp --use-live
```

## Artifact Checks

Single pilot runs write under `artifacts\pilot_runs\...`.

Check each run for:

- `provider_selection_result.json`
- `raw\`
- `normalized_signal_summary.json`
- `runtime_result.json`
- `ops_report.json`
- `warnings_errors.json`

The public batch demo writes under `C:\ecpb\...` by default on Windows. The library-level `BatchPilotRunner` still defaults to `artifacts\pilot_batches\...`.

Check each batch for:

- `batch_summary.json`
- per-run `archive_path`
- per-run `decision`
- per-run warnings and errors

## Verification Commands

Run the repository baseline:

```powershell
cd C:\Users\user\Documents\Claude\Projects\EnhengClaw
python -m unittest discover -s tests -p "test*.py"
python scripts\verify\run_boundary_gates.py
python scripts\verify\run_operational_readiness.py
python scripts\redteam\final_boundary_acceptance.py
```

## Archived Surface

Do not treat the following as the operator path:

- `examples/legacy/*`
- `examples/runtime_demo.py`
- `examples/runtime_batch_demo.py`
- `examples/scenario_cases.py`
- `examples/snapshot_adapter_demo.py`
- retired controller APIs such as `run_new_from_adapters` and `run_new_from_provider_bindings`
