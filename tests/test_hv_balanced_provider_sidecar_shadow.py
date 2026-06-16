from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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

from enhengclaw.live_trading.provider_sidecar_shadow import run_provider_sidecar_shadow  # noqa: E402


class HvBalancedProviderSidecarShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-provider-sidecar-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)

    def test_sidecar_shadow_records_required_fields_and_passes_gates(self) -> None:
        output_root = self.temp_dir / "sidecar"
        summary, exit_code = run_provider_sidecar_shadow(
            Namespace(
                config=str(self._config_path(symbols="BTCUSDT,ETHUSDT")),
                decision_artifact_root="",
                symbols="",
                as_of="now",
                output_root=str(output_root),
            ),
            http_get_json_fn=self._fake_coinglass_http,
            now_fn=lambda: self.now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "provider_sidecar_shadow_ready")
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["alpha_score_changed"])
        self.assertFalse(summary["live_config_changed"])
        self.assertEqual(summary["exchange_order_submission"], "disabled")
        self.assertGreaterEqual(summary["core_ready_fraction"], 0.95)
        self.assertTrue(summary["latency_gate_passed"])
        self.assertTrue(summary["pit_gate_passed"])
        self.assertTrue(summary["fallback_gate_passed"])
        self.assertTrue(summary["determinism_gate_passed"])

        observations_path = output_root / "provider_sidecar_observations.jsonl"
        endpoint_path = output_root / "provider_sidecar_endpoint_manifest.jsonl"
        self.assertTrue(observations_path.exists())
        self.assertTrue(endpoint_path.exists())
        observations = [json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(observations), 12)
        required = {
            "decision_time",
            "symbol",
            "provider",
            "endpoint",
            "provider_timestamp",
            "available_at",
            "request_latency_ms",
            "raw_status",
            "normalized_value",
            "factor_value",
            "readiness",
        }
        self.assertTrue(required.issubset(observations[0].keys()))
        self.assertTrue(all(row["pit_ok"] for row in observations if row["readiness"] == "ready"))
        self.assertTrue(all(row["applied_to_live"] is False for row in observations))
        self.assertIn("funding_basis_residual_implied_repo_30", {row["factor_id"] for row in observations})

        combined = (
            (output_root / "provider_sidecar_shadow_summary.json").read_text(encoding="utf-8")
            + observations_path.read_text(encoding="utf-8")
            + endpoint_path.read_text(encoding="utf-8")
        )
        self.assertNotIn("CG-API-KEY", combined)
        self.assertNotIn("CoinglassAPI", combined)

    def test_not_ready_fallback_blocks_without_zero_filling(self) -> None:
        output_root = self.temp_dir / "missing"

        def sparse_http(url: str):
            parsed = urlparse(url)
            if "top-long-short-position-ratio" in parsed.path:
                return {"code": "0", "data": self._daily_rows(limit=2, field="top_position_long_percent", start=52.0)}
            return self._fake_coinglass_http(url)

        summary, exit_code = run_provider_sidecar_shadow(
            Namespace(
                config=str(self._config_path(symbols="BTCUSDT")),
                decision_artifact_root="",
                symbols="",
                as_of="now",
                output_root=str(output_root),
            ),
            http_get_json_fn=sparse_http,
            now_fn=lambda: self.now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "provider_sidecar_shadow_blocked")
        self.assertTrue(summary["fallback_gate_passed"])
        observations = [
            json.loads(line)
            for line in (output_root / "provider_sidecar_observations.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        top = [row for row in observations if row["factor_id"] == "top_trader_long_pct_smooth_5"][0]
        self.assertEqual(top["readiness"], "not_ready")
        self.assertIsNone(top["factor_value"])
        self.assertEqual(top["overlay_action"], "not_ready_no_overlay")

    def _config_path(self, *, symbols: str) -> Path:
        config_path = self.temp_dir / "hv_balanced_shadow_loop.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    "  frozen_config_path: config/quant_research/binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json",
                    "  rebalance_interval_days: 10",
                    "market_data:",
                    "  public_data_enabled: false",
                    f"  symbols: {symbols}",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _fake_coinglass_http(self, url: str):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        interval = query.get("interval", ["1d"])[0]
        limit = int(query.get("limit", ["10"])[0])
        path = parsed.path
        if "top-long-short-position-ratio" in path:
            return {"code": "0", "msg": "success", "data": self._daily_rows(limit=limit, field="top_position_long_percent", start=55.0)}
        if "taker-buy-sell-volume" in path:
            return {"code": "0", "msg": "success", "data": self._hourly_rows(limit=max(limit, 30), kind="taker")}
        if "funding-rate" in path:
            return {"code": "0", "msg": "success", "data": self._rows_for_interval(interval, limit, field="close", start=0.0001, step=0.00001)}
        if "open-interest" in path:
            return {"code": "0", "msg": "success", "data": self._rows_for_interval(interval, limit, field="close", start=1_000_000.0, step=1_000.0)}
        if "futures/price" in path:
            return {"code": "0", "msg": "success", "data": self._rows_for_interval(interval, limit, field="close", start=101.0, step=0.2)}
        if "spot/price" in path:
            return {"code": "0", "msg": "success", "data": self._rows_for_interval(interval, limit, field="close", start=100.0, step=0.15)}
        if "liquidation" in path:
            return {"code": "0", "msg": "success", "data": self._hourly_rows(limit=max(limit, 840), kind="liquidation")}
        if "orderbook" in path:
            return {"code": "0", "msg": "success", "data": self._hourly_rows(limit=max(limit, 30), kind="orderbook")}
        return {"code": "0", "msg": "success", "data": []}

    def _rows_for_interval(self, interval: str, limit: int, *, field: str, start: float, step: float) -> list[dict[str, float]]:
        if interval == "1h":
            return self._hourly_value_rows(limit=limit, field=field, start=start, step=step)
        return self._daily_rows(limit=limit, field=field, start=start, step=step)

    def _daily_rows(self, *, limit: int, field: str, start: float, step: float = 1.0) -> list[dict[str, float]]:
        base = self.now - timedelta(days=limit - 1)
        return [
            {"time": int((base + timedelta(days=index)).timestamp() * 1000), field: start + index * step}
            for index in range(limit)
        ]

    def _hourly_value_rows(self, *, limit: int, field: str, start: float, step: float) -> list[dict[str, float]]:
        base = self.now - timedelta(hours=limit - 1)
        return [
            {"time": int((base + timedelta(hours=index)).timestamp() * 1000), field: start + index * step}
            for index in range(limit)
        ]

    def _hourly_rows(self, *, limit: int, kind: str) -> list[dict[str, float]]:
        base = self.now - timedelta(hours=limit - 1)
        rows = []
        for index in range(limit):
            ts = int((base + timedelta(hours=index)).timestamp() * 1000)
            if kind == "taker":
                rows.append(
                    {
                        "time": ts,
                        "taker_buy_volume_usd": 1000.0 + index * 10.0,
                        "taker_sell_volume_usd": 900.0 + (index % 5) * 20.0,
                    }
                )
            elif kind == "liquidation":
                rows.append(
                    {
                        "time": ts,
                        "long_liquidation_usd": 100.0 + (index % 17) * 10.0,
                        "short_liquidation_usd": 50.0 + (index % 11) * 8.0,
                    }
                )
            elif kind == "orderbook":
                rows.append(
                    {
                        "time": ts,
                        "bids_usd": 10_000.0 + index * 30.0,
                        "asks_usd": 9_000.0 + (index % 3) * 20.0,
                    }
                )
        return rows


if __name__ == "__main__":
    unittest.main()
