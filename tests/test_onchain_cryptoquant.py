from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enhengclaw.quant_research.onchain_cryptoquant import (
    _resolve_cryptoquant_api_token,
    run_cryptoquant_reflexivity_sync,
    run_cryptoquant_stablecoin_sync,
)


def _identity_evidence(payload: dict, **kwargs) -> dict:  # noqa: ARG001
    return dict(payload)


def _day_from_params(params: dict[str, object]) -> str:
    date_text = str(params["to"])
    return f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"


def _fake_cryptoquant_get_json(*, access_token: str, path: str, params: dict[str, object]) -> dict[str, object]:
    assert access_token == "test-token"
    day = _day_from_params(params)
    if path == "/stablecoin/network-data/supply":
        token = str(params["token"])
        supply_total = 100.0 if token == "usdt_eth" else 200.0
        return {
            "status": {"code": 200, "message": "success"},
            "result": {
                "window": "day",
                "data": [
                    {
                        "date": day,
                        "supply_total": supply_total,
                        "supply_circulating": supply_total - 10.0,
                        "supply_minted": 5.0,
                        "supply_burned": 1.0,
                        "supply_issued": 4.0,
                        "supply_redeemed": 0.5,
                    }
                ],
            },
        }
    if path == "/stablecoin/network-data/tokens-transferred":
        return {
            "status": {"code": 200, "message": "success"},
            "result": {"window": "day", "data": [{"date": day, "tokens_transferred_total": 50.0, "tokens_transferred_mean": 2.5}]},
        }
    if path == "/stablecoin/network-data/addresses-count":
        return {
            "status": {"code": 200, "message": "success"},
            "result": {
                "window": "day",
                "data": [
                    {
                        "date": day,
                        "addresses_active_count": 10,
                        "addresses_active_sender_count": 6,
                        "addresses_active_receiver_count": 7,
                        "addresses_active_sender_percent": 0.6,
                        "addresses_active_receiver_percent": 0.7,
                    }
                ],
            },
        }
    if path.startswith("/stablecoin/exchange-flows/"):
        exchange = str(params["exchange"])
        payload_row: dict[str, object] = {"date": day}
        if path.endswith("/reserve"):
            payload_row["reserve"] = 25.0 if exchange == "spot_exchange" else 35.0
        elif path.endswith("/inflow"):
            payload_row.update({"inflow_total": 11.0, "inflow_top10": 7.0, "inflow_mean": 1.1})
        elif path.endswith("/outflow"):
            payload_row.update({"outflow_total": 9.0, "outflow_top10": 5.0, "outflow_mean": 0.9})
        elif path.endswith("/netflow"):
            payload_row["netflow_total"] = 2.0
        elif path.endswith("/transactions-count"):
            payload_row.update({"transactions_count_inflow": 4, "transactions_count_outflow": 3})
        elif path.endswith("/addresses-count"):
            payload_row.update({"addresses_count_inflow": 2, "addresses_count_outflow": 2})
        else:
            raise AssertionError(f"unexpected path {path}")
        return {"status": {"code": 200, "message": "success"}, "result": {"window": "day", "data": [payload_row]}}
    if path.startswith("/btc/exchange-flows/") or path.startswith("/eth/exchange-flows/"):
        payload_row: dict[str, object] = {"date": day}
        if path.endswith("/reserve"):
            payload_row.update({"reserve": 100.0, "reserve_usd": 1000.0})
        elif path.endswith("/inflow"):
            payload_row.update({"inflow_total": 13.0, "inflow_top10": 8.0, "inflow_mean": 1.3})
        elif path.endswith("/outflow"):
            payload_row.update({"outflow_total": 8.0, "outflow_top10": 4.0, "outflow_mean": 0.8})
        elif path.endswith("/netflow"):
            payload_row["netflow_total"] = 5.0
        elif path.endswith("/transactions-count"):
            payload_row.update({"transactions_count_inflow": 5, "transactions_count_outflow": 4})
        elif path.endswith("/addresses-count"):
            payload_row.update({"addresses_count_inflow": 3, "addresses_count_outflow": 2})
        else:
            raise AssertionError(f"unexpected path {path}")
        return {"status": {"code": 200, "message": "success"}, "result": {"window": "day", "data": [payload_row]}}
    if path.startswith("/btc/market-indicator/"):
        payload_row: dict[str, object] = {"date": day}
        if path.endswith("/sopr"):
            payload_row.update({"sopr": 1.02, "a_sopr": 1.01, "sth_sopr": 0.98, "lth_sopr": 1.04})
        elif path.endswith("/sopr-ratio"):
            payload_row["sopr_ratio"] = 1.06
        elif path.endswith("/stablecoin-supply-ratio"):
            payload_row["stablecoin_supply_ratio"] = 12.5
        elif path.endswith("/realized-price"):
            payload_row["realized_price"] = 42000.0
        else:
            raise AssertionError(f"unexpected path {path}")
        return {"status": {"code": 200, "message": "success"}, "result": {"window": "day", "data": [payload_row]}}
    raise AssertionError(f"unexpected path {path}")


class CryptoQuantOnchainTests(unittest.TestCase):
    def test_resolve_cryptoquant_api_token_prefers_process_name(self) -> None:
        self.assertEqual(_resolve_cryptoquant_api_token(base_env={"Crypto_Quant_API": "abc"}), "abc")

    def test_resolve_cryptoquant_api_token_accepts_alias(self) -> None:
        self.assertEqual(_resolve_cryptoquant_api_token(base_env={"CRYPTOQUANT_API_KEY": "alias"}), "alias")

    def test_run_cryptoquant_stablecoin_sync_writes_supply_and_exchange_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                patch("enhengclaw.quant_research.onchain_cryptoquant._resolve_cryptoquant_api_token", return_value="test-token"),
                patch("enhengclaw.quant_research.onchain_cryptoquant._cryptoquant_get_json", side_effect=_fake_cryptoquant_get_json),
                patch("enhengclaw.quant_research.onchain_cryptoquant.with_evidence_metadata", side_effect=_identity_evidence),
            ):
                summary = run_cryptoquant_stablecoin_sync(
                    external_root=root,
                    token_ids=["usdt_eth"],
                    exchanges=["spot_exchange"],
                    lookback_days=2,
                )
            self.assertTrue(summary["success"])
            supply_path = root / "stablecoin_supply_daily.csv"
            flow_path = root / "stablecoin_exchange_flows_daily.csv"
            self.assertTrue(supply_path.exists())
            self.assertTrue(flow_path.exists())
            with supply_path.open("r", encoding="utf-8", newline="") as handle:
                supply_rows = list(csv.DictReader(handle))
            with flow_path.open("r", encoding="utf-8", newline="") as handle:
                flow_rows = list(csv.DictReader(handle))
        self.assertEqual(len(supply_rows), 1)
        self.assertEqual(supply_rows[0]["token_id"], "usdt_eth")
        self.assertEqual(supply_rows[0]["supply_total"], "100.0")
        self.assertEqual(len(flow_rows), 1)
        self.assertEqual(flow_rows[0]["exchange"], "spot_exchange")
        self.assertEqual(flow_rows[0]["netflow_total"], "2.0")

    def test_run_cryptoquant_reflexivity_sync_writes_exchange_and_market_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                patch("enhengclaw.quant_research.onchain_cryptoquant._resolve_cryptoquant_api_token", return_value="test-token"),
                patch("enhengclaw.quant_research.onchain_cryptoquant._cryptoquant_get_json", side_effect=_fake_cryptoquant_get_json),
                patch("enhengclaw.quant_research.onchain_cryptoquant.with_evidence_metadata", side_effect=_identity_evidence),
            ):
                summary = run_cryptoquant_reflexivity_sync(
                    external_root=root,
                    asset_ids=["btc", "eth"],
                    exchanges=["all_exchange"],
                    lookback_days=2,
                )
            self.assertTrue(summary["success"])
            exchange_path = root / "reflexivity_exchange_flows_daily.csv"
            market_path = root / "reflexivity_market_indicators_daily.csv"
            with exchange_path.open("r", encoding="utf-8", newline="") as handle:
                exchange_rows = list(csv.DictReader(handle))
            with market_path.open("r", encoding="utf-8", newline="") as handle:
                market_rows = list(csv.DictReader(handle))
        self.assertEqual(len(exchange_rows), 2)
        self.assertEqual({row["asset_id"] for row in exchange_rows}, {"btc", "eth"})
        self.assertEqual(len(market_rows), 1)
        self.assertEqual(market_rows[0]["asset_id"], "btc")
        self.assertEqual(market_rows[0]["sopr_ratio"], "1.06")


if __name__ == "__main__":
    unittest.main()
