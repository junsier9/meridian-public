from __future__ import annotations

from typing import Any

from enhengclaw.live_trading.config import LIVE_MODES
from enhengclaw.live_trading.models import RiskGateResult, TargetPortfolio


def evaluate_risk_gate(
    portfolio: TargetPortfolio,
    *,
    mode: str,
    config: dict[str, Any],
    live_confirmed: bool = False,
    local_state_health: dict[str, Any] | None = None,
) -> RiskGateResult:
    normalized_mode = str(mode or "plan_only").strip().lower() or "plan_only"
    blockers: list[str] = []
    warnings: list[str] = []
    if normalized_mode not in LIVE_MODES:
        blockers.append(f"unsupported_mode:{normalized_mode}")
    risk = dict(config.get("risk") or {})
    capital = dict(config.get("capital") or {})
    if portfolio.status != "ok":
        blockers.append("target_portfolio_not_ok")
        blockers.extend(portfolio.blockers)
    health = dict(local_state_health or {})
    if health and str(health.get("status") or "ok") != "ok":
        blockers.append("local_state_health_not_ok")
        blockers.extend(str(item) for item in list(health.get("blockers") or []))
    max_allocated = float(risk.get("max_allocated_capital_usdt", capital.get("allocated_capital_usdt", 0.0)) or 0.0)
    if max_allocated > 0 and portfolio.allocated_capital_usdt > max_allocated:
        blockers.append("allocated_capital_exceeds_risk_cap")
    max_gross_notional = float(risk.get("max_gross_notional_usdt", capital.get("allocated_capital_usdt", 0.0)) or 0.0)
    gross_notional = portfolio.allocated_capital_usdt * portfolio.target_gross_weight
    if max_gross_notional > 0 and gross_notional > max_gross_notional:
        blockers.append("gross_notional_exceeds_risk_cap")
    max_symbol = float(risk.get("max_symbol_notional_usdt", capital.get("max_symbol_notional_usdt", 0.0)) or 0.0)
    if max_symbol > 0:
        for position in portfolio.positions:
            if position.target_notional_usdt > max_symbol:
                blockers.append(f"symbol_notional_exceeds_cap:{position.usdm_symbol}")
    # Absolute hard ceilings (equity-compounding v2): TRUE fail-closed, NEVER auto-lifted.
    # Independent of the equity-tracking caps above so a mis-derived plan-stage cap cannot
    # leak through. Absent keys (== 0.0) leave legacy behaviour unchanged.
    abs_allocated = float(risk.get("abs_max_allocated_capital_usdt", 0.0) or 0.0)
    if abs_allocated > 0 and portfolio.allocated_capital_usdt > abs_allocated:
        blockers.append("allocated_capital_exceeds_absolute_ceiling")
    abs_gross = float(risk.get("abs_max_gross_notional_usdt", 0.0) or 0.0)
    if abs_gross > 0 and gross_notional > abs_gross:
        blockers.append("gross_notional_exceeds_absolute_ceiling")
    abs_symbol = float(risk.get("abs_max_symbol_notional_usdt", 0.0) or 0.0)
    if abs_symbol > 0:
        for position in portfolio.positions:
            if position.target_notional_usdt > abs_symbol:
                blockers.append(f"symbol_notional_exceeds_absolute_ceiling:{position.usdm_symbol}")
    # Fail-closed channel for the v2 resolver (e.g. unresolved absolute ceiling): a zero
    # cap must never read as "no cap", so the resolver surfaces explicit blockers here.
    for item in list(risk.get("_wallet_v2_blockers") or []):
        blockers.append(f"wallet_v2:{item}")
    if normalized_mode == "live":
        if not live_confirmed:
            blockers.append("missing_live_confirmation_flag")
        if not bool(risk.get("trading_enabled", False)):
            blockers.append("live_trading_disabled_in_config")
    if normalized_mode == "testnet":
        warnings.append("testnet_order_router_requires_explicit_runner_confirmation")
    decision = "allow_plan" if not blockers and normalized_mode in {"plan_only", "paper"} else ("allow" if not blockers else "block")
    return RiskGateResult(
        risk_gate_id=f"{portfolio.portfolio_id}:risk:{normalized_mode}",
        portfolio_id=portfolio.portfolio_id,
        mode=normalized_mode,
        passed=not blockers,
        decision=decision,
        blockers=sorted(set(blockers)),
        warnings=warnings,
    )
