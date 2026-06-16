from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enhengclaw.quant_research.contracts import utc_now


SCHEMA_VERSION = 8


def _expanded_run_id_set(values: list[str] | tuple[str, ...] | set[str] | None = None) -> set[str]:
    expanded: set[str] = set()
    for raw in list(values or []):
        for item in str(raw or "").split(","):
            text = item.strip()
            if text:
                expanded.add(text)
    return expanded


class LiveTradingStateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS run_summaries (run_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS decision_snapshots (decision_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS target_portfolios (portfolio_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS risk_gate_results (risk_gate_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS execution_plans (plan_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS paper_executions (plan_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS paper_orders (paper_order_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS paper_fills (paper_fill_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, symbol TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS paper_positions (symbol TEXT PRIMARY KEY, position_amt REAL NOT NULL, updated_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS heartbeats (run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, status TEXT NOT NULL, started_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, finished_at_utc TEXT, artifact_root TEXT, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS operator_actions (action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, action_type TEXT NOT NULL, status TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS operator_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS live_artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, artifact_type TEXT NOT NULL, created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS multiphase_sleeve_targets (sleeve_id TEXT PRIMARY KEY, strategy_label TEXT NOT NULL, phase_offset_days INTEGER NOT NULL, decision_time_ms INTEGER, decision_date_utc TEXT, updated_at_utc TEXT NOT NULL, status TEXT NOT NULL, target_positions_json TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rebalance_slot_targets (slot_id TEXT PRIMARY KEY, target_engine TEXT NOT NULL, strategy_label TEXT NOT NULL, status TEXT NOT NULL, target_hash TEXT NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, completed_at_utc TEXT, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def write_json_row(self, table: str, key_column: str, key_value: str, payload: dict[str, Any]) -> None:
        if table not in {
            "run_summaries",
            "decision_snapshots",
            "target_portfolios",
            "risk_gate_results",
            "execution_plans",
        }:
            raise ValueError(f"unsupported live trading state table: {table}")
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {table}({key_column}, created_at_utc, payload_json) VALUES (?, ?, ?)",
                (key_value, utc_now(), json.dumps(payload, sort_keys=True, default=str)),
            )

    def record_live_artifact(
        self,
        *,
        run_id: str,
        artifact_type: str,
        artifact_id: str | None = None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        created_at = utc_now()
        safe_type = str(artifact_type).strip().lower().replace(" ", "_")
        record_id = str(artifact_id or f"{run_id}:{safe_type}:{created_at}")
        record = {
            "artifact_id": record_id,
            "run_id": str(run_id),
            "artifact_type": safe_type,
            "created_at_utc": created_at,
            "payload": dict(payload),
        }
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO live_artifacts(artifact_id, run_id, artifact_type, created_at_utc, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    record_id,
                    str(run_id),
                    safe_type,
                    created_at,
                    json.dumps(record, sort_keys=True, default=str),
                ),
            )
        return record

    def write_multiphase_sleeve_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        updated_at = utc_now()
        strategy_label = str(payload.get("strategy_label") or "hv_balanced")
        phase_offset = int(payload.get("phase_offset_days") or 0)
        sleeve_id = str(payload.get("sleeve_id") or f"{strategy_label}:phase:{phase_offset}")
        target_positions = list(payload.get("target_positions") or [])
        record = {
            **dict(payload),
            "sleeve_id": sleeve_id,
            "strategy_label": strategy_label,
            "phase_offset_days": phase_offset,
            "updated_at_utc": updated_at,
        }
        decision_time = record.get("decision_time_ms")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO multiphase_sleeve_targets(sleeve_id, strategy_label, phase_offset_days, decision_time_ms, decision_date_utc, updated_at_utc, status, target_positions_json, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sleeve_id,
                    strategy_label,
                    phase_offset,
                    int(decision_time) if decision_time is not None else None,
                    str(record.get("decision_date_utc") or ""),
                    updated_at,
                    str(record.get("status") or "unknown"),
                    json.dumps(target_positions, sort_keys=True, default=str),
                    json.dumps(record, sort_keys=True, default=str),
                ),
            )
        return record

    def read_multiphase_sleeve_targets(self, *, strategy_label: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            if strategy_label:
                rows = conn.execute(
                    "SELECT payload_json FROM multiphase_sleeve_targets WHERE strategy_label = ? ORDER BY phase_offset_days",
                    (str(strategy_label),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM multiphase_sleeve_targets ORDER BY strategy_label, phase_offset_days"
                ).fetchall()
        output: list[dict[str, Any]] = []
        for (payload_json,) in rows:
            try:
                output.append(dict(json.loads(str(payload_json))))
            except json.JSONDecodeError:
                continue
        return output

    def write_rebalance_slot_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        now = utc_now()
        slot_id = str(payload.get("slot_id") or "").strip()
        if not slot_id:
            raise ValueError("rebalance slot target requires slot_id")
        record = dict(payload)
        record.setdefault("status", "open")
        record.setdefault("created_at_utc", now)
        record["updated_at_utc"] = now
        target_engine = str(record.get("target_engine") or "")
        strategy_label = str(record.get("strategy_label") or "")
        target_hash = str(record.get("target_hash") or "")
        status = str(record.get("status") or "open")
        with sqlite3.connect(self.path) as conn:
            existing = conn.execute(
                "SELECT payload_json FROM rebalance_slot_targets WHERE slot_id = ?",
                (slot_id,),
            ).fetchone()
            if existing:
                try:
                    previous = dict(json.loads(str(existing[0])))
                except json.JSONDecodeError:
                    previous = {}
                if previous.get("created_at_utc") and not payload.get("created_at_utc"):
                    record["created_at_utc"] = previous["created_at_utc"]
                if previous.get("completed_at_utc") and not payload.get("completed_at_utc"):
                    record["completed_at_utc"] = previous["completed_at_utc"]
                if str(previous.get("status") or "") == "completed" and status == "open":
                    record["status"] = "completed"
                    status = "completed"
            conn.execute(
                "INSERT OR REPLACE INTO rebalance_slot_targets(slot_id, target_engine, strategy_label, status, target_hash, created_at_utc, updated_at_utc, completed_at_utc, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slot_id,
                    target_engine,
                    strategy_label,
                    status,
                    target_hash,
                    str(record.get("created_at_utc") or now),
                    now,
                    record.get("completed_at_utc"),
                    json.dumps(record, sort_keys=True, default=str),
                ),
            )
        return record

    def read_rebalance_slot_target(self, slot_id: str) -> dict[str, Any] | None:
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM rebalance_slot_targets WHERE slot_id = ?",
                (str(slot_id),),
            ).fetchone()
        if row is None:
            return None
        try:
            return dict(json.loads(str(row[0])))
        except json.JSONDecodeError:
            return None

    def mark_rebalance_slot_target_completed(
        self,
        *,
        slot_id: str,
        run_id: str,
        artifact_root: str,
        reason: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        record = self.read_rebalance_slot_target(slot_id)
        if record is None:
            return None
        completed_at = utc_now()
        record["status"] = "completed"
        record["completed_at_utc"] = completed_at
        record["completed_by_run_id"] = str(run_id)
        record["completed_artifact_root"] = str(artifact_root or "")
        record["completion_reason"] = str(reason or "")
        record["updated_at_utc"] = completed_at
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE rebalance_slot_targets SET status = ?, updated_at_utc = ?, completed_at_utc = ?, payload_json = ? WHERE slot_id = ?",
                (
                    "completed",
                    completed_at,
                    completed_at,
                    json.dumps(record, sort_keys=True, default=str),
                    str(slot_id),
                ),
            )
        return record

    def latest_live_order_submission(self) -> dict[str, Any]:
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT run_id, created_at_utc, payload_json FROM run_summaries ORDER BY created_at_utc DESC"
            ).fetchall()
        for run_id, created_at_utc, payload_json in rows:
            try:
                payload = json.loads(str(payload_json))
            except json.JSONDecodeError:
                continue
            submitted = int(
                float(payload.get("submitted_order_count", payload.get("orders_submitted", 0)) or 0)
            )
            if submitted <= 0:
                continue
            execution_stage = _extract_live_execution_stage(payload)
            status_text = str(payload.get("status") or "").strip().lower()
            if status_text.startswith("unattended_daily_policy"):
                continue
            fill_count = int(float(payload.get("fill_count", 0) or 0))
            cycle_status = _extract_live_cycle_status(payload)
            post_trade_reconcile_status = _extract_post_trade_reconcile_status(payload)
            return {
                "run_id": str(run_id),
                "created_at_utc": str(created_at_utc),
                "submitted_order_count": submitted,
                "fill_count": fill_count,
                "status": str(payload.get("status") or ""),
                "execution_stage": execution_stage,
                "cycle_status": cycle_status,
                "post_trade_reconcile_status": post_trade_reconcile_status,
                "live_delta_authorized": bool(payload.get("live_delta_authorized")),
                "started_at_utc": payload.get("started_at_utc"),
                "finished_at_utc": payload.get("finished_at_utc"),
                "artifact_root": payload.get("artifact_root"),
            }
        return {}

    def has_json_row(self, table: str, key_column: str, key_value: str) -> bool:
        if table not in {
            "run_summaries",
            "decision_snapshots",
            "target_portfolios",
            "risk_gate_results",
            "execution_plans",
            "paper_executions",
        }:
            raise ValueError(f"unsupported live trading state table: {table}")
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                f"SELECT 1 FROM {table} WHERE {key_column} = ? LIMIT 1",
                (key_value,),
            ).fetchone()
        return row is not None

    def has_paper_execution(self, plan_id: str) -> bool:
        return self.has_json_row("paper_executions", "plan_id", str(plan_id))

    def read_paper_positions(self) -> dict[str, float]:
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("SELECT symbol, position_amt FROM paper_positions ORDER BY symbol").fetchall()
        positions: dict[str, float] = {}
        for symbol, position_amt in rows:
            amount = float(position_amt)
            if abs(amount) > 1e-12:
                positions[str(symbol)] = amount
        return positions

    def record_paper_execution(self, execution: Any) -> None:
        self.initialize()
        created_at = utc_now()
        submitted_orders = execution.submitted_orders.copy()
        fills = execution.fills.copy()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO paper_executions(plan_id, run_id, created_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                (
                    str(execution.plan_id),
                    str(execution.run_id),
                    created_at,
                    json.dumps(execution.metadata(), sort_keys=True, default=str),
                ),
            )
            for row in submitted_orders.to_dict(orient="records"):
                conn.execute(
                    "INSERT INTO paper_orders(paper_order_id, plan_id, created_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        str(row["paper_order_id"]),
                        str(execution.plan_id),
                        created_at,
                        json.dumps(row, sort_keys=True, default=str),
                    ),
                )
            positions = {
                str(symbol): float(position_amt)
                for symbol, position_amt in conn.execute("SELECT symbol, position_amt FROM paper_positions").fetchall()
            }
            for row in fills.to_dict(orient="records"):
                symbol = str(row["symbol"])
                signed_quantity = float(row.get("signed_quantity", 0.0) or 0.0)
                positions[symbol] = float(positions.get(symbol, 0.0) or 0.0) + signed_quantity
                conn.execute(
                    "INSERT INTO paper_fills(paper_fill_id, plan_id, symbol, created_at_utc, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(row["paper_fill_id"]),
                        str(execution.plan_id),
                        symbol,
                        created_at,
                        json.dumps(row, sort_keys=True, default=str),
                    ),
                )
            for symbol, amount in sorted(positions.items()):
                payload = {
                    "symbol": symbol,
                    "position_amt": float(amount),
                    "updated_at_utc": created_at,
                    "updated_from_plan_id": str(execution.plan_id),
                }
                conn.execute(
                    "INSERT OR REPLACE INTO paper_positions(symbol, position_amt, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (symbol, float(amount), created_at, json.dumps(payload, sort_keys=True, default=str)),
                )

    def write_heartbeat(
        self,
        *,
        run_id: str,
        mode: str,
        status: str,
        started_at_utc: str,
        updated_at_utc: str | None = None,
        finished_at_utc: str | None = None,
        artifact_root: str | None = None,
        blockers: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.initialize()
        updated = updated_at_utc or utc_now()
        payload = {
            "run_id": str(run_id),
            "mode": str(mode),
            "status": str(status),
            "started_at_utc": str(started_at_utc),
            "updated_at_utc": str(updated),
            "finished_at_utc": finished_at_utc,
            "artifact_root": artifact_root,
            "blockers": list(blockers or []),
        }
        payload.update(dict(extra or {}))
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO heartbeats(run_id, mode, status, started_at_utc, updated_at_utc, finished_at_utc, artifact_root, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(run_id),
                    str(mode),
                    str(status),
                    str(started_at_utc),
                    str(updated),
                    finished_at_utc,
                    artifact_root,
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )

    def evaluate_local_state_health(
        self,
        *,
        now: datetime | str | None = None,
        max_heartbeat_age_seconds: float = 900.0,
        ignore_run_id: str | None = None,
        ignore_run_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        now_dt = _parse_utc(now or utc_now())
        blockers: list[str] = []
        ignored_run_ids = _expanded_run_id_set(ignore_run_ids)
        if ignore_run_id is not None:
            ignored_run_ids.update(_expanded_run_id_set([str(ignore_run_id)]))
        with sqlite3.connect(self.path) as conn:
            orphan_order_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_orders po
                    LEFT JOIN paper_executions pe ON pe.plan_id = po.plan_id
                    WHERE pe.plan_id IS NULL
                    """
                ).fetchone()[0]
            )
            orphan_fill_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_fills pf
                    LEFT JOIN paper_executions pe ON pe.plan_id = pf.plan_id
                    WHERE pe.plan_id IS NULL
                    """
                ).fetchone()[0]
            )
            running_rows = conn.execute(
                "SELECT run_id, mode, updated_at_utc FROM heartbeats WHERE status = 'running' ORDER BY updated_at_utc"
            ).fetchall()
        if orphan_order_count > 0:
            blockers.append(f"orphan_paper_orders_without_execution:{orphan_order_count}")
        if orphan_fill_count > 0:
            blockers.append(f"orphan_paper_fills_without_execution:{orphan_fill_count}")
        running_heartbeats: list[dict[str, Any]] = []
        for run_id, mode, updated_at in running_rows:
            if str(run_id) in ignored_run_ids:
                continue
            updated_dt = _parse_utc(str(updated_at))
            age_seconds = max(0.0, (now_dt - updated_dt).total_seconds())
            item = {
                "run_id": str(run_id),
                "mode": str(mode),
                "updated_at_utc": str(updated_at),
                "age_seconds": round(age_seconds, 3),
            }
            running_heartbeats.append(item)
            if age_seconds > float(max_heartbeat_age_seconds):
                blockers.append(f"stale_running_heartbeat:{run_id}")
            else:
                blockers.append(f"active_run_in_progress:{run_id}")
        return {
            "status": "ok" if not blockers else "blocked",
            "blockers": sorted(set(blockers)),
            "orphan_paper_order_count": orphan_order_count,
            "orphan_paper_fill_count": orphan_fill_count,
            "running_heartbeats": running_heartbeats,
            "max_heartbeat_age_seconds": float(max_heartbeat_age_seconds),
            "checked_at_utc": now_dt.isoformat().replace("+00:00", "Z"),
        }

    def recover_stale_running_heartbeats(
        self,
        *,
        now: datetime | str | None = None,
        max_heartbeat_age_seconds: float = 900.0,
        recovery_run_id: str,
        reason: str,
        ignore_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        now_dt = _parse_utc(now or utc_now())
        recovered_at = now_dt.isoformat().replace("+00:00", "Z")
        recovered: list[dict[str, Any]] = []
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT run_id, mode, started_at_utc, updated_at_utc, finished_at_utc, artifact_root, payload_json
                FROM heartbeats
                WHERE status = 'running'
                ORDER BY updated_at_utc
                """
            ).fetchall()
            for run_id, mode, started_at, updated_at, _finished_at, artifact_root, payload_json in rows:
                if ignore_run_id is not None and str(run_id) == str(ignore_run_id):
                    continue
                updated_dt = _parse_utc(str(updated_at))
                age_seconds = max(0.0, (now_dt - updated_dt).total_seconds())
                if age_seconds <= float(max_heartbeat_age_seconds):
                    continue
                try:
                    payload = json.loads(str(payload_json))
                except json.JSONDecodeError:
                    payload = {}
                blockers = sorted(
                    set(
                        [
                            *list(payload.get("blockers") or []),
                            f"stale_running_heartbeat_recovered:{run_id}",
                        ]
                    )
                )
                recovery_record = {
                    "run_id": str(run_id),
                    "mode": str(mode),
                    "previous_status": "running",
                    "new_status": "reconcile_required",
                    "started_at_utc": str(started_at),
                    "last_updated_at_utc": str(updated_at),
                    "recovered_at_utc": recovered_at,
                    "age_seconds": round(age_seconds, 3),
                    "max_heartbeat_age_seconds": float(max_heartbeat_age_seconds),
                    "artifact_root": artifact_root,
                    "recovery_run_id": str(recovery_run_id),
                    "reason": str(reason or ""),
                    "blockers": blockers,
                }
                new_payload = dict(payload)
                new_payload.update(
                    {
                        "status": "reconcile_required",
                        "updated_at_utc": recovered_at,
                        "finished_at_utc": recovered_at,
                        "blockers": blockers,
                        "recovery": recovery_record,
                    }
                )
                conn.execute(
                    """
                    UPDATE heartbeats
                    SET status = 'reconcile_required',
                        updated_at_utc = ?,
                        finished_at_utc = ?,
                        payload_json = ?
                    WHERE run_id = ?
                    """,
                    (
                        recovered_at,
                        recovered_at,
                        json.dumps(new_payload, sort_keys=True, default=str),
                        str(run_id),
                    ),
                )
                recovered.append(recovery_record)
        return recovered

    def read_operator_state(self) -> dict[str, Any]:
        self.initialize()
        defaults = {
            "paused": False,
            "live_delta_armed": False,
            "last_action_type": None,
            "last_action_id": None,
            "last_reason": None,
            "updated_at_utc": None,
            "live_delta_last_action_type": None,
            "live_delta_last_action_id": None,
            "live_delta_last_reason": None,
            "live_delta_updated_at_utc": None,
        }
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("SELECT key, value, updated_at_utc, payload_json FROM operator_state").fetchall()
        output = dict(defaults)
        for key, value, updated_at, payload_json in rows:
            try:
                payload = json.loads(str(payload_json))
            except json.JSONDecodeError:
                payload = {}
            if key == "paused":
                output["paused"] = str(value).strip().lower() == "true"
                for field in ("last_action_type", "last_action_id", "last_reason"):
                    output[field] = payload.get(field, output.get(field))
                output["updated_at_utc"] = str(updated_at)
            elif key == "live_delta_armed":
                output["live_delta_armed"] = str(value).strip().lower() == "true"
                for source, target in (
                    ("last_action_type", "live_delta_last_action_type"),
                    ("last_action_id", "live_delta_last_action_id"),
                    ("last_reason", "live_delta_last_reason"),
                ):
                    output[target] = payload.get(source, output.get(target))
                output["live_delta_updated_at_utc"] = str(updated_at)
        return output

    def record_operator_action(
        self,
        *,
        run_id: str,
        action_type: str,
        reason: str = "",
        status: str = "applied",
        created_at_utc: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        action = str(action_type).strip().lower().replace("_", "-")
        created_at = created_at_utc or utc_now()
        action_id = f"{created_at.replace(':', '').replace('-', '').replace('.', '')}:{action}:{run_id}"
        record = {
            "action_id": action_id,
            "run_id": str(run_id),
            "action_type": action,
            "status": str(status),
            "reason": str(reason or ""),
            "created_at_utc": created_at,
        }
        record.update(dict(payload or {}))
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO operator_actions(action_id, run_id, action_type, status, created_at_utc, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action_id,
                    str(run_id),
                    action,
                    str(status),
                    created_at,
                    json.dumps(record, sort_keys=True, default=str),
                ),
            )
            if action in {"pause", "kill-switch", "resume"} and status == "applied":
                paused = action in {"pause", "kill-switch"}
                state_payload = {
                    "paused": paused,
                    "last_action_type": action,
                    "last_action_id": action_id,
                    "last_reason": str(reason or ""),
                    "updated_at_utc": created_at,
                }
                conn.execute(
                    "INSERT OR REPLACE INTO operator_state(key, value, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        "paused",
                        "true" if paused else "false",
                        created_at,
                        json.dumps(state_payload, sort_keys=True, default=str),
                    ),
                )
            if action in {"arm-live-delta", "disarm-live-delta", "kill-switch"} and status == "applied":
                armed = action == "arm-live-delta"
                state_payload = {
                    "live_delta_armed": armed,
                    "last_action_type": action,
                    "last_action_id": action_id,
                    "last_reason": str(reason or ""),
                    "updated_at_utc": created_at,
                }
                conn.execute(
                    "INSERT OR REPLACE INTO operator_state(key, value, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        "live_delta_armed",
                        "true" if armed else "false",
                        created_at,
                        json.dumps(state_payload, sort_keys=True, default=str),
                    ),
                )
        return record

    def latest_operator_action(
        self,
        *,
        action_type: str,
        status: str | None = None,
        plan_id: str | None = None,
        slot_id: str | None = None,
        target_hash: str | None = None,
    ) -> dict[str, Any] | None:
        self.initialize()
        normalized_action = str(action_type).strip().lower().replace("_", "-")
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM operator_actions
                WHERE action_type = ?
                ORDER BY created_at_utc DESC
                """,
                (normalized_action,),
            ).fetchall()
        for (payload_json,) in rows:
            try:
                payload = json.loads(str(payload_json))
            except json.JSONDecodeError:
                continue
            if status is not None and str(payload.get("status") or "") != str(status):
                continue
            if plan_id is not None and str(payload.get("plan_id") or "") != str(plan_id):
                continue
            if slot_id is not None:
                payload_slot = str(payload.get("slot_id") or payload.get("rebalance_slot_id") or "")
                if payload_slot != str(slot_id):
                    continue
            if target_hash is not None:
                payload_hash = str(payload.get("target_hash") or payload.get("rebalance_target_hash") or "")
                if payload_hash != str(target_hash):
                    continue
            return dict(payload)
        return None


def _parse_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_live_execution_stage(payload: dict[str, Any]) -> str:
    direct = str(payload.get("execution_stage") or "").strip().lower()
    if direct:
        return direct
    cycles = list(payload.get("cycles") or [])
    if cycles:
        cycle = dict(cycles[-1]) if isinstance(cycles[-1], dict) else {}
        policy = dict(cycle.get("live_delta_policy_gate") or {})
        stage = str(policy.get("execution_stage") or "").strip().lower()
        if stage:
            return stage
        core = dict(cycle.get("core_loop_summary") or {})
        core_stage = _extract_live_execution_stage(core)
        if core_stage:
            return core_stage
    return ""


def _extract_live_cycle_status(payload: dict[str, Any]) -> str:
    cycles = list(payload.get("cycles") or [])
    if not cycles:
        return ""
    cycle = dict(cycles[-1]) if isinstance(cycles[-1], dict) else {}
    status = str(cycle.get("status") or "").strip()
    if status:
        return status
    core = dict(cycle.get("core_loop_summary") or {})
    return _extract_live_cycle_status(core)


def _extract_post_trade_reconcile_status(payload: dict[str, Any]) -> str:
    top_level = _post_trade_status(payload.get("post_trade_reconcile"))
    if top_level:
        return top_level
    direct_status = str(payload.get("post_trade_reconcile_status") or "").strip()
    if direct_status:
        return direct_status
    cycles = list(payload.get("cycles") or [])
    if not cycles:
        return ""
    cycle = dict(cycles[-1]) if isinstance(cycles[-1], dict) else {}
    status = _post_trade_status(cycle.get("post_trade_reconcile"))
    if status:
        return status
    core = dict(cycle.get("core_loop_summary") or {})
    return _extract_post_trade_reconcile_status(core)


def _post_trade_status(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("status") or "").strip()
