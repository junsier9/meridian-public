from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class LiveDecisionSnapshot:
    decision_id: str
    strategy_label: str
    config_sha256: str
    decision_time_ms: int
    decision_date_utc: str
    rebalance_slot: bool
    input_bar_end_ms: int
    status: str
    blockers: list[str] = field(default_factory=list)
    scores: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)

    def metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("scores", None)
        return payload


@dataclass(frozen=True, slots=True)
class TargetPosition:
    subject: str
    usdm_symbol: str
    side: str
    score: float
    target_weight: float
    target_notional_usdt: float
    previous_target_weight: float
    delta_target_weight: float
    raw_short_multiplier: float
    portfolio_drawdown_multiplier: float
    selection_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TargetPortfolio:
    portfolio_id: str
    decision_id: str
    strategy_label: str
    allocated_capital_usdt: float
    portfolio_drawdown: float
    portfolio_drawdown_multiplier: float
    target_gross_weight: float
    target_net_weight: float
    status: str
    blockers: list[str] = field(default_factory=list)
    positions: list[TargetPosition] = field(default_factory=list)

    def metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("positions", None)
        return payload

    def positions_frame(self) -> pd.DataFrame:
        return pd.DataFrame([position.to_dict() for position in self.positions])


@dataclass(frozen=True, slots=True)
class RiskGateResult:
    risk_gate_id: str
    portfolio_id: str
    mode: str
    passed: bool
    decision: str
    blockers: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    portfolio_id: str
    symbol: str
    side: str
    position_side: str
    order_type: str
    quantity: float
    reduce_only: bool
    target_position_amt: float
    current_position_amt: float
    delta_position_amt: float
    max_slippage_bps: float
    client_order_id: str
    execution_phase: str = ""
    delta_classification: str = ""
    final_target_position_amt: float = 0.0
    second_phase_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionPlan:
    plan_id: str
    portfolio_id: str
    mode: str
    status: str
    blockers: list[str] = field(default_factory=list)
    intents: list[OrderIntent] = field(default_factory=list)
    active_execution_phase: str = ""
    phase_counts: dict[str, int] = field(default_factory=dict)
    deferred_phase_counts: dict[str, int] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("intents", None)
        return payload

    def intents_frame(self) -> pd.DataFrame:
        return pd.DataFrame([intent.to_dict() for intent in self.intents])
