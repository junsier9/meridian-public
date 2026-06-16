from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

import pandas as pd

from enhengclaw.quant_research.research_dataset_builder import (
    build_research_dataset_manifest_fields,
    scope_research_dataset_to_frame,
    validate_research_dataset_requirements,
)


class ResearchDatasetBuilderTests(unittest.TestCase):
    def _frame(self, *, include_sidecar: bool) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        start = datetime(2025, 1, 1, tzinfo=UTC)
        for offset in range(190):
            timestamp = start + timedelta(days=offset)
            timestamp_ms = int(timestamp.timestamp() * 1000)
            for subject in ("AAA", "BBB"):
                row: dict[str, object] = {
                    "timestamp_ms": timestamp_ms,
                    "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                    "subject": subject,
                    "usdm_symbol": f"{subject}USDT",
                    "perp_close": 100.0 + offset,
                    "open_interest_value": 1_000_000.0 + offset,
                    "perp_quote_volume_usd": 2_000_000.0 + offset,
                }
                if include_sidecar:
                    row["funding_rate"] = 0.0001
                    row["open_interest"] = 100_000.0 + offset
                    row["basis_proxy"] = 0.0003
                rows.append(row)
        return pd.DataFrame.from_records(rows)

    def test_build_research_dataset_manifest_fields_tracks_sidecars_and_history(self) -> None:
        fields = build_research_dataset_manifest_fields(
            as_of="2026-05-01",
            dataset_id="2026-05-01-cross-sectional-daily-1d",
            dataset_profile="cross_sectional_daily_4h",
            primary_interval="1d",
            raw_panel=self._frame(include_sidecar=True),
        )

        self.assertEqual(fields["subject_count"], 2)
        research_dataset = dict(fields["research_dataset"])
        self.assertTrue(research_dataset["required_sidecar_families_present"])
        self.assertTrue(research_dataset["minimum_executable_history_passed"])
        self.assertIn("derivatives_core", research_dataset["sidecar_fingerprints"])
        self.assertEqual(validate_research_dataset_requirements(research_dataset=research_dataset), [])

    def test_validate_research_dataset_requirements_fails_closed_when_core_sidecar_missing(self) -> None:
        fields = build_research_dataset_manifest_fields(
            as_of="2026-05-01",
            dataset_id="2026-05-01-cross-sectional-daily-1d",
            dataset_profile="cross_sectional_daily_4h",
            primary_interval="1d",
            raw_panel=self._frame(include_sidecar=False),
        )

        blockers = validate_research_dataset_requirements(
            research_dataset=fields["research_dataset"],
        )
        self.assertIn("research_dataset_missing_required_sidecar", blockers)

    def test_scope_research_dataset_to_frame_uses_strategy_universe_not_raw_panel(self) -> None:
        raw_panel = self._frame(include_sidecar=True)
        late_subject_rows = []
        late_start = datetime(2025, 6, 1, tzinfo=UTC)
        for offset in range(30):
            timestamp = late_start + timedelta(days=offset)
            timestamp_ms = int(timestamp.timestamp() * 1000)
            late_subject_rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                    "subject": "LATE",
                    "usdm_symbol": "LATEUSDT",
                    "perp_close": 200.0 + offset,
                    "open_interest_value": 1_500_000.0 + offset,
                    "perp_quote_volume_usd": 2_500_000.0 + offset,
                    "funding_rate": 0.0002,
                    "open_interest": 120_000.0 + offset,
                    "basis_proxy": 0.0004,
                }
            )
        raw_panel = pd.concat([raw_panel, pd.DataFrame.from_records(late_subject_rows)], ignore_index=True)

        fields = build_research_dataset_manifest_fields(
            as_of="2026-05-01",
            dataset_id="2026-05-01-cross-sectional-daily-1d",
            dataset_profile="cross_sectional_daily_4h",
            primary_interval="1d",
            raw_panel=raw_panel,
        )
        global_research_dataset = dict(fields["research_dataset"])
        self.assertFalse(global_research_dataset["minimum_executable_history_passed"])
        self.assertIn(
            "research_dataset_minimum_executable_history_failed",
            validate_research_dataset_requirements(research_dataset=global_research_dataset),
        )

        scoped_frame = raw_panel.loc[raw_panel["subject"].isin(["AAA", "BBB"])].copy()
        scoped_research_dataset = scope_research_dataset_to_frame(
            research_dataset=global_research_dataset,
            scoped_frame=scoped_frame,
        )

        self.assertTrue(scoped_research_dataset["minimum_executable_history_passed"])
        self.assertEqual(validate_research_dataset_requirements(research_dataset=scoped_research_dataset), [])
        self.assertEqual(scoped_research_dataset["dataset_scope"]["scope_kind"], "strategy_universe")
        self.assertEqual(scoped_research_dataset["dataset_scope"]["scope_subject_count"], 2)
        self.assertFalse(
            scoped_research_dataset["dataset_scope"]["base_metrics"]["minimum_executable_history_passed"]
        )


if __name__ == "__main__":
    unittest.main()
