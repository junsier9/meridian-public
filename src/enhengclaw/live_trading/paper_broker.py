from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from enhengclaw.live_trading.models import ExecutionPlan


DEFAULT_PAPER_TAKER_FEE_RATE = 0.0004


@dataclass(slots=True)
class PaperExecutionResult:
    run_id: str
    plan_id: str
    status: str
    blockers: list[str] = field(default_factory=list)
    fee_rate: float = DEFAULT_PAPER_TAKER_FEE_RATE
    submitted_orders: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    fills: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    account_before: dict[str, Any] = field(default_factory=dict)
    account_after: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "blockers": list(self.blockers),
            "fee_rate": self.fee_rate,
            "submitted_order_count": int(len(self.submitted_orders)),
            "fill_count": int(len(self.fills)),
            "account_before": dict(self.account_before),
            "account_after": dict(self.account_after),
            "reconciliation": dict(self.reconciliation),
        }


def simulate_paper_execution(
    plan: ExecutionPlan,
    *,
    mark_prices: dict[str, float],
    run_id: str,
    created_at_utc: str,
    current_positions: dict[str, float] | None = None,
    fee_rate: float = DEFAULT_PAPER_TAKER_FEE_RATE,
) -> PaperExecutionResult:
    blockers: list[str] = []
    if plan.mode != "paper":
        blockers.append(f"unsupported_paper_mode:{plan.mode}")
    if plan.status != "ok":
        blockers.append("execution_plan_not_ok")
        blockers.extend(plan.blockers)
    order_rows: list[dict[str, Any]] = []
    fill_rows: list[dict[str, Any]] = []
    start_positions = {str(symbol): float(amount) for symbol, amount in dict(current_positions or {}).items()}
    end_positions = dict(start_positions)
    total_fee = 0.0
    total_notional = 0.0
    if not blockers:
        for seq, intent in enumerate(plan.intents, start=1):
            price = float(mark_prices.get(intent.symbol, 0.0) or 0.0)
            if price <= 0.0:
                blockers.append(f"missing_mark_price:{intent.symbol}")
                continue
            signed_qty = float(intent.quantity) if intent.side == "BUY" else -float(intent.quantity)
            notional = abs(float(intent.quantity) * price)
            fee = notional * float(fee_rate)
            total_fee += fee
            total_notional += notional
            end_positions[intent.symbol] = float(end_positions.get(intent.symbol, 0.0) or 0.0) + signed_qty
            paper_order_id = f"paper-{run_id}-{seq}"
            order_rows.append(
                {
                    "paper_order_id": paper_order_id,
                    "client_order_id": intent.client_order_id,
                    "intent_id": intent.intent_id,
                    "plan_id": plan.plan_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "position_side": intent.position_side,
                    "order_type": intent.order_type,
                    "quantity": float(intent.quantity),
                    "reduce_only": bool(intent.reduce_only),
                    "paper_status": "FILLED",
                    "created_at_utc": created_at_utc,
                }
            )
            fill_rows.append(
                {
                    "paper_fill_id": f"{paper_order_id}-fill",
                    "paper_order_id": paper_order_id,
                    "client_order_id": intent.client_order_id,
                    "intent_id": intent.intent_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "price": price,
                    "quantity": float(intent.quantity),
                    "signed_quantity": signed_qty,
                    "notional_usdt": notional,
                    "fee_usdt": fee,
                    "target_position_amt": float(intent.target_position_amt),
                    "filled_at_utc": created_at_utc,
                    "liquidity": "TAKER_SIM",
                }
            )
    submitted_orders = pd.DataFrame(order_rows)
    fills = pd.DataFrame(fill_rows)
    status = "filled" if not blockers else "blocked"
    account_before = {
        "mode": "paper",
        "source": "local_state_store",
        "positions": {symbol: amount for symbol, amount in sorted(start_positions.items()) if abs(amount) > 1e-12},
        "gross_notional_usdt": _gross_notional(start_positions, mark_prices=mark_prices),
    }
    account_after = {
        "mode": "paper",
        "positions": {symbol: amount for symbol, amount in sorted(end_positions.items()) if abs(amount) > 1e-12},
        "gross_notional_usdt": _gross_notional(end_positions, mark_prices=mark_prices),
        "simulated_gross_notional_usdt": total_notional,
        "simulated_fee_usdt": total_fee,
        "simulated_fill_count": int(len(fills)),
    }
    reconciliation = {
        "status": "paper_simulated" if status == "filled" else "paper_blocked",
        "submitted_order_count": int(len(submitted_orders)),
        "fill_count": int(len(fills)),
        "blockers": sorted(set(blockers)),
    }
    return PaperExecutionResult(
        run_id=run_id,
        plan_id=plan.plan_id,
        status=status,
        blockers=sorted(set(blockers)),
        fee_rate=float(fee_rate),
        submitted_orders=submitted_orders,
        fills=fills,
        account_before=account_before,
        account_after=account_after,
        reconciliation=reconciliation,
    )


def _gross_notional(positions: dict[str, float], *, mark_prices: dict[str, float]) -> float:
    total = 0.0
    for symbol, amount in positions.items():
        price = float(mark_prices.get(symbol, 0.0) or 0.0)
        if price > 0.0:
            total += abs(float(amount) * price)
    return float(total)
