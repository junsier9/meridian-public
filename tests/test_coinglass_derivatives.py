from __future__ import annotations

from datetime import UTC, datetime
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_derivatives import load_derivatives_rows
from enhengclaw.quant_research.coinglass_derivatives import sync_coinglass_derivatives_history
from enhengclaw.quant_research.runtime_support import run_quant_derivatives_sync_cycle
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


class CoinglassDerivativesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coinglass-derivatives-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.derivatives_root = self.temp_dir / "external" / "derivatives"
        self.quant_input_root = self.temp_dir / "quant_inputs"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        write_pit_quant_input(
            root=self.quant_input_root,
            as_of="2026-04-22",
            candidates=[pit_candidate("ETH", 2, listing_age_days_as_of=2200)],
        )

    def test_sync_coinglass_derivatives_history_writes_rows_with_perp_close(self) -> None:
        fixed_now = datetime(2026, 4, 22, 0, 0, tzinfo=UTC)
        base_time = int(datetime(2026, 4, 21, 0, 0, tzinfo=UTC).timestamp() * 1000)

        def fake_http(url: str):
            if "supported-exchange-pairs" in url:
                return {"code": "0", "msg": "success", "data": [{"Binance": [{"instrument_id": "ETHUSDT"}]}]}
            if "funding-rate/history" in url:
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {"time": base_time, "open": "0.0001", "high": "0.0001", "low": "0.0001", "close": "0.0002"},
                        {"time": base_time + 14_400_000, "open": "0.0002", "high": "0.0002", "low": "0.0002", "close": "0.0003"},
                    ],
                }
            if "open-interest/history" in url and "unit=coin" in url:
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {"time": base_time, "open": "1000", "high": "1100", "low": "900", "close": "1050"},
                        {"time": base_time + 14_400_000, "open": "1050", "high": "1150", "low": "1000", "close": "1100"},
                    ],
                }
            if "open-interest/history" in url and "unit=usd" in url:
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {"time": base_time, "open": "2000000", "high": "2100000", "low": "1900000", "close": "2050000"},
                        {"time": base_time + 14_400_000, "open": "2050000", "high": "2200000", "low": "2000000", "close": "2150000"},
                    ],
                }
            if "price/history" in url:
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {"time": base_time, "open": "2100", "high": "2120", "low": "2080", "close": "2110", "volume_usd": "1"},
                        {"time": base_time + 14_400_000, "open": "2110", "high": "2140", "low": "2090", "close": "2130", "volume_usd": "1"},
                    ],
                }
            if "taker-buy-sell-volume/history" in url:
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {"time": base_time, "taker_buy_volume_usd": "1250000", "taker_sell_volume_usd": "950000"},
                        {
                            "time": base_time + 14_400_000,
                            "taker_buy_volume_usd": "1450000",
                            "taker_sell_volume_usd": "1050000",
                        },
                    ],
                }
            raise AssertionError(url)

        with patch("enhengclaw.quant_research.coinglass_derivatives.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            summary = sync_coinglass_derivatives_history(
                symbols=["ETHUSDT"],
                intervals=("4h",),
                mode="bootstrap",
                as_of="2026-04-22",
                external_root=self.derivatives_root,
                http_get_json_fn=fake_http,
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["provider"], "coinglass")
        self.assertTrue(Path(str(summary["by_as_of_summary_path"])).exists())
        rows = load_derivatives_rows(external_root=self.derivatives_root, symbol="ETHUSDT", interval="4h")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "coinglass_rest")
        self.assertEqual(rows[0]["perp_close"], "2110.0000000000")
        self.assertEqual(rows[0]["perp_quote_volume_usd"], "2200000.0000000000")
        self.assertEqual(rows[1]["open_interest_value"], "2150000.0000000000")

    def test_run_quant_derivatives_sync_cycle_auto_prefers_coinglass_when_key_present(self) -> None:
        with patch.dict("os.environ", {"CoinglassAPI": "test-key"}, clear=False):
            with patch("enhengclaw.quant_research.runtime_support.sync_coinglass_derivatives_history") as mock_coinglass:
                with patch("enhengclaw.quant_research.runtime_support.sync_binance_derivatives_history") as mock_binance:
                    mock_coinglass.return_value = {"status": "success", "provider": "coinglass"}
                    run_quant_derivatives_sync_cycle(
                        as_of="2026-04-22",
                        quant_input_root=self.quant_input_root,
                        derivatives_external_root=self.derivatives_root,
                        mode="refresh",
                        intervals=("4h",),
                        provider="auto",
                    )

        self.assertTrue(mock_coinglass.called)
        self.assertFalse(mock_binance.called)
