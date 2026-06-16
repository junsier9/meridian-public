from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.alpha_manifest import load_daily_alpha_manifest, write_daily_alpha_manifest
from enhengclaw.quant_research.bridge_contracts import verify_bridge_summary_contract
from enhengclaw.quant_research.contracts import read_json, utc_now, write_json
from enhengclaw.quant_research.governance import build_strategy_entry, save_strategy_library
from enhengclaw.quant_research.repo_health import (
    _load_canonical_experiments,
    _read_positive_control_view,
    build_repo_health_anomaly_findings,
    classify_repo_health_finding,
    repair_quant_repo_artifacts,
    run_quant_repo_health_guard,
)


ANOMALY_ALPHA_ID = "2026-04-20-baseline-eth-aggressive-breakout-continuation-single-asset"


class QuantRepoHealthGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-repo-health-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        source_commit_patcher = mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def test_classify_repo_health_finding_routes_expected_codes(self) -> None:
        self.assertEqual(classify_repo_health_finding("bridge_summary_contract_violation"), "auto_repairable")
        self.assertEqual(classify_repo_health_finding("promotion_decision_missing"), "auto_repairable")
        self.assertEqual(classify_repo_health_finding("leakage_audit_missing"), "auto_repairable")
        self.assertEqual(classify_repo_health_finding("positive_control_summary_missing"), "auto_repairable")
        self.assertEqual(classify_repo_health_finding("positive_control_summary_drift"), "auto_repairable")
        self.assertEqual(classify_repo_health_finding("compileall_failed"), "incident_only")
        self.assertEqual(classify_repo_health_finding("single_asset_pipeline_regression"), "incident_only")
        self.assertEqual(classify_repo_health_finding("threshold_provenance_drift"), "incident_only")
        self.assertEqual(classify_repo_health_finding("reproducibility_contract_drift"), "incident_only")
        self.assertEqual(classify_repo_health_finding("validation_contract_drift"), "incident_only")
        self.assertEqual(classify_repo_health_finding("sharpe_anomaly_detected"), "quarantine_only")
        self.assertEqual(classify_repo_health_finding("positive_control_marginal"), "quarantine_only")

    def test_guard_repairs_missing_quant_artifacts_and_anomaly_evidence(self) -> None:
        source_artifacts_root = ROOT / "artifacts" / "quant_research"
        experiment_root = source_artifacts_root / "experiments" / ANOMALY_ALPHA_ID
        dataset_root = source_artifacts_root / "datasets" / "2026-04-20-single-asset-4h"
        feature_root = source_artifacts_root / "features" / "2026-04-20-single-asset-4h-features-v1"
        if not experiment_root.exists() or not dataset_root.exists() or not feature_root.exists():
            self.skipTest("checked-in anomaly fixture is not present in this workspace")

        shutil.copytree(experiment_root, self.artifacts_root / "experiments" / ANOMALY_ALPHA_ID)
        shutil.copytree(dataset_root, self.artifacts_root / "datasets" / "2026-04-20-single-asset-4h")
        shutil.copytree(feature_root, self.artifacts_root / "features" / "2026-04-20-single-asset-4h-features-v1")
        self._upgrade_experiment_to_validation_contract_v2(self.artifacts_root / "experiments" / ANOMALY_ALPHA_ID)

        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [
                    build_strategy_entry(
                        strategy_id="baseline-eth-aggressive-breakout-continuation-single-asset",
                        shape="single_asset",
                        strategy_profile="aggressive",
                        subject="ETH",
                        universe_filter=None,
                        model_family="breakout_continuation",
                        feature_groups=["core_context", "trend", "derivatives"],
                        profile_constraints_override=None,
                        source="baseline",
                        status="active",
                    )
                ],
            },
        )

        def _fake_write_sharpe_anomaly_postmortem(**kwargs: object) -> dict[str, str]:
            alpha_id = str(kwargs["alpha_id"])
            evidence_path = self.artifacts_root / "assessments" / "sharpe_anomaly" / alpha_id / "postmortem_evidence.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(json.dumps({"alpha_id": alpha_id}, indent=2), encoding="utf-8")
            return {"postmortem_evidence_path": str(evidence_path)}

        with mock.patch(
            "enhengclaw.quant_research.repo_health._scan_positive_control_summary",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.write_sharpe_anomaly_postmortem",
            side_effect=_fake_write_sharpe_anomaly_postmortem,
        ):
            exit_code, summary = run_quant_repo_health_guard(
                as_of="2026-04-20",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                now_utc="2026-04-21T00:00:00Z",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["repair_status"], "repaired")
        self.assertTrue((self.artifacts_root / "governance" / "daily_alpha_manifests" / "2026-04-20.json").exists())
        self.assertTrue((self.artifacts_root / "governance" / "promotion_decisions" / "2026-04-20" / f"{ANOMALY_ALPHA_ID}.promotion_decision.json").exists())
        self.assertTrue((self.artifacts_root / "governance" / "leakage_audits" / "2026-04-20" / f"{ANOMALY_ALPHA_ID}.leakage_audit.json").exists())
        self.assertTrue((self.artifacts_root / "assessments" / "sharpe_anomaly" / ANOMALY_ALPHA_ID / "postmortem_evidence.json").exists())
        self.assertTrue((self.artifacts_root / "registry" / "alpha_registry.json").exists())
        self.assertTrue((self.artifacts_root / "cycles" / "2026-04-20" / "research_quality_summary.json").exists())
        summary_path = self.artifacts_root / "bridge_exports" / "2026-04-20" / "bridge_summary.json"
        self.assertTrue(summary_path.exists())
        self.assertEqual(
            verify_bridge_summary_contract(
                summary_path=summary_path,
                artifacts_root=self.artifacts_root,
                now_utc="2026-04-21T00:00:00Z",
            ),
            [],
        )
        repo_health_summary_path = self.artifacts_root / "ops" / "repo_health" / "2026-04-20" / "repo_health_summary.json"
        self.assertTrue(repo_health_summary_path.exists())
        repo_health_summary = read_json(repo_health_summary_path)
        self.assertTrue(any(item.get("code") == "sharpe_anomaly_detected" for item in repo_health_summary["findings"]))
        self.assertIn("positive_control_pipeline_health", repo_health_summary)
        self.assertIn("single_asset_strong_oracle_all_raw_positive", repo_health_summary)

    def test_repair_quant_repo_artifacts_rebuilds_positive_control_summary(self) -> None:
        positive_control_root = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-20"

        def _fake_write_positive_control_summary(**_: object) -> dict[str, str]:
            positive_control_root.mkdir(parents=True, exist_ok=True)
            json_path = positive_control_root / "positive_control_summary.json"
            markdown_path = positive_control_root / "positive_control_summary.md"
            json_path.write_text(
                json.dumps(
                    {
                        "contract_version": "quant_positive_control_summary.v1",
                        "evidence_family": "quant_positive_controls",
                        "as_of": "2026-04-20",
                        "dataset_ids": {},
                        "feature_set_ids": {},
                        "benchmark_constraints_profile": "balanced",
                        "subject_count_by_shape": {"single_asset": 1, "cross_sectional": 1},
                        "control_cases": [],
                        "pipeline_health": "healthy",
                        "pipeline_health_rationale": "all strong oracle controls passed and 2/2 weak oracle controls remained raw_positive",
                        "lane_interpretation": {},
                        "real_lane_reference": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            markdown_path.write_text("# Positive Control Summary\n", encoding="utf-8")
            return {
                "positive_control_summary_path": "artifacts/quant_research/assessments/positive_controls/2026-04-20/positive_control_summary.json",
                "positive_control_markdown_path": "artifacts/quant_research/assessments/positive_controls/2026-04-20/positive_control_summary.md",
            }

        with mock.patch(
            "enhengclaw.quant_research.repo_health._load_canonical_experiments",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.load_strategy_library",
            return_value={"entries": [], "path": str(self.artifacts_root / "governance" / "strategy_library.json")},
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.write_positive_control_summary",
            side_effect=_fake_write_positive_control_summary,
        ) as write_mock:
            repairs, repaired_paths = repair_quant_repo_artifacts(
                as_of="2026-04-20",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                findings=[
                    {
                        "code": "positive_control_summary_missing",
                        "scope": "positive_controls:2026-04-20",
                        "classification": "auto_repairable",
                        "blocking": True,
                    }
                ],
                now_utc="2026-04-21T00:00:00Z",
            )

        write_mock.assert_called_once()
        self.assertIn("rebuild_positive_control_summary", repairs)
        self.assertIn(
            "artifacts/quant_research/assessments/positive_controls/2026-04-20/positive_control_summary.json",
            repaired_paths,
        )
        self.assertIn(
            "artifacts/quant_research/assessments/positive_controls/2026-04-20/positive_control_summary.md",
            repaired_paths,
        )

    def test_repair_quant_repo_artifacts_rebuilds_positive_controls_after_manifest_and_promotion(self) -> None:
        call_order: list[str] = []

        def _fake_write_manifest(**_: object) -> dict[str, str]:
            call_order.append("manifest")
            path = self.artifacts_root / "governance" / "daily_alpha_manifests" / "2026-04-22.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            return {"path": str(path)}

        def _fake_write_decisions(**_: object) -> list[dict[str, str]]:
            call_order.append("promotion")
            return []

        def _fake_write_positive_controls(**_: object) -> dict[str, str]:
            call_order.append("positive_controls")
            root = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-22"
            root.mkdir(parents=True, exist_ok=True)
            json_path = root / "positive_control_summary.json"
            md_path = root / "positive_control_summary.md"
            json_path.write_text("{}", encoding="utf-8")
            md_path.write_text("# summary\n", encoding="utf-8")
            return {
                "positive_control_summary_path": str(json_path),
                "positive_control_markdown_path": str(md_path),
            }

        with mock.patch(
            "enhengclaw.quant_research.repo_health._load_canonical_experiments",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.write_daily_alpha_manifest_from_artifacts",
            side_effect=_fake_write_manifest,
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.load_strategy_library",
            return_value={"entries": [], "path": str(self.artifacts_root / "governance" / "strategy_library.json")},
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.write_promotion_decisions_for_manifest",
            side_effect=_fake_write_decisions,
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.write_positive_control_summary",
            side_effect=_fake_write_positive_controls,
        ):
            repair_quant_repo_artifacts(
                as_of="2026-04-22",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                findings=[
                    {"code": "daily_alpha_manifest_drift"},
                    {"code": "promotion_decision_drift"},
                    {"code": "positive_control_summary_drift"},
                ],
                now_utc="2026-04-22T12:00:00Z",
            )

        self.assertEqual(call_order, ["manifest", "promotion", "positive_controls"])

    def test_build_repo_health_anomaly_findings_flags_single_asset_pipeline_regression(self) -> None:
        summary_path = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-20" / "positive_control_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "contract_version": "quant_positive_control_summary.v1",
                    "evidence_family": "quant_positive_controls",
                    "as_of": "2026-04-20",
                    "pipeline_health": "broken",
                    "pipeline_health_rationale": "strong oracle controls failed raw_positive for 2026-04-20-single-asset-eth-strong-oracle",
                    "control_cases": [
                        {
                            "control_id": "2026-04-20-single-asset-eth-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": False,
                        },
                        {
                            "control_id": "2026-04-20-cross-sectional-strong-oracle",
                            "shape": "cross_sectional",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        findings = build_repo_health_anomaly_findings(as_of="2026-04-20", artifacts_root=self.artifacts_root)

        regression = next(item for item in findings if item["code"] == "single_asset_pipeline_regression")
        self.assertTrue(regression["blocking"])
        self.assertEqual(regression["classification"], "incident_only")

    def test_build_repo_health_anomaly_findings_flags_positive_control_marginal_as_warning(self) -> None:
        summary_path = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-21" / "positive_control_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "contract_version": "quant_positive_control_summary.v1",
                    "evidence_family": "quant_positive_controls",
                    "as_of": "2026-04-21",
                    "pipeline_health": "marginal",
                    "pipeline_health_rationale": "all strong oracle controls passed but only 1/4 weak oracle controls remained raw_positive",
                    "control_cases": [
                        {
                            "control_id": "2026-04-21-single-asset-eth-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                        {
                            "control_id": "2026-04-21-cross-sectional-strong-oracle",
                            "shape": "cross_sectional",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        findings = build_repo_health_anomaly_findings(as_of="2026-04-21", artifacts_root=self.artifacts_root)

        warning = next(item for item in findings if item["code"] == "positive_control_marginal")
        self.assertFalse(warning["blocking"])
        self.assertEqual(warning["classification"], "quarantine_only")

    def test_build_repo_health_anomaly_findings_ignores_skipped_short_history_single_asset_controls(self) -> None:
        summary_path = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-22" / "positive_control_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "contract_version": "quant_positive_control_summary.v1",
                    "evidence_family": "quant_positive_controls",
                    "as_of": "2026-04-22",
                    "pipeline_health": "marginal",
                    "pipeline_health_rationale": "no strong oracle controls were eligible for execution; positive-control coverage is insufficient.",
                    "control_cases": [
                        {
                            "control_id": "2026-04-22-single-asset-night-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-night-weak-oracle",
                            "shape": "single_asset",
                            "control_kind": "weak_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-cross-sectional-strong-oracle",
                            "shape": "cross_sectional",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        findings = build_repo_health_anomaly_findings(as_of="2026-04-22", artifacts_root=self.artifacts_root)

        self.assertNotIn("single_asset_pipeline_regression", {item["code"] for item in findings})
        warning = next(item for item in findings if item["code"] == "positive_control_marginal")
        self.assertFalse(warning["blocking"])

    def test_read_positive_control_view_reports_single_asset_coverage_counts(self) -> None:
        summary_path = self.artifacts_root / "assessments" / "positive_controls" / "2026-04-22" / "positive_control_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "contract_version": "quant_positive_control_summary.v1",
                    "evidence_family": "quant_positive_controls",
                    "as_of": "2026-04-22",
                    "pipeline_health": "healthy",
                    "pipeline_health_rationale": "all strong oracle controls passed. Coverage telemetry: skipped 2 strong-oracle and 3 weak-oracle controls.",
                    "control_cases": [
                        {
                            "control_id": "2026-04-22-single-asset-eth-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-night-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-xaut-strong-oracle",
                            "shape": "single_asset",
                            "control_kind": "strong_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-eth-weak-oracle",
                            "shape": "single_asset",
                            "control_kind": "weak_oracle",
                            "status": "executed",
                            "raw_positive": True,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-night-weak-oracle",
                            "shape": "single_asset",
                            "control_kind": "weak_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-xaut-weak-oracle",
                            "shape": "single_asset",
                            "control_kind": "weak_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                        {
                            "control_id": "2026-04-22-single-asset-ena-weak-oracle",
                            "shape": "single_asset",
                            "control_kind": "weak_oracle",
                            "status": "skipped_insufficient_history",
                            "raw_positive": None,
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        view = _read_positive_control_view(artifacts_root=self.artifacts_root, as_of="2026-04-22")

        self.assertTrue(view["single_asset_strong_oracle_all_raw_positive"])
        self.assertEqual(view["single_asset_strong_oracle_executed_count"], 1)
        self.assertEqual(view["single_asset_strong_oracle_skipped_count"], 2)
        self.assertEqual(view["single_asset_weak_oracle_executed_count"], 1)
        self.assertEqual(view["single_asset_weak_oracle_skipped_count"], 3)

    def test_load_canonical_experiments_prefers_latest_duplicate_alpha_card(self) -> None:
        older_root = self.artifacts_root / "experiments" / "2026-04-22-older"
        newer_root = self.artifacts_root / "experiments" / "2026-04-22-newer"
        older_root.mkdir(parents=True, exist_ok=True)
        newer_root.mkdir(parents=True, exist_ok=True)
        older_alpha_card = {
            "as_of": "2026-04-22",
            "experiment_id": "duplicate-alpha",
            "strategy_id": "duplicate-strategy",
            "generated_at_utc": "2026-04-22T05:00:00Z",
            "experiment_status": "fail",
        }
        newer_alpha_card = {
            "as_of": "2026-04-22",
            "experiment_id": "duplicate-alpha",
            "strategy_id": "duplicate-strategy",
            "generated_at_utc": "2026-04-22T11:00:00Z",
            "experiment_status": "quarantined",
        }
        (older_root / "alpha_card.json").write_text(json.dumps(older_alpha_card, indent=2), encoding="utf-8")
        (newer_root / "alpha_card.json").write_text(json.dumps(newer_alpha_card, indent=2), encoding="utf-8")

        experiments = _load_canonical_experiments(artifacts_root=self.artifacts_root, as_of="2026-04-22")

        self.assertEqual(len(experiments), 1)
        self.assertEqual(experiments[0]["alpha_card"]["generated_at_utc"], "2026-04-22T11:00:00Z")
        self.assertTrue(str(experiments[0]["alpha_card_path"]).endswith("2026-04-22-newer\\alpha_card.json"))

    def test_daily_alpha_manifest_dedupes_duplicate_experiment_entries(self) -> None:
        older_root = self.temp_dir / "older-alpha"
        newer_root = self.temp_dir / "newer-alpha"
        older_root.mkdir(parents=True, exist_ok=True)
        newer_root.mkdir(parents=True, exist_ok=True)
        older_alpha_card = older_root / "alpha_card.json"
        newer_alpha_card = newer_root / "alpha_card.json"
        older_alpha_card.write_text(
            json.dumps({"generated_at_utc": "2026-04-22T05:00:00Z"}, indent=2),
            encoding="utf-8",
        )
        newer_alpha_card.write_text(
            json.dumps({"generated_at_utc": "2026-04-22T11:00:00Z"}, indent=2),
            encoding="utf-8",
        )

        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-22",
            entries=[
                {
                    "experiment_id": "duplicate-alpha",
                    "strategy_id": "duplicate-strategy",
                    "alpha_card_path": str(older_alpha_card),
                    "as_of": "2026-04-22",
                    "backend_mode": "deterministic",
                    "dataset_provenance": "live_ohlcv_dataset",
                },
                {
                    "experiment_id": "duplicate-alpha",
                    "strategy_id": "duplicate-strategy",
                    "alpha_card_path": str(newer_alpha_card),
                    "as_of": "2026-04-22",
                    "backend_mode": "deterministic",
                    "dataset_provenance": "live_ohlcv_dataset",
                },
            ],
        )

        manifest = load_daily_alpha_manifest(artifacts_root=self.artifacts_root, as_of="2026-04-22")

        self.assertEqual(manifest["entry_count"], 1)
        self.assertEqual(len(manifest["entries"]), 1)
        self.assertEqual(manifest["entries"][0]["alpha_card_path"], str(newer_alpha_card.resolve()))

    def test_guard_auto_repairs_missing_positive_control_summary_and_records_view(self) -> None:
        missing_finding = {
            "code": "positive_control_summary_missing",
            "scope": "positive_controls:2026-04-21",
            "message": "positive control summary is missing for as_of=2026-04-21",
            "classification": "auto_repairable",
            "blocking": True,
            "evidence_paths": [],
            "recommended_manual_action": "",
        }
        with mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_source_contracts",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_artifact_drift",
            side_effect=[[missing_finding], []],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.repair_quant_repo_artifacts",
            return_value=(
                ["rebuild_positive_control_summary"],
                ["artifacts/quant_research/assessments/positive_controls/2026-04-21/positive_control_summary.json"],
            ),
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.build_repo_health_anomaly_findings",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health._read_positive_control_view",
            return_value={
                "positive_control_pipeline_health": "healthy",
                "positive_control_rationale": "all strong oracle controls passed and 2/4 weak oracle controls remained raw_positive",
                "single_asset_strong_oracle_all_raw_positive": True,
                "cross_sectional_strong_oracle_all_raw_positive": True,
            },
        ):
            exit_code, summary = run_quant_repo_health_guard(
                as_of="2026-04-21",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                now_utc="2026-04-22T00:00:00Z",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["repair_status"], "repaired")
        self.assertEqual(summary["positive_control_pipeline_health"], "healthy")
        self.assertTrue(summary["single_asset_strong_oracle_all_raw_positive"])
        repo_health_summary = read_json(self.artifacts_root / "ops" / "repo_health" / "2026-04-21" / "repo_health_summary.json")
        self.assertEqual(repo_health_summary["positive_control_pipeline_health"], "healthy")

    def test_guard_fails_and_writes_incident_for_single_asset_pipeline_regression(self) -> None:
        regression_finding = {
            "code": "single_asset_pipeline_regression",
            "scope": "positive_controls:2026-04-21",
            "message": "single-asset positive controls regressed",
            "classification": "incident_only",
            "blocking": True,
            "evidence_paths": [
                "artifacts/quant_research/assessments/positive_controls/2026-04-21/positive_control_summary.json"
            ],
            "recommended_manual_action": "Repair the single-asset score-to-position-to-PnL path before trusting today's single-asset results.",
        }
        with mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_source_contracts",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_artifact_drift",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.build_repo_health_anomaly_findings",
            return_value=[regression_finding],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health._read_positive_control_view",
            return_value={
                "positive_control_pipeline_health": "broken",
                "positive_control_rationale": "strong oracle controls failed",
                "single_asset_strong_oracle_all_raw_positive": False,
                "cross_sectional_strong_oracle_all_raw_positive": True,
            },
        ):
            exit_code, summary = run_quant_repo_health_guard(
                as_of="2026-04-21",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                now_utc="2026-04-22T00:00:00Z",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "failed")
        incident_paths = list((self.artifacts_root / "ops" / "incidents").glob("*.json"))
        self.assertTrue(incident_paths)
        payload = read_json(incident_paths[0])
        self.assertEqual(payload["code"], "single_asset_pipeline_regression")
        self.assertTrue(payload["blocking"])

    def _upgrade_experiment_to_validation_contract_v2(self, experiment_root: Path) -> None:
        alpha_card_path = experiment_root / "alpha_card.json"
        validation_report_path = experiment_root / "validation_report.json"
        alpha_card = read_json(alpha_card_path)
        validation_report = read_json(validation_report_path)
        validation_contract = {
            "contract_version": "quant_validation_contract.v2",
            "status": "passed",
            "required_sections_present": [
                "split_integrity",
                "walk_forward_assessment",
                "execution_stress",
                "regime_holdout",
            ],
            "blocker_codes": [],
        }
        validation_report["validation_contract"] = {
            "contract_version": "quant_validation_contract.v2",
            "status": "passed",
            "required_sections_present": list(validation_contract["required_sections_present"]),
            "blockers": [],
            "summary": {},
        }
        validation_report["split_integrity"] = {
            "label_horizon_bars": 6,
            "bar_interval_ms": 14_400_000,
            "purge_gap_bars": 6,
            "overlap_integrity": {"passed": True},
            "leakage_checks": {"passed": True},
            "passed": True,
        }
        validation_report["walk_forward_assessment"] = {
            "window_count": 12,
            "median_oos_sharpe": 1.2,
            "loss_window_fraction": 0.0,
            "passed": True,
        }
        validation_report["execution_stress"] = {
            "test_metrics": {"net_return": 0.1},
            "walk_forward_median_oos_sharpe": 0.9,
            "max_participation_rate": 0.001,
            "passed": True,
        }
        validation_report["regime_holdout"] = {
            "covered_regime_count": 3,
            "positive_regime_fraction": 1.0,
            "worst_regime_median_oos_sharpe": 0.9,
            "passed": True,
        }
        alpha_card["validation_contract"] = validation_contract
        write_json(alpha_card_path, alpha_card)
        write_json(validation_report_path, validation_report)

    def test_guard_records_positive_control_marginal_as_warning_without_blocking(self) -> None:
        warning_finding = {
            "code": "positive_control_marginal",
            "scope": "positive_controls:2026-04-20",
            "message": "positive controls remain marginal",
            "classification": "quarantine_only",
            "blocking": False,
            "evidence_paths": [
                "artifacts/quant_research/assessments/positive_controls/2026-04-20/positive_control_summary.json"
            ],
            "recommended_manual_action": "Treat this as weak-oracle headroom telemetry.",
        }
        with mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_source_contracts",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_artifact_drift",
            return_value=[],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health.build_repo_health_anomaly_findings",
            return_value=[warning_finding],
        ), mock.patch(
            "enhengclaw.quant_research.repo_health._read_positive_control_view",
            return_value={
                "positive_control_pipeline_health": "marginal",
                "positive_control_rationale": "all strong oracle controls passed but only 1/4 weak oracle controls remained raw_positive",
                "single_asset_strong_oracle_all_raw_positive": True,
                "cross_sectional_strong_oracle_all_raw_positive": True,
            },
        ):
            exit_code, summary = run_quant_repo_health_guard(
                as_of="2026-04-20",
                repo_root=ROOT,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                now_utc="2026-04-22T00:00:00Z",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed")
        incident_paths = list((self.artifacts_root / "ops" / "incidents").glob("*.json"))
        self.assertTrue(incident_paths)
        payload = read_json(incident_paths[0])
        self.assertEqual(payload["code"], "positive_control_marginal")
        self.assertFalse(payload["blocking"])

    def test_guard_fails_and_writes_incident_for_source_level_blockers(self) -> None:
        blocking_finding = {
            "code": "compileall_failed",
            "scope": "src",
            "message": "compileall failed for src/",
            "classification": "incident_only",
            "blocking": True,
            "evidence_paths": ["src"],
            "recommended_manual_action": "Restore source files.",
        }
        with mock.patch(
            "enhengclaw.quant_research.repo_health.scan_repo_health_source_contracts",
            return_value=[blocking_finding],
        ):
            with mock.patch(
                "enhengclaw.quant_research.repo_health.repair_quant_repo_artifacts",
            ) as repair_mock:
                exit_code, summary = run_quant_repo_health_guard(
                    as_of="2026-04-20",
                    repo_root=ROOT,
                    artifacts_root=self.artifacts_root,
                    workbench_root=self.workbench_root,
                    now_utc="2026-04-21T00:00:00Z",
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["repair_status"], "failed")
        repair_mock.assert_not_called()
        incident_root = self.artifacts_root / "ops" / "incidents"
        incident_paths = list(incident_root.glob("*.json"))
        self.assertTrue(incident_paths)
        incident_payload = read_json(incident_paths[0])
        self.assertEqual(incident_payload["code"], "compileall_failed")
        self.assertTrue(incident_payload["blocking"])


if __name__ == "__main__":
    unittest.main()
