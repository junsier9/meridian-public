from __future__ import annotations

import csv
from datetime import UTC, datetime
import gzip
from pathlib import Path
import shutil
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

from enhengclaw.quant_research.binance_derivatives import CSV_HEADERS as DERIVATIVES_HEADERS
from enhengclaw.quant_research.coinglass_oi_provenance import (
    CSV_HEADERS as OI_PROVENANCE_HEADERS,
)
from enhengclaw.quant_research.coinglass_oi_provenance import load_oi_provenance_frame
from enhengclaw.quant_research.market_data import load_derivatives_frame


class CoinglassOiProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coinglass-oi-provenance-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.sidecar_root = self.temp_dir / "coinglass_oi_provenance"
        self.derivatives_root = self.temp_dir / "binance_derivatives"
        self.base_time_ms = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)

    def test_loader_uses_native_usd_value_not_derived_fallback(self) -> None:
        self._write_oi_rows(
            symbol="ETHUSDT",
            interval="1h",
            rows=[
                self._oi_row(
                    self.base_time_ms,
                    native_value=222.0,
                    coin_value=1.0,
                    price=999.0,
                    derived_value=999.0,
                    formula_status="fail",
                )
            ],
        )

        frame = load_oi_provenance_frame(
            symbol="ETHUSDT",
            interval="1h",
            external_root=self.sidecar_root,
            end_time_ms=self.base_time_ms,
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(float(frame.iloc[0]["open_interest_value"]), 222.0)
        self.assertEqual(frame.iloc[0]["open_interest_value_provider"], "coinglass_native_usd")
        self.assertEqual(frame.iloc[0]["open_interest_value_canonical_policy"], "native_usd_only")

    def test_loader_aggregates_1h_native_usd_to_4h_last_value(self) -> None:
        rows = [
            self._oi_row(self.base_time_ms + offset * 3_600_000, native_value=100.0 + offset)
            for offset in range(4)
        ]
        self._write_oi_rows(symbol="ETHUSDT", interval="1h", rows=rows)

        frame = load_oi_provenance_frame(
            symbol="ETHUSDT",
            interval="4h",
            external_root=self.sidecar_root,
            end_time_ms=self.base_time_ms + 3 * 3_600_000,
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(int(frame.iloc[0]["open_time_ms"]), self.base_time_ms)
        self.assertEqual(float(frame.iloc[0]["open_interest_value"]), 103.0)
        self.assertEqual(int(frame.iloc[0]["open_interest_value_sample_count"]), 4)
        self.assertEqual(frame.iloc[0]["open_interest_value_source_interval"], "1h")

    def test_market_data_overlay_extends_rows_and_preserves_coin_oi(self) -> None:
        second_time_ms = self.base_time_ms + 3_600_000
        self._write_derivatives_rows(
            symbol="ETHUSDT",
            interval="1h",
            rows=[
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": "ETHUSDT",
                    "interval": "1h",
                    "open_time_ms": str(self.base_time_ms),
                    "close_time_ms": str(self.base_time_ms + 3_600_000 - 1),
                    "funding_rate": "0.0001",
                    "funding_sample_count": "1",
                    "open_interest": "12.0",
                    "open_interest_value": "111.0",
                    "perp_close": "10.0",
                    "perp_quote_volume_usd": "1000.0",
                    "source": "binance_rest",
                }
            ],
        )
        self._write_oi_rows(
            symbol="ETHUSDT",
            interval="1h",
            rows=[
                self._oi_row(self.base_time_ms, native_value=222.0),
                self._oi_row(second_time_ms, native_value=333.0),
            ],
        )

        frame = load_derivatives_frame(
            symbol="ETHUSDT",
            interval="1h",
            external_root=self.derivatives_root,
            oi_provenance_external_root=self.sidecar_root,
            end_time_ms=second_time_ms,
        )

        self.assertEqual(len(frame), 2)
        first = frame.loc[frame["open_time_ms"].eq(self.base_time_ms)].iloc[0]
        second = frame.loc[frame["open_time_ms"].eq(second_time_ms)].iloc[0]
        self.assertEqual(float(first["open_interest_value"]), 222.0)
        self.assertEqual(float(first["open_interest"]), 12.0)
        self.assertEqual(first["open_interest_value_source"], "coinglass_oi_provenance_sidecar")
        self.assertEqual(float(second["open_interest_value"]), 333.0)
        self.assertTrue(pd.isna(second["open_interest"]))

    def _oi_row(
        self,
        open_time_ms: int,
        *,
        native_value: float,
        coin_value: float = 1.0,
        price: float = 100.0,
        derived_value: float | None = None,
        formula_status: str = "pass",
    ) -> dict[str, str]:
        resolved_derived = coin_value * price if derived_value is None else derived_value
        rel_diff = abs(resolved_derived - native_value) / max(abs(native_value), 1e-12)
        return {
            "exchange": "binance",
            "market_type": "usdm_perp",
            "symbol": "ETHUSDT",
            "interval": "1h",
            "open_time_ms": str(open_time_ms),
            "close_time_ms": str(open_time_ms + 3_600_000 - 1),
            "open_interest_value": f"{native_value:.10f}",
            "open_interest_value_native_usd": f"{native_value:.10f}",
            "open_interest_coin": f"{coin_value:.10f}",
            "binance_perp_close": f"{price:.10f}",
            "open_interest_value_derived_usd": f"{resolved_derived:.10f}",
            "derived_native_rel_diff": f"{rel_diff:.10f}",
            "derived_native_formula_status": formula_status,
            "oi_value_provenance": "native_usd",
            "price_source_for_derived_value": "binance_usdm_perp_ohlcv",
            "source": "coinglass_open_interest_history",
        }

    def _write_oi_rows(self, *, symbol: str, interval: str, rows: list[dict[str, str]]) -> None:
        path = self.sidecar_root / "usdm_perp" / symbol / interval / "2026-01.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OI_PROVENANCE_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_derivatives_rows(self, *, symbol: str, interval: str, rows: list[dict[str, str]]) -> None:
        path = self.derivatives_root / symbol / interval / "2026-01.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DERIVATIVES_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


if __name__ == "__main__":
    unittest.main()
