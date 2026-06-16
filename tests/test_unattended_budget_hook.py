from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.unattended_budget_hook import (  # noqa: E402
    ORPHAN_BLOCKER,
    budget_gate_enabled,
    post_submit_reconcile,
    pre_submit_budget_blockers,
    projected_turnover_usdt,
    realized_turnover_usdt,
    reconcile_or_block_realized,
    reservation_key,
    reserved_ok,
)
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402

T0 = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


def _store(tmp_path):
    s = UnattendedBudgetStore(tmp_path / "state" / "live.sqlite3")
    s.open_epoch(epoch_id="e1", max_live_cycles=6, max_gross_turnover_usdt=600.0, max_age_seconds=3600, now_utc=T0)
    return s


# -- config flag --------------------------------------------------------------
def test_budget_gate_enabled_defaults_false():
    assert budget_gate_enabled({}) is False
    assert budget_gate_enabled({"core_loop": {}}) is False
    assert budget_gate_enabled({"core_loop": {"unattended_budget_gate_enabled": True}}) is True
    assert budget_gate_enabled({"core_loop": {"unattended_budget_gate_enabled": "true"}}) is True


# -- B1: reconcile-or-block on unmeasured realized turnover --------------------
def test_reconcile_or_block_realized_blocks_when_orders_submitted_but_realized_none():
    may, blocker = reconcile_or_block_realized(orders_submitted=1, realized_turnover=None)
    assert may is False
    assert blocker == "unattended_budget_realized_turnover_unmeasured"


def test_reconcile_or_block_realized_allows_when_realized_known():
    assert reconcile_or_block_realized(orders_submitted=3, realized_turnover=42.0) == (True, None)


def test_reconcile_or_block_realized_allows_when_no_orders_submitted():
    # No orders submitted -> nothing to measure; the reserve over-counted (conservative) -> reconcile.
    assert reconcile_or_block_realized(orders_submitted=0, realized_turnover=None) == (True, None)


def test_b1_skipping_reconcile_leaves_orphan_for_next_cycle(tmp_path):
    # End-to-end at the store level: a reserved cycle that does NOT reconcile (the B1 unmeasured
    # path) leaves the reservation as an orphan, so the NEXT cycle's pre-submit orphan check fails
    # closed. Silently reconciling would clear it and under-count the budget.
    store = _store(tmp_path)
    key = reservation_key("e1", "plan-1", 1)
    assert reserved_ok(
        store.reserve(epoch_id="e1", reservation_key=key, run_id="r1", projected_turnover_usdt=100.0, now_utc=T0)
    )
    may, _ = reconcile_or_block_realized(orders_submitted=1, realized_turnover=None)
    assert may is False
    assert store.has_unreconciled_reservation(epoch_id="e1") is True
    # Contrast: an actual reconcile clears the orphan.
    post_submit_reconcile(store, reserved=True, reservation_key=key, realized_turnover=100.0, now=T0)
    assert store.has_unreconciled_reservation(epoch_id="e1") is False


# -- projected turnover -------------------------------------------------------
def test_projected_turnover_sums_abs_notional():
    pj = projected_turnover_usdt({"rows": [{"rounded_notional_usdt": 75.0}, {"rounded_notional_usdt": -40.0}]})
    assert pj == 115.0


def test_projected_turnover_zero_with_planned_orders_is_none():
    # a submitting plan that computes zero notional must fail closed, not pass free
    pj = projected_turnover_usdt({"row_count": 2, "rows": [{"rounded_notional_usdt": 0.0}, {"rounded_notional_usdt": 0.0}]})
    assert pj is None


def test_projected_turnover_no_rows_is_zero():
    assert projected_turnover_usdt({"rows": []}) == 0.0


def test_projected_turnover_unreadable_row_is_none():
    assert projected_turnover_usdt({"rows": [{"rounded_notional_usdt": "x"}]}) is None
    assert projected_turnover_usdt({"rows": [{"rounded_notional_usdt": float("nan")}]}) is None


# -- realized turnover --------------------------------------------------------
def test_realized_turnover_takes_max_of_fill_and_submitted():
    ex = {
        "fills": [{"notional_usdt": 50.0}],
        "submitted_orders": [{"planned_rounded_notional_usdt": 75.0}],
    }
    # submitted exposure (75) exceeds realized fills (50) -> charge 75
    assert realized_turnover_usdt(ex) == 75.0


def test_realized_turnover_none_when_empty():
    assert realized_turnover_usdt({"fills": [], "submitted_orders": []}) is None


def test_realized_turnover_fills_only():
    assert realized_turnover_usdt({"fills": [{"notional_usdt": 63.0}], "submitted_orders": []}) == 63.0


# -- reservation key ----------------------------------------------------------
def test_reservation_key_stable():
    assert reservation_key("e1", "planhash", 1) == "e1:planhash:1"


# -- pre-submit reserve / orphan ----------------------------------------------
def test_disabled_returns_no_blockers(tmp_path):
    store = _store(tmp_path)
    blockers, result = pre_submit_budget_blockers(
        store, enabled=False, epoch=store.read_current_epoch(),
        projected_turnover=100.0, run_id="r1", reservation_key="k1", now=T0,
    )
    assert blockers == []
    assert result["status"] == "disabled"


def test_no_epoch_blocks(tmp_path):
    store = UnattendedBudgetStore(tmp_path / "state" / "live.sqlite3")  # no epoch opened
    store.initialize()
    blockers, result = pre_submit_budget_blockers(
        store, enabled=True, epoch=None, projected_turnover=100.0, run_id="r1", reservation_key="k1", now=T0,
    )
    assert "unattended_budget_no_open_epoch" in blockers


def test_reserve_succeeds_then_reconcile_clears(tmp_path):
    store = _store(tmp_path)
    epoch = store.read_current_epoch()
    blockers, result = pre_submit_budget_blockers(
        store, enabled=True, epoch=epoch, projected_turnover=100.0, run_id="r1", reservation_key="k1", now=T0,
    )
    assert blockers == []
    assert reserved_ok(result) is True
    # while unreconciled, a NEW cycle must fail closed on the orphan
    blockers2, result2 = pre_submit_budget_blockers(
        store, enabled=True, epoch=store.read_current_epoch(), projected_turnover=50.0,
        run_id="r2", reservation_key="k2", now=T0,
    )
    assert ORPHAN_BLOCKER in blockers2
    # reconcile the first, then the orphan clears
    rc = post_submit_reconcile(store, reserved=True, reservation_key="k1", realized_turnover=120.0, now=T0)
    assert rc["status"] == "reconciled"
    blockers3, result3 = pre_submit_budget_blockers(
        store, enabled=True, epoch=store.read_current_epoch(), projected_turnover=50.0,
        run_id="r3", reservation_key="k3", now=T0,
    )
    assert blockers3 == []
    assert reserved_ok(result3) is True


def test_exhausted_budget_blocks(tmp_path):
    store = UnattendedBudgetStore(tmp_path / "state" / "live.sqlite3")
    store.open_epoch(epoch_id="e1", max_live_cycles=1, max_gross_turnover_usdt=10000.0, max_age_seconds=3600, now_utc=T0)
    b1, r1 = pre_submit_budget_blockers(
        store, enabled=True, epoch=store.read_current_epoch(), projected_turnover=10.0,
        run_id="r1", reservation_key="k1", now=T0,
    )
    assert reserved_ok(r1) is True
    post_submit_reconcile(store, reserved=True, reservation_key="k1", realized_turnover=10.0, now=T0)
    # epoch exhausted -> read_current_epoch None -> next pre-submit blocks
    b2, r2 = pre_submit_budget_blockers(
        store, enabled=True, epoch=store.read_current_epoch(), projected_turnover=10.0,
        run_id="r2", reservation_key="k2", now=T0,
    )
    assert "unattended_budget_no_open_epoch" in b2


def test_projected_none_blocks_reserve(tmp_path):
    store = _store(tmp_path)
    blockers, result = pre_submit_budget_blockers(
        store, enabled=True, epoch=store.read_current_epoch(), projected_turnover=None,
        run_id="r1", reservation_key="k1", now=T0,
    )
    assert reserved_ok(result) is False
    assert any("projected_turnover_unknown" in b for b in blockers)


def test_post_submit_reconcile_skipped_when_not_reserved(tmp_path):
    store = _store(tmp_path)
    out = post_submit_reconcile(store, reserved=False, reservation_key="k1", realized_turnover=10.0, now=T0)
    assert out["status"] == "skipped_not_reserved"
