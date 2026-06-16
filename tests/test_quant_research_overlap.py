from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.alpha_manifest import build_daily_alpha_manifest_entry, write_daily_alpha_manifest
from enhengclaw.quant_research.contracts import utc_now, write_json
from enhengclaw.quant_research.experiment_status import EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX
from enhengclaw.quant_research.governance import build_strategy_entry, load_strategy_library, save_strategy_library
from enhengclaw.quant_research.lab import _backtest_single_asset
from enhengclaw.quant_research.overlap_integrity import (
    chronological_split_with_purge,
    evaluate_overlap_integrity,
    infer_interval_ms,
    infer_label_horizon_bars,
    walk_forward_split_with_purge,
)
from enhengclaw.quant_research.overlap_rerun import (
    discover_experiments_needing_overlap_rerun,
    mark_experiments_needing_overlap_rerun,
    remediate_historical_overlap_reruns,
)
from enhengclaw.quant_research.split_realization_contract import build_split_realization_contract
from enhengclaw.quant_research.validation_contract import VALIDATION_CONTRACT_VERSION


class QuantResearchOverlapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-overlap-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        self._saved_source_commit_sha = os.environ.get("SOURCE_COMMIT_SHA")
        os.environ["SOURCE_COMMIT_SHA"] = "abc123"
        self.addCleanup(self._restore_source_commit_sha)

    def _restore_source_commit_sha(self) -> None:
        if self._saved_source_commit_sha is None:
            os.environ.pop("SOURCE_COMMIT_SHA", None)
        else:
            os.environ["SOURCE_COMMIT_SHA"] = self._saved_source_commit_sha

    def test_split_realization_contract_defaults_match_shape_contract(self) -> None:
        single_asset = build_split_realization_contract(shape="single_asset", interval="4h")
        cross_sectional = build_split_realization_contract(shape="cross_sectional", interval="1d")
        self.assertEqual(single_asset["target_horizon_bars"], 6)
        self.assertEqual(single_asset["realization_step_bars"], 6)
        self.assertEqual(single_asset["partition_gap_bars"], 6)
        self.assertEqual(single_asset["skipped_between_partitions_bars"], 5)
        self.assertEqual(cross_sectional["target_horizon_bars"], 1)
        self.assertEqual(cross_sectional["realization_step_bars"], 1)
        self.assertEqual(cross_sectional["partition_gap_bars"], 1)
        self.assertEqual(cross_sectional["skipped_between_partitions_bars"], 0)

    def test_single_asset_split_purge_eliminates_label_overlap(self) -> None:
        frame = self._single_asset_frame(periods=48, horizon_bars=6)
        split_contract = build_split_realization_contract(shape="single_asset", interval="4h")
        split = chronological_split_with_purge(
            frame,
            time_col="timestamp_ms",
            split_realization_contract=split_contract,
        )
        self.assertIsNotNone(split)
        train_df, validation_df, test_df = split or (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        overlap = evaluate_overlap_integrity(
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            split_realization_contract=split_contract,
            evaluation_step_bars=6,
            prediction_count=len(test_df),
            rebalance_count=max(len(test_df) // 6, 1),
        )
        self.assertEqual(overlap["label_split_overlap"], 0)
        self.assertFalse(overlap["backtest_horizon_mismatch"]["detected"])
        self.assertTrue(overlap["passed"])

    def test_infer_interval_ms_ignores_duplicate_cross_sectional_timestamps(self) -> None:
        frame = self._cross_sectional_frame(periods=40)
        self.assertEqual(infer_interval_ms(frame["timestamp_ms"]), 24 * 60 * 60 * 1000)

    def test_cross_sectional_horizon_one_inference_and_overlap_gate(self) -> None:
        frame = self._cross_sectional_frame(periods=40)
        self.assertEqual(infer_label_horizon_bars(frame=frame), 1)
        split_contract = build_split_realization_contract(shape="cross_sectional", interval="1d")
        split = chronological_split_with_purge(
            frame,
            time_col="timestamp_ms",
            split_realization_contract=split_contract,
        )
        self.assertIsNotNone(split)
        train_df, validation_df, test_df = split or (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        overlap = evaluate_overlap_integrity(
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            split_realization_contract=split_contract,
            evaluation_step_bars=1,
            prediction_count=len(test_df),
            rebalance_count=len(test_df["timestamp_ms"].drop_duplicates()),
        )
        self.assertEqual(overlap["label_split_overlap"], 0)
        self.assertTrue(overlap["passed"])

    def test_overlap_gate_rejects_non_positive_interval(self) -> None:
        frame = self._cross_sectional_frame(periods=40)
        split = chronological_split_with_purge(frame, time_col="timestamp_ms", label_horizon_bars=1)
        self.assertIsNotNone(split)
        train_df, validation_df, test_df = split or (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        with self.assertRaisesRegex(ValueError, "bar_interval_ms must be a positive integer"):
            evaluate_overlap_integrity(
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
                label_horizon_bars=1,
                bar_interval_ms=0,
                evaluation_step_bars=1,
                prediction_count=len(test_df),
                rebalance_count=len(test_df["timestamp_ms"].drop_duplicates()),
            )

        ordered_times = sorted(frame["timestamp_ms"].drop_duplicates().tolist())
        with self.assertRaisesRegex(ValueError, "interval_ms must be a positive integer"):
            walk_forward_split_with_purge(
                frame=frame,
                time_col="timestamp_ms",
                train_end=pd.to_datetime(ordered_times[20], unit="ms", utc=True),
                validation_end=pd.to_datetime(ordered_times[30], unit="ms", utc=True),
                test_end=pd.to_datetime(ordered_times[-1], unit="ms", utc=True),
                interval_ms=0,
                label_horizon_bars=1,
            )

    def test_single_asset_backtest_uses_non_overlapping_realization(self) -> None:
        frame = self._single_asset_frame(periods=18, horizon_bars=6)
        frame["score"] = 1.0
        metrics = _backtest_single_asset(
            frame,
            constraints={"long_only": True, "long_leverage": 1.0},
            split_realization_contract=build_split_realization_contract(shape="single_asset", interval="4h"),
        )
        self.assertEqual(metrics["evaluation_step_bars"], 6)
        self.assertEqual(metrics["rebalance_count"], 2)

    def test_overlap_rerun_migration_rewrites_canonical_statuses(self) -> None:
        entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-regression-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [entry],
            },
        )
        experiment_root = self.artifacts_root / "experiments" / "2026-04-20-baseline-eth-balanced-logistic-regression-single-asset"
        experiment_root.mkdir(parents=True, exist_ok=True)
        alpha_card = {
            "generated_at_utc": utc_now(),
            "experiment_id": "2026-04-20-baseline-eth-balanced-logistic-regression-single-asset",
            "as_of": "2026-04-20",
            "shape": "single_asset",
            "model_family": "logistic_regression",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "strategy_id": entry["strategy_id"],
            "spec_hash": entry["spec_hash"],
            "source": entry["source"],
            "compiler_backend": "deterministic",
            "backend_mode": "deterministic",
            "experiment_status": "fail",
            "dataset_provenance": "live_ohlcv_dataset",
            "lifecycle": "active",
            "monitoring_status": "active",
            "selection_lane": "active",
            "promotion_state": "promoted",
            "validation": "failed",
            "publication_status": "archived_only",
            "validation_metrics": {"net_return": -0.1, "sharpe": -0.2},
            "test_metrics": {"net_return": -0.2, "sharpe": -0.3, "max_drawdown": 0.1, "trade_count": 20, "rebalance_count": 20},
            "walk_forward": {"window_count": 4, "median_oos_sharpe": -0.1, "windows": []},
        }
        for file_name in ("alpha_card.json", "validation_report.json", "backtest_report.json", "experiment_spec.json"):
            write_json(experiment_root / file_name, alpha_card)
        manifest_entry = build_daily_alpha_manifest_entry(alpha_card_path=experiment_root / "alpha_card.json", alpha_card=alpha_card)
        self.assertIsNotNone(manifest_entry)
        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
            entries=[manifest_entry] if manifest_entry is not None else [],
        )

        summary = mark_experiments_needing_overlap_rerun(
            artifacts_root=self.artifacts_root,
            workbench_root=self.workbench_root,
            as_of="2026-04-20",
        )

        self.assertEqual(summary["status"], "success")
        rewritten = json.loads((experiment_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(rewritten["experiment_status"], EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX)
        self.assertEqual(rewritten["validation"], "insufficient_track_record")
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        updated_entry = library["entries"][0]
        self.assertEqual(updated_entry["last_daily_experiment_status"], EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX)
        self.assertEqual(updated_entry["daily_pass_streak"], 0)
        self.assertEqual(updated_entry["daily_fail_streak"], 0)

    def test_overlap_rerun_discovery_and_partial_rewrite_only_touch_affected_experiment(self) -> None:
        affected_entry = build_strategy_entry(
            strategy_id="baseline-balanced-carry-funding-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter=None,
            model_family="carry_funding",
            feature_groups=["core_context", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        unaffected_entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-regression-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [affected_entry, unaffected_entry],
            },
        )
        affected_root = self._write_canonical_experiment(
            as_of="2026-04-20",
            entry=affected_entry,
            bar_interval_ms=0,
            validation_contract_version="quant_validation_contract.v2",
            include_split_realization_contract=False,
        )
        unaffected_root = self._write_canonical_experiment(
            as_of="2026-04-20",
            entry=unaffected_entry,
            bar_interval_ms=4 * 60 * 60 * 1000,
            validation_contract_version=VALIDATION_CONTRACT_VERSION,
            include_split_realization_contract=True,
        )
        manifest_entries = []
        for experiment_root in (affected_root, unaffected_root):
            alpha_card = json.loads((experiment_root / "alpha_card.json").read_text(encoding="utf-8"))
            entry = build_daily_alpha_manifest_entry(alpha_card_path=experiment_root / "alpha_card.json", alpha_card=alpha_card)
            self.assertIsNotNone(entry)
            if entry is not None:
                manifest_entries.append(entry)
        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
            entries=manifest_entries,
        )

        discovered = discover_experiments_needing_overlap_rerun(artifacts_root=self.artifacts_root)
        self.assertEqual(
            discovered,
            {"2026-04-20": ["2026-04-20-baseline-balanced-carry-funding-cross-sectional"]},
        )

        summary = mark_experiments_needing_overlap_rerun(
            artifacts_root=self.artifacts_root,
            workbench_root=self.workbench_root,
            as_of="2026-04-20",
            experiment_ids=discovered["2026-04-20"],
        )
        self.assertEqual(summary["rewritten_experiment_ids"], discovered["2026-04-20"])

        affected_alpha_card = json.loads((affected_root / "alpha_card.json").read_text(encoding="utf-8"))
        unaffected_alpha_card = json.loads((unaffected_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(affected_alpha_card["experiment_status"], EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX)
        self.assertEqual(unaffected_alpha_card["experiment_status"], "fail")

        manifest = json.loads(
            (self.artifacts_root / "governance" / "daily_alpha_manifests" / "2026-04-20.json").read_text(encoding="utf-8")
        )
        manifest_statuses = {entry["experiment_id"]: entry["experiment_status"] for entry in manifest["entries"]}
        self.assertEqual(
            manifest_statuses["2026-04-20-baseline-balanced-carry-funding-cross-sectional"],
            EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
        )
        self.assertEqual(
            manifest_statuses["2026-04-20-baseline-eth-balanced-logistic-regression-single-asset"],
            "fail",
        )

        library = load_strategy_library(artifacts_root=self.artifacts_root)
        library_by_id = {entry["strategy_id"]: entry for entry in library["entries"]}
        self.assertEqual(
            library_by_id["baseline-balanced-carry-funding-cross-sectional"]["last_daily_experiment_status"],
            EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
        )
        self.assertNotEqual(
            library_by_id["baseline-eth-balanced-logistic-regression-single-asset"]["last_transition_reason"],
            "awaiting_overlap_rerun",
        )

        quality_summary = json.loads(
            (self.artifacts_root / "cycles" / "2026-04-20" / "research_quality_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(quality_summary["experiment_status_counts"]["fail"], 1)
        self.assertEqual(
            quality_summary["experiment_status_counts"][EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX],
            1,
        )
        self.assertEqual(quality_summary["decisive_experiment_count"], 1)

    def test_historical_overlap_rerun_remediation_scans_all_manifests(self) -> None:
        affected_entry = build_strategy_entry(
            strategy_id="baseline-balanced-basis-divergence-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter=None,
            model_family="basis_divergence",
            feature_groups=["core_context", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        clean_entry = build_strategy_entry(
            strategy_id="baseline-sui-balanced-meta-labeling-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="SUI",
            universe_filter=None,
            model_family="meta_labeling",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [affected_entry, clean_entry],
            },
        )
        affected_root = self._write_canonical_experiment(
            as_of="2026-04-20",
            entry=affected_entry,
            bar_interval_ms=0,
            validation_contract_version="quant_validation_contract.v2",
            include_split_realization_contract=False,
        )
        clean_root = self._write_canonical_experiment(
            as_of="2026-04-21",
            entry=clean_entry,
            bar_interval_ms=4 * 60 * 60 * 1000,
            validation_contract_version=VALIDATION_CONTRACT_VERSION,
            include_split_realization_contract=True,
        )
        for as_of, experiment_root in (("2026-04-20", affected_root), ("2026-04-21", clean_root)):
            alpha_card = json.loads((experiment_root / "alpha_card.json").read_text(encoding="utf-8"))
            entry = build_daily_alpha_manifest_entry(alpha_card_path=experiment_root / "alpha_card.json", alpha_card=alpha_card)
            self.assertIsNotNone(entry)
            write_daily_alpha_manifest(
                artifacts_root=self.artifacts_root,
                as_of=as_of,
                entries=[entry] if entry is not None else [],
            )

        summary = remediate_historical_overlap_reruns(
            artifacts_root=self.artifacts_root,
            workbench_root=self.workbench_root,
        )
        self.assertEqual(summary["affected_dates"], ["2026-04-20"])
        self.assertEqual(summary["affected_experiment_count"], 1)
        self.assertEqual(len(summary["per_as_of"]), 1)

        affected_alpha_card = json.loads((affected_root / "alpha_card.json").read_text(encoding="utf-8"))
        clean_alpha_card = json.loads((clean_root / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(affected_alpha_card["experiment_status"], EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX)
        self.assertEqual(clean_alpha_card["experiment_status"], "fail")

    def _single_asset_frame(self, *, periods: int, horizon_bars: int) -> pd.DataFrame:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        closes = [100.0 + float(index) for index in range(periods)]
        frame = pd.DataFrame(
            {
                "timestamp_ms": [int((start + timedelta(hours=4 * index)).timestamp() * 1000) for index in range(periods)],
                "spot_close": closes,
            }
        )
        frame["target_forward_return"] = frame["spot_close"].shift(-horizon_bars) / frame["spot_close"] - 1.0
        frame["subject"] = "ETH"
        frame = frame.dropna().reset_index(drop=True)
        return frame

    def _cross_sectional_frame(self, *, periods: int) -> pd.DataFrame:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows: list[dict[str, object]] = []
        for subject, base in (("ETH", 100.0), ("SUI", 10.0)):
            closes = [base + float(index) for index in range(periods)]
            subject_frame = pd.DataFrame(
                {
                    "timestamp_ms": [int((start + timedelta(days=index)).timestamp() * 1000) for index in range(periods)],
                    "spot_close": closes,
                    "subject": subject,
                }
            )
            subject_frame["target_forward_return"] = subject_frame["spot_close"].shift(-1) / subject_frame["spot_close"] - 1.0
            rows.extend(subject_frame.dropna().to_dict(orient="records"))
        return pd.DataFrame(rows).sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)

    def _write_canonical_experiment(
        self,
        *,
        as_of: str,
        entry: dict[str, object],
        bar_interval_ms: int,
        validation_contract_version: str,
        include_split_realization_contract: bool,
    ) -> Path:
        experiment_id = f"{as_of}-{entry['strategy_id']}"
        experiment_root = self.artifacts_root / "experiments" / experiment_id
        experiment_root.mkdir(parents=True, exist_ok=True)
        shape = str(entry["shape"])
        label_horizon_bars = 1 if shape == "cross_sectional" else 6
        partition_gap_bars = label_horizon_bars if include_split_realization_contract else max(label_horizon_bars - 1, 0)
        overlap_integrity = {
            "label_horizon_bars": label_horizon_bars,
            "bar_interval_ms": bar_interval_ms,
            "purge_gap_bars": partition_gap_bars,
            "split_boundary_contamination_counts": {
                "train_to_validation": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
                "validation_to_test": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
            },
            "label_split_overlap": 0,
            "backtest_horizon_mismatch": {
                "detected": False,
                "label_horizon_bars": label_horizon_bars,
                "evaluation_step_bars": label_horizon_bars,
                "prediction_count": 12,
                "rebalance_count": 12,
            },
            "passed": True,
        }
        split_realization_contract = (
            build_split_realization_contract(shape=shape, bar_interval_ms=bar_interval_ms)
            if include_split_realization_contract
            else None
        )
        validation_contract = {
            "contract_version": validation_contract_version,
            "status": "failed",
            "required_sections_present": [
                "split_integrity",
                "walk_forward_assessment",
                "execution_stress",
                "regime_holdout",
            ],
            "blocker_codes": [],
        }
        payload = {
            "generated_at_utc": utc_now(),
            "experiment_id": experiment_id,
            "as_of": as_of,
            "shape": shape,
            "model_family": entry["model_family"],
            "strategy_profile": entry["strategy_profile"],
            "subject": entry.get("subject"),
            "strategy_id": entry["strategy_id"],
            "spec_hash": entry["spec_hash"],
            "source": entry["source"],
            "compiler_backend": "deterministic",
            "backend_mode": "deterministic",
            "experiment_status": "fail",
            "dataset_provenance": "live_ohlcv_dataset",
            "lifecycle": entry["lifecycle"],
            "monitoring_status": entry["monitoring_status"],
            "selection_lane": entry["selection_lane"],
            "promotion_state": entry["promotion_state"],
            "validation": "failed",
            "publication_status": "archived_only",
            "validation_metrics": {"net_return": -0.1, "sharpe": -0.2},
            "test_metrics": {
                "net_return": -0.2,
                "sharpe": -0.3,
                "max_drawdown": 0.1,
                "trade_count": 20,
                "rebalance_count": 20,
            },
            "walk_forward": {"window_count": 4, "median_oos_sharpe": -0.1, "windows": []},
            "bar_interval_ms": bar_interval_ms,
            "label_horizon_bars": label_horizon_bars,
            "overlap_integrity": overlap_integrity,
            "validation_contract": dict(validation_contract),
            "quality_summary": {"quality_gate_passed": False, "quality_blockers": [], "metrics_snapshot": {}},
        }
        if split_realization_contract is not None:
            payload["split_realization_contract"] = split_realization_contract
        validation_report = dict(payload)
        validation_report["passed"] = True
        validation_report["validation_contract"] = {
            "contract_version": validation_contract_version,
            "status": "failed",
            "required_sections_present": list(validation_contract["required_sections_present"]),
            "blockers": [],
            "summary": {},
        }
        if split_realization_contract is not None:
            validation_report["split_integrity"] = {
                "split_realization_contract": split_realization_contract,
                "split_boundary_contamination_total": 0,
                "walk_forward_boundary_contamination_total": 0,
                "backtest_realization_mismatch": {"detected": False},
                "overlap_integrity": overlap_integrity,
                "leakage_checks": {"passed": True, "blockers": []},
                "passed": True,
            }
        for file_name, body in (
            ("alpha_card.json", payload),
            ("validation_report.json", validation_report),
            ("backtest_report.json", dict(validation_report)),
            ("experiment_spec.json", dict(payload)),
        ):
            write_json(experiment_root / file_name, body)
        return experiment_root


if __name__ == "__main__":
    unittest.main()
