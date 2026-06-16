from __future__ import annotations

import csv
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import zipfile

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.market_data import binance_1m_archive as archive


def _list_bucket_xml(*, keys: list[str] | None = None, prefixes: list[str] | None = None) -> str:
    key_xml = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in (keys or []))
    prefix_xml = "".join(f"<CommonPrefixes><Prefix>{prefix}</Prefix></CommonPrefixes>" for prefix in (prefixes or []))
    return (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<IsTruncated>false</IsTruncated>"
        f"{key_xml}{prefix_xml}"
        "</ListBucketResult>"
    )


class BinanceOneMinuteArchiveTests(unittest.TestCase):
    def test_five_year_window_uses_previous_complete_month(self) -> None:
        months, start, end = archive.five_year_window(months=3, end_month="2026-04")

        self.assertEqual(months, ["2026-02", "2026-03", "2026-04"])
        self.assertEqual(start, "2026-02")
        self.assertEqual(end, "2026-04")

    def test_discovery_selects_only_symbols_with_complete_required_window(self) -> None:
        def fake_fetch_text(url: str) -> str:
            query = parse_qs(urlparse(url).query)
            prefix = query["prefix"][0]
            if prefix == "data/spot/monthly/klines/":
                return _list_bucket_xml(
                    prefixes=[
                        "data/spot/monthly/klines/BTCUSDT/",
                        "data/spot/monthly/klines/ETHUSDT/",
                    ]
                )
            if prefix == "data/spot/monthly/klines/BTCUSDT/1m/":
                return _list_bucket_xml(
                    keys=[
                        f"data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2021-0{month}.zip"
                        for month in (5, 6, 7)
                    ]
                )
            if prefix == "data/spot/monthly/klines/ETHUSDT/1m/":
                return _list_bucket_xml(
                    keys=[
                        "data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2021-05.zip",
                        "data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2021-07.zip",
                    ]
                )
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory(prefix="binance_1m_discovery_") as tmpdir:
            summary = archive.discover_five_year_coverage(
                external_root=Path(tmpdir),
                markets=("spot",),
                months=3,
                end_month="2021-07",
                active_only=False,
                workers=2,
                fetch_text_fn=fake_fetch_text,
            )

            self.assertEqual(summary["eligible_count"], 1)
            self.assertEqual(summary["eligible_symbols"], [{"market_type": "spot", "symbol": "BTCUSDT"}])
            eth = next(item for item in summary["coverage"] if item["symbol"] == "ETHUSDT")
            self.assertFalse(eth["eligible"])
            self.assertEqual(eth["missing_required_months"], ["2021-06"])
            self.assertTrue(archive.discovery_summary_path(external_root=Path(tmpdir)).exists())
            self.assertTrue(archive.discovery_csv_path(external_root=Path(tmpdir)).exists())

    def test_download_writes_resumable_csv_gz_partition(self) -> None:
        row = "1622505600000,1,2,0.5,1.5,10,1622505659999,100,4,5,50,0\n"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
            zip_handle.writestr("BTCUSDT-1m-2021-06.csv", row)

        def fake_download_bytes(url: str) -> bytes:
            self.assertIn("BTCUSDT-1m-2021-06.zip", url)
            return buffer.getvalue()

        discovery_summary = {
            "source": "test",
            "external_root": "",
            "required_months": ["2021-06"],
            "required_start_month": "2021-06",
            "required_end_month": "2021-06",
            "eligible_symbols": [{"market_type": "spot", "symbol": "BTCUSDT"}],
        }
        with tempfile.TemporaryDirectory(prefix="binance_1m_download_") as tmpdir:
            root = Path(tmpdir)
            summary = archive.download_eligible_1m_archive(
                discovery_summary=discovery_summary,
                external_root=root,
                output_format="csv.gz",
                download_bytes_fn=fake_download_bytes,
            )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["written_partition_count"], 1)
            partition_path = archive.data_partition_path(
                external_root=root,
                market_type="spot",
                symbol="BTCUSDT",
                interval="1m",
                month="2021-06",
                output_format="csv.gz",
            )
            self.assertTrue(partition_path.exists())
            with gzip.open(partition_path, "rt", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["close"], "1.5")
            self.assertTrue(archive.download_summary_path(external_root=root).exists())
            stored_summary = json.loads(archive.download_summary_path(external_root=root).read_text(encoding="utf-8"))
            self.assertEqual(stored_summary["written_row_count"], 1)

    def test_rest_backfill_merges_missing_minutes_into_existing_partition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="binance_1m_rest_backfill_") as tmpdir:
            root = Path(tmpdir)
            partition_path = archive.data_partition_path(
                external_root=root,
                market_type="usdm_perp",
                symbol="BTCUSDT",
                interval="1m",
                month="2026-01",
                output_format="csv.gz",
            )
            archive.write_partition(
                partition_path=partition_path,
                rows=[
                    _kline_row(
                        open_time_ms=1767225600000,
                        close_time_ms=1767225659999,
                        source="archive",
                    )
                ],
                output_format="csv.gz",
                month="2026-01",
            )

            def fake_http_get_json(url: str):
                self.assertIn("/fapi/v1/klines?", url)
                return [
                    _api_kline(1767225660000, 1767225719999, "2.5"),
                    _api_kline(1767225720000, 1767225779999, "3.5"),
                ]

            summary = archive.backfill_1m_archive_rest_gaps(
                external_root=root,
                markets=("usdm_perp",),
                symbols=("BTCUSDT",),
                months=("2026-01",),
                output_format="csv.gz",
                request_sleep_seconds=0.0,
                http_get_json_fn=fake_http_get_json,
            )

            result = summary["partition_results"][0]
            self.assertEqual(summary["status"], "success")
            self.assertEqual(result["fetched_row_count"], 2)
            self.assertEqual(result["written_row_count"], 3)
            self.assertLess(
                result["missing_open_time_count_after"],
                result["missing_open_time_count_before"],
            )
            with gzip.open(partition_path, "rt", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["source"] for row in rows], ["archive", "rest", "rest"])
            self.assertTrue(archive.rest_backfill_summary_path(external_root=root).exists())

def _kline_row(*, open_time_ms: int, close_time_ms: int, source: str) -> dict[str, str]:
    return {
        "exchange": "binance",
        "market_type": "usdm_perp",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "open_time_ms": str(open_time_ms),
        "close_time_ms": str(close_time_ms),
        "open": "1",
        "high": "2",
        "low": "0.5",
        "close": "1.5",
        "volume": "10",
        "quote_volume": "100",
        "trade_count": "4",
        "taker_buy_base_volume": "5",
        "taker_buy_quote_volume": "50",
        "source": source,
    }


def _api_kline(open_time_ms: int, close_time_ms: int, close: str) -> list[str | int]:
    return [
        open_time_ms,
        "1",
        "2",
        "0.5",
        close,
        "10",
        close_time_ms,
        "100",
        4,
        "5",
        "50",
        "0",
    ]


if __name__ == "__main__":
    unittest.main()
