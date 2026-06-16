from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import write_json
from enhengclaw.quant_research.deterministic_survival import (
    BASELINE_ALPHA_SURVIVAL_CONTRACT_VERSION,
    DAILY_SAMPLE_CONTRACT_VERSION,
    SURVIVAL_OUTCOME_BLOCKED,
    SURVIVAL_OUTCOME_FAILED,
    SURVIVAL_OUTCOME_MISSING,
    SURVIVAL_OUTCOME_SURVIVED,
    run_baseline_alpha_survival,
    run_quant_deterministic_daily_sample,
)


ETH_STRATEGY_ID = "core-eth-conservative-breakout-volatility-expansion-single-asset"
BTC_STRATEGY_ID = "core-btc-balanced-mean-reversion-single-asset"
CROSS_SECTIONAL_STRATEGY_ID = "core-liquidity-balanced-ranking-scorer-cross-sectional"


class DeterministicSurvivalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-deterministic-survival-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_input_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.spot_root = self.temp_dir / "external" / "coinapi_ohlcv"
        self.perp_root = self.temp_dir / "external" / "binance_ohlcv"
        self.derivatives_root = self.temp_dir / "external" / "derivatives"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        env_patcher = patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    def test_daily_sample_runner_writes_survived_and_blocked_single_asset_outcomes(self) -> None:
        as_of = "2026-04-24"
        manifest = self._strategy_manifest()

        def fake_cycle(**kwargs):
            self.assertEqual(kwargs["as_of"], as_of)
            self.assertEqual(Path(kwargs["ohlcv_external_root"]).resolve(), self.perp_root.resolve())
            self.assertEqual(Path(kwargs["spot_ohlcv_external_root"]).resolve(), self.spot_root.resolve())
            self._write_experiment(
                as_of=as_of,
                strategy_id=ETH_STRATEGY_ID,
                subject="ETH",
                outcome=SURVIVAL_OUTCOME_SURVIVED,
            )
            self._write_experiment(
                as_of=as_of,
                strategy_id=BTC_STRATEGY_ID,
                subject="BTC",
                outcome=SURVIVAL_OUTCOME_BLOCKED,
            )
            return {
                "status": "success",
                "summary_path": str(self.artifacts_root / "cycles" / as_of / "quant_cycle_summary.json"),
                "experiment_ids": [
                    f"{as_of}-{ETH_STRATEGY_ID}",
                    f"{as_of}-{BTC_STRATEGY_ID}",
                ],
                "blocked_strategy_ids": [BTC_STRATEGY_ID],
                "data_gap_blockers": ["BTC: missing perp_close for execution path"],
            }

        with patch("enhengclaw.quant_research.deterministic_survival.load_deterministic_strategy_manifest", return_value=manifest), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_input_producer", return_value=self._producer_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_freeze", return_value=self._freeze_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival._write_derivatives_evidence_for_as_of", return_value=({"status": "success"}, self.derivatives_root / "summaries" / as_of / "sync_summary.json")), \
             patch("enhengclaw.quant_research.lab.run_quant_research_cycle", side_effect=fake_cycle):
            sample = run_quant_deterministic_daily_sample(
                as_of=as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_input_root,
                workbench_root=self.workbench_root,
                spot_ohlcv_external_root=self.spot_root,
                perp_ohlcv_external_root=self.perp_root,
                derivatives_external_root=self.derivatives_root,
            )

        self.assertEqual(sample["contract_version"], DAILY_SAMPLE_CONTRACT_VERSION)
        self.assertEqual(sample["eligible_strategy_ids"], [ETH_STRATEGY_ID, BTC_STRATEGY_ID])
        self.assertEqual(sample["strategy_outcome_counts"][SURVIVAL_OUTCOME_SURVIVED], 1)
        self.assertEqual(sample["strategy_outcome_counts"][SURVIVAL_OUTCOME_BLOCKED], 1)
        self.assertTrue((self.artifacts_root / "cycles" / as_of / "deterministic_daily_sample.json").exists())
        sample_by_strategy = {
            item["strategy_id"]: item
            for item in sample["strategy_samples"]
        }
        self.assertEqual(sample_by_strategy[ETH_STRATEGY_ID]["outcome"], SURVIVAL_OUTCOME_SURVIVED)
        self.assertEqual(sample_by_strategy[BTC_STRATEGY_ID]["outcome"], SURVIVAL_OUTCOME_BLOCKED)
        self.assertNotIn(CROSS_SECTIONAL_STRATEGY_ID, sample_by_strategy)

    def test_daily_sample_runner_writes_blocked_sample_when_cycle_stops_before_experiments(self) -> None:
        as_of = "2026-04-24"
        manifest = self._strategy_manifest()
        error_message = "deterministic quant core blocked before experiments: single_asset_spot_history_gap"

        with patch("enhengclaw.quant_research.deterministic_survival.load_deterministic_strategy_manifest", return_value=manifest), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_input_producer", return_value=self._producer_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_freeze", return_value=self._freeze_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival._write_derivatives_evidence_for_as_of", return_value=({"status": "success"}, self.derivatives_root / "summaries" / as_of / "sync_summary.json")), \
             patch("enhengclaw.quant_research.lab.run_quant_research_cycle", side_effect=RuntimeError(error_message)):
            sample = run_quant_deterministic_daily_sample(
                as_of=as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_input_root,
                workbench_root=self.workbench_root,
                spot_ohlcv_external_root=self.spot_root,
                perp_ohlcv_external_root=self.perp_root,
                derivatives_external_root=self.derivatives_root,
            )

        self.assertEqual(sample["cycle_status"], "blocked_before_experiments")
        self.assertEqual(sample["cycle_error_message"], error_message)
        for item in sample["strategy_samples"]:
            self.assertEqual(item["outcome"], SURVIVAL_OUTCOME_BLOCKED)
            self.assertIn("single_asset_spot_history_gap", item["blocker_codes"])

    def test_daily_sample_runner_resolves_hashed_experiment_directory(self) -> None:
        as_of = "2026-04-24"
        manifest = self._strategy_manifest()

        def fake_cycle(**kwargs):
            self.assertEqual(kwargs["as_of"], as_of)
            self._write_experiment(
                as_of=as_of,
                strategy_id=ETH_STRATEGY_ID,
                subject="ETH",
                outcome=SURVIVAL_OUTCOME_SURVIVED,
                hashed_directory=True,
            )
            self._write_experiment(
                as_of=as_of,
                strategy_id=BTC_STRATEGY_ID,
                subject="BTC",
                outcome=SURVIVAL_OUTCOME_FAILED,
            )
            return {
                "status": "success",
                "summary_path": str(self.artifacts_root / "cycles" / as_of / "quant_cycle_summary.json"),
                "experiment_ids": [
                    f"{as_of}-{ETH_STRATEGY_ID}",
                    f"{as_of}-{BTC_STRATEGY_ID}",
                ],
                "blocked_strategy_ids": [],
                "data_gap_blockers": [],
            }

        with patch("enhengclaw.quant_research.deterministic_survival.load_deterministic_strategy_manifest", return_value=manifest), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_input_producer", return_value=self._producer_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival.run_quant_universe_freeze", return_value=self._freeze_summary(as_of)), \
             patch("enhengclaw.quant_research.deterministic_survival._write_derivatives_evidence_for_as_of", return_value=({"status": "success"}, self.derivatives_root / "summaries" / as_of / "sync_summary.json")), \
             patch("enhengclaw.quant_research.lab.run_quant_research_cycle", side_effect=fake_cycle):
            sample = run_quant_deterministic_daily_sample(
                as_of=as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_input_root,
                workbench_root=self.workbench_root,
                spot_ohlcv_external_root=self.spot_root,
                perp_ohlcv_external_root=self.perp_root,
                derivatives_external_root=self.derivatives_root,
            )

        sample_by_strategy = {item["strategy_id"]: item for item in sample["strategy_samples"]}
        self.assertEqual(sample_by_strategy[ETH_STRATEGY_ID]["outcome"], SURVIVAL_OUTCOME_SURVIVED)
        self.assertEqual(sample_by_strategy[BTC_STRATEGY_ID]["outcome"], SURVIVAL_OUTCOME_BLOCKED)

    def test_baseline_alpha_survival_marks_alpha_like_after_five_consecutive_survived_days(self) -> None:
        manifest = self._strategy_manifest()
        for index, as_of in enumerate(["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24"], start=1):
            self._write_daily_sample(
                as_of=as_of,
                strategy_samples=[
                    self._strategy_sample(strategy_id=ETH_STRATEGY_ID, subject="ETH", outcome=SURVIVAL_OUTCOME_SURVIVED, spec_hash="eth-spec"),
                    self._strategy_sample(strategy_id=BTC_STRATEGY_ID, subject="BTC", outcome=SURVIVAL_OUTCOME_FAILED, spec_hash="btc-spec"),
                ],
            )

        with patch("enhengclaw.quant_research.deterministic_survival.load_deterministic_strategy_manifest", return_value=manifest):
            report = run_baseline_alpha_survival(
                date_from="2026-04-20",
                date_to="2026-04-24",
                survival_window_days=5,
                artifacts_root=self.artifacts_root,
            )

        self.assertEqual(report["contract_version"], BASELINE_ALPHA_SURVIVAL_CONTRACT_VERSION)
        self.assertTrue(report["started_looking_like_alpha"])
        self.assertEqual(report["alpha_like_strategy_ids"], [ETH_STRATEGY_ID])
        self.assertEqual(report["per_strategy"][ETH_STRATEGY_ID]["current_consecutive_survival_streak"], 5)
        self.assertEqual(report["per_strategy"][ETH_STRATEGY_ID]["max_consecutive_survival_streak"], 5)
        self.assertEqual(report["per_strategy"][BTC_STRATEGY_ID]["current_consecutive_survival_streak"], 0)
        self.assertNotIn(CROSS_SECTIONAL_STRATEGY_ID, report["eligible_strategy_ids"])

    def test_baseline_alpha_survival_breaks_streak_on_missing_sample(self) -> None:
        manifest = self._strategy_manifest()
        self._write_daily_sample(
            as_of="2026-04-20",
            strategy_samples=[
                self._strategy_sample(strategy_id=ETH_STRATEGY_ID, subject="ETH", outcome=SURVIVAL_OUTCOME_SURVIVED, spec_hash="eth-spec"),
                self._strategy_sample(strategy_id=BTC_STRATEGY_ID, subject="BTC", outcome=SURVIVAL_OUTCOME_BLOCKED, spec_hash="btc-spec"),
            ],
        )
        self._write_daily_sample(
            as_of="2026-04-21",
            strategy_samples=[
                self._strategy_sample(strategy_id=ETH_STRATEGY_ID, subject="ETH", outcome=SURVIVAL_OUTCOME_SURVIVED, spec_hash="eth-spec"),
                self._strategy_sample(strategy_id=BTC_STRATEGY_ID, subject="BTC", outcome=SURVIVAL_OUTCOME_BLOCKED, spec_hash="btc-spec"),
            ],
        )
        self._write_daily_sample(
            as_of="2026-04-23",
            strategy_samples=[
                self._strategy_sample(strategy_id=ETH_STRATEGY_ID, subject="ETH", outcome=SURVIVAL_OUTCOME_SURVIVED, spec_hash="eth-spec"),
                self._strategy_sample(strategy_id=BTC_STRATEGY_ID, subject="BTC", outcome=SURVIVAL_OUTCOME_FAILED, spec_hash="btc-spec"),
            ],
        )
        self._write_daily_sample(
            as_of="2026-04-24",
            strategy_samples=[
                self._strategy_sample(strategy_id=ETH_STRATEGY_ID, subject="ETH", outcome=SURVIVAL_OUTCOME_SURVIVED, spec_hash="eth-spec"),
                self._strategy_sample(strategy_id=BTC_STRATEGY_ID, subject="BTC", outcome=SURVIVAL_OUTCOME_FAILED, spec_hash="btc-spec"),
            ],
        )

        with patch("enhengclaw.quant_research.deterministic_survival.load_deterministic_strategy_manifest", return_value=manifest):
            report = run_baseline_alpha_survival(
                date_from="2026-04-20",
                date_to="2026-04-24",
                survival_window_days=5,
                artifacts_root=self.artifacts_root,
            )

        self.assertFalse(report["started_looking_like_alpha"])
        self.assertEqual(report["alpha_like_strategy_ids"], [])
        eth_outcomes = report["per_strategy"][ETH_STRATEGY_ID]["daily_outcomes"]
        outcome_by_date = {item["as_of"]: item["outcome"] for item in eth_outcomes}
        self.assertEqual(outcome_by_date["2026-04-22"], SURVIVAL_OUTCOME_MISSING)
        self.assertIn("2026-04-22", report["per_strategy"][ETH_STRATEGY_ID]["breaker_dates"])
        self.assertEqual(report["per_strategy"][ETH_STRATEGY_ID]["max_consecutive_survival_streak"], 2)

    def _strategy_manifest(self) -> dict[str, object]:
        return {
            "path": str(self.temp_dir / "deterministic_strategy_manifest.json"),
            "contract_version": "quant_deterministic_strategy_manifest.v1",
            "selection_policy": "checked_in_manifest_order_enabled_only",
            "entries": [
                {
                    "strategy_id": ETH_STRATEGY_ID,
                    "enabled": True,
                    "shape": "single_asset",
                    "subject": "ETH",
                    "spec_hash": "eth-spec",
                },
                {
                    "strategy_id": BTC_STRATEGY_ID,
                    "enabled": True,
                    "shape": "single_asset",
                    "subject": "BTC",
                    "spec_hash": "btc-spec",
                },
                {
                    "strategy_id": CROSS_SECTIONAL_STRATEGY_ID,
                    "enabled": True,
                    "shape": "cross_sectional",
                    "subject": None,
                    "spec_hash": "cross-spec",
                },
            ],
        }

    def _producer_summary(self, as_of: str) -> dict[str, object]:
        return {
            "quant_input_path": str(self.quant_input_root / f"pit-liquidity-top100-{as_of}.quant_universe.json"),
            "quant_universe_input_producer_summary_path": str(self.artifacts_root / "cycles" / as_of / "quant_universe_input_producer_summary.json"),
        }

    def _freeze_summary(self, as_of: str) -> dict[str, object]:
        return {
            "universe_snapshot_path": str(self.artifacts_root / "universe" / as_of / "universe_snapshot.json"),
            "universe_freeze_summary_path": str(self.artifacts_root / "cycles" / as_of / "universe_freeze_summary.json"),
        }

    def _write_experiment(
        self,
        *,
        as_of: str,
        strategy_id: str,
        subject: str,
        outcome: str,
        hashed_directory: bool = False,
    ) -> None:
        experiment_id = f"{as_of}-{strategy_id}"
        experiment_directory = experiment_id
        if hashed_directory and len(experiment_id) > 64:
            digest = hashlib.sha1(experiment_id.encode("utf-8")).hexdigest()[:12]
            experiment_directory = f"{experiment_id[:40].rstrip('-')}-{digest}"
        experiment_root = self.artifacts_root / "experiments" / experiment_directory
        experiment_root.mkdir(parents=True, exist_ok=True)
        if outcome == SURVIVAL_OUTCOME_SURVIVED:
            alpha_card = {
                "experiment_id": experiment_id,
                "strategy_id": strategy_id,
                "subject": subject,
                "experiment_status": "pass",
                "validation": "passed",
                "publication_status": "archived_only",
                "credible_research_evidence": True,
                "falsification_status": "not_required",
                "falsification_blocker_codes": [],
                "execution_stress": {"passed": True},
                "regime_holdout": {"passed": True},
                "data_gap_blockers": [],
            }
            validation_report = {
                "strategy_id": strategy_id,
                "validation_contract": {"status": "passed", "blockers": []},
                "credible_research_evidence": True,
                "execution_stress": {"passed": True},
                "regime_holdout": {"passed": True},
                "data_gap_blockers": [],
            }
        else:
            alpha_card = {
                "experiment_id": experiment_id,
                "strategy_id": strategy_id,
                "subject": subject,
                "experiment_status": "invalidated",
                "validation": "failed",
                "publication_status": "archived_only",
                "credible_research_evidence": False,
                "falsification_status": "not_required",
                "falsification_blocker_codes": [],
                "execution_stress": {"passed": False},
                "regime_holdout": {"passed": False},
                "data_gap_blockers": ["BTC: missing perp_close for execution path"],
            }
            validation_report = {
                "strategy_id": strategy_id,
                "validation_contract": {
                    "status": "incomplete",
                    "blockers": [{"code": "execution_cost_model_data_gap"}],
                },
                "credible_research_evidence": False,
                "execution_stress": {"passed": False},
                "regime_holdout": {"passed": False},
                "data_gap_blockers": ["BTC: missing perp_close for execution path"],
            }
        write_json(experiment_root / "alpha_card.json", alpha_card)
        write_json(experiment_root / "validation_report.json", validation_report)

    def _write_daily_sample(self, *, as_of: str, strategy_samples: list[dict[str, object]]) -> None:
        cycle_root = self.artifacts_root / "cycles" / as_of
        cycle_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "contract_version": DAILY_SAMPLE_CONTRACT_VERSION,
            "strategy_manifest_path": str(self.temp_dir / "deterministic_strategy_manifest.json"),
            "strategy_manifest_contract_version": "quant_deterministic_strategy_manifest.v1",
            "eligible_strategy_ids": [ETH_STRATEGY_ID, BTC_STRATEGY_ID],
            "eligible_strategy_spec_hashes": {
                ETH_STRATEGY_ID: "eth-spec",
                BTC_STRATEGY_ID: "btc-spec",
            },
            "strategy_samples": strategy_samples,
        }
        write_json(cycle_root / "deterministic_daily_sample.json", payload)

    def _strategy_sample(
        self,
        *,
        strategy_id: str,
        subject: str,
        outcome: str,
        spec_hash: str,
    ) -> dict[str, object]:
        return {
            "strategy_id": strategy_id,
            "subject": subject,
            "spec_hash": spec_hash,
            "outcome": outcome,
            "reason": "test-fixture",
            "experiment_id": f"exp-{strategy_id}",
            "blocker_codes": [] if outcome == SURVIVAL_OUTCOME_SURVIVED else ["fixture_blocker"],
            "validation_contract_status": "passed" if outcome == SURVIVAL_OUTCOME_SURVIVED else "failed",
            "credible_research_evidence": outcome == SURVIVAL_OUTCOME_SURVIVED,
            "falsification_status": "not_required",
            "execution_stress_passed": outcome == SURVIVAL_OUTCOME_SURVIVED,
            "regime_holdout_passed": outcome == SURVIVAL_OUTCOME_SURVIVED,
        }


if __name__ == "__main__":
    unittest.main()
