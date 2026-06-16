from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research import shadow_proposals
from enhengclaw.quant_research.contracts import read_json, write_json
from enhengclaw.quant_research.deterministic_core import load_deterministic_strategy_manifest
from enhengclaw.quant_research.execution_backtest import _single_asset_positions


class QuantShadowGridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-shadow-grid-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_inputs_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.quant_inputs_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        env_patcher = patch.dict(
            os.environ,
            {
                "SOURCE_COMMIT_SHA": "abc123",
                "LOCALAPPDATA": str(self.temp_dir / "localappdata"),
            },
            clear=False,
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        manifest = load_deterministic_strategy_manifest()
        self.entries_by_id = {
            str(entry["strategy_id"]): copy.deepcopy(entry)
            for entry in manifest["entries"]
        }
        self.eth_entry = copy.deepcopy(self.entries_by_id["core-eth-conservative-breakout-volatility-expansion-single-asset"])
        self.btc_entry = copy.deepcopy(self.entries_by_id["core-btc-balanced-mean-reversion-single-asset"])
        self.cross_entry = copy.deepcopy(
            next(entry for entry in manifest["entries"] if str(entry.get("shape") or "") == "cross_sectional")
        )
        self.manifest = {
            "path": "deterministic_strategy_manifest.json",
            "contract_version": "quant_deterministic_strategy_manifest.v1",
            "entries": [self.btc_entry, self.eth_entry, self.cross_entry],
        }
        self.as_of = "2026-04-24"

    def test_grid_variants_are_eth_only_and_include_incumbent_control(self) -> None:
        variants = shadow_proposals._build_eth_shadow_grid_variants(base_strategy_entry=self.eth_entry)

        self.assertEqual(len(variants), 12)
        self.assertEqual({variant["base_strategy_id"] for variant in variants}, {self.eth_entry["strategy_id"]})
        self.assertEqual(len({variant["variant_id"] for variant in variants}), 12)
        incumbent = [variant for variant in variants if variant["is_incumbent_control"]]
        self.assertEqual(len(incumbent), 1)
        self.assertEqual(incumbent[0]["parameter_patch"], shadow_proposals.ETH_SHADOW_GRID_INCUMBENT_PATCH)
        spot_long_only = next(
            variant
            for variant in variants
            if variant["parameter_patch"]["execution_venue"] == "spot"
            and variant["parameter_patch"]["positioning_mode"] == "long_only"
        )
        self.assertEqual(spot_long_only["effective_profile_constraints"]["long_only_full_size_abs_score"], 1.0)

    def test_spot_long_only_positions_scale_continuously_after_neutral_band(self) -> None:
        positions = _single_asset_positions(
            pd.Series([-0.2, 0.1, 0.3, 0.5, 0.8], dtype="float64"),
            constraints={
                "long_only": True,
                "spot_only": False,
                "execution_venue": "spot",
                "long_leverage": 1.0,
                "neutral_band_abs_score": 0.2,
                "long_only_full_size_abs_score": 0.5,
            },
        )

        self.assertEqual(
            [round(value, 6) for value in positions.tolist()],
            [0.0, 0.0, 0.333333, 1.0, 1.0],
        )

    def test_grid_daily_sample_writes_variant_artifacts_and_reuses_feature_sets(self) -> None:
        cycle_summary_path = self._write_canonical_cycle_feature_summary(as_of=self.as_of)
        baseline_experiment_id = self._write_baseline_experiment(
            strategy_entry=self.eth_entry,
            experiment_id=f"{self.as_of}-{self.eth_entry['strategy_id']}",
            subject="ETH",
            hashed_directory=True,
        )
        canonical_daily_sample = {
            "deterministic_daily_sample_path": str(self.artifacts_root / "cycles" / self.as_of / "deterministic_daily_sample.json"),
            "cycle_summary_path": str(cycle_summary_path),
            "quant_input_path": "input.json",
            "universe_snapshot_path": "snapshot.json",
            "derivatives_sync_summary_path": "derivatives.json",
            "strategy_samples": [
                {
                    "strategy_id": self.eth_entry["strategy_id"],
                    "outcome": "failed",
                    "reason": "baseline_failed",
                    "blocker_codes": ["execution_stress_failed"],
                    "experiment_id": baseline_experiment_id,
                }
            ],
        }
        seen_shapes: list[tuple[str, ...]] = []

        def _fake_eval(**kwargs):
            seen_shapes.append(tuple(sorted({item["shape"] for item in kwargs["feature_sets"]})))
            strategy = kwargs["strategies"][0]
            sandbox_root = Path(kwargs["artifacts_root"])
            experiment_id = f"{self.as_of}-{strategy['strategy_id']}"
            experiment_root = sandbox_root / "experiments" / experiment_id
            experiment_root.mkdir(parents=True, exist_ok=True)
            alpha_card = {
                "experiment_id": experiment_id,
                "strategy_id": strategy["strategy_id"],
                "subject": "ETH",
                "validation_contract": {"status": "failed"},
                "falsification_status": "cleared",
                "falsification_blocker_codes": [],
                "credible_research_evidence": True,
                "test_metrics": {"net_return": -0.1},
                "walk_forward_assessment": {"median_oos_sharpe": -0.2},
                "execution_stress": {"passed": False, "max_participation_rate": 0.02},
                "regime_holdout": {"passed": False, "positive_regime_fraction": 0.3},
            }
            validation_report = {
                "validation_contract": {"status": "failed"},
                "falsification_status": "cleared",
                "falsification_blocker_codes": [],
                "credible_research_evidence": True,
                "test_metrics": {"net_return": -0.1},
                "walk_forward_assessment": {"median_oos_sharpe": -0.2},
                "execution_stress": {"passed": False, "max_participation_rate": 0.02},
                "regime_holdout": {"passed": False, "positive_regime_fraction": 0.3},
            }
            alpha_card_path = experiment_root / "alpha_card.json"
            validation_report_path = experiment_root / "validation_report.json"
            write_json(alpha_card_path, alpha_card)
            write_json(validation_report_path, validation_report)
            return [
                {
                    "experiment_id": experiment_id,
                    "alpha_card": alpha_card,
                    "validation_report": validation_report,
                    "alpha_card_path": str(alpha_card_path),
                    "validation_report_path": str(validation_report_path),
                }
            ]

        with (
            patch("enhengclaw.quant_research.shadow_proposals.load_deterministic_strategy_manifest", return_value=self.manifest),
            patch("enhengclaw.quant_research.shadow_proposals.run_quant_deterministic_daily_sample", return_value=canonical_daily_sample),
            patch("enhengclaw.quant_research.shadow_proposals.run_quant_experiments_for_strategies", side_effect=_fake_eval),
        ):
            sample = shadow_proposals.run_eth_shadow_grid_daily_sample(
                as_of=self.as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
            )

        self.assertEqual(sample["variant_outcome_counts"]["failed"], 12)
        self.assertEqual(len(sample["variant_samples"]), 12)
        self.assertTrue(all(shapes == ("cross_sectional", "single_asset") for shapes in seen_shapes))
        self.assertFalse((self.artifacts_root / "shadow_proposals").exists())
        first_variant = sample["variant_samples"][0]
        self.assertTrue((ROOT / Path(first_variant["variant_spec_path"])).exists())
        self.assertTrue((ROOT / Path(first_variant["variant_evaluation_path"])).exists())
        self.assertTrue((ROOT / Path(first_variant["variant_vs_baseline_path"])).exists())

    def test_survival_requires_five_adjacent_survived_days(self) -> None:
        variants = shadow_proposals._build_eth_shadow_grid_variants(base_strategy_entry=self.eth_entry)
        target_variant = variants[0]
        for offset in range(5):
            as_of = f"2026-04-2{offset}"
            self._write_grid_daily_sample(
                as_of=as_of,
                variant_samples=[
                    self._variant_sample(target_variant, outcome="survived", experiment_id=f"{as_of}-exp"),
                ],
            )

        with patch("enhengclaw.quant_research.shadow_proposals.load_deterministic_strategy_manifest", return_value=self.manifest):
            report = shadow_proposals.run_eth_shadow_grid_survival(
                as_of="2026-04-24",
                artifacts_root=self.artifacts_root,
                base_strategy_ids=[self.eth_entry["strategy_id"]],
            )

        self.assertTrue(report["started_looking_like_alpha"])
        self.assertIn(target_variant["variant_id"], report["alpha_like_variant_ids"])

    def test_survival_breaks_when_a_day_is_blocked(self) -> None:
        variants = shadow_proposals._build_eth_shadow_grid_variants(base_strategy_entry=self.eth_entry)
        target_variant = variants[0]
        outcomes = ["survived", "survived", "blocked", "survived", "survived"]
        for offset, outcome in enumerate(outcomes):
            as_of = f"2026-04-2{offset}"
            self._write_grid_daily_sample(
                as_of=as_of,
                variant_samples=[
                    self._variant_sample(
                        target_variant,
                        outcome=outcome,
                        experiment_id=f"{as_of}-exp" if outcome == "survived" else None,
                    ),
                ],
            )

        with patch("enhengclaw.quant_research.shadow_proposals.load_deterministic_strategy_manifest", return_value=self.manifest):
            report = shadow_proposals.run_eth_shadow_grid_survival(
                as_of="2026-04-24",
                artifacts_root=self.artifacts_root,
                base_strategy_ids=[self.eth_entry["strategy_id"]],
            )

        self.assertFalse(report["started_looking_like_alpha"])
        self.assertEqual(
            report["per_variant"][target_variant["variant_id"]]["current_consecutive_survival_streak"],
            2,
        )

    def test_orchestrator_reruns_full_window_and_accepts_only_five_day_survivors(self) -> None:
        variants = shadow_proposals._build_eth_shadow_grid_variants(base_strategy_entry=self.eth_entry)
        target_variant = variants[0]
        written_dates: list[str] = []

        def _fake_daily_sample(*, as_of: str, **_: object):
            written_dates.append(as_of)
            sample_path = self.artifacts_root / "cycles" / as_of / "eth_shadow_grid_daily_sample.json"
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "as_of": as_of,
                "contract_version": shadow_proposals.ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION,
                "eth_shadow_grid_daily_sample_path": str(sample_path),
                "variant_samples": [
                    self._variant_sample(target_variant, outcome="survived", experiment_id=f"{as_of}-exp"),
                ],
            }
            write_json(sample_path, payload)
            return payload

        def _fake_survival(*, as_of: str, **_: object):
            report_path = self.artifacts_root / "cycles" / as_of / "eth_shadow_survival.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "as_of": as_of,
                "survival_window_days": 5,
                "eth_shadow_survival_path": str(report_path),
                "started_looking_like_alpha": True,
                "alpha_like_variant_ids": [target_variant["variant_id"]],
                "per_variant": {
                    target_variant["variant_id"]: {
                        "current_consecutive_survival_streak": 5,
                    }
                },
            }
            write_json(report_path, payload)
            return payload

        with (
            patch("enhengclaw.quant_research.shadow_proposals.load_deterministic_strategy_manifest", return_value=self.manifest),
            patch("enhengclaw.quant_research.shadow_proposals.run_eth_shadow_grid_daily_sample", side_effect=_fake_daily_sample),
            patch("enhengclaw.quant_research.shadow_proposals.run_eth_shadow_grid_survival", side_effect=_fake_survival),
        ):
            summary = shadow_proposals.run_quantagent_shadow_proposal_cycle(
                as_of=self.as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
            )

        self.assertEqual(
            written_dates,
            ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24"],
        )
        self.assertEqual(summary["accepted_candidate_count"], 1)
        candidate_list = read_json(self.artifacts_root / "shadow_candidates" / self.as_of / "shadow_candidate_list.json")
        self.assertEqual(candidate_list["accepted_candidate_count"], 1)
        self.assertEqual(candidate_list["accepted_candidates"][0]["variant_id"], target_variant["variant_id"])
        self.assertFalse((self.artifacts_root / "shadow_proposals").exists())

    def test_orchestrator_rejects_non_eth_base_strategy_id(self) -> None:
        with patch("enhengclaw.quant_research.shadow_proposals.load_deterministic_strategy_manifest", return_value=self.manifest):
            with self.assertRaises(ValueError):
                shadow_proposals.run_quantagent_shadow_proposal_cycle(
                    as_of=self.as_of,
                    artifacts_root=self.artifacts_root,
                    quant_input_root=self.quant_inputs_root,
                    workbench_root=self.workbench_root,
                    base_strategy_ids=[self.btc_entry["strategy_id"]],
                )

    def test_shadow_cycle_cli_exit_codes_follow_candidate_state(self) -> None:
        module = self._load_shadow_cli_module()

        module.run_quantagent_shadow_proposal_cycle = lambda **_: {"accepted_candidate_count": 1, "success": True}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 0)

        module.run_quantagent_shadow_proposal_cycle = lambda **_: {"accepted_candidate_count": 0, "success": True}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 2)

        module.run_quantagent_shadow_proposal_cycle = lambda **_: {"accepted_candidate_count": 0, "success": False}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 1)

    def _write_baseline_experiment(
        self,
        *,
        strategy_entry: dict[str, object],
        experiment_id: str,
        subject: str,
        hashed_directory: bool = False,
    ) -> str:
        experiment_directory = experiment_id
        if hashed_directory and len(experiment_id) > 64:
            digest = hashlib.sha1(experiment_id.encode("utf-8")).hexdigest()[:12]
            experiment_directory = f"{experiment_id[:40].rstrip('-')}-{digest}"
        experiment_root = self.artifacts_root / "experiments" / experiment_directory
        experiment_root.mkdir(parents=True, exist_ok=True)
        alpha_card = {
            "experiment_id": experiment_id,
            "strategy_id": str(strategy_entry["strategy_id"]),
            "subject": subject,
            "validation_contract": {"status": "failed"},
            "falsification_status": "cleared",
            "falsification_blocker_codes": [],
            "credible_research_evidence": True,
            "test_metrics": {"net_return": -0.25},
            "walk_forward_assessment": {"median_oos_sharpe": -0.9},
            "execution_stress": {"passed": False, "max_participation_rate": 0.02},
            "regime_holdout": {"passed": False, "positive_regime_fraction": 0.33},
        }
        validation_report = {
            "validation_contract": {"status": "failed"},
            "falsification_status": "cleared",
            "falsification_blocker_codes": [],
            "credible_research_evidence": True,
            "test_metrics": {"net_return": -0.25},
            "walk_forward_assessment": {"median_oos_sharpe": -0.9},
            "execution_stress": {"passed": False, "max_participation_rate": 0.02},
            "regime_holdout": {"passed": False, "positive_regime_fraction": 0.33},
        }
        write_json(experiment_root / "alpha_card.json", alpha_card)
        write_json(experiment_root / "validation_report.json", validation_report)
        return experiment_id

    def _write_canonical_cycle_feature_summary(self, *, as_of: str) -> Path:
        cycle_root = self.artifacts_root / "cycles" / as_of
        cycle_root.mkdir(parents=True, exist_ok=True)
        single_manifest_path = self._write_feature_fixture(as_of=as_of, shape="single_asset")
        cross_manifest_path = self._write_feature_fixture(as_of=as_of, shape="cross_sectional")
        cycle_summary_path = cycle_root / "quant_cycle_summary.json"
        write_json(
            cycle_summary_path,
            {
                "feature_manifests": [str(single_manifest_path), str(cross_manifest_path)],
            },
        )
        return cycle_summary_path

    def _write_feature_fixture(self, *, as_of: str, shape: str) -> Path:
        feature_root = self.artifacts_root / "features" / f"{as_of}-{shape}"
        feature_root.mkdir(parents=True, exist_ok=True)
        feature_frame = [
            {"timestamp": "2026-04-24T00:00:00+00:00", "subject": "ETH", "trend_strength_20": 0.2}
            if shape == "single_asset"
            else {"timestamp": "2026-04-24T00:00:00+00:00", "subject": "ETH", "relative_strength_20": 0.3}
        ]
        import gzip

        with gzip.open(feature_root / "features.csv.gz", "wt", encoding="utf-8") as handle:
            handle.write("timestamp,subject,trend_strength_20\n" if shape == "single_asset" else "timestamp,subject,relative_strength_20\n")
            handle.write("2026-04-24T00:00:00+00:00,ETH,0.2\n" if shape == "single_asset" else "2026-04-24T00:00:00+00:00,ETH,0.3\n")
        dataset_manifest_path = feature_root / "dataset_manifest.json"
        write_json(dataset_manifest_path, {"data_readiness": {"shape": shape}})
        manifest_path = feature_root / "feature_manifest.json"
        write_json(
            manifest_path,
            {
                "feature_set_id": f"{as_of}-{shape}",
                "dataset_id": f"{as_of}-{shape}",
                "shape": shape,
                "available_numeric_columns": ["trend_strength_20"] if shape == "single_asset" else ["relative_strength_20"],
                "numeric_feature_columns": ["trend_strength_20"] if shape == "single_asset" else ["relative_strength_20"],
                "excluded_numeric_columns": [],
                "feature_admission_policy": {},
                "derivatives_feature_quality": {},
                "split_realization_contract": {},
                "dataset_fingerprint": f"dataset-{shape}",
                "dataset_manifest_path": str(dataset_manifest_path),
                "feature_hash": f"feature-hash-{shape}",
                "universe_definition_id": "pit_binance_liquidity_top100",
                "universe_contract_version": "quant_universe_input.v2",
                "universe_snapshot_path": "",
                "universe_selection_policy_hash": "policy",
            },
        )
        return manifest_path

    def _write_grid_daily_sample(self, *, as_of: str, variant_samples: list[dict[str, object]]) -> None:
        path = self.artifacts_root / "cycles" / as_of / "eth_shadow_grid_daily_sample.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            path,
            {
                "as_of": as_of,
                "contract_version": shadow_proposals.ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION,
                "variant_samples": variant_samples,
            },
        )

    def _variant_sample(self, variant: dict[str, object], *, outcome: str, experiment_id: str | None) -> dict[str, object]:
        return {
            "variant_id": str(variant["variant_id"]),
            "shadow_strategy_id": str(variant["shadow_strategy_id"]),
            "base_strategy_id": str(variant["base_strategy_id"]),
            "parameter_patch": dict(variant["parameter_patch"]),
            "outcome": outcome,
            "reason": f"{outcome}_reason",
            "hard_gate_passed": outcome == "survived",
            "better_than_baseline": outcome == "survived",
            "experiment_id": experiment_id,
            "blocker_codes": [] if outcome == "survived" else [f"{outcome}_blocker"],
            "variant_vs_baseline_path": "compare.json",
        }

    def _load_shadow_cli_module(self):
        script_path = ROOT / "scripts" / "quant_research" / "run_quantagent_shadow_proposal_cycle.py"
        spec = importlib.util.spec_from_file_location("quant_shadow_grid_cli", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
