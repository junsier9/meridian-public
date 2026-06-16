from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from .research_workbench_queues import (
    KNOWN_QUEUE_SOURCES,
    LEGACY_QUEUE,
    QUANT_QUEUE,
    STRUCTURAL_QUEUE,
    consumed_archive_root,
    incoming_queue_root,
    known_incoming_roots,
)


DEFAULT_WINDOW_HOURS = 24
DEFAULT_WARNING_AGE_MINUTES = 40
DEFAULT_CRITICAL_AGE_MINUTES = 120
DEFAULT_SAMPLE_LIMIT = 5
DEFAULT_TOP_SUBJECT_LIMIT = 5


def generate_research_workbench_queue_dashboard(
    *,
    workbench_root: Path,
    quant_artifacts_root: Path | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    warning_age_minutes: int = DEFAULT_WARNING_AGE_MINUTES,
    critical_age_minutes: int = DEFAULT_CRITICAL_AGE_MINUTES,
) -> dict[str, Any]:
    if window_hours <= 0:
        raise ValueError("window_hours must be positive")
    if warning_age_minutes <= 0 or critical_age_minutes <= 0:
        raise ValueError("warning_age_minutes and critical_age_minutes must be positive")
    if warning_age_minutes >= critical_age_minutes:
        raise ValueError("warning_age_minutes must be less than critical_age_minutes")

    resolved_workbench_root = workbench_root.expanduser().resolve()
    resolved_quant_artifacts_root = (
        quant_artifacts_root.expanduser().resolve()
        if quant_artifacts_root is not None
        else (resolved_workbench_root.parent / "quant_research").resolve()
    )
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=window_hours)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")

    queue_status, queue_alerts = _collect_queue_status(
        workbench_root=resolved_workbench_root,
        now=now,
        warning_age_minutes=warning_age_minutes,
        critical_age_minutes=critical_age_minutes,
    )
    producer_status, producer_alerts = _collect_producer_status(
        workbench_root=resolved_workbench_root,
        quant_artifacts_root=resolved_quant_artifacts_root,
    )
    quant_governance_status = _collect_quant_governance_status(
        quant_artifacts_root=resolved_quant_artifacts_root,
    )
    intake_status, intake_alerts = _collect_intake_status(
        workbench_root=resolved_workbench_root,
        now=now,
        window_start=window_start,
    )

    derived_alerts = _derive_cross_system_alerts(
        workbench_root=resolved_workbench_root,
        queue_status=queue_status,
        producer_status=producer_status,
        intake_status=intake_status,
        window_start=window_start,
    )
    alerts = _sort_alerts([*queue_alerts, *producer_alerts, *intake_alerts, *derived_alerts])
    alert_counts = Counter(str(alert.get("level", "warning")) for alert in alerts)

    dashboard = {
        "generated_at_utc": _isoformat_utc(now),
        "run_id": run_id,
        "workbench_root": str(resolved_workbench_root),
        "quant_artifacts_root": str(resolved_quant_artifacts_root),
        "window_hours": int(window_hours),
        "warning_age_minutes": int(warning_age_minutes),
        "critical_age_minutes": int(critical_age_minutes),
        "queue_status": queue_status,
        "producer_status": producer_status,
        "quant_governance_status": quant_governance_status,
        "intake_status": intake_status,
        "alerts": alerts,
        "alert_counts": {
            "critical": int(alert_counts.get("critical", 0)),
            "warning": int(alert_counts.get("warning", 0)),
            "info": int(alert_counts.get("info", 0)),
        },
    }

    operations_root = resolved_workbench_root / "operations" / "queue_dashboard"
    run_root = operations_root / "runs" / run_id
    latest_json_path = operations_root / "queue_dashboard.json"
    latest_md_path = operations_root / "queue_dashboard.md"
    run_json_path = run_root / "queue_dashboard.json"
    run_md_path = run_root / "queue_dashboard.md"

    markdown = render_research_workbench_queue_dashboard_markdown(dashboard)
    _write_json(latest_json_path, dashboard)
    _write_json(run_json_path, dashboard)
    latest_md_path.parent.mkdir(parents=True, exist_ok=True)
    latest_md_path.write_text(markdown, encoding="utf-8")
    run_md_path.parent.mkdir(parents=True, exist_ok=True)
    run_md_path.write_text(markdown, encoding="utf-8")

    dashboard["queue_dashboard_json_path"] = str(latest_json_path)
    dashboard["queue_dashboard_markdown_path"] = str(latest_md_path)
    dashboard["run_queue_dashboard_json_path"] = str(run_json_path)
    dashboard["run_queue_dashboard_markdown_path"] = str(run_md_path)
    return dashboard


def render_research_workbench_queue_dashboard_markdown(dashboard: dict[str, Any]) -> str:
    queue_status = dashboard["queue_status"]
    producer_status = dashboard["producer_status"]
    quant_governance_status = dashboard.get("quant_governance_status", {})
    intake_status = dashboard["intake_status"]
    alerts = dashboard["alerts"]
    alert_counts = dashboard["alert_counts"]

    lines = [
        "# Research Workbench Queue Dashboard",
        "",
        "## Current State",
        f"- Generated at (UTC): `{dashboard['generated_at_utc']}`",
        f"- Queue totals: pending `{queue_status['total_pending_snapshot_count']}`, existing queues `{queue_status['existing_queue_count']}/{len(KNOWN_QUEUE_SOURCES)}`",
        f"- Alerts: critical `{alert_counts['critical']}`, warning `{alert_counts['warning']}`, info `{alert_counts['info']}`",
        f"- Latest intake: `{intake_status['latest_run'].get('status', 'missing')}` processed `{intake_status['latest_run'].get('processed_snapshot_count', 0)}` snapshots",
        f"- Latest structural producer: scan `{producer_status['structural'].get('scan_id', 'missing')}` selected `{producer_status['structural'].get('selected_snapshot_count', 0)}`",
        (
            f"- Latest quant producer: as-of `{producer_status['quant'].get('as_of', 'missing')}` "
            f"published `{producer_status['quant'].get('published_snapshot_count', 0)}` "
            f"staged `{producer_status['quant'].get('staged_only_snapshot_count', 0)}`"
        ),
        "",
        "## Queue Backlog",
        "| Source | Exists | Pending | Oldest Pending (UTC) | Oldest Age (min) | Top Subjects | Sample Cycle IDs |",
        "| --- | --- | ---: | --- | ---: | --- | --- |",
    ]
    for source in (STRUCTURAL_QUEUE, QUANT_QUEUE, LEGACY_QUEUE):
        entry = queue_status[source]
        subject_summary = ", ".join(f"{item['subject']}:{item['count']}" for item in entry["top_subjects"]) or "-"
        sample_cycles = ", ".join(entry["sample_cycle_ids"]) or "-"
        lines.append(
            f"| {source} | {str(entry['exists']).lower()} | {entry['pending_snapshot_count']} | "
            f"{entry['oldest_pending_at_utc'] or '-'} | {entry['oldest_pending_age_minutes'] if entry['oldest_pending_age_minutes'] is not None else '-'} | "
            f"{subject_summary} | {sample_cycles} |"
        )

    structural = producer_status["structural"]
    quant = producer_status["quant"]
    recent_processed_by_source = intake_status["recent_processed_by_source"]
    lines.extend(
        [
            "",
            "## Producer vs Intake",
            (
                f"- Structural latest: status `{structural.get('status', 'missing')}`, scan `{structural.get('scan_id', 'missing')}`, "
                f"selected `{structural.get('selected_snapshot_count', 0)}`, generated `{structural.get('generated_at_utc', '-')}`, "
                f"incoming `{structural.get('incoming_root', '-')}`"
            ),
            (
                f"- Quant latest: status `{quant.get('status', 'missing')}`, queue `{quant.get('queue', '-')}`, exported `{quant.get('exported_snapshot_count', 0)}`, "
                f"published `{quant.get('published_snapshot_count', 0)}`, staged `{quant.get('staged_only_snapshot_count', 0)}`, "
                f"generated `{quant.get('generated_at_utc', '-')}`"
            ),
            (
                f"- Quant governance latest: as-of `{quant_governance_status.get('as_of', quant_governance_status.get('week_of', 'missing'))}`, "
                f"run `{quant_governance_status.get('run_id', 'missing')}`, "
                f"lane mix `agent={quant_governance_status.get('proposal_lane_mix', {}).get('agent', 0)}` "
                f"`heuristic={quant_governance_status.get('proposal_lane_mix', {}).get('heuristic', 0)}`, "
                f"auto-bridged `{quant_governance_status.get('auto_bridged_snapshot_count', 0)}`, "
                f"agent quarantine rate `{quant_governance_status.get('agent_quarantine_rate', 0.0)}`"
            ),
            (
                f"- Intake recent `{dashboard['window_hours']}h`: runs `{intake_status['recent_run_count']}`, processed `{intake_status['recent_processed_snapshot_count']}`, "
                f"structural `{recent_processed_by_source.get(STRUCTURAL_QUEUE, 0)}`, quant `{recent_processed_by_source.get(QUANT_QUEUE, 0)}`, legacy `{recent_processed_by_source.get(LEGACY_QUEUE, 0)}`"
            ),
            "",
            "## Alerts",
        ]
    )
    if int(quant.get("staged_only_snapshot_count", 0)) > 0:
        lines.append(
            "- Quant staged-only snapshots remain research-only / archive-only and are not executable until a later promotion decision publishes them."
        )
    if not alerts:
        lines.append("- No active alerts.")
    else:
        for alert in alerts:
            source = alert.get("source")
            source_text = f" [{source}]" if source else ""
            lines.append(f"- `{str(alert.get('level', 'warning')).upper()}`{source_text} {alert.get('message')}")
    lines.append("")
    return "\n".join(lines)


def _collect_queue_status(
    *,
    workbench_root: Path,
    now: datetime,
    warning_age_minutes: int,
    critical_age_minutes: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    alerts: list[dict[str, Any]] = []
    status: dict[str, Any] = {}
    total_pending = 0
    existing_queue_count = 0

    for source, queue_root in known_incoming_roots(workbench_root=workbench_root).items():
        entry: dict[str, Any] = {
            "source": source,
            "queue_root": str(queue_root),
            "exists": queue_root.exists(),
            "pending_snapshot_count": 0,
            "oldest_pending_at_utc": None,
            "newest_pending_at_utc": None,
            "oldest_pending_age_minutes": None,
            "top_subjects": [],
            "sample_cycle_ids": [],
        }
        if not queue_root.exists():
            if source != LEGACY_QUEUE:
                alerts.append(
                    _alert(
                        level="warning",
                        code="missing_queue_dir",
                        message=f"Queue directory is missing: {queue_root}",
                        source=source,
                    )
                )
            status[source] = entry
            continue

        existing_queue_count += 1
        snapshots = sorted(queue_root.glob("*.snapshot.json"), key=lambda path: (path.stat().st_mtime, path.name))
        payloads = [_snapshot_descriptor(path) for path in snapshots]
        entry["pending_snapshot_count"] = len(payloads)
        total_pending += len(payloads)
        if payloads:
            oldest = payloads[0]
            newest = payloads[-1]
            oldest_seen = _datetime_from_epoch(oldest["modified_epoch"])
            newest_seen = _datetime_from_epoch(newest["modified_epoch"])
            oldest_age_minutes = int((now - oldest_seen).total_seconds() // 60)
            entry["oldest_pending_at_utc"] = _isoformat_utc(oldest_seen)
            entry["newest_pending_at_utc"] = _isoformat_utc(newest_seen)
            entry["oldest_pending_age_minutes"] = oldest_age_minutes
            entry["sample_cycle_ids"] = [str(item["cycle_id"]) for item in payloads[:DEFAULT_SAMPLE_LIMIT]]
            subject_counts = Counter(str(item["subject"]) for item in payloads if str(item["subject"]).strip())
            entry["top_subjects"] = [
                {"subject": subject, "count": count}
                for subject, count in subject_counts.most_common(DEFAULT_TOP_SUBJECT_LIMIT)
            ]
            if oldest_age_minutes >= critical_age_minutes:
                alerts.append(
                    _alert(
                        level="critical",
                        code="stale_pending",
                        message=f"Oldest pending snapshot in {source} queue is {oldest_age_minutes} minutes old.",
                        source=source,
                    )
                )
            elif oldest_age_minutes >= warning_age_minutes:
                alerts.append(
                    _alert(
                        level="warning",
                        code="stale_pending",
                        message=f"Oldest pending snapshot in {source} queue is {oldest_age_minutes} minutes old.",
                        source=source,
                    )
                )
        if source == LEGACY_QUEUE and entry["pending_snapshot_count"] > 0:
            alerts.append(
                _alert(
                    level="warning",
                    code="legacy_backlog_present",
                    message=f"Legacy queue still has {entry['pending_snapshot_count']} pending snapshots.",
                    source=source,
                )
            )
        status[source] = entry

    if status.get(LEGACY_QUEUE, {}).get("pending_snapshot_count", 0) > 0 and (
        not status.get(QUANT_QUEUE, {}).get("exists") or not status.get(STRUCTURAL_QUEUE, {}).get("exists")
    ):
        alerts.append(
            _alert(
                level="warning",
                code="rollout_mismatch",
                message="Legacy backlog exists while one or both new intake queues are still missing.",
                source="queue_rollout",
            )
        )

    status["total_pending_snapshot_count"] = int(total_pending)
    status["existing_queue_count"] = int(existing_queue_count)
    return status, alerts


def _collect_quant_governance_status(*, quant_artifacts_root: Path) -> dict[str, Any]:
    summary_path = _latest_quant_governance_summary_path(quant_artifacts_root=quant_artifacts_root)
    if summary_path is None:
        return {"status": "missing"}
    latest = _read_json(summary_path)
    return {
        "status": "present",
        "summary_path": str(summary_path),
        "as_of": latest.get("as_of", latest.get("week_of")),
        "run_id": latest.get("run_id"),
        "week_of": latest.get("week_of"),
        "proposal_lane_mix": dict(latest.get("proposal_lane_mix") or {}),
        "agent_parse_success_rate": float(latest.get("agent_parse_success_rate", 0.0) or 0.0),
        "agent_quarantine_rate": float(latest.get("agent_quarantine_rate", 0.0) or 0.0),
        "agent_api_failure_rate": float(latest.get("agent_api_failure_rate", 0.0) or 0.0),
        "registry_growth": dict(latest.get("registry_growth") or {}),
        "auto_bridged_snapshot_count": int(latest.get("auto_bridged_snapshot_count", 0) or 0),
        "downstream_acceptance_count": int(latest.get("downstream_acceptance_count", 0) or 0),
        "openai_usage": dict(latest.get("openai_usage") or {}),
    }


def _latest_quant_governance_summary_path(*, quant_artifacts_root: Path) -> Path | None:
    discovery_paths = sorted((quant_artifacts_root / "governance" / "discovery_runs").glob("*/*/discovery_governance_summary.json"))
    if discovery_paths:
        return discovery_paths[-1]
    weekly_paths = sorted((quant_artifacts_root / "governance" / "weekly_reviews").glob("*/weekly_governance_summary.json"))
    return weekly_paths[-1] if weekly_paths else None


def _collect_producer_status(
    *,
    workbench_root: Path,
    quant_artifacts_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    alerts: list[dict[str, Any]] = []
    structural = _collect_structural_producer_status(workbench_root=workbench_root)
    quant = _collect_quant_producer_status(workbench_root=workbench_root, quant_artifacts_root=quant_artifacts_root)
    alerts.extend(structural.pop("alerts"))
    alerts.extend(quant.pop("alerts"))
    return {"structural": structural, "quant": quant}, alerts


def _collect_structural_producer_status(*, workbench_root: Path) -> dict[str, Any]:
    expected_root = incoming_queue_root(workbench_root=workbench_root, source=STRUCTURAL_QUEUE).resolve()
    summary_path = _latest_json_file(workbench_root / "_scan_runs", "*/scan_summary.json")
    status: dict[str, Any] = {
        "available": summary_path is not None,
        "summary_path": None if summary_path is None else str(summary_path),
        "status": "missing" if summary_path is None else "success",
        "scan_id": None,
        "scan_date": None,
        "generated_at_utc": None,
        "selected_snapshot_count": 0,
        "incoming_root": str(expected_root),
        "source": STRUCTURAL_QUEUE,
        "selected_snapshot_cycle_ids": [],
        "alerts": [],
    }
    if summary_path is None:
        return status

    payload = _read_json(summary_path)
    generated_at = _summary_timestamp(payload=payload, path=summary_path)
    incoming_root_text = str(payload.get("incoming_root", "")).strip()
    actual_incoming_root = Path(incoming_root_text).expanduser().resolve() if incoming_root_text else expected_root
    selected_snapshots = list(payload.get("selected_snapshots", [])) if isinstance(payload.get("selected_snapshots"), list) else []
    status.update(
        {
            "status": str(payload.get("status", "unknown")),
            "scan_id": payload.get("scan_id"),
            "scan_date": payload.get("scan_date"),
            "generated_at_utc": _isoformat_utc(generated_at),
            "selected_snapshot_count": int(payload.get("selected_snapshot_count", len(selected_snapshots) or 0)),
            "incoming_root": str(actual_incoming_root),
            "source": str(payload.get("source", STRUCTURAL_QUEUE)),
            "selected_snapshot_cycle_ids": [str(item.get("cycle_id", "")) for item in selected_snapshots if str(item.get("cycle_id", "")).strip()],
        }
    )
    if actual_incoming_root != expected_root:
        status["alerts"].append(
            _alert(
                level="warning",
                code="structural_incoming_root_mismatch",
                message=(
                    f"Latest structural scan summary points to `{actual_incoming_root}` instead of the structural queue `{expected_root}`."
                ),
                source=STRUCTURAL_QUEUE,
            )
        )
    missing_evidence = []
    for item in selected_snapshots:
        if not _producer_snapshot_evidence_exists(
            workbench_root=workbench_root,
            source=STRUCTURAL_QUEUE,
            snapshot_path=item.get("snapshot_path"),
            cycle_id=item.get("cycle_id"),
            object_id=item.get("object_id"),
        ):
            missing_evidence.append(str(item.get("cycle_id", "")))
    if missing_evidence:
        status["alerts"].append(
            _alert(
                level="warning",
                code="structural_snapshot_missing",
                message=f"Latest structural scan references snapshots with no queue/archive/cycle evidence: {', '.join(missing_evidence)}.",
                source=STRUCTURAL_QUEUE,
            )
        )
    return status


def _collect_quant_producer_status(*, workbench_root: Path, quant_artifacts_root: Path) -> dict[str, Any]:
    summary_path = _latest_json_file(quant_artifacts_root / "bridge_exports", "*/bridge_summary.json")
    status: dict[str, Any] = {
        "available": summary_path is not None,
        "summary_path": None if summary_path is None else str(summary_path),
        "status": "missing" if summary_path is None else "success",
        "as_of": None,
        "generated_at_utc": None,
        "queue": QUANT_QUEUE,
        "queue_root": str(incoming_queue_root(workbench_root=workbench_root, source=QUANT_QUEUE)),
        "exported_snapshot_count": 0,
        "published_snapshot_count": 0,
        "staged_only_snapshot_count": 0,
        "alerts": [],
    }
    if summary_path is None:
        return status

    payload = _read_json(summary_path)
    generated_at = _summary_timestamp(payload=payload, path=summary_path)
    queue = str(payload.get("queue", QUANT_QUEUE)).strip() or QUANT_QUEUE
    try:
        expected_queue_root = incoming_queue_root(workbench_root=workbench_root, source=queue).resolve()
    except ValueError:
        expected_queue_root = (workbench_root / f"_incoming_{queue}").resolve()
    queue_root_text = str(payload.get("queue_root", "")).strip()
    actual_queue_root = Path(queue_root_text).expanduser().resolve() if queue_root_text else expected_queue_root
    exports = list(payload.get("exports", [])) if isinstance(payload.get("exports"), list) else []
    suppressed = list(payload.get("suppressed_exports", [])) if isinstance(payload.get("suppressed_exports"), list) else []
    published_snapshot_count = int(payload.get("published_snapshot_count", len(exports)))
    staged_only_snapshot_count = int(payload.get("staged_only_snapshot_count", payload.get("suppressed_snapshot_count", len(suppressed))))
    exported_snapshot_count = int(payload.get("exported_snapshot_count", published_snapshot_count + staged_only_snapshot_count))
    if exported_snapshot_count < published_snapshot_count + staged_only_snapshot_count:
        exported_snapshot_count = published_snapshot_count + staged_only_snapshot_count
    status.update(
        {
            "status": "success",
            "as_of": payload.get("as_of"),
            "generated_at_utc": _isoformat_utc(generated_at),
            "queue": queue,
            "queue_root": str(actual_queue_root),
            "export_root": payload.get("export_root"),
            "exported_snapshot_count": exported_snapshot_count,
            "published_snapshot_count": published_snapshot_count,
            "staged_only_snapshot_count": staged_only_snapshot_count,
        }
    )
    if actual_queue_root != expected_queue_root:
        status["alerts"].append(
            _alert(
                level="warning",
                code="quant_queue_root_mismatch",
                message=f"Latest quant bridge summary points to `{actual_queue_root}` instead of `{expected_queue_root}`.",
                source=queue,
            )
        )
    if published_snapshot_count > 0 and not actual_queue_root.exists():
        status["alerts"].append(
            _alert(
                level="critical",
                code="quant_queue_missing_for_published_exports",
                message=f"Latest quant bridge summary published {published_snapshot_count} snapshots, but queue directory `{actual_queue_root}` does not exist.",
                source=queue,
            )
        )
    missing_evidence = []
    for item in exports:
        if not _bridge_export_evidence_exists(workbench_root=workbench_root, queue=queue, entry=item):
            missing_evidence.append(str(item.get("experiment_id", "")))
    if missing_evidence:
        status["alerts"].append(
            _alert(
                level="warning",
                code="quant_export_missing",
                message=f"Latest quant bridge summary references published exports with no queue/archive/cycle evidence: {', '.join(missing_evidence)}.",
                source=queue,
            )
        )
    return status


def _collect_intake_status(*, workbench_root: Path, now: datetime, window_start: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    alerts: list[dict[str, Any]] = []
    intake_run_paths = sorted((workbench_root / "_intake_runs").glob("*/intake_summary.json"), key=lambda path: path.stat().st_mtime)
    latest_path = intake_run_paths[-1] if intake_run_paths else None
    latest_summary = _read_json(latest_path) if latest_path is not None else {}
    recent_summaries = []
    for path in intake_run_paths:
        timestamp = _summary_timestamp(payload=None, path=path)
        if timestamp >= window_start:
            recent_summaries.append((path, _read_json(path)))

    latest_processed_by_source = _processed_by_source(latest_summary)
    recent_processed_by_source_counter: Counter[str] = Counter()
    recent_processed_snapshot_count = 0
    for _, payload in recent_summaries:
        recent_processed_by_source_counter.update(_processed_by_source(payload))
        recent_processed_snapshot_count += int(payload.get("processed_snapshot_count", len(payload.get("processed", [])) if isinstance(payload.get("processed"), list) else 0))

    status = {
        "available": latest_path is not None,
        "latest_run": {
            "summary_path": None if latest_path is None else str(latest_path),
            "run_id": latest_summary.get("run_id"),
            "status": latest_summary.get("status", "missing" if latest_path is None else "unknown"),
            "processed_snapshot_count": int(
                latest_summary.get(
                    "processed_snapshot_count",
                    len(latest_summary.get("processed", [])) if isinstance(latest_summary.get("processed"), list) else 0,
                )
            ),
            "processed_by_source": latest_processed_by_source,
            "generated_at_utc": latest_summary.get("generated_at_utc"),
            "age_minutes": None if latest_path is None else int((now - _summary_timestamp(payload=latest_summary, path=latest_path)).total_seconds() // 60),
        },
        "recent_window_hours": int((now - window_start).total_seconds() // 3600),
        "recent_run_count": len(recent_summaries),
        "recent_processed_snapshot_count": int(recent_processed_snapshot_count),
        "recent_processed_by_source": {source: int(recent_processed_by_source_counter.get(source, 0)) for source in KNOWN_QUEUE_SOURCES},
    }
    return status, alerts


def _derive_cross_system_alerts(
    *,
    workbench_root: Path,
    queue_status: dict[str, Any],
    producer_status: dict[str, Any],
    intake_status: dict[str, Any],
    window_start: datetime,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    recent_processed_by_source = intake_status["recent_processed_by_source"]
    structural_recent = _status_generated_within_window(producer_status["structural"], window_start=window_start)
    quant_recent = _status_generated_within_window(producer_status["quant"], window_start=window_start)

    structural_selected = int(producer_status["structural"].get("selected_snapshot_count", 0))
    if structural_recent and structural_selected > 0 and int(recent_processed_by_source.get(STRUCTURAL_QUEUE, 0)) == 0:
        alerts.append(
            _alert(
                level="warning",
                code="structural_no_recent_intake",
                message="Structural producer emitted snapshots recently, but intake has not consumed any structural snapshots in the current window.",
                source=STRUCTURAL_QUEUE,
            )
        )

    quant_published = int(producer_status["quant"].get("published_snapshot_count", 0))
    if quant_recent and quant_published > 0 and int(recent_processed_by_source.get(QUANT_QUEUE, 0)) == 0:
        alerts.append(
            _alert(
                level="warning",
                code="quant_no_recent_intake",
                message="Quant producer published snapshots recently, but intake has not consumed any quant snapshots in the current window.",
                source=QUANT_QUEUE,
            )
        )

    if (
        int(recent_processed_by_source.get(LEGACY_QUEUE, 0)) > 0
        and int(recent_processed_by_source.get(STRUCTURAL_QUEUE, 0)) == 0
        and int(recent_processed_by_source.get(QUANT_QUEUE, 0)) == 0
        and (
            int(queue_status[STRUCTURAL_QUEUE].get("pending_snapshot_count", 0)) > 0
            or int(queue_status[QUANT_QUEUE].get("pending_snapshot_count", 0)) > 0
            or (structural_recent and structural_selected > 0)
            or (quant_recent and quant_published > 0)
        )
    ):
        alerts.append(
            _alert(
                level="warning",
                code="legacy_only_intake",
                message="Recent intake throughput is legacy-only while quant/structural work is present or being produced.",
                source=LEGACY_QUEUE,
            )
        )
    return alerts


def _processed_by_source(payload: dict[str, Any]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    processed = payload.get("processed", [])
    if isinstance(processed, list):
        for item in processed:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            if source in KNOWN_QUEUE_SOURCES:
                counter[source] += 1
    return {source: int(counter.get(source, 0)) for source in KNOWN_QUEUE_SOURCES}


def _snapshot_descriptor(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    return {
        "path": str(path),
        "cycle_id": str(payload.get("cycle_id", "")).strip() or path.stem.replace(".snapshot", ""),
        "object_id": str(payload.get("object_id", "")).strip(),
        "subject": str(payload.get("subject", "")).strip().upper(),
        "modified_epoch": float(path.stat().st_mtime),
    }


def _producer_snapshot_evidence_exists(
    *,
    workbench_root: Path,
    source: str,
    snapshot_path: Any,
    cycle_id: Any,
    object_id: Any,
) -> bool:
    cycle_id_text = str(cycle_id or "").strip()
    object_id_text = str(object_id or "").strip()
    if snapshot_path:
        path = Path(str(snapshot_path)).expanduser()
        if path.exists():
            return True
    if cycle_id_text:
        archive_path = consumed_archive_root(workbench_root=workbench_root, source=source) / f"{cycle_id_text}.snapshot.json"
        if archive_path.exists():
            return True
    if cycle_id_text and object_id_text and (workbench_root / object_id_text / "cycles" / cycle_id_text / "cycle_summary.json").exists():
        return True
    return False


def _bridge_export_evidence_exists(*, workbench_root: Path, queue: str, entry: dict[str, Any]) -> bool:
    if not bool(entry.get("published_to_intake", True)):
        return True
    queue_path = entry.get("queue_path")
    if queue_path and Path(str(queue_path)).expanduser().exists():
        return True
    archive_path = entry.get("archive_path")
    if archive_path and Path(str(archive_path)).expanduser().exists():
        return True
    cycle_id = str(entry.get("cycle_id", "")).strip()
    object_id = str(entry.get("object_id", "")).strip()
    if cycle_id and object_id and (workbench_root / object_id / "cycles" / cycle_id / "cycle_summary.json").exists():
        return True
    if cycle_id:
        consumed_path = consumed_archive_root(workbench_root=workbench_root, source=queue) / f"{cycle_id}.snapshot.json"
        if consumed_path.exists():
            return True
    return False


def _latest_json_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def _summary_timestamp(*, payload: dict[str, Any] | None, path: Path) -> datetime:
    payload = payload or _read_json(path)
    generated_at_utc = str(payload.get("generated_at_utc", "")).strip()
    if generated_at_utc:
        parsed = _parse_utc_timestamp(generated_at_utc)
        if parsed is not None:
            return parsed
    return _datetime_from_epoch(path.stat().st_mtime)


def _status_generated_within_window(status: dict[str, Any], *, window_start: datetime) -> bool:
    generated_at_utc = str(status.get("generated_at_utc", "")).strip()
    if not generated_at_utc:
        return False
    parsed = _parse_utc_timestamp(generated_at_utc)
    if parsed is None:
        return False
    return parsed >= window_start


def _parse_utc_timestamp(value: str) -> datetime | None:
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _datetime_from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _alert(*, level: str, code: str, message: str, source: str | None = None) -> dict[str, Any]:
    payload = {"level": level, "code": code, "message": message}
    if source is not None:
        payload["source"] = source
    return payload


def _sort_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    level_order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(
        alerts,
        key=lambda item: (
            level_order.get(str(item.get("level", "warning")), 9),
            str(item.get("source", "")),
            str(item.get("code", "")),
            str(item.get("message", "")),
        ),
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
