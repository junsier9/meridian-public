from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinapi_spot_sync import run_quant_coinapi_spot_sync
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


class QuantCoinApiSpotSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-coinapi-spot-sync-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.quant_input_root = self.temp_dir / "artifacts" / "quant_research" / "_quant_inputs"
        self.external_root = self.temp_dir / "external" / "coinapi"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        source_commit_patcher = patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def test_refresh_uses_exact_as_of_quant_input_and_top30_intraday_slice(self) -> None:
        self._write_quant_input(as_of="2026-04-20", subject_count=35, subject_prefix="A")
        self._write_quant_input(as_of="2026-04-21", subject_count=50, subject_prefix="B")
        calls: list[dict[str, object]] = []

        def fake_sync(**kwargs):
            calls.append(dict(kwargs))
            return {
                "status": "success",
                "success": True,
                "artifact_family": "coinapi_ohlcv_sync",
                "contract_version": "coinapi_ohlcv_sync.v1",
                "input_watermarks": {},
                "upstream_versions": {},
                "requested_symbols": list(kwargs.get("symbols") or []),
                "requested_symbol_count": len(list(kwargs.get("symbols") or [])),
            }

        with patch("enhengclaw.quant_research.coinapi_spot_sync.sync_coinapi_ohlcv", side_effect=fake_sync):
            summary = run_quant_coinapi_spot_sync(
                as_of="2026-04-20",
                mode="refresh",
                quant_input_root=self.quant_input_root,
                external_root=self.external_root,
                refresh_catalog=True,
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["top100_symbol_count"], 35)
        self.assertEqual(summary["top30_intraday_symbol_count"], 30)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["intervals"], ("1d", "4h"))
        self.assertEqual(len(list(calls[0]["symbols"])), 35)
        self.assertTrue(all(str(symbol).startswith("A") for symbol in calls[0]["symbols"]))
        self.assertEqual(calls[1]["intervals"], ("1h",))
        self.assertEqual(len(list(calls[1]["symbols"])), 30)
        self.assertTrue(all(str(symbol).startswith("A") for symbol in calls[1]["symbols"]))
        self.assertTrue(calls[0]["refresh_catalog"])
        self.assertFalse(calls[1]["refresh_catalog"])

    def test_bootstrap_applies_phase_lookback_caps(self) -> None:
        self._write_quant_input(as_of="2026-04-20", subject_count=2, subject_prefix="Q", listing_ages=(10, 400))
        calls: list[dict[str, object]] = []

        def fake_sync(**kwargs):
            calls.append(dict(kwargs))
            return {
                "status": "success",
                "success": True,
                "artifact_family": "coinapi_ohlcv_sync",
                "contract_version": "coinapi_ohlcv_sync.v1",
                "input_watermarks": {},
                "upstream_versions": {},
                "requested_symbols": list(kwargs.get("symbols") or []),
                "requested_symbol_count": len(list(kwargs.get("symbols") or [])),
            }

        with patch("enhengclaw.quant_research.coinapi_spot_sync.sync_coinapi_ohlcv", side_effect=fake_sync):
            summary = run_quant_coinapi_spot_sync(
                as_of="2026-04-20",
                mode="bootstrap",
                quant_input_root=self.quant_input_root,
                external_root=self.external_root,
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(len(calls), 6)
        one_day_starts = [call["time_start"] for call in calls if call["intervals"] == ("1d",)]
        four_hour_starts = [call["time_start"] for call in calls if call["intervals"] == ("4h",)]
        one_hour_starts = [call["time_start"] for call in calls if call["intervals"] == ("1h",)]
        self.assertEqual(one_day_starts, ["2026-04-11T00:00:00Z", "2025-03-17T00:00:00Z"])
        self.assertEqual(four_hour_starts, ["2026-04-11T00:00:00Z", "2025-03-17T00:00:00Z"])
        self.assertEqual(one_hour_starts, ["2026-04-11T00:00:00Z", "2025-10-23T00:00:00Z"])
        self.assertTrue(all(call["time_end"] == "2026-04-21T00:00:00Z" for call in calls))

    def test_refresh_falls_back_to_per_symbol_sync_and_records_partial_success(self) -> None:
        self._write_quant_input(as_of="2026-04-20", subject_count=2, subject_prefix="R")
        calls: list[dict[str, object]] = []

        def fake_sync(**kwargs):
            calls.append(dict(kwargs))
            symbols = list(kwargs.get("symbols") or [])
            if len(symbols) > 1:
                raise RuntimeError("batch failure")
            if symbols == ["R01USDT"]:
                raise RuntimeError("R01 failed")
            return {
                "status": "success",
                "success": True,
                "artifact_family": "coinapi_ohlcv_sync",
                "contract_version": "coinapi_ohlcv_sync.v1",
                "input_watermarks": {},
                "upstream_versions": {},
                "requested_symbols": symbols,
                "requested_symbol_count": len(symbols),
                "synced_symbol_count": len(symbols),
            }

        with patch("enhengclaw.quant_research.coinapi_spot_sync.sync_coinapi_ohlcv", side_effect=fake_sync):
            summary = run_quant_coinapi_spot_sync(
                as_of="2026-04-20",
                mode="refresh",
                quant_input_root=self.quant_input_root,
                external_root=self.external_root,
                refresh_catalog=True,
            )

        self.assertEqual(summary["status"], "partial_success")
        self.assertTrue(summary["success"])
        self.assertEqual(summary["successful_sync_count"], 2)
        self.assertEqual(summary["phase_failure_count"], 2)
        self.assertTrue(all(item["symbol"] == "R01USDT" for item in summary["phase_failures"]))
        self.assertEqual(len(calls), 6)
        self.assertTrue(calls[0]["refresh_catalog"])
        self.assertTrue(all(not call["refresh_catalog"] for call in calls[1:]))
        self.assertTrue(summary["phases"][0]["batch_attempt_failed"])
        self.assertTrue(summary["phases"][1]["batch_attempt_failed"])

    def test_bootstrap_records_partial_success_when_individual_symbol_fails(self) -> None:
        self._write_quant_input(as_of="2026-04-20", subject_count=2, subject_prefix="P", listing_ages=(10, 20))

        def fake_sync(**kwargs):
            symbols = list(kwargs.get("symbols") or [])
            if symbols == ["P01USDT"] and tuple(kwargs.get("intervals") or ()) == ("4h",):
                raise RuntimeError("P01 4h failed")
            return {
                "status": "success",
                "success": True,
                "artifact_family": "coinapi_ohlcv_sync",
                "contract_version": "coinapi_ohlcv_sync.v1",
                "input_watermarks": {},
                "upstream_versions": {},
                "requested_symbols": symbols,
                "requested_symbol_count": len(symbols),
                "synced_symbol_count": len(symbols),
            }

        with patch("enhengclaw.quant_research.coinapi_spot_sync.sync_coinapi_ohlcv", side_effect=fake_sync):
            summary = run_quant_coinapi_spot_sync(
                as_of="2026-04-20",
                mode="bootstrap",
                quant_input_root=self.quant_input_root,
                external_root=self.external_root,
            )

        self.assertEqual(summary["status"], "partial_success")
        self.assertEqual(summary["phase_failure_count"], 1)
        self.assertEqual(summary["phase_failures"][0]["symbol"], "P01USDT")
        self.assertEqual(summary["phases"][1]["failure_count"], 1)
        self.assertEqual(summary["successful_sync_count"], 5)

    def _write_quant_input(
        self,
        *,
        as_of: str,
        subject_count: int,
        subject_prefix: str,
        listing_ages: tuple[int, ...] | None = None,
    ) -> None:
        candidates = []
        for index in range(subject_count):
            symbol = f"{subject_prefix}{index:02d}"
            candidates.append(
                pit_candidate(
                    symbol,
                    index + 1,
                    listing_age_days_as_of=listing_ages[index] if listing_ages is not None else 500,
                )
            )
        write_pit_quant_input(root=self.quant_input_root, as_of=as_of, candidates=candidates)


if __name__ == "__main__":
    unittest.main()
