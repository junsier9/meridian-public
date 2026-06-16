from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
)
from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.daily_rebalance_slot_gate import (
    FROZEN_TARGET_SNAPSHOT_ARTIFACT,
    REBALANCE_SLOT_POST_FILL_CLEANUP_ACTION,
    REBALANCE_SLOT_REEXECUTION_ACTION,
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
    apply_frozen_snapshot_to_portfolio,
    build_frozen_target_snapshot,
    completed_slot_execution_gate,
    hold_execution_plan,
    target_position_overrides,
    target_reference_prices,
)
from enhengclaw.live_trading.execution_planner import (
    build_execution_plan,
    build_order_sizing_report,
    summarize_dust_residual_order_sizing,
    summarize_order_sizing_report,
)
from enhengclaw.live_trading.frozen_frontier_live import (
    FRONTIER_PLAN_ARTIFACT,
    FrontierResolution,
    resolve_live_frontier,
)
from enhengclaw.live_trading.hv_balanced_live_signal import (
    build_live_hv_balanced_snapshot,
    file_sha256,
    is_rebalance_slot,
    load_frozen_config,
)
from enhengclaw.live_trading.live_pit_universe import (
    LIVE_UNIVERSE_ARTIFACT,
    write_universe_change_log,
)
from enhengclaw.live_trading.live_risk_controls import evaluate_margin_cushion_gate
from enhengclaw.live_trading.mainnet_rebalance_plan_runner import (
    _account_snapshot,
    _as_bool,
    _apply_live_universe_churn_gate,
    _build_mainnet_client,
    _build_permission_client,
    _capital_topup_plan_gate,
    _capital_topup_gate_requested,
    _config_blockers,
    _credential_context,
    _current_unattended_budget_epoch_id,
    _float,
    _load_panel,
    _mark_prices,
    _optional_float,
    _parse_as_of_ms,
    _resolve_capital_allocation_context,
    _resolve_decision_time_context,
    _risk_payload_plan_only,
    _safe_exchange_filters,
)
from enhengclaw.live_trading.models import ExecutionPlan, LiveDecisionSnapshot, TargetPortfolio, TargetPosition
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json as _base_write_json


DAY_MS = 86_400_000
PHASES = tuple(range(10))
MULTIPHASE_TARGET_ENGINE = "multiphase_equal_sleeve"


def write_json(path: Path, payload: Any) -> None:
    _base_write_json(path, _json_safe(payload))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, Path):
        return str(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "No-order mainnet shadow comparison for current single-phase hv_balanced target versus "
            "a live-compatible 10-phase aggregate target. It reads account/public data and never submits orders."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_core_loop.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--api-secret-env", default="")
    parser.add_argument(
        "--target-plan",
        action="store_true",
        help="Write the multiphase aggregate as a reusable no-order current-position-aware plan artifact.",
    )
    parser.add_argument(
        "--capital-topup",
        action="store_true",
        help="Resolve allocated capital dynamically from the signed account wallet balance and run the top-up gate.",
    )
    args = parser.parse_args(argv)
    if bool(getattr(args, "target_plan", False)):
        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(args)
    else:
        summary, exit_code = run_mainnet_multiphase_target_shadow(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_multiphase_target_shadow(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    market_client_factory: Callable[..., Any] = BinanceUsdmClient,
    account_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(str(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_core_loop.yaml")))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-multiphase-target-shadow"
    run_root = live_config.artifact_root.parent / "mainnet_multiphase_target_shadow" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    blockers = _config_blockers(payload)
    credentials = _credential_context(payload=payload, args=args, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    account_snapshot: dict[str, Any] = {"status": "not_run", "blockers": list(blockers)}
    current_positions: dict[str, float] = {}
    current_mark_prices: dict[str, float] = {}
    current_symbol_filters: dict[str, dict[str, Any]] = {}
    if not blockers:
        try:
            account_client = _build_mainnet_client(credentials, account_client_factory)
            permission_client = _build_permission_client(credentials, permission_client_factory)
            account_snapshot = _account_snapshot(
                account_client,
                permission_client=permission_client,
                expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
                expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
                max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            )
        except Exception as exc:  # pragma: no cover - exercised by live API/IP failures.
            blocker = f"account_snapshot_failed:{type(exc).__name__}:{_safe_error_message(exc)}"
            account_snapshot = {"status": "blocked", "blockers": [blocker]}
            blockers.append(blocker)
        else:
            blockers.extend(account_snapshot["blockers"])
            current_positions = {
                str(row["symbol"]): float(row["positionAmt"])
                for row in list(account_snapshot.get("open_positions_redacted") or [])
            }
            current_mark_prices = {
                str(row["symbol"]): float(row.get("markPrice") or 0.0)
                for row in list(account_snapshot.get("open_positions_redacted") or [])
                if float(row.get("markPrice") or 0.0) > 0.0
            }
            try:
                current_symbol_filters = _safe_exchange_filters(account_client, symbols=sorted(current_positions))
            except Exception as exc:  # pragma: no cover - live exchange-info safety net.
                blocker = f"current_position_exchange_filters_failed:{type(exc).__name__}:{_safe_error_message(exc)}"
                blockers.append(blocker)
    write_json(run_root / "account_snapshot.json", account_snapshot)
    pd.DataFrame(list(account_snapshot.get("open_positions_redacted") or [])).to_csv(run_root / "current_positions.csv", index=False)
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
        )
        _write_empty_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    frozen_path = live_config.strategy_config_path
    frozen_config = load_frozen_config(frozen_path)
    config_sha = file_sha256(frozen_path)
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")

    # Frozen 12-factor frontier resolution (default-off), shared chokepoint with both plan
    # runners so the shadow comparator never split-brains against the executed plan.
    frontier = resolve_live_frontier(live_config, payload)
    write_json(run_root / FRONTIER_PLAN_ARTIFACT, frontier.to_artifact())
    if frontier.is_blocked:
        blockers.extend(f"frontier:{item}" for item in (frontier.blockers or ["unspecified"]))
    portfolio_config = (
        frontier.effective_config
        if (frontier.is_armed_ready and frontier.effective_config)
        else frozen_config
    )

    panel, market_data_audit, symbol_filters = _load_panel(
        args=args,
        payload=payload,
        frozen_config=frozen_config,
        market_client_factory=market_client_factory,
        frontier=frontier,
    )
    symbol_filters = {**current_symbol_filters, **symbol_filters}
    market_data_audit = _apply_live_universe_churn_gate(
        run_root=run_root,
        run_id=run_id,
        market_data_audit=market_data_audit,
    )
    write_json(run_root / "market_data_audit.json", market_data_audit)
    write_json(run_root / "symbol_exchange_filters.json", symbol_filters)
    # Fail closed on any armed-frontier feature-assembly failure (sidecar/spot). Empty for default-off.
    blockers.extend(f"frontier_feature:{item}" for item in (market_data_audit.get("frontier_feature_blockers") or []))
    # Fail closed on any PIT rolling universe gate. Empty for default-off => baseline flow unchanged.
    blockers.extend(f"universe:{item}" for item in (market_data_audit.get("universe_blockers") or []))
    if market_data_audit.get("live_universe"):
        write_json(run_root / LIVE_UNIVERSE_ARTIFACT, market_data_audit["live_universe"])
        # Read-only day-over-day universe churn trail (traceability only; best-effort, never fed
        # back into selection and never able to crash/block the run). Drift prevention is the
        # live_universe.json copy bound into plan_hash.
        write_universe_change_log(
            run_root=run_root, run_id=run_id, live_universe=market_data_audit["live_universe"]
        )
    if panel.empty:
        blockers.append("empty_market_data_panel")
    if "timestamp_ms" not in panel.columns:
        blockers.append("market_data_panel_missing_timestamp_ms")
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
        )
        _write_empty_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    strategy_cfg = dict(payload.get("strategy") or {})
    rebalance_interval_days = int(strategy_cfg.get("rebalance_interval_days", 10) or 10)
    rebalance_epoch_ms = int(strategy_cfg.get("rebalance_epoch_ms", 0) or 0)
    single_context = _resolve_decision_time_context(
        panel,
        _single_phase_as_of(getattr(args, "as_of", "now")),
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
    )
    upper_ms = _resolve_as_of_upper_ms(panel, str(getattr(args, "as_of", "now") or "now"))
    phase_contexts = [
        _resolve_phase_decision_time_context(
            panel,
            phase_offset_days=phase,
            upper_timestamp_ms=upper_ms,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
        )
        for phase in PHASES
    ]
    write_json(run_root / "single_phase_decision_time_context.json", single_context)
    write_json(run_root / "multiphase_decision_time_context.json", {"upper_timestamp_ms": upper_ms, "phases": phase_contexts})

    capital_context = _resolve_capital_allocation_context(
        payload=payload,
        account_snapshot=account_snapshot,
        capital_topup_requested=False,
    )
    write_json(run_root / "capital_allocation_context.json", capital_context)
    blockers.extend(str(item) for item in list(capital_context.get("blockers") or []))
    single_decision_ms = single_context.get("decision_time_ms")
    if single_decision_ms is None:
        blockers.extend(str(item) for item in list(single_context.get("blockers") or []))
    if any(context.get("decision_time_ms") is None for context in phase_contexts):
        missing = [str(context.get("phase_offset_days")) for context in phase_contexts if context.get("decision_time_ms") is None]
        blockers.append(f"multiphase_missing_phase_decision_slots:{','.join(missing)}")
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
        )
        _write_empty_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    allocated = float(capital_context.get("resolved_allocated_capital_usdt") or 0.0)
    panel = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").le(int(upper_ms))].copy()
    single_snapshot = build_live_hv_balanced_snapshot(
        panel,
        config=frozen_config,
        config_sha256=config_sha,
        decision_time_ms=int(single_decision_ms),
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
        frontier=frontier,
    )
    single_portfolio = build_target_portfolio(single_snapshot, config=portfolio_config, allocated_capital_usdt=allocated)
    multiphase_portfolio, multiphase_context = build_multiphase_aggregate_target_portfolio(
        panel,
        config=frozen_config,
        config_sha256=config_sha,
        allocated_capital_usdt=allocated,
        phase_contexts=phase_contexts,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
        frontier=frontier,
    )
    write_json(run_root / "multiphase_target_context.json", multiphase_context)

    mark_prices = {**current_mark_prices, **_mark_prices(single_snapshot.scores), **_scores_mark_prices(multiphase_context)}
    risk_payload = _risk_payload_plan_only(payload, capital_allocation_context=capital_context)
    single_bundle = _build_shadow_bundle(
        label="single_phase",
        portfolio=single_portfolio,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        payload=payload,
        risk_payload=risk_payload,
        account_snapshot=account_snapshot,
    )
    multi_bundle = _build_shadow_bundle(
        label="multiphase_aggregate",
        portfolio=multiphase_portfolio,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        payload=payload,
        risk_payload=risk_payload,
        account_snapshot=account_snapshot,
    )
    comparison = build_target_shadow_comparison(
        single_positions=single_portfolio.positions_frame(),
        multiphase_positions=multiphase_portfolio.positions_frame(),
        single_sizing=single_bundle["order_sizing_report"],
        multiphase_sizing=multi_bundle["order_sizing_report"],
        allocated_capital_usdt=allocated,
    )
    _write_bundle(run_root / "single_phase", single_snapshot, single_portfolio, single_bundle)
    _write_bundle(run_root / "multiphase_aggregate", None, multiphase_portfolio, multi_bundle)
    comparison["by_symbol"].to_csv(run_root / "target_shadow_comparison_by_symbol.csv", index=False)
    write_json(run_root / "target_shadow_comparison.json", comparison["summary"])

    run_blockers = [
        *single_snapshot.blockers,
        *single_portfolio.blockers,
        *multiphase_portfolio.blockers,
        *single_bundle["risk_gate"].blockers,
        *multi_bundle["risk_gate"].blockers,
        *list(single_bundle["margin_cushion_gate"].get("blockers") or []),
        *list(multi_bundle["margin_cushion_gate"].get("blockers") or []),
    ]
    status = "passed" if not run_blockers else "passed_with_shadow_blockers"
    summary = _summary(
        run_id=run_id,
        status=status,
        blockers=[],
        shadow_blockers=sorted(set(str(item) for item in run_blockers)),
        started_at=started,
        artifact_root=run_root,
        account_snapshot=account_snapshot,
        single_phase=single_bundle["summary"],
        multiphase_aggregate=multi_bundle["summary"],
        comparison=comparison["summary"],
        single_decision_date_utc=single_context.get("decision_date_utc"),
        multiphase_latest_decision_dates=[
            str(context.get("decision_date_utc") or "") for context in phase_contexts
        ],
    )
    write_json(run_root / "run_summary.json", summary)
    return summary, 0


def run_mainnet_multiphase_current_position_rebalance_plan(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    market_client_factory: Callable[..., Any] = BinanceUsdmClient,
    account_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    """Build a reusable no-order current-position-aware plan from 10 equal sleeves.

    This runner intentionally mirrors the single-phase rebalance plan artifact contract
    so the supervisor/core loop can observe a multiphase target without opening the
    live-order path.
    """

    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(str(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_core_loop.yaml")))
    payload = live_config.payload
    capital_topup_requested = bool(getattr(args, "capital_topup", False))
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-multiphase-target-plan"
    run_root = live_config.artifact_root.parent / "mainnet_multiphase_target_plan" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    blockers = _config_blockers(payload)
    if bool(getattr(args, "execute_live_delta", False)):
        blockers.append("multiphase_target_plan_is_no_order_only")
    credentials = _credential_context(payload=payload, args=args, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    account_snapshot: dict[str, Any] = {"status": "not_run", "blockers": list(blockers)}
    current_positions: dict[str, float] = {}
    current_mark_prices: dict[str, float] = {}
    current_symbol_filters: dict[str, dict[str, Any]] = {}
    if not blockers:
        try:
            account_client = _build_mainnet_client(credentials, account_client_factory)
            permission_client = _build_permission_client(credentials, permission_client_factory)
            account_snapshot = _account_snapshot(
                account_client,
                permission_client=permission_client,
                expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
                expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
                max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            )
        except Exception as exc:  # pragma: no cover - live API/IP safety net.
            blocker = f"account_snapshot_failed:{type(exc).__name__}:{_safe_error_message(exc)}"
            account_snapshot = {"status": "blocked", "blockers": [blocker]}
            blockers.append(blocker)
        else:
            blockers.extend(account_snapshot["blockers"])
            current_positions = {
                str(row["symbol"]): float(row["positionAmt"])
                for row in list(account_snapshot.get("open_positions_redacted") or [])
            }
            current_mark_prices = {
                str(row["symbol"]): float(row.get("markPrice") or 0.0)
                for row in list(account_snapshot.get("open_positions_redacted") or [])
                if float(row.get("markPrice") or 0.0) > 0.0
            }
            try:
                current_symbol_filters = _safe_exchange_filters(account_client, symbols=sorted(current_positions))
            except Exception as exc:  # pragma: no cover - live exchange-info safety net.
                blockers.append(f"current_position_exchange_filters_failed:{type(exc).__name__}:{_safe_error_message(exc)}")
    write_json(run_root / "account_snapshot.json", account_snapshot)
    pd.DataFrame(list(account_snapshot.get("open_positions_redacted") or [])).to_csv(run_root / "current_positions.csv", index=False)
    if blockers:
        summary = _target_plan_summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
            current_positions=current_positions,
            planned_order_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
        )
        _write_empty_target_plan_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    frozen_path = live_config.strategy_config_path
    frozen_config = load_frozen_config(frozen_path)
    config_sha = file_sha256(frozen_path)
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")

    # Frozen 12-factor frontier resolution (default-off). Same chokepoint as the single-phase
    # runner — both consume the one shared scorer, so there is no split-brain to keep in sync.
    frontier = resolve_live_frontier(live_config, payload)
    write_json(run_root / FRONTIER_PLAN_ARTIFACT, frontier.to_artifact())
    if frontier.is_blocked:
        blockers.extend(f"frontier:{item}" for item in (frontier.blockers or ["unspecified"]))

    panel, market_data_audit, symbol_filters = _load_panel(
        args=args,
        payload=payload,
        frozen_config=frozen_config,
        market_client_factory=market_client_factory,
        frontier=frontier,
    )
    symbol_filters = {**current_symbol_filters, **symbol_filters}
    market_data_audit = _apply_live_universe_churn_gate(
        run_root=run_root,
        run_id=run_id,
        market_data_audit=market_data_audit,
    )
    write_json(run_root / "market_data_audit.json", market_data_audit)
    write_json(run_root / "symbol_exchange_filters.json", symbol_filters)
    # Fail closed on any armed-frontier feature-assembly failure (sidecar/spot). Empty for default-off.
    blockers.extend(f"frontier_feature:{item}" for item in (market_data_audit.get("frontier_feature_blockers") or []))
    # Fail closed on any PIT rolling universe gate. Empty for default-off => baseline flow unchanged.
    blockers.extend(f"universe:{item}" for item in (market_data_audit.get("universe_blockers") or []))
    if market_data_audit.get("live_universe"):
        write_json(run_root / LIVE_UNIVERSE_ARTIFACT, market_data_audit["live_universe"])
        # Read-only day-over-day universe churn trail (traceability only; best-effort, never fed
        # back into selection and never able to crash/block the run). Drift prevention is the
        # live_universe.json copy bound into plan_hash.
        write_universe_change_log(
            run_root=run_root, run_id=run_id, live_universe=market_data_audit["live_universe"]
        )
    if panel.empty:
        blockers.append("empty_market_data_panel")
    if "timestamp_ms" not in panel.columns:
        blockers.append("market_data_panel_missing_timestamp_ms")
    if blockers:
        summary = _target_plan_summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
            current_positions=current_positions,
            planned_order_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
        )
        _write_empty_target_plan_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    strategy_cfg = dict(payload.get("strategy") or {})
    rebalance_interval_days = int(strategy_cfg.get("rebalance_interval_days", 10) or 10)
    rebalance_epoch_ms = int(strategy_cfg.get("rebalance_epoch_ms", 0) or 0)
    upper_ms = _resolve_as_of_upper_ms(panel, str(getattr(args, "as_of", "now") or "now"))
    phase_contexts = [
        _resolve_phase_decision_time_context(
            panel,
            phase_offset_days=phase,
            upper_timestamp_ms=upper_ms,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
        )
        for phase in PHASES
    ]
    decision_time_context = {
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "requested_as_of": str(getattr(args, "as_of", "now") or "now"),
        "upper_timestamp_ms": int(upper_ms),
        "phase_count": int(len(phase_contexts)),
        "phases": phase_contexts,
    }
    write_json(run_root / "decision_time_context.json", decision_time_context)
    write_json(run_root / "multiphase_decision_time_context.json", decision_time_context)
    if any(context.get("decision_time_ms") is None for context in phase_contexts):
        missing = [str(context.get("phase_offset_days")) for context in phase_contexts if context.get("decision_time_ms") is None]
        blockers.append(f"multiphase_missing_phase_decision_slots:{','.join(missing)}")

    capital_allocation_context = _resolve_capital_allocation_context(
        payload=payload,
        account_snapshot=account_snapshot,
        capital_topup_requested=capital_topup_requested,
    )
    capital_topup_gate = {
        "status": "pending_plan" if capital_topup_requested else "not_requested",
        "blockers": [],
        "warnings": list(capital_allocation_context.get("warnings") or []),
        "target_engine": MULTIPHASE_TARGET_ENGINE,
    }
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
    blockers.extend(str(item) for item in list(capital_allocation_context.get("blockers") or []))
    if blockers:
        if capital_topup_requested and list(capital_allocation_context.get("blockers") or []):
            capital_topup_gate = {
                "status": "blocked",
                "blockers": list(capital_allocation_context.get("blockers") or []),
                "warnings": list(capital_allocation_context.get("warnings") or []),
                "target_engine": MULTIPHASE_TARGET_ENGINE,
            }
            write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
        summary = _target_plan_summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            account_snapshot=account_snapshot,
            current_positions=current_positions,
            planned_order_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
            capital_allocation_context=capital_allocation_context,
            capital_topup_gate=capital_topup_gate,
        )
        _write_empty_target_plan_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    allocated = float(capital_allocation_context.get("resolved_allocated_capital_usdt") or 0.0)
    panel = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").le(int(upper_ms))].copy()
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    mark_prices = {**_latest_mark_prices_from_panel(panel, upper_timestamp_ms=upper_ms), **current_mark_prices}
    strategy_label = str(
        dict(payload.get("strategy") or {}).get("label")
        or frozen_config.get("strategy_label")
        or "hv_balanced"
    )

    def build_candidate(
        candidate_allocated: float,
    ) -> tuple[TargetPortfolio, dict[str, Any], dict[str, Any], dict[str, Any]]:
        candidate_capital_context = _capital_context_with_resolved_allocated_capital(
            capital_allocation_context,
            resolved_allocated_capital_usdt=float(candidate_allocated),
        )
        candidate_portfolio, candidate_multiphase_context = build_multiphase_target_portfolio(
            panel,
            config=frozen_config,
            config_sha256=config_sha,
            allocated_capital_usdt=float(candidate_allocated),
            phase_contexts=phase_contexts,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
            state_store=None,
            persist_sleeve_state=False,
            strategy_label=strategy_label,
            frontier=frontier,
        )
        candidate_risk_payload = _risk_payload_plan_only(
            payload,
            capital_allocation_context=candidate_capital_context,
        )
        candidate_bundle = _build_shadow_bundle(
            label="multiphase_target_plan",
            portfolio=candidate_portfolio,
            current_positions=current_positions,
            mark_prices=mark_prices,
            symbol_filters=symbol_filters,
            payload=payload,
            risk_payload=candidate_risk_payload,
            account_snapshot=account_snapshot,
        )
        return candidate_portfolio, candidate_multiphase_context, candidate_bundle, candidate_capital_context

    portfolio, multiphase_context, bundle, capital_allocation_context = build_candidate(allocated)
    truncation = _select_margin_safe_allocated_capital(
        payload=payload,
        initial_allocated_capital_usdt=allocated,
        initial_portfolio=portfolio,
        initial_multiphase_context=multiphase_context,
        initial_bundle=bundle,
        initial_capital_context=capital_allocation_context,
        build_candidate=build_candidate,
    )
    portfolio = truncation["portfolio"]
    multiphase_context = truncation["multiphase_context"]
    bundle = truncation["bundle"]
    capital_allocation_context = dict(truncation["capital_context"])
    capital_allocation_context["margin_safe_truncation"] = dict(truncation["context"])
    bundle["summary"]["margin_safe_truncation"] = dict(truncation["context"])
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    write_json(run_root / "margin_safe_truncation.json", truncation["context"])
    _persist_multiphase_sleeve_state(state_store, multiphase_context)
    write_json(run_root / "multiphase_target_context.json", multiphase_context)
    write_json(run_root / "multiphase_sleeve_targets.json", {"sleeves": list(multiphase_context.get("sleeve_state_records") or [])})
    decision_metadata = _multiphase_decision_metadata(portfolio=portfolio, context=multiphase_context, upper_ms=upper_ms)
    candidate_frozen_snapshot = build_frozen_target_snapshot(
        target_engine=MULTIPHASE_TARGET_ENGINE,
        portfolio=portfolio,
        order_sizing_report=bundle["order_sizing_report"],
        capital_allocation_context=capital_allocation_context,
        decision_metadata=decision_metadata,
        created_at=started,
    )
    stored_frozen_snapshot = state_store.read_rebalance_slot_target(str(candidate_frozen_snapshot["slot_id"]))
    frozen_slot_gate = {
        "status": "freeze_new_slot_target",
        "slot_id": str(candidate_frozen_snapshot["slot_id"]),
        "candidate_target_hash": str(candidate_frozen_snapshot["target_hash"]),
        "active_target_hash": str(candidate_frozen_snapshot["target_hash"]),
        "blockers": [],
        "warnings": [],
    }
    if stored_frozen_snapshot is None:
        frozen_target_snapshot = state_store.write_rebalance_slot_target(candidate_frozen_snapshot)
    else:
        frozen_target_snapshot = dict(stored_frozen_snapshot)
        frozen_slot_gate.update(
            {
                "status": "reuse_frozen_slot_target",
                "active_target_hash": str(frozen_target_snapshot.get("target_hash") or ""),
                "stored_status": str(frozen_target_snapshot.get("status") or ""),
            }
        )
        if str(frozen_target_snapshot.get("target_hash") or "") != str(candidate_frozen_snapshot.get("target_hash") or ""):
            frozen_slot_gate["warnings"] = [
                "same_slot_candidate_target_drift_ignored_in_favor_of_frozen_snapshot"
            ]
    portfolio = apply_frozen_snapshot_to_portfolio(portfolio, frozen_target_snapshot)
    capital_allocation_context = _capital_context_with_resolved_allocated_capital(
        capital_allocation_context,
        resolved_allocated_capital_usdt=float(frozen_target_snapshot.get("resolved_capital_usdt") or 0.0),
    )
    capital_allocation_context["frozen_rebalance_slot_target"] = {
        "slot_id": str(frozen_target_snapshot.get("slot_id") or ""),
        "target_hash": str(frozen_target_snapshot.get("target_hash") or ""),
        "status": str(frozen_target_snapshot.get("status") or ""),
    }
    risk_payload = _risk_payload_plan_only(
        payload,
        capital_allocation_context=capital_allocation_context,
    )
    bundle = _build_shadow_bundle(
        label="multiphase_target_plan",
        portfolio=portfolio,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        payload=payload,
        risk_payload=risk_payload,
        account_snapshot=account_snapshot,
        frozen_target_snapshot=frozen_target_snapshot,
    )
    if dict(frozen_target_snapshot).get("completed_at_utc"):
        frozen_slot_gate["completed_at_utc"] = frozen_target_snapshot.get("completed_at_utc")
    slot_id = str(frozen_target_snapshot.get("slot_id") or "")
    target_hash = str(frozen_target_snapshot.get("target_hash") or "")
    completed_gate = completed_slot_execution_gate(
        slot_record=frozen_target_snapshot,
        plan=bundle["execution_plan"],
        reexecution_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_REEXECUTION_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        post_fill_cleanup_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_POST_FILL_CLEANUP_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        risk_only_reduce_cleanup_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        risk_only_reduce_cleanup_consumed=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        current_budget_epoch_id=_current_unattended_budget_epoch_id(payload),
    )
    frozen_slot_gate["completed_slot_execution_gate"] = completed_gate
    if bool(completed_gate.get("hold_until_next_rebalance_slot")):
        bundle["execution_plan"] = hold_execution_plan(bundle["execution_plan"])
        _refresh_bundle_plan_summary(bundle)
        frozen_slot_gate["status"] = "hold_until_next_rebalance_slot"
    write_json(run_root / FROZEN_TARGET_SNAPSHOT_ARTIFACT, frozen_target_snapshot)
    write_json(run_root / "frozen_slot_gate.json", frozen_slot_gate)
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    plan = bundle["execution_plan"]
    capital_topup_gate_requested = _capital_topup_gate_requested(
        payload=payload,
        explicit_requested=capital_topup_requested,
        capital_allocation_context=capital_allocation_context,
        plan=plan,
    )
    capital_topup_gate = _capital_topup_plan_gate(
        payload=payload,
        requested=capital_topup_gate_requested,
        capital_allocation_context=capital_allocation_context,
        order_sizing_report=bundle["order_sizing_report"],
        plan=plan,
    )
    capital_topup_gate["target_engine"] = MULTIPHASE_TARGET_ENGINE
    write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
    dust_delta_summary = bundle["dust_delta_summary"]
    capital_deployment_deferred = str(capital_topup_gate.get("status") or "") == "deferred"
    if capital_deployment_deferred:
        deferred_if_executed_margin_gate = bundle["margin_cushion_gate"]
        current_margin_gate = evaluate_margin_cushion_gate(
            {
                "available_balance_usdt": account_snapshot.get("available_balance_usdt"),
                "total_wallet_balance_usdt": account_snapshot.get("total_wallet_balance_usdt"),
            },
            config=payload,
            planned_additional_initial_margin_usdt=0.0,
            require_configured=True,
        )
        bundle["deferred_if_executed_margin_cushion_gate"] = deferred_if_executed_margin_gate
        bundle["margin_cushion_gate"] = current_margin_gate
        bundle["summary"]["margin_cushion_gate"] = current_margin_gate
        bundle["summary"]["deferred_if_executed_margin_cushion_gate"] = deferred_if_executed_margin_gate
    plan_hard_blockers = list(plan.blockers)
    dust_delta_only = (
        bool(dust_delta_summary.get("is_dust_residual_only"))
        and not plan.intents
        and (not plan.blockers or sorted(set(plan.blockers)) == sorted(set(dust_delta_summary.get("dust_blockers") or [])))
    )
    if dust_delta_only:
        plan.status = "dust_noop"
        plan.blockers = list(dust_delta_summary.get("dust_blockers") or [])
        plan_hard_blockers = []
    normalized_dust = dict(dust_delta_summary)
    if not dust_delta_only:
        normalized_dust["is_dust_residual_only"] = False

    blockers.extend([*portfolio.blockers, *bundle["risk_gate"].blockers, *plan_hard_blockers])
    blockers.extend(str(item) for item in list(capital_topup_gate.get("blockers") or []))
    blockers.extend(str(item) for item in list(bundle["margin_cushion_gate"].get("blockers") or []))
    warnings = list(bundle["risk_gate"].warnings)
    warnings.extend(str(item) for item in list(capital_topup_gate.get("warnings") or []))
    if dust_delta_only:
        warnings.append("dust_delta_noop:all_delta_orders_below_min_order_constraints")
    warnings.extend(str(item) for item in list(frozen_slot_gate.get("warnings") or []))

    runtime_gate_context = {
        "mode": "mainnet_multiphase_current_position_rebalance_plan_gate",
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "plan_only": True,
        "current_position_aware": True,
        "frozen_rebalance_slot_target": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_authorized": False,
        "config_trading_enabled": bool(dict(payload.get("risk") or {}).get("trading_enabled", False)),
        "requested_as_of": str(getattr(args, "as_of", "now") or "now"),
        "resolved_as_of_mode": "latest_closed_multiphase_rebalance_slots",
        "upper_timestamp_ms": int(upper_ms),
        "dust_delta_summary": normalized_dust,
        "capital_allocation_context": capital_allocation_context,
        "capital_topup_gate": capital_topup_gate,
        "frozen_slot_gate": frozen_slot_gate,
    }
    _write_multiphase_plan_artifacts(
        run_root,
        decision_metadata=decision_metadata,
        portfolio=portfolio,
        bundle=bundle,
        runtime_gate_context=runtime_gate_context,
    )
    status = "mainnet_current_position_rebalance_plan_ready" if not blockers else "blocked"
    if not blockers and capital_deployment_deferred:
        status = "mainnet_current_position_rebalance_deferred"
    if not blockers and not plan.intents:
        if str(plan.status) == "hold_until_next_rebalance_slot":
            status = "mainnet_current_position_rebalance_hold_until_next_rebalance_slot"
        else:
            status = (
                "mainnet_current_position_rebalance_dust_noop"
                if dust_delta_only
                else "mainnet_current_position_rebalance_noop"
            )
    summary = _target_plan_summary(
        run_id=run_id,
        status=status,
        blockers=blockers,
        warnings=warnings,
        started_at=started,
        artifact_root=run_root,
        account_snapshot=account_snapshot,
        current_positions=current_positions,
        planned_order_count=len(plan.intents),
        risk_gate_status="passed" if bundle["risk_gate"].passed else "blocked",
        execution_plan_status=plan.status,
        latest_decision_id=portfolio.decision_id,
        latest_portfolio_id=portfolio.portfolio_id,
        active_execution_phase=plan.active_execution_phase,
        phase_counts=plan.phase_counts,
        deferred_phase_counts=plan.deferred_phase_counts,
        dust_delta_summary=normalized_dust,
        reduce_only_intent_count=sum(1 for intent in plan.intents if intent.reduce_only),
        non_reduce_only_intent_count=sum(1 for intent in plan.intents if not intent.reduce_only),
        target_position_count=len(portfolio.positions),
        capital_allocation_context=capital_allocation_context,
        capital_topup_gate=capital_topup_gate,
        multiphase_context=multiphase_context,
        frozen_slot_gate=frozen_slot_gate,
    )
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("target_portfolios", "portfolio_id", portfolio.portfolio_id, portfolio.metadata())
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="mainnet_multiphase_target_plan",
        artifact_id=f"{run_id}:target_plan",
        payload=summary,
    )
    return summary, 0 if status in {
        "mainnet_current_position_rebalance_plan_ready",
        "mainnet_current_position_rebalance_noop",
        "mainnet_current_position_rebalance_dust_noop",
        "mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
        "mainnet_current_position_rebalance_deferred",
    } else 2


def build_multiphase_aggregate_target_portfolio(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any],
    config_sha256: str,
    allocated_capital_usdt: float,
    phase_contexts: list[dict[str, Any]],
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
    frontier: FrontierResolution | None = None,
) -> tuple[TargetPortfolio, dict[str, Any]]:
    return build_multiphase_target_portfolio(
        panel,
        config=config,
        config_sha256=config_sha256,
        allocated_capital_usdt=allocated_capital_usdt,
        phase_contexts=phase_contexts,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
        frontier=frontier,
    )


def build_multiphase_target_portfolio(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any],
    config_sha256: str,
    allocated_capital_usdt: float,
    phase_contexts: list[dict[str, Any]],
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
    state_store: LiveTradingStateStore | None = None,
    persist_sleeve_state: bool = False,
    strategy_label: str | None = None,
    frontier: FrontierResolution | None = None,
) -> tuple[TargetPortfolio, dict[str, Any]]:
    sleeve_weight = 1.0 / float(len(phase_contexts) or 1)
    sleeve_rows: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    snapshots: list[dict[str, Any]] = []
    sleeve_state_records: list[dict[str, Any]] = []
    # When the frontier is armed, BOTH the snapshot and the sleeve portfolio must consume
    # the contract-pinned effective config — otherwise the per-phase sleeves would silently
    # split-brain against the single-phase plan. Default-off => frontier None => baseline.
    effective_config = (
        frontier.effective_config
        if (frontier is not None and frontier.is_armed_ready and frontier.effective_config)
        else config
    )
    label = str(strategy_label or effective_config.get("strategy_label") or "hv_balanced")
    for context in phase_contexts:
        phase = int(context.get("phase_offset_days") or 0)
        decision_ms = context.get("decision_time_ms")
        if decision_ms is None:
            blockers.extend(str(item) for item in list(context.get("blockers") or []))
            record = _sleeve_state_record(
                strategy_label=label,
                phase=phase,
                context=context,
                sleeve_weight=sleeve_weight,
                status="blocked",
                blockers=list(context.get("blockers") or []),
                target_positions=[],
            )
            sleeve_state_records.append(record)
            if state_store is not None and persist_sleeve_state:
                state_store.write_multiphase_sleeve_target(record)
            continue
        phase_epoch = int(rebalance_epoch_ms) + phase * DAY_MS
        snapshot = build_live_hv_balanced_snapshot(
            panel,
            config=config,
            config_sha256=config_sha256,
            decision_time_ms=int(decision_ms),
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=phase_epoch,
            frontier=frontier,
        )
        snapshots.append(snapshot.metadata())
        sleeve = build_target_portfolio(snapshot, config=effective_config, allocated_capital_usdt=allocated_capital_usdt)
        blockers.extend(snapshot.blockers)
        blockers.extend(sleeve.blockers)
        record = _sleeve_state_record(
            strategy_label=label,
            phase=phase,
            context=context,
            sleeve_weight=sleeve_weight,
            status="ok" if not [*snapshot.blockers, *sleeve.blockers] else "blocked",
            blockers=[*snapshot.blockers, *sleeve.blockers],
            target_positions=[position.to_dict() for position in sleeve.positions],
            snapshot=snapshot.metadata(),
            portfolio=sleeve.metadata(),
        )
        sleeve_state_records.append(record)
        if state_store is not None and persist_sleeve_state:
            state_store.write_multiphase_sleeve_target(record)
        for position in sleeve.positions:
            weighted = float(position.target_weight) * sleeve_weight
            item = aggregate.setdefault(
                position.usdm_symbol,
                {
                    "subject": position.subject,
                    "usdm_symbol": position.usdm_symbol,
                    "score_sum": 0.0,
                    "weight": 0.0,
                    "phases": [],
                    "selection_reasons": [],
                    "short_multiplier_sum": 0.0,
                    "drawdown_multiplier_sum": 0.0,
                    "count": 0,
                },
            )
            item["weight"] += weighted
            item["score_sum"] += float(position.score) * sleeve_weight
            item["short_multiplier_sum"] += float(position.raw_short_multiplier) * sleeve_weight
            item["drawdown_multiplier_sum"] += float(position.portfolio_drawdown_multiplier) * sleeve_weight
            item["count"] += 1
            item["phases"].append(phase)
            item["selection_reasons"].append(position.selection_reason)
            sleeve_rows.append(
                {
                    "phase_offset_days": phase,
                    "decision_time_ms": int(decision_ms),
                    "decision_date_utc": context.get("decision_date_utc"),
                    "subject": position.subject,
                    "usdm_symbol": position.usdm_symbol,
                    "sleeve_weight": sleeve_weight,
                    "sleeve_target_weight": float(position.target_weight),
                    "aggregate_weight_contribution": weighted,
                    "side": position.side,
                    "score": float(position.score),
                    "selection_reason": position.selection_reason,
                }
            )
    positions: list[TargetPosition] = []
    for symbol, item in sorted(aggregate.items()):
        weight = float(item["weight"])
        if abs(weight) <= 1e-12:
            continue
        count = max(int(item["count"]), 1)
        positions.append(
            TargetPosition(
                subject=str(item["subject"]),
                usdm_symbol=str(symbol),
                side="long" if weight > 0.0 else "short",
                score=float(item["score_sum"]),
                target_weight=weight,
                target_notional_usdt=float(abs(weight) * allocated_capital_usdt),
                previous_target_weight=0.0,
                delta_target_weight=weight,
                raw_short_multiplier=float(item["short_multiplier_sum"]) / float(count),
                portfolio_drawdown_multiplier=float(item["drawdown_multiplier_sum"]) / float(count),
                selection_reason="multiphase_aggregate:" + ",".join(sorted(set(str(value) for value in item["selection_reasons"]))),
            )
        )
    gross = sum(abs(position.target_weight) for position in positions)
    net = sum(position.target_weight for position in positions)
    portfolio = TargetPortfolio(
        portfolio_id=f"hv_balanced_multiphase:{max(int(context.get('decision_time_ms') or 0) for context in phase_contexts)}:portfolio",
        decision_id="hv_balanced_multiphase_aggregate",
        strategy_label=label + ":multiphase_10_sleeve",
        allocated_capital_usdt=float(allocated_capital_usdt),
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=float(gross),
        target_net_weight=float(net),
        status="ok" if not blockers else "blocked",
        blockers=sorted(set(str(item) for item in blockers)),
        positions=positions,
    )
    return portfolio, {
        "status": portfolio.status,
        "blockers": portfolio.blockers,
        "sleeve_weight": sleeve_weight,
        "phase_contexts": phase_contexts,
        "snapshots": snapshots,
        "sleeve_targets": sleeve_rows,
        "sleeve_state_records": sleeve_state_records,
        "target_engine": MULTIPHASE_TARGET_ENGINE,
    }


def build_target_shadow_comparison(
    *,
    single_positions: pd.DataFrame,
    multiphase_positions: pd.DataFrame,
    single_sizing: pd.DataFrame,
    multiphase_sizing: pd.DataFrame,
    allocated_capital_usdt: float,
) -> dict[str, Any]:
    single = _positions_by_symbol(single_positions, "single")
    multi = _positions_by_symbol(multiphase_positions, "multiphase")
    merged = single.merge(multi, on="symbol", how="outer").fillna(0.0)
    if merged.empty:
        by_symbol = pd.DataFrame(columns=["symbol"])
    else:
        merged["target_weight_delta_multiphase_minus_single"] = merged["multiphase_target_weight"] - merged["single_target_weight"]
        merged["target_notional_delta_multiphase_minus_single"] = (
            merged["target_weight_delta_multiphase_minus_single"].abs() * float(allocated_capital_usdt)
        )
        by_symbol = merged.sort_values("symbol").reset_index(drop=True)
    return {
        "summary": {
            "single_phase": _sizing_summary(single_sizing),
            "multiphase_aggregate": _sizing_summary(multiphase_sizing),
            "target_symbol_union_count": int(len(by_symbol)),
            "absolute_target_weight_difference_sum": float(
                pd.to_numeric(by_symbol.get("target_weight_delta_multiphase_minus_single"), errors="coerce").abs().sum()
            )
            if not by_symbol.empty
            else 0.0,
            "absolute_target_notional_difference_sum_usdt": float(
                pd.to_numeric(by_symbol.get("target_notional_delta_multiphase_minus_single"), errors="coerce").sum()
            )
            if not by_symbol.empty
            else 0.0,
        },
        "by_symbol": by_symbol,
    }


def _capital_context_with_resolved_allocated_capital(
    capital_context: dict[str, Any],
    *,
    resolved_allocated_capital_usdt: float,
) -> dict[str, Any]:
    context = dict(capital_context)
    baseline = _float(context.get("baseline_allocated_capital_usdt"))
    resolved = max(0.0, float(resolved_allocated_capital_usdt))
    context["resolved_allocated_capital_usdt"] = float(resolved)
    context["capped_resolved_allocated_capital_usdt"] = float(resolved)
    context["additional_allocated_capital_usdt"] = float(resolved - baseline)
    context["raw_additional_allocated_capital_usdt"] = float(resolved - baseline)
    return context


def _select_margin_safe_allocated_capital(
    *,
    payload: dict[str, Any],
    initial_allocated_capital_usdt: float,
    initial_portfolio: TargetPortfolio,
    initial_multiphase_context: dict[str, Any],
    initial_bundle: dict[str, Any],
    initial_capital_context: dict[str, Any],
    build_candidate: Callable[[float], tuple[TargetPortfolio, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    context = {
        "enabled": _margin_safe_truncation_enabled(payload),
        "applied": False,
        "status": "disabled",
        "initial_allocated_capital_usdt": float(initial_allocated_capital_usdt),
        "final_allocated_capital_usdt": float(initial_allocated_capital_usdt),
        "initial_margin_gate": _margin_gate_snapshot(initial_bundle),
        "final_margin_gate": _margin_gate_snapshot(initial_bundle),
        "iterations": 0,
        "blockers": [],
    }
    if not context["enabled"]:
        return {
            "portfolio": initial_portfolio,
            "multiphase_context": initial_multiphase_context,
            "bundle": initial_bundle,
            "capital_context": initial_capital_context,
            "context": context,
        }
    context["status"] = "not_required"
    if _margin_gate_passed(initial_bundle):
        return {
            "portfolio": initial_portfolio,
            "multiphase_context": initial_multiphase_context,
            "bundle": initial_bundle,
            "capital_context": initial_capital_context,
            "context": context,
        }
    if not _margin_gate_has_truncatable_blocker(initial_bundle):
        context["status"] = "not_truncatable"
        return {
            "portfolio": initial_portfolio,
            "multiphase_context": initial_multiphase_context,
            "bundle": initial_bundle,
            "capital_context": initial_capital_context,
            "context": context,
        }

    capital = dict(payload.get("capital") or {})
    deployment = dict(payload.get("capital_deployment") or {})
    min_allocated = _first_configured_float(
        capital.get("margin_safe_min_allocated_capital_usdt"),
        deployment.get("margin_safe_min_allocated_capital_usdt"),
        0.0,
    )
    tolerance = _first_configured_float(
        capital.get("margin_safe_truncation_tolerance_usdt"),
        deployment.get("margin_safe_truncation_tolerance_usdt"),
        1.0,
    )
    max_iterations = int(
        _first_configured_float(
            capital.get("margin_safe_truncation_max_iterations"),
            deployment.get("margin_safe_truncation_max_iterations"),
            18.0,
        )
        or 18
    )
    min_allocated = max(0.0, float(min_allocated or 0.0))
    tolerance = max(0.01, float(tolerance or 1.0))
    max_iterations = max(1, min(int(max_iterations), 40))

    low = min(min_allocated, max(0.0, float(initial_allocated_capital_usdt)))
    high = max(0.0, float(initial_allocated_capital_usdt))
    best_portfolio, best_context, best_bundle, best_capital_context = build_candidate(low)
    context["min_allocated_capital_usdt"] = float(low)
    context["min_allocated_margin_gate"] = _margin_gate_snapshot(best_bundle)
    if not _margin_gate_passed(best_bundle):
        context["status"] = "blocked_min_allocated_not_margin_safe"
        context["blockers"] = list(best_bundle.get("margin_cushion_gate", {}).get("blockers") or [])
        return {
            "portfolio": initial_portfolio,
            "multiphase_context": initial_multiphase_context,
            "bundle": initial_bundle,
            "capital_context": initial_capital_context,
            "context": context,
        }

    iterations = 0
    while iterations < max_iterations and high - low > tolerance:
        iterations += 1
        mid = (low + high) / 2.0
        candidate_portfolio, candidate_context, candidate_bundle, candidate_capital_context = build_candidate(mid)
        if _margin_gate_passed(candidate_bundle):
            low = mid
            best_portfolio = candidate_portfolio
            best_context = candidate_context
            best_bundle = candidate_bundle
            best_capital_context = candidate_capital_context
        else:
            high = mid

    final_allocated = float(best_capital_context.get("resolved_allocated_capital_usdt") or 0.0)
    context.update(
        {
            "applied": True,
            "status": "applied",
            "iterations": int(iterations),
            "final_allocated_capital_usdt": float(final_allocated),
            "truncated_allocated_capital_usdt": float(max(0.0, initial_allocated_capital_usdt - final_allocated)),
            "final_margin_gate": _margin_gate_snapshot(best_bundle),
        }
    )
    best_capital_context = dict(best_capital_context)
    best_capital_context["margin_safe_truncation_applied"] = True
    best_capital_context["pre_truncation_resolved_allocated_capital_usdt"] = float(initial_allocated_capital_usdt)
    return {
        "portfolio": best_portfolio,
        "multiphase_context": best_context,
        "bundle": best_bundle,
        "capital_context": best_capital_context,
        "context": context,
    }


def _margin_safe_truncation_enabled(payload: dict[str, Any]) -> bool:
    capital = dict(payload.get("capital") or {})
    deployment = dict(payload.get("capital_deployment") or {})
    return _as_bool(
        capital.get(
            "auto_truncate_allocated_capital_to_margin_gate",
            deployment.get("auto_truncate_allocated_capital_to_margin_gate"),
        ),
        default=False,
    )


def _first_configured_float(*values: Any) -> float:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return float(parsed)
    return 0.0


def _margin_gate_passed(bundle: dict[str, Any]) -> bool:
    gate = dict(bundle.get("margin_cushion_gate") or {})
    return str(gate.get("status") or "").strip().lower() == "passed" and not list(gate.get("blockers") or [])


def _margin_gate_has_truncatable_blocker(bundle: dict[str, Any]) -> bool:
    blockers = [str(item) for item in list(dict(bundle.get("margin_cushion_gate") or {}).get("blockers") or [])]
    fragments = (
        "available_balance_below_min_after_plan",
        "available_balance_negative_after_plan",
        "available_balance_ratio_below_min_after_plan",
        "margin_cushion_below_min_after_plan",
    )
    return any(any(fragment in blocker for fragment in fragments) for blocker in blockers)


def _margin_gate_snapshot(bundle: dict[str, Any]) -> dict[str, Any]:
    gate = dict(bundle.get("margin_cushion_gate") or {})
    return {
        "status": str(gate.get("status") or ""),
        "blockers": list(gate.get("blockers") or []),
        "available_balance_usdt": _float(gate.get("available_balance_usdt")),
        "planned_additional_initial_margin_usdt": _float(gate.get("planned_additional_initial_margin_usdt")),
        "post_plan_available_balance_usdt": _float(gate.get("post_plan_available_balance_usdt")),
        "post_plan_available_balance_ratio": _float(gate.get("post_plan_available_balance_ratio")),
        "min_available_balance_after_plan_usdt": gate.get("min_available_balance_after_plan_usdt"),
        "min_available_balance_ratio_after_plan": gate.get("min_available_balance_ratio_after_plan"),
        "min_margin_cushion_after_plan_usdt": gate.get("min_margin_cushion_after_plan_usdt"),
    }


def _persist_multiphase_sleeve_state(state_store: LiveTradingStateStore, multiphase_context: dict[str, Any]) -> None:
    for record in list(multiphase_context.get("sleeve_state_records") or []):
        state_store.write_multiphase_sleeve_target(dict(record))


def _build_shadow_bundle(
    *,
    label: str,
    portfolio: TargetPortfolio,
    current_positions: dict[str, float],
    mark_prices: dict[str, float],
    symbol_filters: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    risk_payload: dict[str, Any],
    account_snapshot: dict[str, Any],
    frozen_target_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_gate = evaluate_risk_gate(portfolio, mode="plan_only", config=risk_payload, live_confirmed=False)
    execution_deadband = dict(payload.get("execution_deadband") or {})
    frozen_target_positions = target_position_overrides(frozen_target_snapshot)
    frozen_reference_prices = target_reference_prices(frozen_target_snapshot)
    sizing = build_order_sizing_report(
        portfolio,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        target_position_overrides=frozen_target_positions,
        target_reference_prices=frozen_reference_prices,
    )
    min_capital = summarize_order_sizing_report(sizing, allocated_capital_usdt=portfolio.allocated_capital_usdt)
    dust = summarize_dust_residual_order_sizing(sizing)
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        target_position_overrides=frozen_target_positions,
        target_reference_prices=frozen_reference_prices,
        allow_live_order_submission=False,
    )
    planned_margin = planned_additional_initial_margin_usdt_for_plan(sizing, plan=plan, payload=payload)
    margin_gate = evaluate_margin_cushion_gate(
        {
            "available_balance_usdt": account_snapshot.get("available_balance_usdt"),
            "total_wallet_balance_usdt": account_snapshot.get("total_wallet_balance_usdt"),
        },
        config=payload,
        planned_additional_initial_margin_usdt=planned_margin,
        require_configured=True,
    )
    margin_gate, pre_reduce_only_margin_gate = _maybe_allow_reduce_only_margin_gate_below_min(
        margin_gate,
        plan=plan,
        payload=payload,
    )
    bundle: dict[str, Any] = {
        "label": label,
        "risk_gate": risk_gate,
        "order_sizing_report": sizing,
        "min_executable_capital_report": min_capital,
        "dust_delta_summary": dust,
        "execution_plan": plan,
        "margin_cushion_gate": margin_gate,
        "summary": {
            "label": label,
            "target_status": portfolio.status,
            "target_blockers": list(portfolio.blockers),
            "target_position_count": int(len(portfolio.positions)),
            "target_gross_weight": float(portfolio.target_gross_weight),
            "target_net_weight": float(portfolio.target_net_weight),
            "risk_gate_status": "passed" if risk_gate.passed else "blocked",
            "risk_gate_blockers": list(risk_gate.blockers),
            "execution_plan_status": plan.status,
            "planned_delta_order_count": int(len(plan.intents)),
            "active_execution_phase": str(plan.active_execution_phase or ""),
            "phase_counts": dict(plan.phase_counts),
            "deferred_phase_counts": dict(plan.deferred_phase_counts),
            "sizing_status": min_capital.get("status"),
            "min_allocated_capital_usdt_for_all_targets": min_capital.get("min_allocated_capital_usdt_for_all_targets"),
            "non_executable_target_symbols": list(min_capital.get("non_executable_target_symbols") or []),
            "dust_delta_summary": dust,
            "planned_additional_initial_margin_usdt": float(planned_margin),
            "margin_cushion_gate": margin_gate,
        },
    }
    if pre_reduce_only_margin_gate is not None:
        bundle["pre_reduce_only_margin_cushion_gate"] = pre_reduce_only_margin_gate
        bundle["summary"]["pre_reduce_only_margin_cushion_gate"] = pre_reduce_only_margin_gate
    return bundle


def _refresh_bundle_plan_summary(bundle: dict[str, Any]) -> None:
    plan = bundle.get("execution_plan")
    if not isinstance(plan, ExecutionPlan):
        return
    summary = dict(bundle.get("summary") or {})
    summary.update(
        {
            "execution_plan_status": str(plan.status),
            "planned_delta_order_count": int(len(plan.intents)),
            "active_execution_phase": str(plan.active_execution_phase or ""),
            "phase_counts": dict(plan.phase_counts),
            "deferred_phase_counts": dict(plan.deferred_phase_counts),
        }
    )
    bundle["summary"] = summary


def planned_additional_initial_margin_usdt(sizing: pd.DataFrame, *, payload: dict[str, Any]) -> float:
    leverage = int(float(dict(payload.get("binance") or {}).get("max_leverage") or 0))
    if leverage <= 0 or sizing.empty:
        return 0.0
    total = 0.0
    for _, row in sizing.iterrows():
        if _truthy(row.get("no_order_required")) or _truthy(row.get("reduce_only")):
            continue
        phase = str(row.get("execution_phase") or "").strip().lower()
        if phase in {"", "noop", "dust_noop", "deadband_noop", "reduce_first"}:
            continue
        if str(row.get("blockers") or "").strip():
            continue
        notional = _float(row.get("rounded_notional_usdt"))
        if notional <= 0.0:
            notional = abs(_float(row.get("order_delta_position_amt"))) * _float(row.get("mark_price"))
        total += max(0.0, notional / float(leverage))
    return float(total)


def planned_additional_initial_margin_usdt_for_plan(
    sizing: pd.DataFrame,
    *,
    plan: ExecutionPlan,
    payload: dict[str, Any],
) -> float:
    if sizing.empty or not plan.intents:
        return 0.0
    rows = sizing.to_dict(orient="records")
    active_rows: list[dict[str, Any]] = []
    for intent in plan.intents:
        if bool(intent.reduce_only):
            continue
        for row in rows:
            if str(row.get("symbol") or "") != str(intent.symbol):
                continue
            if str(row.get("execution_phase") or "") != str(intent.execution_phase or ""):
                continue
            if _truthy(row.get("no_order_required")) or _truthy(row.get("reduce_only")):
                continue
            if str(row.get("blockers") or "").strip():
                continue
            active_rows.append(dict(row))
            break
    if not active_rows:
        return 0.0
    return planned_additional_initial_margin_usdt(pd.DataFrame(active_rows), payload=payload)


def _maybe_allow_reduce_only_margin_gate_below_min(
    margin_gate: dict[str, Any],
    *,
    plan: ExecutionPlan,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    risk = dict(payload.get("risk") or {})
    if not _as_bool(risk.get("allow_reduce_only_plan_when_margin_below_min"), default=False):
        return margin_gate, None
    if str(margin_gate.get("status") or "").strip().lower() == "passed" and not list(margin_gate.get("blockers") or []):
        return margin_gate, None
    if not plan.intents or any(not bool(intent.reduce_only) for intent in plan.intents):
        return margin_gate, None
    if str(plan.active_execution_phase or "").strip().lower() != "reduce_first":
        return margin_gate, None
    if _float(margin_gate.get("planned_additional_initial_margin_usdt")) > 1e-9:
        return margin_gate, None
    blockers = [str(item) for item in list(margin_gate.get("blockers") or [])]
    allowed_fragments = (
        "available_balance_below_min_after_plan",
        "available_balance_negative_after_plan",
        "available_balance_ratio_below_min_after_plan",
        "margin_cushion_below_min_after_plan",
    )
    if not blockers or not all(any(fragment in blocker for fragment in allowed_fragments) for blocker in blockers):
        return margin_gate, None

    pre_override = dict(margin_gate)
    warnings = sorted(set([str(item) for item in list(margin_gate.get("warnings") or [])] + ["reduce_only_plan_allowed_below_margin_floor"]))
    updated = dict(margin_gate)
    updated.update(
        {
            "status": "passed",
            "passed": True,
            "blockers": [],
            "warnings": warnings,
            "reduce_only_margin_floor_override": True,
            "pre_override_status": str(margin_gate.get("status") or ""),
            "pre_override_blockers": blockers,
            "override_reason": "active_plan_is_reduce_only_and_adds_no_initial_margin",
        }
    )
    return updated, pre_override


def _write_bundle(
    root: Path,
    snapshot: LiveDecisionSnapshot | None,
    portfolio: TargetPortfolio,
    bundle: dict[str, Any],
    *,
    decision_metadata: dict[str, Any] | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if snapshot is not None:
        write_json(root / "decision_snapshot.json", snapshot.metadata())
        snapshot.scores.to_csv(root / "decision_scores.csv", index=False)
    else:
        write_json(root / "decision_snapshot.json", decision_metadata or {"status": "multiphase_aggregate"})
        pd.DataFrame().to_csv(root / "decision_scores.csv", index=False)
    write_json(root / "target_portfolio.json", portfolio.metadata())
    portfolio.positions_frame().to_csv(root / "target_positions.csv", index=False)
    write_json(root / "risk_gate.json", bundle["risk_gate"].to_dict())
    bundle["order_sizing_report"].to_csv(root / "order_sizing_report.csv", index=False)
    write_json(root / "min_executable_capital_report.json", bundle["min_executable_capital_report"])
    write_json(root / "dust_delta_summary.json", bundle["dust_delta_summary"])
    write_json(root / "execution_plan.json", bundle["execution_plan"].metadata())
    bundle["execution_plan"].intents_frame().to_csv(root / "execution_plan.csv", index=False)
    write_json(root / "margin_cushion_gate.json", bundle["margin_cushion_gate"])
    if "pre_reduce_only_margin_cushion_gate" in bundle:
        write_json(root / "pre_reduce_only_margin_cushion_gate.json", bundle["pre_reduce_only_margin_cushion_gate"])
    if "deferred_if_executed_margin_cushion_gate" in bundle:
        write_json(
            root / "deferred_if_executed_margin_cushion_gate.json",
            bundle["deferred_if_executed_margin_cushion_gate"],
        )
    write_json(root / "summary.json", bundle["summary"])
    pd.DataFrame().to_csv(root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(root / "fills.csv", index=False)


def _write_multiphase_plan_artifacts(
    run_root: Path,
    *,
    decision_metadata: dict[str, Any],
    portfolio: TargetPortfolio,
    bundle: dict[str, Any],
    runtime_gate_context: dict[str, Any],
) -> None:
    write_json(run_root / "runtime_gate_context.json", runtime_gate_context)
    _write_bundle(run_root, None, portfolio, bundle, decision_metadata=decision_metadata)


def _write_empty_target_plan_artifacts(run_root: Path) -> None:
    write_json(run_root / "runtime_gate_context.json", {"plan_only": True, "mainnet_order_submission_authorized": False})
    write_json(run_root / "decision_snapshot.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "decision_scores.csv", index=False)
    write_json(run_root / "target_portfolio.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "target_positions.csv", index=False)
    write_json(run_root / "risk_gate.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "order_sizing_report.csv", index=False)
    write_json(run_root / "min_executable_capital_report.json", {"status": "not_run"})
    write_json(run_root / "dust_delta_summary.json", {"status": "not_run"})
    write_json(run_root / "execution_plan.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "execution_plan.csv", index=False)
    write_json(run_root / "margin_cushion_gate.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)


def _write_empty_artifacts(run_root: Path) -> None:
    write_json(run_root / "target_shadow_comparison.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "target_shadow_comparison_by_symbol.csv", index=False)


def _sleeve_state_record(
    *,
    strategy_label: str,
    phase: int,
    context: dict[str, Any],
    sleeve_weight: float,
    status: str,
    blockers: list[Any],
    target_positions: list[dict[str, Any]],
    snapshot: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "sleeve_id": f"{strategy_label}:phase:{int(phase)}",
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "strategy_label": str(strategy_label),
        "phase_offset_days": int(phase),
        "decision_time_ms": context.get("decision_time_ms"),
        "decision_date_utc": context.get("decision_date_utc"),
        "rebalance_interval_days": context.get("rebalance_interval_days"),
        "rebalance_epoch_ms": context.get("rebalance_epoch_ms"),
        "sleeve_weight": float(sleeve_weight),
        "status": str(status),
        "blockers": sorted(set(str(item) for item in blockers)),
        "target_position_count": int(len(target_positions)),
        "target_positions": list(target_positions),
        "snapshot": dict(snapshot or {}),
        "portfolio": dict(portfolio or {}),
    }


def _multiphase_decision_metadata(
    *,
    portfolio: TargetPortfolio,
    context: dict[str, Any],
    upper_ms: int,
) -> dict[str, Any]:
    phase_contexts = list(context.get("phase_contexts") or [])
    decision_times = [
        int(item.get("decision_time_ms"))
        for item in phase_contexts
        if item.get("decision_time_ms") is not None
    ]
    dates = [str(item.get("decision_date_utc") or "") for item in phase_contexts if str(item.get("decision_date_utc") or "")]
    return {
        "decision_id": portfolio.decision_id,
        "strategy_label": portfolio.strategy_label,
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "decision_time_ms": max(decision_times, default=int(upper_ms)),
        "decision_date_utc": max(dates) if dates else datetime.fromtimestamp(int(upper_ms) / 1000, tz=UTC).date().isoformat(),
        "rebalance_slot": True,
        "status": "ok" if portfolio.status == "ok" else portfolio.status,
        "blockers": list(portfolio.blockers),
        "phase_count": int(len(phase_contexts)),
        "phase_decision_time_ms": decision_times,
        "phase_decision_dates_utc": dates,
        "input_bar_end_ms": int(upper_ms),
    }


def _latest_mark_prices_from_panel(panel: pd.DataFrame, *, upper_timestamp_ms: int) -> dict[str, float]:
    if panel.empty or "timestamp_ms" not in panel.columns or "usdm_symbol" not in panel.columns:
        return {}
    price_column = "mark_price" if "mark_price" in panel.columns else "perp_close" if "perp_close" in panel.columns else ""
    if not price_column:
        return {}
    frame = panel.copy()
    frame["timestamp_ms"] = pd.to_numeric(frame["timestamp_ms"], errors="coerce")
    frame[price_column] = pd.to_numeric(frame[price_column], errors="coerce")
    frame = frame.loc[frame["timestamp_ms"].le(int(upper_timestamp_ms)) & frame[price_column].gt(0.0)].copy()
    if frame.empty:
        return {}
    latest = frame.sort_values(["usdm_symbol", "timestamp_ms"]).groupby("usdm_symbol", as_index=False).tail(1)
    return {str(row["usdm_symbol"]): float(row[price_column]) for _, row in latest.iterrows()}


def _target_plan_summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    warnings: list[str],
    started_at: datetime,
    artifact_root: Path,
    account_snapshot: dict[str, Any],
    current_positions: dict[str, float],
    planned_order_count: int,
    risk_gate_status: str,
    execution_plan_status: str,
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
    active_execution_phase: str = "",
    phase_counts: dict[str, int] | None = None,
    deferred_phase_counts: dict[str, int] | None = None,
    dust_delta_summary: dict[str, Any] | None = None,
    reduce_only_intent_count: int = 0,
    non_reduce_only_intent_count: int = 0,
    target_position_count: int = 0,
    capital_allocation_context: dict[str, Any] | None = None,
    capital_topup_gate: dict[str, Any] | None = None,
    multiphase_context: dict[str, Any] | None = None,
    frozen_slot_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capital_context = dict(capital_allocation_context or {})
    topup_gate = dict(capital_topup_gate or {})
    context = dict(multiphase_context or {})
    dust = dict(dust_delta_summary or {})
    slot_gate = dict(frozen_slot_gate or {})
    return {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "artifact_root": str(artifact_root),
        "latest_decision_id": latest_decision_id,
        "latest_portfolio_id": latest_portfolio_id,
        "current_position_aware": True,
        "plan_only": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_enabled": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "open_order_count": int(account_snapshot.get("open_order_count") or 0),
        "current_position_count": int(sum(1 for value in current_positions.values() if abs(float(value)) > 1e-12)),
        "target_position_count": int(target_position_count),
        "planned_delta_order_count": int(planned_order_count),
        "reduce_only_intent_count": int(reduce_only_intent_count),
        "non_reduce_only_intent_count": int(non_reduce_only_intent_count),
        "risk_gate_status": risk_gate_status,
        "execution_plan_status": execution_plan_status,
        "active_execution_phase": active_execution_phase,
        "phase_counts": dict(phase_counts or {}),
        "deferred_phase_counts": dict(deferred_phase_counts or {}),
        "dust_delta_noop": bool(dust.get("is_dust_residual_only")),
        "dust_delta_symbols": list(dust.get("dust_symbols") or []),
        "dust_delta_blockers": list(dust.get("dust_blockers") or []),
        "capital_topup_requested": bool(capital_context.get("capital_topup_requested", False)),
        "capital_dynamic_requested": bool(capital_context.get("capital_dynamic_requested", False)),
        "capital_topup_gate_status": str(topup_gate.get("status") or "not_requested"),
        "capital_topup_gate_blockers": list(topup_gate.get("blockers") or []),
        "capital_sizing_basis": str(capital_context.get("sizing_basis") or ""),
        "baseline_allocated_capital_usdt": float(capital_context.get("baseline_allocated_capital_usdt") or 0.0),
        "resolved_allocated_capital_usdt": float(capital_context.get("resolved_allocated_capital_usdt") or 0.0),
        "additional_allocated_capital_usdt": float(capital_context.get("additional_allocated_capital_usdt") or 0.0),
        "frozen_rebalance_slot_target": bool(slot_gate),
        "rebalance_slot_id": str(slot_gate.get("slot_id") or ""),
        "rebalance_slot_target_hash": str(slot_gate.get("active_target_hash") or ""),
        "rebalance_slot_gate_status": str(slot_gate.get("status") or ""),
        "hold_until_next_rebalance_slot": str(slot_gate.get("status") or "") == "hold_until_next_rebalance_slot",
        "multiphase_sleeve_count": int(len(context.get("sleeve_state_records") or [])),
        "multiphase_latest_decision_dates": [
            str(item.get("decision_date_utc") or "")
            for item in list(context.get("phase_contexts") or [])
        ],
    }


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    account_snapshot: dict[str, Any],
    shadow_blockers: list[str] | None = None,
    single_phase: dict[str, Any] | None = None,
    multiphase_aggregate: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    single_decision_date_utc: str | None = None,
    multiphase_latest_decision_dates: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "shadow_type": "single_phase_vs_multiphase_aggregate_no_order",
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "shadow_blockers": sorted(set(shadow_blockers or [])),
        "artifact_root": str(artifact_root),
        "plan_only": True,
        "mainnet_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "open_order_count": int(account_snapshot.get("open_order_count") or 0),
        "available_balance_usdt": float(account_snapshot.get("available_balance_usdt") or 0.0),
        "total_wallet_balance_usdt": float(account_snapshot.get("total_wallet_balance_usdt") or 0.0),
        "single_decision_date_utc": single_decision_date_utc,
        "multiphase_latest_decision_dates": list(multiphase_latest_decision_dates or []),
        "single_phase": dict(single_phase or {}),
        "multiphase_aggregate": dict(multiphase_aggregate or {}),
        "comparison": dict(comparison or {}),
    }


def _resolve_as_of_upper_ms(panel: pd.DataFrame, as_of: str) -> int:
    timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce").dropna().astype("int64")
    unique = pd.Series(sorted(set(int(item) for item in timestamps.tolist())), dtype="int64")
    if unique.empty:
        return 0
    normalized = str(as_of or "now").strip().lower()
    if normalized in {"", "now", "auto", "latest_closed_bar", "latest_closed_rebalance_slot"}:
        return int(unique.max())
    return min(int(_parse_as_of_ms(str(as_of))), int(unique.max()))


def _resolve_phase_decision_time_context(
    panel: pd.DataFrame,
    *,
    phase_offset_days: int,
    upper_timestamp_ms: int,
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
) -> dict[str, Any]:
    timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce").dropna().astype("int64")
    unique = pd.Series(sorted(set(int(item) for item in timestamps.tolist())), dtype="int64")
    phase_epoch = int(rebalance_epoch_ms) + int(phase_offset_days) * DAY_MS
    eligible = unique.loc[
        unique.le(int(upper_timestamp_ms))
        & unique.map(
            lambda value: is_rebalance_slot(
                decision_time_ms=int(value),
                rebalance_interval_days=int(rebalance_interval_days),
                epoch_ms=phase_epoch,
            )
        )
    ]
    if eligible.empty:
        return {
            "phase_offset_days": int(phase_offset_days),
            "decision_time_ms": None,
            "blockers": [f"phase_no_closed_rebalance_slot:{phase_offset_days}"],
        }
    decision_ms = int(eligible.max())
    return {
        "phase_offset_days": int(phase_offset_days),
        "decision_time_ms": decision_ms,
        "decision_date_utc": datetime.fromtimestamp(decision_ms / 1000, tz=UTC).date().isoformat(),
        "rebalance_interval_days": int(rebalance_interval_days),
        "rebalance_epoch_ms": phase_epoch,
        "blockers": [],
    }


def _single_phase_as_of(as_of: Any) -> str:
    raw = str(as_of or "now").strip().lower()
    if raw in {"", "now", "auto"}:
        return "latest_closed_rebalance_slot"
    return str(as_of)


def _positions_by_symbol(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["symbol", f"{prefix}_target_weight", f"{prefix}_target_notional_usdt"])
    out = frame.copy()
    out["symbol"] = out["usdm_symbol"].astype(str)
    return out[["symbol", "target_weight", "target_notional_usdt"]].rename(
        columns={
            "target_weight": f"{prefix}_target_weight",
            "target_notional_usdt": f"{prefix}_target_notional_usdt",
        }
    )


def _sizing_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"row_count": 0}
    rows = frame.to_dict(orient="records")
    blockers = [str(row.get("blockers") or "") for row in rows if str(row.get("blockers") or "").strip()]
    return {
        "row_count": int(len(rows)),
        "target_row_count": int(sum(_truthy(row.get("has_target")) for row in rows)),
        "executable_order_count": int(sum(_truthy(row.get("executable")) for row in rows)),
        "no_order_required_count": int(sum(_truthy(row.get("no_order_required")) for row in rows)),
        "raw_abs_delta_qty_sum": float(sum(abs(_float(row.get("raw_abs_delta_qty"))) for row in rows)),
        "rounded_order_notional_sum_usdt": float(sum(_float(row.get("rounded_notional_usdt")) for row in rows)),
        "min_notional_blocker_count": int(sum("notional_below_min" in str(row.get("blockers") or "") for row in rows)),
        "min_qty_blocker_count": int(sum("quantity_below_min" in str(row.get("blockers") or "") for row in rows)),
        "blockers": sorted(set(blockers)),
    }


def _scores_mark_prices(multiphase_context: dict[str, Any]) -> dict[str, float]:
    # The aggregate positions are sized from the single shared live panel; order sizing
    # will also receive mark prices from the latest single-phase decision scores.
    # This hook is kept explicit so future phase-specific mark snapshots can be added
    # without changing the runner contract.
    return {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _max_allowed_leverage(binance: dict[str, Any]) -> int:
    return int(float(binance.get("max_leverage") or binance.get("leverage") or 0))


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").replace("\r", " ").strip()
    return message[:500]
