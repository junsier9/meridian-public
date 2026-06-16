from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "quant_research" / "bootstrap_quant_runtime.py"
SCIENTIFIC_IMPORT_SMOKE = "import numpy, pandas, sklearn"


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    return (repo_root or ROOT).expanduser().resolve()


def resolve_repo_venv_python(repo_root: Path | None = None) -> Path:
    resolved_repo_root = resolve_repo_root(repo_root)
    if sys.platform.startswith("win"):
        return resolved_repo_root / ".venv" / "Scripts" / "python.exe"
    return resolved_repo_root / ".venv" / "bin" / "python"


def scientific_stack_status(repo_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = resolve_repo_root(repo_root)
    venv_python = resolve_repo_venv_python(resolved_repo_root)
    if not venv_python.exists():
        return {
            "status": "scientific_python_runtime_missing",
            "ready": False,
            "reason": "venv_missing",
            "repo_root": str(resolved_repo_root),
            "venv_python": str(venv_python),
            "bootstrap_script": str(BOOTSTRAP_SCRIPT),
        }
    result = subprocess.run(
        [str(venv_python), "-c", SCIENTIFIC_IMPORT_SMOKE],
        cwd=str(resolved_repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return {
            "status": "success",
            "ready": True,
            "reason": "scientific_stack_ready",
            "repo_root": str(resolved_repo_root),
            "venv_python": str(venv_python),
            "bootstrap_script": str(BOOTSTRAP_SCRIPT),
        }
    return {
        "status": "scientific_python_runtime_missing",
        "ready": False,
        "reason": "scientific_stack_import_failed",
        "repo_root": str(resolved_repo_root),
        "venv_python": str(venv_python),
        "bootstrap_script": str(BOOTSTRAP_SCRIPT),
        "stderr": result.stderr.strip(),
    }


def bootstrap_quant_runtime(*, repo_root: Path | None = None, check_only: bool = False) -> dict[str, Any]:
    resolved_repo_root = resolve_repo_root(repo_root)
    venv_python = resolve_repo_venv_python(resolved_repo_root)
    created_venv = False
    installed_editable = False
    commands: list[list[str]] = []

    if not venv_python.exists() and not check_only:
        subprocess.run([sys.executable, "-m", "venv", str(resolved_repo_root / ".venv")], cwd=str(resolved_repo_root), check=True)
        created_venv = True

    if venv_python.exists() and not check_only:
        upgrade_cmd = [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"]
        install_cmd = [str(venv_python), "-m", "pip", "install", "-e", "."]
        subprocess.run(upgrade_cmd, cwd=str(resolved_repo_root), check=True)
        subprocess.run(install_cmd, cwd=str(resolved_repo_root), check=True)
        commands.extend([upgrade_cmd, install_cmd])
        installed_editable = True

    smoke = scientific_stack_status(resolved_repo_root)
    summary = {
        "status": smoke["status"],
        "success": bool(smoke["ready"]),
        "mode": "check_only" if check_only else "bootstrap",
        "repo_root": str(resolved_repo_root),
        "venv_python": str(venv_python),
        "bootstrap_script": str(BOOTSTRAP_SCRIPT),
        "created_venv": created_venv,
        "installed_editable": installed_editable,
        "scientific_stack_ready": bool(smoke["ready"]),
        "reason": smoke["reason"],
        "commands": commands,
    }
    if smoke.get("stderr"):
        summary["stderr"] = smoke["stderr"]
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap or verify the repo-local quant scientific runtime.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--check-only", action="store_true", help="Only validate the repo .venv scientific stack; do not create or install anything.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = bootstrap_quant_runtime(repo_root=args.repo_root, check_only=args.check_only)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["success"] else 1
