from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.openclaw import run_openclaw_research_scan as research_scan


class OpenClawResearchScanTests(unittest.TestCase):
    def _symbol_catalog(self) -> dict[str, object]:
        symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT", "ATOMUSDT", "JTOUSDT")
        return {
            "markets": {
                "spot": {"symbols": {symbol: {"symbol": symbol} for symbol in symbols}},
                "usdm_perp": {"symbols": {symbol: {"symbol": symbol} for symbol in symbols}},
            }
        }

    def _build_ohlcv_context(self, *, market_symbols: dict[str, object], scope: str, **_: object) -> dict[str, object]:
        markets: dict[str, object] = {}
        for market_type, key in (("spot", "spot_symbol"), ("usdm_perp", "usdm_symbol")):
            symbol = market_symbols.get(key)
            if symbol:
                markets[market_type] = {
                    "market_type": market_type,
                    "symbol": symbol,
                    "status": "full",
                    "intervals": {
                        interval: {
                            "interval": interval,
                            "bar_count": 256,
                            "coverage_days": 365.0,
                            "ready": True,
                            "last_open_time_utc": "2026-04-20T00:00:00Z",
                            "last_close_time_utc": "2026-04-20T01:00:00Z",
                            "last_close": "1.00000000",
                            "distance_to_high_pct": {"20": -1.0, "60": -2.0, "120": -3.0},
                            "distance_to_low_pct": {"20": 1.0, "60": 2.0, "120": 3.0},
                            "relative_volume_20": 1.1,
                            "realized_volatility_20": 0.02,
                        }
                        for interval in ("1h", "4h", "1d")
                    },
                    "breakout_samples_1d": [
                        {
                            "breakout_open_time_utc": "2026-04-10T00:00:00Z",
                            "forward_5d_return_pct": 4.2,
                            "max_drawdown_10d_pct": -2.3,
                        }
                    ],
                    "breakout_comparison_ready": True,
                }
        return {
            "generated_at_utc": "2026-04-20T00:00:00Z",
            "exchange": "binance",
            "scope": scope,
            "market_symbols": {
                "spot_symbol": market_symbols.get("spot_symbol"),
                "usdm_symbol": market_symbols.get("usdm_symbol"),
            },
            "history_coverage": {
                "status": "full",
                "scope": scope,
                "markets": {
                    market_type: {
                        "symbol": entry["symbol"],
                        "status": "full",
                        "intervals": {
                            interval: {"bars": 256, "coverage_days": 365.0, "ready": True}
                            for interval in ("1h", "4h", "1d")
                        },
                    }
                    for market_type, entry in markets.items()
                },
                "breakout_comparison_ready": True,
            },
            "markets": markets,
            "summary_text": "history_coverage_status=full\nbreakout_comparison_ready=True",
        }

    def _write_market_scan(self, root: Path, payload: dict[str, object]) -> Path:
        market_scan_path = root / "market_scan.json"
        market_scan_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return market_scan_path

    def _write_thesis_profile(
        self,
        *,
        workbench_root: Path,
        object_id: str,
        subject: str,
        strategy_profile: str,
        asset_bucket: str,
    ) -> None:
        thesis_root = workbench_root / object_id
        thesis_root.mkdir(parents=True, exist_ok=True)
        (thesis_root / "thesis_profile.json").write_text(
            json.dumps(
                {
                    "object_id": object_id,
                    "subject": subject,
                    "scope": "spot+perp",
                    "strategy_profile": strategy_profile,
                    "asset_bucket": asset_bucket,
                    "created_at_utc": "2026-04-20T00:00:00Z",
                    "updated_at_utc": "2026-04-20T00:00:00Z",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _write_cycle_summary(self, *, workbench_root: Path, object_id: str, cycle_id: str, cycle_date: str) -> None:
        cycle_root = workbench_root / object_id / "cycles" / cycle_id
        cycle_root.mkdir(parents=True, exist_ok=True)
        (cycle_root / "cycle_summary.json").write_text(
            json.dumps(
                {
                    "status": "success",
                    "object_id": object_id,
                    "cycle_id": cycle_id,
                    "cycle_date": cycle_date,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def test_asset_bucket_for_rank_maps_expected_ranges(self) -> None:
        self.assertEqual(research_scan.asset_bucket_for_rank(1), "large_cap")
        self.assertEqual(research_scan.asset_bucket_for_rank(20), "large_cap")
        self.assertEqual(research_scan.asset_bucket_for_rank(21), "mid_cap")
        self.assertEqual(research_scan.asset_bucket_for_rank(100), "mid_cap")
        self.assertEqual(research_scan.asset_bucket_for_rank(101), "small_cap")
        self.assertEqual(research_scan.asset_bucket_for_rank(300), "small_cap")
        self.assertIsNone(research_scan.asset_bucket_for_rank(301))

    def test_run_scan_emits_at_most_three_snapshots_and_prioritizes_missing_buckets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_scan_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            incoming_root = workbench_root / "_incoming"
            self._write_thesis_profile(
                workbench_root=workbench_root,
                object_id="btc-conservative-20260420",
                subject="BTC",
                strategy_profile="conservative",
                asset_bucket="large_cap",
            )
            market_scan_path = self._write_market_scan(
                root,
                {
                    "scan_id": "scan-001",
                    "scan_date": "2026-04-20",
                    "candidates": [
                        {
                            "subject": "USDT",
                            "market_cap_rank": 3,
                            "structure_clarity_score": 95,
                            "liquidity_score": 99,
                            "catalyst_score": 10,
                            "risk_boundary_score": 99,
                            "volatility_score": 1,
                            "observation": "Stablecoin should be excluded.",
                            "evidence": "Excluded candidate.",
                            "risk": "n/a",
                            "next_step": "n/a",
                            "is_stablecoin": True,
                        },
                        {
                            "subject": "ETH",
                            "market_cap_rank": 2,
                            "structure_clarity_score": 88,
                            "liquidity_score": 94,
                            "catalyst_score": 62,
                            "risk_boundary_score": 82,
                            "volatility_score": 45,
                            "observation": "ETH remains constructive.",
                            "evidence": "Spot leadership stayed healthy.",
                            "risk": "Loss of local support weakens the setup.",
                            "next_step": "Re-check after the next session.",
                        },
                        {
                            "subject": "ARB",
                            "market_cap_rank": 45,
                            "structure_clarity_score": 79,
                            "liquidity_score": 76,
                            "catalyst_score": 72,
                            "risk_boundary_score": 70,
                            "volatility_score": 64,
                            "observation": "ARB is setting up above support.",
                            "evidence": "Catalyst and structure remain aligned.",
                            "risk": "A failed retest invalidates the setup.",
                            "next_step": "Check follow-through tomorrow.",
                        },
                        {
                            "subject": "JTO",
                            "market_cap_rank": 140,
                            "structure_clarity_score": 73,
                            "liquidity_score": 58,
                            "catalyst_score": 87,
                            "risk_boundary_score": 61,
                            "volatility_score": 82,
                            "observation": "JTO is volatile but catalyst-rich.",
                            "evidence": "Momentum remains event-driven.",
                            "risk": "A failed breakout would invalidate the move.",
                            "next_step": "Monitor catalyst persistence.",
                        },
                        {
                            "subject": "ATOM",
                            "market_cap_rank": 50,
                            "structure_clarity_score": 77,
                            "liquidity_score": 71,
                            "catalyst_score": 63,
                            "risk_boundary_score": 68,
                            "volatility_score": 58,
                            "observation": "ATOM is constructive but less urgent.",
                            "evidence": "Relative strength improved modestly.",
                            "risk": "A rollover into the range invalidates the setup.",
                            "next_step": "Review after the next session.",
                        },
                    ],
                },
            )

            with patch.object(research_scan, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_scan,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ):
                result = research_scan.run_openclaw_research_scan(
                    market_scan_path=market_scan_path,
                    workbench_root=workbench_root,
                    incoming_root=incoming_root,
                    max_snapshots=3,
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["selected_snapshot_count"], 3)
            self.assertEqual(result["filtered_candidate_counts"]["stablecoin_or_pegged"], 1)
            selected = result["selected_snapshots"]
            selected_buckets = {item["asset_bucket"] for item in selected}
            self.assertIn("mid_cap", selected_buckets)
            self.assertIn("small_cap", selected_buckets)
            self.assertTrue(all(Path(item["snapshot_path"]).exists() for item in selected))
            self.assertTrue(all(Path(item["ohlcv_context_ref"]).exists() for item in selected))
            self.assertTrue(all(item["history_coverage"]["status"] == "full" for item in selected))
            summary_path = workbench_root / "_scan_runs" / "scan-001" / "scan_summary.json"
            self.assertTrue(summary_path.exists())
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["source"], "structural")
            self.assertEqual(summary_payload["incoming_root"], str(incoming_root.resolve()))

    def test_run_scan_respects_two_cycles_per_day_limit_for_same_thesis(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_scan_daily_limit_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            incoming_root = workbench_root / "_incoming"
            object_id = "sol-balanced-20260420"
            self._write_thesis_profile(
                workbench_root=workbench_root,
                object_id=object_id,
                subject="SOL",
                strategy_profile="conservative",
                asset_bucket="large_cap",
            )
            self._write_cycle_summary(
                workbench_root=workbench_root,
                object_id=object_id,
                cycle_id="sol-cycle-1",
                cycle_date="2026-04-20",
            )
            self._write_cycle_summary(
                workbench_root=workbench_root,
                object_id=object_id,
                cycle_id="sol-cycle-2",
                cycle_date="2026-04-20",
            )
            market_scan_path = self._write_market_scan(
                root,
                {
                    "scan_id": "scan-002",
                    "scan_date": "2026-04-20",
                    "candidates": [
                        {
                            "subject": "SOL",
                            "market_cap_rank": 6,
                            "structure_clarity_score": 82,
                            "liquidity_score": 86,
                            "catalyst_score": 68,
                            "risk_boundary_score": 74,
                            "volatility_score": 56,
                            "observation": "SOL remains above the shelf.",
                            "evidence": "Flow stayed constructive.",
                            "risk": "A breakdown invalidates the setup.",
                            "next_step": "Review after the next session.",
                        }
                    ],
                },
            )

            with patch.object(research_scan, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_scan,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ):
                result = research_scan.run_openclaw_research_scan(
                    market_scan_path=market_scan_path,
                    workbench_root=workbench_root,
                    incoming_root=incoming_root,
                )

            self.assertEqual(result["selected_snapshot_count"], 0)
            self.assertEqual(result["filtered_candidate_counts"]["daily_cycle_limit"], 1)

    def test_existing_unconsumed_snapshots_reduce_available_slots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_scan_slots_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            incoming_root = workbench_root / "_incoming"
            incoming_root.mkdir(parents=True, exist_ok=True)
            for cycle_id in ("pending-1", "pending-2"):
                (incoming_root / f"{cycle_id}.snapshot.json").write_text(
                    json.dumps(
                        {
                            "cycle_id": cycle_id,
                            "cycle_date": "2026-04-20",
                            "object_id": f"{cycle_id}-object",
                            "subject": cycle_id.upper(),
                            "scope": "spot+perp",
                            "strategy_profile": "balanced",
                            "asset_bucket": "mid_cap",
                            "observation": "Pending snapshot.",
                            "evidence": "Pending evidence.",
                            "risk": "Pending risk.",
                            "next_step": "Pending next step.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            market_scan_path = self._write_market_scan(
                root,
                {
                    "scan_id": "scan-003",
                    "scan_date": "2026-04-20",
                    "candidates": [
                        {
                            "subject": "ETH",
                            "market_cap_rank": 2,
                            "structure_clarity_score": 88,
                            "liquidity_score": 94,
                            "catalyst_score": 62,
                            "risk_boundary_score": 82,
                            "volatility_score": 45,
                            "observation": "ETH remains constructive.",
                            "evidence": "Spot leadership stayed healthy.",
                            "risk": "Loss of local support weakens the setup.",
                            "next_step": "Re-check after the next session.",
                        },
                        {
                            "subject": "ARB",
                            "market_cap_rank": 45,
                            "structure_clarity_score": 79,
                            "liquidity_score": 76,
                            "catalyst_score": 72,
                            "risk_boundary_score": 70,
                            "volatility_score": 64,
                            "observation": "ARB is setting up above support.",
                            "evidence": "Catalyst and structure remain aligned.",
                            "risk": "A failed retest invalidates the setup.",
                            "next_step": "Check follow-through tomorrow.",
                        },
                    ],
                },
            )

            with patch.object(research_scan, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_scan,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ):
                result = research_scan.run_openclaw_research_scan(
                    market_scan_path=market_scan_path,
                    workbench_root=workbench_root,
                    incoming_root=incoming_root,
                    max_snapshots=3,
                )

            self.assertEqual(result["unconsumed_snapshot_count_before_scan"], 2)
            self.assertEqual(result["available_snapshot_slots"], 1)
            self.assertEqual(result["selected_snapshot_count"], 1)

    def test_run_scan_accepts_utf8_bom_market_scan_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_scan_bom_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            market_scan_path = root / "market_scan_bom.json"
            market_scan_path.write_text(
                json.dumps(
                    {
                        "scan_id": "scan-bom",
                        "scan_date": "2026-04-20",
                        "candidates": [
                            {
                                "subject": "ETH",
                                "market_cap_rank": 2,
                                "structure_clarity_score": 88,
                                "liquidity_score": 94,
                                "catalyst_score": 62,
                                "risk_boundary_score": 82,
                                "volatility_score": 45,
                                "observation": "ETH remains constructive.",
                                "evidence": "Spot leadership stayed healthy.",
                                "risk": "Loss of local support weakens the setup.",
                                "next_step": "Re-check after the next session.",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8-sig",
            )

            with patch.object(research_scan, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_scan,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ):
                result = research_scan.run_openclaw_research_scan(
                    market_scan_path=market_scan_path,
                    workbench_root=workbench_root,
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["selected_snapshot_count"], 1)
            self.assertEqual(result["source"], "structural")
            self.assertEqual(result["incoming_root"], str((workbench_root / "_incoming_structural").resolve()))


if __name__ == "__main__":
    unittest.main()
