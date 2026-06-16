from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.bridge import export_passed_alphas_to_workbench
from enhengclaw.quant_research.bridge_contracts import verify_bridge_summary_contract
from enhengclaw.quant_research.alpha_manifest import build_daily_alpha_manifest_entry, write_daily_alpha_manifest
from enhengclaw.quant_research.contracts import (
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
    read_json,
    resolve_portable_path,
    utc_now,
    write_json,
)
from enhengclaw.quant_research.features import evaluate_no_future_leakage
from enhengclaw.quant_research.feature_admission import build_feature_admission_policy
from enhengclaw.quant_research.governance import build_strategy_entry, load_strategy_library, save_strategy_library
from enhengclaw.quant_research.leakage_audit import write_pending_leakage_audit
from enhengclaw.quant_research.legacy_surface import (
    LEGACY_QUANT_SURFACE_ERROR_CODE,
    LegacyQuantSurfaceFrozenError,
)
from enhengclaw.quant_research.promotion import (
    evaluate_quant_publication_assessment,
    write_promotion_decision,
)
from enhengclaw.quant_research.split_realization_contract import build_split_realization_contract
from enhengclaw.quant_research.validation_contract import (
    VALIDATION_CONTRACT_VERSION,
    build_execution_stress_section,
    build_regime_holdout_section,
    build_split_integrity_section,
    build_walk_forward_assessment,
    evaluate_validation_contract,
    load_validation_contract,
)
from enhengclaw.quant_research.governance import STRATEGY_LIBRARY_VERSION, THESIS_TASK_LIBRARY_MODE


class QuantResearchIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-integrity-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.strategy_library_path = self.artifacts_root / "governance" / "strategy_library.json"
        self.experiments_root = self.artifacts_root / "experiments"
        self.universe_snapshots_root = self.artifacts_root / "universe_snapshots"
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        self.experiments_root.mkdir(parents=True, exist_ok=True)
        self.universe_snapshots_root.mkdir(parents=True, exist_ok=True)
        self.universe_snapshot_path = self.universe_snapshots_root / "2026-04-20.pit_liquidity_universe_snapshot.json"
        self.universe_selection_policy_hash = "test-pit-liquidity-policy-hash"
        write_json(
            self.universe_snapshot_path,
            {
                "generated_at_utc": utc_now(),
                "as_of": "2026-04-20",
                "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
                "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
                "selection_policy_hash": self.universe_selection_policy_hash,
                "selected_candidates": [
                    {
                        "subject": "ETH",
                        "selection_rank": 2,
                        "liquidity_bucket": "top_liquidity",
                    }
                ],
            },
        )
        source_commit_patcher = mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def _assert_bridge_export_frozen(self, *, as_of: str = "2026-04-20") -> LegacyQuantSurfaceFrozenError:
        with self.assertRaises(LegacyQuantSurfaceFrozenError) as raised:
            export_passed_alphas_to_workbench(
                as_of=as_of,
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
            )
        exc = raised.exception
        self.assertEqual(exc.operation, "bridge_export")
        self.assertEqual(exc.as_of, as_of)
        self.assertEqual(exc.artifacts_root, str(self.artifacts_root.resolve()))
        self.assertEqual(exc.workbench_root, str(self.workbench_root.resolve()))
        self.assertIn(LEGACY_QUANT_SURFACE_ERROR_CODE, str(exc))
        return exc

    def _assert_promotion_write_frozen(
        self,
        *,
        alpha_card_path: Path,
        alpha_card: dict[str, object],
        strategy_entry: dict[str, object],
        decision_run_id: str,
        as_of: str = "2026-04-20",
    ) -> LegacyQuantSurfaceFrozenError:
        with self.assertRaises(LegacyQuantSurfaceFrozenError) as raised:
            write_promotion_decision(
                artifacts_root=self.artifacts_root,
                as_of=as_of,
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                strategy_entry=strategy_entry,
                strategy_library_path=self.strategy_library_path,
                decision_run_id=decision_run_id,
            )
        exc = raised.exception
        self.assertEqual(exc.operation, "promotion_decision_write")
        self.assertEqual(exc.as_of, as_of)
        self.assertEqual(exc.artifacts_root, str(self.artifacts_root.resolve()))
        self.assertIsNone(exc.workbench_root)
        self.assertIn(LEGACY_QUANT_SURFACE_ERROR_CODE, str(exc))
        return exc

    def test_bridge_export_is_frozen_for_hand_toggled_candidate(self) -> None:
        candidate_entry = build_strategy_entry(
            strategy_id="proposal-eth-balanced-logistic-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override={"max_gross_leverage": 1.2},
            source="proposal",
            status="candidate",
        )
        self._save_library([candidate_entry])
        self._write_alpha_card(
            experiment_id="tampered-candidate-alpha",
            strategy_entry=candidate_entry,
            governance_status="active",
        )

        self._assert_bridge_export_frozen()

    def test_bridge_export_is_frozen_before_daily_alpha_manifest_load(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        self._write_alpha_card(
            experiment_id="manifest-missing-alpha",
            strategy_entry=active_entry,
            governance_status="active",
            include_in_manifest=False,
        )

        self._assert_bridge_export_frozen()

    def test_bridge_export_is_frozen_before_legacy_manifest_filtering(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="canonical-alpha",
            strategy_entry=active_entry,
            governance_status="active",
        )
        legacy_root = self.experiments_root / "2026-04-20-single_asset-logistic_regression-balanced-eth"
        legacy_root.mkdir(parents=True, exist_ok=True)
        write_json(
            legacy_root / "alpha_card.json",
            {
                "generated_at_utc": utc_now(),
                "experiment_id": "2026-04-20-single_asset-logistic_regression-balanced-eth",
                "as_of": "2026-04-20",
                "shape": "single_asset",
                "model_family": "logistic_regression",
                "strategy_profile": "balanced",
                "subject": "ETH",
                "compiler_backend": "deterministic",
                "experiment_status": "pass",
                "dataset_provenance": "live_ohlcv_dataset",
            },
        )

        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            decision_run_id="2026-04-20:canonical-alpha",
        )
        self._assert_bridge_export_frozen()

    def test_bridge_export_is_frozen_before_manifest_validation(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        self._write_alpha_card(
            experiment_id="broken-manifest-alpha",
            strategy_entry=active_entry,
            governance_status="active",
            include_in_manifest=False,
        )
        write_json(
            self.artifacts_root / "governance" / "daily_alpha_manifests" / "2026-04-20.json",
            {
                "contract_version": "quant_daily_alpha_manifest.v1",
                "generated_at_utc": utc_now(),
                "as_of": "2026-04-20",
                "entry_count": 1,
                "entries": [
                    {
                        "experiment_id": "broken-manifest-alpha",
                        "alpha_card_path": "artifacts/quant_research/experiments/broken-manifest-alpha/alpha_card.json",
                        "strategy_id": "",
                        "backend_mode": "deterministic",
                        "dataset_provenance": "live_ohlcv_dataset",
                        "as_of": "2026-04-20",
                    }
                ],
            },
        )

        self._assert_bridge_export_frozen()

    def test_promotion_decision_write_is_frozen_before_hash_eligibility(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="active-alpha",
            strategy_entry=active_entry,
            governance_status="active",
        )

        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            decision_run_id="2026-04-20:active-alpha",
        )

    def test_promotion_decision_write_is_frozen_before_freshness_eligibility(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stale-alpha",
            strategy_entry=active_entry,
            governance_status="active",
        )

        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            decision_run_id="2026-04-20:stale-alpha",
        )

    def test_promotion_decision_write_is_frozen_before_commit_eligibility(self) -> None:
        active_entry = self._active_strategy_entry()
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="commit-alpha",
            strategy_entry=active_entry,
            governance_status="active",
        )

        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            decision_run_id="2026-04-20:commit-alpha",
        )

    def test_stage_1_deterministic_bridge_archives_only_and_uses_truthful_wording(self) -> None:
        active_entry = self._active_strategy_entry(daily_pass_streak=7, last_transition_reason="watch_recovered")
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage1-deterministic-alpha",
            strategy_entry=active_entry,
            governance_status="active",
            compiler_backend="deterministic",
        )

        assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            artifacts_root=self.artifacts_root,
        )

        self.assertEqual(assessment["publication_status"], "archived_only")
        self.assertIn("backend_mode=deterministic is archive-only", assessment["quality_blockers"])
        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=active_entry,
            decision_run_id="2026-04-20:stage1-deterministic-alpha",
        )
        self._assert_bridge_export_frozen()

    def test_stage_2_live_alpha_write_and_bridge_are_frozen_even_when_quality_gates_pass(self) -> None:
        active_entry = self._active_strategy_entry(daily_pass_streak=5, last_transition_reason="watch_recovered")
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage2-live-alpha",
            strategy_entry=active_entry,
            governance_status="active",
            compiler_backend="live",
            validation_sharpe=1.1,
            test_sharpe=1.2,
            max_drawdown=0.1,
            walk_forward_window_count=12,
            walk_forward_median_oos_sharpe=1.0,
        )

        with mock.patch("enhengclaw.quant_research.promotion.current_project_stage", return_value="stage_2_manual_export_human_review"):
            assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                artifacts_root=self.artifacts_root,
            )
            self.assertEqual(assessment["publication_status"], "archived_only")
            self.assertIn("credible_research_evidence=false", assessment["quality_blockers"])
            self._assert_promotion_write_frozen(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                decision_run_id="2026-04-20:stage2-live-alpha",
            )
            self._assert_bridge_export_frozen()

    def test_stage_1_live_agent_candidate_write_and_bridge_are_frozen(self) -> None:
        agent_entry = build_strategy_entry(
            strategy_id="proposal-eth-agent-tree-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override={"max_gross_leverage": 1.0},
            source="proposal",
            status="candidate",
            proposal_origin="agent",
            search_action="parameter_tune",
            auto_bridge_requested=True,
            family_id="logistic_regression",
        )
        agent_entry["last_transition_reason"] = "weekly_promoted_to_candidate"
        self._save_library([agent_entry])
        agent_entry["proposal_origin"] = "agent"
        agent_entry["auto_bridge_requested"] = True
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage1-live-agent-auto-bridge",
            strategy_entry=agent_entry,
            governance_status="candidate",
            compiler_backend="live",
            validation_sharpe=1.2,
            test_sharpe=1.4,
            max_drawdown=0.1,
            walk_forward_window_count=12,
            walk_forward_median_oos_sharpe=1.0,
        )

        assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=agent_entry,
            artifacts_root=self.artifacts_root,
        )
        self.assertEqual(assessment["publication_status"], "archived_only")
        self.assertIn("credible_research_evidence=false", assessment["quality_blockers"])
        self._assert_promotion_write_frozen(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=agent_entry,
            decision_run_id="2026-04-20:stage1-live-agent-auto-bridge",
        )
        self._assert_bridge_export_frozen()

    def test_live_alpha_with_insufficient_track_record_stays_archived_only(self) -> None:
        active_entry = self._active_strategy_entry(daily_pass_streak=1, last_transition_reason="watch_recovered")
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage2-live-insufficient-track-record",
            strategy_entry=active_entry,
            governance_status="active",
            compiler_backend="live",
            validation_sharpe=1.0,
            test_sharpe=1.1,
            max_drawdown=0.1,
            walk_forward_window_count=12,
            walk_forward_median_oos_sharpe=1.0,
        )

        with mock.patch("enhengclaw.quant_research.promotion.current_project_stage", return_value="stage_2_manual_export_human_review"):
            assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                artifacts_root=self.artifacts_root,
            )
            self.assertEqual(assessment["publication_status"], "archived_only")
            self.assertEqual(assessment["validation"], "insufficient_track_record")
            self._assert_promotion_write_frozen(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                decision_run_id="2026-04-20:stage2-live-insufficient-track-record",
            )
            self._assert_bridge_export_frozen()

    def test_live_alpha_with_sharpe_anomaly_is_archive_only_under_frozen_surface(self) -> None:
        active_entry = self._active_strategy_entry(daily_pass_streak=25, last_transition_reason="watch_recovered")
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage2-live-sharpe-anomaly",
            strategy_entry=active_entry,
            governance_status="active",
            compiler_backend="live",
            validation_sharpe=6.2,
            test_sharpe=6.4,
            max_drawdown=0.1,
            walk_forward_window_count=12,
            walk_forward_median_oos_sharpe=1.1,
        )

        with mock.patch("enhengclaw.quant_research.promotion.current_project_stage", return_value="stage_2_manual_export_human_review"):
            assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                artifacts_root=self.artifacts_root,
            )
            self.assertEqual(assessment["publication_status"], "archived_only")
            self.assertIn(
                "credible_research_evidence=false",
                assessment["quality_blockers"],
            )
            self._assert_promotion_write_frozen(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                decision_run_id="2026-04-20:stage2-live-sharpe-anomaly",
            )
            self._assert_bridge_export_frozen()
    def test_live_alpha_with_too_many_losing_walk_forward_windows_is_archive_only_under_frozen_surface(self) -> None:
        active_entry = self._active_strategy_entry(daily_pass_streak=25, last_transition_reason="watch_recovered")
        self._save_library([active_entry])
        alpha_card_path, alpha_card = self._write_alpha_card(
            experiment_id="stage2-live-loss-window-fraction",
            strategy_entry=active_entry,
            governance_status="active",
            compiler_backend="live",
            validation_sharpe=1.2,
            test_sharpe=1.1,
            max_drawdown=0.1,
            walk_forward_window_count=10,
            walk_forward_median_oos_sharpe=0.9,
            walk_forward_windows=[
                {"sharpe": 1.4},
                {"sharpe": 1.2},
                {"sharpe": 1.0},
                {"sharpe": 0.8},
                {"sharpe": 0.7},
                {"sharpe": 0.6},
                {"sharpe": -0.1},
                {"sharpe": -0.2},
                {"sharpe": -0.3},
                {"sharpe": -0.4},
            ],
        )

        with mock.patch("enhengclaw.quant_research.promotion.current_project_stage", return_value="stage_2_manual_export_human_review"):
            assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                artifacts_root=self.artifacts_root,
            )
            self.assertEqual(assessment["publication_status"], "archived_only")
            self.assertIn(
                "credible_research_evidence=false",
                assessment["quality_blockers"],
            )
            self._assert_promotion_write_frozen(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                strategy_entry=active_entry,
                decision_run_id="2026-04-20:stage2-live-loss-window-fraction",
            )
            self._assert_bridge_export_frozen()

    def test_checked_in_bridge_summary_agrees_with_current_contract(self) -> None:
        summary_path = ROOT / "artifacts" / "quant_research" / "bridge_exports" / "2026-04-20" / "bridge_summary.json"
        blockers = verify_bridge_summary_contract(
            summary_path=summary_path,
            artifacts_root=ROOT / "artifacts" / "quant_research",
            now_utc="2026-04-21T00:00:00Z",
        )
        self.assertIn("bridge summary source_commit_sha must be non-empty", blockers)
        summary = read_json(summary_path)
        self.assertFalse(str(summary["artifacts_root"]).startswith("C:\\"))
        self.assertFalse(str(summary["export_root"]).startswith("C:\\"))
        self.assertFalse(str(summary["queue_root"]).startswith("C:\\"))
        for collection_name in ("exports", "suppressed_exports", "blocked_exports"):
            for entry in summary.get(collection_name, []):
                self.assertTrue(str(entry.get("experiment_id") or "").startswith("2026-04-20-baseline-"))
        for entry in summary.get("suppressed_exports", []):
            archive_path = resolve_portable_path(str(entry["archive_path"]), repo_root=ROOT)
            self.assertTrue(archive_path.exists())

    def test_no_future_leakage_passes_for_strictly_ordered_splits(self) -> None:
        train_df = pd.DataFrame({"timestamp_ms": [1, 2, 3]})
        validation_df = pd.DataFrame({"timestamp_ms": [4, 5]})
        test_df = pd.DataFrame({"timestamp_ms": [6, 7]})

        result = evaluate_no_future_leakage(
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["blockers"], [])

    def test_no_future_leakage_fails_for_overlap(self) -> None:
        train_df = pd.DataFrame({"timestamp_ms": [1, 2, 4]})
        validation_df = pd.DataFrame({"timestamp_ms": [4, 5]})
        test_df = pd.DataFrame({"timestamp_ms": [6, 7]})

        result = evaluate_no_future_leakage(
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
        )

        self.assertFalse(result["passed"])
        self.assertTrue(any("chronological split overlap" in blocker for blocker in result["blockers"]))

    def _active_strategy_entry(
        self,
        *,
        daily_pass_streak: int = 0,
        last_transition_reason: str = "bootstrap",
    ) -> dict[str, object]:
        entry = build_strategy_entry(
            strategy_id="thesis-eth-balanced-logistic-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_model",
            promotion_eligibility="eligible",
            thesis_family="event_drift",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile={
                "thesis_id": "event-drift-overlay",
                "thesis_family": "event_drift",
                "market_mechanism": "event conditioned overlay",
                "directional_claim": "model overlay is only allowed after factor and portfolio gates",
                "universe_rule": {"subject": "ETH"},
                "execution_venue": "perp",
                "requires_derivatives_features": True,
                "minimum_executable_history_days": 365,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["funding_zscore_20"],
                "factor_formula": "overlay(logistic_regression)",
                "intended_holding_horizon_bars": 6,
                "falsification_conditions": ["factor_evidence_failed"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        )
        entry["daily_pass_streak"] = daily_pass_streak
        entry["last_transition_reason"] = last_transition_reason
        return entry

    def _save_library(self, entries: list[dict[str, object]]) -> None:
        requested_entries = [dict(entry) for entry in entries]
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": requested_entries,
            },
        )
        canonical_entries = {
            str(entry.get("strategy_id")): entry
            for entry in load_strategy_library(artifacts_root=self.artifacts_root).get("entries", [])
            if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
        }
        merged_entries = []
        for entry in requested_entries:
            strategy_id = str(entry.get("strategy_id") or "").strip()
            merged_entries.append({**dict(canonical_entries.get(strategy_id) or {}), **dict(entry)})
        write_json(
            self.strategy_library_path,
            {
                "library_version": STRATEGY_LIBRARY_VERSION,
                "library_mode": THESIS_TASK_LIBRARY_MODE,
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": merged_entries,
            },
        )
        final_entries = {
            str(entry.get("strategy_id")): entry
            for entry in load_strategy_library(artifacts_root=self.artifacts_root).get("entries", [])
            if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
        }
        for index, entry in enumerate(list(entries)):
            strategy_id = str(entry.get("strategy_id") or "").strip()
            if strategy_id in final_entries:
                entries[index].clear()
                entries[index].update(dict(final_entries[strategy_id]))

    def _write_alpha_card(
        self,
        *,
        experiment_id: str,
        strategy_entry: dict[str, object],
        governance_status: str,
        include_in_manifest: bool = True,
        compiler_backend: str = "deterministic",
        validation_sharpe: float = 1.0,
        test_sharpe: float = 1.0,
        max_drawdown: float = 0.1,
        walk_forward_window_count: int = 12,
        walk_forward_median_oos_sharpe: float = 0.8,
        walk_forward_windows: list[dict[str, object]] | None = None,
    ) -> tuple[Path, dict[str, object]]:
        alpha_root = self.experiments_root / experiment_id
        alpha_root.mkdir(parents=True, exist_ok=True)
        alpha_card_path = alpha_root / "alpha_card.json"
        subject = str(strategy_entry.get("subject") or "ETH").upper()
        split_realization_contract = build_split_realization_contract(shape="single_asset", interval="4h")
        alpha_card = {
            "generated_at_utc": utc_now(),
            "experiment_id": experiment_id,
            "as_of": "2026-04-20",
            "shape": strategy_entry["shape"],
            "model_family": strategy_entry["model_family"],
            "strategy_profile": strategy_entry["strategy_profile"],
            "subject": subject,
            "liquidity_bucket": "top_liquidity",
            "market_symbols": {
                "spot_symbol": f"{subject}USDT",
                "usdm_symbol": f"{subject}USDT",
            },
            "compiler_backend": compiler_backend,
            "backend_mode": "live" if compiler_backend == "live" else "deterministic",
            "experiment_status": "pass",
            "dataset_provenance": "live_ohlcv_dataset",
            "lifecycle": str(strategy_entry.get("lifecycle") or governance_status),
            "strategy_id": strategy_entry["strategy_id"],
            "spec_hash": strategy_entry["spec_hash"],
            "source": strategy_entry["source"],
            "validation_metrics": {"net_return": 0.2, "sharpe": validation_sharpe, "max_drawdown": 0.1},
            "test_metrics": {
                "net_return": 0.25,
                "sharpe": test_sharpe,
                "max_drawdown": max_drawdown,
                "trade_count": 40,
                "rebalance_count": 25,
            },
            "split_realization_contract": split_realization_contract,
            "walk_forward": {
                "window_count": walk_forward_window_count,
                "median_oos_sharpe": walk_forward_median_oos_sharpe,
                "windows": self._enriched_walk_forward_windows(
                    walk_forward_windows=walk_forward_windows,
                    median_oos_sharpe=walk_forward_median_oos_sharpe,
                ),
            },
            "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
            "universe_contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
            "universe_snapshot_path": str(self.universe_snapshot_path),
            "universe_selection_policy_hash": self.universe_selection_policy_hash,
        }
        validation_contract_config = load_validation_contract()
        split_integrity = build_split_integrity_section(
            split_realization_contract=split_realization_contract,
            overlap_integrity={
                "passed": True,
                "label_horizon_bars": 6,
                "bar_interval_ms": 14_400_000,
                "purge_gap_bars": 6,
            },
            leakage_checks={"passed": True, "blockers": []},
        )
        walk_forward_assessment = build_walk_forward_assessment(
            walk_forward=dict(alpha_card["walk_forward"]),
            contract=validation_contract_config,
        )
        execution_stress = build_execution_stress_section(
            strategy_profile=str(alpha_card["strategy_profile"]),
            stress_test_metrics={
                "net_return": 0.11,
                "sharpe": max(test_sharpe - 0.1, 0.1),
                "max_drawdown": max_drawdown,
                "max_participation_rate": 0.001,
            },
            walk_forward=dict(alpha_card["walk_forward"]),
            contract=validation_contract_config,
        )
        regime_holdout = build_regime_holdout_section(
            walk_forward=dict(alpha_card["walk_forward"]),
            contract=validation_contract_config,
        )
        validation_contract = evaluate_validation_contract(
            validation_metrics=dict(alpha_card["validation_metrics"]),
            test_metrics=dict(alpha_card["test_metrics"]),
            walk_forward=dict(alpha_card["walk_forward"]),
            split_integrity=split_integrity,
            feature_admission={
                "feature_admission_policy": build_feature_admission_policy(),
                "selected_feature_columns": ["momentum_6", "basis_zscore_20"],
                "excluded_feature_columns": ["timestamp_ms"],
                "banned_proxy_columns_present": [],
                "unknown_numeric_columns_present": [],
                "selected_feature_columns_outside_manifest": [],
                "passed": True,
            },
            reproducibility={
                "source_commit_sha": "abc123",
                "dataset_fingerprint": "dataset-fingerprint",
                "feature_hash": "feature-hash",
                "dataset_manifest_path": "artifacts/quant_research/datasets/demo/dataset_manifest.json",
                "feature_manifest_path": "artifacts/quant_research/features/demo/feature_manifest.json",
                "passed": True,
            },
            factor_evidence={
                "rank_ic_mean": 0.02,
                "rank_ic_positive_rate": 0.6,
                "top_minus_bottom_return": 0.03,
                "monotonicity_passed": True,
                "decay_curve": {"intended_horizon_return": 0.03},
                "turnover": 1.0,
                "max_trade_participation_rate": 0.001,
                "max_inventory_participation_rate": 0.001,
                "regime_split_results": [
                    {"quarter": "2025-08", "top_minus_bottom_return": 0.02, "positive": True},
                    {"quarter": "2025-11", "top_minus_bottom_return": 0.02, "positive": True},
                    {"quarter": "2026-02", "top_minus_bottom_return": 0.01, "positive": True},
                    {"quarter": "2026-03", "top_minus_bottom_return": -0.005, "positive": False}
                ],
                "passed": True,
            },
            walk_forward_assessment=walk_forward_assessment,
            execution_stress=execution_stress,
            regime_holdout=regime_holdout,
            contract=validation_contract_config,
        )
        alpha_card["split_integrity"] = split_integrity
        alpha_card["walk_forward_assessment"] = walk_forward_assessment
        alpha_card["execution_stress"] = execution_stress
        alpha_card["regime_holdout"] = regime_holdout
        alpha_card["validation_contract"] = {
            "contract_version": VALIDATION_CONTRACT_VERSION,
            "status": validation_contract["status"],
            "required_sections_present": validation_contract["required_sections_present"],
            "blockers": list(validation_contract["blockers"]),
        }
        publication_assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=dict(strategy_entry),
            artifacts_root=self.artifacts_root,
        )
        alpha_card["validation"] = publication_assessment["validation"]
        alpha_card["publication_status"] = publication_assessment["publication_status"]
        alpha_card["quality_summary"] = {
            "quality_gate_passed": publication_assessment["quality_gate_passed"],
            "quality_blockers": publication_assessment["quality_blockers"],
            "metrics_snapshot": publication_assessment["metrics_snapshot"],
        }
        alpha_card_path.write_text(json.dumps(alpha_card, indent=2), encoding="utf-8")
        if alpha_card["validation"] == "leakage_audit_required":
            write_pending_leakage_audit(
                artifacts_root=self.artifacts_root,
                as_of="2026-04-20",
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
                quality_blockers=publication_assessment["quality_blockers"],
            )
            publication_assessment = evaluate_quant_publication_assessment(
                alpha_card=alpha_card,
                strategy_entry=dict(strategy_entry),
                artifacts_root=self.artifacts_root,
            )
            alpha_card["validation"] = publication_assessment["validation"]
            alpha_card["publication_status"] = publication_assessment["publication_status"]
            alpha_card["quality_summary"] = {
                "quality_gate_passed": publication_assessment["quality_gate_passed"],
                "quality_blockers": publication_assessment["quality_blockers"],
                "metrics_snapshot": publication_assessment["metrics_snapshot"],
            }
            alpha_card_path.write_text(json.dumps(alpha_card, indent=2), encoding="utf-8")
        if include_in_manifest:
            self._refresh_daily_manifest()
        return alpha_card_path, alpha_card

    def _refresh_daily_manifest(self) -> None:
        entries: list[dict[str, object]] = []
        for alpha_card_path in sorted(self.experiments_root.glob("*/alpha_card.json")):
            alpha_card = read_json(alpha_card_path)
            entry = build_daily_alpha_manifest_entry(
                alpha_card_path=alpha_card_path,
                alpha_card=alpha_card,
            )
            if entry is not None:
                entries.append(entry)
        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
            entries=entries,
        )

    def _enriched_walk_forward_windows(
        self,
        *,
        walk_forward_windows: list[dict[str, object]] | None,
        median_oos_sharpe: float,
    ) -> list[dict[str, object]]:
        base_windows = walk_forward_windows or [
            {"sharpe": median_oos_sharpe} for _ in range(12)
        ]
        anchors = [
            ("2025-08-05T00:00:00Z", "2025-08-31T23:59:59Z"),
            ("2025-09-05T00:00:00Z", "2025-09-30T23:59:59Z"),
            ("2025-10-05T00:00:00Z", "2025-10-31T23:59:59Z"),
            ("2025-11-05T00:00:00Z", "2025-11-30T23:59:59Z"),
            ("2025-12-05T00:00:00Z", "2025-12-31T23:59:59Z"),
            ("2026-01-05T00:00:00Z", "2026-01-31T23:59:59Z"),
            ("2026-02-05T00:00:00Z", "2026-02-28T23:59:59Z"),
            ("2026-03-05T00:00:00Z", "2026-03-31T23:59:59Z"),
            ("2026-04-01T00:00:00Z", "2026-04-20T23:59:59Z"),
            ("2025-08-10T00:00:00Z", "2025-08-20T23:59:59Z"),
            ("2025-11-10T00:00:00Z", "2025-11-20T23:59:59Z"),
            ("2026-02-10T00:00:00Z", "2026-02-20T23:59:59Z"),
        ]
        enriched: list[dict[str, object]] = []
        for index, window in enumerate(base_windows):
            payload = dict(window)
            start_utc, end_utc = anchors[index % len(anchors)]
            payload.setdefault("test_start_utc", start_utc)
            payload.setdefault("test_end_utc", end_utc)
            payload.setdefault("turnover", 1.0)
            payload.setdefault("trade_count", 10)
            payload.setdefault("rebalance_count", 10)
            payload.setdefault("stress_sharpe", float(payload.get("sharpe", median_oos_sharpe) or 0.0))
            payload.setdefault("max_participation_rate", 0.001)
            enriched.append(payload)
        return enriched


if __name__ == "__main__":
    unittest.main()
