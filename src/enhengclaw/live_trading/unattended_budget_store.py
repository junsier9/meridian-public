"""Persistence for the restricted-unattended live_delta budget — DRAFT.

Not yet wired into the live path. Kept as a standalone store (rather than
expanding LiveTradingStateStore) so the draft is self-contained and the critical
safety logic can be adversarially reviewed and temp-DB tested in isolation. In
production it shares the same sqlite file as LiveTradingStateStore (operator
arm/pause state lives alongside the budget) but owns its own tables.

The design answers three fail-open holes an adversarial review found in a naive
"evaluate then record-after-fill" budget:

  1. CRASH-BEFORE-CONSUME UNDERCOUNT (catastrophic): a crash between submit and a
     post-fill consume would leave the ledger at 0 and the next timer fire would
     re-permit. Fix: RESERVE-BEFORE-SUBMIT via a single atomic conditional
     UPDATE that debits the projected turnover up front. A crash then leaves the
     budget ALREADY debited (over-counts, fails safe), never under-counted.

  2. run_id-keyed idempotency (undercount on retry): each timer fire mints a new
     run_id, so it cannot dedupe the same work. Fix: idempotency key is the
     caller-supplied ``reservation_key`` derived from the plan/decision, not the
     process clock.

  3. multiple open epochs / counter rollback: fix via a partial UNIQUE index
     enforcing at most one open epoch, plus an orphan-reservation check that
     fails closed if a prior in-flight reservation was never reconciled.

Reserve flow (all inside one transaction = atomic):
  - validate the epoch (exists / open / not stale)  -> blocker, no debit
  - conditional UPDATE debit guarded by WHERE cycles<max AND turnover fits
  - INSERT the reservation row (PK = reservation_key) -> dedupes retries
  - if the reservation key already existed, the IntegrityError rolls the whole
    transaction back (debit undone) and the caller gets "already_reserved"

Post-fill: ``reconcile_reservation`` bumps the ledger UP to realized turnover if
it exceeded the projected reserve (never down), and marks the reservation
terminal so the orphan check clears.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enhengclaw.live_trading.unattended_budget_gate import (
    EPOCH_STATUS_CLOSED,
    EPOCH_STATUS_EXHAUSTED,
    EPOCH_STATUS_OPEN,
    BudgetEpoch,
    epoch_status_after_consume,
)


SCHEMA_VERSION = 1
_EPS = 1e-9

RESV_RESERVED = "reserved"      # debited, awaiting post-fill reconcile (orphan if stale)
RESV_RECONCILED = "reconciled"  # debited + reconciled (terminal success)
RESV_RELEASED = "released"      # not debited, no budget at reserve time (terminal no-op)


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("empty timestamp")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class UnattendedBudgetStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # -- schema -------------------------------------------------------------
    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            # WAL: concurrent readers don't block the single writer, and writers
            # serialize cleanly under overlapping timer processes. The atomic
            # conditional UPDATE in reserve() is the binding budget guard; WAL +
            # busy_timeout make it robust under contention instead of erroring.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS unattended_budget_ledger ("
                "epoch_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, "
                "max_live_cycles INTEGER NOT NULL, max_gross_turnover_usdt REAL NOT NULL, "
                "max_age_seconds INTEGER NOT NULL, consumed_cycles INTEGER NOT NULL DEFAULT 0, "
                "consumed_turnover_usdt REAL NOT NULL DEFAULT 0, status TEXT NOT NULL, "
                "updated_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            # At most ONE open epoch, enforced at the DB layer (defence even
            # against a buggy caller that opens twice).
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_unattended_budget_open "
                "ON unattended_budget_ledger(status) WHERE status='open'"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS unattended_budget_reservations ("
                "reservation_key TEXT PRIMARY KEY, epoch_id TEXT NOT NULL, run_id TEXT NOT NULL, "
                "reserved_cycles INTEGER NOT NULL, reserved_turnover_usdt REAL NOT NULL, "
                "realized_turnover_usdt REAL, status TEXT NOT NULL, "
                "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )

    # -- epoch lifecycle ----------------------------------------------------
    def open_epoch(
        self,
        *,
        epoch_id: str,
        max_live_cycles: int,
        max_gross_turnover_usdt: float,
        max_age_seconds: int,
        now_utc: datetime | None = None,
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Open exactly one budget epoch. Fail closed if one is already open or
        bounds are non-finite / non-positive."""
        self.initialize()
        now = now_utc or datetime.now(UTC)
        cycles = int(max_live_cycles)
        turnover = _finite_float(max_gross_turnover_usdt)
        age = int(max_age_seconds)
        if cycles <= 0 or age <= 0 or turnover is None or turnover <= 0.0:
            return {"status": "rejected", "blockers": ["unattended_budget_open_bounds_invalid"], "epoch_id": epoch_id}
        record = {
            "epoch_id": str(epoch_id),
            "created_at_utc": _iso(now),
            "max_live_cycles": cycles,
            "max_gross_turnover_usdt": float(turnover),
            "max_age_seconds": age,
            "status": EPOCH_STATUS_OPEN,
            "reason": str(reason or ""),
        }
        record.update(dict(payload or {}))
        try:
            with sqlite3.connect(self.path) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                existing = conn.execute(
                    "SELECT epoch_id FROM unattended_budget_ledger WHERE status='open'"
                ).fetchone()
                if existing is not None:
                    return {
                        "status": "rejected",
                        "blockers": ["unattended_budget_open_epoch_already_exists"],
                        "epoch_id": epoch_id,
                        "existing_open_epoch_id": str(existing[0]),
                    }
                conn.execute(
                    "INSERT INTO unattended_budget_ledger(epoch_id, created_at_utc, max_live_cycles, "
                    "max_gross_turnover_usdt, max_age_seconds, consumed_cycles, consumed_turnover_usdt, "
                    "status, updated_at_utc, payload_json) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                    (
                        record["epoch_id"],
                        record["created_at_utc"],
                        cycles,
                        float(turnover),
                        age,
                        EPOCH_STATUS_OPEN,
                        _iso(now),
                        json.dumps(record, sort_keys=True, default=str),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            # Lost a race to the partial unique index, or duplicate epoch_id.
            return {"status": "rejected", "blockers": ["unattended_budget_open_epoch_conflict"], "epoch_id": epoch_id, "error": str(exc)}
        return {"status": "opened", "blockers": [], "epoch_id": epoch_id, "created_at_utc": record["created_at_utc"]}

    def read_current_epoch(self) -> BudgetEpoch | None:
        """Return the single open epoch (or None). The partial unique index
        guarantees at most one row with status='open'."""
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            row = conn.execute(
                "SELECT epoch_id, created_at_utc, max_live_cycles, max_gross_turnover_usdt, "
                "max_age_seconds, consumed_cycles, consumed_turnover_usdt, status "
                "FROM unattended_budget_ledger WHERE status='open' LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return BudgetEpoch(
            epoch_id=str(row[0]),
            created_at_utc=str(row[1]),
            max_live_cycles=row[2],
            max_gross_turnover_usdt=row[3],
            max_age_seconds=row[4],
            consumed_cycles=row[5],
            consumed_turnover_usdt=row[6],
            status=str(row[7]),
        )

    def close_epoch(self, *, epoch_id: str, now_utc: datetime | None = None, reason: str = "") -> dict[str, Any]:
        self.initialize()
        now = now_utc or datetime.now(UTC)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            cur = conn.execute(
                "UPDATE unattended_budget_ledger SET status=?, updated_at_utc=? WHERE epoch_id=?",
                (EPOCH_STATUS_CLOSED, _iso(now), str(epoch_id)),
            )
        return {"status": "closed" if cur.rowcount == 1 else "not_found", "epoch_id": epoch_id}

    # -- reserve / reconcile ------------------------------------------------
    def reserve(
        self,
        *,
        epoch_id: str,
        reservation_key: str,
        run_id: str,
        projected_turnover_usdt: float | None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve one live-submitting cycle BEFORE it submits.

        Returns status in {"reserved", "already_reserved", "blocked"}. Only a
        "reserved" or "already_reserved" result may be followed by a live submit.
        The whole body is one transaction: the conditional UPDATE is the binding
        budget guard; the reservation INSERT (PK) dedupes retries; an
        IntegrityError on a pre-existing key rolls the debit back.
        """
        self.initialize()
        now = now_utc or datetime.now(UTC)
        proj = _finite_float(projected_turnover_usdt) if projected_turnover_usdt is not None else None
        if proj is None or proj < 0.0:
            return self._reserve_blocked(epoch_id, reservation_key, ["unattended_budget_projected_turnover_unknown"])

        try:
            with sqlite3.connect(self.path) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                row = conn.execute(
                    "SELECT created_at_utc, max_age_seconds, status FROM unattended_budget_ledger WHERE epoch_id=?",
                    (str(epoch_id),),
                ).fetchone()
                if row is None:
                    return self._reserve_blocked(epoch_id, reservation_key, ["unattended_budget_epoch_not_found"])
                created_at, max_age, status = str(row[0]), int(row[1]), str(row[2])
                blockers: list[str] = []
                if status.strip().lower() != EPOCH_STATUS_OPEN:
                    blockers.append(f"unattended_budget_epoch_not_open:{status}")
                try:
                    age = max(0.0, (now.astimezone(UTC) - _parse_utc(created_at)).total_seconds())
                    if max_age > 0 and age > float(max_age):
                        blockers.append(f"unattended_budget_epoch_stale:{age:.0f}>{max_age}")
                except (ValueError, TypeError):
                    blockers.append("unattended_budget_epoch_created_at_unparseable")
                if blockers:
                    return self._reserve_blocked(epoch_id, reservation_key, blockers)

                # Binding atomic debit. WHERE re-evaluated against committed state,
                # so two concurrent reserves cannot both pass the last unit.
                cur = conn.execute(
                    "UPDATE unattended_budget_ledger "
                    "SET consumed_cycles = consumed_cycles + 1, "
                    "    consumed_turnover_usdt = consumed_turnover_usdt + ?, updated_at_utc = ? "
                    "WHERE epoch_id = ? AND status='open' "
                    "  AND consumed_cycles < max_live_cycles "
                    "  AND consumed_turnover_usdt + ? <= max_gross_turnover_usdt + ?",
                    (proj, _iso(now), str(epoch_id), proj, _EPS),
                )
                if cur.rowcount != 1:
                    # No budget: the conditional UPDATE matched no row, so the
                    # ledger is unchanged. Write NOTHING to the reservations table
                    # (a released audit row could collide on the PK and mislead a
                    # later same-key re-ask into "already_reserved"). The empty
                    # transaction commits a no-op.
                    return self._reserve_blocked(epoch_id, reservation_key, ["unattended_budget_reserve_rejected"])

                # Debit succeeded; claim the reservation key. If it already exists,
                # this raises IntegrityError -> the whole txn (incl. the debit) is
                # rolled back -> handled as already_reserved below (no double debit).
                conn.execute(
                    "INSERT INTO unattended_budget_reservations(reservation_key, epoch_id, run_id, "
                    "reserved_cycles, reserved_turnover_usdt, realized_turnover_usdt, status, "
                    "created_at_utc, updated_at_utc, payload_json) VALUES (?, ?, ?, 1, ?, NULL, ?, ?, ?, ?)",
                    (
                        str(reservation_key), str(epoch_id), str(run_id), proj, RESV_RESERVED,
                        _iso(now), _iso(now),
                        json.dumps({"reason": "reserved"}, sort_keys=True),
                    ),
                )

                after = conn.execute(
                    "SELECT max_live_cycles, max_gross_turnover_usdt, consumed_cycles, consumed_turnover_usdt "
                    "FROM unattended_budget_ledger WHERE epoch_id=?",
                    (str(epoch_id),),
                ).fetchone()
                epoch_after = BudgetEpoch(
                    epoch_id=str(epoch_id), created_at_utc=created_at,
                    max_live_cycles=after[0], max_gross_turnover_usdt=after[1], max_age_seconds=max_age,
                    consumed_cycles=after[2], consumed_turnover_usdt=after[3], status=EPOCH_STATUS_OPEN,
                )
                new_status = epoch_status_after_consume(epoch_after)
                if new_status != EPOCH_STATUS_OPEN:
                    conn.execute(
                        "UPDATE unattended_budget_ledger SET status=?, updated_at_utc=? WHERE epoch_id=?",
                        (new_status, _iso(now), str(epoch_id)),
                    )
                return {
                    "status": "reserved", "passed": True, "blockers": [],
                    "epoch_id": str(epoch_id), "reservation_key": str(reservation_key),
                    "debited_turnover_usdt": proj,
                    "consumed_cycles": int(after[2]), "remaining_cycles": int(after[0]) - int(after[2]),
                    "consumed_turnover_usdt": float(after[3]),
                    "remaining_turnover_usdt": float(after[1]) - float(after[3]),
                    "epoch_status_after": new_status,
                }
        except sqlite3.IntegrityError:
            # reservation_key already claimed in a prior committed txn -> this work
            # was already accounted for; the debit just attempted was rolled back.
            return {
                "status": "already_reserved", "passed": True, "blockers": [],
                "epoch_id": str(epoch_id), "reservation_key": str(reservation_key),
            }

    @staticmethod
    def _reserve_blocked(epoch_id: str, reservation_key: str, blockers: list[str]) -> dict[str, Any]:
        return {
            "status": "blocked",
            "passed": False,
            "blockers": sorted(set(blockers)),
            "epoch_id": str(epoch_id),
            "reservation_key": str(reservation_key),
        }

    def reconcile_reservation(
        self,
        *,
        reservation_key: str,
        realized_turnover_usdt: float | None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Post-fill: bump the ledger UP to realized turnover if it exceeded the
        reserve (never down), and mark the reservation terminal so the orphan
        check clears. Conservative by design: budget is never returned."""
        self.initialize()
        now = now_utc or datetime.now(UTC)
        realized = _finite_float(realized_turnover_usdt)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            row = conn.execute(
                "SELECT epoch_id, reserved_turnover_usdt, status FROM unattended_budget_reservations WHERE reservation_key=?",
                (str(reservation_key),),
            ).fetchone()
            if row is None:
                return {"status": "not_found", "blockers": ["unattended_budget_reservation_not_found"], "reservation_key": reservation_key}
            epoch_id, reserved_turnover, resv_status = str(row[0]), float(row[1]), str(row[2])
            if resv_status != RESV_RESERVED:
                return {"status": "noop", "reservation_key": reservation_key, "reservation_status": resv_status}
            extra = 0.0
            if realized is not None and realized > reserved_turnover:
                extra = realized - reserved_turnover
                conn.execute(
                    "UPDATE unattended_budget_ledger SET consumed_turnover_usdt = consumed_turnover_usdt + ?, "
                    "updated_at_utc = ? WHERE epoch_id = ?",
                    (extra, _iso(now), epoch_id),
                )
                after = conn.execute(
                    "SELECT max_live_cycles, max_gross_turnover_usdt, consumed_cycles, consumed_turnover_usdt, status "
                    "FROM unattended_budget_ledger WHERE epoch_id=?",
                    (epoch_id,),
                ).fetchone()
                if str(after[4]) == EPOCH_STATUS_OPEN:
                    epoch_after = BudgetEpoch(
                        epoch_id=epoch_id, created_at_utc=_iso(now),
                        max_live_cycles=after[0], max_gross_turnover_usdt=after[1], max_age_seconds=1,
                        consumed_cycles=after[2], consumed_turnover_usdt=after[3], status=EPOCH_STATUS_OPEN,
                    )
                    new_status = epoch_status_after_consume(epoch_after)
                    if new_status != EPOCH_STATUS_OPEN:
                        conn.execute(
                            "UPDATE unattended_budget_ledger SET status=?, updated_at_utc=? WHERE epoch_id=?",
                            (new_status, _iso(now), epoch_id),
                        )
            conn.execute(
                "UPDATE unattended_budget_reservations SET status=?, realized_turnover_usdt=?, updated_at_utc=? "
                "WHERE reservation_key=?",
                (RESV_RECONCILED, realized if realized is not None else reserved_turnover, _iso(now), str(reservation_key)),
            )
        return {"status": "reconciled", "reservation_key": reservation_key, "extra_turnover_debited": extra}

    # -- orphan / pre-cycle safety -----------------------------------------
    def unreconciled_reservations(self, *, epoch_id: str | None = None) -> list[dict[str, Any]]:
        """Reservations that were debited but never reconciled = a prior in-flight
        cycle that crashed after reserve. The pre-cycle hook must fail closed when
        any exist, so disarm_on_blocker cascades and auto_rearm cannot resume."""
        self.initialize()
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            if epoch_id is not None:
                rows = conn.execute(
                    "SELECT reservation_key, epoch_id, run_id, reserved_turnover_usdt, created_at_utc "
                    "FROM unattended_budget_reservations WHERE status=? AND epoch_id=? ORDER BY created_at_utc",
                    (RESV_RESERVED, str(epoch_id)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT reservation_key, epoch_id, run_id, reserved_turnover_usdt, created_at_utc "
                    "FROM unattended_budget_reservations WHERE status=? ORDER BY created_at_utc",
                    (RESV_RESERVED,),
                ).fetchall()
        return [
            {"reservation_key": str(r[0]), "epoch_id": str(r[1]), "run_id": str(r[2]),
             "reserved_turnover_usdt": float(r[3]), "created_at_utc": str(r[4])}
            for r in rows
        ]

    def has_unreconciled_reservation(self, *, epoch_id: str | None = None) -> bool:
        return len(self.unreconciled_reservations(epoch_id=epoch_id)) > 0
