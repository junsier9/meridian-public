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

from enhengclaw.ops.daily_review import DailyReviewPackBuilder


class DailyReviewPackBuilderTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_run_artifact(
        self,
        root: Path,
        run_id: str,
        *,
        symbol: str,
        status: str,
        decision: str | None,
        selection_mode: str = "default",
        allowed_provider_names: list[str] | None = None,
        rejected: list[dict[str, str]] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        provider_statuses: dict[str, str] | None = None,
        raw_payload_files: list[str] | None = None,
    ) -> Path:
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        allowed = allowed_provider_names or []
        rejected_items = rejected or []
        self._write_json(
            run_dir / "provider_selection_result.json",
            {
                "mode": selection_mode,
                "allowed_provider_names": allowed,
                "rejected_provider_names": [item["provider_name"] for item in rejected_items],
                "rejected": rejected_items,
            },
        )
        self._write_json(
            run_dir / "warnings_errors.json",
            {
                "warnings": warnings or [],
                "errors": errors or [],
            },
        )
        self._write_json(
            run_dir / "ops_report.json",
            {
                "providers": [
                    {"provider_name": name, "portfolio_status": portfolio_status}
                    for name, portfolio_status in (provider_statuses or {}).items()
                ]
            },
        )
        self._write_json(run_dir / "normalized_signal_summary.json", [])
        if decision is not None:
            self._write_json(
                run_dir / "runtime_result.json",
                {
                    "decision": decision,
                    "research_object": {"object_id": f"pilot:{run_id}:{symbol.upper()}"},
                },
            )
        for relative_name in raw_payload_files or []:
            raw_path = run_dir / "raw" / relative_name
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text("{}", encoding="utf-8")
        return run_dir

    def test_empty_directories_produce_valid_pack(self) -> None:
        with tempfile.TemporaryDirectory() as runs_dir, tempfile.TemporaryDirectory() as batches_dir, tempfile.TemporaryDirectory() as output_dir:
            builder = DailyReviewPackBuilder(
                pilot_runs_root=runs_dir,
                pilot_batches_root=batches_dir,
                output_root=output_dir,
            )
            result = builder.build_and_write(date_utc="2026-04-07", write_markdown=True)

            self.assertEqual(result.pack.run_count, 0)
            self.assertEqual(result.pack.batch_count, 0)
            self.assertEqual(result.pack.status_distribution, {})
            self.assertEqual(result.pack.decision_distribution, {})
            self.assertTrue(Path(result.artifacts.json_path).exists())
            self.assertTrue(Path(result.artifacts.markdown_path).exists())

    def test_multiple_runs_and_batches_are_aggregated_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as runs_dir, tempfile.TemporaryDirectory() as batches_dir, tempfile.TemporaryDirectory() as output_dir:
            runs_root = Path(runs_dir)
            batches_root = Path(batches_dir)
            self._write_run_artifact(
                runs_root,
                "20260407T010101Z_000001_aix",
                symbol="AIX",
                status="ok",
                decision="monitoring",
                allowed_provider_names=["binance-public-cex"],
                rejected=[{"provider_name": "real_onchain_provider_shadow", "reason": "retired providers are not selectable"}],
                provider_statuses={"binance-public-cex": "active", "real_onchain_provider_shadow": "retired"},
                raw_payload_files=["binance-public-cex/cex_snapshot.json"],
            )
            self._write_run_artifact(
                runs_root,
                "20260407T020202Z_000002_bad",
                symbol="BAD",
                status="runtime_unavailable",
                decision=None,
                allowed_provider_names=[],
                rejected=[{"provider_name": "binance-public-cex", "reason": "provider is not in default runtime allowlist"}],
                warnings=["default runtime unavailable; fail closed"],
                errors=["provider selection rejected all candidate providers"],
                provider_statuses={"binance-public-cex": "probation"},
            )

            batch_dir = batches_root / "20260407T030303Z_000003"
            batch_runs_root = batch_dir / "runs"
            run_btc = self._write_run_artifact(
                batch_runs_root,
                "20260407T030304Z_000004_btc",
                symbol="BTC",
                status="ok",
                decision="publish",
                selection_mode="include_shadow",
                allowed_provider_names=["binance-public-cex", "real_onchain_provider_shadow"],
                provider_statuses={"binance-public-cex": "active", "real_onchain_provider_shadow": "shadow_only"},
                raw_payload_files=[
                    "binance-public-cex/cex_snapshot.json",
                    "real_onchain_provider_shadow/onchain_snapshot.csv",
                ],
            )
            run_eth = self._write_run_artifact(
                batch_runs_root,
                "20260407T030305Z_000005_eth",
                symbol="ETH",
                status="error",
                decision=None,
                selection_mode="manual_override",
                allowed_provider_names=["real_onchain_provider_shadow"],
                provider_statuses={"real_onchain_provider_shadow": "retired"},
                errors=["simulated downstream error"],
                raw_payload_files=["real_onchain_provider_shadow/onchain_snapshot.csv"],
            )
            self._write_json(
                batch_dir / "batch_summary.json",
                {
                    "batch_id": "20260407T030303Z_000003",
                    "symbols": ["BTC", "ETH"],
                    "success_count": 1,
                    "runtime_unavailable_count": 0,
                    "error_count": 1,
                    "runs": [
                        {
                            "symbol": "BTC",
                            "status": "ok",
                            "decision": "publish",
                            "archive_path": str(run_btc),
                            "warnings": [],
                            "errors": [],
                            "provider_mode": "replay",
                        },
                        {
                            "symbol": "ETH",
                            "status": "error",
                            "decision": None,
                            "archive_path": str(run_eth),
                            "warnings": [],
                            "errors": ["simulated downstream error"],
                            "provider_mode": "replay",
                        },
                    ],
                },
            )

            builder = DailyReviewPackBuilder(
                pilot_runs_root=runs_root,
                pilot_batches_root=batches_root,
                output_root=output_dir,
            )
            pack = builder.build(date_utc="2026-04-07")

            self.assertEqual(pack.run_count, 4)
            self.assertEqual(pack.batch_count, 1)
            self.assertEqual(pack.decision_distribution["monitoring"], 1)
            self.assertEqual(pack.decision_distribution["publish"], 1)
            self.assertEqual(pack.decision_distribution["none"], 2)
            self.assertEqual(pack.status_distribution["ok"], 2)
            self.assertEqual(pack.status_distribution["runtime_unavailable"], 1)
            self.assertEqual(pack.status_distribution["error"], 1)
            self.assertEqual(pack.provider_selection_distribution["binance-public-cex"], 1)
            self.assertEqual(pack.provider_selection_distribution["(none)"], 1)
            self.assertEqual(pack.provider_selection_distribution["binance-public-cex+real_onchain_provider_shadow"], 1)
            self.assertEqual(pack.provider_selection_distribution["real_onchain_provider_shadow"], 1)
            self.assertCountEqual(pack.symbols_run, ["AIX", "BAD", "BTC", "ETH"])
            self.assertEqual(pack.raw_payload_files_count, 4)
            self.assertEqual(pack.replay_compatible_records_count, 4)
            self.assertEqual(pack.fail_closed_count, 1)
            self.assertEqual(pack.rejected_provider_frequency["real_onchain_provider_shadow"], 1)

    def test_non_default_and_debug_override_usage_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as runs_dir, tempfile.TemporaryDirectory() as batches_dir:
            runs_root = Path(runs_dir)
            self._write_run_artifact(
                runs_root,
                "20260407T040404Z_000006_btc",
                symbol="BTC",
                status="ok",
                decision="monitoring",
                selection_mode="include_shadow",
                allowed_provider_names=["binance-public-cex", "real_onchain_provider_shadow"],
                provider_statuses={"binance-public-cex": "active", "real_onchain_provider_shadow": "shadow_only"},
            )
            self._write_run_artifact(
                runs_root,
                "20260407T050505Z_000007_eth",
                symbol="ETH",
                status="ok",
                decision="monitoring",
                selection_mode="manual_override",
                allowed_provider_names=["real_onchain_provider_shadow"],
                provider_statuses={"real_onchain_provider_shadow": "retired"},
            )

            builder = DailyReviewPackBuilder(
                pilot_runs_root=runs_root,
                pilot_batches_root=batches_dir,
            )
            pack = builder.build(date_utc="2026-04-07")

            self.assertEqual(pack.non_default_mode_count, 2)
            self.assertEqual(pack.debug_override_count, 1)
            self.assertEqual(pack.selection_mode_distribution["include_shadow"], 1)
            self.assertEqual(pack.selection_mode_distribution["manual_override"], 1)

    def test_builder_is_read_only_for_source_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as runs_dir, tempfile.TemporaryDirectory() as batches_dir, tempfile.TemporaryDirectory() as output_dir:
            run_dir = self._write_run_artifact(
                Path(runs_dir),
                "20260407T060606Z_000008_aix",
                symbol="AIX",
                status="ok",
                decision="monitoring",
                allowed_provider_names=["binance-public-cex"],
                provider_statuses={"binance-public-cex": "active"},
                raw_payload_files=["binance-public-cex/cex_snapshot.json"],
            )
            selection_path = run_dir / "provider_selection_result.json"
            before = selection_path.read_text(encoding="utf-8")

            builder = DailyReviewPackBuilder(
                pilot_runs_root=runs_dir,
                pilot_batches_root=batches_dir,
                output_root=output_dir,
            )
            builder.build_and_write(date_utc="2026-04-07", write_markdown=True)
            after = selection_path.read_text(encoding="utf-8")

            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
