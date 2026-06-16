from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.orchestration.shadow_acceptance import (
    DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    DEFAULT_MAX_TOTAL_LOG_BYTES,
    DEFAULT_MIN_FREE_DISK_MB,
    DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    REAL_24H_DURATION_SECONDS,
    REAL_24H_MIN_PERMIT_MARGIN_SECONDS,
    evaluate_real_24h_rerun_verdict,
    run_real_24h_preflight_only,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the formal real-24h shadow operator bundle: preflight-only -> rerun -> rerun verdict."
    )
    parser.add_argument("--execution-permit", required=True, type=Path)
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--preflight-label", required=True)
    parser.add_argument("--rerun-label", required=True)
    parser.add_argument("--trust-root-dir", default=None, type=Path)
    parser.add_argument("--duration-seconds", type=int, default=REAL_24H_DURATION_SECONDS)
    parser.add_argument("--clock-reference-url", default="https://api.binance.com/api/v3/time")
    parser.add_argument("--binance-websocket-url", default="wss://stream.binance.com:9443/ws")
    parser.add_argument("--alchemy-endpoint-url", default=None)
    parser.add_argument("--min-free-disk-mb", type=int, default=DEFAULT_MIN_FREE_DISK_MB)
    parser.add_argument("--max-total-log-bytes", type=int, default=DEFAULT_MAX_TOTAL_LOG_BYTES)
    parser.add_argument("--clock-skew-threshold-seconds", type=float, default=DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS)
    parser.add_argument("--provider-probe-timeout-seconds", type=float, default=DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS)
    parser.add_argument("--min-permit-margin-seconds", type=float, default=REAL_24H_MIN_PERMIT_MARGIN_SECONDS)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts_root = Path(args.artifacts_root).resolve()
    bundle_root = (artifacts_root / "real_24h_bundles" / args.rerun_label).resolve()
    bundle_root.mkdir(parents=True, exist_ok=True)
    preflight_stage_path = bundle_root / "preflight_stage.json"
    rerun_stage_path = bundle_root / "rerun_stage.json"
    verdict_stage_path = bundle_root / "verdict_stage.json"
    bundle_summary_path = bundle_root / "bundle_summary.json"
    rerun_stdout_log = bundle_root / "rerun.stdout.log"
    rerun_stderr_log = bundle_root / "rerun.stderr.log"

    preflight_stage: dict[str, Any] = {
        "status": "not_started",
        "all_green": False,
    }
    rerun_stage: dict[str, Any] = {
        "status": "not_started",
        "rerun_started": False,
        "stdout_log": str(rerun_stdout_log),
        "stderr_log": str(rerun_stderr_log),
    }
    verdict_stage: dict[str, Any] = {
        "status": "not_started",
    }
    status = "failed"
    failing_stage = None
    failure_reason = None
    rerun_evidence_root = str((artifacts_root / "soak_runs" / args.rerun_label).resolve())
    preflight_evidence_root = str((artifacts_root / "preflight_only" / args.preflight_label).resolve())

    try:
        if args.preflight_label == args.rerun_label:
            raise ValueError("rerun label must differ from preflight label")
        if Path(rerun_evidence_root).exists():
            raise FileExistsError(f"rerun evidence dir already exists: {rerun_evidence_root}")

        preflight_result = run_real_24h_preflight_only(
            repo_root=ROOT,
            execution_permit_path=Path(args.execution_permit).resolve(),
            artifacts_root=artifacts_root,
            label=args.preflight_label,
            duration_seconds=args.duration_seconds,
            binance_websocket_url=args.binance_websocket_url,
            alchemy_endpoint_url=args.alchemy_endpoint_url,
            clock_reference_url=args.clock_reference_url,
            min_free_disk_mb=args.min_free_disk_mb,
            max_total_log_bytes=args.max_total_log_bytes,
            clock_skew_threshold_seconds=args.clock_skew_threshold_seconds,
            provider_probe_timeout_seconds=args.provider_probe_timeout_seconds,
            min_permit_margin_seconds=args.min_permit_margin_seconds,
            trust_root_dir=args.trust_root_dir,
        )
        preflight_stage = {
            "status": "passed" if preflight_result.get("all_green") else "failed",
            **preflight_result,
        }
        preflight_evidence_root = str(preflight_result.get("evidence_root", preflight_evidence_root))
        write_json(preflight_stage_path, preflight_stage)
        if preflight_result.get("all_green") is not True:
            failing_stage = "preflight"
            failure_reason = "preflight_all_green_false"
            rerun_stage["status"] = "skipped"
            rerun_stage["failure_reason"] = failure_reason
            verdict_stage["status"] = "skipped"
            verdict_stage["failure_reason"] = failure_reason
            write_json(rerun_stage_path, rerun_stage)
            write_json(verdict_stage_path, verdict_stage)
            return _finalize_bundle(
                bundle_summary_path=bundle_summary_path,
                status=status,
                failing_stage=failing_stage,
                failure_reason=failure_reason,
                preflight_stage=preflight_stage,
                rerun_stage=rerun_stage,
                verdict_stage=verdict_stage,
                preflight_evidence_root=preflight_evidence_root,
                rerun_evidence_root=rerun_evidence_root,
                bundle_root=bundle_root,
            )

        rerun_stage = _run_rerun_stage(
            args=args,
            rerun_stdout_log=rerun_stdout_log,
            rerun_stderr_log=rerun_stderr_log,
        )
        rerun_stage["rerun_started"] = True
        rerun_stage["rerun_evidence_root"] = rerun_evidence_root
        write_json(rerun_stage_path, rerun_stage)

        verdict_result = evaluate_real_24h_rerun_verdict(
            artifacts_root=artifacts_root,
            rerun_label=args.rerun_label,
            preflight_label=args.preflight_label,
        )
        verdict_stage = verdict_result
        write_json(verdict_stage_path, verdict_stage)

        # A green rerun process exit is necessary, but the retained verdict
        # bundle stays authoritative for the final pass/fail decision.
        if rerun_stage.get("exit_code") == 0 and verdict_stage.get("status") == "passed":
            status = "passed"
        elif rerun_stage.get("exit_code") != 0:
            failing_stage = "rerun"
            failure_reason = f"rerun_exit_code={rerun_stage.get('exit_code')}"
        else:
            failing_stage = "verdict"
            failure_reason = "; ".join(verdict_stage.get("failures", [])) or "rerun_verdict_failed"
    except Exception as exc:  # noqa: BLE001
        if preflight_stage["status"] == "not_started":
            failing_stage = "preflight"
        elif rerun_stage["status"] in {"not_started", "skipped"}:
            failing_stage = "rerun"
        else:
            failing_stage = "verdict"
        failure_reason = str(exc)
        if rerun_stage["status"] == "not_started":
            rerun_stage["status"] = "skipped"
            rerun_stage["failure_reason"] = failure_reason
            write_json(rerun_stage_path, rerun_stage)
        if verdict_stage["status"] == "not_started":
            verdict_stage["status"] = "failed"
            verdict_stage["failure_reason"] = failure_reason
            write_json(verdict_stage_path, verdict_stage)
        if preflight_stage["status"] == "not_started":
            preflight_stage["status"] = "failed"
            preflight_stage["failure_reason"] = failure_reason
            write_json(preflight_stage_path, preflight_stage)

    if not preflight_stage_path.exists():
        write_json(preflight_stage_path, preflight_stage)
    if not rerun_stage_path.exists():
        write_json(rerun_stage_path, rerun_stage)
    if not verdict_stage_path.exists():
        write_json(verdict_stage_path, verdict_stage)

    return _finalize_bundle(
        bundle_summary_path=bundle_summary_path,
        status=status,
        failing_stage=failing_stage,
        failure_reason=failure_reason,
        preflight_stage=preflight_stage,
        rerun_stage=rerun_stage,
        verdict_stage=verdict_stage,
        preflight_evidence_root=preflight_evidence_root,
        rerun_evidence_root=rerun_evidence_root,
        bundle_root=bundle_root,
    )


def _run_rerun_stage(
    *,
    args: argparse.Namespace,
    rerun_stdout_log: Path,
    rerun_stderr_log: Path,
) -> dict[str, Any]:
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str((ROOT / "scripts" / "run_shadow_24h.ps1").resolve()),
        "-ExecutionPermitPath",
        str(Path(args.execution_permit).resolve()),
        "-ArtifactsRoot",
        str(Path(args.artifacts_root).resolve()),
        "-Label",
        args.rerun_label,
        "-DurationSeconds",
        str(args.duration_seconds),
        "-ClockReferenceUrl",
        args.clock_reference_url,
        "-BinanceWebsocketUrl",
        args.binance_websocket_url,
        "-MinFreeDiskMb",
        str(args.min_free_disk_mb),
        "-MaxTotalLogBytes",
        str(args.max_total_log_bytes),
        "-ClockSkewThresholdSeconds",
        str(args.clock_skew_threshold_seconds),
        "-ProviderProbeTimeoutSeconds",
        str(args.provider_probe_timeout_seconds),
        "-MinPermitMarginSeconds",
        str(args.min_permit_margin_seconds),
        "-LogLevel",
        args.log_level,
    ]
    if args.alchemy_endpoint_url:
        command.extend(["-AlchemyEndpointUrl", str(args.alchemy_endpoint_url)])

    child_env = os.environ.copy()
    if args.trust_root_dir is None:
        child_env.pop("ENHENGCLAW_TRUST_ROOT_DIR", None)
    else:
        child_env["ENHENGCLAW_TRUST_ROOT_DIR"] = str(Path(args.trust_root_dir).resolve())

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=child_env,
    )
    rerun_stdout_log.write_text(completed.stdout, encoding="utf-8")
    rerun_stderr_log.write_text(completed.stderr, encoding="utf-8")
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": command,
        "exit_code": completed.returncode,
        "stdout_log": str(rerun_stdout_log.resolve()),
        "stderr_log": str(rerun_stderr_log.resolve()),
    }


def _finalize_bundle(
    *,
    bundle_summary_path: Path,
    status: str,
    failing_stage: str | None,
    failure_reason: str | None,
    preflight_stage: dict[str, Any],
    rerun_stage: dict[str, Any],
    verdict_stage: dict[str, Any],
    preflight_evidence_root: str,
    rerun_evidence_root: str,
    bundle_root: Path,
) -> int:
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": status,
        "failing_stage": failing_stage,
        "failure_reason": failure_reason,
        "preflight_status": preflight_stage.get("preflight_status"),
        "preflight_all_green": preflight_stage.get("all_green"),
        "rerun_started": rerun_stage.get("rerun_started", False),
        "rerun_exit_code": rerun_stage.get("exit_code"),
        "rerun_verdict": verdict_stage.get("status"),
        "READY_FOR_REAL_24H_SHADOW": verdict_stage.get("READY_FOR_REAL_24H_SHADOW"),
        "READY_FOR_AGENT_LAYER": verdict_stage.get("READY_FOR_AGENT_LAYER"),
        "READY_FOR_BROAD_AGENT_LAYER": verdict_stage.get("READY_FOR_BROAD_AGENT_LAYER"),
        "preflight_evidence_root": preflight_evidence_root,
        "rerun_evidence_root": rerun_evidence_root,
        "bundle_retain_root": str(bundle_root.resolve()),
        "preflight_stage": preflight_stage,
        "rerun_stage": rerun_stage,
        "verdict_stage": verdict_stage,
    }
    write_json(
        bundle_summary_path,
        with_evidence_metadata(
            summary,
            evidence_family="real_24h_bundle",
            contract_version="real_24h_bundle.v1",
            repo_root=ROOT,
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
