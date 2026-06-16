from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.unattended_budget_store import (  # noqa: E402
    RESV_RECONCILED,
    RESV_RESERVED,
    UnattendedBudgetStore,
)

T0 = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


def _store(tmp_path):
    return UnattendedBudgetStore(tmp_path / "state" / "live.sqlite3")


def _ledger_row(store, epoch_id):
    with sqlite3.connect(store.path) as conn:
        return conn.execute(
            "SELECT consumed_cycles, consumed_turnover_usdt, status FROM unattended_budget_ledger WHERE epoch_id=?",
            (epoch_id,),
        ).fetchone()


def _open(store, **kw):
    base = dict(epoch_id="e1", max_live_cycles=6, max_gross_turnover_usdt=600.0, max_age_seconds=3600, now_utc=T0)
    base.update(kw)
    return store.open_epoch(**base)


def test_open_and_read(tmp_path):
    store = _store(tmp_path)
    assert _open(store)["status"] == "opened"
    epoch = store.read_current_epoch()
    assert epoch is not None
    assert epoch.epoch_id == "e1"
    assert epoch.consumed_cycles == 0
    assert epoch.status == "open"


def test_single_open_epoch_invariant(tmp_path):
    store = _store(tmp_path)
    assert _open(store, epoch_id="e1")["status"] == "opened"
    second = _open(store, epoch_id="e2")
    assert second["status"] == "rejected"
    assert "unattended_budget_open_epoch_already_exists" in second["blockers"]
    # still exactly one open epoch, the first
    assert store.read_current_epoch().epoch_id == "e1"


def test_open_rejects_non_positive_bounds(tmp_path):
    store = _store(tmp_path)
    assert _open(store, max_gross_turnover_usdt=0.0)["status"] == "rejected"
    assert _open(store, max_live_cycles=0)["status"] == "rejected"
    assert _open(store, max_age_seconds=0)["status"] == "rejected"
    assert _open(store, max_gross_turnover_usdt=float("inf"))["status"] == "rejected"


def test_reserve_within_budget_debits(tmp_path):
    store = _store(tmp_path)
    _open(store)
    r = store.reserve(epoch_id="e1", reservation_key="k1", run_id="run-1", projected_turnover_usdt=107.0, now_utc=T0)
    assert r["status"] == "reserved"
    assert r["remaining_cycles"] == 5
    consumed_cycles, consumed_turnover, status = _ledger_row(store, "e1")
    assert consumed_cycles == 1
    assert consumed_turnover == 107.0
    assert status == "open"


def test_same_key_reserve_is_idempotent_no_double_debit(tmp_path):
    store = _store(tmp_path)
    _open(store)
    a = store.reserve(epoch_id="e1", reservation_key="k1", run_id="run-1", projected_turnover_usdt=100.0, now_utc=T0)
    b = store.reserve(epoch_id="e1", reservation_key="k1", run_id="run-2", projected_turnover_usdt=100.0, now_utc=T0)
    assert a["status"] == "reserved"
    assert b["status"] == "already_reserved"
    assert b["passed"] is True
    # debited exactly once despite two reserve calls with the same key
    consumed_cycles, consumed_turnover, _ = _ledger_row(store, "e1")
    assert consumed_cycles == 1
    assert consumed_turnover == 100.0


def test_cycle_budget_exhaustion_blocks_and_marks_terminal(tmp_path):
    store = _store(tmp_path)
    _open(store, max_live_cycles=2, max_gross_turnover_usdt=10000.0)
    assert store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=10.0, now_utc=T0)["status"] == "reserved"
    assert store.reserve(epoch_id="e1", reservation_key="k2", run_id="r2", projected_turnover_usdt=10.0, now_utc=T0)["status"] == "reserved"
    # epoch now exhausted -> no longer the current open epoch
    assert store.read_current_epoch() is None
    assert _ledger_row(store, "e1")[2] == "exhausted"
    # a third reserve against the same epoch id is blocked (not open)
    third = store.reserve(epoch_id="e1", reservation_key="k3", run_id="r3", projected_turnover_usdt=10.0, now_utc=T0)
    assert third["status"] == "blocked"


def test_turnover_budget_blocks_without_debit(tmp_path):
    store = _store(tmp_path)
    _open(store, max_live_cycles=10, max_gross_turnover_usdt=150.0)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    blocked = store.reserve(epoch_id="e1", reservation_key="k2", run_id="r2", projected_turnover_usdt=100.0, now_utc=T0)
    assert blocked["status"] == "blocked"
    assert "unattended_budget_reserve_rejected" in blocked["blockers"]
    # consumed turnover unchanged by the rejected reserve
    assert _ledger_row(store, "e1")[1] == 100.0
    # and no reservation row was written for the rejected key
    with sqlite3.connect(store.path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM unattended_budget_reservations WHERE reservation_key='k2'"
        ).fetchone()[0] == 0


def test_turnover_exact_boundary_allowed(tmp_path):
    store = _store(tmp_path)
    _open(store, max_gross_turnover_usdt=150.0)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=75.0, now_utc=T0)
    r = store.reserve(epoch_id="e1", reservation_key="k2", run_id="r2", projected_turnover_usdt=75.0, now_utc=T0)
    assert r["status"] == "reserved"  # 75 + 75 == 150 ceiling


def test_stale_epoch_blocks(tmp_path):
    store = _store(tmp_path)
    _open(store, max_age_seconds=3600)
    late = T0 + timedelta(seconds=4000)
    r = store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=10.0, now_utc=late)
    assert r["status"] == "blocked"
    assert any("unattended_budget_epoch_stale" in b for b in r["blockers"])
    assert _ledger_row(store, "e1")[0] == 0  # no debit


def test_projected_none_blocks_without_debit(tmp_path):
    store = _store(tmp_path)
    _open(store)
    r = store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=None, now_utc=T0)
    assert r["status"] == "blocked"
    assert "unattended_budget_projected_turnover_unknown" in r["blockers"]
    assert _ledger_row(store, "e1")[0] == 0


def test_projected_nan_blocks_without_debit(tmp_path):
    store = _store(tmp_path)
    _open(store)
    r = store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=float("nan"), now_utc=T0)
    assert r["status"] == "blocked"
    assert _ledger_row(store, "e1")[0] == 0


def test_reserve_unknown_epoch_blocks(tmp_path):
    store = _store(tmp_path)
    _open(store, epoch_id="e1")
    r = store.reserve(epoch_id="missing", reservation_key="k1", run_id="r1", projected_turnover_usdt=10.0, now_utc=T0)
    assert r["status"] == "blocked"
    assert "unattended_budget_epoch_not_found" in r["blockers"]


def test_crash_after_reserve_leaves_orphan_and_overcounts(tmp_path):
    # The crash-before-consume hole: reserve (debit) happens BEFORE submit, so a
    # crash leaves the budget already debited (fail-safe over-count) AND an
    # unreconciled reservation that the pre-cycle orphan check must catch.
    store = _store(tmp_path)
    _open(store)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    # simulate crash: no reconcile happens
    assert store.has_unreconciled_reservation(epoch_id="e1") is True
    orphans = store.unreconciled_reservations(epoch_id="e1")
    assert len(orphans) == 1 and orphans[0]["reservation_key"] == "k1"
    # budget already debited (not under-counted)
    assert _ledger_row(store, "e1")[1] == 100.0


def test_reconcile_clears_orphan_and_bumps_up_only(tmp_path):
    store = _store(tmp_path)
    _open(store, max_gross_turnover_usdt=600.0)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    # realized exceeded the reserve -> ledger bumps UP by the difference
    store.reconcile_reservation(reservation_key="k1", realized_turnover_usdt=150.0, now_utc=T0)
    assert _ledger_row(store, "e1")[1] == 150.0
    assert store.has_unreconciled_reservation(epoch_id="e1") is False
    with sqlite3.connect(store.path) as conn:
        assert conn.execute(
            "SELECT status FROM unattended_budget_reservations WHERE reservation_key='k1'"
        ).fetchone()[0] == RESV_RECONCILED


def test_reconcile_never_decreases_budget(tmp_path):
    store = _store(tmp_path)
    _open(store, max_gross_turnover_usdt=600.0)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    # realized BELOW the reserve -> budget is NOT returned (conservative)
    store.reconcile_reservation(reservation_key="k1", realized_turnover_usdt=40.0, now_utc=T0)
    assert _ledger_row(store, "e1")[1] == 100.0


def test_reconcile_over_budget_marks_terminal(tmp_path):
    store = _store(tmp_path)
    _open(store, max_live_cycles=10, max_gross_turnover_usdt=150.0)
    store.reserve(epoch_id="e1", reservation_key="k1", run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    store.reconcile_reservation(reservation_key="k1", realized_turnover_usdt=200.0, now_utc=T0)
    # consumed turnover 200 > 150 ceiling -> epoch terminal, no longer open
    assert store.read_current_epoch() is None
    assert _ledger_row(store, "e1")[2] == "exhausted"


def test_reconcile_unknown_reservation_reports_not_found(tmp_path):
    store = _store(tmp_path)
    _open(store)
    out = store.reconcile_reservation(reservation_key="nope", realized_turnover_usdt=10.0, now_utc=T0)
    assert out["status"] == "not_found"
