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


def main_for_slice(
    *,
    argv: list[str] | None,
    slug: str,
    description: str,
    unit_target: str,
    acceptance_target: str,
    pending_target: str,
    fixture_input: Path,
    command_name: str,
    text_flag: str,
    text_key: str,
    required_env: tuple[str, str, str],
    public_acceptance_label: str = "public acceptance",
    expected_live_run_state: str = "BLOCKED",
    expect_public_runtime_session: bool = False,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--live-smoke", action="store_true", help="Run one explicit live backend smoke if env vars are present.")
    args = parser.parse_args(argv)

    commands = [
        (
            f"{command_name} execution unit tests",
            [sys.executable, "-m", "unittest", unit_target],
        ),
        (
            f"{command_name} execution acceptance tests",
            [sys.executable, "-m", "unittest", acceptance_target],
        ),
        (
            f"{command_name} {public_acceptance_label}",
            [sys.executable, "-m", "unittest", pending_target],
        ),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[{slug}] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[{slug}] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[{slug}] PASS {label}")

    if args.live_smoke:
        live_result = _run_live_smoke(
            slug=slug,
            env=env,
            fixture_input=fixture_input,
            command_name=command_name,
            text_flag=text_flag,
            text_key=text_key,
            required_env=required_env,
            expected_live_run_state=expected_live_run_state,
            expect_public_runtime_session=expect_public_runtime_session,
        )
        if live_result != 0:
            return live_result

    print(f"[{slug}] ALL GATES PASSED")
    return 0


def _run_live_smoke(
    *,
    slug: str,
    env: dict[str, str],
    fixture_input: Path,
    command_name: str,
    text_flag: str,
    text_key: str,
    required_env: tuple[str, str, str],
    expected_live_run_state: str,
    expect_public_runtime_session: bool,
) -> int:
    missing = [name for name in required_env if not env.get(name, "").strip()]
    if missing:
        print(f"[{slug}] SKIP live smoke (missing {', '.join(missing)})")
        return 0
    fixture = json.loads(fixture_input.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="ecgd_live_") as tmpdir:
        command = [
            sys.executable,
            str(DEMO),
            command_name,
            "--artifacts-root",
            tmpdir,
            "--object-id",
            str(fixture["object_id"]),
            "--subject",
            str(fixture["subject"]),
            "--scope",
            str(fixture["scope"]),
            text_flag,
            str(fixture[text_key]),
            "--compiler-backend",
            "live",
        ]
        print(f"[{slug}] START live smoke")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env, capture_output=True, text=True)
        if completed.returncode != 0:
            print(completed.stderr)
            print(f"[{slug}] FAIL live smoke (exit={completed.returncode})")
            return completed.returncode
        payload = json.loads(completed.stdout)
        if payload.get("compiler_backend") != "live":
            print(f"[{slug}] FAIL live smoke (compiler_backend != live)")
            return 1
        if not payload.get("compiler_artifact_paths"):
            print(f"[{slug}] FAIL live smoke (missing compiler artifacts)")
            return 1
        if payload.get("run_state") != expected_live_run_state:
            print(
                f"[{slug}] FAIL live smoke (expected run_state={expected_live_run_state}, "
                f"got {payload.get('run_state')})"
            )
            return 1
        has_session = payload.get("session_path") is not None
        if expect_public_runtime_session and not has_session:
            print(f"[{slug}] FAIL live smoke (expected public path to persist a runtime session)")
            return 1
        if not expect_public_runtime_session and has_session:
            print(f"[{slug}] FAIL live smoke (expected public path to avoid runtime mutation)")
            return 1
        print(f"[{slug}] PASS live smoke")
        return 0


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env
