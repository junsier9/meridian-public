from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run real-provider shadow acceptance tests, fault drills, or the full 24h acceptance package."
    )
    parser.add_argument(
        "--mode",
        choices=("verify", "tests", "fault-drills", "real-24h"),
        default="verify",
    )
    parser.add_argument("--artifacts-root", default=ROOT / "artifacts" / "real_shadow_acceptance", type=Path)
    parser.add_argument("--execution-permit", default=None)
    parser.add_argument("--label", default="real-shadow-acceptance")
    parser.add_argument("--duration-seconds", type=int, default=24 * 60 * 60)
    parser.add_argument("--clock-reference-url", default="https://api.binance.com/api/v3/time")
    parser.add_argument("--binance-websocket-url", default="wss://stream.binance.com:9443/ws")
    parser.add_argument("--alchemy-endpoint-url", default=None)
    parser.add_argument("--min-free-disk-mb", type=int, default=1024)
    parser.add_argument("--max-total-log-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--clock-skew-threshold-seconds", type=float, default=30.0)
    parser.add_argument("--provider-probe-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--min-permit-margin-seconds", type=float, default=(24 * 60 * 60) + 60.0)
    parser.add_argument("--allow-existing-label", action="store_true")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--drill", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "tests":
        return _run_tests()
    if args.mode == "fault-drills":
        return _run_fault_drills(args)
    if args.mode == "real-24h":
        return _run_real_24h(args)
    return _run_verify_bundle(args)


def _run_tests() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_real_shadow_acceptance",
        ],
        check=False,
        cwd=ROOT,
    )
    return completed.returncode


def _run_fault_drills(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    return _invoke_fault_drills(args=args, artifacts_root=artifacts_root)


def _run_verify_bundle(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    verify_root = (
        artifacts_root
        / "verify_runs"
        / f"{_sanitize_label(args.label)}-{_timestamp_token()}"
    )
    verify_root.mkdir(parents=True, exist_ok=True)

    tests_result = _run_stage_with_logs(
        stage_name="tests",
        command=[
            sys.executable,
            "-m",
            "unittest",
            "tests.test_real_shadow_acceptance",
        ],
        log_root=verify_root,
    )
    tests_result["summary"] = None

    retained_fault_drills_summary_path = verify_root / "fault_drills_summary.json"
    fault_drills_result: dict[str, object]
    if int(tests_result["exit_code"]) == 0:
        fault_drills_root = Path(tempfile.mkdtemp(prefix="enhengclaw_real_fault_drills_")) / "artifacts"
        fault_drills_result = _run_stage_with_logs(
            stage_name="fault_drills",
            command=_fault_drills_command(args=args, artifacts_root=fault_drills_root),
            log_root=verify_root,
        )
        fault_drills_result["artifacts_root"] = str(fault_drills_root.resolve())
        fault_drills_summary = _read_json_if_present(fault_drills_root / "fault_drills_summary.json")
        fault_drills_result["summary"] = _summarize_fault_drills_summary(fault_drills_summary)
        fault_drills_result["source_summary_path"] = str((fault_drills_root / "fault_drills_summary.json").resolve())
        fault_drills_result["summary_path"] = str(retained_fault_drills_summary_path.resolve())
        if fault_drills_summary is not None:
            retained_fault_drills_summary_path.write_text(
                json.dumps(fault_drills_summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        if int(fault_drills_result["exit_code"]) == 0 and fault_drills_summary is None:
            fault_drills_result["status"] = "failed"
            fault_drills_result["failure_reason"] = "fault_drills_summary_missing_or_invalid"
    else:
        fault_drills_result = {
            "stage_name": "fault_drills",
            "status": "skipped",
            "exit_code": None,
            "stdout_log": None,
            "stderr_log": None,
            "summary": None,
            "summary_path": str(retained_fault_drills_summary_path.resolve()),
            "failure_reason": "tests_failed",
        }

    failing_stage = None
    failing_log_path = None
    status = "passed"
    if tests_result["status"] != "passed":
        status = "failed"
        failing_stage = "tests"
        failing_log_path = tests_result["stderr_log"]
    elif fault_drills_result["status"] != "passed":
        status = "failed"
        failing_stage = "fault_drills"
        failing_log_path = fault_drills_result["stderr_log"]

    summary = {
        "generated_at_utc": _utc_now(),
        "mode": "verify",
        "label": args.label,
        "status": status,
        "retain_root": str(verify_root.resolve()),
        "tests": tests_result,
        "fault_drills": fault_drills_result,
        "failing_stage": failing_stage,
        "failing_log_path": failing_log_path,
    }
    summary_path = verify_root / "verify_summary.json"
    summary = with_evidence_metadata(
        summary,
        evidence_family="real_shadow_verify",
        contract_version="real_shadow_verify.v1",
        repo_root=ROOT,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_path"] = str(summary_path.resolve())
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


def _invoke_fault_drills(*, args: argparse.Namespace, artifacts_root: Path) -> int:
    command = _fault_drills_command(args=args, artifacts_root=artifacts_root)
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
    )
    return completed.returncode


def _fault_drills_command(*, args: argparse.Namespace, artifacts_root: Path) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "drills" / "run_real_provider_fault_drills.py"),
        "--artifacts-root",
        str(artifacts_root.resolve()),
    ]
    for drill_name in args.drill:
        command.extend(["--drill", drill_name])
    return command


def _run_stage_with_logs(
    *,
    stage_name: str,
    command: list[str],
    log_root: Path,
) -> dict[str, object]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    stdout_log = log_root / f"{stage_name}.stdout.log"
    stderr_log = log_root / f"{stage_name}.stderr.log"
    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")
    return {
        "stage_name": stage_name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "command": command,
        "stdout_log": str(stdout_log.resolve()),
        "stderr_log": str(stderr_log.resolve()),
    }


def _read_json_if_present(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _sanitize_label(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return sanitized or "verify"


def _summarize_fault_drills_summary(payload: dict[str, object] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    results = payload.get("results")
    result_count = len(results) if isinstance(results, list) else 0
    return {
        "all_passed": bool(payload.get("all_passed")),
        "hard_failures": list(payload.get("hard_failures", [])),
        "soft_failures": list(payload.get("soft_failures", [])),
        "result_count": result_count,
    }


def _timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_real_24h(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_controlled_shadow_soak.py"),
        "--artifacts-root",
        str(Path(args.artifacts_root).resolve()),
        "--duration-seconds",
        str(args.duration_seconds),
        "--label",
        args.label,
        "--simulation-profile",
        "real",
        "--clock-reference-url",
        args.clock_reference_url,
        "--binance-websocket-url",
        args.binance_websocket_url,
        "--min-free-disk-mb",
        str(args.min_free_disk_mb),
        "--max-total-log-bytes",
        str(args.max_total_log_bytes),
        "--clock-skew-threshold-seconds",
        str(args.clock_skew_threshold_seconds),
        "--provider-probe-timeout-seconds",
        str(args.provider_probe_timeout_seconds),
        "--min-permit-margin-seconds",
        str(args.min_permit_margin_seconds),
        "--require-real-24h-ready",
        "--require-explicit-real-permit",
        "--log-level",
        args.log_level,
    ]
    if args.allow_existing_label:
        command.append("--allow-existing-label")
    if args.execution_permit:
        command.extend(["--execution-permit", str(Path(args.execution_permit).resolve())])
    if args.alchemy_endpoint_url:
        command.extend(["--alchemy-endpoint-url", args.alchemy_endpoint_url])
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
