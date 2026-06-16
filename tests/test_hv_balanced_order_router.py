from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import hmac
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_USDM_MAINNET_BASE_URL,
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmClient,
    BinanceUsdmRequestError,
    BinanceUsdmResponse,
    BinanceUsdmUnknownExecutionStatus,
    LiveOrderSubmissionDisabled,
    MainnetStrategyOrderGuard as MainnetStrategyOrderGuardError,
    TestnetOrderSubmissionGuard as TestnetOrderSubmissionGuardError,
)
from enhengclaw.live_trading.execution_planner import (
    build_execution_plan,
    build_order_sizing_report,
    summarize_dust_residual_order_sizing,
    summarize_order_sizing_report,
)
from enhengclaw.live_trading.models import OrderIntent, RiskGateResult, TargetPortfolio, TargetPosition
from enhengclaw.live_trading.order_router import (
    cancel_order_by_client_id,
    parse_order_snapshot,
    parse_order_trade_update_event,
    query_order_by_client_id,
    recover_unknown_order_status,
    submit_mainnet_strategy_delta_order_intent,
    submit_mainnet_strategy_single_run_order_intent,
    submit_testnet_strategy_order_intent,
)


class HvBalancedOrderRouterTests(unittest.TestCase):
    def test_signed_params_use_hmac_sha256_and_recv_window(self) -> None:
        client = BinanceUsdmClient(api_secret="secret", api_key="key", time_ms_fn=lambda: 1234567890)

        signed = client.sign_params({"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.01"})

        payload = "symbol=BTCUSDT&side=BUY&type=MARKET&quantity=0.01&recvWindow=5000&timestamp=1234567890"
        expected = hmac.new(b"secret", payload.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(signed["signature"], expected)
        self.assertEqual(signed["recvWindow"], "5000")

    def test_real_order_submission_is_disabled_in_phase1(self) -> None:
        client = BinanceUsdmClient(api_secret="secret", api_key="key")

        with self.assertRaises(LiveOrderSubmissionDisabled):
            client.new_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.01")

    def test_manual_live_smoke_order_uses_explicit_signed_order_endpoint(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": None if request.data is None else request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return _FakeHttpResponse(
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": "manual-smoke",
                    "orderId": 123,
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "MARKET",
                    "positionSide": "BOTH",
                    "reduceOnly": False,
                    "origQty": "0.010",
                    "executedQty": "0.010",
                    "avgPrice": "100000",
                    "updateTime": 1770000000000,
                }
            )

        client = BinanceUsdmClient(
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        response = client.submit_manual_live_order_smoke(
            symbol="BTCUSDT",
            side="BUY",
            positionSide="BOTH",
            type="MARKET",
            quantity="0.010",
            newClientOrderId="manual-smoke",
        )

        self.assertEqual(response.payload["clientOrderId"], "manual-smoke")
        self.assertEqual(captured[0]["method"], "POST")
        self.assertTrue(captured[0]["url"].endswith("/fapi/v1/order"))
        self.assertIn("newClientOrderId=manual-smoke", captured[0]["data"])
        self.assertIn("signature=", captured[0]["data"])

    def test_testnet_strategy_order_guard_rejects_mainnet_base_url(self) -> None:
        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_MAINNET_BASE_URL,
            api_secret="secret",
            api_key="key",
        )

        with self.assertRaises(TestnetOrderSubmissionGuardError):
            client.submit_testnet_strategy_order(
                symbol="BTCUSDT",
                side="BUY",
                positionSide="BOTH",
                type="MARKET",
                quantity="0.001",
                newClientOrderId="hvbal-testnet",
            )

    def test_testnet_strategy_order_uses_testnet_signed_order_endpoint(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": None if request.data is None else request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return _FakeHttpResponse(
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": "hvbal-testnet",
                    "orderId": 456,
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "MARKET",
                    "positionSide": "BOTH",
                    "reduceOnly": False,
                    "origQty": "0.001",
                    "executedQty": "0.001",
                    "avgPrice": "100000",
                    "updateTime": 1770000000000,
                }
            )

        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_TESTNET_BASE_URL,
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        response = client.submit_testnet_strategy_order(
            symbol="BTCUSDT",
            side="BUY",
            positionSide="BOTH",
            type="MARKET",
            quantity="0.001",
            newClientOrderId="hvbal-testnet",
        )

        self.assertEqual(response.payload["clientOrderId"], "hvbal-testnet")
        self.assertEqual(captured[0]["method"], "POST")
        self.assertTrue(captured[0]["url"].startswith(BINANCE_USDM_TESTNET_BASE_URL))
        self.assertTrue(captured[0]["url"].endswith("/fapi/v1/order"))
        self.assertIn("newClientOrderId=hvbal-testnet", captured[0]["data"])
        self.assertIn("signature=", captured[0]["data"])

    def test_mainnet_strategy_single_run_guard_rejects_testnet_base_url(self) -> None:
        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_TESTNET_BASE_URL,
            api_secret="secret",
            api_key="key",
        )

        with self.assertRaises(MainnetStrategyOrderGuardError):
            client.submit_mainnet_strategy_single_run_order(
                symbol="BTCUSDT",
                side="BUY",
                positionSide="BOTH",
                type="MARKET",
                quantity="0.001",
                newClientOrderId="hvbal-mainnet",
            )

    def test_mainnet_strategy_single_run_order_uses_mainnet_signed_order_endpoint(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": None if request.data is None else request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return _FakeHttpResponse(
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": "hvbal-mainnet",
                    "orderId": 457,
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "MARKET",
                    "positionSide": "BOTH",
                    "reduceOnly": False,
                    "origQty": "0.001",
                    "executedQty": "0.001",
                    "avgPrice": "100000",
                    "updateTime": 1770000000000,
                }
            )

        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_MAINNET_BASE_URL,
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        response = client.submit_mainnet_strategy_single_run_order(
            symbol="BTCUSDT",
            side="BUY",
            positionSide="BOTH",
            type="MARKET",
            quantity="0.001",
            newClientOrderId="hvbal-mainnet",
        )

        self.assertEqual(response.payload["clientOrderId"], "hvbal-mainnet")
        self.assertEqual(captured[0]["method"], "POST")
        self.assertTrue(captured[0]["url"].startswith(BINANCE_USDM_MAINNET_BASE_URL))
        self.assertTrue(captured[0]["url"].endswith("/fapi/v1/order"))
        self.assertIn("newClientOrderId=hvbal-mainnet", captured[0]["data"])
        self.assertIn("signature=", captured[0]["data"])

    def test_mainnet_strategy_delta_guard_rejects_testnet_base_url(self) -> None:
        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_TESTNET_BASE_URL,
            api_secret="secret",
            api_key="key",
        )

        with self.assertRaises(MainnetStrategyOrderGuardError):
            client.submit_mainnet_strategy_delta_order(
                symbol="BTCUSDT",
                side="BUY",
                positionSide="BOTH",
                type="MARKET",
                quantity="0.001",
                newClientOrderId="hvbal-delta",
            )

    def test_mainnet_strategy_delta_intent_uses_mainnet_signed_order_endpoint(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": None if request.data is None else request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return _FakeHttpResponse(
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": "hvbal-delta",
                    "orderId": 458,
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "MARKET",
                    "positionSide": "BOTH",
                    "reduceOnly": False,
                    "origQty": "0.001",
                    "executedQty": "0.001",
                    "avgPrice": "100000",
                    "updateTime": 1770000000000,
                }
            )

        client = BinanceUsdmClient(
            base_url=BINANCE_USDM_MAINNET_BASE_URL,
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )
        intent = OrderIntent(
            intent_id="intent-delta",
            portfolio_id="portfolio",
            symbol="BTCUSDT",
            side="BUY",
            position_side="BOTH",
            order_type="MARKET",
            quantity=0.001,
            reduce_only=False,
            target_position_amt=0.002,
            current_position_amt=0.001,
            delta_position_amt=0.001,
            max_slippage_bps=20.0,
            client_order_id="hvbal-delta",
        )

        snapshot = submit_mainnet_strategy_delta_order_intent(client, intent)

        self.assertEqual(snapshot.client_order_id, "hvbal-delta")
        self.assertEqual(captured[0]["method"], "POST")
        self.assertTrue(captured[0]["url"].startswith(BINANCE_USDM_MAINNET_BASE_URL))
        self.assertTrue(captured[0]["url"].endswith("/fapi/v1/order"))
        self.assertIn("newClientOrderId=hvbal-delta", captured[0]["data"])
        self.assertIn("signature=", captured[0]["data"])

    def test_query_order_requires_order_id_or_client_order_id(self) -> None:
        client = BinanceUsdmClient(api_secret="secret", api_key="key")

        with self.assertRaises(ValueError):
            client.query_order(symbol="BTCUSDT")

    def test_query_and_cancel_order_use_signed_usdm_order_endpoint(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": None if request.data is None else request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return _FakeHttpResponse(
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": "hvbal-test",
                    "orderId": 123,
                    "status": "NEW",
                    "side": "BUY",
                    "type": "MARKET",
                    "positionSide": "BOTH",
                    "reduceOnly": True,
                    "origQty": "0.010",
                    "executedQty": "0",
                    "avgPrice": "0",
                    "updateTime": 1770000000000,
                }
            )

        client = BinanceUsdmClient(
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        query = client.query_order(symbol="BTCUSDT", orig_client_order_id="hvbal-test")
        cancel = client.cancel_order(symbol="BTCUSDT", orig_client_order_id="hvbal-test")

        self.assertEqual(query.payload["clientOrderId"], "hvbal-test")
        self.assertEqual(cancel.payload["clientOrderId"], "hvbal-test")
        self.assertEqual(captured[0]["method"], "GET")
        query_params = parse_qs(urlparse(captured[0]["url"]).query)
        self.assertEqual(query_params["symbol"], ["BTCUSDT"])
        self.assertEqual(query_params["origClientOrderId"], ["hvbal-test"])
        self.assertIn("signature", query_params)
        self.assertEqual(captured[1]["method"], "DELETE")
        self.assertIn("origClientOrderId=hvbal-test", captured[1]["data"])
        self.assertIn("signature=", captured[1]["data"])

    def test_503_unknown_execution_status_raises_typed_exception(self) -> None:
        def opener(request, timeout):
            raise HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                {},
                BytesIO(b'{"code":-1000,"msg":"Unknown error, please check your request or try again later."}'),
            )

        client = BinanceUsdmClient(
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        with self.assertRaises(BinanceUsdmUnknownExecutionStatus):
            client.new_order_test(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.01")

    def test_non_unknown_binance_http_error_preserves_sanitized_detail(self) -> None:
        def opener(request, timeout):
            raise HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                BytesIO(b'{"code":-1022,"msg":"Signature for this request is not valid."}'),
            )

        client = BinanceUsdmClient(
            api_secret="secret",
            api_key="key",
            time_ms_fn=lambda: 1234567890,
            urlopen_fn=opener,
        )

        with self.assertRaises(BinanceUsdmRequestError) as context:
            client.account_information_v3()
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("-1022", str(context.exception))
        self.assertNotIn("signature=", str(context.exception))

    def test_order_snapshot_parser_normalizes_rest_payload(self) -> None:
        snapshot = parse_order_snapshot(
            {
                "symbol": "BTCUSDT",
                "clientOrderId": "hvbal-test",
                "orderId": 123,
                "status": "FILLED",
                "side": "SELL",
                "type": "MARKET",
                "positionSide": "BOTH",
                "reduceOnly": True,
                "origQty": "0.010",
                "executedQty": "0.010",
                "avgPrice": "100000",
                "updateTime": 1770000000000,
            }
        )

        self.assertEqual(snapshot.symbol, "BTCUSDT")
        self.assertEqual(snapshot.client_order_id, "hvbal-test")
        self.assertTrue(snapshot.terminal)
        self.assertAlmostEqual(snapshot.executed_quantity, 0.01)

    def test_order_trade_update_parser_normalizes_user_stream_event(self) -> None:
        event = parse_order_trade_update_event(_order_trade_update_event(status="FILLED", execution_type="TRADE"))

        self.assertEqual(event.event_type, "ORDER_TRADE_UPDATE")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.client_order_id, "hvbal-test")
        self.assertEqual(event.order_status, "FILLED")
        self.assertEqual(event.execution_type, "TRADE")
        self.assertTrue(event.reduce_only)
        self.assertTrue(event.terminal)
        self.assertAlmostEqual(event.cumulative_filled_quantity, 0.01)

    def test_recover_unknown_status_prefers_user_event_over_rest_query(self) -> None:
        client = _FakeOrderClient()

        result = recover_unknown_order_status(
            client,
            symbol="BTCUSDT",
            client_order_id="hvbal-test",
            user_events=[
                {"e": "ACCOUNT_UPDATE"},
                _order_trade_update_event(status="FILLED", execution_type="TRADE"),
            ],
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.source, "user_data_stream")
        self.assertEqual(result.order_status, "FILLED")
        self.assertEqual(client.query_count, 0)
        self.assertEqual(result.next_action, "do_not_resubmit")

    def test_recover_unknown_status_falls_back_to_rest_query(self) -> None:
        client = _FakeOrderClient()

        result = recover_unknown_order_status(client, symbol="BTCUSDT", client_order_id="hvbal-test")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.source, "rest_query")
        self.assertEqual(result.order_status, "NEW")
        self.assertEqual(client.query_count, 1)
        self.assertEqual(result.next_action, "do_not_resubmit")

    def test_recover_unknown_status_requires_reconcile_when_query_fails(self) -> None:
        client = _FakeOrderClient(raise_on_query=True)

        result = recover_unknown_order_status(client, symbol="BTCUSDT", client_order_id="hvbal-test")

        self.assertEqual(result.status, "reconcile_required")
        self.assertEqual(result.source, "rest_query_failed")
        self.assertTrue(result.blockers[0].startswith("order_query_failed:RuntimeError"))
        self.assertEqual(result.next_action, "do_not_resubmit")

    def test_query_and_cancel_helpers_parse_snapshots(self) -> None:
        client = _FakeOrderClient()

        queried = query_order_by_client_id(client, symbol="BTCUSDT", client_order_id="hvbal-test")
        canceled = cancel_order_by_client_id(client, symbol="BTCUSDT", client_order_id="hvbal-test")

        self.assertEqual(queried.status, "NEW")
        self.assertEqual(canceled.status, "CANCELED")
        self.assertEqual(client.query_count, 1)
        self.assertEqual(client.cancel_count, 1)

    def test_submit_testnet_strategy_order_intent_formats_and_parses_market_order(self) -> None:
        client = _FakeSubmitTestnetClient()
        intent = OrderIntent(
            intent_id="intent-1",
            portfolio_id="portfolio-1",
            symbol="BTCUSDT",
            side="BUY",
            position_side="BOTH",
            order_type="MARKET",
            quantity=0.001,
            reduce_only=False,
            target_position_amt=0.001,
            current_position_amt=0.0,
            delta_position_amt=0.001,
            max_slippage_bps=20.0,
            client_order_id="hvbal-te-submit",
        )

        snapshot = submit_testnet_strategy_order_intent(client, intent)

        self.assertEqual(snapshot.status, "FILLED")
        self.assertEqual(snapshot.client_order_id, "hvbal-te-submit")
        self.assertEqual(client.submitted[0]["quantity"], "0.001")
        self.assertEqual(client.submitted[0]["newOrderRespType"], "RESULT")
        self.assertNotIn("reduceOnly", client.submitted[0])

    def test_submit_mainnet_strategy_order_intent_formats_and_parses_market_order(self) -> None:
        client = _FakeSubmitMainnetClient()
        intent = OrderIntent(
            intent_id="intent-1",
            portfolio_id="portfolio-1",
            symbol="BTCUSDT",
            side="BUY",
            position_side="BOTH",
            order_type="MARKET",
            quantity=0.001,
            reduce_only=False,
            target_position_amt=0.001,
            current_position_amt=0.0,
            delta_position_amt=0.001,
            max_slippage_bps=20.0,
            client_order_id="hvbal-li-submit",
        )

        snapshot = submit_mainnet_strategy_single_run_order_intent(client, intent)

        self.assertEqual(snapshot.status, "FILLED")
        self.assertEqual(snapshot.client_order_id, "hvbal-li-submit")
        self.assertEqual(client.submitted[0]["quantity"], "0.001")
        self.assertEqual(client.submitted[0]["newOrderRespType"], "RESULT")
        self.assertNotIn("reduceOnly", client.submitted[0])

    def test_execution_planner_outputs_intents_without_submission(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="plan_only",
                passed=True,
                decision="allow_plan",
                blockers=[],
            ),
            mode="plan_only",
            current_positions={},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual(len(plan.intents), 1)
        self.assertEqual(plan.intents[0].side, "BUY")
        self.assertAlmostEqual(plan.intents[0].quantity, 0.1)
        self.assertTrue(plan.intents[0].client_order_id.startswith("hvbal-pl-"))

    def test_execution_planner_closes_stale_paper_position_not_in_target_portfolio(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="paper",
                passed=True,
                decision="allow_plan",
                blockers=[],
            ),
            mode="paper",
            current_positions={"ETHUSDT": -0.2},
            mark_prices={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
            symbol_filters={
                "BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
                "ETHUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
            },
        )

        self.assertEqual(plan.status, "ok")
        by_symbol = {intent.symbol: intent for intent in plan.intents}
        self.assertEqual(by_symbol["ETHUSDT"].side, "BUY")
        self.assertTrue(by_symbol["ETHUSDT"].reduce_only)
        self.assertAlmostEqual(by_symbol["ETHUSDT"].target_position_amt, 0.0)
        self.assertAlmostEqual(by_symbol["ETHUSDT"].quantity, 0.2)
        self.assertEqual(by_symbol["ETHUSDT"].execution_phase, "reduce_first")
        self.assertEqual(by_symbol["ETHUSDT"].delta_classification, "exit_stale_symbol")

    def test_rebalance_phase_classifier_defers_entries_until_reduce_first_reconciles(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="live",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="live",
            current_positions={"ETHUSDT": -0.2},
            mark_prices={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
            symbol_filters={
                "BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
                "ETHUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
            },
            allow_live_order_submission=True,
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual(plan.active_execution_phase, "reduce_first")
        self.assertEqual(plan.deferred_phase_counts, {"entry_second": 1})
        self.assertEqual([intent.symbol for intent in plan.intents], ["ETHUSDT"])
        self.assertTrue(plan.intents[0].reduce_only)
        self.assertEqual(plan.intents[0].execution_phase, "reduce_first")

    def test_rebalance_phase_classifier_flip_flattens_before_reverse_entry(self) -> None:
        plan = build_execution_plan(
            _portfolio(target_weight=-0.1, target_notional_usdt=10.0),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="live",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="live",
            current_positions={"BTCUSDT": 0.2},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            allow_live_order_submission=True,
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual(plan.active_execution_phase, "reduce_first")
        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertEqual(intent.delta_classification, "flip_position")
        self.assertEqual(intent.execution_phase, "reduce_first")
        self.assertTrue(intent.reduce_only)
        self.assertEqual(intent.side, "SELL")
        self.assertAlmostEqual(intent.quantity, 0.2)
        self.assertAlmostEqual(intent.target_position_amt, 0.0)
        self.assertAlmostEqual(intent.final_target_position_amt, -0.1)
        self.assertTrue(intent.second_phase_required)

    def test_rebalance_phase_classifier_reduces_same_side_before_increase(self) -> None:
        plan = build_execution_plan(
            _portfolio(target_weight=0.1, target_notional_usdt=10.0),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="live",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="live",
            current_positions={"BTCUSDT": 0.2},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            allow_live_order_submission=True,
        )

        self.assertEqual(plan.active_execution_phase, "reduce_first")
        intent = plan.intents[0]
        self.assertEqual(intent.delta_classification, "reduce_same_side")
        self.assertEqual(intent.execution_phase, "reduce_first")
        self.assertTrue(intent.reduce_only)
        self.assertEqual(intent.side, "SELL")
        self.assertAlmostEqual(intent.quantity, 0.1)

    def test_rebalance_phase_classifier_entries_when_no_reduce_first_exists(self) -> None:
        plan = build_execution_plan(
            _portfolio(target_weight=0.1, target_notional_usdt=10.0),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="live",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="live",
            current_positions={"BTCUSDT": 0.05},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            allow_live_order_submission=True,
        )

        self.assertEqual(plan.active_execution_phase, "entry_second")
        intent = plan.intents[0]
        self.assertEqual(intent.delta_classification, "increase_same_side")
        self.assertEqual(intent.execution_phase, "entry_second")
        self.assertFalse(intent.reduce_only)
        self.assertAlmostEqual(intent.quantity, 0.05)

    def test_execution_deadband_noops_small_same_side_five_to_ten_dollar_rebalances(self) -> None:
        deadband = {
            "enabled": True,
            "delta_classifications": "increase_same_side,reduce_same_side",
            "same_side_min_delta_notional_usdt": 20.0,
            "min_delta_notional_multiplier_of_min_executable": 3.0,
        }
        portfolio = _portfolio(target_weight=0.1, target_notional_usdt=10.0)
        filters = {"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}}

        cases = [
            ("five_dollar_same_side_increase", 0.05, "increase_same_side", 5.0),
            ("ten_dollar_same_side_reduce", 0.2, "reduce_same_side", 10.0),
        ]
        for label, current_amt, original_classification, notional in cases:
            with self.subTest(label=label):
                report = build_order_sizing_report(
                    portfolio,
                    mode="live",
                    current_positions={"BTCUSDT": current_amt},
                    mark_prices={"BTCUSDT": 100.0},
                    symbol_filters=filters,
                    execution_deadband=deadband,
                )
                row = report.iloc[0]
                self.assertEqual(row["delta_classification"], "rebalance_deadband")
                self.assertEqual(row["execution_phase"], "deadband_noop")
                self.assertEqual(row["deadband_original_delta_classification"], original_classification)
                self.assertEqual(row["deadband_original_execution_phase"], "entry_second" if current_amt < 0.1 else "reduce_first")
                self.assertTrue(bool(row["deadband_applied"]))
                self.assertTrue(bool(row["no_order_required"]))
                self.assertFalse(bool(row["executable"]))
                self.assertAlmostEqual(float(row["deadband_candidate_notional_usdt"]), notional)
                self.assertAlmostEqual(float(row["deadband_threshold_notional_usdt"]), 20.0)
                self.assertAlmostEqual(float(row["target_position_amt"]), 0.1)
                self.assertAlmostEqual(float(row["final_delta_position_amt"]), 0.1 - current_amt)
                self.assertAlmostEqual(float(row["order_target_position_amt"]), current_amt)
                self.assertAlmostEqual(float(row["order_delta_position_amt"]), 0.0)
                self.assertAlmostEqual(float(row["rounded_notional_usdt"]), 0.0)

                plan = build_execution_plan(
                    portfolio,
                    RiskGateResult(
                        risk_gate_id="rg1",
                        portfolio_id="p1",
                        mode="live",
                        passed=True,
                        decision="allow",
                        blockers=[],
                    ),
                    mode="live",
                    current_positions={"BTCUSDT": current_amt},
                    mark_prices={"BTCUSDT": 100.0},
                    symbol_filters=filters,
                    execution_deadband=deadband,
                    allow_live_order_submission=True,
                )
                self.assertEqual(plan.status, "ok")
                self.assertEqual(plan.active_execution_phase, "deadband_noop")
                self.assertEqual(plan.phase_counts, {"deadband_noop": 1})
                self.assertEqual(plan.intents, [])

    def test_execution_deadband_does_not_noop_flip_or_exit(self) -> None:
        deadband = {
            "enabled": True,
            "delta_classifications": "increase_same_side,reduce_same_side",
            "same_side_min_delta_notional_usdt": 1000.0,
        }
        risk_gate = RiskGateResult(
            risk_gate_id="rg1",
            portfolio_id="p1",
            mode="live",
            passed=True,
            decision="allow",
            blockers=[],
        )

        flip_plan = build_execution_plan(
            _portfolio(target_weight=-0.1, target_notional_usdt=10.0),
            risk_gate,
            mode="live",
            current_positions={"BTCUSDT": 0.2},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            execution_deadband=deadband,
            allow_live_order_submission=True,
        )
        self.assertEqual(flip_plan.active_execution_phase, "reduce_first")
        self.assertEqual(len(flip_plan.intents), 1)
        self.assertEqual(flip_plan.intents[0].delta_classification, "flip_position")
        self.assertEqual(flip_plan.intents[0].execution_phase, "reduce_first")
        self.assertTrue(flip_plan.intents[0].reduce_only)
        self.assertAlmostEqual(flip_plan.intents[0].quantity, 0.2)

        exit_plan = build_execution_plan(
            _portfolio(),
            risk_gate,
            mode="live",
            current_positions={"ETHUSDT": -0.2},
            mark_prices={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
            symbol_filters={
                "BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
                "ETHUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0},
            },
            execution_deadband=deadband,
            allow_live_order_submission=True,
        )
        self.assertEqual(exit_plan.active_execution_phase, "reduce_first")
        self.assertEqual(len(exit_plan.intents), 1)
        self.assertEqual(exit_plan.intents[0].symbol, "ETHUSDT")
        self.assertEqual(exit_plan.intents[0].delta_classification, "exit_stale_symbol")
        self.assertEqual(exit_plan.intents[0].execution_phase, "reduce_first")
        self.assertTrue(exit_plan.intents[0].reduce_only)
        self.assertAlmostEqual(exit_plan.intents[0].quantity, 0.2)

    def test_execution_planner_blocks_testnet_submission_in_phase1(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="testnet",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="testnet",
            mark_prices={"BTCUSDT": 100.0},
        )

        self.assertEqual(plan.status, "blocked")
        self.assertIn("testnet_order_submission_not_implemented_in_phase1", plan.blockers)

    def test_execution_planner_allows_testnet_only_when_runner_sets_explicit_flag(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="testnet",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="testnet",
            current_positions={},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            allow_testnet_order_submission=True,
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual(len(plan.intents), 1)
        self.assertTrue(plan.intents[0].client_order_id.startswith("hvbal-te-"))

    def test_execution_planner_allows_live_only_when_runner_sets_explicit_flag(self) -> None:
        plan = build_execution_plan(
            _portfolio(),
            RiskGateResult(
                risk_gate_id="rg1",
                portfolio_id="p1",
                mode="live",
                passed=True,
                decision="allow",
                blockers=[],
            ),
            mode="live",
            current_positions={},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
            allow_live_order_submission=True,
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual(len(plan.intents), 1)
        self.assertTrue(plan.intents[0].client_order_id.startswith("hvbal-li-"))

    def test_order_sizing_report_explains_min_executable_capital(self) -> None:
        portfolio = _portfolio(
            allocated_capital_usdt=100.0,
            target_weight=1.0 / 6.0,
            target_notional_usdt=100.0 / 6.0,
        )

        report = build_order_sizing_report(
            portfolio,
            mode="paper",
            mark_prices={"BTCUSDT": 78_000.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 50.0}},
        )
        summary = summarize_order_sizing_report(report, allocated_capital_usdt=portfolio.allocated_capital_usdt)

        self.assertEqual(len(report), 1)
        row = report.iloc[0]
        self.assertEqual(row["symbol"], "BTCUSDT")
        self.assertEqual(row["blockers"], "notional_below_min:BTCUSDT;quantity_below_min:BTCUSDT")
        self.assertAlmostEqual(float(row["target_notional_usdt"]), 100.0 / 6.0)
        self.assertAlmostEqual(float(row["min_executable_notional_usdt"]), 78.0)
        self.assertAlmostEqual(float(row["min_allocated_capital_usdt_for_target_weight"]), 468.0)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["non_executable_target_symbols"], ["BTCUSDT"])
        self.assertAlmostEqual(summary["min_allocated_capital_usdt_for_all_targets"], 468.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_needed_usdt"], 368.0)

    def test_dust_residual_summary_tolerates_only_current_position_residuals(self) -> None:
        portfolio = _portfolio(target_weight=0.1, target_notional_usdt=10.0)
        residual_report = build_order_sizing_report(
            portfolio,
            mode="plan_only",
            current_positions={"BTCUSDT": 0.09995},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 5.0}},
        )
        fresh_entry_report = build_order_sizing_report(
            portfolio,
            mode="plan_only",
            current_positions={},
            mark_prices={"BTCUSDT": 100.0},
            symbol_filters={"BTCUSDT": {"step_size": "0.001", "min_qty": 0.001, "min_notional": 50.0}},
        )

        residual_summary = summarize_dust_residual_order_sizing(residual_report)
        fresh_entry_summary = summarize_dust_residual_order_sizing(fresh_entry_report)

        self.assertTrue(residual_summary["is_dust_residual_only"])
        self.assertEqual(residual_summary["dust_symbols"], ["BTCUSDT"])
        self.assertEqual(residual_report.iloc[0]["execution_phase"], "dust_noop")
        self.assertEqual(residual_report.iloc[0]["delta_classification"], "dust_residual")
        self.assertFalse(fresh_entry_summary["is_dust_residual_only"])
        self.assertEqual(fresh_entry_report.iloc[0]["delta_classification"], "new_entry")
        self.assertIn("notional_below_min:BTCUSDT", fresh_entry_summary["hard_blockers"])


def _portfolio(
    *,
    allocated_capital_usdt: float = 100.0,
    target_weight: float = 0.1,
    target_notional_usdt: float = 10.0,
) -> TargetPortfolio:
    return TargetPortfolio(
        portfolio_id="p1",
        decision_id="d1",
        strategy_label="fixture",
        allocated_capital_usdt=allocated_capital_usdt,
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=abs(target_weight),
        target_net_weight=target_weight,
        status="ok",
        positions=[
            TargetPosition(
                subject="BTC",
                usdm_symbol="BTCUSDT",
                side="long" if target_weight >= 0.0 else "short",
                score=1.0,
                target_weight=target_weight,
                target_notional_usdt=target_notional_usdt,
                previous_target_weight=0.0,
                delta_target_weight=target_weight,
                raw_short_multiplier=1.0,
                portfolio_drawdown_multiplier=1.0,
                selection_reason="top_long" if target_weight >= 0.0 else "bottom_short",
            )
        ],
    )


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.status = 200
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        import json

        return json.dumps(self.payload).encode("utf-8")


class _FakeOrderClient:
    def __init__(self, *, raise_on_query: bool = False) -> None:
        self.raise_on_query = raise_on_query
        self.query_count = 0
        self.cancel_count = 0

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        self.query_count += 1
        if self.raise_on_query:
            raise RuntimeError("query unavailable")
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 123,
                "status": "NEW",
                "side": "BUY",
                "type": "MARKET",
                "positionSide": "BOTH",
                "reduceOnly": True,
                "origQty": "0.010",
                "executedQty": "0",
                "avgPrice": "0",
                "updateTime": 1770000000000,
            },
        )

    def cancel_order(self, *, symbol: str, orig_client_order_id: str):
        self.cancel_count += 1
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 123,
                "status": "CANCELED",
                "side": "BUY",
                "type": "MARKET",
                "positionSide": "BOTH",
                "reduceOnly": True,
                "origQty": "0.010",
                "executedQty": "0",
                "avgPrice": "0",
                "updateTime": 1770000000000,
            },
        )


class _FakeSubmitTestnetClient:
    def __init__(self) -> None:
        self.submitted: list[dict] = []

    def submit_testnet_strategy_order(self, **params):
        self.submitted.append(dict(params))
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": params["symbol"],
                "clientOrderId": params["newClientOrderId"],
                "orderId": 456,
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100000",
                "updateTime": 1770000000000,
            },
        )


class _FakeSubmitMainnetClient:
    def __init__(self) -> None:
        self.submitted: list[dict] = []

    def submit_mainnet_strategy_single_run_order(self, **params):
        self.submitted.append(dict(params))
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": params["symbol"],
                "clientOrderId": params["newClientOrderId"],
                "orderId": 457,
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100000",
                "updateTime": 1770000000000,
            },
        )


def _order_trade_update_event(*, status: str, execution_type: str) -> dict:
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1770000000001,
        "T": 1770000000000,
        "o": {
            "s": "BTCUSDT",
            "c": "hvbal-test",
            "S": "BUY",
            "o": "MARKET",
            "f": "GTC",
            "q": "0.010",
            "p": "0",
            "ap": "100000",
            "x": execution_type,
            "X": status,
            "i": 123,
            "l": "0.010",
            "z": "0.010",
            "L": "100000",
            "N": "USDT",
            "n": "0.04",
            "T": 1770000000000,
            "t": 456,
            "m": False,
            "R": True,
            "ps": "BOTH",
            "rp": "0",
            "er": "0",
        },
    }
