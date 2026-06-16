from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
DEMO = ROOT / "examples" / "governed_agent_ingress_demo.py"
SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "market_observer" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the model-backed market_observer execution slice.")
    parser.add_argument("--live-smoke", action="store_true", help="Run one explicit live backend smoke if env vars are present.")
    args = parser.parse_args(argv)

    commands = [
        (
            "market_observer execution unit tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_market_observer_execution",
                "tests.test_owner_state",
            ],
        ),
        (
            "market_observer execution acceptance tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.acceptance.test_market_observer_execution_path",
                "tests.acceptance.test_governed_agent_ingress_cli",
            ],
        ),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[market-observer-execution] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[market-observer-execution] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[market-observer-execution] PASS {label}")

    if args.live_smoke:
        live_result = _run_live_smoke(env)
        if live_result != 0:
            return live_result

    print("[market-observer-execution] ALL GATES PASSED")
    return 0


def _run_live_smoke(env: dict[str, str]) -> int:
    required = [
        "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL",
        "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME",
        "ENHENGCLAW_MARKET_OBSERVER_API_KEY",
    ]
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        print("[market-observer-execution] SKIP live smoke (missing " + ", ".join(missing) + ")")
        return 0
    fixture = json.loads(SUCCESS_INPUT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="ecgd_live_") as tmpdir:
        command = [
            sys.executable,
            str(DEMO),
            "market_observer",
            "--artifacts-root",
            tmpdir,
            "--object-id",
            str(fixture["object_id"]),
            "--subject",
            str(fixture["subject"]),
            "--scope",
            str(fixture["scope"]),
            "--observation-text",
            str(fixture["observation_text"]),
            "--compiler-backend",
            "live",
        ]
        print("[market-observer-execution] START live smoke")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env, capture_output=True, text=True)
        if completed.returncode != 0:
            print(completed.stderr)
            print(f"[market-observer-execution] FAIL live smoke (exit={completed.returncode})")
            return completed.returncode
        payload = json.loads(completed.stdout)
        if payload.get("compiler_backend") != "live":
            print("[market-observer-execution] FAIL live smoke (compiler_backend != live)")
            return 1
        if not payload.get("compiler_artifact_paths"):
            print("[market-observer-execution] FAIL live smoke (missing compiler artifacts)")
            return 1
        print("[market-observer-execution] PASS live smoke")
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
