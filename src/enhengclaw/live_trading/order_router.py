from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmClient, BinanceUsdmResponse
from enhengclaw.live_trading.models import OrderIntent


TERMINAL_ORDER_STATUSES = frozenset({"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"})


@dataclass(frozen=True, slots=True)
class BinanceOrderSnapshot:
    symbol: str
    client_order_id: str
    order_id: int | None
    status: str
    side: str
    order_type: str
    position_side: str
    reduce_only: bool
    original_quantity: float
    executed_quantity: float
    average_price: float
    update_time_ms: int | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_ORDER_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OrderTradeUpdateEvent:
    event_type: str
    event_time_ms: int
    transaction_time_ms: int
    symbol: str
    client_order_id: str
    side: str
    order_type: str
    time_in_force: str
    original_quantity: float
    original_price: float
    average_price: float
    execution_type: str
    order_status: str
    order_id: int | None
    last_filled_quantity: float
    cumulative_filled_quantity: float
    last_filled_price: float
    commission_asset: str
    commission: float
    trade_time_ms: int | None
    trade_id: int | None
    maker: bool
    reduce_only: bool
    position_side: str
    realized_profit: float
    expiry_reason: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.order_status in TERMINAL_ORDER_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class UnknownOrderRecoveryResult:
    symbol: str
    client_order_id: str
    status: str
    source: str
    order_status: str | None = None
    execution_type: str | None = None
    order_id: int | None = None
    filled_quantity: float | None = None
    blockers: list[str] = field(default_factory=list)
    next_action: str = "do_not_resubmit"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_order_snapshot(payload: dict[str, Any]) -> BinanceOrderSnapshot:
    return BinanceOrderSnapshot(
        symbol=str(payload.get("symbol") or ""),
        client_order_id=str(payload.get("clientOrderId") or payload.get("origClientOrderId") or ""),
        order_id=_optional_int(payload.get("orderId")),
        status=str(payload.get("status") or ""),
        side=str(payload.get("side") or ""),
        order_type=str(payload.get("type") or payload.get("origType") or ""),
        position_side=str(payload.get("positionSide") or ""),
        reduce_only=bool(payload.get("reduceOnly", False)),
        original_quantity=_float(payload.get("origQty")),
        executed_quantity=_float(payload.get("executedQty") or payload.get("cumQty")),
        average_price=_float(payload.get("avgPrice")),
        update_time_ms=_optional_int(payload.get("updateTime")),
        raw=dict(payload),
    )


def parse_order_trade_update_event(event: dict[str, Any]) -> OrderTradeUpdateEvent:
    if str(event.get("e") or "") != "ORDER_TRADE_UPDATE":
        raise ValueError(f"unsupported user data event type: {event.get('e')}")
    order = dict(event.get("o") or {})
    return OrderTradeUpdateEvent(
        event_type=str(event.get("e") or ""),
        event_time_ms=int(event.get("E") or 0),
        transaction_time_ms=int(event.get("T") or 0),
        symbol=str(order.get("s") or ""),
        client_order_id=str(order.get("c") or ""),
        side=str(order.get("S") or ""),
        order_type=str(order.get("o") or ""),
        time_in_force=str(order.get("f") or ""),
        original_quantity=_float(order.get("q")),
        original_price=_float(order.get("p")),
        average_price=_float(order.get("ap")),
        execution_type=str(order.get("x") or ""),
        order_status=str(order.get("X") or ""),
        order_id=_optional_int(order.get("i")),
        last_filled_quantity=_float(order.get("l")),
        cumulative_filled_quantity=_float(order.get("z")),
        last_filled_price=_float(order.get("L")),
        commission_asset=str(order.get("N") or ""),
        commission=_float(order.get("n")),
        trade_time_ms=_optional_int(order.get("T")),
        trade_id=_optional_int(order.get("t")),
        maker=bool(order.get("m", False)),
        reduce_only=bool(order.get("R", False)),
        position_side=str(order.get("ps") or ""),
        realized_profit=_float(order.get("rp")),
        expiry_reason=str(order.get("er") or ""),
        raw=dict(event),
    )


def query_order_by_client_id(
    client: BinanceUsdmClient,
    *,
    symbol: str,
    client_order_id: str,
) -> BinanceOrderSnapshot:
    response = client.query_order(symbol=symbol, orig_client_order_id=client_order_id)
    return parse_order_snapshot(dict(response.payload))


def cancel_order_by_client_id(
    client: BinanceUsdmClient,
    *,
    symbol: str,
    client_order_id: str,
) -> BinanceOrderSnapshot:
    response = client.cancel_order(symbol=symbol, orig_client_order_id=client_order_id)
    return parse_order_snapshot(dict(response.payload))


def submit_testnet_strategy_order_intent(
    client: BinanceUsdmClient,
    intent: OrderIntent,
    *,
    new_order_resp_type: str = "RESULT",
) -> BinanceOrderSnapshot:
    params: dict[str, Any] = {
        "symbol": intent.symbol,
        "side": intent.side,
        "positionSide": intent.position_side,
        "type": intent.order_type,
        "quantity": _format_quantity(intent.quantity),
        "newClientOrderId": intent.client_order_id,
        "newOrderRespType": new_order_resp_type,
    }
    if intent.reduce_only:
        params["reduceOnly"] = "true"
    response = client.submit_testnet_strategy_order(**params)
    return parse_order_snapshot(dict(response.payload))


def submit_mainnet_strategy_single_run_order_intent(
    client: BinanceUsdmClient,
    intent: OrderIntent,
    *,
    new_order_resp_type: str = "RESULT",
) -> BinanceOrderSnapshot:
    params: dict[str, Any] = {
        "symbol": intent.symbol,
        "side": intent.side,
        "positionSide": intent.position_side,
        "type": intent.order_type,
        "quantity": _format_quantity(intent.quantity),
        "newClientOrderId": intent.client_order_id,
        "newOrderRespType": new_order_resp_type,
    }
    if intent.reduce_only:
        params["reduceOnly"] = "true"
    response = client.submit_mainnet_strategy_single_run_order(**params)
    return parse_order_snapshot(dict(response.payload))


def submit_mainnet_strategy_delta_order_intent(
    client: BinanceUsdmClient,
    intent: OrderIntent,
    *,
    new_order_resp_type: str = "RESULT",
) -> BinanceOrderSnapshot:
    params: dict[str, Any] = {
        "symbol": intent.symbol,
        "side": intent.side,
        "positionSide": intent.position_side,
        "type": intent.order_type,
        "quantity": _format_quantity(intent.quantity),
        "newClientOrderId": intent.client_order_id,
        "newOrderRespType": new_order_resp_type,
    }
    if intent.reduce_only:
        params["reduceOnly"] = "true"
    response = client.submit_mainnet_strategy_delta_order(**params)
    return parse_order_snapshot(dict(response.payload))


def recover_unknown_order_status(
    client: BinanceUsdmClient,
    *,
    symbol: str,
    client_order_id: str,
    user_events: Iterable[dict[str, Any]] | None = None,
) -> UnknownOrderRecoveryResult:
    matching_events = [
        event
        for event in (_parse_matching_events(user_events or [], symbol=symbol, client_order_id=client_order_id))
    ]
    if matching_events:
        event = matching_events[-1]
        return UnknownOrderRecoveryResult(
            symbol=symbol,
            client_order_id=client_order_id,
            status="resolved",
            source="user_data_stream",
            order_status=event.order_status,
            execution_type=event.execution_type,
            order_id=event.order_id,
            filled_quantity=event.cumulative_filled_quantity,
            raw=event.to_dict(),
        )
    try:
        snapshot = query_order_by_client_id(client, symbol=symbol, client_order_id=client_order_id)
    except Exception as exc:
        return UnknownOrderRecoveryResult(
            symbol=symbol,
            client_order_id=client_order_id,
            status="reconcile_required",
            source="rest_query_failed",
            blockers=[f"order_query_failed:{type(exc).__name__}:{exc}"],
        )
    return UnknownOrderRecoveryResult(
        symbol=symbol,
        client_order_id=client_order_id,
        status="resolved",
        source="rest_query",
        order_status=snapshot.status,
        order_id=snapshot.order_id,
        filled_quantity=snapshot.executed_quantity,
        raw=snapshot.to_dict(),
    )


def is_terminal_order_status(status: str) -> bool:
    return str(status or "").upper() in TERMINAL_ORDER_STATUSES


def _parse_matching_events(
    events: Iterable[dict[str, Any]],
    *,
    symbol: str,
    client_order_id: str,
) -> list[OrderTradeUpdateEvent]:
    parsed: list[OrderTradeUpdateEvent] = []
    for raw in events:
        try:
            event = parse_order_trade_update_event(dict(raw))
        except ValueError:
            continue
        if event.symbol == symbol and event.client_order_id == client_order_id:
            parsed.append(event)
    return sorted(parsed, key=lambda item: (item.transaction_time_ms, item.event_time_ms))


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _format_quantity(value: float) -> str:
    formatted = f"{float(value):.12f}".rstrip("0").rstrip(".")
    return formatted if formatted else "0"
