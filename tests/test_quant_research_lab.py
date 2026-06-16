from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta, timezone
import gzip
import io
import json
import math
import os
from pathlib import Path
import pandas as pd
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

from enhengclaw.quant_research.binance_derivatives import CSV_HEADERS as DERIVATIVE_HEADERS
from enhengclaw.quant_research.binance_derivatives import (
    as_of_sync_summary_path,
    sync_binance_derivatives_history,
    write_derivatives_sync_summary_for_as_of,
)
from enhengclaw.quant_research.alpha_manifest import build_daily_alpha_manifest_entry, write_daily_alpha_manifest
from enhengclaw.quant_research.contracts import QuantUniverseInput, utc_now
from enhengclaw.quant_research.data_readiness import (
    CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
    CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
)
from enhengclaw.quant_research.features import build_cross_sectional_features
from enhengclaw.quant_research.governance import build_strategy_entry, save_strategy_library
from enhengclaw.quant_research.lab import require_derivatives_sync_summary, run_quant_research_cycle, run_quant_universe_freeze
from enhengclaw.quant_research.legacy_experiments import archive_superseded_overlap_rerun_experiments
from enhengclaw.quant_research.ohlcv_lane_ab import run_quant_ohlcv_lane_ab
from enhengclaw.quant_research.runtime_support import run_quant_derivatives_sync_cycle
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input
from scripts.market_data.binance_ohlcv import CSV_HEADERS as OHLCV_HEADERS


class QuantResearchLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-research-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_inputs_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.ohlcv_root = self.temp_dir / "external" / "ohlcv"
        self.coinapi_spot_root = self.temp_dir / "external" / "coinapi_spot"
        self.derivatives_root = self.temp_dir / "external" / "derivatives"
        self.quant_inputs_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        self.localappdata_root = self.temp_dir / "localappdata"
        localappdata_patcher = patch.dict(
            os.environ,
            {
                "LOCALAPPDATA": str(self.localappdata_root),
                "CoinglassAPI": "",
                "COINGLASS_API_KEY": "",
                "COINGLASSAPI": "",
                "SOURCE_COMMIT_SHA": "abc123",
                "GITHUB_SHA": "",
            },
            clear=False,
        )
        localappdata_patcher.start()
        self.addCleanup(localappdata_patcher.stop)
        self._seed_quant_input()
        self._seed_market_history()

    def _save_executable_daily_single_asset_strategy(
        self,
        *,
        strategy_id: str = "daily-eth-logit",
        include_cross_sectional: bool = False,
    ) -> None:
        entries = [
            build_strategy_entry(
                strategy_id=strategy_id,
                shape="single_asset",
                strategy_profile="balanced",
                subject="ETH",
                universe_filter=None,
                model_family="logistic_regression",
                feature_groups=["core_context", "trend", "volume", "derivatives"],
                profile_constraints_override=None,
                source="proposal",
                status="active",
                research_lane="hypothesis_factor",
                promotion_eligibility="eligible",
                thesis_family="single_asset_crowding",
                requires_derivatives_features=True,
                daily_executable=True,
                thesis_profile={
                    "thesis_id": strategy_id,
                    "thesis_family": "single_asset_crowding",
                    "market_mechanism": "single-asset crowding reversal",
                    "directional_claim": "trade ETH when derivatives crowding and trend features align",
                    "universe_rule": {"subject": "ETH"},
                    "execution_venue": "perp",
                    "requires_derivatives_features": True,
                    "minimum_executable_history_days": 180,
                    "minimum_executable_coverage_ratio": 1.0,
                    "required_feature_columns": ["return_1", "funding_zscore_20", "oi_change_5", "basis_zscore_20"],
                    "factor_formula": "return_1 - funding_zscore_20",
                    "intended_holding_horizon_bars": 1,
                    "falsification_conditions": ["validation_return_negative"],
                    "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
                },
            )
        ]
        if include_cross_sectional:
            entries.append(
                build_strategy_entry(
                    strategy_id=f"{strategy_id}-cross",
                    shape="cross_sectional",
                    strategy_profile="balanced",
                    subject=None,
                    universe_filter={"liquidity_buckets": ["top_liquidity", "mid_liquidity", "tail_liquidity"]},
                    model_family="logistic_regression",
                    feature_groups=["core_context", "trend", "volume"],
                    profile_constraints_override=None,
                    source="proposal",
                    status="active",
                    research_lane="hypothesis_factor",
                    promotion_eligibility="eligible",
                    thesis_family="cross_sectional_rank",
                    requires_derivatives_features=False,
                    daily_executable=True,
                    thesis_profile={
                        "thesis_id": f"{strategy_id}-cross",
                        "thesis_family": "cross_sectional_rank",
                        "market_mechanism": "cross-sectional trend dispersion",
                        "directional_claim": "rank liquid names and rebalance into the strongest cohort",
                        "universe_rule": {"liquidity_buckets": ["top_liquidity", "mid_liquidity", "tail_liquidity"]},
                        "execution_venue": "spot",
                        "requires_derivatives_features": False,
                        "minimum_executable_history_days": 180,
                        "minimum_executable_coverage_ratio": 1.0,
                        "required_feature_columns": ["relative_strength_20"],
                        "factor_formula": "relative_strength_20",
                        "intended_holding_horizon_bars": 1,
                        "falsification_conditions": ["top_minus_bottom_return_non_positive"],
                        "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
                    },
                )
            )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": entries,
            },
        )

    def test_quant_universe_contract_fails_closed_on_missing_field(self) -> None:
        with self.assertRaises(ValueError):
            QuantUniverseInput.from_payload(
                {
                    "as_of": "2026-04-20",
                    "candidates": [
                        {
                            "subject": "ETH",
                            "market_cap_rank": 2,
                            "market_cap_usd": 10,
                            "quote_volume_24h_usd": 10,
                            "listing_age_days": 100,
                            "spot_symbol": "ETHUSDT",
                            "event_flags": [],
                        }
                    ],
                }
            )

    def test_derivatives_sync_writes_deduped_rows(self) -> None:
        base_time = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)

        def fake_http(url: str):
            if "fundingRate" in url:
                return [
                    {"fundingTime": base_time, "fundingRate": "0.0001"},
                    {"fundingTime": base_time + 8 * 60 * 60 * 1000, "fundingRate": "0.0002"},
                ]
            if "openInterestHist" in url:
                return [
                    {"timestamp": base_time, "sumOpenInterest": "1000", "sumOpenInterestValue": "2000000"},
                    {"timestamp": base_time + 4 * 60 * 60 * 1000, "sumOpenInterest": "1200", "sumOpenInterestValue": "2400000"},
                ]
            raise AssertionError(url)

        summary = sync_binance_derivatives_history(
            symbols=["ETHUSDT"],
            intervals=("4h",),
            mode="bootstrap",
            external_root=self.derivatives_root,
            http_get_json_fn=fake_http,
        )
        self.assertEqual(summary["status"], "success")
        manifest_path = self.derivatives_root / "ETHUSDT" / "4h" / "manifest.json"
        self.assertTrue(manifest_path.exists())
        partition_files = list((self.derivatives_root / "ETHUSDT" / "4h").glob("*.csv.gz"))
        self.assertTrue(partition_files)
        with gzip.open(partition_files[0], "rt", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 1)
        open_times = [int(row["open_time_ms"]) for row in rows]
        self.assertEqual(open_times, sorted(set(open_times)))

    def test_derivatives_sync_surfaces_provider_cap_warning_metadata(self) -> None:
        fixed_now = datetime(2026, 4, 22, 0, 0, tzinfo=UTC)
        start_time_ms = int((fixed_now - timedelta(days=730)).timestamp() * 1000)
        funding_start_ms = start_time_ms + (4 * 60 * 60 * 1000)
        open_interest_time_ms = int((fixed_now - timedelta(days=10)).timestamp() * 1000)

        def fake_http(url: str):
            if "fundingRate" in url:
                return [
                    {"fundingTime": funding_start_ms, "fundingRate": "0.0001"},
                    {"fundingTime": funding_start_ms + 8 * 60 * 60 * 1000, "fundingRate": "0.0002"},
                ]
            if "openInterestHist" in url:
                return [
                    {
                        "timestamp": open_interest_time_ms,
                        "sumOpenInterest": "1000",
                        "sumOpenInterestValue": "2000000",
                    }
                ]
            raise AssertionError(url)

        with patch("enhengclaw.quant_research.binance_derivatives.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
            summary = sync_binance_derivatives_history(
                symbols=["ETHUSDT"],
                intervals=("4h",),
                mode="bootstrap",
                external_root=self.derivatives_root,
                http_get_json_fn=fake_http,
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["coverage_validation"]["status"], "warning")
        self.assertIn("open_interest_provider_latest_window_cap", summary["coverage_validation"]["warning_codes"])
        result = summary["sync_results"][0]
        self.assertEqual(result["requested_window"]["lookback_days"], 730.0)
        self.assertTrue(result["field_coverage"]["open_interest"]["provider_capped"])
        self.assertEqual(
            result["field_coverage"]["open_interest"]["shortfall_reason"],
            "provider_latest_window_cap",
        )
        self.assertEqual(
            summary["provider_cap_summary"]["4h"]["open_interest_provider_capped_symbol_count"],
            1,
        )
        manifest = json.loads((self.derivatives_root / "ETHUSDT" / "4h" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["coverage_validation"]["status"], "warning")
        self.assertEqual(manifest["requested_window"]["lookback_days"], 730.0)

    def test_run_quant_derivatives_sync_cycle_uses_only_usdm_symbols(self) -> None:
        isolated_input_root = self.temp_dir / "isolated_quant_inputs"
        isolated_input_root.mkdir(parents=True, exist_ok=True)
        write_pit_quant_input(
            root=isolated_input_root,
            as_of="2026-04-22",
            candidates=[
                pit_candidate("ETH", 2, listing_age_days_as_of=2200),
                pit_candidate("SPOTONLY", 50, usdm_symbol=None, first_perp_bar_utc=None, listing_age_days_as_of=200),
            ],
        )

        with patch("enhengclaw.quant_research.runtime_support.sync_binance_derivatives_history") as mock_sync:
            mock_sync.return_value = {"status": "success", "sync_results": []}
            run_quant_derivatives_sync_cycle(
                as_of="2026-04-22",
                quant_input_root=isolated_input_root,
                derivatives_external_root=self.derivatives_root,
                mode="bootstrap",
                intervals=("4h",),
            )

        self.assertEqual(mock_sync.call_args.kwargs["symbols"], ["ETHUSDT"])
        self.assertEqual(mock_sync.call_args.kwargs["intervals"], ("4h",))
        self.assertEqual(mock_sync.call_args.kwargs["mode"], "bootstrap")
        self.assertEqual(mock_sync.call_args.kwargs["as_of"], "2026-04-22")

    def test_run_quant_derivatives_sync_cycle_writes_by_as_of_archive(self) -> None:
        fixed_now = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)
        base_time = int((fixed_now - timedelta(hours=8)).timestamp() * 1000)

        def fake_http(url: str):
            if "fundingRate" in url:
                return [
                    {"fundingTime": base_time, "fundingRate": "0.0001"},
                    {"fundingTime": base_time + 8 * 60 * 60 * 1000, "fundingRate": "0.0002"},
                ]
            if "openInterestHist" in url:
                return [
                    {"timestamp": base_time, "sumOpenInterest": "1000", "sumOpenInterestValue": "2000000"},
                    {"timestamp": base_time + 4 * 60 * 60 * 1000, "sumOpenInterest": "1200", "sumOpenInterestValue": "2400000"},
                ]
            raise AssertionError(url)

        with patch("enhengclaw.quant_research.binance_derivatives.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("enhengclaw.quant_research.binance_derivatives._http_get_json", side_effect=fake_http):
                summary = run_quant_derivatives_sync_cycle(
                    as_of="2026-04-20",
                    quant_input_root=self.quant_inputs_root,
                    derivatives_external_root=self.derivatives_root,
                    mode="bootstrap",
                    intervals=("4h",),
                )

        archived_path = Path(str(summary["by_as_of_summary_path"]))
        self.assertTrue(archived_path.exists())
        archived_summary = json.loads(archived_path.read_text(encoding="utf-8"))
        self.assertEqual(archived_summary["summary_scope"], "by_as_of")
        self.assertEqual(archived_summary["as_of"], "2026-04-20")
        self.assertEqual(archived_summary["required_intervals"], ["4h"])
        self.assertEqual(
            archived_path,
            as_of_sync_summary_path(external_root=self.derivatives_root, as_of="2026-04-20"),
        )

    def test_write_derivatives_sync_summary_for_as_of_trims_rows_to_as_of_end(self) -> None:
        symbol = "TRIMUSDT"
        interval = "4h"
        interval_ms = 14_400_000
        as_of = "2026-04-20"
        before_open = int(datetime(2026, 4, 20, 20, 0, tzinfo=UTC).timestamp() * 1000)
        after_open = int(datetime(2026, 4, 21, 0, 0, tzinfo=UTC).timestamp() * 1000)
        self._write_partitioned_rows(
            root=self.derivatives_root / symbol / interval,
            headers=DERIVATIVE_HEADERS,
            rows=[
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(before_open),
                    "close_time_ms": str(before_open + interval_ms - 1),
                    "funding_rate": "0.0001000000",
                    "funding_sample_count": "1",
                    "open_interest": "1000.0000000000",
                    "open_interest_value": "2000000.0000000000",
                    "source": "test",
                },
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(after_open),
                    "close_time_ms": str(after_open + interval_ms - 1),
                    "funding_rate": "0.0002000000",
                    "funding_sample_count": "1",
                    "open_interest": "1100.0000000000",
                    "open_interest_value": "2200000.0000000000",
                    "source": "test",
                },
            ],
        )

        summary, summary_path = write_derivatives_sync_summary_for_as_of(
            as_of=as_of,
            symbols=[symbol],
            intervals=(interval,),
            external_root=self.derivatives_root,
        )

        result = summary["sync_results"][0]
        self.assertEqual(result["stored_row_count"], 1)
        self.assertEqual(summary["window_end_ms"], int(datetime(2026, 4, 20, 23, 59, 59, tzinfo=UTC).timestamp() * 1000))
        self.assertEqual(Path(summary_path), as_of_sync_summary_path(external_root=self.derivatives_root, as_of=as_of))

    def test_write_derivatives_sync_summary_for_as_of_fails_when_required_interval_missing(self) -> None:
        symbol = "MISSUSDT"
        open_time = int(datetime(2026, 4, 20, 0, 0, tzinfo=UTC).timestamp() * 1000)
        self._write_partitioned_rows(
            root=self.derivatives_root / symbol / "4h",
            headers=DERIVATIVE_HEADERS,
            rows=[
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": "4h",
                    "open_time_ms": str(open_time),
                    "close_time_ms": str(open_time + 14_400_000 - 1),
                    "funding_rate": "0.0001000000",
                    "funding_sample_count": "1",
                    "open_interest": "1000.0000000000",
                    "open_interest_value": "2000000.0000000000",
                    "source": "test",
                }
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "MISSUSDT:1d"):
            write_derivatives_sync_summary_for_as_of(
                as_of="2026-04-20",
                symbols=[symbol],
                intervals=("4h", "1d"),
                external_root=self.derivatives_root,
            )

    def test_quant_research_cycle_surfaces_derivatives_warning_summary(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20", warning=True)
        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["derivatives_coverage_validation"]["status"], "warning")
        self.assertEqual(summary["derivatives_coverage_validation"]["warning_count"], 1)
        self.assertEqual(
            summary["derivatives_provider_cap_summary"]["4h"]["open_interest_provider_capped_symbol_count"],
            1,
        )
        self.assertTrue(
            str(summary["derivatives_sync_summary_path"]).replace("\\", "/").endswith(
                "summaries/by_as_of/2026-04-20/sync_summary.json"
            )
        )
        self.assertEqual(summary["derivatives_sync_warning_symbols"][0]["symbol"], "ETHUSDT")
        self.assertIn("dataset_derivatives_quality", summary)
        self.assertIn("feature_derivatives_quality_highlights", summary)
        self.assertIn("strategy_derivatives_quality_highlights", summary)
        single_dataset_quality = summary["dataset_derivatives_quality"]["2026-04-20-single-asset-4h"]
        self.assertIn("funding_coverage_days", single_dataset_quality)
        self.assertIn("open_interest_coverage_days", single_dataset_quality)
        self.assertIn("funding_minus_open_interest_gap_days", single_dataset_quality)
        self.assertIn("open_interest_provider_latest_window_cap", single_dataset_quality["warning_counts"])

    def test_cross_sectional_features_do_not_forward_fill_open_interest_gaps(self) -> None:
        rows: list[dict[str, object]] = []
        open_interest_values = [100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 110.0, 120.0]
        for index, open_interest in enumerate(open_interest_values):
            rows.append(
                {
                    "subject": "ETH",
                    "timestamp_ms": index * 14_400_000,
                    "spot_close": 100.0 + index,
                    "spot_high": 101.0 + index,
                    "spot_low": 99.0 + index,
                    "spot_quote_volume": 1_000_000.0 + (index * 10_000.0),
                    "open_interest": open_interest,
                    "funding_rate": 0.0001,
                    "basis_proxy": 0.0,
                    "market_cap_rank": 1,
                }
            )
        features = build_cross_sectional_features(panel=pd.DataFrame(rows))
        target_row = features.loc[features["timestamp_ms"] == 6 * 14_400_000].iloc[0]
        self.assertEqual(float(target_row["oi_change_5"]), 0.0)

    def test_quant_research_cycle_freezes_cross_sectional_daily_lane_on_thin_coverage(self) -> None:
        broad_candidates = [
            pit_candidate("ETH", 2, listing_age_days_as_of=2200, selection_score=18_000_000_000.0),
            pit_candidate("SUI", 28, listing_age_days_as_of=650, selection_score=1_400_000_000.0),
            pit_candidate("JTO", 95, listing_age_days_as_of=500, selection_score=280_000_000.0),
        ]
        for rank in range(4, 101):
            broad_candidates.append(
                pit_candidate(
                    f"T{rank:03d}",
                    rank,
                    listing_age_days_as_of=400 + rank,
                    selection_score=float(500_000_000 - (rank * 1_000_000)),
                    usdm_symbol=None,
                )
            )
        write_pit_quant_input(
            root=self.quant_inputs_root,
            as_of="2026-04-20",
            candidates=broad_candidates,
        )
        cross_entry = build_strategy_entry(
            strategy_id="daily-cross-logit",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"liquidity_buckets": ["top_liquidity", "mid_liquidity"]},
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "volume"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_factor",
            promotion_eligibility="eligible",
            thesis_family="cross_sectional_rank",
            requires_derivatives_features=False,
            daily_executable=True,
            thesis_profile={
                "thesis_id": "daily-cross-logit",
                "thesis_family": "cross_sectional_rank",
                "market_mechanism": "cross-sectional momentum dispersion",
                "directional_claim": "rank liquid names and rebalance into the strongest cohort",
                "universe_rule": {"liquidity_buckets": ["top_liquidity", "mid_liquidity"]},
                "execution_venue": "spot",
                "requires_derivatives_features": False,
                "minimum_executable_history_days": 365,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["relative_strength_20"],
                "factor_formula": "relative_strength_20",
                "intended_holding_horizon_bars": 1,
                "falsification_conditions": ["top_minus_bottom_return_non_positive"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [cross_entry],
            },
        )
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")

        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )

        coverage = summary["spot_subject_coverage"]["2026-04-20-cross-sectional-daily-1d"]
        self.assertEqual(summary["daily_strategy_count"], 2)
        self.assertIn("core-liquidity-balanced-ranking-scorer-cross-sectional", summary["blocked_strategy_ids"])
        self.assertIn("core-liquidity-balanced-ranking-scorer-intraday-cross-sectional", summary["blocked_strategy_ids"])
        self.assertIn(CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER, summary["data_gap_blockers"])
        self.assertIn(CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER, summary["data_gap_blockers"])
        self.assertEqual(summary["readiness_verdict"], "blocked")
        self.assertEqual(summary["cross_sectional_executable_subject_count"], 3)
        self.assertAlmostEqual(float(coverage["coverage_fraction"]), 0.03)
        self.assertFalse(coverage["coverage_requirement_met"])
        self.assertEqual(int(coverage["required_subject_count_min"]), 85)

    def test_quant_research_cycle_smoke_and_bridge(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["universe_count"], 3)
        self.assertEqual(summary["spot_provider_lane"], "binance_only")
        self.assertIn(f"{summary['as_of']}-single-asset-4h", summary["dataset_subject_counts"])
        self.assertIn(f"{summary['as_of']}-cross-sectional-daily-1d", summary["dataset_subject_counts"])
        self.assertIn(f"{summary['as_of']}-cross-sectional-intraday-1h", summary["dataset_subject_counts"])
        self.assertEqual(summary["trainable_strategy_count"], 1)
        self.assertEqual(summary["experiment_count"], 4)
        self.assertTrue(Path(summary["summary_path"]).exists())
        self.assertTrue(Path(summary["markdown_path"]).exists())
        self.assertTrue(
            str(summary["derivatives_sync_summary_path"]).replace("\\", "/").endswith(
                "summaries/by_as_of/2026-04-20/sync_summary.json"
            )
        )
        self.assertEqual(summary["strategy_manifest_enabled_count"], 4)
        self.assertEqual(summary["daily_strategy_count"], 4)
        self.assertEqual(summary["cross_sectional_executable_subject_count"], 3)
        self.assertIn("research_dataset_minimum_executable_history_failed", summary["data_gap_blockers"])
        self.assertGreaterEqual(len(summary["blocked_strategy_ids"]), 0)
        self.assertEqual(summary["derivatives_coverage_validation"]["status"], "ok")
        self.assertIn("4h", summary["derivatives_provider_cap_summary"])
        self.assertIn("dataset_derivatives_quality", summary)
        self.assertIn("feature_derivatives_quality_highlights", summary)
        self.assertIn("strategy_derivatives_quality_highlights", summary)

    def test_quant_research_cycle_applies_strict_feature_admission_policy(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        forbidden = {
            "timestamp_ms",
            "open_time_ms",
            "close_time_ms",
            "daily_open_time_ms",
            "spot_open",
            "spot_high",
            "spot_low",
            "spot_close",
            "perp_close",
            "daily_close",
            "selection_rank",
            "selection_score",
            "rolling_median_quote_volume_usd_30d",
            "rolling_mean_quote_volume_usd_30d",
            "listing_age_days_as_of",
            "ema_fast",
            "ema_slow",
            "sma_20",
            "sma_60",
            "spot_volume",
            "spot_quote_volume",
            "perp_volume",
            "daily_quote_volume",
            "intraday_quote_volume_4h",
            "intraday_quote_volume_1d",
            "open_interest",
            "open_interest_value",
            "funding_sample_count",
            "has_perp_as_of",
        }
        for manifest_path in summary["feature_manifests"]:
            feature_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(
                feature_manifest["feature_admission_policy"]["contract_version"],
                "quant_feature_admission_policy.v1",
            )
            self.assertFalse(set(feature_manifest["numeric_feature_columns"]).intersection(forbidden))
            self.assertTrue(
                set(feature_manifest["excluded_numeric_columns"]).intersection(
                    {"timestamp_ms", "selection_rank", "rolling_median_quote_volume_usd_30d"}
                )
            )
        for experiment_spec_path in (self.artifacts_root / "experiments").glob("*/experiment_spec.json"):
            experiment_spec = json.loads(experiment_spec_path.read_text(encoding="utf-8"))
            self.assertEqual(
                experiment_spec["feature_admission_policy"]["contract_version"],
                "quant_feature_admission_policy.v1",
            )
            self.assertFalse(set(experiment_spec.get("feature_columns", [])).intersection(forbidden))
            self.assertTrue(
                set(experiment_spec.get("feature_columns", [])).issubset(
                    set(experiment_spec.get("numeric_feature_columns", []))
                )
            )

    def test_quant_research_cycle_repeated_runs_keep_thesis_queue_utilization(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        first = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        second = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )

        self.assertEqual(first["daily_strategy_count"], 4)
        self.assertEqual(second["daily_strategy_count"], 4)
        self.assertEqual(first["daily_strategy_ids"], second["daily_strategy_ids"])
        self.assertEqual(first["experiment_ids"], second["experiment_ids"])
        self.assertEqual(first["summary_hash"], second["summary_hash"])

    def test_archive_superseded_overlap_rerun_experiments_moves_non_canonical_stale_dirs(self) -> None:
        self._save_executable_daily_single_asset_strategy(include_cross_sectional=True)
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        self._refresh_daily_manifest(as_of="2026-04-20")
        manifest_path = self.artifacts_root / "governance" / "daily_alpha_manifests" / "2026-04-20.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["entries"][0]
        canonical_alpha_card_path = Path(entry["alpha_card_path"])
        if not canonical_alpha_card_path.is_absolute():
            canonical_alpha_card_path = ROOT / canonical_alpha_card_path
        canonical_experiment_root = canonical_alpha_card_path.parent
        stale_dir_name = f"{entry['experiment_id']}-stale-copy"
        stale_root = self.artifacts_root / "experiments" / stale_dir_name
        shutil.copytree(canonical_experiment_root, stale_root)
        self._rewrite_experiment_status(
            experiment_root=stale_root,
            experiment_status="needs_rerun_after_overlap_fix",
            reason="overlap_fix_pending_rerun",
        )

        cleanup_summary = archive_superseded_overlap_rerun_experiments(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
        )

        self.assertEqual(cleanup_summary["archived_experiment_count"], 1)
        self.assertFalse(stale_root.exists())
        archived_root = self.artifacts_root / "experiments" / "legacy" / "overlap_rerun_superseded" / "2026-04-20" / stale_dir_name
        self.assertTrue(archived_root.exists())
        archived_alpha_card = json.loads((archived_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(archived_alpha_card["experiment_status"], "superseded_by_overlap_rerun")
        self.assertEqual(archived_alpha_card["reason"], "superseded_by_overlap_rerun")
        self.assertEqual(
            archived_alpha_card["legacy_archive"]["canonical_alpha_card_path"],
            entry["alpha_card_path"],
        )
        feature_highlight = summary["feature_derivatives_quality_highlights"][f"{summary['as_of']}-single-asset-4h-features-v1"]
        self.assertIn("funding_zscore_20", feature_highlight)
        self.assertIn("oi_change_5", feature_highlight)
        self.assertIn("basis_zscore_20", feature_highlight)
        for manifest_path in summary["feature_manifests"]:
            feature_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertGreater(feature_manifest["bar_interval_ms"], 0)
            self.assertIn("split_realization_contract", feature_manifest)
            self.assertEqual(
                feature_manifest["split_realization_contract"]["realization_step_bars"],
                feature_manifest["realization_step_bars"],
            )
            self.assertEqual(
                feature_manifest["split_realization_contract"]["partition_gap_bars"],
                feature_manifest["partition_gap_bars"],
            )

        strategy_quality_summary = summary["strategy_derivatives_quality_highlights"]
        self.assertIn(
            "experiment_count_using_derivatives_features",
            strategy_quality_summary,
        )

        sample_experiment_root = None
        for experiment_root in sorted((self.artifacts_root / "experiments").iterdir()):
            alpha_card_path = experiment_root / "alpha_card.json"
            if not alpha_card_path.exists():
                continue
            alpha_card_candidate = json.loads(alpha_card_path.read_text(encoding="utf-8"))
            if "derivatives_strategy_quality" in alpha_card_candidate:
                sample_experiment_root = experiment_root
                break
        self.assertIsNotNone(sample_experiment_root)
        self.assertGreaterEqual(
            strategy_quality_summary["experiment_count_using_derivatives_features"],
            0,
        )
        validation_report = json.loads((canonical_experiment_root / "validation_report.json").read_text(encoding="utf-8"))
        alpha_card = json.loads((canonical_experiment_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertIn("derivatives_strategy_quality", validation_report)
        self.assertIn("derivatives_strategy_quality", alpha_card)
        self.assertIn("validation_contract", validation_report)
        self.assertIn("split_integrity", validation_report)
        self.assertIn("feature_admission", validation_report)
        self.assertIn("factor_evidence", validation_report)
        self.assertIn("walk_forward_assessment", validation_report)
        self.assertIn("execution_stress", validation_report)
        self.assertIn("regime_holdout", validation_report)
        self.assertIn("split_realization_contract", validation_report)
        self.assertIn("validation_contract", alpha_card)
        self.assertIn("feature_admission", alpha_card)
        self.assertIn("factor_evidence", alpha_card)
        self.assertIn("split_realization_contract", alpha_card)
        self.assertIn("funding_family", alpha_card["derivatives_strategy_quality"])
        self.assertIn("open_interest_family", alpha_card["derivatives_strategy_quality"])
        self.assertIn("data_gap_blockers", validation_report)
        self.assertIn("data_gap_blockers", alpha_card)
        self.assertEqual(validation_report["validation_contract"]["contract_version"], "quant_validation_contract.v10")
        self.assertEqual(alpha_card["validation_contract"]["contract_version"], "quant_validation_contract.v10")
        self.assertIn("execution_cost_model", validation_report)
        self.assertIn("execution_cost_model", alpha_card)
        self.assertEqual(validation_report["execution_cost_model"]["contract_version"], "quant_execution_cost_model.v1")
        self.assertIn("frictionless_metrics", validation_report)
        self.assertIn("frictionless_metrics", alpha_card)
        self.assertIn("reproducibility", validation_report)
        self.assertIn("reproducibility", alpha_card)
        self.assertEqual(validation_report["source_commit_sha"], "abc123")
        self.assertEqual(alpha_card["source_commit_sha"], "abc123")
        self.assertTrue(validation_report["dataset_fingerprint"])
        self.assertTrue(validation_report["feature_hash"])
        self.assertTrue(validation_report["reproducibility"]["passed"])
        self.assertEqual(validation_report["split_integrity"]["split_boundary_contamination_total"], 0)
        self.assertEqual(validation_report["split_integrity"]["walk_forward_boundary_contamination_total"], 0)
        self.assertIn(
            validation_report["validation_contract"]["status"],
            {"passed", "failed", "incomplete", "falsification_required"},
        )

        cross_sectional_experiment_root = None
        for experiment_root in sorted((self.artifacts_root / "experiments").iterdir()):
            alpha_card_path = experiment_root / "alpha_card.json"
            if not alpha_card_path.exists():
                continue
            alpha_card_candidate = json.loads(alpha_card_path.read_text(encoding="utf-8"))
            if alpha_card_candidate.get("shape") == "cross_sectional":
                cross_sectional_experiment_root = experiment_root
                break
        self.assertIsNotNone(cross_sectional_experiment_root)
        cross_validation_report = json.loads((cross_sectional_experiment_root / "validation_report.json").read_text(encoding="utf-8"))
        cross_alpha_card = json.loads((cross_sectional_experiment_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(cross_validation_report["data_gap_blockers"], cross_alpha_card["data_gap_blockers"])
        self.assertTrue(all(isinstance(item, str) for item in cross_validation_report["data_gap_blockers"]))
        self.assertIn("execution_stress", cross_validation_report)
        self.assertIn("regime_holdout", cross_validation_report)

    def test_quant_ohlcv_lane_ab_expands_subjects_with_spot_split_root(self) -> None:
        binance_lane_root = self.temp_dir / "external" / "binance_lane"
        self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=binance_lane_root, market_type="spot", symbol="ETHUSDT")
        for symbol in ("ETHUSDT", "SUIUSDT", "JTOUSDT"):
            self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=binance_lane_root, market_type="usdm_perp", symbol=symbol)
        for symbol in ("SUIUSDT", "JTOUSDT"):
            self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=self.coinapi_spot_root, market_type="spot", symbol=symbol)

        self._write_derivatives_sync_summary(as_of="2026-04-20")
        summary = run_quant_ohlcv_lane_ab(
            as_of="2026-04-20",
            quant_input_root=self.quant_inputs_root,
            ohlcv_external_root=binance_lane_root,
            spot_ohlcv_external_root=self.coinapi_spot_root,
            derivatives_external_root=self.derivatives_root,
            output_root=self.temp_dir / "benchmarks" / "lane_ab",
        )

        self.assertEqual(summary["status"], "success")
        baseline = summary["lane_results"]["binance_only"]
        mixed = summary["lane_results"]["coinapi_spot_binance_fallback"]
        self.assertEqual(baseline["dataset_subject_counts"]["2026-04-20-single-asset-4h"], 1)
        self.assertEqual(baseline["dataset_subject_counts"]["2026-04-20-cross-sectional-daily-1d"], 1)
        self.assertEqual(baseline["dataset_subject_counts"]["2026-04-20-cross-sectional-intraday-1h"], 1)
        self.assertEqual(mixed["dataset_subject_counts"]["2026-04-20-single-asset-4h"], 3)
        self.assertEqual(mixed["dataset_subject_counts"]["2026-04-20-cross-sectional-daily-1d"], 3)
        self.assertEqual(mixed["dataset_subject_counts"]["2026-04-20-cross-sectional-intraday-1h"], 3)
        self.assertGreaterEqual(summary["comparison"]["train_split_row_count_total_delta"], 0)
        self.assertGreater(
            summary["comparison"]["dataset_row_count_delta"]["2026-04-20-single-asset-4h"],
            0,
        )

    def test_quant_research_cycle_auto_detects_default_coinapi_spot_root(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        binance_lane_root = self.temp_dir / "external" / "binance_lane_autodetect"
        self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=binance_lane_root, market_type="spot", symbol="ETHUSDT")
        for symbol in ("ETHUSDT", "SUIUSDT", "JTOUSDT"):
            self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=binance_lane_root, market_type="usdm_perp", symbol=symbol)
        autodetect_spot_root = self.localappdata_root / "EnhengClaw" / "market_history" / "coinapi_ohlcv"
        for symbol in ("SUIUSDT", "JTOUSDT"):
            self._copy_symbol_tree(source_root=self.ohlcv_root, dest_root=autodetect_spot_root, market_type="spot", symbol=symbol)

        self._write_derivatives_sync_summary(as_of="2026-04-20")
        summary = run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=binance_lane_root,
            derivatives_external_root=self.derivatives_root,
        )

        self.assertEqual(summary["spot_provider_lane"], "coinapi_spot_binance_fallback")
        self.assertEqual(summary["dataset_subject_counts"]["2026-04-20-single-asset-4h"], 3)
        self.assertEqual(summary["dataset_subject_counts"]["2026-04-20-cross-sectional-daily-1d"], 3)
        self.assertEqual(summary["dataset_subject_counts"]["2026-04-20-cross-sectional-intraday-1h"], 3)
        self.assertTrue(Path(summary["summary_path"]).exists())
        self.assertTrue(Path(summary["markdown_path"]).exists())

    def test_quant_universe_freeze_fails_closed_when_exact_date_input_is_missing(self) -> None:
        stale_root = self.temp_dir / "stale_quant_inputs"
        stale_root.mkdir(parents=True, exist_ok=True)
        write_pit_quant_input(
            root=stale_root,
            as_of="2026-04-15",
            candidates=[pit_candidate("ETH", 2, listing_age_days_as_of=2200)],
        )

        with self.assertRaisesRegex(FileNotFoundError, "2026-04-20"):
            run_quant_universe_freeze(
                as_of="2026-04-20",
                artifacts_root=self.artifacts_root,
                quant_input_root=stale_root,
            )

    def test_require_derivatives_sync_summary_accepts_previous_utc_day_when_local_day_matches(self) -> None:
        self.derivatives_root.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "success",
            "generated_at_utc": "2026-04-20T19:07:34Z",
            "produced_at_utc": "2026-04-20T19:07:34Z",
        }
        (self.derivatives_root / "last_sync_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        with patch("enhengclaw.quant_research.lab._resolve_quant_local_timezone", return_value=timezone(timedelta(hours=8))):
            loaded_summary, loaded_path = require_derivatives_sync_summary(
                as_of="2026-04-21",
                derivatives_external_root=self.derivatives_root,
            )

        self.assertEqual(loaded_summary["generated_at_utc"], "2026-04-20T19:07:34Z")
        self.assertEqual(loaded_path, self.derivatives_root / "last_sync_summary.json")

    def test_require_derivatives_sync_summary_accepts_historical_rerun_with_next_local_day(self) -> None:
        self.derivatives_root.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "success",
            "generated_at_utc": "2026-04-20T19:07:34Z",
            "produced_at_utc": "2026-04-20T19:07:34Z",
        }
        (self.derivatives_root / "last_sync_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        with patch("enhengclaw.quant_research.lab._resolve_quant_local_timezone", return_value=timezone(timedelta(hours=8))):
            with patch("enhengclaw.quant_research.lab.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 4, 21, 12, 0, tzinfo=timezone(timedelta(hours=8)))
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                mock_datetime.strptime.side_effect = datetime.strptime
                loaded_summary, loaded_path = require_derivatives_sync_summary(
                    as_of="2026-04-20",
                    derivatives_external_root=self.derivatives_root,
                )

        self.assertEqual(loaded_summary["generated_at_utc"], "2026-04-20T19:07:34Z")
        self.assertEqual(loaded_path, self.derivatives_root / "last_sync_summary.json")

    def test_require_derivatives_sync_summary_rejects_previous_local_day(self) -> None:
        self.derivatives_root.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "success",
            "generated_at_utc": "2026-04-20T14:59:59Z",
            "produced_at_utc": "2026-04-20T14:59:59Z",
        }
        (self.derivatives_root / "last_sync_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        with patch("enhengclaw.quant_research.lab._resolve_quant_local_timezone", return_value=timezone(timedelta(hours=8))):
            with self.assertRaisesRegex(RuntimeError, "local_date=2026-04-20"):
                require_derivatives_sync_summary(
                    as_of="2026-04-21",
                    derivatives_external_root=self.derivatives_root,
                )

    def test_require_derivatives_sync_summary_prefers_archived_as_of_summary(self) -> None:
        self._write_derivatives_sync_summary(as_of="2026-04-22", write_archive=False)
        self._write_derivatives_sync_summary(as_of="2026-04-20", write_last=False, write_archive=True)

        loaded_summary, loaded_path = require_derivatives_sync_summary(
            as_of="2026-04-20",
            derivatives_external_root=self.derivatives_root,
        )

        self.assertEqual(loaded_summary["as_of"], "2026-04-20")
        self.assertEqual(
            loaded_path,
            as_of_sync_summary_path(external_root=self.derivatives_root, as_of="2026-04-20"),
        )

    def test_require_derivatives_sync_summary_rejects_archived_summary_window_after_as_of(self) -> None:
        self._write_derivatives_sync_summary(
            as_of="2026-04-20",
            write_last=False,
            write_archive=True,
            summary_overrides={
                "window_end_ms": int(datetime(2026, 4, 21, 0, 0, tzinfo=UTC).timestamp() * 1000),
            },
        )

        with self.assertRaisesRegex(RuntimeError, "window_end_ms exceeds as_of=2026-04-20"):
            require_derivatives_sync_summary(
                as_of="2026-04-20",
                derivatives_external_root=self.derivatives_root,
            )

    def test_require_derivatives_sync_summary_rejects_historical_rerun_without_matching_archive(self) -> None:
        self._write_derivatives_sync_summary(as_of="2026-04-22", write_archive=False)

        with patch("enhengclaw.quant_research.lab._resolve_quant_local_timezone", return_value=timezone(timedelta(hours=8))):
            with patch("enhengclaw.quant_research.lab.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 4, 22, 12, 0, tzinfo=timezone(timedelta(hours=8)))
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                mock_datetime.strptime.side_effect = datetime.strptime
                with self.assertRaisesRegex(RuntimeError, "stale for 2026-04-20"):
                    require_derivatives_sync_summary(
                        as_of="2026-04-20",
                        derivatives_external_root=self.derivatives_root,
                    )

    def test_quant_research_cycle_fails_closed_without_source_commit_sha(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        with patch("enhengclaw.ops.evidence_contracts.current_source_commit_sha", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "source_commit_sha is required"):
                run_quant_research_cycle(
                    as_of="2026-04-20",
                    artifacts_root=self.artifacts_root,
                    quant_input_root=self.quant_inputs_root,
                    workbench_root=self.workbench_root,
                    ohlcv_external_root=self.ohlcv_root,
                    derivatives_external_root=self.derivatives_root,
                )

    def _seed_quant_input(self) -> None:
        write_pit_quant_input(
            root=self.quant_inputs_root,
            as_of="2026-04-20",
            candidates=[
                pit_candidate("ETH", 2, listing_age_days_as_of=2200, selection_score=18_000_000_000.0),
                pit_candidate("SUI", 28, listing_age_days_as_of=650, selection_score=1_400_000_000.0),
                pit_candidate("JTO", 95, listing_age_days_as_of=500, selection_score=280_000_000.0),
            ],
        )

    def _seed_market_history(self) -> None:
        start_daily = datetime(2025, 9, 1, tzinfo=UTC)
        start_4h = datetime(2025, 12, 1, tzinfo=UTC)
        start_1h = datetime(2026, 2, 1, tzinfo=UTC)
        specs = [
            ("ETHUSDT", 2500.0, 0.004, 0.02),
            ("SUIUSDT", 1.2, 0.006, 0.05),
            ("JTOUSDT", 2.0, 0.008, 0.08),
        ]
        for symbol, base_price, drift, wiggle in specs:
            self._write_ohlcv_series("spot", symbol, "1d", start_daily, 230, base_price, drift, wiggle)
            self._write_ohlcv_series("spot", symbol, "4h", start_4h, 1100, base_price, drift / 6.0, wiggle / 2.0)
            self._write_ohlcv_series("spot", symbol, "1h", start_1h, 1600, base_price, drift / 24.0, wiggle / 3.0)
            self._write_ohlcv_series("usdm_perp", symbol, "1d", start_daily, 230, base_price * 1.001, drift * 1.05, wiggle)
            self._write_ohlcv_series("usdm_perp", symbol, "4h", start_4h, 1100, base_price * 1.001, drift / 6.0, wiggle / 2.0)
            self._write_derivative_series(symbol, "4h", start_4h, 1100)
            self._write_derivative_series(symbol, "1d", start_daily, 230)

    def _write_ohlcv_series(
        self,
        market_type: str,
        symbol: str,
        interval: str,
        start: datetime,
        periods: int,
        base_price: float,
        drift: float,
        wiggle: float,
    ) -> None:
        interval_delta = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        current_price = base_price
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            oscillation = math.sin(index / 7.0) * wiggle
            close_price = current_price * (1.0 + drift + oscillation / 100.0)
            high_price = max(current_price, close_price) * 1.01
            low_price = min(current_price, close_price) * 0.99
            volume = 1_000_000 + (index * 500)
            quote_volume = volume * ((current_price + close_price) / 2.0)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": market_type,
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "open": f"{current_price:.8f}",
                    "high": f"{high_price:.8f}",
                    "low": f"{low_price:.8f}",
                    "close": f"{close_price:.8f}",
                    "volume": f"{volume:.8f}",
                    "quote_volume": f"{quote_volume:.8f}",
                    "trade_count": "1000",
                    "taker_buy_base_volume": f"{volume * 0.51:.8f}",
                    "taker_buy_quote_volume": f"{quote_volume * 0.51:.8f}",
                    "source": "test",
                }
            )
            current_price = close_price
        self._write_partitioned_rows(
            root=self.ohlcv_root / market_type / symbol / interval,
            headers=OHLCV_HEADERS,
            rows=rows,
        )

    def _write_derivative_series(self, symbol: str, interval: str, start: datetime, periods: int) -> None:
        interval_delta = {"4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "funding_rate": f"{0.0001 + (index % 5) * 0.00001:.10f}",
                    "funding_sample_count": "1",
                    "open_interest": f"{1_000_000 + (index * 10_000):.10f}",
                    "open_interest_value": f"{50_000_000 + (index * 500_000):.10f}",
                    "source": "test",
                }
            )
        self._write_partitioned_rows(
            root=self.derivatives_root / symbol / interval,
            headers=DERIVATIVE_HEADERS,
            rows=rows,
        )

    def _write_partitioned_rows(self, *, root: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        monthly: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            open_time_ms = int(row["open_time_ms"])
            month_key = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).strftime("%Y-%m")
            monthly.setdefault(month_key, []).append(row)
        root.mkdir(parents=True, exist_ok=True)
        for month_key, month_rows in monthly.items():
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=headers)
            writer.writeheader()
            writer.writerows(month_rows)
            with gzip.open(root / f"{month_key}.csv.gz", "wt", encoding="utf-8", newline="") as handle:
                handle.write(buffer.getvalue())
        manifest = {
            "generated_at_utc": utc_now(),
            "total_rows": len(rows),
            "coverage_days": 999,
            "partitions": sorted(f"{month}.csv.gz" for month in monthly),
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _rewrite_experiment_status(self, *, experiment_root: Path, experiment_status: str, reason: str) -> None:
        for file_name in ("alpha_card.json", "validation_report.json", "backtest_report.json", "experiment_spec.json"):
            path = experiment_root / file_name
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["experiment_status"] = experiment_status
            payload["publication_status"] = "archived_only"
            payload["reason"] = reason
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_derivatives_sync_summary(
        self,
        *,
        as_of: str,
        warning: bool = False,
        write_last: bool = True,
        write_archive: bool = True,
        summary_overrides: dict[str, object] | None = None,
    ) -> None:
        self.derivatives_root.mkdir(parents=True, exist_ok=True)
        window_end_ms = int(datetime.fromisoformat(f"{as_of}T23:59:59+00:00").timestamp() * 1000)
        summary = {
            "status": "success",
            "generated_at_utc": f"{as_of}T03:05:00Z",
            "produced_at_utc": f"{as_of}T03:05:00Z",
            "external_root": str(self.derivatives_root),
            "mode": "refresh",
            "summary_scope": "by_as_of",
            "as_of": as_of,
            "window_end_ms": window_end_ms,
            "symbols": ["ETHUSDT", "JTOUSDT", "SUIUSDT"],
            "intervals": ["4h", "1d"],
            "required_symbols": ["ETHUSDT", "JTOUSDT", "SUIUSDT"],
            "required_intervals": ["4h", "1d"],
            "sync_results": (
                [
                    {
                        "status": "success",
                        "symbol": "ETHUSDT",
                        "interval": "4h",
                        "coverage_validation": {
                            "status": "warning",
                            "warning_codes": ["open_interest_provider_latest_window_cap"],
                        },
                        "requested_window": {
                            "start_time_ms": 0,
                            "end_time_ms": 1,
                            "lookback_days": 730.0,
                        },
                        "field_coverage": {
                            "funding_rate": {"coverage_days": 700.0},
                            "open_interest": {
                                "coverage_days": 29.0,
                                "provider_capped": True,
                            },
                        },
                    }
                ]
                if warning
                else []
            ),
            "coverage_validation": {
                "status": "warning" if warning else "ok",
                "warning_count": 1 if warning else 0,
                "warning_codes": ["open_interest_provider_latest_window_cap"] if warning else [],
            },
            "warning_count": 1 if warning else 0,
            "provider_cap_summary": {
                "4h": {
                    "requested_lookback_days": 730.0,
                    "funding_median_coverage_days": 700.0 if warning else 240.0,
                    "open_interest_median_coverage_days": 29.0 if warning else 29.0,
                    "open_interest_provider_capped_symbol_count": 1 if warning else 0,
                }
            },
        }
        if summary_overrides:
            summary.update(summary_overrides)
        if write_last:
            last_summary = dict(summary)
            if not write_archive:
                last_summary.pop("as_of", None)
                last_summary.pop("window_end_ms", None)
                last_summary.pop("summary_scope", None)
                last_summary.pop("required_symbols", None)
                last_summary.pop("required_intervals", None)
            (self.derivatives_root / "last_sync_summary.json").write_text(
                json.dumps(last_summary, indent=2),
                encoding="utf-8",
            )
        if write_archive:
            archive_path = as_of_sync_summary_path(external_root=self.derivatives_root, as_of=as_of)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _refresh_daily_manifest(self, *, as_of: str) -> None:
        entries: list[dict[str, object]] = []
        for alpha_card_path in sorted((self.artifacts_root / "experiments").glob("*/alpha_card.json")):
            alpha_card = json.loads(alpha_card_path.read_text(encoding="utf-8"))
            entry = build_daily_alpha_manifest_entry(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
            )
            if entry is not None and entry["as_of"] == as_of:
                entries.append(entry)
        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of=as_of,
            entries=entries,
        )

    def _copy_symbol_tree(self, *, source_root: Path, dest_root: Path, market_type: str, symbol: str) -> None:
        source = source_root / market_type / symbol
        destination = dest_root / market_type / symbol
        shutil.copytree(source, destination, dirs_exist_ok=True)


if __name__ == "__main__":
    unittest.main()
