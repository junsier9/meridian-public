from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import read_json, write_json


PASSED_MONITOR_STATUS = "passed_live_position_monitor"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill a direct mainnet delta execution with an explicit post-trade "
            "position-monitor reconcile artifact. Default mode is dry-run."
        )
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--delta-run", required=True, help="Direct mainnet_delta_execution artifact root.")
    parser.add_argument("--position-monitor-run", required=True, help="Position monitor artifact root.")
    parser.add_argument("--expected-position-monitor-sha256", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_delta_post_trade_reconcile_backfill(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_delta_post_trade_reconcile_backfill(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    clock = now_fn or (lambda: datetime.now(UTC))
    started = clock()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(str(getattr(args, "config", "")))
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-delta-post-trade-reconcile-backfill"
    run_root = live_config.artifact_root.parent / "delta_post_trade_reconcile_backfill" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    apply = bool(getattr(args, "apply", False))
    blockers: list[str] = []

    delta_root = resolve_repo_path(str(getattr(args, "delta_run", "") or ""))
    monitor_root = resolve_repo_path(str(getattr(args, "position_monitor_run", "") or ""))
    delta_summary_path = delta_root / "run_summary.json"
    delta_reconciliation_path = delta_root / "reconciliation.json"
    monitor_summary_path = monitor_root / "run_summary.json"
    monitor_report_path = monitor_root / "monitor_report.json"

    delta_summary = _read_json_or_block(delta_summary_path, blockers, "delta_run_summary")
    delta_reconciliation = _read_json_or_block(delta_reconciliation_path, blockers, "delta_reconciliation")
    monitor_summary = _read_json_or_block(monitor_summary_path, blockers, "position_monitor_summary")
    monitor_report = _read_optional_json(monitor_report_path)
    db_payload = _read_db_run_summary(state_store.path, str(delta_summary.get("run_id") or delta_root.name), blockers)

    blockers.extend(
        _validation_blockers(
            delta_root=delta_root,
            monitor_root=monitor_root,
            delta_summary=delta_summary,
            delta_reconciliation=delta_reconciliation,
            monitor_summary=monitor_summary,
            monitor_report=monitor_report,
            db_payload=db_payload,
            expected_monitor_sha=str(getattr(args, "expected_position_monitor_sha256", "") or ""),
        )
    )

    post_trade_reconcile = _post_trade_reconcile_record(
        run_id=run_id,
        checked_at=started,
        delta_root=delta_root,
        monitor_root=monitor_root,
        monitor_summary=monitor_summary,
        monitor_summary_path=monitor_summary_path,
    )
    updated_delta_summary = dict(delta_summary)
    updated_delta_summary["post_trade_reconcile"] = post_trade_reconcile
    updated_delta_summary["post_trade_reconcile_status"] = PASSED_MONITOR_STATUS
    updated_delta_summary["post_trade_reconcile_artifacts"] = {
        "artifact_root": str(monitor_root),
        "run_summary": str(monitor_summary_path),
        "run_summary_sha256": _sha256_or_empty(monitor_summary_path),
        "monitor_report": str(monitor_report_path) if monitor_report_path.exists() else "",
        "monitor_report_sha256": _sha256_or_empty(monitor_report_path),
    }

    write_json(run_root / "candidate_delta_run_summary.json", updated_delta_summary)

    applied = False
    backup_path = ""
    if not blockers and apply:
        backup = delta_summary_path.with_name(f"run_summary.pre_post_trade_backfill_{run_id}.json")
        if not backup.exists():
            shutil.copy2(delta_summary_path, backup)
        backup_path = str(backup)
        write_json(delta_summary_path, updated_delta_summary)
        _update_db_run_summary(state_store.path, str(delta_summary.get("run_id") or delta_root.name), updated_delta_summary)
        state_store.record_live_artifact(
            run_id=str(delta_summary.get("run_id") or delta_root.name),
            artifact_type="post_trade_reconcile_backfill",
            artifact_id=f"{delta_summary.get('run_id') or delta_root.name}:post_trade_reconcile_backfill:{run_id}",
            payload={
                "backfill_run_id": run_id,
                "backfill_artifact_root": str(run_root),
                "delta_run_root": str(delta_root),
                "position_monitor_root": str(monitor_root),
                "post_trade_reconcile": post_trade_reconcile,
                "backup_path": backup_path,
            },
        )
        applied = True

    status = "delta_post_trade_reconcile_backfill_blocked"
    if not blockers:
        status = "delta_post_trade_reconcile_backfill_applied" if applied else "delta_post_trade_reconcile_backfill_ready"
    summary = {
        "run_id": run_id,
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "apply": apply,
        "applied": applied,
        "artifact_root": str(run_root),
        "sqlite_path": str(live_config.sqlite_path),
        "delta_run_root": str(delta_root),
        "position_monitor_root": str(monitor_root),
        "delta_run_id": str(delta_summary.get("run_id") or delta_root.name),
        "position_monitor_run_id": str(monitor_summary.get("run_id") or monitor_root.name),
        "post_trade_reconcile_status": PASSED_MONITOR_STATUS if not blockers else "",
        "backup_path": backup_path,
        "orders_submitted": int(float(delta_summary.get("submitted_order_count") or 0)),
        "fill_count": int(float(delta_summary.get("fill_count") or 0)),
    }
    write_json(run_root / "run_summary.json", summary)
    return summary, 0 if not blockers else 2


def _read_json_or_block(path: Path, blockers: list[str], label: str) -> dict[str, Any]:
    if not path.exists():
        blockers.append(f"{label}_missing:{path}")
        return {}
    try:
        return dict(read_json(path))
    except Exception as exc:  # noqa: BLE001 - fail closed with retained blocker details.
        blockers.append(f"{label}_unreadable:{exc.__class__.__name__}")
        return {}


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return dict(read_json(path))
    except Exception:
        return {}


def _read_db_run_summary(path: Path, run_id: str, blockers: list[str]) -> dict[str, Any]:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT payload_json FROM run_summaries WHERE run_id = ?", (str(run_id),)).fetchone()
    if row is None:
        blockers.append(f"delta_run_summary_missing_in_sqlite:{run_id}")
        return {}
    try:
        return dict(json.loads(str(row[0])))
    except json.JSONDecodeError:
        blockers.append(f"delta_run_summary_unreadable_in_sqlite:{run_id}")
        return {}


def _update_db_run_summary(path: Path, run_id: str, payload: dict[str, Any]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE run_summaries SET payload_json = ? WHERE run_id = ?",
            (json.dumps(payload, sort_keys=True, default=str), str(run_id)),
        )


def _validation_blockers(
    *,
    delta_root: Path,
    monitor_root: Path,
    delta_summary: dict[str, Any],
    delta_reconciliation: dict[str, Any],
    monitor_summary: dict[str, Any],
    monitor_report: dict[str, Any],
    db_payload: dict[str, Any],
    expected_monitor_sha: str,
) -> list[str]:
    blockers: list[str] = []
    delta_run_id = str(delta_summary.get("run_id") or delta_root.name)
    if str(delta_summary.get("status") or "") != "mainnet_delta_orders_submitted":
        blockers.append(f"delta_status_not_orders_submitted:{delta_summary.get('status') or 'missing'}")
    submitted = int(float(delta_summary.get("submitted_order_count") or 0))
    fills = int(float(delta_summary.get("fill_count") or 0))
    if submitted <= 0:
        blockers.append("delta_submitted_order_count_missing")
    if fills <= 0 or fills != submitted:
        blockers.append(f"delta_fill_count_mismatch:{fills}!={submitted}")
    if str(delta_summary.get("reconciliation_status") or "") != "reconciled":
        blockers.append(f"delta_summary_reconciliation_not_reconciled:{delta_summary.get('reconciliation_status') or 'missing'}")
    if str(delta_reconciliation.get("status") or "") != "reconciled":
        blockers.append(f"delta_reconciliation_artifact_not_reconciled:{delta_reconciliation.get('status') or 'missing'}")
    existing_post = str(
        dict(delta_summary.get("post_trade_reconcile") or {}).get("status")
        or delta_summary.get("post_trade_reconcile_status")
        or ""
    ).strip()
    if existing_post and existing_post != PASSED_MONITOR_STATUS and not existing_post.startswith("direct_delta_"):
        blockers.append(f"delta_existing_post_trade_reconcile_status_unexpected:{existing_post}")

    if db_payload:
        db_submitted = int(float(db_payload.get("submitted_order_count") or 0))
        db_fills = int(float(db_payload.get("fill_count") or 0))
        if db_submitted != submitted or db_fills != fills:
            blockers.append(f"sqlite_delta_count_mismatch:{db_submitted}/{db_fills}!={submitted}/{fills}")

    if str(monitor_summary.get("status") or "") != PASSED_MONITOR_STATUS:
        blockers.append(f"position_monitor_not_passed:{monitor_summary.get('status') or 'missing'}")
    if int(float(monitor_summary.get("open_order_count") or 0)) != 0:
        blockers.append(f"position_monitor_open_orders:{monitor_summary.get('open_order_count')}")
    monitor_reference = str(monitor_summary.get("reference_run") or "").strip()
    if monitor_reference and not _same_reference(monitor_reference, delta_root):
        blockers.append(f"position_monitor_reference_mismatch:{monitor_reference}!={delta_root}")
    if monitor_report:
        if monitor_report.get("read_only") is not True:
            blockers.append("position_monitor_report_not_read_only")
        side_effects = dict(monitor_report.get("side_effects") or {})
        for key in ("orders_submitted", "orders_canceled", "order_test_calls", "account_settings_changed"):
            if int(float(side_effects.get(key) or 0)) != 0:
                blockers.append(f"position_monitor_side_effect_{key}:{side_effects.get(key)}")
        if side_effects and side_effects.get("only_http_get_endpoints") is not True:
            blockers.append("position_monitor_not_get_only")

    delta_finished = _parse_utc(delta_summary.get("finished_at_utc"))
    monitor_started = _parse_utc(monitor_summary.get("started_at_utc"))
    if delta_finished and monitor_started and monitor_started < delta_finished:
        blockers.append(
            "position_monitor_started_before_delta_finished:"
            f"{monitor_started.isoformat()}<{delta_finished.isoformat()}"
        )
    if expected_monitor_sha:
        actual = _sha256_or_empty(monitor_root / "run_summary.json")
        if actual != expected_monitor_sha:
            blockers.append(f"position_monitor_sha256_mismatch:{actual}!={expected_monitor_sha}")
    if delta_run_id and str(db_payload.get("run_id") or delta_run_id) != delta_run_id:
        blockers.append(f"sqlite_delta_run_id_mismatch:{db_payload.get('run_id')}!={delta_run_id}")
    return blockers


def _post_trade_reconcile_record(
    *,
    run_id: str,
    checked_at: datetime,
    delta_root: Path,
    monitor_root: Path,
    monitor_summary: dict[str, Any],
    monitor_summary_path: Path,
) -> dict[str, Any]:
    return {
        "status": PASSED_MONITOR_STATUS,
        "source": "delta_post_trade_reconcile_backfill",
        "accepted_by_prior_live_submission_gate": True,
        "backfill_run_id": run_id,
        "checked_at_utc": checked_at.isoformat().replace("+00:00", "Z"),
        "delta_run_root": str(delta_root),
        "position_monitor_run_id": str(monitor_summary.get("run_id") or monitor_root.name),
        "position_monitor_artifact_root": str(monitor_root),
        "position_monitor_run_summary": str(monitor_summary_path),
        "position_monitor_run_summary_sha256": _sha256_or_empty(monitor_summary_path),
        "blockers": [],
    }


def _same_reference(reference: str, delta_root: Path) -> bool:
    ref_path = Path(reference)
    if str(ref_path) == str(delta_root):
        return True
    try:
        if ref_path.exists() and delta_root.exists() and ref_path.resolve() == delta_root.resolve():
            return True
    except OSError:
        pass
    return ref_path.name == delta_root.name


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sha256_or_empty(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
