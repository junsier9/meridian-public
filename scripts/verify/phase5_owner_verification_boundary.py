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
            "owner-first finalized write persists verification",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_rulebook_agent_team.RulebookAgentArchitectureAcceptanceTests."
                "test_owner_first_evidence_write_finalizes_and_persists_nested_artifacts",
            ],
        ),
        (
            "missing required review blocks finalization",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_rulebook_agent_team.RulebookAgentArchitectureAcceptanceTests."
                "test_missing_required_review_record_blocks_final_output",
            ],
        ),
        (
            "missing verification item fails closed",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_rulebook_agent_team.RulebookAgentArchitectureAcceptanceTests."
                "test_missing_verification_item_generates_blocked_final_output",
            ],
        ),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[owner-verification-boundary] START {label}")
        completed = subprocess.run(
            command,
            check=False,
            cwd=ROOT,
            env=env,
        )
        if completed.returncode != 0:
            print(f"[owner-verification-boundary] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[owner-verification-boundary] PASS {label}")
    print("[owner-verification-boundary] ALL GATES PASSED")
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
