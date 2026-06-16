from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.live_risk_controls import (  # noqa: E402
    evaluate_per_order_notional_gate,
)
from enhengclaw.live_trading.unattended_budget_hook import (  # noqa: E402
    per_order_gate_enabled,
    per_order_hard_multiplier,
    resolved_per_order_notional_cap,
)


def _has(result, fragment):
    return any(fragment in b for b in result["blockers"])


# -- pure gate ---------------------------------------------------------------
def test_legit_orders_under_ceiling_pass():
    # cap 1034, multiplier 1.5 -> ceiling 1551; legit orders up to ~1100 pass
    rows = [{"symbol": "BTCUSDT", "rounded_notional_usdt": 1097.0, "reduce_only": False}]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0, hard_multiplier=1.5)
    assert r["passed"] is True, r["blockers"]
    assert r["ceiling_usdt"] == 1551.0


def test_gross_oversized_order_blocked():
    rows = [{"symbol": "BTCUSDT", "rounded_notional_usdt": 5000.0, "reduce_only": False}]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0, hard_multiplier=1.5)
    assert r["passed"] is False
    assert _has(r, "order_notional_exceeds_cap:BTCUSDT")
    assert r["offending_orders"] == [{"symbol": "BTCUSDT", "notional_usdt": 5000.0}]


def test_reduce_only_oversized_is_exempt():
    # a large de-risking order must never be blocked
    rows = [{"symbol": "ARBUSDT", "rounded_notional_usdt": 9000.0, "reduce_only": True}]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0, hard_multiplier=1.5)
    assert r["passed"] is True
    assert r["checked_order_count"] == 0


def test_exact_ceiling_passes():
    rows = [{"symbol": "X", "rounded_notional_usdt": 1551.0, "reduce_only": False}]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0, hard_multiplier=1.5)
    assert r["passed"] is True


def test_cap_not_configured_fails_closed_when_required():
    r = evaluate_per_order_notional_gate(
        [{"symbol": "X", "rounded_notional_usdt": 10.0, "reduce_only": False}],
        per_order_notional_cap_usdt=None,
        require_configured=True,
    )
    assert r["passed"] is False
    assert _has(r, "per_order_notional_cap_not_configured")


def test_cap_not_configured_is_noop_when_not_required():
    r = evaluate_per_order_notional_gate(
        [{"symbol": "X", "rounded_notional_usdt": 1e9, "reduce_only": False}],
        per_order_notional_cap_usdt=None,
        require_configured=False,
    )
    assert r["passed"] is True
    assert r["status"] == "not_configured"


def test_unreadable_notional_blocks():
    rows = [{"symbol": "X", "rounded_notional_usdt": "oops", "reduce_only": False}]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0)
    assert r["passed"] is False
    assert _has(r, "per_order_notional_unreadable:X")


def test_mixed_batch_blocks_only_offender():
    rows = [
        {"symbol": "BTCUSDT", "rounded_notional_usdt": 1000.0, "reduce_only": False},
        {"symbol": "ETHUSDT", "rounded_notional_usdt": 4000.0, "reduce_only": False},
        {"symbol": "ARBUSDT", "rounded_notional_usdt": 8000.0, "reduce_only": True},
    ]
    r = evaluate_per_order_notional_gate(rows, per_order_notional_cap_usdt=1034.0, hard_multiplier=1.5)
    assert r["passed"] is False
    assert _has(r, "order_notional_exceeds_cap:ETHUSDT")
    assert not _has(r, "BTCUSDT")
    assert not _has(r, "ARBUSDT")
    assert r["checked_order_count"] == 2  # reduce-only excluded


# -- cap source + flag helpers -----------------------------------------------
def test_resolved_cap_prefers_resolved_over_static():
    payload = {
        "risk": {"max_order_notional_usdt": 600.0},
        "capital": {"max_order_weight_cap": 0.35},
    }
    ctx = {"resolved_allocated_capital_usdt": 3000.0}
    cap = resolved_per_order_notional_cap(payload, ctx, capital_topup_selected=False)
    # 3000.0 * 0.35 = 1034.18 > static 600
    assert abs(cap - 1034.18) < 0.5


def test_resolved_cap_falls_back_to_static_when_no_context():
    payload = {"risk": {"max_order_notional_usdt": 600.0}, "capital": {"max_order_weight_cap": 0.35}}
    cap = resolved_per_order_notional_cap(payload, {}, capital_topup_selected=False)
    assert cap == 600.0


def test_resolved_cap_uses_topup_weight_when_selected():
    payload = {
        "risk": {"max_order_notional_usdt": 600.0},
        "capital": {"max_order_weight_cap": 0.10},
        "capital_topup": {"max_order_weight_cap": 0.35},
    }
    ctx = {"resolved_allocated_capital_usdt": 3000.0}
    cap = resolved_per_order_notional_cap(payload, ctx, capital_topup_selected=True)
    assert abs(cap - 1034.18) < 0.5  # uses topup 0.35, not capital 0.10


def test_per_order_gate_flag_defaults_false():
    assert per_order_gate_enabled({}) is False
    assert per_order_gate_enabled({"risk": {"per_order_notional_gate_enabled": True}}) is True


def test_per_order_multiplier_default_and_override():
    assert per_order_hard_multiplier({}) == 1.5
    assert per_order_hard_multiplier({"risk": {"per_order_notional_hard_multiplier": 2.0}}) == 2.0
    # non-positive / bad -> default
    assert per_order_hard_multiplier({"risk": {"per_order_notional_hard_multiplier": 0}}) == 1.5
