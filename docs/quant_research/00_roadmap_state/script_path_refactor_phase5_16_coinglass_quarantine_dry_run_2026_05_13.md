# Phase 5.16 CoinGlass Quarantine Script Path Dry-Run

`Status: dry-run decision artifact`
`Date: 2026-05-13`
`Scope: CoinGlass quarantined R-lane and spot-concordance quarantine scripts`

## Decision

Move the two CoinGlass quarantine implementations into a narrow directory:

- `scripts/quant_research/coinglass_quarantine/`

Keep the old root paths as thin CLI/module compatibility shims. This is a
low-medium risk implementation batch because the target semantics are narrow,
no scheduled/config strong references were found, and the two scripts are
already cataloged as quarantined evidence rather than current default
entrypoints.

Do not move CoinGlass sync pipelines, CoinGlass diagnostics, provider
capability probes, or h10d-parent historical scripts in this phase.

## Candidate Files

| current root path | target implementation path | catalog status | run priority | wrapper |
| --- | --- | --- | --- | --- |
| `scripts/quant_research/run_coinglass_r1a_top_liquidity_ex_trx_strict.py` | `scripts/quant_research/coinglass_quarantine/run_coinglass_r1a_top_liquidity_ex_trx_strict.py` | `quarantined` | `quarantined_falsification` | yes |
| `scripts/quant_research/write_coinglass_spot_concordance_quarantine.py` | `scripts/quant_research/coinglass_quarantine/write_coinglass_spot_concordance_quarantine.py` | `quarantined` | `quarantined_falsification` | yes |

## Reference Audit

Search command:

```powershell
rg -n "run_coinglass_r1a_top_liquidity_ex_trx_strict|write_coinglass_spot_concordance_quarantine" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
```

Findings:

- No `config/`, scheduled-task manifest, PowerShell runner, or test strong
  reference was found.
- Non-catalog references are documentation/governance references:
  - `docs/quant_research/00_roadmap_state/script_path_refactor_completion_control_plan_2026_05_13.md`
  - `docs/quant_research/00_roadmap_state/script_path_refactor_remaining_root_dry_run_2026_05_13.md`
  - `docs/quant_research/00_roadmap_state/worktree_staging_plan_2026-05-07.md`
- Roadmap evidence still belongs to CoinGlass foundation / R-lane history:
  - `docs/quant_research/01_data_foundation/coinglass_full_stack_data_research_roadmap.md`
  - `docs/quant_research/03_alpha_branches/research_priority_update_full_stack.md`
- `scripts/quant_research/coinglass_diagnostics/write_coinglass_coverage_reset_report.py`
  references the generated quarantine artifact path, not the old script path.

## Import Audit

- `run_coinglass_r1a_top_liquidity_ex_trx_strict.py` imports helper functions
  from root-level `run_coinglass_h10d_parent_frozen_reset_strict.py`.
- That h10d-parent script remains root-level in this phase. Do not move it as
  part of CoinGlass quarantine cleanup.
- `write_coinglass_spot_concordance_quarantine.py` has no sibling script import
  and exposes `main(argv)`.

Wrapper strategy:

- Use root re-export shims, not CLI-only wrappers, so external root-module
  imports remain compatible.
- Forward `main()` through the moved module:
  - both implementations expose `main(argv: list[str] | None = None) -> int`;
  - root shims can call `_IMPL.main()` under `if __name__ == "__main__"`.

## Required Implementation Updates

- Create `scripts/quant_research/coinglass_quarantine/`.
- Move exactly the two candidate implementation files.
- Change moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`.
- Keep two root shims with:
  - repo-root `sys.path` injection;
  - `import_module("scripts.quant_research.coinglass_quarantine.<name>")`;
  - `globals().update(...)` re-export for module compatibility;
  - `raise SystemExit(_IMPL.main())` for CLI compatibility.
- Update:
  - `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`;
  - `scripts/quant_research/README.md`;
  - `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`.

## Boundaries

Do not move in this phase:

- `scripts/quant_research/run_coinglass_h10d_parent_frozen_reset_strict.py`;
- CoinGlass sync/default entrypoints;
- CoinGlass diagnostic scripts already under `coinglass_diagnostics/`;
- provider capability probes already under `provider_probes/`;
- h10d current-line or historical h10d scripts.

## Verification

```powershell
python -m compileall -q scripts\quant_research\coinglass_quarantine scripts\quant_research\run_coinglass_r1a_top_liquidity_ex_trx_strict.py scripts\quant_research\write_coinglass_spot_concordance_quarantine.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_coinglass_r1a_top_liquidity_ex_trx_strict.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\write_coinglass_spot_concordance_quarantine.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Run the local Markdown link checker because this dry-run, README, checklist,
and catalog are documentation surfaces.
