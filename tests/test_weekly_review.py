from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.weekly_review import WeeklyReviewBuilder


class WeeklyReviewBuilderTests(unittest.TestCase):
    def _write_daily_pack(
        self,
        root: Path,
        day: str,
        *,
        run_count: int = 0,
        batch_count: int = 0,
        symbols_run: list[str] | None = None,
        decision_distribution: dict[str, int] | None = None,
        status_distribution: dict[str, int] | None = None,
        provider_selection_distribution: dict[str, int] | None = None,
        fail_closed_count: int = 0,
        runtime_unavailable_runs: list[str] | None = None,
        debug_override_count: int = 0,
        raw_payload_files_count: int = 0,
        replay_compatible_records_count: int = 0,
        rejected_provider_frequency: dict[str, int] | None = None,
        rejected_provider_reason_frequency: dict[str, int] | None = None,
    ) -> Path:
        pack_dir = root / day
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "date_utc": day,
            "generated_at_utc": f"{day}T00:00:00+00:00",
            "run_count": run_count,
            "batch_count": batch_count,
            "symbols_run": symbols_run or [],
            "decision_distribution": decision_distribution or {},
            "status_distribution": status_distribution or {},
            "provider_selection_distribution": provider_selection_distribution or {},
            "selection_mode_distribution": {},
            "non_default_mode_count": 0,
            "debug_override_count": debug_override_count,
            "raw_payload_files_count": raw_payload_files_count,
            "replay_compatible_records_count": replay_compatible_records_count,
            "runtime_unavailable_runs": runtime_unavailable_runs or [],
            "error_runs": [],
            "fail_closed_count": fail_closed_count,
            "rejected_provider_frequency": rejected_provider_frequency or {},
            "rejected_provider_reason_frequency": rejected_provider_reason_frequency or {},
            "runs": [],
        }
        path = pack_dir / "daily_review_pack.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_missing_daily_packs_still_generate_valid_weekly_review(self) -> None:
        with tempfile.TemporaryDirectory() as daily_root, tempfile.TemporaryDirectory() as output_root:
            self._write_daily_pack(Path(daily_root), "2026-04-07", run_count=2, symbols_run=["AIX"])
            builder = WeeklyReviewBuilder(
                daily_review_packs_root=daily_root,
                output_root=output_root,
            )
            result = builder.build_and_write(
                start_date_utc="2026-04-07",
                end_date_utc="2026-04-09",
                write_markdown=True,
            )

            self.assertEqual(result.pack.total_run_count, 2)
            self.assertEqual(result.pack.missing_daily_packs, ["2026-04-08", "2026-04-09"])
            self.assertEqual(len(result.pack.days), 3)
            self.assertTrue(Path(result.artifacts.json_path).exists())
            self.assertTrue(Path(result.artifacts.markdown_path).exists())

    def test_multi_day_data_is_aggregated_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as daily_root:
            root = Path(daily_root)
            self._write_daily_pack(
                root,
                "2026-04-07",
                run_count=4,
                batch_count=1,
                symbols_run=["AIX", "BTC"],
                decision_distribution={"monitoring": 3, "publish": 1},
                status_distribution={"ok": 4},
                provider_selection_distribution={"binance-public-cex": 4},
                raw_payload_files_count=4,
                replay_compatible_records_count=4,
                rejected_provider_frequency={"real_onchain_provider_shadow": 4},
                rejected_provider_reason_frequency={"retired providers are not selectable": 4},
            )
            self._write_daily_pack(
                root,
                "2026-04-08",
                run_count=2,
                batch_count=0,
                symbols_run=["ETH", "SOL"],
                decision_distribution={"monitoring": 2},
                status_distribution={"ok": 1, "runtime_unavailable": 1},
                provider_selection_distribution={"binance-public-cex": 1, "(none)": 1},
                fail_closed_count=1,
                runtime_unavailable_runs=["20260408T010101Z_bad"],
                raw_payload_files_count=1,
                replay_compatible_records_count=1,
                rejected_provider_frequency={"binance-public-cex": 1},
                rejected_provider_reason_frequency={"provider is not in default runtime allowlist": 1},
            )

            builder = WeeklyReviewBuilder(daily_review_packs_root=root)
            pack = builder.build(start_date_utc="2026-04-07", end_date_utc="2026-04-08")

            self.assertEqual(pack.total_run_count, 6)
            self.assertEqual(pack.total_batch_count, 1)
            self.assertCountEqual(pack.symbols_seen, ["AIX", "BTC", "ETH", "SOL"])
            self.assertEqual(pack.decision_distribution_by_day["2026-04-07"]["publish"], 1)
            self.assertEqual(pack.status_distribution_by_day["2026-04-08"]["runtime_unavailable"], 1)
            self.assertEqual(pack.provider_selection_distribution_by_day["2026-04-08"]["(none)"], 1)
            self.assertEqual(pack.fail_closed_trend["2026-04-08"], 1)
            self.assertEqual(pack.runtime_unavailable_trend["2026-04-08"], 1)
            self.assertEqual(
                pack.rejected_provider_trend["2026-04-07"]["real_onchain_provider_shadow"],
                4,
            )

    def test_operator_checklist_reflects_fail_closed_debug_override_and_selection_shift(self) -> None:
        with tempfile.TemporaryDirectory() as daily_root:
            root = Path(daily_root)
            self._write_daily_pack(
                root,
                "2026-04-07",
                run_count=3,
                status_distribution={"ok": 3},
                provider_selection_distribution={"binance-public-cex": 3},
                raw_payload_files_count=3,
                replay_compatible_records_count=3,
            )
            self._write_daily_pack(
                root,
                "2026-04-08",
                run_count=2,
                status_distribution={"ok": 1, "runtime_unavailable": 1},
                provider_selection_distribution={"binance-public-cex+real_onchain_provider_shadow": 1, "(none)": 1},
                fail_closed_count=1,
                runtime_unavailable_runs=["run-bad"],
                debug_override_count=1,
                raw_payload_files_count=1,
                replay_compatible_records_count=1,
            )

            builder = WeeklyReviewBuilder(daily_review_packs_root=root)
            pack = builder.build(start_date_utc="2026-04-07", end_date_utc="2026-04-08")
            checklist = pack.operator_checklist

            self.assertTrue(checklist.default_runtime_unavailable_any_day)
            self.assertTrue(checklist.debug_override_seen)
            self.assertTrue(checklist.provider_selection_anomaly)
            self.assertTrue(checklist.review_new_raw_payloads)
            self.assertTrue(checklist.review_new_replay_records)
            self.assertTrue(checklist.golden_corpus_candidates_present)
            self.assertTrue(any("default runtime became unavailable" in note for note in checklist.notes))
            self.assertTrue(any("debug override" in note for note in checklist.notes))
            self.assertTrue(any("provider selection distribution shifted" in note for note in checklist.notes))

    def test_builder_is_read_only_for_daily_packs(self) -> None:
        with tempfile.TemporaryDirectory() as daily_root, tempfile.TemporaryDirectory() as output_root:
            path = self._write_daily_pack(
                Path(daily_root),
                "2026-04-07",
                run_count=1,
                status_distribution={"ok": 1},
                provider_selection_distribution={"binance-public-cex": 1},
            )
            before = path.read_text(encoding="utf-8")

            builder = WeeklyReviewBuilder(
                daily_review_packs_root=daily_root,
                output_root=output_root,
            )
            builder.build_and_write(
                start_date_utc="2026-04-07",
                end_date_utc="2026-04-07",
                write_markdown=True,
            )
            after = path.read_text(encoding="utf-8")

            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
