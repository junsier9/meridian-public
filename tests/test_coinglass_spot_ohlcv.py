from __future__ import annotations

from datetime import UTC, datetime
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from enhengclaw.quant_research.coinglass_spot_ohlcv import load_spot_rows, sync_coinglass_spot_ohlcv
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


class CoinglassSpotOhlcvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coinglass-spot-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.quant_input_root = self.temp_dir / "quant_inputs"
        self.external_root = self.temp_dir / "coinglass_spot"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        write_pit_quant_input(
            root=self.quant_input_root,
            as_of="2026-05-04",
            candidates=[
                pit_candidate("BTC", 1, listing_age_days_as_of=4000),
                pit_candidate("ETH", 2, listing_age_days_as_of=3000),
            ],
        )

    def test_sync_writes_normalized_spot_rows(self) -> None:
        base = int(datetime(2026, 5, 4, 0, 0, tzinfo=UTC).timestamp() * 1000)

        def fake_http(url: str):
            rows = []
            for i in range(24):
                t = base + i * 3_600_000
                rows.append({"time": t, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume_usd": 1000 + i})
            return {"code": "0", "data": rows}

        summary = sync_coinglass_spot_ohlcv(
            as_of="2026-05-04",
            intervals=("1h",),
            quant_input_root=self.quant_input_root,
            external_root=self.external_root,
            lookback_days=1,
            max_symbols=1,
            http_get_json_fn=fake_http,
            write_repo_artifacts=False,
        )

        self.assertTrue(summary["success"])
        self.assertEqual(summary["requested_symbol_count"], 1)
        rows = load_spot_rows(external_root=self.external_root, symbol="BTCUSDT", interval="1h")
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0]["source"], "coinglass_spot_price_history")
        self.assertEqual(rows[0]["quote_volume"], "1000.0000000000")
        self.assertEqual(rows[0]["volume"], "")
        manifest = json.loads(Path(summary["sync_results"][0]["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["requested_completeness"], 1.0)


if __name__ == "__main__":
    unittest.main()
