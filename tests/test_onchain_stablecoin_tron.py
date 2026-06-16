from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enhengclaw.quant_research.onchain_stablecoin_tron import run_m3_2_tron_stablecoin_sync


def _identity_evidence(payload: dict, **kwargs) -> dict:  # noqa: ARG001
    return dict(payload)


def _build_day_strings(lookback_days: int) -> list[str]:
    end_date = datetime.now(UTC).date() - timedelta(days=1)
    start_date = end_date - timedelta(days=lookback_days - 1)
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(lookback_days)]


class TronStablecoinSyncTests(unittest.TestCase):
    def test_run_m3_2_tron_stablecoin_sync_writes_daily_aggregates(self) -> None:
        days = _build_day_strings(2)
        analysis_rows = [
            {
                "day": day,
                "from_count": 10 + index,
                "to_count": 12 + index,
                "amount": 1000.0 + index,
                "amount_usd": 1000.0 + index,
                "transfer_count": 50 + index,
                "transfer_address_count": 20 + index,
                "holders": 1000000 + index,
            }
            for index, day in enumerate(days)
        ]
        stats_rows = [
            {
                "dateDayStr": day,
                "active_account_number": 500 + index,
                "newTransactionSeen": 10000 + index,
                "usdt_transaction": 50 + index,
            }
            for index, day in enumerate(days)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with (
                patch(
                    "enhengclaw.quant_research.onchain_stablecoin_tron._fetch_token_analysis_range",
                    return_value=analysis_rows,
                ),
                patch(
                    "enhengclaw.quant_research.onchain_stablecoin_tron._fetch_tronscan_stats_overview",
                    return_value=stats_rows,
                ),
                patch(
                    "enhengclaw.quant_research.onchain_stablecoin_tron.with_evidence_metadata",
                    side_effect=_identity_evidence,
                ),
            ):
                summary = run_m3_2_tron_stablecoin_sync(
                    external_root=root,
                    lookback_days=2,
                    token_symbols=["USDT_TRX"],
                )

            self.assertTrue(summary["success"])
            output_path = root / "daily_aggregates.csv"
            self.assertTrue(output_path.exists())
            with output_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["token_symbol"] for row in rows}, {"USDT_TRX"})
        self.assertEqual(rows[0]["source"], "tronscan_public_api")
        self.assertEqual(rows[0]["transfer_count_vs_stats_delta"], "0.0")


if __name__ == "__main__":
    unittest.main()
