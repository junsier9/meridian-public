from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.market_data import binance_ohlcv as history


def _kline_row(*, open_time_ms: int, close_time_ms: int, close_value: float) -> dict[str, str]:
    return {
        "exchange": history.EXCHANGE,
        "market_type": "spot",
        "symbol": "ETHUSDT",
        "interval": "1h",
        "open_time_ms": str(open_time_ms),
        "close_time_ms": str(close_time_ms),
        "open": f"{close_value - 0.5:.8f}",
        "high": f"{close_value + 0.5:.8f}",
        "low": f"{close_value - 1.0:.8f}",
        "close": f"{close_value:.8f}",
        "volume": "100.00000000",
        "quote_volume": "1000.00000000",
        "trade_count": "10",
        "taker_buy_base_volume": "55.00000000",
        "taker_buy_quote_volume": "550.00000000",
        "source": "rest",
    }


class BinanceOhlcvHistoryTests(unittest.TestCase):
    def _exchange_info(self) -> dict[str, object]:
        return {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
            ]
        }

    def _write_interval_rows(
        self,
        *,
        external_root: Path,
        market_type: str,
        symbol: str,
        interval: str,
        bars: int,
        bar_ms: int,
        starting_close: float,
    ) -> None:
        base_open = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
        rows = []
        for index in range(bars):
            open_time_ms = base_open + (index * bar_ms)
            close_time_ms = open_time_ms + bar_ms - 1
            close_value = starting_close + index
            rows.append(
                {
                    "exchange": history.EXCHANGE,
                    "market_type": market_type,
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(open_time_ms),
                    "close_time_ms": str(close_time_ms),
                    "open": f"{close_value - 0.5:.8f}",
                    "high": f"{close_value + 0.5:.8f}",
                    "low": f"{close_value - 1.0:.8f}",
                    "close": f"{close_value:.8f}",
                    "volume": "100.00000000",
                    "quote_volume": "1000.00000000",
                    "trade_count": "10",
                    "taker_buy_base_volume": "55.00000000",
                    "taker_buy_quote_volume": "550.00000000",
                    "source": "rest",
                }
            )
        history._merge_rows_into_store(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            rows=rows,
        )

    def test_parse_archive_rows_normalizes_microseconds_and_monthly_alias(self) -> None:
        open_time_us = 1_735_689_600_000_000
        close_time_us = open_time_us + (60_000_000 - 1)
        csv_body = (
            f"{open_time_us},1,2,0.5,1.5,10,{close_time_us},100,4,5,50,0\n"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
            zip_handle.writestr("ETHUSDT-1mo-2025-01.csv", csv_body)

        rows = history._parse_archive_rows(
            archive_bytes=buffer.getvalue(),
            market_type="spot",
            symbol="ETHUSDT",
            interval="1mo",
            source="archive",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interval"], "1M")
        self.assertEqual(rows[0]["open_time_ms"], "1735689600000")
        self.assertEqual(rows[0]["close_time_ms"], "1735689659999")

    def test_fetch_rest_klines_normalizes_rows(self) -> None:
        captured_urls: list[str] = []

        def fake_http_get_json(url: str) -> list[list[object]]:
            captured_urls.append(url)
            return [
                [
                    1_735_689_600_000,
                    "1.0",
                    "2.0",
                    "0.5",
                    "1.5",
                    "10.0",
                    1_735_689_659_999,
                    "100.0",
                    4,
                    "5.0",
                    "50.0",
                    "0",
                ]
            ]

        rows = history.fetch_rest_klines(
            market_type="usdm_perp",
            symbol="ETHUSDT",
            interval="4h",
            start_time_ms=1_735_689_600_000,
            end_time_ms=1_735_700_000_000,
            limit=100,
            http_get_json_fn=fake_http_get_json,
        )

        self.assertEqual(len(rows), 1)
        self.assertIn("/fapi/v1/klines?", captured_urls[0])
        self.assertIn("interval=4h", captured_urls[0])
        self.assertEqual(rows[0]["market_type"], "usdm_perp")
        self.assertEqual(rows[0]["symbol"], "ETHUSDT")
        self.assertEqual(rows[0]["close"], "1.5")

    def test_resolve_market_symbols_falls_back_to_subject_usdt_and_marks_partial(self) -> None:
        symbol_catalog = {
            "markets": {
                "spot": {"symbols": {"ETHUSDT": {"symbol": "ETHUSDT"}}},
                "usdm_perp": {"symbols": {}},
            }
        }

        mapping = history.resolve_market_symbols(
            subject="ETH",
            scope="spot+perp",
            symbol_catalog=symbol_catalog,
        )

        self.assertEqual(mapping["spot_symbol"], "ETHUSDT")
        self.assertIsNone(mapping["usdm_symbol"])
        self.assertEqual(mapping["status"], "partial")

    def test_build_ohlcv_context_reports_full_coverage_and_breakout_samples(self) -> None:
        with tempfile.TemporaryDirectory(prefix="binance_ohlcv_context_") as tmpdir:
            external_root = Path(tmpdir)
            for market_type in ("spot", "usdm_perp"):
                self._write_interval_rows(
                    external_root=external_root,
                    market_type=market_type,
                    symbol="ETHUSDT",
                    interval="1h",
                    bars=24 * 35,
                    bar_ms=history.interval_to_ms("1h"),
                    starting_close=100.0,
                )
                self._write_interval_rows(
                    external_root=external_root,
                    market_type=market_type,
                    symbol="ETHUSDT",
                    interval="4h",
                    bars=6 * 130,
                    bar_ms=history.interval_to_ms("4h"),
                    starting_close=200.0,
                )
                self._write_interval_rows(
                    external_root=external_root,
                    market_type=market_type,
                    symbol="ETHUSDT",
                    interval="1d",
                    bars=220,
                    bar_ms=history.interval_to_ms("1d"),
                    starting_close=300.0,
                )

            context = history.build_ohlcv_context(
                external_root=external_root,
                market_symbols={"spot_symbol": "ETHUSDT", "usdm_symbol": "ETHUSDT"},
                scope="spot+perp",
            )

            self.assertEqual(context["history_coverage"]["status"], "full")
            self.assertTrue(context["history_coverage"]["breakout_comparison_ready"])
            self.assertEqual(context["markets"]["spot"]["status"], "full")
            self.assertGreater(len(context["markets"]["spot"]["breakout_samples_1d"]), 0)
            self.assertIn("history_coverage_status=full", context["summary_text"])

    def test_sync_binance_ohlcv_bootstrap_and_refresh_writes_store(self) -> None:
        with tempfile.TemporaryDirectory(prefix="binance_ohlcv_sync_") as tmpdir:
            external_root = Path(tmpdir) / "history"

            def fake_http_get_json(url: str) -> object:
                if url == history.SPOT_EXCHANGE_INFO_URL:
                    return self._exchange_info()
                if url == history.USDM_EXCHANGE_INFO_URL:
                    return self._exchange_info()
                return []

            archive_month = (datetime.now(UTC) - timedelta(days=30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            archive_name = f"ETHUSDT-1h-{archive_month.year:04d}-{archive_month.month:02d}.csv"
            row_open_ms = int(archive_month.timestamp() * 1000)
            csv_body = (
                f"{row_open_ms},1,2,0.5,1.5,10,{row_open_ms + history.interval_to_ms('1h') - 1},100,4,5,50,0\n"
            )

            def fake_download_bytes(url: str) -> bytes:
                self.assertIn("data.binance.vision", url)
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
                    zip_handle.writestr(archive_name, csv_body)
                return buffer.getvalue()

            summary = history.sync_binance_ohlcv(
                external_root=external_root,
                symbols=("ETHUSDT",),
                markets=("spot",),
                intervals=("1h",),
                mode="bootstrap",
                http_get_json_fn=fake_http_get_json,
                download_bytes_fn=fake_download_bytes,
            )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["symbol_count"], 1)
            manifest_path = history.interval_manifest_path(
                external_root=external_root,
                market_type="spot",
                symbol="ETHUSDT",
                interval="1h",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(manifest["total_rows"], 1)
            self.assertGreaterEqual(manifest["coverage_days"], 0.0)


if __name__ == "__main__":
    unittest.main()
