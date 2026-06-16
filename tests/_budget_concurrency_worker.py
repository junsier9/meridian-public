"""Top-level worker for the multiprocess budget concurrency stress test.

Must live in its own importable module (not inside the test) so the spawn-start
child processes (Windows default) can import it by reference. Sets up sys.path at
import time so the child finds the package.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _p in (ROOT, SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402


def reserve_many(db_path: str, epoch_id: str, keys: list[str], proj: float) -> tuple[int, int]:
    """Attempt a reserve for each key; return (reserved_count, already_reserved_count).

    Retries transiently on SQLITE_BUSY beyond the busy_timeout so the test is not
    flaky under heavy contention; a genuine no-budget result is NOT a retry.
    """
    store = UnattendedBudgetStore(db_path)
    reserved = 0
    already = 0
    for key in keys:
        result = None
        for _attempt in range(5):
            try:
                result = store.reserve(
                    epoch_id=epoch_id,
                    reservation_key=key,
                    run_id=key,
                    projected_turnover_usdt=proj,
                )
                break
            except sqlite3.OperationalError:
                result = None
        if result is None:
            continue
        status = str(result.get("status"))
        if status == "reserved":
            reserved += 1
        elif status == "already_reserved":
            already += 1
    return reserved, already
