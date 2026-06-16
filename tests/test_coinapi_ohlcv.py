from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import gzip
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.market_data import load_ohlcv_frame
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input
from scripts.market_data.coinapi_ohlcv import (
    _align_time_ms_to_interval,
    exchange_mapping_path,
    refresh_symbol_catalog,
    resolve_external_history_root,
    symbol_catalog_path,
    sync_coinapi_ohlcv,
)


class CoinApiOhlcvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coinapi-ohlcv-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.external_root = self.temp_dir / "external" / "coinapi"
        self.quant_input_root = self.temp_dir / "artifacts" / "quant_research" / "_quant_inputs"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)

    def test_refresh_symbol_catalog_writes_coinapi_mapping(self) -> None:
        catalog = refresh_symbol_catalog(
            external_root=self.external_root,
            exchange_id="BINANCE",
            quote_asset="USDT",
            http_get_json_fn=self._fake_http,
        )

        self.assertEqual(catalog["provider"], "coinapi")
        self.assertTrue(symbol_catalog_path(external_root=self.external_root).exists())
        self.assertTrue(exchange_mapping_path(external_root=self.external_root).exists())
        spot_symbols = catalog["markets"]["spot"]["symbols"]
        self.assertIn("ETHUSDT", spot_symbols)
        self.assertIn("SUIUSDT", spot_symbols)
        self.assertNotIn("BTCFDUSD", spot_symbols)
        self.assertEqual(spot_symbols["ETHUSDT"]["coinapi_symbol_id"], "BINANCE_SPOT_ETH_USDT")
        mapping_payload = json.loads(exchange_mapping_path(external_root=self.external_root).read_text(encoding="utf-8"))
        self.assertEqual(mapping_payload["canonical_to_coinapi_symbol_id"]["ETHUSDT"], "BINANCE_SPOT_ETH_USDT")
        self.assertEqual(mapping_payload["coinapi_symbol_id_to_exchange_symbol"]["BINANCE_SPOT_ETH_USDT"], "ETHUSDT")

    def test_sync_coinapi_ohlcv_writes_quant_compatible_store(self) -> None:
        self._write_quant_input(
            {
                "as_of": "2026-04-21",
                "candidates": [
                    pit_candidate("ETH", 2, listing_age_days_as_of=1000),
                ],
            }
        )

        summary = sync_coinapi_ohlcv(
            external_root=self.external_root,
            symbols=None,
            intervals=("1h", "4h", "1d"),
            mode="bootstrap",
            exchange_id="BINANCE",
            quant_input_root=self.quant_input_root,
            time_start="2026-04-20",
            time_end="2026-04-21",
            http_get_json_fn=self._fake_http,
            refresh_catalog=True,
        )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["requested_symbols"], ["ETHUSDT"])
        self.assertEqual(summary["synced_symbol_count"], 1)
        self.assertEqual(summary["discovery_source"], "latest_quant_input")
        self.assertEqual(len(summary["sync_results"]), 3)

        interval_root = self.external_root / "spot" / "ETHUSDT" / "1h"
        partition_files = sorted(interval_root.glob("*.csv.gz"))
        self.assertTrue(partition_files)
        with gzip.open(partition_files[0], "rt", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["exchange"], "binance")
        self.assertTrue(rows[0]["source"].startswith("coinapi_rest:BINANCE_SPOT_ETH_USDT"))
        self.assertNotEqual(rows[0]["quote_volume"], "0.00000000")
        manifest_payload = json.loads((interval_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest_payload["provider"], "coinapi")
        self.assertEqual(manifest_payload["coinapi_symbol_id"], "BINANCE_SPOT_ETH_USDT")
        self.assertEqual(manifest_payload["quote_volume_mode"], "estimated_from_typical_price")

        frame = load_ohlcv_frame(
            symbol="ETHUSDT",
            market_type="spot",
            interval="1h",
            external_root=self.external_root,
            end_time_ms=int(datetime(2026, 4, 21, tzinfo=UTC).timestamp() * 1000),
        )
        self.assertFalse(frame.empty)
        self.assertIn("quote_volume", frame.columns)

    def test_sync_coinapi_ohlcv_resolves_exchange_symbol_alias_and_writes_requested_symbol_store(self) -> None:
        summary = sync_coinapi_ohlcv(
            external_root=self.external_root,
            symbols=("OPUSDT",),
            intervals=("1d", "4h"),
            mode="bootstrap",
            exchange_id="BINANCE",
            time_start="2026-04-20",
            time_end="2026-04-21",
            http_get_json_fn=self._fake_http,
            refresh_catalog=True,
        )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["requested_symbols"], ["OPUSDT"])
        self.assertEqual(summary["alias_resolved_symbols"], ["OPUSDT"])
        self.assertEqual(summary["missing_requested_symbols"], [])
        self.assertEqual(summary["synced_symbol_count"], 1)

        interval_root = self.external_root / "spot" / "OPUSDT" / "1d"
        manifest_payload = json.loads((interval_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest_payload["symbol"], "OPUSDT")
        self.assertEqual(manifest_payload["source_symbol"], "OPUSDT")
        self.assertEqual(manifest_payload["coinapi_symbol_id"], "BINANCE_SPOT_OPTIM_USDT")
        with gzip.open(next(interval_root.glob("*.csv.gz")), "rt", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "OPUSDT")
        self.assertTrue(rows[0]["source"].startswith("coinapi_rest:BINANCE_SPOT_OPTIM_USDT:OPUSDT"))

    def test_refresh_aligns_unseeded_requests_to_interval_boundaries(self) -> None:
        recorded_queries: list[dict[str, str]] = []

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 4, 22, 19, 44, 42, 564000, tzinfo=UTC)
                if tz is None:
                    return value.replace(tzinfo=None)
                return value.astimezone(tz)

        def recording_http(url: str):
            parsed = urlparse(url)
            if parsed.path.endswith("/history"):
                query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                recorded_queries.append(query)
            return self._fake_http(url)

        with patch("scripts.market_data.coinapi_ohlcv.datetime", FixedDateTime):
            summary = sync_coinapi_ohlcv(
                external_root=self.external_root,
                symbols=("ETHUSDT",),
                intervals=("1d", "4h"),
                mode="refresh",
                exchange_id="BINANCE",
                http_get_json_fn=recording_http,
                refresh_catalog=True,
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(len(recorded_queries), 2)
        one_day = next(item for item in recorded_queries if item["period_id"] == "1DAY")
        four_hour = next(item for item in recorded_queries if item["period_id"] == "4HRS")
        self.assertEqual(one_day["time_start"], "2024-04-22T00:00:00Z")
        self.assertEqual(one_day["time_end"], "2026-04-22T00:00:00Z")
        self.assertEqual(four_hour["time_start"], "2025-08-25T16:00:00Z")
        self.assertEqual(four_hour["time_end"], "2026-04-22T16:00:00Z")

    def test_align_time_ms_to_interval_floors_to_bucket_open(self) -> None:
        value = int(datetime(2026, 4, 22, 19, 44, 42, tzinfo=UTC).timestamp() * 1000)
        self.assertEqual(
            _align_time_ms_to_interval(value_ms=value, interval="1d"),
            int(datetime(2026, 4, 22, 0, 0, tzinfo=UTC).timestamp() * 1000),
        )
        self.assertEqual(
            _align_time_ms_to_interval(value_ms=value, interval="4h"),
            int(datetime(2026, 4, 22, 16, 0, tzinfo=UTC).timestamp() * 1000),
        )

    def _write_quant_input(self, payload: dict[str, object]) -> None:
        write_pit_quant_input(
            root=self.quant_input_root,
            as_of=str(payload["as_of"]),
            candidates=list(payload["candidates"]),
        )

    def _fake_http(self, url: str):
        parsed = urlparse(url)
        if parsed.path == "/v1/symbols/BINANCE/active":
            return [
                {
                    "symbol_id": "BINANCE_SPOT_ETH_USDT",
                    "exchange_id": "BINANCE",
                    "symbol_type": "SPOT",
                    "asset_id_base": "ETH",
                    "asset_id_quote": "USDT",
                    "data_start": "2017-01-01",
                    "data_end": None,
                },
                {
                    "symbol_id": "BINANCE_SPOT_SUI_USDT",
                    "exchange_id": "BINANCE",
                    "symbol_type": "SPOT",
                    "asset_id_base": "SUI",
                    "asset_id_quote": "USDT",
                    "data_start": "2023-01-01",
                    "data_end": None,
                },
                {
                    "symbol_id": "BINANCE_SPOT_OPTIM_USDT",
                    "exchange_id": "BINANCE",
                    "symbol_type": "SPOT",
                    "asset_id_base": "OPTIM",
                    "asset_id_quote": "USDT",
                    "data_start": "2022-06-01",
                    "data_end": None,
                },
                {
                    "symbol_id": "BINANCE_SPOT_BTC_FDUSD",
                    "exchange_id": "BINANCE",
                    "symbol_type": "SPOT",
                    "asset_id_base": "BTC",
                    "asset_id_quote": "FDUSD",
                    "data_start": "2024-01-01",
                    "data_end": None,
                },
                {
                    "symbol_id": "BINANCE_PERP_ETH_USDT",
                    "exchange_id": "BINANCE",
                    "symbol_type": "PERPETUAL",
                    "asset_id_base": "ETH",
                    "asset_id_quote": "USDT",
                    "data_start": "2019-01-01",
                    "data_end": None,
                },
            ]
        if parsed.path == "/v1/symbols/map/BINANCE":
            return [
                {
                    "symbol_id": "BINANCE_SPOT_ETH_USDT",
                    "symbol_id_exchange": "ETHUSDT",
                    "asset_id_base_exchange": "ETH",
                    "asset_id_quote_exchange": "USDT",
                    "asset_id_base": "ETH",
                    "asset_id_quote": "USDT",
                    "price_precision": 2,
                    "size_precision": 6,
                },
                {
                    "symbol_id": "BINANCE_SPOT_SUI_USDT",
                    "symbol_id_exchange": "SUIUSDT",
                    "asset_id_base_exchange": "SUI",
                    "asset_id_quote_exchange": "USDT",
                    "asset_id_base": "SUI",
                    "asset_id_quote": "USDT",
                    "price_precision": 4,
                    "size_precision": 2,
                },
                {
                    "symbol_id": "BINANCE_SPOT_OPTIM_USDT",
                    "symbol_id_exchange": "OPUSDT",
                    "asset_id_base_exchange": "OP",
                    "asset_id_quote_exchange": "USDT",
                    "asset_id_base": "OPTIM",
                    "asset_id_quote": "USDT",
                    "price_precision": 4,
                    "size_precision": 2,
                },
            ]
        if parsed.path == "/v1/ohlcv/BINANCE_SPOT_ETH_USDT/history":
            query = parse_qs(parsed.query)
            period_id = str(query["period_id"][0])
            return self._ohlcv_payload(period_id=period_id)
        if parsed.path == "/v1/ohlcv/BINANCE_SPOT_OPTIM_USDT/history":
            query = parse_qs(parsed.query)
            period_id = str(query["period_id"][0])
            return self._ohlcv_payload(period_id=period_id)
        raise AssertionError(url)

    def _ohlcv_payload(self, *, period_id: str) -> list[dict[str, object]]:
        if period_id == "1HRS":
            start = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
            step = timedelta(hours=1)
            periods = 24
        elif period_id == "4HRS":
            start = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
            step = timedelta(hours=4)
            periods = 6
        elif period_id == "1DAY":
            start = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
            step = timedelta(days=1)
            periods = 1
        else:
            raise AssertionError(period_id)
        rows: list[dict[str, object]] = []
        price = 3000.0
        for index in range(periods):
            open_time = start + (step * index)
            close_time = open_time + step
            price_open = price
            price_close = price * 1.001
            rows.append(
                {
                    "time_period_start": open_time.isoformat().replace("+00:00", "Z"),
                    "time_period_end": close_time.isoformat().replace("+00:00", "Z"),
                    "time_open": open_time.isoformat().replace("+00:00", "Z"),
                    "time_close": (close_time - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                    "price_open": price_open,
                    "price_high": price_open * 1.01,
                    "price_low": price_open * 0.99,
                    "price_close": price_close,
                    "volume_traded": 100.0 + index,
                    "trades_count": 50 + index,
                }
            )
            price = price_close
        return rows


if __name__ == "__main__":
    unittest.main()
