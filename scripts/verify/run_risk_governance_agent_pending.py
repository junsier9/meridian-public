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
            "risk_governance_agent promoted public acceptance",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_risk_governance_agent_pending",
            ],
        ),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[risk-governance-pending] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[risk-governance-pending] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[risk-governance-pending] PASS {label}")
    print("[risk-governance-pending] ALL GATES PASSED")
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
