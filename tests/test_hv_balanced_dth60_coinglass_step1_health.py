from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import run_step1_health  # noqa: E402


class HvBalancedDth60CoinglassStep1HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-step1-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.now = datetime(2026, 6, 6, 4, 0, tzinfo=UTC)

    def test_ready_health_check_writes_no_secret_evidence(self) -> None:
        output_root = self.temp_dir / "ready"
        summary, exit_code = run_step1_health(
            self._args(output_root=output_root),
            http_get_json_fn=self._fake_http,
            now_fn=lambda: self.now,
            base_env={"CoinglassAPI": "secret-test-key"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertTrue(summary["api_key_present"])
        self.assertEqual(summary["ready_symbol_count"], 2)
        self.assertEqual(summary["blockers"], [])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "coinglass_requests.csv").exists())
        self.assertTrue((output_root / "top_trader_observations.csv").exists())

        combined = (
            (output_root / "summary.json").read_text(encoding="utf-8")
            + (output_root / "coinglass_requests.csv").read_text(encoding="utf-8")
            + (output_root / "top_trader_observations.csv").read_text(encoding="utf-8")
        )
        self.assertNotIn("secret-test-key", combined)
        self.assertNotIn("CG-API-KEY", combined)

    def test_missing_key_blocks_before_provider_calls(self) -> None:
        output_root = self.temp_dir / "missing"
        call_count = 0

        def fake_http(url: str, api_key: str, timeout: float):
            nonlocal call_count
            call_count += 1
            return self._fake_http(url, api_key, timeout)

        summary, exit_code = run_step1_health(
            self._args(output_root=output_root),
            http_get_json_fn=fake_http,
            now_fn=lambda: self.now,
            base_env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("coinglass_api_key_missing", summary["blockers"])
        self.assertEqual(call_count, 0)
        self.assertTrue((output_root / "summary.json").exists())

    def test_stale_top_trader_blocks_symbol(self) -> None:
        output_root = self.temp_dir / "stale"

        def stale_http(url: str, api_key: str, timeout: float):
            parsed = urlparse(url)
            if "top-long-short-position-ratio" in parsed.path:
                return {"code": "0", "msg": "success", "data": self._rows(days_ago=3)}
            return self._fake_http(url, api_key, timeout)

        summary, exit_code = run_step1_health(
            self._args(output_root=output_root, freshness_seconds=36 * 3600),
            http_get_json_fn=stale_http,
            now_fn=lambda: self.now,
            base_env={"CoinglassAPI": "secret-test-key"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("BTCUSDT:top_trader_stale", summary["blockers"])
        self.assertIn("ETHUSDT:top_trader_stale", summary["blockers"])

    def _args(self, *, output_root: Path, freshness_seconds: int = 36 * 3600) -> Namespace:
        return Namespace(
            config=str(self._config_path()),
            symbols="",
            output_root=str(output_root),
            interval="1d",
            limit=10,
            freshness_seconds=freshness_seconds,
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

    def _fake_http(self, url: str, api_key: str, timeout: float):
        self.assertEqual(api_key, "secret-test-key")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "user/account/subscription" in parsed.path:
            return {"code": "0", "msg": "success", "data": {"plan": "test"}}
        if "supported-exchange-pairs" in parsed.path:
            return {
                "code": "0",
                "msg": "success",
                "data": [{"Binance": [{"instrument_id": "BTCUSDT"}, {"instrument_id": "ETHUSDT"}]}],
            }
        if "top-long-short-position-ratio" in parsed.path:
            self.assertIn(query.get("symbol", [""])[0], {"BTCUSDT", "ETHUSDT"})
            return {"code": "0", "msg": "success", "data": self._rows(days_ago=1)}
        raise AssertionError(url)

    def _rows(self, *, days_ago: int) -> list[dict[str, str]]:
        latest = self.now - timedelta(days=days_ago)
        rows = []
        for index in range(5):
            ts = int((latest - timedelta(days=4 - index)).timestamp() * 1000)
            rows.append({"time": str(ts), "top_position_long_percent": json.dumps(55.0 + index)})
        return rows


if __name__ == "__main__":
    unittest.main()
