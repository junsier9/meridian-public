from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def main() -> int:
    commands = [
        (
            "governed-agent ingress public cli acceptance",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_governed_agent_ingress_cli",
            ],
        ),
        (
            "governed-agent ingress direct slice acceptance",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_market_observer_slice",
                "tests.acceptance.test_market_observer_execution_path",
                "tests.acceptance.test_evidence_agent_execution_path",
                "tests.acceptance.test_pending_slice_execution_path",
                "tests.acceptance.test_risk_signal_agent_pending",
                "tests.acceptance.test_risk_governance_agent_pending",
                "tests.acceptance.test_validation_agent_pending",
                "tests.acceptance.test_attention_allocator_pending",
                "tests.acceptance.test_research_synthesizer_pending",
                "tests.acceptance.test_research_lead_pending",
                "tests.acceptance.test_rulebook_agent_team",
            ],
        ),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[governed-agent-ingress] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[governed-agent-ingress] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[governed-agent-ingress] PASS {label}")
    print("[governed-agent-ingress] ALL GATES PASSED")
    return 0


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


if __name__ == "__main__":
    raise SystemExit(main())
