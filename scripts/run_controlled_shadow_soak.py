from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
)
from enhengclaw.orchestration.shadow_ingestion_providers import (
    ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
    ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
    ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
    alchemy_endpoint_url_for_network,
    build_legacy_provider_payloads,
    load_provider_payloads_from_config,
)
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.orchestration.shadow_acceptance import (
    DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    DEFAULT_MAX_TOTAL_LOG_BYTES,
    DEFAULT_MIN_FREE_DISK_MB,
    DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS,
    DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    PreflightConfig,
    artifacts_root_isolated,
    build_controlled_agent_slices_summary,
    build_go_no_go,
    effective_alchemy_endpoint_url,
    build_interruption_failure_evidence,
    build_lease_lifecycle_summary,
    build_provider_health_snapshot,
    build_rejection_root,
    copy_or_placeholder,
    ensure_jsonl,
    ensure_text,
    format_utc,
    load_json,
    REAL_24H_DURATION_SECONDS,
    REAL_24H_MIN_PERMIT_MARGIN_SECONDS,
    REAL_SHADOW_EVIDENCE_BUNDLE_VERSION,
    render_postmortem,
    run_preflight,
    utc_now,
    write_json,
)
from enhengclaw.orchestration.worker_operations import default_ingestion_audit_root
from enhengclaw.testing.execution_testbed import execution_testbed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled shadow soak and emit auditable evidence artifacts.")
    parser.add_argument("--artifacts-root", default=ROOT / "artifacts" / "controlled_shadow_soak", type=Path)
    parser.add_argument(
        "--execution-permit",
        default=None,
        help="Optional execution permit path. If omitted, the script provisions an ephemeral permit unless explicit real permit enforcement is enabled.",
    )
    parser.add_argument("--duration-seconds", type=int, default=300, help="Wall-clock soak duration.")
    parser.add_argument("--simulation-profile", choices=("synthetic", "real"), default="synthetic")
    parser.add_argument("--synthetic-event-interval-seconds", type=float, default=0.2)
    parser.add_argument("--synthetic-quarantine-every", type=int, default=15)
    parser.add_argument("--label", default="short", help="Run label used for evidence directories.")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--provider-config", default=None)
    parser.add_argument("--binance-websocket-url", default="wss://stream.binance.com:9443/ws")
    parser.add_argument("--alchemy-endpoint-url", default=None)
    parser.add_argument("--clock-reference-url", default="https://api.binance.com/api/v3/time")
    parser.add_argument("--min-free-disk-mb", type=int, default=DEFAULT_MIN_FREE_DISK_MB)
    parser.add_argument("--max-total-log-bytes", type=int, default=DEFAULT_MAX_TOTAL_LOG_BYTES)
    parser.add_argument(
        "--clock-skew-threshold-seconds",
        type=float,
        default=DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    )
    parser.add_argument(
        "--provider-probe-timeout-seconds",
        type=float,
        default=DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--min-permit-margin-seconds",
        type=float,
        default=None,
    )
    parser.add_argument("--allow-existing-label", action="store_true")
    parser.add_argument("--require-real-24h-ready", action="store_true")
    parser.add_argument("--require-explicit-real-permit", action="store_true")
    parser.add_argument("--binance-receive-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--binance-initial-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--binance-max-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--binance-max-reconnect-attempts", type=int, default=None)
    parser.add_argument("--alchemy-poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--alchemy-request-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--alchemy-initial-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--alchemy-max-backoff-seconds", type=float, default=20.0)
    parser.add_argument("--alchemy-max-retry-attempts", type=int, default=5)
    parser.add_argument("--alchemy-degraded-after-failures", type=int, default=3)
    parser.add_argument("--disable-eth-get-block-by-number", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_artifacts_root = Path(args.artifacts_root).resolve()
    requested_artifacts_root = base_artifacts_root / "runs" / args.label
    requested_soak_root = base_artifacts_root / "soak_runs" / args.label

    if args.allow_existing_label:
        effective_soak_root = requested_soak_root
    else:
        artifacts_isolated, _ = artifacts_root_isolated(requested_artifacts_root)
        soak_isolated, _ = artifacts_root_isolated(requested_soak_root)
        effective_soak_root = (
            requested_soak_root
            if artifacts_isolated and soak_isolated
            else build_rejection_root(base_artifacts_root, label=args.label)
        )
    effective_soak_root.mkdir(parents=True, exist_ok=True)

    if args.execution_permit:
        return _run_soak(
            args=args,
            base_artifacts_root=base_artifacts_root,
            requested_artifacts_root=requested_artifacts_root,
            requested_soak_root=requested_soak_root,
            soak_root=effective_soak_root,
            permit_path=Path(args.execution_permit).resolve(),
            explicit_permit_supplied=True,
        )

    if args.require_explicit_real_permit and args.simulation_profile == "real":
        missing = effective_soak_root / "missing_execution_permit.json"
        return _run_soak(
            args=args,
            base_artifacts_root=base_artifacts_root,
            requested_artifacts_root=requested_artifacts_root,
            requested_soak_root=requested_soak_root,
            soak_root=effective_soak_root,
            permit_path=missing,
            explicit_permit_supplied=False,
        )

    effective_min_permit_margin_seconds = _effective_min_permit_margin_seconds(args)
    with execution_testbed() as bed:
        permit_path, _ = bed.issue_permit(
            slug=f"controlled-soak-{args.label}",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            expires_after=timedelta(
                seconds=max(
                    int(args.duration_seconds + effective_min_permit_margin_seconds),
                    900,
                )
            ),
        )
        return _run_soak(
            args=args,
            base_artifacts_root=base_artifacts_root,
            requested_artifacts_root=requested_artifacts_root,
            requested_soak_root=requested_soak_root,
            soak_root=effective_soak_root,
            permit_path=permit_path,
            explicit_permit_supplied=False,
        )


def _run_soak(
    *,
    args: argparse.Namespace,
    base_artifacts_root: Path,
    requested_artifacts_root: Path,
    requested_soak_root: Path,
    soak_root: Path,
    permit_path: Path,
    explicit_permit_supplied: bool,
) -> int:
    started_at = utc_now()
    artifacts_root = requested_artifacts_root
    audit_root = default_ingestion_audit_root(artifacts_root)
    effective_min_permit_margin_seconds = _effective_min_permit_margin_seconds(args)
    providers = _resolve_provider_payloads(args)
    stdout_log = soak_root / "controller.stdout.log"
    stderr_log = soak_root / "controller.stderr.log"
    worker_audit_path = soak_root / "audit_record.json"
    worker_events_path = soak_root / "events.jsonl"
    worker_stdout_path = soak_root / "worker.stdout.log"
    worker_stderr_path = soak_root / "worker.stderr.log"
    provider_health_snapshot_path = soak_root / "provider_health_snapshot.json"
    interruption_evidence_path = soak_root / "interruption_failure_evidence.json"
    go_no_go_path = soak_root / "go_no_go.json"
    run_config_path = soak_root / "run_config.json"
    exit_status_path = soak_root / "exit_status.json"
    summary_path = soak_root / "soak_summary.json"
    postmortem_path = soak_root / "postmortem.md"

    command = _build_command(args=args, artifacts_root=artifacts_root, permit_path=permit_path)
    run_config = {
        "evidence_bundle_version": REAL_SHADOW_EVIDENCE_BUNDLE_VERSION,
        "acceptance_profile": "real_24h" if args.simulation_profile == "real" else "controlled_soak",
        "label": args.label,
        "simulation_profile": args.simulation_profile,
        "duration_seconds": args.duration_seconds,
        "requested_artifacts_root": str(requested_artifacts_root),
        "requested_soak_root": str(requested_soak_root),
        "effective_artifacts_root": str(artifacts_root),
        "effective_soak_root": str(soak_root),
        "base_artifacts_root": str(base_artifacts_root),
        "execution_permit": str(permit_path),
        "explicit_execution_permit_supplied": explicit_permit_supplied,
        "command": command,
        "launched_at_utc": format_utc(started_at),
        "started_at_utc": format_utc(started_at),
        "clock_reference_url": args.clock_reference_url,
        "binance_websocket_url": args.binance_websocket_url,
        "alchemy_endpoint_url": _effective_alchemy_endpoint(providers),
        "provider_config_path": None if args.provider_config in {None, ""} else str(Path(args.provider_config).resolve()),
        "providers": providers,
        "min_free_disk_mb": args.min_free_disk_mb,
        "max_total_log_bytes": args.max_total_log_bytes,
        "clock_skew_threshold_seconds": args.clock_skew_threshold_seconds,
        "provider_probe_timeout_seconds": args.provider_probe_timeout_seconds,
        "min_permit_margin_seconds": effective_min_permit_margin_seconds,
        "require_real_24h_ready": args.require_real_24h_ready,
        "require_explicit_real_permit": args.require_explicit_real_permit,
    }
    write_json(run_config_path, run_config)

    preflight = run_preflight(
        PreflightConfig(
            execution_permit_path=permit_path,
            artifacts_root=artifacts_root,
            soak_root=soak_root,
            audit_root=audit_root,
            duration_seconds=args.duration_seconds,
            simulation_profile=args.simulation_profile,
            binance_websocket_url=args.binance_websocket_url,
            alchemy_endpoint_url=_effective_alchemy_endpoint(providers),
            alchemy_include_block_details=not args.disable_eth_get_block_by_number,
            clock_reference_url=args.clock_reference_url,
            min_free_disk_mb=args.min_free_disk_mb,
            max_total_log_bytes=args.max_total_log_bytes,
            clock_skew_threshold_seconds=args.clock_skew_threshold_seconds,
            provider_probe_timeout_seconds=args.provider_probe_timeout_seconds,
            min_permit_margin_seconds=effective_min_permit_margin_seconds,
            require_explicit_real_permit=args.require_explicit_real_permit,
            providers=tuple(providers),
        )
    )
    if preflight.get("status") != "passed":
        exit_status = _write_preflight_failure_bundle(
            started_at=started_at,
            soak_root=soak_root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            worker_audit_path=worker_audit_path,
            worker_events_path=worker_events_path,
            worker_stdout_path=worker_stdout_path,
            worker_stderr_path=worker_stderr_path,
            exit_status_path=exit_status_path,
            preflight=preflight,
        )
        shadow_summary = _empty_shadow_summary(run_config_path=run_config_path, exit_status_path=exit_status_path)
        return _finalize_summary(
            run_config=run_config,
            preflight=preflight,
            shadow_summary=shadow_summary,
            audit_record=load_json(worker_audit_path),
            events_path=worker_events_path,
            exit_status=exit_status,
            evidence_artifacts=_evidence_artifacts(
                run_config_path=run_config_path,
                exit_status_path=exit_status_path,
                summary_path=summary_path,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
                worker_audit_path=worker_audit_path,
                worker_events_path=worker_events_path,
                worker_stdout_path=worker_stdout_path,
                worker_stderr_path=worker_stderr_path,
                provider_health_snapshot_path=provider_health_snapshot_path,
                interruption_evidence_path=interruption_evidence_path,
                go_no_go_path=go_no_go_path,
                postmortem_path=postmortem_path,
            ),
            artifacts_root=artifacts_root,
            latest_run_root=None,
            provider_health_snapshot_path=provider_health_snapshot_path,
            interruption_evidence_path=interruption_evidence_path,
            go_no_go_path=go_no_go_path,
            summary_path=summary_path,
            postmortem_path=postmortem_path,
            require_real_24h_ready=args.require_real_24h_ready,
            max_total_log_bytes=args.max_total_log_bytes,
            forced_exit_code=1,
        )

    with stdout_log.open("w", encoding="utf-8") as stdout_handle, stderr_log.open("w", encoding="utf-8") as stderr_handle:
        completed = subprocess.run(
            command,
            check=False,
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=_pythonpath_env(),
            cwd=ROOT,
        )
    ended_at = utc_now()
    exit_status = {
        "started_at_utc": format_utc(started_at),
        "ended_at_utc": format_utc(ended_at),
        "exit_code": completed.returncode,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    write_json(exit_status_path, exit_status)

    latest_run_root = _latest_run_root(audit_root)
    _materialize_worker_bundle(
        latest_run_root=latest_run_root,
        worker_audit_path=worker_audit_path,
        worker_events_path=worker_events_path,
        worker_stdout_path=worker_stdout_path,
        worker_stderr_path=worker_stderr_path,
    )
    try:
        shadow_summary = _check_shadow_run(
            artifacts_root=artifacts_root,
            soak_root=soak_root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            run_config_path=run_config_path,
            exit_status_path=exit_status_path,
        )
    except Exception as exc:  # noqa: BLE001
        shadow_summary = _empty_shadow_summary(
            run_config_path=run_config_path,
            exit_status_path=exit_status_path,
            error=str(exc),
        )

    return _finalize_summary(
        run_config=run_config,
        preflight=preflight,
        shadow_summary=shadow_summary,
        audit_record=load_json(worker_audit_path),
        events_path=worker_events_path,
        exit_status=exit_status,
        evidence_artifacts=_evidence_artifacts(
            run_config_path=run_config_path,
            exit_status_path=exit_status_path,
            summary_path=summary_path,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            worker_audit_path=worker_audit_path,
            worker_events_path=worker_events_path,
            worker_stdout_path=worker_stdout_path,
            worker_stderr_path=worker_stderr_path,
            provider_health_snapshot_path=provider_health_snapshot_path,
            interruption_evidence_path=interruption_evidence_path,
            go_no_go_path=go_no_go_path,
            postmortem_path=postmortem_path,
        ),
        artifacts_root=artifacts_root,
        latest_run_root=latest_run_root,
        provider_health_snapshot_path=provider_health_snapshot_path,
        interruption_evidence_path=interruption_evidence_path,
        go_no_go_path=go_no_go_path,
        summary_path=summary_path,
        postmortem_path=postmortem_path,
        require_real_24h_ready=args.require_real_24h_ready,
        max_total_log_bytes=args.max_total_log_bytes,
        forced_exit_code=completed.returncode,
    )


def _finalize_summary(
    *,
    run_config: dict[str, Any],
    preflight: dict[str, Any],
    shadow_summary: dict[str, Any],
    audit_record: dict[str, Any],
    events_path: Path,
    exit_status: dict[str, Any],
    evidence_artifacts: dict[str, str],
    artifacts_root: Path,
    latest_run_root: Path | None,
    provider_health_snapshot_path: Path,
    interruption_evidence_path: Path,
    go_no_go_path: Path,
    summary_path: Path,
    postmortem_path: Path,
    require_real_24h_ready: bool,
    max_total_log_bytes: int,
    forced_exit_code: int,
) -> int:
    agent_layer_governance = evaluate_agent_layer_governance()
    provider_health_snapshot = build_provider_health_snapshot(
        artifacts_root=artifacts_root,
        shadow_summary=shadow_summary,
        run_root=latest_run_root,
        preflight=preflight,
    )
    write_json(provider_health_snapshot_path, provider_health_snapshot)
    interruption_evidence = build_interruption_failure_evidence(
        preflight=preflight,
        audit_record=audit_record,
        events_path=events_path,
        exit_status=exit_status,
    )
    write_json(interruption_evidence_path, interruption_evidence)
    lease_lifecycle = build_lease_lifecycle_summary(
        audit_record=audit_record,
        events_path=events_path,
        interruption_evidence=interruption_evidence,
    )
    ensure_text(postmortem_path, "")
    write_json(go_no_go_path, {"status": "pending"})
    write_json(summary_path, {"status": "pending"})

    summary = {
        "run": {
            "artifacts_root": str(artifacts_root),
            "soak_root": run_config["effective_soak_root"],
            "audit_root": str(default_ingestion_audit_root(artifacts_root)),
            "latest_run_root": None if latest_run_root is None else str(latest_run_root),
            "summary_generated_at_utc": format_utc(utc_now()),
        },
        "run_config": run_config,
        "preflight": preflight,
        "audit": {
            "audit_record": audit_record,
            "event_counts": _summarize_events(events_path),
            "events_path": str(events_path),
        },
        "shadow": shadow_summary,
        "controlled_agent_slices": build_controlled_agent_slices_summary(),
        "agent_layer_governance": agent_layer_governance,
        "provider_health_snapshot": provider_health_snapshot,
        "interruption_failure_evidence": interruption_evidence,
        "lease_lifecycle": lease_lifecycle,
        "evidence_artifacts": evidence_artifacts,
    }
    violations = _evaluate_summary(summary, max_total_log_bytes=max_total_log_bytes)
    summary["ready"] = not violations
    summary["violations"] = violations
    summary["go_no_go"] = build_go_no_go(
        summary=summary,
        require_real_24h=require_real_24h_ready,
        agent_layer_governance=agent_layer_governance,
    )
    write_json(go_no_go_path, summary["go_no_go"])
    postmortem_path.write_text(render_postmortem(summary), encoding="utf-8")
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if forced_exit_code != 0:
        return forced_exit_code
    if violations:
        return 1
    if require_real_24h_ready and summary["go_no_go"]["READY_FOR_REAL_24H_SHADOW"] is not True:
        return 1
    return 0


def _build_command(*, args: argparse.Namespace, artifacts_root: Path, permit_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "enhengclaw.orchestration.shadow_ingestion_runner",
        "--artifacts-root",
        str(artifacts_root),
        "--execution-permit",
        str(permit_path),
        "--run-seconds",
        str(args.duration_seconds),
        "--log-level",
        args.log_level,
        "--simulation-profile",
        args.simulation_profile,
        "--synthetic-event-interval-seconds",
        str(args.synthetic_event_interval_seconds),
        "--synthetic-quarantine-every",
        str(args.synthetic_quarantine_every),
        "--binance-receive-timeout-seconds",
        str(args.binance_receive_timeout_seconds),
        "--binance-initial-backoff-seconds",
        str(args.binance_initial_backoff_seconds),
        "--binance-max-backoff-seconds",
        str(args.binance_max_backoff_seconds),
        "--binance-websocket-url",
        args.binance_websocket_url,
        "--alchemy-poll-interval-seconds",
        str(args.alchemy_poll_interval_seconds),
        "--alchemy-request-timeout-seconds",
        str(args.alchemy_request_timeout_seconds),
        "--alchemy-initial-backoff-seconds",
        str(args.alchemy_initial_backoff_seconds),
        "--alchemy-max-backoff-seconds",
        str(args.alchemy_max_backoff_seconds),
        "--alchemy-max-retry-attempts",
        str(args.alchemy_max_retry_attempts),
        "--alchemy-degraded-after-failures",
        str(args.alchemy_degraded_after_failures),
    ] + _optional_command_parts(args)


def _optional_command_parts(args: argparse.Namespace) -> list[str]:
    parts: list[str] = []
    if args.provider_config:
        parts.extend(["--provider-config", str(Path(args.provider_config).resolve())])
    if args.binance_max_reconnect_attempts is not None:
        parts.extend(["--binance-max-reconnect-attempts", str(args.binance_max_reconnect_attempts)])
    if args.disable_eth_get_block_by_number:
        parts.append("--disable-eth-get-block-by-number")
    if args.alchemy_endpoint_url:
        parts.extend(["--alchemy-endpoint-url", str(args.alchemy_endpoint_url)])
    return parts


def _write_preflight_failure_bundle(
    *,
    started_at: datetime,
    soak_root: Path,
    stdout_log: Path,
    stderr_log: Path,
    worker_audit_path: Path,
    worker_events_path: Path,
    worker_stdout_path: Path,
    worker_stderr_path: Path,
    exit_status_path: Path,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    ensure_text(stdout_log, "")
    ensure_text(stderr_log, json.dumps(preflight, indent=2, sort_keys=True))
    write_json(
        worker_audit_path,
        {
            "component": "ingestion_worker",
            "status": "preflight_failed",
            "failure_category": "preflight_failed",
            "interruption_reason": "; ".join(str(item) for item in preflight.get("failures", [])),
            "created_at_utc": format_utc(started_at),
            "started_at_utc": format_utc(started_at),
            "ended_at_utc": format_utc(utc_now()),
            "lease_id": None,
            "worker_pid": None,
        },
    )
    ensure_jsonl(
        worker_events_path,
        [
            {
                "timestamp_utc": format_utc(utc_now()),
                "event": "preflight.failed",
                "component": "controlled_shadow_soak",
                "failure_count": len(preflight.get("failures", [])),
            }
        ],
    )
    ensure_text(worker_stdout_path, "")
    ensure_text(worker_stderr_path, json.dumps(preflight, indent=2, sort_keys=True))
    exit_status = {
        "started_at_utc": format_utc(started_at),
        "ended_at_utc": format_utc(utc_now()),
        "exit_code": 1,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "preflight_failed": True,
    }
    write_json(exit_status_path, exit_status)
    return exit_status


def _materialize_worker_bundle(
    *,
    latest_run_root: Path | None,
    worker_audit_path: Path,
    worker_events_path: Path,
    worker_stdout_path: Path,
    worker_stderr_path: Path,
) -> None:
    copy_or_placeholder(
        None if latest_run_root is None else latest_run_root / "audit_record.json",
        worker_audit_path,
        default_text=json.dumps({"status": "missing_worker_audit"}, indent=2),
    )
    copy_or_placeholder(
        None if latest_run_root is None else latest_run_root / "events.jsonl",
        worker_events_path,
        default_text="",
    )
    copy_or_placeholder(
        None if latest_run_root is None else latest_run_root / "worker.stdout.log",
        worker_stdout_path,
        default_text="",
    )
    copy_or_placeholder(
        None if latest_run_root is None else latest_run_root / "worker.stderr.log",
        worker_stderr_path,
        default_text="",
    )


def _evidence_artifacts(
    *,
    run_config_path: Path,
    exit_status_path: Path,
    summary_path: Path,
    stdout_log: Path,
    stderr_log: Path,
    worker_audit_path: Path,
    worker_events_path: Path,
    worker_stdout_path: Path,
    worker_stderr_path: Path,
    provider_health_snapshot_path: Path,
    interruption_evidence_path: Path,
    go_no_go_path: Path,
    postmortem_path: Path,
) -> dict[str, str]:
    return {
        "run_config": str(run_config_path),
        "exit_status": str(exit_status_path),
        "soak_summary": str(summary_path),
        "controller_stdout_log": str(stdout_log),
        "controller_stderr_log": str(stderr_log),
        "worker_audit_record": str(worker_audit_path),
        "worker_events": str(worker_events_path),
        "worker_stdout_log": str(worker_stdout_path),
        "worker_stderr_log": str(worker_stderr_path),
        "provider_health_snapshot": str(provider_health_snapshot_path),
        "interruption_failure_evidence": str(interruption_evidence_path),
        "go_no_go": str(go_no_go_path),
        "postmortem": str(postmortem_path),
    }


def _effective_alchemy_endpoint(providers: list[dict[str, Any]]) -> str:
    for provider in providers:
        if provider["kind"] in {
            ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
            ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
            ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
        }:
            return alchemy_endpoint_url_for_network(
                provider["network"],
                provider.get("endpoint_url"),
            )
    return effective_alchemy_endpoint_url(None)


def _resolve_provider_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.provider_config not in {None, ""}:
        return load_provider_payloads_from_config(Path(args.provider_config).resolve())
    return build_legacy_provider_payloads(
        binance_websocket_url=args.binance_websocket_url,
        binance_receive_timeout_seconds=args.binance_receive_timeout_seconds,
        binance_initial_backoff_seconds=args.binance_initial_backoff_seconds,
        binance_max_backoff_seconds=args.binance_max_backoff_seconds,
        binance_max_reconnect_attempts=args.binance_max_reconnect_attempts,
        alchemy_poll_interval_seconds=args.alchemy_poll_interval_seconds,
        alchemy_request_timeout_seconds=args.alchemy_request_timeout_seconds,
        alchemy_initial_backoff_seconds=args.alchemy_initial_backoff_seconds,
        alchemy_max_backoff_seconds=args.alchemy_max_backoff_seconds,
        alchemy_max_retry_attempts=args.alchemy_max_retry_attempts,
        alchemy_degraded_after_failures=args.alchemy_degraded_after_failures,
        disable_eth_get_block_by_number=args.disable_eth_get_block_by_number,
        alchemy_endpoint_url=args.alchemy_endpoint_url,
    )


def _effective_min_permit_margin_seconds(args: argparse.Namespace) -> float:
    requested_margin = (
        DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS
        if args.min_permit_margin_seconds is None
        else float(args.min_permit_margin_seconds)
    )
    if args.require_real_24h_ready and args.simulation_profile == "real" and args.duration_seconds >= REAL_24H_DURATION_SECONDS:
        return max(requested_margin, REAL_24H_MIN_PERMIT_MARGIN_SECONDS)
    return requested_margin


def _check_shadow_run(
    *,
    artifacts_root: Path,
    soak_root: Path,
    stdout_log: Path,
    stderr_log: Path,
    run_config_path: Path,
    exit_status_path: Path,
) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_shadow_run.py"),
            "--artifacts-root",
            str(artifacts_root),
            "--run-root",
            str(soak_root),
            "--stdout-log",
            str(stdout_log),
            "--stderr-log",
            str(stderr_log),
            "--run-config",
            str(run_config_path),
            "--exit-status",
            str(exit_status_path),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_pythonpath_env(),
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"check_shadow_run.py failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def _empty_shadow_summary(
    *,
    run_config_path: Path,
    exit_status_path: Path,
    error: str | None = None,
) -> dict[str, Any]:
    run_config = load_json(run_config_path)
    exit_status = load_json(exit_status_path)
    providers = run_config.get("providers") if isinstance(run_config.get("providers"), list) else [
        {"subject_key": "BTCUSDT.binance.spot"},
        {"subject_key": "ETHUSDT.binance.spot"},
        {"subject_key": "ETH.alchemy.onchain"},
    ]
    return {
        "run": {
            "artifacts_root": run_config.get("effective_artifacts_root"),
            "run_root": run_config.get("effective_soak_root"),
            "started_at_utc": run_config.get("started_at_utc"),
            "ended_at_utc": exit_status.get("ended_at_utc"),
            "exit_code": exit_status.get("exit_code"),
            "run_completed": exit_status != {},
            "summary_error": error,
        },
        "subjects": {
            str(provider["subject_key"]): {
                "event_count": 0,
                "event_type_counts": {},
                "missing_hours": [],
                "parse_error_count": 0,
                "contamination_count": 0,
            }
            for provider in providers
        },
        "stability": {
            "binance_reconnect_count": 0,
            "binance_subscription_ack_count": 0,
            "alchemy_retry_count": 0,
            "provider_degraded_count": 0,
            "provider_recovered_count": 0,
            "process_start_count": 0,
            "process_exit_count": 0 if exit_status.get("exit_code") == 0 else 1,
        },
        "quality": {
            "quarantine_count": 0,
            "quarantine_file_count": 0,
            "schema_rejection_count": 0,
            "replay_parse_error_count": 0,
            "replay_write_failure_count": 0,
            "cross_subject_contamination_count": 0,
            "quarantine_reason_counts": {},
        },
        "security": {
            "key_leakage_detected": False,
            "unredacted_alchemy_endpoint_detected": False,
        },
    }


def _evaluate_summary(summary: dict[str, Any], *, max_total_log_bytes: int) -> list[str]:
    violations: list[str] = []
    audit_record = dict(summary["audit"]["audit_record"])
    event_counts = dict(summary["audit"]["event_counts"])
    shadow = dict(summary["shadow"])
    run = dict(shadow["run"])
    quality = dict(shadow["quality"])
    security = dict(shadow["security"])
    subjects = dict(shadow["subjects"])
    evidence = dict(summary["evidence_artifacts"])

    if run.get("run_completed") is not True:
        violations.append("shadow run did not complete")
    if run.get("exit_code") != 0:
        violations.append(f"shadow controller exited with code {run.get('exit_code')}")
    if audit_record.get("status") != "completed":
        violations.append(f"worker audit status is {audit_record.get('status')}")
    if event_counts.get("lease.acquired", 0) < 1:
        violations.append("worker audit is missing lease.acquired evidence")
    if event_counts.get("lease.heartbeat", 0) < 1:
        violations.append("worker audit is missing lease.heartbeat evidence")
    if event_counts.get("lease.released", 0) < 1:
        violations.append("worker audit is missing lease.released evidence")
    if quality.get("cross_subject_contamination_count") != 0:
        violations.append("cross-subject contamination was detected")
    if quality.get("replay_parse_error_count") != 0:
        violations.append("replay parse errors were detected")
    if quality.get("replay_write_failure_count") != 0:
        violations.append("replay write failures were detected")
    if security.get("key_leakage_detected") is True:
        violations.append("secret leakage was detected in logs")
    if security.get("unredacted_alchemy_endpoint_detected") is True:
        violations.append("an unredacted Alchemy endpoint was detected in logs")
    for subject_key, subject_summary in subjects.items():
        if int(subject_summary.get("event_count", 0)) <= 0:
            violations.append(f"subject {subject_key} has no replay events")
    total_log_bytes = 0
    for key in (
        "controller_stdout_log",
        "controller_stderr_log",
        "worker_stdout_log",
        "worker_stderr_log",
    ):
        path_value = evidence.get(key)
        if path_value and Path(path_value).exists():
            total_log_bytes += Path(path_value).stat().st_size
    if total_log_bytes > max_total_log_bytes:
        violations.append(
            f"combined controller/worker logs reached {total_log_bytes} bytes, above threshold {max_total_log_bytes}"
        )
    return violations


def _pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _latest_run_root(audit_root: Path) -> Path | None:
    runs_root = audit_root / "runs"
    if not runs_root.exists():
        return None
    candidates = [path for path in runs_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _summarize_events(events_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not events_path.exists():
        return counts
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        event_name = str(payload.get("event", "unknown"))
        counts[event_name] = counts.get(event_name, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
