from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import csv
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase2_join import run_phase2_join  # noqa: E402


class HvBalancedDth60CoinglassPhase2JoinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase2-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.decision_time = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)

    def test_join_uses_latest_eligible_row_and_blocks_future_row(self) -> None:
        output_root = self.temp_dir / "future"
        now = self.decision_time - timedelta(minutes=5)
        summary, exit_code = run_phase2_join(
            self._args(output_root=output_root, decision_time=self.decision_time),
            http_get_json_fn=self._http_with_future_row,
            now_fn=lambda: now,
            base_env={"CoinglassAPI": "secret-test-key"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["joined_symbol_count"], 2)
        self.assertGreater(summary["future_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(output_root / "pit_joined_snapshot.csv")
        self.assertTrue(all(row["join_status"] == "joined" for row in joined))
        self.assertTrue(all(row["provider_timestamp_utc"] == "2026-06-06T00:00:00Z" for row in joined))
        self.assertTrue(all(row["future_fill_violation"] == "False" for row in joined))

    def test_stale_rows_are_not_joined_or_zero_filled(self) -> None:
        output_root = self.temp_dir / "stale"
        now = self.decision_time - timedelta(minutes=5)
        summary, exit_code = run_phase2_join(
            self._args(output_root=output_root, decision_time=self.decision_time, freshness_seconds=60),
            http_get_json_fn=self._http_without_future_row,
            now_fn=lambda: now,
            base_env={"CoinglassAPI": "secret-test-key"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase2_join_missing_symbol", summary["blockers"])
        self.assertEqual(summary["joined_symbol_count"], 0)
        self.assertGreater(summary["stale_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(output_root / "pit_joined_snapshot.csv")
        self.assertTrue(all(row["join_status"] == "blocked_no_eligible_sidecar_row" for row in joined))
        self.assertTrue(all(row["coinglass_top_trader_long_pct_smooth_5"] == "" for row in joined))

    def test_insufficient_window_does_not_join_or_zero_fill(self) -> None:
        output_root = self.temp_dir / "short-window"
        now = self.decision_time - timedelta(minutes=5)
        summary, exit_code = run_phase2_join(
            self._args(output_root=output_root, decision_time=self.decision_time),
            http_get_json_fn=self._http_short_window,
            now_fn=lambda: now,
            base_env={"CoinglassAPI": "secret-test-key"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["joined_symbol_count"], 0)
        self.assertGreater(summary["insufficient_window_count"], 0)
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(output_root / "pit_joined_snapshot.csv")
        self.assertTrue(all(row["coinglass_top_trader_long_pct_smooth_5"] == "" for row in joined))

    def test_missing_key_blocks_without_provider_call(self) -> None:
        output_root = self.temp_dir / "missing-key"
        call_count = 0

        def fake_http(url: str, api_key: str, timeout: float):
            nonlocal call_count
            call_count += 1
            return self._http_without_future_row(url, api_key, timeout)

        summary, exit_code = run_phase2_join(
            self._args(output_root=output_root, decision_time=self.decision_time),
            http_get_json_fn=fake_http,
            now_fn=lambda: self.decision_time - timedelta(minutes=5),
            base_env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("coinglass_api_key_missing", summary["blockers"])
        self.assertEqual(call_count, 0)

    def _args(
        self,
        *,
        output_root: Path,
        decision_time: datetime,
        freshness_seconds: int = 36 * 3600,
    ) -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            symbols="",
            output_root=str(output_root),
            decision_time=decision_time.isoformat().replace("+00:00", "Z"),
            interval="1d",
            limit=10,
            freshness_seconds=freshness_seconds,
            min_window=5,
            request_sleep_seconds=0.0,
            request_timeout_seconds=20.0,
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_live_timer.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "market_data:",
                    "  symbols: BTCUSDT,ETHUSDT",
                    "state:",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _http_with_future_row(self, url: str, api_key: str, timeout: float):
        self.assertEqual(api_key, "secret-test-key")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertIn(query.get("symbol", [""])[0], {"BTCUSDT", "ETHUSDT"})
        return {"code": "0", "msg": "success", "data": self._rows(include_future=True, count=7)}

    def _http_without_future_row(self, url: str, api_key: str, timeout: float):
        self.assertEqual(api_key, "secret-test-key")
        return {"code": "0", "msg": "success", "data": self._rows(include_future=False, count=6)}

    def _http_short_window(self, url: str, api_key: str, timeout: float):
        self.assertEqual(api_key, "secret-test-key")
        return {"code": "0", "msg": "success", "data": self._rows(include_future=False, count=4)}

    def _rows(self, *, include_future: bool, count: int) -> list[dict[str, str]]:
        latest = datetime(2026, 6, 6, 0, 0, tzinfo=UTC)
        start = latest - timedelta(days=count - 1)
        rows = []
        for index in range(count):
            ts = start + timedelta(days=index)
            rows.append(
                {
                    "time": str(int(ts.timestamp() * 1000)),
                    "top_position_long_percent": str(50.0 + index),
                }
            )
        if include_future:
            future = self.decision_time + timedelta(days=1)
            rows.append(
                {
                    "time": str(int(future.timestamp() * 1000)),
                    "top_position_long_percent": "99.0",
                }
            )
        return rows

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
