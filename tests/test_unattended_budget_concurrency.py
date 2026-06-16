from __future__ import annotations

import multiprocessing as mp
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
SRC = ROOT / "src"
# tests/ must be on sys.path so the spawned children (which inherit this sys.path)
# can import the top-level worker module by reference.
for path in (TESTS_DIR, ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402

from _budget_concurrency_worker import reserve_many  # noqa: E402

T0 = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


def _ledger_row(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT consumed_cycles, consumed_turnover_usdt, status FROM unattended_budget_ledger WHERE epoch_id='e1'"
        ).fetchone()


def _reserved_reservation_count(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM unattended_budget_reservations WHERE status='reserved'"
        ).fetchone()[0]


def _run_pool(db_path, jobs, procs):
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=procs) as pool:
        return pool.starmap(reserve_many, jobs)


def test_concurrent_reserves_never_overspend_cycle_budget(tmp_path):
    # 8 processes x 12 distinct keys = 96 reserve attempts against a 20-cycle
    # budget. The atomic conditional UPDATE must let through EXACTLY 20, no more.
    db = tmp_path / "state" / "live.sqlite3"
    store = UnattendedBudgetStore(db)
    MAX_CYCLES = 20
    PROJ = 5.0
    store.open_epoch(
        epoch_id="e1", max_live_cycles=MAX_CYCLES, max_gross_turnover_usdt=100000.0,
        max_age_seconds=999999, now_utc=T0,
    )
    procs, per = 8, 12
    jobs = [(str(db), "e1", [f"k-{p}-{i}" for i in range(per)], PROJ) for p in range(procs)]
    results = _run_pool(str(db), jobs, procs)

    total_reserved = sum(r for r, _ in results)
    consumed_cycles, consumed_turnover, status = _ledger_row(db)
    # SAFETY: never over-spend the cycle budget
    assert consumed_cycles <= MAX_CYCLES
    # no double-debit: ledger count == sum of 'reserved' results == reservation rows
    assert consumed_cycles == total_reserved
    assert consumed_cycles == _reserved_reservation_count(db)
    # with 96 attempts the 20-cycle budget is fully (and exactly) claimed
    assert consumed_cycles == MAX_CYCLES
    assert consumed_turnover == MAX_CYCLES * PROJ
    assert status == "exhausted"


def test_concurrent_reserves_never_overspend_turnover_budget(tmp_path):
    # Turnover is the binding constraint: budget 100, proj 5 -> at most 20 reserves.
    db = tmp_path / "state" / "live.sqlite3"
    store = UnattendedBudgetStore(db)
    PROJ = 5.0
    MAX_TURNOVER = 100.0
    store.open_epoch(
        epoch_id="e1", max_live_cycles=100000, max_gross_turnover_usdt=MAX_TURNOVER,
        max_age_seconds=999999, now_utc=T0,
    )
    procs, per = 8, 10
    jobs = [(str(db), "e1", [f"k-{p}-{i}" for i in range(per)], PROJ) for p in range(procs)]
    results = _run_pool(str(db), jobs, procs)

    total_reserved = sum(r for r, _ in results)
    consumed_cycles, consumed_turnover, _ = _ledger_row(db)
    # SAFETY: never over-spend the turnover budget
    assert consumed_turnover <= MAX_TURNOVER + 1e-9
    assert consumed_cycles == total_reserved
    # fully claimed: exactly 20 reserves of 5 == 100
    assert consumed_turnover == MAX_TURNOVER
    assert consumed_cycles == 20


def test_concurrent_same_key_debits_exactly_once(tmp_path):
    # All 8 processes hammer the SAME reservation key. Idempotency (PK + rollback)
    # must debit exactly once regardless of the race.
    db = tmp_path / "state" / "live.sqlite3"
    store = UnattendedBudgetStore(db)
    store.open_epoch(
        epoch_id="e1", max_live_cycles=50, max_gross_turnover_usdt=100000.0,
        max_age_seconds=999999, now_utc=T0,
    )
    procs = 8
    jobs = [(str(db), "e1", ["shared-key"], 7.0) for _ in range(procs)]
    results = _run_pool(str(db), jobs, procs)

    total_reserved = sum(r for r, _ in results)
    total_already = sum(a for _, a in results)
    consumed_cycles, consumed_turnover, _ = _ledger_row(db)
    # exactly one debit for the shared key, no double-spend
    assert consumed_cycles == 1
    assert consumed_turnover == 7.0
    # exactly one process won the 'reserved'; the rest saw 'already_reserved'
    assert total_reserved == 1
    assert total_already == procs - 1
