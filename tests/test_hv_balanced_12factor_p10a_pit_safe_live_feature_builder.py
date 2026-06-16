from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import csv
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_12factor_p10a_pit_safe_live_feature_builder import (  # noqa: E402
    BINANCE_PUBLIC_FACTOR_IDS,
    _build_settlement_sidecar,
    _perp_spot_basis_proxy,
    build_deterministic_fixture_panel,
    run_p10a_live_feature_builder,
)


REQUIRED_FACTORS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
]


class HvBalanced12FactorP10aPitSafeLiveFeatureBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10a-live-features-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.decision_time = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        self.symbols = ["BTCUSDT", "ETHUSDT"]

    def test_deterministic_fixture_all_12_factors_ready(self) -> None:
        summary, exit_code = run_p10a_live_feature_builder(
            self._args(output_root=self.temp_dir / "ready", mode="deterministic-fixture"),
            now_fn=lambda: self.decision_time,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["required_feature_count"], 12)
        self.assertEqual(summary["required_feature_columns"], REQUIRED_FACTORS)
        self.assertEqual(summary["required_feature_cell_count"], 24)
        self.assertEqual(summary["joined_feature_cell_count"], 24)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        readiness = self._read_csv(self.temp_dir / "ready" / "pit_live_feature_factor_readiness.csv")
        self.assertEqual({row["status"] for row in readiness}, {"ready"})

    def test_future_rows_are_blocked_and_latest_eligible_rows_are_used(self) -> None:
        panel = self._fresh_fixture()
        future = panel.copy()
        future_provider_ms = int((self.decision_time + timedelta(hours=1)).timestamp() * 1000)
        future_available_ms = future_provider_ms + 60_000
        for factor in REQUIRED_FACTORS:
            future[factor] = 99.0
            future[f"{factor}_provider_timestamp_ms"] = future_provider_ms
            future[f"{factor}_available_at_ms"] = future_available_ms
        panel = pd.concat([panel, future], ignore_index=True, sort=False)

        summary, exit_code = run_p10a_live_feature_builder(
            self._args(output_root=self.temp_dir / "future", mode="input-panel"),
            now_fn=lambda: self.decision_time,
            input_panel=panel,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertGreater(summary["future_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        joined = self._read_csv(self.temp_dir / "future" / "pit_live_feature_joined_snapshot.csv")
        self.assertTrue(all(row["join_status"] == "joined" for row in joined))
        self.assertTrue(all(float(row["value"]) < 99.0 for row in joined))

    def test_stale_rows_are_not_joined_or_zero_filled(self) -> None:
        panel = self._fresh_fixture()
        stale_provider_ms = int((self.decision_time - timedelta(days=5)).timestamp() * 1000)
        stale_available_ms = stale_provider_ms + 60_000
        for factor in REQUIRED_FACTORS:
            panel[f"{factor}_provider_timestamp_ms"] = stale_provider_ms
            panel[f"{factor}_available_at_ms"] = stale_available_ms

        summary, exit_code = run_p10a_live_feature_builder(
            self._args(output_root=self.temp_dir / "stale", mode="input-panel", freshness_seconds=3600),
            now_fn=lambda: self.decision_time,
            input_panel=panel,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["joined_feature_cell_count"], 0)
        self.assertGreater(summary["stale_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(self.temp_dir / "stale" / "pit_live_feature_joined_snapshot.csv")
        self.assertTrue(all(row["join_status"] == "blocked_no_eligible_live_feature_row" for row in joined))
        self.assertTrue(all(row["value"] == "" for row in joined))

    def test_missing_values_are_not_zero_filled(self) -> None:
        panel = self._fresh_fixture()
        panel["quality_funding_oi"] = float("nan")

        summary, exit_code = run_p10a_live_feature_builder(
            self._args(output_root=self.temp_dir / "missing-value", mode="input-panel"),
            now_fn=lambda: self.decision_time,
            input_panel=panel,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertGreater(summary["missing_value_blocked_count"], 0)
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(self.temp_dir / "missing-value" / "pit_live_feature_joined_snapshot.csv")
        missing_rows = [row for row in joined if row["factor_id"] == "quality_funding_oi"]
        self.assertEqual({row["join_status"] for row in missing_rows}, {"blocked_no_eligible_live_feature_row"})
        self.assertTrue(all(row["value"] == "" for row in missing_rows))

    def test_live_binance_public_panel_blocks_missing_12_factor_sidecars(self) -> None:
        def fake_fetcher(**_: object):
            provider_ms = int((self.decision_time - timedelta(hours=2)).timestamp() * 1000)
            rows = []
            for symbol in self.symbols:
                subject = symbol[:-4]
                row = {
                    "timestamp_ms": provider_ms - 86_400_000,
                    "close_time_ms": provider_ms,
                    "symbol": symbol,
                    "usdm_symbol": symbol,
                    "subject": subject,
                }
                for factor in sorted(BINANCE_PUBLIC_FACTOR_IDS):
                    row[factor] = 0.1
                rows.append(row)
            return pd.DataFrame(rows), {"source": "fake_binance_public_rest", "blockers": []}, {}

        summary, exit_code = run_p10a_live_feature_builder(
            self._args(
                output_root=self.temp_dir / "live-public-subset",
                mode="live-binance-public",
                disable_sidecar_builders=True,
            ),
            now_fn=lambda: self.decision_time,
            live_panel_fetcher=fake_fetcher,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        self.assertIn("factor:coinglass_top_trader_long_pct_smooth_5:missing_column", summary["blockers"])
        self.assertIn("factor:settlement_cycle_premium_60d:missing_column", summary["blockers"])

    def test_live_sidecar_builder_can_complete_missing_5_factors(self) -> None:
        def fake_fetcher(**_: object):
            provider_ms = int((self.decision_time - timedelta(hours=2)).timestamp() * 1000)
            rows = []
            for symbol in self.symbols:
                subject = symbol[:-4]
                row = {
                    "timestamp_ms": provider_ms - 86_400_000,
                    "close_time_ms": provider_ms,
                    "date_utc": (self.decision_time - timedelta(days=1)).date().isoformat(),
                    "symbol": symbol,
                    "usdm_symbol": symbol,
                    "subject": subject,
                }
                for factor in sorted(BINANCE_PUBLIC_FACTOR_IDS):
                    row[factor] = 0.1
                rows.append(row)
            return pd.DataFrame(rows), {"source": "fake_binance_public_rest", "blockers": []}, {}

        def fake_sidecar_builder(**kwargs: object):
            panel = kwargs["panel"].copy()
            provider_ms = int((self.decision_time - timedelta(hours=2)).timestamp() * 1000)
            available_ms = provider_ms + 60_000
            for index, factor in enumerate(
                [
                    "coinglass_top_trader_long_pct_smooth_5",
                    "coinglass_taker_imb_intraday_dispersion_24h",
                    "quality_funding_oi",
                    "funding_basis_residual_implied_repo_30",
                    "settlement_cycle_premium_60d",
                ]
            ):
                panel[factor] = 0.2 + index * 0.01
                panel[f"{factor}_provider_timestamp_ms"] = provider_ms
                panel[f"{factor}_available_at_ms"] = available_ms
                panel[f"{factor}_source"] = "fake_sidecar_builder"
            return panel, {"enabled": True, "status": "ready", "blockers": [], "request_count": 0}

        summary, exit_code = run_p10a_live_feature_builder(
            self._args(
                output_root=self.temp_dir / "live-sidecar-complete",
                mode="live-binance-public",
                disable_sidecar_builders=False,
            ),
            now_fn=lambda: self.decision_time,
            live_panel_fetcher=fake_fetcher,
            live_sidecar_builder=fake_sidecar_builder,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["joined_feature_cell_count"], 24)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])

    def test_paginated_settlement_builder_produces_60d_history_after_warmup(self) -> None:
        decision_time = datetime(2026, 6, 8, 0, 1, tzinfo=UTC)
        rows = _hourly_kline_rows(
            start=decision_time - timedelta(days=80, minutes=1),
            hours=80 * 24,
        )
        client = _FakeKlineClient(rows)

        frame, audit = _build_settlement_sidecar(
            symbol="BTCUSDT",
            decision_time=decision_time,
            args=Namespace(
                settlement_lookback_days=80,
                settlement_page_limit=500,
                settlement_request_sleep_seconds=0.0,
                settlement_request_max_attempts=3,
                settlement_request_retry_sleep_seconds=0.0,
                availability_lag_seconds=60,
            ),
            binance_client=client,
        )

        self.assertFalse(frame.empty)
        self.assertTrue(audit["pagination_enabled"])
        self.assertGreater(audit["page_count"], 1)
        self.assertGreater(len(client.requests), 1)
        self.assertGreaterEqual(int(frame["settlement_cycle_premium_60d"].notna().sum()), 15)
        ready = frame.loc[frame["settlement_cycle_premium_60d"].notna()].copy()
        self.assertLessEqual(ready["date_utc"].min(), "2026-05-23")
        self.assertTrue(
            (
                pd.to_numeric(ready["settlement_cycle_premium_60d_available_at_ms"], errors="coerce")
                - pd.to_numeric(ready["settlement_cycle_premium_60d_provider_timestamp_ms"], errors="coerce")
            )
            .eq(60_000)
            .all()
        )
        self.assertEqual(set(ready["settlement_cycle_premium_60d_source"]), {"binance_1h_settlement_sidecar_p10b"})

    def test_paginated_settlement_builder_retries_single_page_timeout_and_succeeds(self) -> None:
        decision_time = datetime(2026, 6, 8, 0, 1, tzinfo=UTC)
        rows = _hourly_kline_rows(
            start=decision_time - timedelta(days=80, minutes=1),
            hours=80 * 24,
        )
        client = _FlakyKlineClient(rows, fail_call_numbers={11})

        frame, audit = _build_settlement_sidecar(
            symbol="FILUSDT",
            decision_time=decision_time,
            args=Namespace(
                settlement_lookback_days=80,
                settlement_page_limit=100,
                settlement_request_sleep_seconds=0.0,
                settlement_request_max_attempts=3,
                settlement_request_retry_sleep_seconds=0.0,
                availability_lag_seconds=60,
            ),
            binance_client=client,
        )

        self.assertFalse(frame.empty)
        self.assertEqual(audit["blockers"], [])
        self.assertEqual(audit["retry_count"], 1)
        failed_page_11 = [
            row
            for row in audit["requests"]
            if row.get("pagination_page") == 11 and row.get("retry_attempt") == 1 and row.get("status") == "error"
        ]
        recovered_page_11 = [
            row
            for row in audit["requests"]
            if row.get("pagination_page") == 11 and row.get("retry_attempt") == 2 and row.get("status") == "success"
        ]
        self.assertEqual(len(failed_page_11), 1)
        self.assertEqual(len(recovered_page_11), 1)

    def test_paginated_settlement_builder_exhausted_retry_still_fails_closed(self) -> None:
        decision_time = datetime(2026, 6, 8, 0, 1, tzinfo=UTC)
        rows = _hourly_kline_rows(
            start=decision_time - timedelta(days=80, minutes=1),
            hours=80 * 24,
        )
        client = _FlakyKlineClient(rows, fail_call_numbers={1, 2})

        frame, audit = _build_settlement_sidecar(
            symbol="FILUSDT",
            decision_time=decision_time,
            args=Namespace(
                settlement_lookback_days=80,
                settlement_page_limit=100,
                settlement_request_sleep_seconds=0.0,
                settlement_request_max_attempts=2,
                settlement_request_retry_sleep_seconds=0.0,
                availability_lag_seconds=60,
            ),
            binance_client=client,
        )

        self.assertTrue(frame.empty)
        self.assertIn("FILUSDT:binance_1h_settlement_request_failed", audit["blockers"])
        self.assertEqual(audit["retry_count"], 1)
        self.assertEqual([row.get("status") for row in audit["requests"]], ["error", "error"])
        self.assertEqual(audit["requests"][-1].get("retryable"), False)

    def _args(
        self,
        *,
        output_root: Path,
        mode: str,
        freshness_seconds: int = 36 * 3600,
        disable_sidecar_builders: bool = True,
    ) -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            symbols=",".join(self.symbols),
            mode=mode,
            input_panel=None,
            output_root=str(output_root),
            decision_time=self.decision_time.isoformat().replace("+00:00", "Z"),
            freshness_seconds=freshness_seconds,
            availability_lag_seconds=60,
            min_symbol_coverage=1.0,
            daily_limit=140,
            four_hour_limit=840,
            base_url="https://fapi.binance.com",
            request_timeout_seconds=20.0,
            disable_sidecar_builders=disable_sidecar_builders,
            sidecar_lookback_days=90,
            sidecar_hour_lookback_days=4,
            settlement_hour_limit=1500,
            settlement_lookback_days=0,
            settlement_page_limit=1500,
            settlement_request_sleep_seconds=0.0,
            settlement_request_max_attempts=3,
            settlement_request_retry_sleep_seconds=0.0,
            coinglass_request_sleep_seconds=0.0,
            active_h10d_registry=ROOT / "config" / "quant_research" / "active_h10d_registry.json",
            research_parent_manifest=None,
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_live_timer.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "market_data:",
                    f"  symbols: {','.join(self.symbols)}",
                    "state:",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _fresh_fixture(self) -> pd.DataFrame:
        return build_deterministic_fixture_panel(
            required_factors=REQUIRED_FACTORS,
            symbols=self.symbols,
            decision_time=self.decision_time,
            availability_lag_seconds=60,
        )

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


class _FakeKlineClient:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.requests: list[dict[str, object]] = []

    def klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> SimpleNamespace:
        self.requests.append(
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        selected = [
            row
            for row in self.rows
            if (start_time is None or int(row[0]) >= int(start_time))
            and (end_time is None or int(row[0]) <= int(end_time))
        ]
        return SimpleNamespace(payload=selected[: int(limit)])


class _FlakyKlineClient(_FakeKlineClient):
    def __init__(self, rows: list[list[object]], *, fail_call_numbers: set[int]) -> None:
        super().__init__(rows)
        self.fail_call_numbers = set(fail_call_numbers)
        self.call_count = 0

    def klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> SimpleNamespace:
        self.call_count += 1
        if self.call_count in self.fail_call_numbers:
            self.requests.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit,
                    "start_time": start_time,
                    "end_time": end_time,
                    "failed": True,
                }
            )
            raise TimeoutError("synthetic ssl handshake timeout")
        return super().klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )


def _hourly_kline_rows(*, start: datetime, hours: int) -> list[list[object]]:
    aligned = start.replace(minute=0, second=0, microsecond=0)
    rows: list[list[object]] = []
    for index in range(int(hours)):
        open_time = aligned + timedelta(hours=index)
        open_ms = int(open_time.timestamp() * 1000)
        close_time_ms = open_ms + 3_600_000 - 1
        price = 100.0 + index * 0.01 + (index % 24) * 0.001
        rows.append(
            [
                open_ms,
                f"{price:.8f}",
                f"{price + 0.05:.8f}",
                f"{price - 0.05:.8f}",
                f"{price + 0.01:.8f}",
                "10.0",
                close_time_ms,
                "1000.0",
                10,
                "5.0",
                "500.0",
                "0",
            ]
        )
    return rows


class PerpSpotBasisProxyTests(unittest.TestCase):
    """funding_basis source-change: research-parity basis = (perp_close - spot_close)/spot_close,
    fail-closed when spot is unavailable (so the snapshot blocks rather than silently mis-sourcing)."""

    def _panel(self) -> pd.DataFrame:
        ts = [int(datetime(2026, 6, day, tzinfo=UTC).timestamp() * 1000) for day in (1, 2, 3)]
        return pd.DataFrame(
            {
                "timestamp_ms": ts,
                "subject": ["BTC"] * 3,
                "usdm_symbol": ["BTCUSDT"] * 3,
                "perp_close": [101.0, 102.0, 103.0],
                "date_utc": ["2026-06-01", "2026-06-02", "2026-06-03"],
            }
        )

    def test_matches_research_perp_spot_formula(self) -> None:
        spot = pd.DataFrame(
            {"subject": ["BTC"] * 3, "date_utc": ["2026-06-01", "2026-06-02", "2026-06-03"], "spot_close": [100.0, 100.0, 100.0]}
        )
        basis, blockers = _perp_spot_basis_proxy(panel=self._panel(), symbol="BTCUSDT", subject="BTC", spot_close_frame=spot)
        self.assertEqual(blockers, [])
        self.assertEqual([round(v, 4) for v in basis["basis_proxy"].tolist()], [0.01, 0.02, 0.03])

    def test_missing_spot_fails_closed(self) -> None:
        basis, blockers = _perp_spot_basis_proxy(panel=self._panel(), symbol="BTCUSDT", subject="BTC", spot_close_frame=None)
        self.assertTrue(basis.empty)
        self.assertTrue(any("perp_spot_basis_spot_unavailable" in b for b in blockers))

    def test_spot_subject_missing_fails_closed(self) -> None:
        spot = pd.DataFrame({"subject": ["ETH"], "date_utc": ["2026-06-01"], "spot_close": [100.0]})
        basis, blockers = _perp_spot_basis_proxy(panel=self._panel(), symbol="BTCUSDT", subject="BTC", spot_close_frame=spot)
        self.assertTrue(basis.empty)
        self.assertTrue(any("perp_spot_basis_spot_subject_missing" in b for b in blockers))


if __name__ == "__main__":
    unittest.main()
