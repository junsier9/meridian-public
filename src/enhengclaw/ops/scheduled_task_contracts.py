from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any


REQUIRED_SUMMARY_FIELDS = (
    "task_key",
    "task_name",
    "exit_status",
    "success",
    "produced_at_utc",
    "source_commit_sha",
    "artifact_family",
    "input_watermarks",
    "upstream_versions",
)

WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def load_scheduled_task_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def tasks_by_key(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(task["task_key"]): task
        for task in manifest.get("tasks", [])
        if isinstance(task, dict) and str(task.get("task_key", "")).strip()
    }


def task_registration(task_entry: dict[str, Any]) -> dict[str, Any]:
    registration = task_entry.get("registration") or {}
    return {
        "principal_mode": str(registration.get("principal_mode", "interactive")),
        "run_level": str(registration.get("run_level", "limited")),
    }


def task_resilience(task_entry: dict[str, Any]) -> dict[str, Any]:
    resilience = task_entry.get("resilience") or {}
    return {
        "wake_to_run": bool(resilience.get("wake_to_run", False)),
        "restart_count": int(resilience.get("restart_count", 0)),
        "restart_interval_minutes": int(resilience.get("restart_interval_minutes", 0)),
        "startup_catchup_enabled": bool(resilience.get("startup_catchup_enabled", False)),
        "startup_delay_minutes": int(resilience.get("startup_delay_minutes", 0)),
    }


def validate_scheduled_task_summary(summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for field_name in REQUIRED_SUMMARY_FIELDS:
        if field_name not in summary:
            blockers.append(f"summary missing required field: {field_name}")
    if "success" in summary and type(summary.get("success")) is not bool:
        blockers.append("summary field 'success' must be a boolean")
    if "input_watermarks" in summary and not isinstance(summary.get("input_watermarks"), dict):
        blockers.append("summary field 'input_watermarks' must be an object")
    if "upstream_versions" in summary and not isinstance(summary.get("upstream_versions"), dict):
        blockers.append("summary field 'upstream_versions' must be an object")
    return blockers


def evaluate_task_readiness(
    *,
    task_key: str,
    manifest: dict[str, Any],
    summaries_by_task_key: dict[str, dict[str, Any]],
    now_utc: str,
) -> dict[str, Any]:
    task_map = tasks_by_key(manifest)
    task_entry = task_map[str(task_key)]
    blockers = _summary_blockers(task_key=task_key, summary=summaries_by_task_key.get(task_key), task_entry=task_entry, now_utc=now_utc)
    current_summary = summaries_by_task_key.get(task_key)
    watermark_map = {} if not isinstance(current_summary, dict) else dict(current_summary.get("input_watermarks") or {})
    for dependency_key in task_entry.get("upstream_dependencies", []):
        dependency_entry = task_map.get(str(dependency_key))
        dependency_summary = summaries_by_task_key.get(str(dependency_key))
        if dependency_entry is None or dependency_summary is None:
            blockers.append(f"upstream dependency summary missing: {dependency_key}")
            continue
        blockers.extend(
            _summary_blockers(
                task_key=str(dependency_key),
                summary=dependency_summary,
                task_entry=dependency_entry,
                now_utc=now_utc,
            )
        )
        watermark_key = f"{dependency_key}_produced_at_utc"
        expected_watermark = str(watermark_map.get(watermark_key, "")).strip()
        actual_watermark = str(dependency_summary.get("produced_at_utc", "")).strip()
        if expected_watermark and actual_watermark and expected_watermark != actual_watermark:
            blockers.append(
                f"upstream watermark mismatch for {dependency_key}: "
                f"summary={expected_watermark} current={actual_watermark}"
            )
    return {
        "task_key": task_key,
        "status": "passed" if not blockers else "failed",
        "blockers": blockers,
    }


def evaluate_upstream_dependency_status(
    *,
    task_key: str,
    manifest: dict[str, Any],
    summaries_by_task_key: dict[str, dict[str, Any]],
    now_utc: str,
) -> dict[str, Any]:
    task_map = tasks_by_key(manifest)
    task_entry = task_map[str(task_key)]
    dependency_statuses: dict[str, str] = {}
    blockers: list[str] = []
    overall_status = "ready"
    for dependency_key in task_entry.get("upstream_dependencies", []):
        dependency_entry = task_map.get(str(dependency_key))
        dependency_summary = summaries_by_task_key.get(str(dependency_key))
        if dependency_entry is None or dependency_summary is None:
            dependency_statuses[str(dependency_key)] = "missing"
            blockers.append(f"upstream dependency summary missing: {dependency_key}")
            overall_status = "missing"
            continue
        dependency_blockers = _summary_blockers(
            task_key=str(dependency_key),
            summary=dependency_summary,
            task_entry=dependency_entry,
            now_utc=now_utc,
        )
        if dependency_blockers:
            dependency_statuses[str(dependency_key)] = "stale"
            blockers.extend(dependency_blockers)
            if overall_status != "missing":
                overall_status = "stale"
            continue
        dependency_statuses[str(dependency_key)] = "ready"
    return {
        "task_key": task_key,
        "status": overall_status,
        "dependencies": dependency_statuses,
        "blockers": blockers,
    }


def evaluate_startup_catchup(
    *,
    task_entry: dict[str, Any],
    current_summary: dict[str, Any] | None,
    now_local: str,
) -> dict[str, Any]:
    now_dt = _parse_local(now_local)
    expected_interval = str(task_entry.get("expected_interval", ""))
    schedule = task_entry.get("schedule") or {}
    success_local = _successful_produced_at_local(current_summary, now_dt)

    if expected_interval == "hourly":
        if current_summary is None:
            return {"should_run": True, "reason": "summary_missing"}
        if success_local is None:
            return {"should_run": True, "reason": "last_run_not_successful"}
        produced_at = _parse_utc(str(current_summary.get("produced_at_utc", "")))
        age_hours = (_parse_utc(now_local) - produced_at).total_seconds() / 3600.0
        freshness_budget = float(task_entry.get("freshness_budget_hours", 0))
        if age_hours > freshness_budget:
            return {"should_run": True, "reason": "stale_summary"}
        return {"should_run": False, "reason": "summary_fresh"}

    schedule_type = str(schedule.get("type", ""))
    if schedule_type == "daily":
        scheduled_at = _replace_time(now_dt, str(schedule["time"]))
        if now_dt < scheduled_at:
            return {"should_run": False, "reason": "scheduled_time_not_reached"}
        if success_local is not None and success_local.date() == now_dt.date():
            return {"should_run": False, "reason": "already_succeeded_today"}
        return {"should_run": True, "reason": "scheduled_window_missed"}

    if schedule_type == "weekly":
        week_start = _week_start(now_dt)
        due_times = []
        for day_name in schedule.get("days_of_week", []):
            if str(day_name) not in WEEKDAY_INDEX:
                continue
            due_times.append(_replace_time(week_start + timedelta(days=WEEKDAY_INDEX[str(day_name)]), str(schedule["time"])))
        due_this_week = [candidate for candidate in due_times if candidate <= now_dt]
        if not due_this_week:
            return {"should_run": False, "reason": "scheduled_weekly_window_not_reached"}
        if success_local is not None and success_local >= week_start:
            return {"should_run": False, "reason": "already_succeeded_this_week"}
        return {"should_run": True, "reason": "scheduled_weekly_window_missed"}

    return {"should_run": False, "reason": "unsupported_catchup_schedule"}


def _summary_blockers(
    *,
    task_key: str,
    summary: dict[str, Any] | None,
    task_entry: dict[str, Any],
    now_utc: str,
) -> list[str]:
    if summary is None:
        return [f"summary missing for task: {task_key}"]
    blockers = validate_scheduled_task_summary(summary)
    if blockers:
        return blockers
    if not bool(summary.get("success")):
        blockers.append(f"task summary not successful: {task_key}")
    produced_at = _parse_utc(str(summary.get("produced_at_utc")))
    age_hours = (_parse_utc(now_utc) - produced_at).total_seconds() / 3600.0
    max_age_hours = float(task_entry.get("freshness_budget_hours", 0))
    if age_hours > max_age_hours:
        blockers.append(
            f"task summary is stale for {task_key}: age_hours={age_hours:.3f} max={max_age_hours:.3f}"
        )
    return blockers


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_local(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    return parsed


def _successful_produced_at_local(summary: dict[str, Any] | None, now_local: datetime) -> datetime | None:
    if summary is None or not bool(summary.get("success")):
        return None
    produced_at = str(summary.get("produced_at_utc", "")).strip()
    if not produced_at:
        return None
    parsed = datetime.fromisoformat(produced_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    if now_local.tzinfo is None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed.astimezone(now_local.tzinfo)


def _replace_time(base: datetime, clock: str) -> datetime:
    hour, minute = [int(part) for part in clock.split(":", 1)]
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _week_start(now_local: datetime) -> datetime:
    return now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_local.weekday())
