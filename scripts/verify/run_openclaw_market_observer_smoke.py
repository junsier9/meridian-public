from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path, PureWindowsPath
import shlex
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.compat.naming import getenv_compat, materialize_env_alias, pop_env_aliases
from enhengclaw.integrations.openclaw.market_observer import OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "market_observer"
RECORDED_WSL_SMOKE = "/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_market_observer_recorded.sh"
LIVE_WSL_SMOKE = "/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_market_observer_live.sh"
WSL_AUDIT = "/root/.openclaw/workspace-meridian-alpha-audit/tools/audit_market_observer_response.sh"
LIVE_REQUIRED_ENV = (
    "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL",
    "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME",
    "ENHENGCLAW_MARKET_OBSERVER_API_KEY",
)
LIVE_OPTIONAL_WSL_PASSTHROUGH_ENV = ("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT",)
RECORDED_ENV_TO_SCRUB = (
    *LIVE_REQUIRED_ENV,
    "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT",
    "ENHENGCLAW_TRUST_ROOT_DIR",
    "ENHENGCLAW_LEASE_REGISTRY_PATH",
    "ENHENGCLAW_RUNTIME_SESSION_ROOT",
    "ENHENGCLAW_WORKER_LEASE_ID",
    "ENHENGCLAW_WORKER_MODE",
    "ENHENGCLAW_WORKER_PERMIT_PATH",
)
STAGE_PREFLIGHT = "live_preflight"
STAGE_RECORDED = "recorded_gate"
STAGE_HOST = "host_live_adapter_smoke"
STAGE_WSL = "workspace_live_smoke"
STAGE_AUDIT = "workspace_live_audit"


class SmokeFailure(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the canonical OpenClaw deployment smoke for the market_observer lane."
    )
    parser.add_argument(
        "--live-smoke",
        action="store_true",
        help="After the recorded gate passes, run one explicit host+WSL live deployment proof.",
    )
    parser.add_argument(
        "--execution-permit",
        type=Path,
        help="Explicit external execution permit path required when --live-smoke is set.",
    )
    parser.add_argument(
        "--trust-root-dir",
        type=Path,
        help="Optional trust-root directory forwarded as ENHENGCLAW_TRUST_ROOT_DIR during live smoke.",
    )
    parser.add_argument(
        "--retain-root",
        type=Path,
        help="Optional root directory for retained live-smoke evidence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    recorded_env = _build_recorded_env()
    env = _build_env(trust_root_dir=args.trust_root_dir)

    live_context: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    if args.live_smoke:
        live_context = _prepare_live_context(
            execution_permit_path=args.execution_permit,
            trust_root_dir=args.trust_root_dir,
            env=env,
            retain_root=args.retain_root,
        )
        summary = live_context["summary"]
        if summary["stages"][STAGE_PREFLIGHT]["status"] != "passed":
            _print_live_failure(
                label=STAGE_PREFLIGHT,
                message=summary["stages"][STAGE_PREFLIGHT]["message"],
                retain_root=Path(summary["retain_root"]),
            )
            return int(summary["stages"][STAGE_PREFLIGHT]["exit_code"])

    recorded_exit = _run_recorded_gate(recorded_env)
    if recorded_exit != 0:
        if summary is not None:
            _set_stage(summary, STAGE_RECORDED, status="failed", exit_code=recorded_exit, message="recorded gate failed")
            _finalize_live_summary(summary=summary, overall_status="failed")
            _write_live_summary(summary)
            _write_failure_snapshot(
                retain_root=Path(summary["retain_root"]),
                stage_label=STAGE_RECORDED,
                error="recorded gate failed",
                env=env,
                execution_permit_path=live_context.get("execution_permit_path"),
                trust_root_dir=live_context.get("trust_root_dir"),
                paths=live_context["paths"],
                summary=summary,
            )
            _print_live_failure(
                label=STAGE_RECORDED,
                message="recorded gate failed",
                retain_root=Path(summary["retain_root"]),
            )
        return recorded_exit
    if summary is None:
        print("[openclaw-market-observer] ALL GATES PASSED")
        return 0

    _set_stage(summary, STAGE_RECORDED, status="passed", exit_code=0, message="recorded gate passed")
    live_exit = _run_live_proof(env=env, live_context=live_context)
    if live_exit != 0:
        return live_exit
    print("[openclaw-market-observer] ALL GATES PASSED")
    return 0


def _run_recorded_gate(env: dict[str, str]) -> int:
    commands = [
        (
            "openclaw market_observer unit and acceptance tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "-q",
                "-b",
                "tests.test_openclaw_market_observer",
                "tests.acceptance.test_openclaw_market_observer_deployment_path",
            ],
        ),
    ]
    for label, command in commands:
        print(f"[openclaw-market-observer] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        if completed.returncode != 0:
            print(f"[openclaw-market-observer] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[openclaw-market-observer] PASS {label}")

    print("[openclaw-market-observer] START workspace recorded smoke")
    smoke = subprocess.run(
        ["wsl.exe", "bash", "-lc", RECORDED_WSL_SMOKE],
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if smoke.returncode != 0:
        _print_completed_process(smoke)
        print(f"[openclaw-market-observer] FAIL workspace recorded smoke (exit={smoke.returncode})")
        return smoke.returncode
    if smoke.stdout:
        print(smoke.stdout.rstrip())
    print("[openclaw-market-observer] PASS workspace recorded smoke")
    return 0


def _run_live_proof(*, env: dict[str, str], live_context: dict[str, Any]) -> int:
    summary = live_context["summary"]
    paths = live_context["paths"]
    retain_root = Path(summary["retain_root"])

    print(f"[openclaw-market-observer] START {_stage_failure_message(STAGE_HOST)}")
    host_completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from enhengclaw.integrations.openclaw.market_observer import main as _main; "
                "raise SystemExit(_main())"
            ),
            "--request",
            str(paths["host_request_path"]),
            "--response",
            str(paths["host_response_path"]),
        ],
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    _write_text(paths["host_stdout_path"], host_completed.stdout)
    _write_text(paths["host_stderr_path"], host_completed.stderr)
    if host_completed.returncode != 0:
        message = _stage_failure_message(STAGE_HOST, completed=host_completed)
        if not paths["host_response_path"].exists():
            _write_live_failure_response(
                paths["host_response_path"],
                error=message,
                artifacts_root=paths["host_artifacts_root"],
            )
        _set_stage(summary, STAGE_HOST, status="failed", exit_code=host_completed.returncode, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_HOST,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            completed=host_completed,
            summary=summary,
        )
        _print_completed_process(host_completed)
        _print_live_failure(label=STAGE_HOST, message=message, retain_root=retain_root)
        return host_completed.returncode or 1
    _print_completed_process(host_completed)
    try:
        host_payload = _load_json(paths["host_response_path"])
        assert_market_observer_artifact_chain(host_payload)
    except Exception as exc:
        message = _stage_failure_message(STAGE_HOST, error=str(exc))
        _set_stage(summary, STAGE_HOST, status="failed", exit_code=1, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_HOST,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            summary=summary,
        )
        _print_live_failure(label=STAGE_HOST, message=message, retain_root=retain_root)
        return 1
    summary["host_response_path"] = str(paths["host_response_path"])
    _set_stage(summary, STAGE_HOST, status="passed", exit_code=0, message="host live adapter finalized successfully")
    _write_live_summary(summary)
    print(f"[openclaw-market-observer] PASS {_stage_failure_message(STAGE_HOST)}")

    wsl_env = env.copy()
    wsl_exports = [
        f"{name}={shlex.quote(str(env[name]))}"
        for name in LIVE_REQUIRED_ENV
        if str(env.get(name, "")).strip()
    ]
    wsl_exports.extend(
        f"{name}={shlex.quote(str(env[name]))}"
        for name in LIVE_OPTIONAL_WSL_PASSTHROUGH_ENV
        if str(env.get(name, "")).strip()
    )
    if live_context.get("wsl_trust_root_dir"):
        wsl_exports.append(
            f"ENHENGCLAW_TRUST_ROOT_DIR={shlex.quote(str(live_context['wsl_trust_root_dir']))}"
        )
    wsl_command = " ".join(
        (
            *wsl_exports,
            shlex.quote(LIVE_WSL_SMOKE),
            shlex.quote(str(live_context["wsl_permit_path"])),
            shlex.quote(str(live_context["wsl_artifacts_path"])),
        )
    )
    print(f"[openclaw-market-observer] START {_stage_failure_message(STAGE_WSL)}")
    wsl_completed = subprocess.run(
        ["wsl.exe", "bash", "-lc", wsl_command],
        check=False,
        cwd=ROOT,
        env=wsl_env,
        capture_output=True,
        text=True,
    )
    _write_text(paths["wsl_stdout_path"], wsl_completed.stdout)
    _write_text(paths["wsl_stderr_path"], wsl_completed.stderr)
    if wsl_completed.returncode != 0:
        message = _stage_failure_message(STAGE_WSL, completed=wsl_completed)
        if not paths["wsl_response_path"].exists():
            _write_live_failure_response(
                paths["wsl_response_path"],
                error=message,
                artifacts_root=paths["wsl_artifacts_root"],
            )
        _set_stage(summary, STAGE_WSL, status="failed", exit_code=wsl_completed.returncode, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_WSL,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            completed=wsl_completed,
            summary=summary,
        )
        _print_completed_process(wsl_completed)
        _print_live_failure(label=STAGE_WSL, message=message, retain_root=retain_root)
        return wsl_completed.returncode or 1
    _print_completed_process(wsl_completed)
    try:
        wsl_wrapper_summary = _load_json_from_output(wsl_completed.stdout)
        _write_json(paths["wsl_wrapper_summary_path"], wsl_wrapper_summary)
        wsl_payload = _load_json(paths["wsl_response_path"])
        assert_market_observer_artifact_chain(wsl_payload)
    except Exception as exc:
        message = _stage_failure_message(STAGE_WSL, error=str(exc))
        _set_stage(summary, STAGE_WSL, status="failed", exit_code=1, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_WSL,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            summary=summary,
        )
        _print_live_failure(label=STAGE_WSL, message=message, retain_root=retain_root)
        return 1
    summary["wsl_response_path"] = str(paths["wsl_response_path"])
    summary["final_output_path"] = wsl_payload.get("final_output_path")
    summary["runtime_session_path"] = wsl_payload.get("runtime_session_path")
    _set_stage(summary, STAGE_WSL, status="passed", exit_code=0, message="workspace live smoke finalized successfully")
    _write_live_summary(summary)
    print(f"[openclaw-market-observer] PASS {_stage_failure_message(STAGE_WSL)}")

    audit_command = " ".join((shlex.quote(WSL_AUDIT), shlex.quote(str(live_context["wsl_response_path"]))))
    print(f"[openclaw-market-observer] START {_stage_failure_message(STAGE_AUDIT)}")
    audit_completed = subprocess.run(
        ["wsl.exe", "bash", "-lc", audit_command],
        check=False,
        cwd=ROOT,
        env=wsl_env,
        capture_output=True,
        text=True,
    )
    _write_text(paths["audit_stdout_path"], audit_completed.stdout)
    _write_text(paths["audit_stderr_path"], audit_completed.stderr)
    if audit_completed.returncode != 0:
        message = _stage_failure_message(STAGE_AUDIT, completed=audit_completed)
        _set_stage(summary, STAGE_AUDIT, status="failed", exit_code=audit_completed.returncode, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_AUDIT,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            completed=audit_completed,
            summary=summary,
        )
        _print_completed_process(audit_completed)
        _print_live_failure(label=STAGE_AUDIT, message=message, retain_root=retain_root)
        return audit_completed.returncode or 1
    _print_completed_process(audit_completed)
    try:
        audit_summary = _load_json_from_output(audit_completed.stdout)
        _write_json(paths["audit_summary_path"], audit_summary)
        _assert_audit_summary(audit_summary)
    except Exception as exc:
        message = _stage_failure_message(STAGE_AUDIT, error=str(exc))
        _set_stage(summary, STAGE_AUDIT, status="failed", exit_code=1, message=message)
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        _write_failure_snapshot(
            retain_root=retain_root,
            stage_label=STAGE_AUDIT,
            error=message,
            env=env,
            execution_permit_path=live_context["execution_permit_path"],
            trust_root_dir=live_context["trust_root_dir"],
            paths=paths,
            summary=summary,
        )
        _print_live_failure(label=STAGE_AUDIT, message=message, retain_root=retain_root)
        return 1
    summary["audit_result"] = audit_summary.get("status")
    summary["audit_summary_path"] = str(paths["audit_summary_path"])
    _set_stage(summary, STAGE_AUDIT, status="passed", exit_code=0, message="workspace live audit passed")
    _finalize_live_summary(summary=summary, overall_status="success")
    _write_live_summary(summary)
    print(f"[openclaw-market-observer] PASS {_stage_failure_message(STAGE_AUDIT)}")
    print(
        json.dumps(
            _compact_summary(summary),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _build_env(*, trust_root_dir: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    _set_pythonpath(env)
    if trust_root_dir is not None:
        materialize_env_alias(env, "ENHENGCLAW_TRUST_ROOT_DIR", str(trust_root_dir.resolve()))
    for name in LIVE_REQUIRED_ENV:
        value = str(getenv_compat(name, "", env=env) or "").strip()
        if value:
            materialize_env_alias(env, name, value)
    for name in LIVE_OPTIONAL_WSL_PASSTHROUGH_ENV:
        value = str(getenv_compat(name, "", env=env) or "").strip()
        if value:
            materialize_env_alias(env, name, value)
    return env


def _build_recorded_env() -> dict[str, str]:
    env = os.environ.copy()
    _set_pythonpath(env)
    for name in RECORDED_ENV_TO_SCRUB:
        pop_env_aliases(env, name)
    return env


def _set_pythonpath(env: dict[str, str]) -> None:
    pythonpath_parts = [str(ROOT), str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)


def missing_live_env(env: dict[str, str]) -> list[str]:
    return [name for name in LIVE_REQUIRED_ENV if not str(getenv_compat(name, "", env=env) or "").strip()]


def windows_path_to_wsl(path: str | Path) -> str:
    text = str(path)
    if text.startswith("/mnt/"):
        return text
    windows = PureWindowsPath(text)
    if not windows.drive or len(windows.drive) != 2 or not windows.drive[0].isalpha():
        raise ValueError(
            f"OpenClaw live smoke requires a Windows local-drive path convertible to /mnt/<drive>/..., got: {text}"
        )
    drive = windows.drive[0].lower()
    tail = "/".join(windows.parts[1:])
    if tail:
        return f"/mnt/{drive}/{tail}"
    return f"/mnt/{drive}"


def assert_market_observer_artifact_chain(payload: dict[str, Any]) -> None:
    if payload.get("status") != "success":
        raise SmokeFailure(f"expected status=success, got {payload.get('status')!r}")
    if payload.get("run_state") != "FINALIZED":
        raise SmokeFailure(f"expected run_state=FINALIZED, got {payload.get('run_state')!r}")
    accepted_signal_ids = payload.get("accepted_signal_ids") or []
    if not accepted_signal_ids:
        raise SmokeFailure("expected non-empty accepted_signal_ids")
    final_output_path = _coerce_platform_path(payload.get("final_output_path"))
    runtime_session_path = _coerce_platform_path(payload.get("runtime_session_path"))
    compiler_artifact_paths = [
        coerced
        for coerced in (_coerce_platform_path(item) for item in (payload.get("compiler_artifact_paths") or []))
        if coerced is not None
    ]
    if final_output_path is None or not final_output_path.exists():
        raise SmokeFailure(f"missing final output artifact: {payload.get('final_output_path')!r}")
    if runtime_session_path is None or not runtime_session_path.exists():
        raise SmokeFailure(f"missing runtime session artifact: {payload.get('runtime_session_path')!r}")
    if not compiler_artifact_paths:
        raise SmokeFailure("expected compiler_artifact_paths to be non-empty")
    missing = [str(path) for path in compiler_artifact_paths if not path.exists()]
    if missing:
        raise SmokeFailure(f"missing compiler artifacts: {missing}")


def _assert_audit_summary(summary: dict[str, Any]) -> None:
    if summary.get("status") != "success":
        raise SmokeFailure(f"audit expected status=success, got {summary.get('status')!r}")
    if summary.get("run_state") != "FINALIZED":
        raise SmokeFailure(f"audit expected run_state=FINALIZED, got {summary.get('run_state')!r}")
    for field in ("compiler_artifacts_exist", "runtime_session_exists", "final_output_exists"):
        if summary.get(field) is not True:
            raise SmokeFailure(f"audit expected {field}=true, got {summary.get(field)!r}")
    if summary.get("review_gate_consistent") is False:
        raise SmokeFailure("audit reported inconsistent review gate artifacts")


def _prepare_live_context(
    *,
    execution_permit_path: Path | None,
    trust_root_dir: Path | None,
    env: dict[str, str],
    retain_root: Path | None,
) -> dict[str, Any]:
    resolved_retain_root = _resolve_retain_root(retain_root)
    paths = _live_paths(resolved_retain_root)
    for directory in (paths["host_root"], paths["wsl_root"], paths["host_artifacts_root"], paths["wsl_artifacts_root"]):
        directory.mkdir(parents=True, exist_ok=True)
    summary = _initial_live_summary(paths)

    if execution_permit_path is None:
        message = "live smoke requires --execution-permit <path>"
        _set_stage(summary, STAGE_PREFLIGHT, status="failed", exit_code=2, message=message)
        _write_failure_snapshot(
            retain_root=resolved_retain_root,
            stage_label=STAGE_PREFLIGHT,
            error=message,
            env=env,
            execution_permit_path=None,
            trust_root_dir=trust_root_dir,
            paths=paths,
        )
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        return {"summary": summary, "paths": paths}

    resolved_permit_path = execution_permit_path.resolve()
    if not resolved_permit_path.exists() or not resolved_permit_path.is_file():
        message = f"live smoke execution permit file does not exist: {resolved_permit_path}"
        _set_stage(summary, STAGE_PREFLIGHT, status="failed", exit_code=1, message=message)
        _write_failure_snapshot(
            retain_root=resolved_retain_root,
            stage_label=STAGE_PREFLIGHT,
            error=message,
            env=env,
            execution_permit_path=resolved_permit_path,
            trust_root_dir=trust_root_dir,
            paths=paths,
        )
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        return {"summary": summary, "paths": paths}

    resolved_trust_root_dir = None if trust_root_dir is None else trust_root_dir.resolve()
    if resolved_trust_root_dir is not None and (not resolved_trust_root_dir.exists() or not resolved_trust_root_dir.is_dir()):
        message = f"live smoke trust-root directory does not exist: {resolved_trust_root_dir}"
        _set_stage(summary, STAGE_PREFLIGHT, status="failed", exit_code=1, message=message)
        _write_failure_snapshot(
            retain_root=resolved_retain_root,
            stage_label=STAGE_PREFLIGHT,
            error=message,
            env=env,
            execution_permit_path=resolved_permit_path,
            trust_root_dir=resolved_trust_root_dir,
            paths=paths,
        )
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        return {"summary": summary, "paths": paths}

    fixture = _load_success_fixture()
    host_payload = _build_live_request_payload(
        fixture=fixture,
        execution_permit_path=str(resolved_permit_path),
        artifacts_root=paths["host_artifacts_root"],
        input_id="openclaw-market-observer-live-host:1",
    )
    _write_json(paths["host_request_path"], host_payload)

    try:
        wsl_permit_path = windows_path_to_wsl(resolved_permit_path)
        wsl_artifacts_path = windows_path_to_wsl(paths["wsl_artifacts_root"])
        wsl_response_path = windows_path_to_wsl(paths["wsl_response_path"])
        wsl_trust_root = None if resolved_trust_root_dir is None else windows_path_to_wsl(resolved_trust_root_dir)
    except Exception as exc:
        message = str(exc)
        _write_live_failure_response(paths["host_response_path"], error=message, artifacts_root=paths["host_artifacts_root"])
        _write_live_failure_response(paths["wsl_response_path"], error=message, artifacts_root=paths["wsl_artifacts_root"])
        _set_stage(summary, STAGE_PREFLIGHT, status="failed", exit_code=1, message=message)
        _write_failure_snapshot(
            retain_root=resolved_retain_root,
            stage_label=STAGE_PREFLIGHT,
            error=message,
            env=env,
            execution_permit_path=resolved_permit_path,
            trust_root_dir=resolved_trust_root_dir,
            paths=paths,
        )
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        return {"summary": summary, "paths": paths}

    wsl_payload = _build_live_request_payload(
        fixture=fixture,
        execution_permit_path=wsl_permit_path,
        artifacts_root=wsl_artifacts_path,
        input_id="openclaw-market-observer-live-wsl:1",
    )
    _write_json(paths["wsl_request_path"], wsl_payload)

    missing_env = missing_live_env(env)
    if missing_env:
        message = "OpenClaw market_observer live smoke requires environment variables: " + ", ".join(missing_env)
        _write_live_failure_response(paths["host_response_path"], error=message, artifacts_root=paths["host_artifacts_root"])
        _write_live_failure_response(paths["wsl_response_path"], error=message, artifacts_root=paths["wsl_artifacts_root"])
        _set_stage(summary, STAGE_PREFLIGHT, status="failed", exit_code=1, message=message)
        _write_failure_snapshot(
            retain_root=resolved_retain_root,
            stage_label=STAGE_PREFLIGHT,
            error=message,
            env=env,
            execution_permit_path=resolved_permit_path,
            trust_root_dir=resolved_trust_root_dir,
            paths=paths,
        )
        _finalize_live_summary(summary=summary, overall_status="failed")
        _write_live_summary(summary)
        return {"summary": summary, "paths": paths}

    _set_stage(summary, STAGE_PREFLIGHT, status="passed", exit_code=0, message="live preflight passed")
    _write_live_summary(summary)
    return {
        "summary": summary,
        "paths": paths,
        "execution_permit_path": resolved_permit_path,
        "trust_root_dir": resolved_trust_root_dir,
        "wsl_permit_path": wsl_permit_path,
        "wsl_artifacts_path": wsl_artifacts_path,
        "wsl_response_path": wsl_response_path,
        "wsl_trust_root_dir": wsl_trust_root,
    }


def _live_paths(retain_root: Path) -> dict[str, Path]:
    host_root = retain_root / "host_live"
    wsl_root = retain_root / "wsl_live"
    return {
        "retain_root": retain_root,
        "summary_path": retain_root / "live_smoke_summary.json",
        "failure_snapshot_path": retain_root / "failure_snapshot.json",
        "host_root": host_root,
        "host_request_path": host_root / "request.json",
        "host_response_path": host_root / "response.json",
        "host_artifacts_root": host_root / "artifacts",
        "host_stdout_path": host_root / "stdout.log",
        "host_stderr_path": host_root / "stderr.log",
        "wsl_root": wsl_root,
        "wsl_request_path": wsl_root / "request.json",
        "wsl_response_path": wsl_root / "response.json",
        "wsl_artifacts_root": wsl_root / "artifacts",
        "wsl_stdout_path": wsl_root / "stdout.log",
        "wsl_stderr_path": wsl_root / "stderr.log",
        "wsl_wrapper_summary_path": wsl_root / "wrapper_summary.json",
        "audit_summary_path": wsl_root / "audit_summary.json",
        "audit_stdout_path": wsl_root / "audit_stdout.log",
        "audit_stderr_path": wsl_root / "audit_stderr.log",
    }


def _initial_live_summary(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "overall_status": "pending",
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "completed_at_utc": None,
        "retain_root": str(paths["retain_root"]),
        "summary_path": str(paths["summary_path"]),
        "host_response_path": str(paths["host_response_path"]),
        "wsl_response_path": str(paths["wsl_response_path"]),
        "final_output_path": None,
        "runtime_session_path": None,
        "audit_result": None,
        "audit_summary_path": str(paths["audit_summary_path"]),
        "stages": {
            key: {
                "label": _stage_failure_message(key),
                "status": "pending",
                "exit_code": None,
                "message": None,
            }
            for key in (STAGE_PREFLIGHT, STAGE_RECORDED, STAGE_HOST, STAGE_WSL, STAGE_AUDIT)
        },
    }


def _set_stage(
    summary: dict[str, Any],
    stage_key: str,
    *,
    status: str,
    exit_code: int | None,
    message: str | None,
) -> None:
    summary["stages"][stage_key] = {
        "label": _stage_failure_message(stage_key),
        "status": status,
        "exit_code": exit_code,
        "message": message,
    }


def _finalize_live_summary(*, summary: dict[str, Any], overall_status: str) -> None:
    summary["overall_status"] = overall_status
    summary["completed_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_live_summary(summary: dict[str, Any]) -> None:
    _write_json(Path(summary["summary_path"]), summary)


def _print_live_failure(*, label: str, message: str, retain_root: Path) -> None:
    print(
        f"[openclaw-market-observer] FAIL {_stage_failure_message(label)}: {message}\n"
        f"[openclaw-market-observer] retained evidence: {retain_root}"
    )


def _load_success_fixture() -> dict[str, Any]:
    return _load_json(FIXTURE_ROOT / "success" / "input.json")


def _build_live_request_payload(
    *,
    fixture: dict[str, Any],
    execution_permit_path: str,
    artifacts_root: Path | str,
    input_id: str,
) -> dict[str, Any]:
    return {
        "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
        "subject": fixture["subject"],
        "scope": fixture["scope"],
        "object_id": fixture["object_id"],
        "observation_text": fixture["observation_text"],
        "execution_permit_path": execution_permit_path,
        "input_id": input_id,
        "compiler_backend": "live",
        "artifacts_root": str(artifacts_root),
    }


def _resolve_retain_root(retain_root: Path | None) -> Path:
    if retain_root is None:
        return Path(tempfile.mkdtemp(prefix="enhengclaw_openclaw_market_observer_live_")).resolve()
    resolved = retain_root.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_status": summary["overall_status"],
        "retain_root": summary["retain_root"],
        "summary_path": summary["summary_path"],
        "host_response_path": summary["host_response_path"],
        "wsl_response_path": summary["wsl_response_path"],
        "final_output_path": summary["final_output_path"],
        "runtime_session_path": summary["runtime_session_path"],
        "audit_result": summary["audit_result"],
        "stages": {
            key: {
                "label": value["label"],
                "status": value["status"],
                "exit_code": value["exit_code"],
                "message": value["message"],
            }
            for key, value in summary["stages"].items()
        },
    }


def _write_live_failure_response(path: Path, *, error: str, artifacts_root: Path) -> None:
    payload = {
        "accepted_signal_ids": [],
        "artifacts_root": str(artifacts_root),
        "blocked_reason": None,
        "compiler_artifact_paths": [],
        "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
        "error": error,
        "execution_status": None,
        "final_output_path": None,
        "owner_run_id": None,
        "quarantine_reason": None,
        "run_state": "FAILED",
        "runtime_session_path": None,
        "spec_version": None,
        "status": "failed",
    }
    _write_json(path, payload)


def _write_failure_snapshot(
    *,
    retain_root: Path,
    stage_label: str,
    error: str,
    env: dict[str, str],
    execution_permit_path: Path | None,
    trust_root_dir: Path | None,
    paths: dict[str, Path],
    completed: subprocess.CompletedProcess[str] | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    snapshot = {
        "stage_label": _stage_failure_message(stage_label),
        "error": error,
        "retain_root": str(retain_root),
        "execution_permit_path": None if execution_permit_path is None else str(execution_permit_path),
        "trust_root_dir": None if trust_root_dir is None else str(trust_root_dir),
        "required_live_env": {name: bool(str(env.get(name, "")).strip()) for name in LIVE_REQUIRED_ENV},
        "host_request_path": str(paths["host_request_path"]),
        "host_response_path": str(paths["host_response_path"]),
        "wsl_request_path": str(paths["wsl_request_path"]),
        "wsl_response_path": str(paths["wsl_response_path"]),
        "summary_path": str(paths["summary_path"]),
        "failure_snapshot_path": str(paths["failure_snapshot_path"]),
        "summary": None if summary is None else _compact_summary(summary),
    }
    if completed is not None:
        snapshot["returncode"] = completed.returncode
        snapshot["stdout_path"] = _stage_stdout_path(paths, stage_label)
        snapshot["stderr_path"] = _stage_stderr_path(paths, stage_label)
    _write_json(paths["failure_snapshot_path"], snapshot)


def _stage_failure_message(
    stage_key: str,
    *,
    completed: subprocess.CompletedProcess[str] | None = None,
    error: str | None = None,
) -> str:
    labels = {
        STAGE_PREFLIGHT: "live env preflight",
        STAGE_RECORDED: "recorded gate",
        STAGE_HOST: "host live adapter smoke",
        STAGE_WSL: "workspace live smoke",
        STAGE_AUDIT: "workspace live audit",
    }
    label = labels.get(stage_key, stage_key)
    if error:
        return error
    if completed is None:
        return label
    detail = completed.stderr.strip() or completed.stdout.strip()
    if detail:
        return detail
    return f"{label} failed"


def _print_completed_process(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)


def _coerce_platform_path(value: str | None) -> Path | None:
    if value in {None, ""}:
        return None
    text = str(value)
    if text.startswith("/mnt/") and len(text) > 7 and text[5].isalpha() and text[6] == "/":
        drive = text[5].upper()
        suffix = text[7:].replace("/", "\\")
        return Path(f"{drive}:\\{suffix}")
    return Path(text)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_from_output(output: str) -> dict[str, Any]:
    text = output.strip()
    if not text:
        raise SmokeFailure("expected machine-readable JSON output, got empty stdout")
    return json.loads(text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _stage_stdout_path(paths: dict[str, Path], stage_label: str) -> str | None:
    mapping = {
        STAGE_HOST: paths["host_stdout_path"],
        STAGE_WSL: paths["wsl_stdout_path"],
        STAGE_AUDIT: paths["audit_stdout_path"],
    }
    path = mapping.get(stage_label)
    return None if path is None else str(path)


def _stage_stderr_path(paths: dict[str, Path], stage_label: str) -> str | None:
    mapping = {
        STAGE_HOST: paths["host_stderr_path"],
        STAGE_WSL: paths["wsl_stderr_path"],
        STAGE_AUDIT: paths["audit_stderr_path"],
    }
    path = mapping.get(stage_label)
    return None if path is None else str(path)


if __name__ == "__main__":
    raise SystemExit(main())
