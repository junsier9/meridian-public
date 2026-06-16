from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


IMPORT_TARGETS = (
    "enhengclaw",
    "meridian_alpha",
    "meridian_alpha.integrations.openclaw.market_observer",
    "enhengclaw.integrations.openclaw.market_observer",
    "enhengclaw.integrations.openclaw.evidence_agent",
    "enhengclaw.integrations.openclaw.risk_signal_agent",
    "enhengclaw.integrations.openclaw.risk_governance_agent",
    "enhengclaw.integrations.openclaw.validation_agent",
    "enhengclaw.integrations.openclaw.attention_allocator",
    "enhengclaw.integrations.openclaw.research_synthesizer",
    "enhengclaw.integrations.openclaw.research_lead",
)

HELP_COMMANDS = (
    [sys.executable, "scripts/verify/run_real_24h_shadow_bundle.py", "--help"],
    [sys.executable, "scripts/verify/run_openclaw_deployment_readiness.py", "--help"],
    [sys.executable, "scripts/verify/run_real_shadow_acceptance.py", "--help"],
    [sys.executable, "scripts/openclaw/provision_market_observer_live_inputs.py", "--help"],
    [sys.executable, "scripts/openclaw/run_market_observer_deployment_gate.py", "--help"],
    [sys.executable, "-m", "enhengclaw.integrations.openclaw.market_observer", "--help"],
    [sys.executable, "-m", "meridian_alpha.integrations.openclaw.market_observer", "--help"],
)


def main() -> int:
    summary = run_dependency_contract()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


def run_dependency_contract() -> dict[str, Any]:
    import_results = [_import_target(name) for name in IMPORT_TARGETS]
    help_results = [_run_help_command(command) for command in HELP_COMMANDS]
    all_results = [*import_results, *help_results]
    status = "passed" if all(item["status"] == "passed" for item in all_results) else "failed"
    return {
        "status": status,
        "repo_root": str(ROOT),
        "imports": import_results,
        "help_commands": help_results,
    }


def _import_target(name: str) -> dict[str, Any]:
    try:
        importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        return {
            "type": "import",
            "target": name,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "type": "import",
        "target": name,
        "status": "passed",
    }


def _run_help_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "type": "help",
        "command": command,
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stderr": (completed.stderr or "").strip(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
