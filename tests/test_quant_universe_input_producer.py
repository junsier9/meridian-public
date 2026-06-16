from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import (
    PIT_SELECTION_METRIC,
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
)
from enhengclaw.quant_research.universe_input_producer import run_quant_universe_input_producer
from scripts.market_data.binance_ohlcv import CSV_HEADERS as OHLCV_HEADERS


class QuantUniverseInputProducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-input-producer-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_input_root = self.artifacts_root / "_quant_inputs"
        self.spot_ohlcv_root = self.temp_dir / "external" / "coinapi_ohlcv"
        self.perp_ohlcv_root = self.temp_dir / "external" / "binance_ohlcv"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        source_commit_patcher = mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def test_input_producer_builds_offline_pit_payload_and_excludes_stable_and_pegged_assets(self) -> None:
        start = datetime(2026, 3, 15, tzinfo=UTC)
        self._write_daily_quote_volume_series(symbol="ETHUSDT", start=start, quote_volumes=[2_000.0] * 35)
        self._write_daily_quote_volume_series(symbol="SUIUSDT", start=start, quote_volumes=[500.0] * 35)
        self._write_daily_quote_volume_series(symbol="USDCUSDT", start=start, quote_volumes=[9_999.0] * 35)
        self._write_daily_quote_volume_series(symbol="WBTCUSDT", start=start, quote_volumes=[8_888.0] * 35)
        self._write_daily_quote_volume_series(
            symbol="ETHUSDT",
            start=start,
            quote_volumes=[1_000.0] * 35,
            market_type="usdm_perp",
        )
        self._write_daily_quote_volume_series(
            symbol="DOGEUSDT",
            start=start,
            quote_volumes=[50_000.0] * 35,
            market_type="usdm_perp",
        )

        summary = run_quant_universe_input_producer(
            as_of="2026-04-21",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_input_root,
            spot_ohlcv_external_root=self.spot_ohlcv_root,
            perp_ohlcv_external_root=self.perp_ohlcv_root,
        )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["exclusion_counts"]["stablecoin"], 1)
        self.assertEqual(summary["exclusion_counts"]["pegged_asset"], 1)

        payload = json.loads(
            (self.quant_input_root / "pit-liquidity-top100-2026-04-21.quant_universe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["contract_version"], QUANT_UNIVERSE_INPUT_CONTRACT_VERSION)
        self.assertEqual(payload["universe_definition_id"], QUANT_UNIVERSE_DEFINITION_ID)
        self.assertEqual(payload["candidate_count_effective"], 2)
        self.assertFalse(payload["top100_complete"])
        self.assertEqual(payload["selection_policy"]["selection_metric"], PIT_SELECTION_METRIC)
        self.assertEqual([item["subject"] for item in payload["candidates"]], ["ETH", "SUI"])
        self.assertEqual(payload["input_provenance"]["spot_history_provider"], "coinapi")
        self.assertEqual(payload["input_provenance"]["perp_history_provider"], "binance")
        self.assertEqual(Path(payload["input_provenance"]["spot_history_root"]).name, "coinapi_ohlcv")
        self.assertEqual(Path(payload["input_provenance"]["perp_history_root"]).name, "binance_ohlcv")
        eth, sui = payload["candidates"]
        self.assertEqual(eth["selection_rank"], 1)
        self.assertEqual(eth["liquidity_bucket"], "top_liquidity")
        self.assertEqual(eth["usdm_symbol"], "ETHUSDT")
        self.assertIsNotNone(eth["first_perp_bar_utc"])
        self.assertIsNone(sui["usdm_symbol"])
        self.assertIsNone(sui["first_perp_bar_utc"])
        self.assertNotIn("DOGE", [item["subject"] for item in payload["candidates"]])
        self.assertIn("window_partition_paths", eth["field_provenance"]["selection_metric"])
        self.assertIn("manifest_path", eth["field_provenance"]["spot_symbol"])

    def test_input_producer_uses_d_minus_1_only_for_selection_and_listing_age(self) -> None:
        start = datetime(2026, 3, 22, tzinfo=UTC)
        self._write_daily_quote_volume_series(
            symbol="ETHUSDT",
            start=start,
            quote_volumes=([100.0] * 30) + [999_999.0],
        )
        self._write_daily_quote_volume_series(
            symbol="SUIUSDT",
            start=start,
            quote_volumes=[200.0] * 31,
        )

        run_quant_universe_input_producer(
            as_of="2026-04-21",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_input_root,
            spot_ohlcv_external_root=self.spot_ohlcv_root,
            perp_ohlcv_external_root=self.perp_ohlcv_root,
        )
        payload = json.loads(
            (self.quant_input_root / "pit-liquidity-top100-2026-04-21.quant_universe.json").read_text(encoding="utf-8")
        )

        self.assertEqual([item["subject"] for item in payload["candidates"]], ["SUI", "ETH"])
        eth = next(item for item in payload["candidates"] if item["subject"] == "ETH")
        self.assertEqual(eth["selection_score"], 100.0)
        self.assertEqual(eth["listing_age_days_as_of"], 30)
        self.assertTrue(eth["selection_window_end_utc"].startswith("2026-04-20T23:59:59"))

    def test_input_producer_tie_breaks_by_mean_then_subject(self) -> None:
        start = datetime(2026, 3, 15, tzinfo=UTC)
        self._write_daily_quote_volume_series(
            symbol="AAAUSDT",
            start=start,
            quote_volumes=([100.0] * 20) + ([300.0] * 10),
        )
        self._write_daily_quote_volume_series(
            symbol="BBBUSDT",
            start=start,
            quote_volumes=([100.0] * 20) + ([300.0] * 10),
        )
        self._write_daily_quote_volume_series(
            symbol="CCCUSDT",
            start=start,
            quote_volumes=([100.0] * 25) + ([200.0] * 5),
        )

        run_quant_universe_input_producer(
            as_of="2026-04-21",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_input_root,
            spot_ohlcv_external_root=self.spot_ohlcv_root,
            perp_ohlcv_external_root=self.perp_ohlcv_root,
        )
        payload = json.loads(
            (self.quant_input_root / "pit-liquidity-top100-2026-04-21.quant_universe.json").read_text(encoding="utf-8")
        )
        self.assertEqual([item["subject"] for item in payload["candidates"]], ["AAA", "BBB", "CCC"])

    def test_input_producer_rejects_retired_single_root_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "single-root ohlcv_external_root has been retired"):
            run_quant_universe_input_producer(
                as_of="2026-04-21",
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_input_root,
                ohlcv_external_root=self.perp_ohlcv_root,
            )

    def _write_daily_quote_volume_series(
        self,
        *,
        symbol: str,
        start: datetime,
        quote_volumes: list[float],
        market_type: str = "spot",
        external_root: Path | None = None,
    ) -> None:
        rows = []
        for index, quote_volume in enumerate(quote_volumes):
            open_time = start + timedelta(days=index)
            close_time = open_time + timedelta(days=1) - timedelta(milliseconds=1)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": market_type,
                    "symbol": symbol,
                    "interval": "1d",
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "open": "1.0",
                    "high": "1.1",
                    "low": "0.9",
                    "close": "1.0",
                    "volume": f"{quote_volume:.10f}",
                    "quote_volume": f"{quote_volume:.10f}",
                    "trade_count": "10",
                    "taker_buy_base_volume": f"{quote_volume / 2.0:.10f}",
                    "taker_buy_quote_volume": f"{quote_volume / 2.0:.10f}",
                    "source": "test",
                }
            )
        resolved_root = external_root or (
            self.spot_ohlcv_root if market_type == "spot" else self.perp_ohlcv_root
        )
        root = resolved_root / market_type / symbol / "1d"
        root.mkdir(parents=True, exist_ok=True)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=OHLCV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        partition_name = f"{start:%Y-%m}.csv.gz"
        with gzip.open(root / partition_name, "wt", encoding="utf-8", newline="") as handle:
            handle.write(buffer.getvalue())
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "generated_at_utc": "2026-04-21T00:00:00Z",
                    "total_rows": len(rows),
                    "partitions": [partition_name],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
