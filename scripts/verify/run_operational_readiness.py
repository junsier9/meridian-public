from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.compat.naming import env_aliases, materialize_env_alias
from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.core.execution_control import snapshot_execution_lease_registry
FORCED_KILL_TEST = (
    "tests.test_operational_readiness."
    "IngestionOperationalReadinessTests."
    "test_ingestion_worker_forced_kill_allows_orphan_cleanup_and_restart"
)
HEARTBEAT_LOSS_TEST = (
    "tests.test_operational_readiness."
    "IngestionOperationalReadinessTests."
    "test_ingestion_heartbeat_loss_fail_closed"
)
DEFAULT_FORCED_KILL_RECOVERY_REPEATS = 3
DEFAULT_HEARTBEAT_LOSS_REPEATS = 3
STATEFUL_ENV_VARS_TO_SCRUB = (
    "ENHENGCLAW_TEST_REVIEW_OVERRIDE",
    "ENHENGCLAW_WORKER_TEST_HOOK_JSON",
    "ENHENGCLAW_LEASE_REGISTRY_PATH",
    "ENHENGCLAW_OPERATIONAL_AUDIT_ROOT",
    "ENHENGCLAW_TRUST_ROOT_DIR",
    "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT",
    "ENHENGCLAW_RUNTIME_SESSION_ROOT",
    "ENHENGCLAW_WORKER_MODE",
    "ENHENGCLAW_WORKER_LEASE_ID",
    "ENHENGCLAW_WORKER_PERMIT_PATH",
)


@dataclass(slots=True)
class CommandResult:
    label: str
    command: list[str]
    returncode: int
    stdout_path: str
    stderr_path: str
    result_path: str


@dataclass(slots=True)
class AttemptResult:
    attempt_index: int
    status: str
    exit_code: int
    attempt_root: str
    attempt_context_path: str
    attempt_summary_path: str
    failure_snapshot_path: str | None
    step_results: list[CommandResult]


@dataclass(slots=True)
class OperationalReadinessRunResult:
    exit_code: int
    attempts_requested: int
    attempts_completed: int
    retain_root: str
    summary_path: str
    attempts: list[AttemptResult]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the operational readiness gate with retained attempt evidence.")
    parser.add_argument("--attempts", type=int, default=1, help="Number of full operational-readiness attempts to require.")
    parser.add_argument(
        "--retain-root",
        type=Path,
        default=None,
        help="Optional root directory used to retain per-attempt stdout/stderr, JSON summaries, and soak artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.attempts < 1:
        raise SystemExit("--attempts must be >= 1")

    result = run_operational_readiness(
        attempts=args.attempts,
        retain_root=args.retain_root,
    )
    print(f"[operational-readiness] retain_root={result.retain_root}")
    print(f"[operational-readiness] summary={result.summary_path}")
    return result.exit_code


def run_operational_readiness(
    *,
    attempts: int = 1,
    retain_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    forced_kill_repeats: int = DEFAULT_FORCED_KILL_RECOVERY_REPEATS,
    heartbeat_loss_repeats: int = DEFAULT_HEARTBEAT_LOSS_REPEATS,
) -> OperationalReadinessRunResult:
    resolved_retain_root = _prepare_retain_root(retain_root)
    results: list[AttemptResult] = []
    exit_code = 0
    for attempt_index in range(1, attempts + 1):
        attempt_result = _run_single_attempt(
            attempt_index=attempt_index,
            retain_root=resolved_retain_root,
            base_env=base_env,
            forced_kill_repeats=forced_kill_repeats,
            heartbeat_loss_repeats=heartbeat_loss_repeats,
        )
        results.append(attempt_result)
        if attempt_result.exit_code != 0:
            exit_code = attempt_result.exit_code
            break

    completed = len(results)
    summary_path = resolved_retain_root / "operational_readiness_summary.json"
    summary = with_evidence_metadata(
        {
        "status": "passed" if exit_code == 0 and completed == attempts else "failed",
        "attempts_requested": attempts,
        "attempts_completed": completed,
        "retain_root": str(resolved_retain_root),
        "attempts": [_attempt_payload(item) for item in results],
        },
        evidence_family="operational_readiness",
        contract_version="operational_readiness.v1",
        repo_root=ROOT,
    )
    _write_json(summary_path, summary)
    if exit_code == 0 and completed != attempts:
        exit_code = 1
    return OperationalReadinessRunResult(
        exit_code=exit_code,
        attempts_requested=attempts,
        attempts_completed=completed,
        retain_root=str(resolved_retain_root),
        summary_path=str(summary_path),
        attempts=results,
    )


def build_child_env(
    *,
    attempt_root: Path,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = build_sanitized_env(base_env=base_env)
    state_root = attempt_root / "state"
    materialize_env_alias(env, "ENHENGCLAW_LEASE_REGISTRY_PATH", str(state_root / "execution-leases.sqlite3"))
    materialize_env_alias(env, "ENHENGCLAW_OPERATIONAL_AUDIT_ROOT", str(state_root / "operational_audit"))
    materialize_env_alias(env, "ENHENGCLAW_RUNTIME_SESSION_ROOT", str(state_root / "runtime_sessions"))
    return env


def build_sanitized_env(*, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    for name in STATEFUL_ENV_VARS_TO_SCRUB:
        for alias in env_aliases(name):
            env.pop(alias, None)

    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _run_single_attempt(
    *,
    attempt_index: int,
    retain_root: Path,
    base_env: dict[str, str] | None,
    forced_kill_repeats: int,
    heartbeat_loss_repeats: int,
) -> AttemptResult:
    attempt_root = retain_root / f"attempt-{attempt_index}"
    attempt_root.mkdir(parents=True, exist_ok=True)
    child_env = build_child_env(attempt_root=attempt_root, base_env=base_env)

    attempt_context_path = attempt_root / "attempt_context.json"
    attempt_summary_path = attempt_root / "attempt_summary.json"
    _write_json(
        attempt_context_path,
        {
            "attempt_index": attempt_index,
            "forced_kill_repeats": forced_kill_repeats,
            "heartbeat_loss_repeats": heartbeat_loss_repeats,
            "scrubbed_env_vars": list(STATEFUL_ENV_VARS_TO_SCRUB),
            "state_root": str(attempt_root / "state"),
            "lease_registry_path": child_env["ENHENGCLAW_LEASE_REGISTRY_PATH"],
            "operational_audit_root": child_env["ENHENGCLAW_OPERATIONAL_AUDIT_ROOT"],
            "runtime_session_root": child_env["ENHENGCLAW_RUNTIME_SESSION_ROOT"],
            "soak_artifacts_root": str(attempt_root / "short_soak_artifacts"),
            "pythonpath": child_env["PYTHONPATH"],
        },
    )

    step_results: list[CommandResult] = []
    for repeat_index in range(1, forced_kill_repeats + 1):
        result = _run_logged_command(
            label=f"forced_kill_recovery_repeat_{repeat_index}",
            command=[sys.executable, "-m", "unittest", FORCED_KILL_TEST],
            cwd=ROOT,
            env=child_env,
            output_root=attempt_root / f"forced_kill_recovery_repeat_{repeat_index}",
        )
        step_results.append(result)
        if result.returncode != 0:
            return _finalize_attempt(
                attempt_index=attempt_index,
                status="failed",
                exit_code=result.returncode,
                attempt_root=attempt_root,
                attempt_context_path=attempt_context_path,
                attempt_summary_path=attempt_summary_path,
                step_results=step_results,
                child_env=child_env,
            )

    for repeat_index in range(1, heartbeat_loss_repeats + 1):
        result = _run_logged_command(
            label=f"heartbeat_loss_repeat_{repeat_index}",
            command=[sys.executable, "-m", "unittest", HEARTBEAT_LOSS_TEST],
            cwd=ROOT,
            env=child_env,
            output_root=attempt_root / f"heartbeat_loss_repeat_{repeat_index}",
        )
        step_results.append(result)
        if result.returncode != 0:
            return _finalize_attempt(
                attempt_index=attempt_index,
                status="failed",
                exit_code=result.returncode,
                attempt_root=attempt_root,
                attempt_context_path=attempt_context_path,
                attempt_summary_path=attempt_summary_path,
                step_results=step_results,
                child_env=child_env,
            )

    full_suite = _run_logged_command(
        label="tests_test_operational_readiness",
        command=[sys.executable, "-m", "unittest", "tests.test_operational_readiness"],
        cwd=ROOT,
        env=child_env,
        output_root=attempt_root / "tests_test_operational_readiness",
    )
    step_results.append(full_suite)
    if full_suite.returncode != 0:
        return _finalize_attempt(
            attempt_index=attempt_index,
            status="failed",
            exit_code=full_suite.returncode,
            attempt_root=attempt_root,
            attempt_context_path=attempt_context_path,
            attempt_summary_path=attempt_summary_path,
            step_results=step_results,
            child_env=child_env,
        )

    duration_seconds = os.getenv("ENHENGCLAW_SHORT_SOAK_DURATION_SECONDS", "60").strip() or "60"
    soak = _run_logged_command(
        label="short_soak",
        command=[
            sys.executable,
            str(ROOT / "scripts" / "run_controlled_shadow_soak.py"),
            "--artifacts-root",
            str(attempt_root / "short_soak_artifacts"),
            "--duration-seconds",
            duration_seconds,
            "--label",
            "readiness-short",
            "--simulation-profile",
            "synthetic",
            "--synthetic-event-interval-seconds",
            "0.2",
            "--synthetic-quarantine-every",
            "15",
        ],
        cwd=ROOT,
        env=child_env,
        output_root=attempt_root / "short_soak",
    )
    step_results.append(soak)
    if soak.returncode != 0:
        return _finalize_attempt(
            attempt_index=attempt_index,
            status="failed",
            exit_code=soak.returncode,
            attempt_root=attempt_root,
            attempt_context_path=attempt_context_path,
            attempt_summary_path=attempt_summary_path,
            step_results=step_results,
            child_env=child_env,
        )

    return _finalize_attempt(
        attempt_index=attempt_index,
        status="passed",
        exit_code=0,
        attempt_root=attempt_root,
        attempt_context_path=attempt_context_path,
        attempt_summary_path=attempt_summary_path,
        step_results=step_results,
        child_env=child_env,
    )


def _run_logged_command(
    *,
    label: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    output_root: Path,
) -> CommandResult:
    output_root.mkdir(parents=True, exist_ok=True)
    stdout_path = output_root / "stdout.log"
    stderr_path = output_root / "stderr.log"
    result_path = output_root / "result.json"
    completed = subprocess.run(
        command,
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    _write_json(
        result_path,
        {
            "label": label,
            "command": command,
            "returncode": completed.returncode,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        },
    )
    return CommandResult(
        label=label,
        command=command,
        returncode=completed.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        result_path=str(result_path),
    )


def _finalize_attempt(
    *,
    attempt_index: int,
    status: str,
    exit_code: int,
    attempt_root: Path,
    attempt_context_path: Path,
    attempt_summary_path: Path,
    step_results: list[CommandResult],
    child_env: dict[str, str],
) -> AttemptResult:
    failure_snapshot_path: str | None = None
    if status != "passed":
        failure_snapshot = _build_failure_snapshot(
            attempt_root=attempt_root,
            child_env=child_env,
            failing_step=step_results[-1].label if step_results else "<unknown>",
        )
        snapshot_path = attempt_root / "failure_snapshot.json"
        _write_json(snapshot_path, failure_snapshot)
        failure_snapshot_path = str(snapshot_path)
    summary = {
        "attempt_index": attempt_index,
        "status": status,
        "exit_code": exit_code,
        "attempt_root": str(attempt_root),
        "attempt_context_path": str(attempt_context_path),
        "failure_snapshot_path": failure_snapshot_path,
        "step_results": [asdict(item) for item in step_results],
    }
    _write_json(attempt_summary_path, summary)
    return AttemptResult(
        attempt_index=attempt_index,
        status=status,
        exit_code=exit_code,
        attempt_root=str(attempt_root),
        attempt_context_path=str(attempt_context_path),
        attempt_summary_path=str(attempt_summary_path),
        failure_snapshot_path=failure_snapshot_path,
        step_results=step_results,
    )


def _prepare_retain_root(retain_root: Path | None) -> Path:
    if retain_root is not None:
        retain_root.mkdir(parents=True, exist_ok=True)
        return retain_root.resolve()
    return Path(tempfile.mkdtemp(prefix="enhengclaw_operational_readiness_")).resolve()


def _attempt_payload(result: AttemptResult) -> dict[str, Any]:
    return {
        "attempt_index": result.attempt_index,
        "status": result.status,
        "exit_code": result.exit_code,
        "attempt_root": result.attempt_root,
        "attempt_context_path": result.attempt_context_path,
        "attempt_summary_path": result.attempt_summary_path,
        "failure_snapshot_path": result.failure_snapshot_path,
        "step_results": [asdict(item) for item in result.step_results],
    }


def _build_failure_snapshot(
    *,
    attempt_root: Path,
    child_env: dict[str, str],
    failing_step: str,
) -> dict[str, Any]:
    state_root = attempt_root / "state"
    registry_path = Path(child_env["ENHENGCLAW_LEASE_REGISTRY_PATH"])
    audit_root = Path(child_env["ENHENGCLAW_OPERATIONAL_AUDIT_ROOT"])
    runtime_session_root = Path(child_env["ENHENGCLAW_RUNTIME_SESSION_ROOT"])
    latest_run_root, latest_audit_record = _latest_audit_snapshot(audit_root)
    return {
        "failing_step": failing_step,
        "state_env": {
            "ENHENGCLAW_LEASE_REGISTRY_PATH": str(registry_path),
            "ENHENGCLAW_OPERATIONAL_AUDIT_ROOT": str(audit_root),
            "ENHENGCLAW_RUNTIME_SESSION_ROOT": str(runtime_session_root),
        },
        "state_root": str(state_root),
        "lease_registry": snapshot_execution_lease_registry(registry_path=registry_path),
        "task_lock_snapshot": _task_lock_snapshot(audit_root),
        "latest_audit_run_root": None if latest_run_root is None else str(latest_run_root),
        "latest_controller_audit_record": latest_audit_record,
    }


def _latest_audit_snapshot(audit_root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    if not audit_root.exists():
        return None, None
    audit_candidates = list(audit_root.rglob("audit_record.json"))
    if not audit_candidates:
        return None, None
    latest = max(audit_candidates, key=lambda path: path.stat().st_mtime)
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        payload = None
    return latest.parent, payload


def _task_lock_snapshot(audit_root: Path) -> list[dict[str, Any]]:
    if not audit_root.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for path in sorted(audit_root.rglob("*.json")):
        if "locks" not in path.parts:
            continue
        payload: dict[str, Any] | None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = None
        snapshots.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "payload": payload,
            }
        )
    return snapshots


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
