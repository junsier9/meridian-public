from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


VERIFY_DIR = Path(__file__).resolve().parent
ROOT = VERIFY_DIR.parents[1]
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

from enhengclaw.compat.naming import env_aliases, materialize_env_alias
from run_operational_readiness import build_sanitized_env


PASS_THROUGH_ENV = ("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", "OPENCLAW", "ENHENGCLAW_TEST_REVIEW_OVERRIDE")


def build_parser(*, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--execution-permit", type=Path, required=True)
    parser.add_argument("--trust-root-dir", type=Path, default=None)
    parser.add_argument("--retain-root", type=Path, default=None)
    return parser


def run_live_readiness_bundle(
    *,
    bundle_id: str,
    bundle_label: str,
    lane_ids: tuple[str, ...],
    execution_permit: Path,
    trust_root_dir: Path | None = None,
    retain_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_retain_root = _prepare_retain_root(retain_root, prefix=f"{bundle_id}_")
    summary = {
        "bundle_id": bundle_id,
        "bundle_label": bundle_label,
        "status": "pending",
        "retain_root": str(resolved_retain_root),
        "generated_at_utc": _utc_now(),
        "completed_at_utc": None,
        "lane_results": {},
        "failing_lane": None,
        "failing_stage": None,
        "exit_code": 1,
    }
    env = _build_env(base_env=base_env)

    for lane_id in lane_ids:
        lane_root = _prepare_lane_retain_root(bundle_id=bundle_id, lane_id=lane_id)
        lane_result = _run_lane_live_gate(
            lane_id=lane_id,
            execution_permit=execution_permit,
            trust_root_dir=trust_root_dir,
            retain_root=lane_root,
            env=env,
        )
        summary["lane_results"][lane_id] = lane_result
        _write_json(resolved_retain_root / "bundle_summary.json", summary)
        if lane_result["status"] != "passed":
            summary["status"] = "failed"
            summary["completed_at_utc"] = _utc_now()
            summary["failing_lane"] = lane_id
            summary["failing_stage"] = lane_result.get("failing_stage")
            summary["exit_code"] = int(lane_result["exit_code"])
            _write_json(resolved_retain_root / "bundle_summary.json", summary)
            return summary

    summary["status"] = "success"
    summary["completed_at_utc"] = _utc_now()
    summary["exit_code"] = 0
    _write_json(resolved_retain_root / "bundle_summary.json", summary)
    return summary


def _build_env(*, base_env: dict[str, str] | None) -> dict[str, str]:
    env = build_sanitized_env(base_env=base_env)
    source_env = os.environ if base_env is None else base_env
    for name in PASS_THROUGH_ENV:
        value = next((source_env[alias] for alias in env_aliases(name) if alias in source_env), None)
        if value is not None:
            materialize_env_alias(env, name, value)
    return env


def _run_lane_live_gate(
    *,
    lane_id: str,
    execution_permit: Path,
    trust_root_dir: Path | None,
    retain_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "bundle_stdout.log"
    stderr_path = retain_root / "bundle_stderr.log"
    result_path = retain_root / "bundle_result.json"
    summary_path = retain_root / "live_smoke_summary.json"
    command = [
        sys.executable,
        str(VERIFY_DIR / f"run_openclaw_{lane_id}_smoke.py"),
        "--live-smoke",
        "--execution-permit",
        str(execution_permit),
        "--retain-root",
        str(retain_root),
    ]
    if trust_root_dir is not None:
        command.extend(["--trust-root-dir", str(trust_root_dir)])
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    live_summary = _safe_load_json(summary_path)
    result = {
        "lane_id": lane_id,
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "live_summary": live_summary,
        "failing_stage": _extract_live_failure_stage(live_summary),
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, result)
    return result


def _extract_live_failure_stage(live_summary: dict[str, Any] | None) -> str | None:
    if not isinstance(live_summary, dict):
        return None
    stages = live_summary.get("stages")
    if not isinstance(stages, dict):
        return None
    for stage_key, stage_value in stages.items():
        if not isinstance(stage_value, dict):
            continue
        if stage_value.get("status") == "failed":
            label = stage_value.get("label")
            if isinstance(label, str) and label.strip():
                return label
            return stage_key
    return None


def _prepare_retain_root(retain_root: Path | None, *, prefix: str) -> Path:
    if retain_root is not None:
        retain_root.mkdir(parents=True, exist_ok=True)
        return retain_root.resolve()
    return Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def _lane_retain_slug(lane_id: str) -> str:
    return {
        "evidence_agent": "ea",
        "risk_signal_agent": "rsa",
        "attention_allocator": "aa",
        "research_synthesizer": "rs",
        "research_lead": "rl",
        "risk_governance_agent": "rga",
        "validation_agent": "va",
    }.get(lane_id, lane_id)


def _prepare_lane_retain_root(*, bundle_id: str, lane_id: str) -> Path:
    short_root = _short_temp_root()
    prefix = f"{_lane_retain_slug(lane_id)}_"
    if short_root is not None:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=short_root)).resolve()
    return Path(tempfile.mkdtemp(prefix=f"{bundle_id}_{prefix}")).resolve()


def _short_temp_root() -> str | None:
    candidates: list[Path] = []
    if os.name == "nt":
        temp_drive = Path(tempfile.gettempdir()).drive or Path.cwd().drive
        if temp_drive:
            candidates.append(Path(f"{temp_drive}\\e"))
    candidates.append(Path(tempfile.gettempdir()) / "e")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(candidate)
    return None


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["build_parser", "run_live_readiness_bundle"]
