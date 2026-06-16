"""wallet_compounding_policy — pure, IO-free resolution of the equity-tracking
(continuous-compounding) sizing equity and the FAIL-CLOSED cap stack for the live book.

No scoring, no orders, no filesystem, no config writes. Mirrors the frozen-frontier
contract pattern:

  * DEFAULT-OFF. Callers gate every use on ``capital.equity_compounding_v2_enabled``.
    With the flag falsey the legacy ``max(pin, resolved)`` behaviour is byte-for-byte
    unchanged (the v2 helpers are simply never called).
  * FAIL-CLOSED when on. A bad/stale wallet read, an unresolved absolute ceiling, or a
    non-finite input collapses the deployable book to 0 AND appends an explicit blocker
    (surfaced through ``risk["_wallet_v2_blockers"]`` -> ``evaluate_risk_gate``), so a
    zero cap can never be mistaken for "no cap / disabled".

Design contract (owner, 2026-06-10):
  - Caps are CEILINGS (``min``), never floors. This is the fix for the legacy
    ``max(pin, resolved)`` lift that turned the pinned risk caps into floors and left
    the book unbounded as the wallet grew.
  - Equity tracks Binance ``totalWalletBalance`` (= principal + realized PnL; NO
    unrealized PnL), so "compound on realized PnL" is correct by construction.
  - On a drawdown the book de-risks to current wallet (intrinsic anti-martingale); there
    is NO external daily-loss breaker (owner decision).
  - Leverage: min 1x (unreadable / <1 fails closed, never silently 1x); the venue/automation
    cap (2x) is enforced by the caller; 4x is owner-attended only and never on the timer path.
"""

from __future__ import annotations

import math
from typing import Any

# Flag key under config["capital"]. Off => legacy path, byte-identical.
V2_FLAG = "equity_compounding_v2_enabled"

# --- Owner-tuned defaults (2026-06-10). All overridable via config. ---
DEFAULT_LEVERAGE_MULT = 2.0                  # book = equity * mult (the 2x target)
DEFAULT_COMPOUNDING_FRACTION = 1.0           # f: full realized-PnL compounding
DEFAULT_K_OP = 2.3                           # automation operational gross-leverage clamp
DEFAULT_K_ABS = 4.0                          # hard gross-leverage ceiling (owner red line)
DEFAULT_MAX_BOOK_GROWTH_PER_CYCLE = 0.15     # g_organic: per-slot book growth limiter
DEFAULT_RESERVE_FLOOR_ABS = 300.0
DEFAULT_RESERVE_FLOOR_RATIO = 0.03           # reserve = max(abs, ratio * wallet)
DEFAULT_DEPOSIT_AUTO_ADMIT_ABS = 500.0
DEFAULT_DEPOSIT_AUTO_ADMIT_RATIO = 0.05      # admit threshold = max(abs, ratio * wallet)
DEFAULT_MAX_ADV_PARTICIPATION = 0.02         # per-cycle per-symbol incremental order <= 2% ADV
MIN_LEVERAGE = 1
DEFAULT_AUTOMATION_LEVERAGE = 2              # never exceeded on the timer / delta path


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _min_present(*values: float | None) -> float | None:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def reserve_floor_usdt(capital: dict[str, Any], wallet_balance: Any) -> float:
    """Hybrid reserve: ``max(absolute, ratio * wallet)``. A legacy scalar
    ``capital.reserve_floor_usdt`` is honoured as the absolute term."""
    abs_floor = _finite(capital.get("reserve_floor_abs_usdt"))
    if abs_floor is None:
        abs_floor = _finite(capital.get("reserve_floor_usdt"), DEFAULT_RESERVE_FLOOR_ABS)
    ratio = _finite(capital.get("reserve_floor_ratio"), DEFAULT_RESERVE_FLOOR_RATIO) or 0.0
    wb = max(0.0, _finite(wallet_balance, 0.0) or 0.0)
    return max(float(abs_floor or 0.0), ratio * wb)


def resolve_sizing_equity(*, capital: dict[str, Any], wallet_balance: Any) -> dict[str, Any]:
    """Deployable sizing equity.

        E = max(0, min(wallet - reserve, (principal - reserve) + f * max(0, wallet - principal)))

    The outer ``min(wallet - reserve, ...)`` keeps the reserve withheld from the whole base
    even when a pinned principal is below the reserve floor. On the upside (wallet >= principal)
    f governs how much *profit* is deployed vs banked
    (f=1 => full compounding => E = wallet - reserve). On a drawdown (wallet < principal)
    the second term is 0 and the first tracks ``wallet`` down, so the book de-risks to
    current equity regardless of f (intrinsic anti-martingale).

    ``wallet_balance`` is Binance ``totalWalletBalance`` (principal + realized PnL; no
    unrealized). The net-deposit anchor is read from ``initial_capital_usdt`` (preferred,
    self-describing) or the legacy ``principal_baseline_usdt`` alias; both are accepted and a
    set-and-disagree pair fails closed (``principal_anchor_keys_conflict``). It is bumped only
    on an acknowledged deposit. An UNSET anchor with full compounding (f == 1) bootstraps to the
    current wallet (no recognised profit => E reduces to ``wallet - reserve``, legacy-equivalent
    sizing); an unset anchor with PARTIAL compounding (f < 1) fails closed
    (``principal_anchor_required_for_partial_compounding``) rather than silently sizing off the
    wallet. NOTE (Phase 1): this resolver is not yet wired into the live caller
    (``_apply_wallet_v2_caps`` backs equity out of the already-resolved capital); the anchor
    keys + guard protect the anchored-compounding path for when it is wired (Phase 2).
    """
    wb = _finite(wallet_balance)
    if wb is None or wb < 0.0:
        return {
            "ok": False,
            "blockers": ["wallet_balance_unreadable_or_negative"],
            "equity": 0.0,
            "wallet_balance": 0.0,
        }
    f = _finite(capital.get("compounding_fraction"), DEFAULT_COMPOUNDING_FRACTION) or 0.0
    f = min(1.0, max(0.0, f))
    # Net-deposit anchor. ``initial_capital_usdt`` is the explicit, self-describing key;
    # ``principal_baseline_usdt`` is the legacy alias. Both are accepted; if both are set they
    # MUST agree (a silent mismatch would size the book off the wrong base => fail closed).
    anchor_explicit = _finite(capital.get("initial_capital_usdt"))
    anchor_legacy = _finite(capital.get("principal_baseline_usdt"))
    if anchor_explicit is not None and anchor_explicit < 0.0:
        anchor_explicit = None
    if anchor_legacy is not None and anchor_legacy < 0.0:
        anchor_legacy = None
    if (
        anchor_explicit is not None
        and anchor_legacy is not None
        and abs(anchor_explicit - anchor_legacy) > 1e-9
    ):
        return {
            "ok": False,
            "blockers": ["principal_anchor_keys_conflict"],
            "equity": 0.0,
            "wallet_balance": float(wb),
        }
    principal = anchor_explicit if anchor_explicit is not None else anchor_legacy
    if principal is None:
        # No explicit anchor. With FULL compounding (f == 1) "follow wallet" is well-defined and
        # is the documented legacy-equivalent sizing, so bootstrap principal to the wallet. With
        # PARTIAL compounding (f < 1) an unset anchor would SILENTLY size off the wallet instead
        # of the intended anchored base, so fail closed rather than degrade silently.
        if f < 1.0:
            return {
                "ok": False,
                "blockers": ["principal_anchor_required_for_partial_compounding"],
                "equity": 0.0,
                "wallet_balance": float(wb),
            }
        principal = wb
    reserve = reserve_floor_usdt(capital, wb)
    realized_profit = wb - principal
    # Reserve is withheld from the WHOLE base, so the deployable equity can never exceed
    # (wallet - reserve) even when the pinned principal_baseline is below the reserve floor.
    # On a drawdown (wallet < principal) the second term is 0 and the cap binds at
    # wallet - reserve (de-risk). On the upside f governs how much profit is deployed.
    equity = max(
        0.0,
        min(wb - reserve, (principal - reserve) + f * max(0.0, realized_profit)),
    )
    return {
        "ok": True,
        "blockers": [],
        "equity": float(equity),
        "wallet_balance": float(wb),
        "principal_baseline": float(principal),
        "realized_profit": float(realized_profit),
        "reserve_floor": float(reserve),
        "compounding_fraction": float(f),
    }


def resolve_effective_caps(
    *,
    equity: float,
    wallet_balance: float,
    capital: dict[str, Any],
    risk: dict[str, Any],
    applied_book_prev: float | None = None,
    deposit_growth_override: float | None = None,
) -> dict[str, Any]:
    """Min-clamped ceiling stack. Returns
    ``{"risk_caps": {...}, "diagnostics": {...}, "blockers": [...]}``.

        book_equity = equity * leverage_mult                       (compounding target)
        book = min(book_equity, k_op*wallet, abs_ceiling,          (operational + hard)
                   applied_book_prev*(1+g))                        (growth limiter)

    The absolute ceiling is inviolable (re-applied after the growth limiter). A deposit
    cycle may raise the per-cycle growth to its impact budget via
    ``deposit_growth_override`` (still bounded by the absolute ceiling). ``abs_ceiling``
    defaults to ``k_abs * wallet`` (R7.1); an unresolved/<=0 ceiling fails closed.
    """
    blockers: list[str] = []
    lev = _finite(capital.get("leverage_mult"), DEFAULT_LEVERAGE_MULT) or DEFAULT_LEVERAGE_MULT
    k_op = _finite(capital.get("operational_gross_leverage_cap"), DEFAULT_K_OP) or DEFAULT_K_OP
    # k_abs may be tightened but NEVER loosened above the 4.0 red line (an over-large config
    # value must not silently relax the inviolable ceiling).
    k_abs = min(DEFAULT_K_ABS, _finite(risk.get("abs_max_gross_leverage"), DEFAULT_K_ABS) or DEFAULT_K_ABS)
    wb = max(0.0, _finite(wallet_balance, 0.0) or 0.0)
    eq = max(0.0, _finite(equity, 0.0) or 0.0)

    book_equity = eq * lev
    op_ceiling = k_op * wb

    # Absolute ceiling = min(explicit pin, k_abs*wallet). A stale-high explicit pin can never
    # exceed the wallet-relative hard cap, so the ceiling always tracks the wallet down.
    abs_pin = _finite(risk.get("abs_max_gross_notional_usdt"))
    wallet_abs = (k_abs * wb) if wb > 0.0 else None
    abs_ceiling = _min_present(abs_pin, wallet_abs)
    if abs_ceiling is None or abs_ceiling <= 0.0:
        blockers.append("abs_max_gross_notional_unresolved")
        abs_ceiling = 0.0

    book = min(book_equity, op_ceiling, abs_ceiling)
    growth_clamped = False
    prev = _finite(applied_book_prev)
    if prev is not None and prev > 0.0:
        g = _finite(capital.get("max_book_growth_per_cycle"), DEFAULT_MAX_BOOK_GROWTH_PER_CYCLE) or 0.0
        allowed = deposit_growth_override if deposit_growth_override is not None else g
        growth_ceiling = prev * (1.0 + max(0.0, allowed))
        if book > growth_ceiling:
            book = growth_ceiling
            growth_clamped = True
    book = min(book, abs_ceiling)  # absolute ceiling is inviolable
    # Fail-closed: a 0 cap reads as "no cap" in risk_gate, so a non-positive book (equity=0,
    # stale/zero wallet, non-finite leverage_mult, ...) MUST surface an explicit blocker —
    # otherwise the operational cap is silently bypassed while the portfolio still carries
    # its raw (un-clamped, Phase-1) allocation.
    if book <= 0.0:
        blockers.append("resolved_book_non_positive")

    sym_w = _finite(capital.get("max_symbol_weight_cap"))
    ord_w = _finite(capital.get("max_order_weight_cap"))
    abs_symbol = _finite(risk.get("abs_max_symbol_notional_usdt"))
    abs_order = _finite(risk.get("abs_max_order_notional_usdt"))
    max_symbol = _min_present(book * sym_w if sym_w is not None else None, abs_symbol)
    max_order = _min_present(book * ord_w if ord_w is not None else None, abs_order)

    risk_caps: dict[str, Any] = {
        "max_allocated_capital_usdt": float(book),
        "max_gross_notional_usdt": float(book),
        "abs_max_allocated_capital_usdt": float(abs_ceiling),
        "abs_max_gross_notional_usdt": float(abs_ceiling),
    }
    if max_symbol is not None:
        risk_caps["max_symbol_notional_usdt"] = float(max_symbol)
    if abs_symbol is not None:
        risk_caps["abs_max_symbol_notional_usdt"] = float(abs_symbol)
    if max_order is not None:
        risk_caps["max_order_notional_usdt"] = float(max_order)

    return {
        "risk_caps": risk_caps,
        "blockers": sorted(set(blockers)),
        "diagnostics": {
            "book_equity_usdt": float(book_equity),
            "op_ceiling_usdt": float(op_ceiling),
            "abs_ceiling_usdt": float(abs_ceiling),
            "resolved_book_usdt": float(book),
            "growth_clamped": bool(growth_clamped),
            "leverage_mult": float(lev),
            "k_op": float(k_op),
            "k_abs": float(k_abs),
        },
    }


def leverage_policy_blockers(
    leverage_raw: Any,
    *,
    symbol: str,
    max_allowed_leverage: int,
    min_leverage: int = MIN_LEVERAGE,
) -> list[str]:
    """Fail-closed venue-leverage check. Unreadable / below-min blocks (never a silent
    1x); above the automation cap blocks (the remote auto-adjust happens in the prepare
    stage, then the snapshot is re-read and re-checked here)."""
    lev = _finite(leverage_raw)
    if lev is None or lev < float(min_leverage):
        return [f"leverage_unreadable_or_below_min:{symbol}:actual={leverage_raw!r}:min={min_leverage}"]
    if max_allowed_leverage > 0 and int(lev) > max_allowed_leverage:
        return [f"leverage_above_max:{symbol}:max={max_allowed_leverage}:actual={int(lev)}"]
    return []


def deposit_admission_threshold_usdt(capital: dict[str, Any], wallet_balance: Any) -> float:
    """Admission threshold = ``max(abs, ratio * wallet)``. A wallet jump above this is a
    *deposit* that requires an owner token before it may expand the book (Phase 2); below
    it is treated as organic (fees / funding / dust) and auto-admitted."""
    abs_t = _finite(capital.get("deposit_auto_admit_threshold_usdt"), DEFAULT_DEPOSIT_AUTO_ADMIT_ABS) or 0.0
    ratio = _finite(capital.get("deposit_auto_admit_ratio"), DEFAULT_DEPOSIT_AUTO_ADMIT_RATIO) or 0.0
    wb = max(0.0, _finite(wallet_balance, 0.0) or 0.0)
    return max(float(abs_t), ratio * wb)


def deposit_impact_tranche_count(
    *,
    per_symbol_increment_usdt: dict[str, float],
    adv_usdt_by_symbol: dict[str, float],
    max_participation: float = DEFAULT_MAX_ADV_PARTICIPATION,
) -> dict[str, Any]:
    """Number of equal tranches to admit a deposit's incremental book so that every
    symbol's per-cycle incremental order stays within ``max_participation * ADV``.

        tranche_count = max_symbol( ceil(increment_s / (participation * ADV_s)) ), floored at 1

    A symbol with a positive increment but missing/zero ADV CANNOT be impact-bounded and
    is a fail-closed blocker (the caller must not auto-deploy it in one shot). Returns the
    count, the binding (most-constrained) symbol, and per-symbol participation diagnostics.
    """
    blockers: list[str] = []
    participation = _finite(max_participation, DEFAULT_MAX_ADV_PARTICIPATION) or DEFAULT_MAX_ADV_PARTICIPATION
    if participation <= 0.0:
        return {"tranche_count": 1, "binding_symbol": "", "blockers": ["impact_participation_non_positive"],
                "per_symbol": {}}
    per_symbol: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    for symbol, increment in (per_symbol_increment_usdt or {}).items():
        inc = _finite(increment, 0.0) or 0.0
        if inc <= 0.0:
            continue
        adv = _finite((adv_usdt_by_symbol or {}).get(symbol))
        if adv is None or adv <= 0.0:
            blockers.append(f"deposit_impact_adv_missing:{symbol}")
            continue
        budget_per_cycle = participation * adv
        count = int(math.ceil(inc / budget_per_cycle))
        counts[symbol] = max(1, count)
        per_symbol[symbol] = {
            "increment_usdt": float(inc),
            "adv_usdt": float(adv),
            "budget_per_cycle_usdt": float(budget_per_cycle),
            "tranches": float(counts[symbol]),
        }
    binding_symbol = max(counts, key=counts.get) if counts else ""
    tranche_count = max([1, *counts.values()]) if counts else 1
    return {
        "tranche_count": int(tranche_count),
        "binding_symbol": binding_symbol,
        "max_participation": float(participation),
        "per_symbol": per_symbol,
        "blockers": sorted(set(blockers)),
    }
