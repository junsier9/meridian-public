from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.orchestration.agent_layer_governance import all_agent_definitions


def main() -> int:
    commands = []
    for agent in all_agent_definitions():
        review_surface = agent.get("operator_review_surface")
        if not isinstance(review_surface, dict):
            continue
        if str(review_surface.get("surface_type", "")).strip() != "readonly_review":
            continue
        agent_id = str(agent["agent_id"])
        commands.append(
            (
                f"{agent_id} review demo acceptance",
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    f"tests.acceptance.test_{agent_id}_review_demo",
                ],
            )
        )
    env = _build_env()
    for label, command in commands:
        print(f"[rulebook-review-samples] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[rulebook-review-samples] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[rulebook-review-samples] PASS {label}")
    print("[rulebook-review-samples] ALL GATES PASSED")
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
