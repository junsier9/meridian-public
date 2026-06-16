# Contributing to Meridian Alpha Platform

Thanks for your interest! A few things to know up front.

## This is a sanitized public mirror

This repository is a **sanitized public mirror** of a private quant-trading platform. Fitted alpha weights,
research artifacts, live operational logs, real infrastructure, and account data are redacted or excluded
(see [`PUBLIC_MIRROR.md`](PUBLIC_MIRROR.md)). As a result:

- It is published to share the **engineering and architecture**, not to run a live strategy as-is.
- Pull requests are welcome for **code quality, documentation, tests, portability, and tooling**.
- PRs that try to reconstruct or add real trading parameters/alpha will not be merged.

## Development setup

```bash
git clone https://github.com/junsier9/meridian-public
cd meridian-public
python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate on Linux/macOS
pip install -e .
```

Runtime floor is intentionally small: Python 3.13 + `numpy`, `pandas`, `scikit-learn`, `websockets`
(declared in `pyproject.toml`).

## Running the checks

The CI gates that must stay green are in [`.github/workflows/boundary-gates.yml`](.github/workflows/boundary-gates.yml):

```bash
# static / document / dependency / evidence contracts
python -m unittest tests.test_document_contracts tests.test_static_contracts tests.test_evidence_contracts

# quant research core
python -m unittest tests.test_quant_research_core tests.test_quant_shadow_proposals

# clean-install dependency contract
python scripts/verify/run_dependency_contract.py
```

Run the full suite with `python -m unittest discover -s tests`.

## House rules

- **Fail-closed by default.** New runtime paths should refuse to act when preconditions are missing, not
  guess. Tests encode these boundaries — keep them.
- **Don't grow the dependency floor silently.** If you need a new runtime dependency, add it to
  `pyproject.toml`; the dependency-contract gate enforces this.
- **Contracts are computed, not hand-edited.** Don't edit checked-in contract/evidence files to make a test
  pass — fix the code or the contract definition.
- **No secrets, ever.** Credentials come from environment variables (see [`.env.example`](.env.example)).
  Never commit keys, tokens, hosts, or real balances.
- Match the surrounding code style; keep changes focused and add tests for new behavior.

## Reporting issues

Open a GitHub issue with a clear description and, where relevant, a minimal reproduction. Security-sensitive
reports: please open a private advisory rather than a public issue.
