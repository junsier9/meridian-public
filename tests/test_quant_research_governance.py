from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import gzip
import io
import json
import math
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_derivatives import CSV_HEADERS as DERIVATIVE_HEADERS
from enhengclaw.agents.execution._shared import SliceCompilerTransportError, normalize_compiler_envelope
from enhengclaw.quant_research.contracts import QuantUniverseCandidate, utc_now
from enhengclaw.quant_research.discovery import build_discovery_recipes
from enhengclaw.quant_research.agent_proposals import (
    _build_compiler_stage_request,
    _build_selector_stage_request,
    _prompt_payload,
    generate_agent_weekly_proposals,
)
from enhengclaw.quant_research.governance import (
    apply_daily_governance,
    apply_weekly_proposal_result,
    build_strategy_entry,
    eligible_daily_strategies,
    ensure_strategy_library,
    load_strategy_library,
    materialize_registry_snapshot,
    model_overlay_child_strategy_id,
    save_strategy_library,
    validate_proposal_spec,
)
from enhengclaw.quant_research.lab import run_quant_research_cycle, run_quant_universe_freeze
from enhengclaw.quant_research.proposals import run_quant_strategy_proposal_cycle
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input
from scripts.market_data.binance_ohlcv import CSV_HEADERS as OHLCV_HEADERS


class QuantResearchGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-governance-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_inputs_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.ohlcv_root = self.temp_dir / "external" / "ohlcv"
        self.derivatives_root = self.temp_dir / "external" / "derivatives"
        self.quant_inputs_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        self.localappdata_root = self.temp_dir / "localappdata"
        localappdata_patcher = patch.dict(
            os.environ,
            {
                "LOCALAPPDATA": str(self.localappdata_root),
                "CoinglassAPI": "",
                "COINGLASS_API_KEY": "",
                "COINGLASSAPI": "",
                "SOURCE_COMMIT_SHA": "abc123",
            },
            clear=False,
        )
        localappdata_patcher.start()
        self.addCleanup(localappdata_patcher.stop)
        self._seed_quant_input()
        self._seed_market_history()

    def test_validate_proposal_spec_rejects_unknown_model_family(self) -> None:
        proposal = {
            "proposal_id": "bad-proposal",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": "proposal-bad",
            "shape": "single_asset",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "universe_filter": {},
            "model_family": "new_magic_model",
            "feature_groups": ["core_context", "trend"],
            "profile_constraints_override": {},
            "rationale": "Test invalid model family rejection.",
            "expected_edge": "None.",
            "invalidates_if": "Always.",
            "proposal_origin": "agent",
            "search_action": "feature_variant",
            "family_registry_patch": {},
            "feature_registry_patch": {},
            "priority_score": 0.75,
            "complexity_tier": "low",
            "risk_tags": ["regime_shift"],
            "auto_bridge_requested": False,
            "thesis_profile": {
                "thesis_id": "bad-model-family",
                "thesis_family": "event_drift",
                "market_mechanism": "test",
                "directional_claim": "test invalid family handling",
                "universe_rule": {"subject": "ETH"},
                "execution_venue": "spot",
                "requires_derivatives_features": False,
                "minimum_executable_history_days": 180,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["return_1"],
                "factor_formula": "return_1",
                "intended_holding_horizon_bars": 1,
                "falsification_conditions": ["test"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        }
        valid, reason = validate_proposal_spec(proposal_spec=proposal, artifacts_root=self.artifacts_root)
        self.assertFalse(valid)
        self.assertIn("model_family", str(reason))

    def test_validate_proposal_spec_rejects_new_model_family_registry_patch(self) -> None:
        proposal = {
            "proposal_id": "agent-new-family",
            "proposal_bucket": "feature",
            "week_of": "2026-04-27",
            "strategy_id": "agent-new-family",
            "shape": "single_asset",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "universe_filter": {},
            "model_family": "adaptive_tree_stack",
            "feature_groups": ["core_context", "trend"],
            "profile_constraints_override": {},
            "rationale": "Try a bounded tree ensemble family.",
            "expected_edge": "Improve non-linear separation without changing execution semantics.",
            "invalidates_if": "Held-out returns turn negative.",
            "proposal_origin": "agent",
            "search_action": "new_model_family",
            "family_registry_patch": {
                "families": [
                    {
                        "family_id": "adaptive_tree_stack",
                        "engine_template": "tree_ensemble",
                        "allowed_shapes": ["single_asset"],
                        "hyperparameters": {"implementation": "extra_trees", "n_estimators": 128},
                    }
                ]
            },
            "feature_registry_patch": {},
            "priority_score": 0.9,
            "complexity_tier": "medium",
            "risk_tags": ["regime_shift"],
            "auto_bridge_requested": True,
            "thesis_profile": {
                "thesis_id": "tree-overlay",
                "thesis_family": "basis_mean_reversion",
                "market_mechanism": "test",
                "directional_claim": "test",
                "universe_rule": {"subject": "ETH"},
                "execution_venue": "spot",
                "requires_derivatives_features": False,
                "minimum_executable_history_days": 180,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["return_1"],
                "factor_formula": "return_1",
                "intended_holding_horizon_bars": 1,
                "falsification_conditions": ["test"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        }
        valid, reason = validate_proposal_spec(proposal_spec=proposal, artifacts_root=self.artifacts_root)
        self.assertFalse(valid)
        self.assertIn("search_action", str(reason))

    def test_validate_proposal_spec_accepts_heuristic_model_overlay_child(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "-funding_zscore_20",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        parent_entry = build_strategy_entry(
            strategy_id="thesis-funding-extreme-reversal-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_portfolio",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        parent_entry["model_overlay_ready"] = True
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [parent_entry]},
        )
        proposal = {
            "proposal_id": "overlay-logistic",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": model_overlay_child_strategy_id(
                base_strategy_id=parent_entry["strategy_id"],
                model_family="logistic_regression",
            ),
            "shape": "cross_sectional",
            "strategy_profile": "balanced",
            "subject": None,
            "universe_filter": {"preset": "liquid_perp_core_20"},
            "model_family": "logistic_regression",
            "feature_groups": ["derivatives"],
            "profile_constraints_override": {},
            "base_strategy_id": parent_entry["strategy_id"],
            "rationale": "Apply a logistic overlay to the validated portfolio thesis.",
            "expected_edge": "Improve ranking calibration without breaking the portfolio edge.",
            "invalidates_if": "The overlay weakens validated OOS performance.",
            "proposal_origin": "heuristic",
            "search_action": "model_overlay",
            "parent_spec_hash": parent_entry["spec_hash"],
            "family_registry_patch": {},
            "feature_registry_patch": {},
            "priority_score": 0.92,
            "complexity_tier": "medium",
            "risk_tags": ["model_overlay"],
            "auto_bridge_requested": False,
            "research_lane": "hypothesis_model",
            "promotion_eligibility": "eligible",
            "thesis_family": "funding_extreme_reversal",
            "requires_derivatives_features": True,
            "daily_executable": True,
            "thesis_profile": thesis_profile,
        }
        valid, reason = validate_proposal_spec(proposal_spec=proposal, artifacts_root=self.artifacts_root)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_validate_proposal_spec_rejects_model_overlay_without_base_strategy(self) -> None:
        proposal = {
            "proposal_id": "overlay-missing-base",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": "hypothesis-model-missing-base-logistic",
            "shape": "cross_sectional",
            "strategy_profile": "balanced",
            "subject": None,
            "universe_filter": {"preset": "liquid_perp_core_20"},
            "model_family": "logistic_regression",
            "feature_groups": ["derivatives"],
            "profile_constraints_override": {},
            "rationale": "Invalid overlay without a base thesis.",
            "expected_edge": "None.",
            "invalidates_if": "Always.",
            "proposal_origin": "heuristic",
            "search_action": "model_overlay",
            "parent_spec_hash": "abc123",
            "family_registry_patch": {},
            "feature_registry_patch": {},
            "priority_score": 0.92,
            "complexity_tier": "medium",
            "risk_tags": ["model_overlay"],
            "auto_bridge_requested": False,
            "research_lane": "hypothesis_model",
            "promotion_eligibility": "eligible",
            "thesis_family": "funding_extreme_reversal",
            "requires_derivatives_features": True,
            "daily_executable": True,
            "thesis_profile": {
                "thesis_id": "funding-extreme-reversal",
                "thesis_family": "funding_extreme_reversal",
                "market_mechanism": "crowding reversal",
                "directional_claim": "fade crowding",
                "universe_rule": {"preset": "liquid_perp_core_20"},
                "execution_venue": "perp",
                "requires_derivatives_features": True,
                "minimum_executable_history_days": 365,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
                "factor_formula": "-funding_zscore_20",
                "intended_holding_horizon_bars": 1,
                "falsification_conditions": ["capacity_constraint_breach"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        }
        valid, reason = validate_proposal_spec(proposal_spec=proposal, artifacts_root=self.artifacts_root)
        self.assertFalse(valid)
        self.assertIn("base_strategy_id", str(reason))

    def test_agent_proposal_cycle_degrades_without_api(self) -> None:
        universe_candidates = (
            self._universe_candidate("ETH", 2),
        )
        strategy_library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=universe_candidates,
        )
        review_root = self.artifacts_root / "governance" / "weekly_reviews" / "2026-W18"
        registry_snapshot = materialize_registry_snapshot(
            artifacts_root=self.artifacts_root,
            week_of="2026-04-27",
        )
        with patch.dict(
            os.environ,
            {
                "OPENCLAW_AGENT_PROPOSAL_API_KEY": "",
                "OPENCLAW": "",
                "OPENAI_API_KEY": "",
            },
            clear=False,
        ):
            summary = generate_agent_weekly_proposals(
                week_of="2026-04-27",
                artifacts_root=self.artifacts_root,
                review_root=review_root,
                strategy_library=strategy_library,
                universe_candidates=universe_candidates,
                registry_snapshot=registry_snapshot,
            )
        self.assertEqual(summary["status"], "degraded_no_api")
        self.assertEqual(summary["validated_proposal_count"], 0)
        self.assertTrue(Path(summary["summary_path"]).exists())

    def test_agent_proposal_cycle_accepts_markdown_fenced_json_envelope(self) -> None:
        universe_candidates = (
            self._universe_candidate("ETH", 2),
        )
        strategy_library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=universe_candidates,
        )
        review_root = self.artifacts_root / "governance" / "weekly_reviews" / "2026-W18"
        registry_snapshot = materialize_registry_snapshot(
            artifacts_root=self.artifacts_root,
            week_of="2026-04-27",
        )
        assistant_envelope = json.dumps(
            {
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [
                    {
                        "proposals": [
                            {
                                "proposal_id": "agent-eth-balanced-logistic-fenced",
                                "proposal_bucket": "config",
                                "week_of": "2026-04-27",
                                "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                                "strategy_id": "agent-eth-balanced-logistic-fenced",
                                "shape": "single_asset",
                                "strategy_profile": "balanced",
                                "subject": "ETH",
                                "universe_filter": {},
                                "model_family": "logistic_regression",
                                "feature_groups": ["core_context", "trend"],
                                "profile_constraints_override": {"max_gross_leverage": 1.1},
                                "rationale": "Tighten leverage while preserving the existing feature family.",
                                "expected_edge": "Reduce left-tail risk without removing core directional exposure.",
                                "invalidates_if": "Validation Sharpe or net return turns negative.",
                                "proposal_origin": "agent",
                                "search_action": "feature_variant",
                                "parent_spec_hash": None,
                                "family_registry_patch": {},
                                "feature_registry_patch": {},
                                "priority_score": 0.9,
                                "complexity_tier": "low",
                                "risk_tags": ["regime_shift"],
                                "auto_bridge_requested": False,
                                "family_id": "logistic_regression",
                                "thesis_profile": self._single_asset_thesis_profile(),
                            }
                        ],
                        "notes": ["fenced payload"],
                    }
                ],
                "notes": ["outer fenced envelope"],
            }
        )
        assistant_text = f"```json\n{assistant_envelope}\n```"
        compiler_output = normalize_compiler_envelope(
            assistant_text=assistant_text,
            raw_body=json.dumps({"choices": [{"message": {"content": assistant_text}}]}),
            parse_error=None,
        )
        selector_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposal_intents": [
                    {
                        "search_action": "feature_variant",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "subject": "ETH",
                        "family_id_hint": "logistic_regression",
                        "priority_score": 0.9,
                        "complexity_tier": "low",
                        "required_patch_kind": "none",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": False,
                        "why_now": "Tighten leverage while preserving the existing feature family.",
                    }
                ],
                "notes": ["selector intent"],
            },
            stage="selector",
            prompt_tokens=80,
            completion_tokens=10,
        )
        fake_artifacts = SimpleNamespace(
            transcript_payload={"backend_kind": "openai_compatible", "backend_name": "gpt-test", "stage": "compiler"},
            compiler_output=compiler_output,
            raw_model_output={"response_json": {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}},
            model_request={"request_body_chars": 2048, "latency_ms": 250, "retry_count": 0, "fallback_without_response_format": False},
        )
        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=[selector_artifacts, fake_artifacts],
            ):
                summary = generate_agent_weekly_proposals(
                    week_of="2026-04-27",
                    artifacts_root=self.artifacts_root,
                    review_root=review_root,
                    strategy_library=strategy_library,
                    universe_candidates=universe_candidates,
                    registry_snapshot=registry_snapshot,
                )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["validated_proposal_count"], 1)
        self.assertEqual(summary["raw_proposal_count"], 1)
        self.assertIn("assistant_content_markdown_fence_stripped", summary["notes"])
        self.assertTrue(Path(summary["summary_path"]).exists())

    def test_agent_proposal_cycle_merges_selector_payloads_before_compiler(self) -> None:
        universe_candidates = (
            self._universe_candidate("ETH", 2),
        )
        strategy_library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=universe_candidates,
        )
        review_root = self.artifacts_root / "governance" / "weekly_reviews" / "2026-W18"
        registry_snapshot = materialize_registry_snapshot(
            artifacts_root=self.artifacts_root,
            week_of="2026-04-27",
        )
        selector_assistant_text = json.dumps(
            {
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [
                    {
                        "proposal_intents": [
                            {
                                "search_action": "feature_variant",
                                "base_strategy_id": "thesis-funding-extreme-reversal-cross-sectional",
                                "subject": "",
                                "family_id_hint": "carry_funding",
                                "priority_score": 0.9,
                                "complexity_tier": "low",
                                "required_patch_kind": "none",
                                "risk_tags": ["regime_shift"],
                                "auto_bridge_requested": False,
                                "why_now": "Probe a tighter feature variant on the validated funding thesis.",
                            }
                        ],
                        "notes": ["selector shard 1"],
                    },
                    {
                        "proposal_intents": [
                            {
                                "search_action": "feature_variant",
                                "base_strategy_id": "thesis-funding-extreme-reversal-cross-sectional",
                                "subject": "",
                                "family_id_hint": "carry_funding",
                                "priority_score": 0.8,
                                "complexity_tier": "medium",
                                "required_patch_kind": "none",
                                "risk_tags": ["trend_shift"],
                                "auto_bridge_requested": False,
                                "why_now": "Probe a second feature variant for the same funding thesis.",
                            }
                        ],
                        "notes": ["selector shard 2"],
                    },
                ],
                "notes": ["selector envelope"],
            }
        )
        selector_artifacts = SimpleNamespace(
            transcript_payload={"backend_kind": "openai_compatible", "backend_name": "gpt-test", "stage": "selector"},
            compiler_output={
                "status": "blocked",
                "blocked_reason": "model_must_emit_exactly_one_candidate_payload",
                "candidate_payloads": [],
                "notes": [],
            },
            raw_model_output={
                "assistant_text": selector_assistant_text,
                "response_text": selector_assistant_text,
                "response_json": {
                    "usage": {
                        "prompt_tokens": 90,
                        "completion_tokens": 18,
                        "total_tokens": 108,
                    }
                },
            },
            model_request={
                "request_body_chars": 3072,
                "latency_ms": 345,
                "retry_count": 0,
                "fallback_without_response_format": False,
            },
        )
        compiler_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposals": [
                    {
                        "proposal_id": "agent-eth-balanced-logistic-selector-merged",
                        "proposal_bucket": "config",
                        "week_of": "2026-04-27",
                        "base_strategy_id": "thesis-funding-extreme-reversal-cross-sectional",
                        "strategy_id": "agent-funding-selector-merged",
                        "shape": "cross_sectional",
                        "strategy_profile": "balanced",
                        "subject": None,
                        "universe_filter": {"preset": "liquid_perp_core_20"},
                        "model_family": "carry_funding",
                        "feature_groups": ["derivatives"],
                        "profile_constraints_override": {"max_gross_leverage": 1.05},
                        "rationale": "Selector shortlisted two opportunities and compiler chose the tighter funding-feature variant.",
                        "expected_edge": "Reduce downside while preserving the existing funding thesis signal.",
                        "invalidates_if": "Validation net return or Sharpe turns negative.",
                        "proposal_origin": "agent",
                        "search_action": "feature_variant",
                        "parent_spec_hash": None,
                        "family_registry_patch": {},
                        "feature_registry_patch": {},
                        "priority_score": 0.9,
                        "complexity_tier": "low",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": False,
                        "family_id": "logistic_regression",
                        "thesis_profile": {
                            "thesis_id": "funding-extreme-reversal",
                            "thesis_family": "funding_extreme_reversal",
                            "market_mechanism": "crowding reversal",
                            "directional_claim": "fade crowding",
                            "universe_rule": {"preset": "liquid_perp_core_20"},
                            "execution_venue": "perp",
                            "requires_derivatives_features": True,
                            "minimum_executable_history_days": 365,
                            "minimum_executable_coverage_ratio": 0.85,
                            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
                            "factor_formula": "-funding_zscore_20",
                            "intended_holding_horizon_bars": 1,
                            "falsification_conditions": ["capacity_constraint_breach"],
                            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
                        },
                    }
                ],
                "notes": ["compiler payload"],
            },
            stage="compiler",
            prompt_tokens=110,
            completion_tokens=26,
        )

        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=[selector_artifacts, compiler_artifacts],
            ):
                summary = generate_agent_weekly_proposals(
                    week_of="2026-04-27",
                    artifacts_root=self.artifacts_root,
                    review_root=review_root,
                    strategy_library=strategy_library,
                    universe_candidates=universe_candidates,
                    registry_snapshot=registry_snapshot,
                )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["selector"]["status"], "success")
        self.assertEqual(summary["selector"]["intent_count"], 2)
        self.assertEqual(summary["compiler"]["status"], "success")
        self.assertEqual(summary["validated_proposal_count"], 1)
        self.assertIn("selector_candidate_payloads_merged:2", summary["notes"])
        self.assertTrue(Path(summary["summary_path"]).exists())

    def test_agent_prompt_payload_compacts_large_registry_context(self) -> None:
        universe_candidates = tuple(
            self._universe_candidate(f"ASSET{i}", i + 1)
            for i in range(30)
        )
        strategy_library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=universe_candidates,
        )
        strategy_library["entries"] = strategy_library.get("entries", []) * 3
        alpha_registry_path = self.artifacts_root / "registry" / "alpha_registry.json"
        alpha_registry_path.parent.mkdir(parents=True, exist_ok=True)
        alpha_registry_payload = {
            "entries": [
                {
                    "strategy_id": f"alpha-{idx}",
                    "shape": "single_asset",
                    "strategy_profile": "balanced",
                    "subject": "ETH",
                    "model_family": "logistic_regression",
                    "publication_status": "archived_only",
                    "experiment_status": "pass",
                    "validation_metrics": {"net_return": 0.2, "sharpe": 1.1, "max_drawdown": 0.1},
                    "test_metrics": {"net_return": 0.1, "sharpe": 0.8, "max_drawdown": 0.15},
                    "walk_forward": {
                        "median_oos_sharpe": 0.9,
                        "window_count": 20,
                        "windows": [{"sharpe": float(step)} for step in range(20)],
                    },
                }
                for idx in range(12)
            ]
        }
        alpha_registry_path.write_text(json.dumps(alpha_registry_payload), encoding="utf-8")
        registry_snapshot = materialize_registry_snapshot(
            artifacts_root=self.artifacts_root,
            week_of="2026-04-27",
        )
        payload = _prompt_payload(
            week_of="2026-04-27",
            artifacts_root=self.artifacts_root,
            strategy_library=strategy_library,
            universe_candidates=universe_candidates,
            registry_snapshot=registry_snapshot,
        )
        self.assertLessEqual(len(payload["strategy_library_excerpt"]), 24)
        self.assertLessEqual(len(payload["recent_alpha_registry_excerpt"]), 6)
        self.assertIn("walk_forward_summary", payload["recent_alpha_registry_excerpt"][0])
        self.assertNotIn("walk_forward", payload["recent_alpha_registry_excerpt"][0])
        selector_request = _build_selector_stage_request(prompt_payload=payload, model_name="gpt-test")
        compiler_request = _build_compiler_stage_request(
            prompt_payload=payload,
            selector_intents=[
                {
                    "search_action": "parameter_tune",
                    "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                    "subject": "ETH",
                    "family_id_hint": "logistic_regression",
                    "priority_score": 0.8,
                    "complexity_tier": "low",
                    "required_patch_kind": "none",
                    "risk_tags": ["regime_shift"],
                    "auto_bridge_requested": False,
                    "why_now": "Retest the strongest baseline under a tighter config.",
                }
            ],
            model_name="gpt-test",
        )
        self.assertEqual(selector_request["budget_status"], "within_budget")
        self.assertEqual(compiler_request["budget_status"], "within_budget")
        self.assertLessEqual(selector_request["request_body_chars"], 14_000)
        self.assertLessEqual(compiler_request["request_body_chars"], 16_000)

    def test_agent_proposal_cycle_quarantines_missing_registry_patch_per_proposal(self) -> None:
        universe_candidates = (self._universe_candidate("ETH", 2),)
        strategy_library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=universe_candidates,
        )
        review_root = self.artifacts_root / "governance" / "weekly_reviews" / "2026-W18"
        registry_snapshot = materialize_registry_snapshot(
            artifacts_root=self.artifacts_root,
            week_of="2026-04-27",
        )
        selector_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposal_intents": [
                    {
                        "search_action": "new_feature_family",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "subject": "ETH",
                        "family_id_hint": "alt_sentiment",
                        "priority_score": 0.95,
                        "complexity_tier": "medium",
                        "required_patch_kind": "feature_registry_patch",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": True,
                        "why_now": "Test a new feature family on the strongest liquid subject.",
                    }
                ],
                "notes": [],
            },
            stage="selector",
            prompt_tokens=200,
            completion_tokens=30,
        )
        compiler_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposals": [
                    {
                        "proposal_id": "agent-eth-balanced-logistic-tightened",
                        "proposal_bucket": "config",
                        "week_of": "2026-04-27",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "strategy_id": "agent-eth-balanced-logistic-tightened",
                        "shape": "single_asset",
                        "strategy_profile": "balanced",
                        "subject": "ETH",
                        "universe_filter": {},
                        "model_family": "logistic_regression",
                        "feature_groups": ["core_context", "trend"],
                        "profile_constraints_override": {"max_gross_leverage": 1.1},
                        "rationale": "Tighten leverage while preserving the strongest liquid baseline.",
                        "expected_edge": "Reduce left-tail exposure without dropping directional edge.",
                        "invalidates_if": "Validation or test net return turns negative.",
                        "proposal_origin": "agent",
                        "search_action": "feature_variant",
                        "parent_spec_hash": None,
                        "family_registry_patch": {},
                        "feature_registry_patch": {},
                        "priority_score": 0.88,
                        "complexity_tier": "low",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": False,
                        "family_id": "logistic_regression",
                        "thesis_profile": self._single_asset_thesis_profile(),
                    },
                    {
                        "proposal_id": "agent-new-feature-family-missing-patch",
                        "proposal_bucket": "config",
                        "week_of": "2026-04-27",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "strategy_id": "agent-new-feature-family-missing-patch",
                        "shape": "single_asset",
                        "strategy_profile": "balanced",
                        "subject": "ETH",
                        "universe_filter": {},
                        "model_family": "logistic_regression",
                        "feature_groups": ["core_context", "trend"],
                        "profile_constraints_override": {},
                        "rationale": "Try a new feature family on the strongest liquid baseline.",
                        "expected_edge": "Capture a new observable that the current baseline misses.",
                        "invalidates_if": "Validation Sharpe turns negative.",
                        "proposal_origin": "agent",
                        "search_action": "new_feature_family",
                        "parent_spec_hash": None,
                        "family_registry_patch": {},
                        "feature_registry_patch": {},
                        "priority_score": 0.9,
                        "complexity_tier": "medium",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": True,
                        "family_id": "logistic_regression",
                        "thesis_profile": self._single_asset_thesis_profile(),
                    }
                ],
                "notes": [],
            },
            stage="compiler",
            prompt_tokens=180,
            completion_tokens=60,
        )

        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=[selector_artifacts, compiler_artifacts],
            ):
                summary = generate_agent_weekly_proposals(
                    week_of="2026-04-27",
                    artifacts_root=self.artifacts_root,
                    review_root=review_root,
                    strategy_library=strategy_library,
                    universe_candidates=universe_candidates,
                    registry_snapshot=registry_snapshot,
                )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["compiler"]["status"], "success")
        self.assertIsNone(summary["compiler"]["blocked_reason"])
        self.assertEqual(summary["compiler_extracted_proposal_count"], 2)
        self.assertEqual(summary["validated_proposal_count"], 1)
        self.assertEqual(summary["quarantined_proposal_count"], 1)
        self.assertEqual(summary["compiler_hygiene_quarantine_count"], 1)
        self.assertEqual(
            summary["quarantine_reason_counts"].get("new_feature_family proposals must include feature_registry_patch"),
            1,
        )
        self.assertTrue(Path(summary["summary_path"]).exists())

    def test_weekly_proposal_cycle_writes_stage_usage_for_agent_lane(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        selector_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposal_intents": [
                    {
                        "search_action": "feature_variant",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "subject": "ETH",
                        "family_id_hint": "logistic_regression",
                        "priority_score": 0.88,
                        "complexity_tier": "low",
                        "required_patch_kind": "none",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": False,
                        "why_now": "Retest the most stable baseline with slightly tighter leverage.",
                    }
                ],
                "notes": [],
            },
            stage="selector",
            prompt_tokens=220,
            completion_tokens=35,
        )
        compiler_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposals": [
                    {
                        "proposal_id": "agent-eth-balanced-logistic-tightened",
                        "proposal_bucket": "config",
                        "week_of": "2026-04-27",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "strategy_id": "agent-eth-balanced-logistic-tightened",
                        "shape": "single_asset",
                        "strategy_profile": "balanced",
                        "subject": "ETH",
                        "universe_filter": {},
                        "model_family": "logistic_regression",
                        "feature_groups": ["core_context", "trend"],
                        "profile_constraints_override": {"max_gross_leverage": 1.1},
                        "rationale": "Tighten leverage while preserving the best daily baseline.",
                        "expected_edge": "Reduce left-tail exposure without dropping directional edge.",
                        "invalidates_if": "Validation or test net return turns negative.",
                        "proposal_origin": "agent",
                        "search_action": "feature_variant",
                        "parent_spec_hash": None,
                        "family_registry_patch": {},
                        "feature_registry_patch": {},
                        "priority_score": 0.88,
                        "complexity_tier": "low",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": False,
                        "family_id": "logistic_regression",
                        "thesis_profile": self._single_asset_thesis_profile(),
                    }
                ],
                "notes": [],
            },
            stage="compiler",
            prompt_tokens=190,
            completion_tokens=55,
            fallback_without_response_format=True,
            retry_count=1,
        )

        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=[selector_artifacts, compiler_artifacts],
            ):
                with patch(
                    "enhengclaw.quant_research.discovery._run_same_week_auto_bridge",
                    return_value={
                        "status": "no_agent_candidates",
                        "success": True,
                        "auto_bridged_snapshot_count": 0,
                        "auto_bridged_agent_snapshot_count": 0,
                        "published_snapshot_count": 0,
                        "bridge_summary_path": None,
                    },
                ):
                    summary = run_quant_strategy_proposal_cycle(
                        week_of="2026-04-27",
                        artifacts_root=self.artifacts_root,
                        quant_input_root=self.quant_inputs_root,
                        workbench_root=self.workbench_root,
                        ohlcv_external_root=self.ohlcv_root,
                        derivatives_external_root=self.derivatives_root,
                    )

        self.assertEqual(summary["selector_usage"]["prompt_tokens"], 220)
        self.assertEqual(summary["compiler_usage"]["completion_tokens"], 55)
        self.assertEqual(summary["response_format_fallback_count"], 1)
        self.assertEqual(summary["prompt_budget_status"]["selector"], "within_budget")
        self.assertGreaterEqual(summary["proposal_lane_mix"].get("agent", 0), 1)
        self.assertEqual(summary["agent_quarantined_proposal_count"], 0)
        self.assertEqual(summary["agent_quarantine_reason_counts"], {})

    def test_weekly_proposal_cycle_falls_back_to_heuristic_when_all_agent_proposals_are_quarantined(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )
        selector_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposal_intents": [
                    {
                        "search_action": "new_feature_family",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "subject": "ETH",
                        "family_id_hint": "alt_sentiment",
                        "priority_score": 0.95,
                        "complexity_tier": "medium",
                        "required_patch_kind": "feature_registry_patch",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": True,
                        "why_now": "Test a new feature family on the strongest liquid subject.",
                    }
                ],
                "notes": [],
            },
            stage="selector",
            prompt_tokens=200,
            completion_tokens=30,
        )
        compiler_artifacts = self._fake_compile_artifacts(
            candidate_payload={
                "proposals": [
                    {
                        "proposal_id": "agent-new-feature-family-missing-patch",
                        "proposal_bucket": "config",
                        "week_of": "2026-04-27",
                        "base_strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                        "strategy_id": "agent-new-feature-family-missing-patch",
                        "shape": "single_asset",
                        "strategy_profile": "balanced",
                        "subject": "ETH",
                        "universe_filter": {},
                        "model_family": "logistic_regression",
                        "feature_groups": ["core_context", "trend"],
                        "profile_constraints_override": {},
                        "rationale": "Try a new feature family on the strongest liquid baseline.",
                        "expected_edge": "Capture a new observable that the current baseline misses.",
                        "invalidates_if": "Validation Sharpe turns negative.",
                        "proposal_origin": "agent",
                        "search_action": "new_feature_family",
                        "parent_spec_hash": None,
                        "family_registry_patch": {},
                        "feature_registry_patch": {},
                        "priority_score": 0.9,
                        "complexity_tier": "medium",
                        "risk_tags": ["regime_shift"],
                        "auto_bridge_requested": True,
                        "family_id": "logistic_regression",
                        "thesis_profile": self._single_asset_thesis_profile(),
                    }
                ],
                "notes": [],
            },
            stage="compiler",
            prompt_tokens=180,
            completion_tokens=60,
        )

        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=[selector_artifacts, compiler_artifacts],
            ):
                summary = run_quant_strategy_proposal_cycle(
                    week_of="2026-04-27",
                    artifacts_root=self.artifacts_root,
                    quant_input_root=self.quant_inputs_root,
                    workbench_root=self.workbench_root,
                    ohlcv_external_root=self.ohlcv_root,
                    derivatives_external_root=self.derivatives_root,
                )

        self.assertEqual(summary["cycle_mode"], "discovery_full_daily")
        self.assertEqual(summary["proposal_lane_mix"].get("agent"), 0)
        self.assertEqual(summary["proposal_lane_mix"].get("heuristic"), 24)
        self.assertEqual(summary["agent_api_failure_rate"], 0.0)
        self.assertEqual(summary["agent_quarantined_proposal_count"], 1)
        self.assertEqual(summary["agent_compiler_hygiene_quarantine_count"], 1)
        self.assertEqual(
            summary["agent_quarantine_reason_counts"].get("new_feature_family proposals must include feature_registry_patch"),
            1,
        )
        self.assertTrue(Path(summary["agent_proposal_summary_path"]).exists())

    def test_weekly_proposal_cycle_falls_back_to_heuristic_on_agent_transport_error(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )

        with patch.dict(os.environ, {"OPENCLAW": "test-key"}, clear=False):
            with patch(
                "enhengclaw.quant_research.agent_proposals.openai_compatible_compile",
                side_effect=SliceCompilerTransportError(
                    "agent proposal selector request timed out: timeout",
                    details={
                        "request_body_chars": 4321,
                        "latency_ms": 2000,
                        "retry_count": 0,
                        "fallback_without_response_format": False,
                    },
                ),
            ):
                summary = run_quant_strategy_proposal_cycle(
                    week_of="2026-04-27",
                    artifacts_root=self.artifacts_root,
                    quant_input_root=self.quant_inputs_root,
                    workbench_root=self.workbench_root,
                    ohlcv_external_root=self.ohlcv_root,
                    derivatives_external_root=self.derivatives_root,
                )

        self.assertEqual(summary["cycle_mode"], "discovery_full_daily")
        self.assertEqual(summary["proposal_lane_mix"].get("agent"), 0)
        self.assertEqual(summary["proposal_lane_mix"].get("heuristic"), 24)
        self.assertEqual(summary["agent_api_failure_rate"], 1.0)
        self.assertTrue(Path(summary["agent_proposal_summary_path"]).exists())

    def test_load_strategy_library_normalizes_legacy_status_to_lifecycle(self) -> None:
        legacy_payload = {
            "generated_at_utc": utc_now(),
            "bootstrapped_as_of": "2026-04-20",
            "entries": [
                {
                    "strategy_id": "legacy-eth-balanced-logistic-single-asset",
                    "status": "candidate",
                    "shape": "single_asset",
                    "strategy_profile": "balanced",
                    "subject": "ETH",
                    "universe_filter": {},
                    "model_family": "logistic_regression",
                    "feature_groups": ["core_context", "trend", "derivatives"],
                    "profile_constraints_override": {},
                    "source": "proposal",
                }
            ],
        }
        save_strategy_library(artifacts_root=self.artifacts_root, payload=legacy_payload)

        loaded = load_strategy_library(artifacts_root=self.artifacts_root)
        self.assertEqual(loaded["entries"][0]["lifecycle"], "candidate")
        self.assertNotIn("status", loaded["entries"][0])

    def test_legacy_library_migrates_to_active_watch_candidate_discovery_split(self) -> None:
        entries: list[dict[str, object]] = []
        active_whitelist = [
            "baseline-eth-balanced-logistic-regression-single-asset",
            "baseline-eth-conservative-logistic-regression-single-asset",
            "baseline-eth-aggressive-meta-labeling-single-asset",
            "baseline-eth-balanced-meta-labeling-single-asset",
            "baseline-eth-conservative-meta-labeling-single-asset",
            "baseline-sui-aggressive-meta-labeling-single-asset",
            "baseline-sui-balanced-meta-labeling-single-asset",
        ]
        watch_whitelist = [
            "baseline-eth-aggressive-logistic-regression-single-asset",
            "baseline-sui-conservative-logistic-regression-single-asset",
        ]
        for strategy_id in active_whitelist + watch_whitelist:
            subject = "ETH" if "-eth-" in strategy_id else "SUI"
            entries.append(
                build_strategy_entry(
                    strategy_id=strategy_id,
                    shape="single_asset",
                    strategy_profile="balanced" if "-balanced-" in strategy_id else ("conservative" if "-conservative-" in strategy_id else "aggressive"),
                    subject=subject,
                    universe_filter=None,
                    model_family="meta_labeling" if "meta-labeling" in strategy_id else "logistic_regression",
                    feature_groups=["core_context", "trend", "derivatives"],
                    profile_constraints_override=None,
                    source="baseline",
                    status="active",
                )
            )
        for idx in range(77):
            entries.append(
                build_strategy_entry(
                    strategy_id=f"baseline-discovery-{idx}",
                    shape="single_asset",
                    strategy_profile="balanced",
                    subject="JTO",
                    universe_filter=None,
                    model_family="logistic_regression",
                    feature_groups=["core_context", "trend", "derivatives"],
                    profile_constraints_override=None,
                    source="baseline",
                    status="active",
                )
            )
        for idx in range(6):
            entries.append(
                build_strategy_entry(
                    strategy_id=f"proposal-candidate-{idx}",
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
            )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "library_version": 1,
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": entries,
            },
        )

        migrated = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=(),
        )
        counts: dict[str, int] = {}
        for entry in migrated["entries"]:
            counts[str(entry["lifecycle"])] = counts.get(str(entry["lifecycle"]), 0) + 1
        self.assertEqual(migrated["library_mode"], "thesis_task")
        self.assertEqual(len(migrated["entries"]), 3)
        self.assertEqual(counts, {"watch": 3})
        for entry in migrated["entries"]:
            self.assertTrue(str(entry.get("rationale") or "").strip())
            self.assertTrue(str(entry.get("expected_edge") or "").strip())
            self.assertTrue(str(entry.get("invalidates_if") or "").strip())
            self.assertTrue(dict(entry.get("data_dependencies") or {}))

    def test_weekly_promotion_candidate_then_active(self) -> None:
        seed_entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-single-asset",
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
        library = {"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-20", "entries": [seed_entry]}
        save_strategy_library(artifacts_root=self.artifacts_root, payload=library)

        proposal = {
            "proposal_id": "proposal-eth-tightened",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": "proposal-eth-tightened",
            "shape": "single_asset",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "universe_filter": {},
            "model_family": "logistic_regression",
            "feature_groups": ["core_context", "trend", "derivatives"],
            "profile_constraints_override": {
                "max_gross_leverage": 1.2,
                "max_turnover_per_rebalance": 1.0,
            },
            "rationale": "Test create-new-task flow.",
            "expected_edge": "If the proposal is real it should survive two consecutive weekly passes.",
            "invalidates_if": "Validation or test Sharpe turns non-positive.",
            "spec_hash": build_strategy_entry(
                strategy_id="tmp",
                shape="single_asset",
                strategy_profile="balanced",
                subject="ETH",
                universe_filter=None,
                model_family="logistic_regression",
                feature_groups=["core_context", "trend", "derivatives"],
                profile_constraints_override={"max_gross_leverage": 1.2, "max_turnover_per_rebalance": 1.0},
                source="proposal",
                status="candidate",
            )["spec_hash"],
        }

        first = apply_weekly_proposal_result(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            proposal_spec=proposal,
            evaluation_status="pass",
            week_of="2026-04-27",
        )
        self.assertEqual(first["action"], "create_new_task")

        second = apply_weekly_proposal_result(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            proposal_spec=proposal,
            evaluation_status="pass",
            week_of="2026-04-28",
        )
        self.assertEqual(second["action"], "promoted_to_active")
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        promoted = next(entry for entry in library["entries"] if entry["strategy_id"] == proposal["strategy_id"])
        self.assertEqual(promoted["lifecycle"], "active")
        self.assertEqual(promoted["source"], "discovery")
        self.assertTrue(str(promoted.get("rationale") or "").strip())

    def test_weekly_proposal_updates_existing_task_in_place(self) -> None:
        base_entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-single-asset",
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
        library = {"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-20", "entries": [base_entry]}
        save_strategy_library(artifacts_root=self.artifacts_root, payload=library)

        proposal = {
            "proposal_id": "proposal-update-existing-task",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": "proposal-update-existing-task",
            "shape": "single_asset",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "universe_filter": {},
            "model_family": "logistic_regression",
            "feature_groups": ["core_context", "trend", "derivatives"],
            "profile_constraints_override": {
                "max_gross_leverage": 1.2,
                "max_turnover_per_rebalance": 1.0,
            },
            "base_strategy_id": base_entry["strategy_id"],
            "rationale": "Update the existing thesis in place.",
            "expected_edge": "The revised task should preserve the same ETH continuation thesis with tighter controls.",
            "invalidates_if": "The revised task cannot survive one full weekly validation pass.",
            "spec_hash": build_strategy_entry(
                strategy_id="tmp-update-existing",
                shape="single_asset",
                strategy_profile="balanced",
                subject="ETH",
                universe_filter=None,
                model_family="logistic_regression",
                feature_groups=["core_context", "trend", "derivatives"],
                profile_constraints_override={"max_gross_leverage": 1.2, "max_turnover_per_rebalance": 1.0},
                source="proposal",
                status="candidate",
            )["spec_hash"],
        }

        result = apply_weekly_proposal_result(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            proposal_spec=proposal,
            evaluation_status="pass",
            week_of="2026-04-27",
        )
        self.assertEqual(result["action"], "update_existing_task")
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        self.assertEqual(len(library["entries"]), 1)
        updated = library["entries"][0]
        self.assertEqual(updated["strategy_id"], base_entry["strategy_id"])
        self.assertEqual(updated["spec_hash"], proposal["spec_hash"])
        self.assertEqual(updated["last_transition_reason"], "weekly_updated_existing_task")

    def test_build_discovery_recipes_generates_model_overlay_children_for_ready_portfolio_thesis(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "-funding_zscore_20",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        ready_entry = build_strategy_entry(
            strategy_id="thesis-funding-extreme-reversal-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_portfolio",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        ready_entry["model_overlay_ready"] = True
        blocked_entry = build_strategy_entry(
            strategy_id="thesis-basis-not-ready-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="basis_divergence",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_portfolio",
            promotion_eligibility="eligible",
            thesis_family="basis_mean_reversion",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile={**thesis_profile, "thesis_id": "basis-mean-reversion", "thesis_family": "basis_mean_reversion"},
        )
        blocked_entry["model_overlay_ready"] = False
        recipes = build_discovery_recipes(
            week_of="2026-04-27",
            strategy_library={"entries": [ready_entry, blocked_entry]},
            universe_candidates=(self._universe_candidate("ETH", 2), self._universe_candidate("SUI", 25)),
        )
        overlay_recipes = [recipe for recipe in recipes if str(recipe.get("search_action") or "") == "model_overlay"]
        self.assertEqual(len(overlay_recipes), 2)
        self.assertEqual(
            sorted(str(recipe["model_family"]) for recipe in overlay_recipes),
            ["logistic_regression", "ranking_scorer"],
        )
        self.assertTrue(all(str(recipe.get("proposal_bucket") or "") == "config" for recipe in overlay_recipes))
        self.assertTrue(all(str(recipe.get("bucket") or "") == "model_overlay" for recipe in overlay_recipes))
        self.assertTrue(all(str(recipe.get("research_lane") or "") == "hypothesis_model" for recipe in overlay_recipes))
        self.assertTrue(all(bool(recipe.get("model_overlay_ready")) for recipe in overlay_recipes))
        self.assertTrue(all(str(recipe.get("base_strategy_id") or "") == ready_entry["strategy_id"] for recipe in overlay_recipes))

    def test_weekly_model_overlay_creates_and_updates_child_without_mutating_parent(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "-funding_zscore_20",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        parent_entry = build_strategy_entry(
            strategy_id="thesis-funding-extreme-reversal-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_portfolio",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        parent_entry["model_overlay_ready"] = True
        parent_entry["portfolio_validation_pass_streak"] = 2
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [parent_entry]},
        )

        first_proposal = {
            "proposal_id": "overlay-logistic-create",
            "proposal_bucket": "config",
            "week_of": "2026-04-27",
            "strategy_id": model_overlay_child_strategy_id(
                base_strategy_id=parent_entry["strategy_id"],
                model_family="logistic_regression",
            ),
            "shape": "cross_sectional",
            "strategy_profile": "balanced",
            "subject": None,
            "universe_filter": {"preset": "liquid_perp_core_20"},
            "model_family": "logistic_regression",
            "feature_groups": ["derivatives"],
            "profile_constraints_override": {"max_turnover_per_rebalance": 0.8},
            "base_strategy_id": parent_entry["strategy_id"],
            "rationale": "First overlay candidate.",
            "expected_edge": "Improve calibration.",
            "invalidates_if": "Overlay weakens the validated portfolio thesis.",
            "proposal_origin": "heuristic",
            "search_action": "model_overlay",
            "parent_spec_hash": parent_entry["spec_hash"],
            "family_registry_patch": {},
            "feature_registry_patch": {},
            "priority_score": 0.92,
            "complexity_tier": "medium",
            "risk_tags": ["model_overlay"],
            "auto_bridge_requested": False,
            "research_lane": "hypothesis_model",
            "promotion_eligibility": "eligible",
            "thesis_family": "funding_extreme_reversal",
            "requires_derivatives_features": True,
            "daily_executable": True,
            "thesis_profile": thesis_profile,
        }
        created = apply_weekly_proposal_result(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            proposal_spec=first_proposal,
            evaluation_status="pass",
            week_of="2026-04-27",
        )
        self.assertEqual(created["action"], "create_new_task")
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        self.assertEqual(len(library["entries"]), 2)
        parent = next(entry for entry in library["entries"] if entry["strategy_id"] == parent_entry["strategy_id"])
        child = next(entry for entry in library["entries"] if entry["strategy_id"] == first_proposal["strategy_id"])
        self.assertEqual(parent["research_lane"], "hypothesis_portfolio")
        self.assertEqual(parent["portfolio_validation_pass_streak"], 2)
        self.assertEqual(child["research_lane"], "hypothesis_model")
        self.assertEqual(child["base_strategy_id"], parent_entry["strategy_id"])
        self.assertTrue(child["model_overlay_ready"])

        second_proposal = dict(first_proposal)
        second_proposal["proposal_id"] = "overlay-logistic-update"
        second_proposal["profile_constraints_override"] = {"max_turnover_per_rebalance": 0.6}
        updated = apply_weekly_proposal_result(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            proposal_spec=second_proposal,
            evaluation_status="pass",
            week_of="2026-04-28",
        )
        self.assertEqual(updated["action"], "update_existing_task")
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        self.assertEqual(len(library["entries"]), 2)
        parent = next(entry for entry in library["entries"] if entry["strategy_id"] == parent_entry["strategy_id"])
        child = next(entry for entry in library["entries"] if entry["strategy_id"] == first_proposal["strategy_id"])
        self.assertEqual(parent["research_lane"], "hypothesis_portfolio")
        self.assertEqual(parent["portfolio_validation_pass_streak"], 2)
        self.assertEqual(child["research_lane"], "hypothesis_model")
        self.assertEqual(child["last_transition_reason"], "weekly_updated_existing_task")
        self.assertEqual(child["base_strategy_id"], parent_entry["strategy_id"])

    def test_daily_governance_keeps_thesis_tasks_in_queue_while_recording_failures(self) -> None:
        entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-single-asset",
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
        library = {"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-20", "entries": [entry]}
        save_strategy_library(artifacts_root=self.artifacts_root, payload=library)

        apply_daily_governance(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            experiments=[
                self._fake_experiment(
                    entry,
                    status="fail",
                    validation_net_return=0.12,
                    walk_forward_median_oos_sharpe=0.4,
                )
            ],
            as_of="2026-04-20",
        )
        retained = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(retained["lifecycle"], "active")
        self.assertEqual(retained["last_daily_experiment_status"], "fail")
        self.assertEqual(retained["daily_fail_streak"], 1)
        self.assertEqual(retained["last_transition_reason"], "daily_active_failure_recorded")

        for offset in range(2):
            apply_daily_governance(
                artifacts_root=self.artifacts_root,
                strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
                experiments=[
                    self._fake_experiment(
                        retained,
                        status="fail",
                        validation_net_return=-0.1,
                        walk_forward_median_oos_sharpe=-0.2,
                    )
                ],
                as_of=f"2026-04-{23 + offset:02d}",
            )
        updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["lifecycle"], "active")
        self.assertEqual(updated["daily_fail_streak"], 3)

    def test_daily_governance_keeps_rerun_required_out_of_fail_streaks(self) -> None:
        entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-single-asset",
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
        entry["daily_pass_streak"] = 3
        entry["daily_fail_streak"] = 1
        library = {"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-20", "entries": [entry]}
        save_strategy_library(artifacts_root=self.artifacts_root, payload=library)

        apply_daily_governance(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            experiments=[
                self._fake_experiment(
                    entry,
                    status="needs_rerun_after_overlap_fix",
                    validation_net_return=-0.2,
                    walk_forward_median_oos_sharpe=-0.1,
                )
            ],
            as_of="2026-04-20",
        )
        updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["lifecycle"], "active")
        self.assertEqual(updated["last_daily_experiment_status"], "needs_rerun_after_overlap_fix")
        self.assertEqual(updated["daily_pass_streak"], 0)
        self.assertEqual(updated["daily_fail_streak"], 0)

    def test_thesis_seed_state_is_preserved_across_library_ensure(self) -> None:
        library = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=(self._universe_candidate("ETH", 2),),
        )
        entry = next(
            item
            for item in library["entries"]
            if str(item.get("strategy_id")) == "thesis-funding-extreme-reversal-cross-sectional"
        )
        entry["research_lane"] = "hypothesis_portfolio"
        entry["factor_gate_pass_streak"] = 1
        entry["portfolio_validation_pass_streak"] = 1
        entry["model_overlay_ready"] = True
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-27",
                "library_mode": "thesis_task",
                "entries": library["entries"],
            },
        )

        refreshed = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-28",
            universe_candidates=(self._universe_candidate("ETH", 2),),
        )
        updated = next(
            item
            for item in refreshed["entries"]
            if str(item.get("strategy_id")) == "thesis-funding-extreme-reversal-cross-sectional"
        )
        self.assertEqual(updated["research_lane"], "hypothesis_portfolio")
        self.assertEqual(updated["factor_gate_pass_streak"], 1)
        self.assertEqual(updated["portfolio_validation_pass_streak"], 1)
        self.assertTrue(updated["model_overlay_ready"])

    def test_hypothesis_factor_lane_advances_to_portfolio_after_pass(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "funding_zscore_20 * -1",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        entry = build_strategy_entry(
            strategy_id="thesis-factor-stage",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_factor",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [entry]},
        )

        apply_daily_governance(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            experiments=[
                self._fake_experiment(
                    entry,
                    status="pass",
                    validation_net_return=0.02,
                    walk_forward_median_oos_sharpe=0.4,
                    factor_evidence_passed=True,
                )
            ],
            as_of="2026-04-27",
        )
        updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["research_lane"], "hypothesis_portfolio")

    def test_hypothesis_factor_lane_archives_after_two_factor_failures(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "funding_zscore_20 * -1",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        entry = build_strategy_entry(
            strategy_id="thesis-factor-failing",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_factor",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [entry]},
        )

        updated = entry
        for offset in range(2):
            apply_daily_governance(
                artifacts_root=self.artifacts_root,
                strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
                experiments=[
                    self._fake_experiment(
                        updated,
                        status="fail",
                        validation_net_return=-0.02,
                        walk_forward_median_oos_sharpe=-0.4,
                        validation="failed",
                        blocker_codes=["factor_evidence_failed"],
                        factor_evidence_passed=False,
                    )
                ],
                as_of=f"2026-04-{28 + offset:02d}",
            )
            updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["lifecycle"], "retired")
        self.assertEqual(updated["promotion_eligibility"], "ineligible")
        self.assertEqual(updated["thesis_archived_reason"], "factor_evidence_failed_twice")

    def test_hypothesis_factor_lane_does_not_consume_fail_streak_when_factor_gate_not_evaluated(self) -> None:
        thesis_profile = {
            "thesis_id": "funding-extreme-reversal",
            "thesis_family": "funding_extreme_reversal",
            "market_mechanism": "crowding reversal",
            "directional_claim": "fade crowding",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
            "factor_formula": "funding_zscore_20 * -1",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["capacity_constraint_breach"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        entry = build_strategy_entry(
            strategy_id="thesis-factor-not-evaluated",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_factor",
            promotion_eligibility="eligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [entry]},
        )

        apply_daily_governance(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            experiments=[
                self._fake_experiment(
                    entry,
                    status="invalidated",
                    validation="failed",
                    blocker_codes=["derivatives_history_gap"],
                    factor_evidence_present=False,
                )
            ],
            as_of="2026-04-27",
        )
        updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["lifecycle"], "active")
        self.assertEqual(updated["factor_gate_fail_streak"], 0)
        self.assertIs(updated["last_factor_evidence_evaluated"], False)
        self.assertIsNone(updated["last_factor_evidence_passed"])
        self.assertEqual(updated["last_transition_reason"], "factor_gate_not_evaluated")

    def test_ensure_strategy_library_repairs_legacy_factor_archive_without_factor_evaluation_marker(self) -> None:
        repaired = build_strategy_entry(
            strategy_id="thesis-funding-extreme-reversal-cross-sectional",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="carry_funding",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="retired",
            research_lane="hypothesis_factor",
            promotion_eligibility="ineligible",
            thesis_family="funding_extreme_reversal",
            requires_derivatives_features=True,
            daily_executable=False,
            thesis_profile={
                "thesis_id": "funding_extreme_reversal",
                "thesis_family": "funding_extreme_reversal",
                "market_mechanism": "crowding reversal",
                "directional_claim": "fade crowding",
                "universe_rule": {"preset": "liquid_perp_core_20"},
                "execution_venue": "perp",
                "requires_derivatives_features": True,
                "minimum_executable_history_days": 365,
                "minimum_executable_coverage_ratio": 0.85,
                "required_feature_columns": ["funding_zscore_20", "oi_change_5"],
                "factor_formula": "funding_zscore_20 * -1",
                "intended_holding_horizon_bars": 1,
                "falsification_conditions": ["capacity_constraint_breach"],
                "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
            },
        )
        repaired["thesis_archived_reason"] = "factor_evidence_failed_twice"
        repaired["last_daily_experiment_status"] = "invalidated"
        repaired["factor_gate_fail_streak"] = 2
        repaired["last_transition_reason"] = "factor_evidence_failed_twice"
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [repaired]},
        )

        refreshed = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=(),
        )
        updated = next(
            item
            for item in refreshed["entries"]
            if str(item.get("strategy_id")) == "thesis-funding-extreme-reversal-cross-sectional"
        )
        self.assertEqual(updated["lifecycle"], "watch")
        self.assertEqual(updated["promotion_eligibility"], "eligible")
        self.assertFalse(updated["daily_executable"])
        self.assertEqual(updated["factor_gate_fail_streak"], 0)
        self.assertIsNone(updated["thesis_archived_reason"])
        self.assertEqual(updated["last_transition_reason"], "restored_after_readiness_gate_rewrite")

    def test_pending_leakage_audit_timeout_archives_thesis(self) -> None:
        thesis_profile = {
            "thesis_id": "basis-mean-reversion",
            "thesis_family": "basis_mean_reversion",
            "market_mechanism": "basis reversion",
            "directional_claim": "fade basis extremes",
            "universe_rule": {"preset": "liquid_perp_core_20"},
            "execution_venue": "perp",
            "requires_derivatives_features": True,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["basis_proxy", "basis_zscore_20"],
            "factor_formula": "-basis_zscore_20",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["leakage_audit_timeout"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        entry = build_strategy_entry(
            strategy_id="thesis-anomaly-stage",
            shape="cross_sectional",
            strategy_profile="balanced",
            subject=None,
            universe_filter={"preset": "liquid_perp_core_20"},
            model_family="basis_divergence",
            feature_groups=["derivatives"],
            profile_constraints_override=None,
            source="proposal",
            status="active",
            research_lane="hypothesis_factor",
            promotion_eligibility="eligible",
            thesis_family="basis_mean_reversion",
            requires_derivatives_features=True,
            daily_executable=True,
            thesis_profile=thesis_profile,
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-27", "entries": [entry]},
        )
        alpha_id = f"fake-{entry['strategy_id']}"
        leakage_path = (
            self.artifacts_root
            / "governance"
            / "leakage_audits"
            / "2026-04-27"
            / f"{alpha_id}.leakage_audit.json"
        )
        leakage_path.parent.mkdir(parents=True, exist_ok=True)
        leakage_path.write_text(
            json.dumps(
                {
                    "contract_version": "quant_leakage_audit.v1",
                    "generated_at_utc": (datetime.now(UTC) - timedelta(hours=25)).isoformat().replace("+00:00", "Z"),
                    "reviewed_at_utc": None,
                    "as_of": "2026-04-27",
                    "alpha_id": alpha_id,
                    "strategy_id": entry["strategy_id"],
                    "status": "pending",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        apply_daily_governance(
            artifacts_root=self.artifacts_root,
            strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
            experiments=[
                self._fake_experiment(
                    entry,
                    status="quarantined",
                    validation="leakage_audit_required",
                    blocker_codes=["sharpe_anomaly_detected"],
                    factor_evidence_passed=True,
                )
            ],
            as_of="2026-04-27",
        )
        updated = load_strategy_library(artifacts_root=self.artifacts_root)["entries"][0]
        self.assertEqual(updated["lifecycle"], "retired")
        self.assertEqual(updated["thesis_archived_reason"], "leakage_audit_timeout")

    def test_strategy_library_sync_adds_derivatives_first_cross_sectional_baselines(self) -> None:
        migrated = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=(
                self._universe_candidate("ETH", 2),
                self._universe_candidate("SUI", 25),
            ),
        )
        self.assertEqual(len(migrated["entries"]), 3)
        cross_sectional_families = sorted(
            str(entry["model_family"])
            for entry in migrated["entries"]
            if str(entry.get("shape")) == "cross_sectional"
        )
        self.assertEqual(
            cross_sectional_families,
            [
                "basis_divergence",
                "carry_funding",
                "event_drift",
            ],
        )
        self.assertEqual(migrated["library_mode"], "thesis_task")
        self.assertTrue(
            all(str(entry.get("rationale") or "").strip() for entry in migrated["entries"])
        )
        self.assertTrue(all(str(entry.get("research_lane") or "") == "hypothesis_factor" for entry in migrated["entries"]))
        self.assertTrue(
            all(str(entry.get("promotion_eligibility") or "") == "eligible" for entry in migrated["entries"])
        )
        self.assertTrue(all("thesis_profile" in entry for entry in migrated["entries"]))

    def test_eligible_daily_strategies_applies_monitoring_and_candidate_budgets(self) -> None:
        entries = []
        thesis_template = {
            "thesis_family": "cross_sectional_rank",
            "market_mechanism": "cross-sectional relative strength dispersion",
            "directional_claim": "rank liquid names and rebalance into the strongest cohort",
            "universe_rule": {"liquidity_buckets": ["top_liquidity", "mid_liquidity"]},
            "execution_venue": "spot",
            "requires_derivatives_features": False,
            "minimum_executable_history_days": 365,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["relative_strength_20"],
            "factor_formula": "relative_strength_20",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["top_minus_bottom_return_non_positive"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }
        for idx in range(10):
            entries.append(
                build_strategy_entry(
                    strategy_id=f"thesis-active-{idx}",
                    shape="cross_sectional",
                    strategy_profile="balanced",
                    subject=None,
                    universe_filter={"liquidity_buckets": ["top_liquidity", "mid_liquidity"]},
                    model_family="logistic_regression",
                    feature_groups=["core_context", "trend", "volume"],
                    profile_constraints_override=None,
                    source="proposal",
                    status="active",
                    research_lane="hypothesis_factor",
                    promotion_eligibility="eligible",
                    thesis_family="cross_sectional_rank",
                    requires_derivatives_features=False,
                    daily_executable=True,
                    thesis_profile={**thesis_template, "thesis_id": f"cross-rank-{idx}"},
                )
            )
        for idx in range(3):
            entries.append(
                build_strategy_entry(
                    strategy_id=f"thesis-watch-{idx}",
                    shape="cross_sectional",
                    strategy_profile="balanced",
                    subject=None,
                    universe_filter={"liquidity_buckets": ["top_liquidity"]},
                    model_family="ranking_scorer",
                    feature_groups=["core_context", "trend", "volume"],
                    profile_constraints_override=None,
                    source="proposal",
                    status="watch",
                    research_lane="hypothesis_factor",
                    promotion_eligibility="eligible",
                    thesis_family="cross_sectional_rank",
                    requires_derivatives_features=False,
                    daily_executable=True,
                    thesis_profile={**thesis_template, "thesis_id": f"watch-rank-{idx}"},
                )
            )
        for idx in range(3):
            entries.append(
                build_strategy_entry(
                    strategy_id=f"thesis-candidate-{idx}",
                    shape="cross_sectional",
                    strategy_profile="balanced",
                    subject=None,
                    universe_filter={"liquidity_buckets": ["top_liquidity", "mid_liquidity", "tail_liquidity"]},
                    model_family="relative_strength_cross_section",
                    feature_groups=["core_context", "trend", "volume"],
                    profile_constraints_override={"max_gross_leverage": 1.2},
                    source="proposal",
                    status="candidate",
                    research_lane="hypothesis_factor",
                    promotion_eligibility="eligible",
                    thesis_family="cross_sectional_rank",
                    requires_derivatives_features=False,
                    daily_executable=True,
                    thesis_profile={**thesis_template, "thesis_id": f"candidate-rank-{idx}"},
                )
            )
        selected = eligible_daily_strategies(strategy_library={"entries": entries})
        active_count = sum(1 for entry in selected if entry["lifecycle"] == "active")
        watch_count = sum(1 for entry in selected if entry["lifecycle"] == "watch")
        candidate_count = sum(1 for entry in selected if entry["lifecycle"] == "candidate")
        self.assertEqual(len(selected), 3)
        self.assertEqual(active_count, 3)
        self.assertEqual(watch_count, 0)
        self.assertEqual(candidate_count, 0)

    def test_ensure_strategy_library_freezes_blocked_seed_families_out_of_daily_lane(self) -> None:
        refreshed = ensure_strategy_library(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-27",
            universe_candidates=(),
        )
        blocked_entries = {
            str(entry.get("strategy_id")): entry
            for entry in refreshed["entries"]
            if str(entry.get("strategy_id") or "").strip()
            in {
                "thesis-funding-extreme-reversal-cross-sectional",
                "thesis-basis-mean-reversion-cross-sectional",
            }
        }
        self.assertEqual(
            set(blocked_entries),
            {
                "thesis-funding-extreme-reversal-cross-sectional",
                "thesis-basis-mean-reversion-cross-sectional",
            },
        )
        self.assertTrue(all(str(entry["lifecycle"]) == "watch" for entry in blocked_entries.values()))
        self.assertTrue(all(entry["daily_executable"] is False for entry in blocked_entries.values()))

    def test_weekly_proposal_cycle_smoke(self) -> None:
        run_quant_universe_freeze(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        self._write_derivatives_sync_summary(as_of="2026-04-20")
        run_quant_research_cycle(
            as_of="2026-04-20",
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
        )

        with patch.dict(
            os.environ,
            {
                "OPENCLAW_AGENT_PROPOSAL_API_KEY": "",
                "OPENCLAW": "",
                "OPENAI_API_KEY": "",
            },
            clear=False,
        ):
            summary = run_quant_strategy_proposal_cycle(
                week_of="2026-04-27",
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
                ohlcv_external_root=self.ohlcv_root,
                derivatives_external_root=self.derivatives_root,
            )
        self.assertEqual(summary["cycle_mode"], "discovery_full_daily")
        self.assertEqual(summary["discovery_recipe_count"], 24)
        self.assertLess(summary["screen_recipe_count"], summary["discovery_recipe_count"])
        self.assertEqual(summary["full_validation_count"], 12)
        self.assertLessEqual(summary["shortlist_count"], 4)
        self.assertEqual(summary["as_of"], "2026-04-27")
        self.assertEqual(summary["governance_as_of"], "2026-04-27")
        self.assertEqual(summary["discovery_cadence"], "daily_full")
        self.assertTrue(str(summary["run_id"]).strip())
        self.assertIn("proposal_lane_mix", summary)
        self.assertEqual(summary["proposal_lane_mix"].get("heuristic"), 24)
        self.assertEqual(summary["proposal_lane_mix"].get("agent"), 0)
        self.assertTrue(Path(summary["registry_snapshot_path"]).exists())
        self.assertTrue(Path(summary["agent_proposal_summary_path"]).exists())
        self.assertTrue(Path(summary["discovery_governance_summary_path"]).exists())
        self.assertTrue(Path(summary["discovery_governance_summary_md_path"]).exists())
        self.assertTrue(Path(summary["weekly_governance_summary_path"]).exists())
        self.assertTrue(Path(summary["weekly_governance_summary_md_path"]).exists())
        self.assertTrue(Path(summary["discovery_recipe_catalog_path"]).exists())
        self.assertTrue(Path(summary["discovery_screen_summary_path"]).exists())
        self.assertTrue(Path(summary["discovery_shortlist_path"]).exists())
        recipe_catalog = json.loads(Path(summary["discovery_recipe_catalog_path"]).read_text(encoding="utf-8"))
        self.assertGreater(recipe_catalog["blocked_data_gap_recipe_count"], 0)
        library = load_strategy_library(artifacts_root=self.artifacts_root)
        self.assertLessEqual(len(library["entries"]), 16)
        self.assertEqual(library["library_mode"], "thesis_task")

    def test_weekly_promotion_cap_defers_third_candidate(self) -> None:
        base_entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-single-asset",
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
        library = {"generated_at_utc": utc_now(), "bootstrapped_as_of": "2026-04-20", "entries": [base_entry]}
        save_strategy_library(artifacts_root=self.artifacts_root, payload=library)

        proposals = []
        for idx in range(3):
            proposal = {
                "proposal_id": f"proposal-eth-tightened-{idx}",
                "proposal_bucket": "config",
                "week_of": "2026-04-27",
                "strategy_id": f"proposal-eth-tightened-{idx}",
                "shape": "single_asset",
                "strategy_profile": "balanced",
                "subject": "ETH",
                "universe_filter": {},
                "model_family": "logistic_regression",
                "feature_groups": ["core_context", "trend", "derivatives"],
                "profile_constraints_override": {
                    "max_gross_leverage": 1.2,
                    "max_turnover_per_rebalance": 1.0,
                },
                "rationale": f"Create new task {idx}.",
                "expected_edge": "Passing proposals can create at most two new tasks per week.",
                "invalidates_if": "The proposal cannot survive validation outside the creation window.",
                "spec_hash": build_strategy_entry(
                    strategy_id=f"tmp-{idx}",
                    shape="single_asset",
                    strategy_profile="balanced",
                    subject="ETH",
                    universe_filter=None,
                    model_family="logistic_regression",
                    feature_groups=["core_context", "trend", "derivatives"],
                    profile_constraints_override={"max_gross_leverage": 1.2, "max_turnover_per_rebalance": 1.0 + idx / 10},
                    source="proposal",
                    status="candidate",
                )["spec_hash"],
            }
            proposal["profile_constraints_override"]["max_turnover_per_rebalance"] = 1.0 + idx / 10
            proposals.append(proposal)
        actions = [
            apply_weekly_proposal_result(
                artifacts_root=self.artifacts_root,
                strategy_library=load_strategy_library(artifacts_root=self.artifacts_root),
                proposal_spec=proposal,
                evaluation_status="pass",
                week_of="2026-04-27",
            )["action"]
            for proposal in proposals
        ]
        self.assertEqual(actions.count("create_new_task"), 2)
        self.assertEqual(actions.count("promotion_deferred_new_task_cap"), 1)

    def _fake_compile_artifacts(
        self,
        *,
        candidate_payload: dict[str, object],
        stage: str,
        prompt_tokens: int,
        completion_tokens: int,
        fallback_without_response_format: bool = False,
        retry_count: int = 0,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            transcript_payload={"backend_kind": "openai_compatible", "backend_name": "gpt-test", "stage": stage},
            compiler_output={
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [candidate_payload],
                "notes": [],
            },
            raw_model_output={
                "response_json": {
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }
                }
            },
            model_request={
                "request_body_chars": 4096,
                "latency_ms": 1234,
                "retry_count": retry_count,
                "fallback_without_response_format": fallback_without_response_format,
            },
        )

    def _fake_experiment(
        self,
        entry: dict[str, object],
        *,
        status: str,
        validation_net_return: float = 0.0,
        walk_forward_median_oos_sharpe: float = 0.0,
        validation: str = "passed",
        blocker_codes: list[str] | None = None,
        factor_evidence_passed: bool = True,
        factor_evidence_present: bool = True,
    ) -> dict[str, object]:
        experiment_root = self.temp_dir / "fake_experiments" / str(entry["strategy_id"])
        experiment_root.mkdir(parents=True, exist_ok=True)
        alpha_card_path = experiment_root / "alpha_card.json"
        alpha_card_md_path = experiment_root / "alpha_card.md"
        alpha_card = {
            "generated_at_utc": utc_now(),
            "experiment_id": f"fake-{entry['strategy_id']}",
            "strategy_id": entry["strategy_id"],
            "spec_hash": entry["spec_hash"],
            "source": entry["source"],
            "experiment_status": status,
        }
        alpha_card_path.write_text(json.dumps(alpha_card, indent=2), encoding="utf-8")
        alpha_card_md_path.write_text("# fake\n", encoding="utf-8")
        return {
            "experiment_id": f"fake-{entry['strategy_id']}",
            "strategy_id": entry["strategy_id"],
            "experiment_status": status,
            "validation": validation,
            "source": entry["source"],
            "spec_hash": entry["spec_hash"],
            "validation_report": {
                "validation": validation,
                "validation_metrics": {"net_return": validation_net_return},
                "test_metrics": {"net_return": validation_net_return, "sharpe": 0.0, "max_drawdown": 0.0},
                "walk_forward": {"median_oos_sharpe": walk_forward_median_oos_sharpe},
                "validation_contract": {
                    "contract_version": "quant_validation_contract.v7",
                    "status": "passed" if not blocker_codes else "failed",
                    "blockers": list(blocker_codes or []),
                },
                "factor_evidence": (
                    {
                        "passed": factor_evidence_passed,
                        "rank_ic_mean": 0.02 if factor_evidence_passed else 0.0,
                        "rank_ic_positive_rate": 0.55 if factor_evidence_passed else 0.0,
                        "top_minus_bottom_return": 0.01 if factor_evidence_passed else 0.0,
                        "monotonicity_passed": factor_evidence_passed,
                        "decay_curve": {"intended_horizon_return": 0.01 if factor_evidence_passed else 0.0},
                        "turnover": 0.2,
                        "max_trade_participation_rate": 0.001,
                        "max_inventory_participation_rate": 0.001,
                        "regime_split_results": {
                            "positive_regime_count": 3 if factor_evidence_passed else 0,
                            "max_positive_contribution_ratio": 0.3,
                        },
                    }
                    if factor_evidence_present
                    else {}
                ),
            },
            "alpha_card": alpha_card,
            "alpha_card_path": str(alpha_card_path),
            "alpha_card_md_path": str(alpha_card_md_path),
        }

    def _single_asset_thesis_profile(self, *, subject: str = "ETH") -> dict[str, object]:
        return {
            "thesis_id": f"{subject.lower()}-feature-variant",
            "thesis_family": "event_drift",
            "market_mechanism": "single-asset feature variant",
            "directional_claim": "test a tighter single-asset feature configuration",
            "universe_rule": {"subject": subject},
            "execution_venue": "spot",
            "requires_derivatives_features": False,
            "minimum_executable_history_days": 180,
            "minimum_executable_coverage_ratio": 0.85,
            "required_feature_columns": ["return_1"],
            "factor_formula": "return_1",
            "intended_holding_horizon_bars": 1,
            "falsification_conditions": ["validation_return_negative"],
            "promotion_path": ["hypothesis_factor", "hypothesis_portfolio", "hypothesis_model"],
        }

    def _universe_candidate(self, subject: str, rank: int) -> QuantUniverseCandidate:
        return QuantUniverseCandidate.from_payload(
            pit_candidate(
                subject,
                rank,
                listing_age_days_as_of=600,
                selection_score=max(1.0, 1_000_000_000.0 - rank),
                rolling_mean_quote_volume_usd_30d=max(1.0, 1_000_000_000.0 - rank),
            )
        )

    def _seed_quant_input(self) -> None:
        smoke_candidates = [
            pit_candidate("ETH", 2, listing_age_days_as_of=2200, selection_score=18_000_000_000.0),
            pit_candidate("SUI", 28, listing_age_days_as_of=650, selection_score=1_400_000_000.0),
            pit_candidate("JTO", 95, listing_age_days_as_of=500, selection_score=280_000_000.0),
        ]
        top100_candidates = list(smoke_candidates)
        for rank in range(4, 29):
            top100_candidates.append(
                pit_candidate(
                    f"T{rank:02d}",
                    rank,
                    listing_age_days_as_of=400 + rank,
                    selection_score=float(500_000_000 - (rank * 1_000_000)),
                    usdm_symbol=f"T{rank:02d}USDT" if rank % 2 == 0 else None,
                )
            )
        payloads = {
            "2026-04-20": smoke_candidates,
            "2026-04-27": top100_candidates,
        }
        for as_of, candidates in payloads.items():
            write_pit_quant_input(
                root=self.quant_inputs_root,
                as_of=as_of,
                candidates=candidates,
            )

    def _seed_market_history(self) -> None:
        start_daily = datetime(2025, 9, 1, tzinfo=UTC)
        start_4h = datetime(2025, 12, 1, tzinfo=UTC)
        start_1h = datetime(2026, 2, 1, tzinfo=UTC)
        specs = [
            ("ETHUSDT", 2500.0, 0.004, 0.02),
            ("SUIUSDT", 1.2, 0.006, 0.05),
            ("JTOUSDT", 2.0, 0.008, 0.08),
        ]
        for symbol, base_price, drift, wiggle in specs:
            self._write_ohlcv_series("spot", symbol, "1d", start_daily, 230, base_price, drift, wiggle)
            self._write_ohlcv_series("spot", symbol, "4h", start_4h, 1100, base_price, drift / 6.0, wiggle / 2.0)
            self._write_ohlcv_series("spot", symbol, "1h", start_1h, 1600, base_price, drift / 24.0, wiggle / 3.0)
            self._write_ohlcv_series("usdm_perp", symbol, "1d", start_daily, 230, base_price * 1.001, drift * 1.05, wiggle)
            self._write_ohlcv_series("usdm_perp", symbol, "4h", start_4h, 1100, base_price * 1.001, drift / 6.0, wiggle / 2.0)
            self._write_derivative_series(symbol, "4h", start_4h, 1100)
            self._write_derivative_series(symbol, "1d", start_daily, 230)

    def _write_ohlcv_series(
        self,
        market_type: str,
        symbol: str,
        interval: str,
        start: datetime,
        periods: int,
        base_price: float,
        drift: float,
        wiggle: float,
    ) -> None:
        interval_delta = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        current_price = base_price
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            oscillation = math.sin(index / 7.0) * wiggle
            close_price = current_price * (1.0 + drift + oscillation / 100.0)
            high_price = max(current_price, close_price) * 1.01
            low_price = min(current_price, close_price) * 0.99
            volume = 1_000_000 + (index * 500)
            quote_volume = volume * ((current_price + close_price) / 2.0)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": market_type,
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "open": f"{current_price:.8f}",
                    "high": f"{high_price:.8f}",
                    "low": f"{low_price:.8f}",
                    "close": f"{close_price:.8f}",
                    "volume": f"{volume:.8f}",
                    "quote_volume": f"{quote_volume:.8f}",
                    "trade_count": "1000",
                    "taker_buy_base_volume": f"{volume * 0.51:.8f}",
                    "taker_buy_quote_volume": f"{quote_volume * 0.51:.8f}",
                    "source": "test",
                }
            )
            current_price = close_price
        self._write_partitioned_rows(root=self.ohlcv_root / market_type / symbol / interval, headers=OHLCV_HEADERS, rows=rows)

    def _write_derivative_series(self, symbol: str, interval: str, start: datetime, periods: int) -> None:
        interval_delta = {"4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "funding_rate": f"{0.0001 + (index % 5) * 0.00001:.10f}",
                    "funding_sample_count": "1",
                    "open_interest": f"{1_000_000 + (index * 10_000):.10f}",
                    "open_interest_value": f"{50_000_000 + (index * 500_000):.10f}",
                    "source": "test",
                }
            )
        self._write_partitioned_rows(root=self.derivatives_root / symbol / interval, headers=DERIVATIVE_HEADERS, rows=rows)

    def _write_partitioned_rows(self, *, root: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        monthly: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            open_time_ms = int(row["open_time_ms"])
            month_key = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).strftime("%Y-%m")
            monthly.setdefault(month_key, []).append(row)
        root.mkdir(parents=True, exist_ok=True)
        for month_key, month_rows in monthly.items():
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=headers)
            writer.writeheader()
            writer.writerows(month_rows)
            with gzip.open(root / f"{month_key}.csv.gz", "wt", encoding="utf-8", newline="") as handle:
                handle.write(buffer.getvalue())
        manifest = {
            "generated_at_utc": utc_now(),
            "partition_count": len(monthly),
            "partitions": {month: {"path": str(root / f"{month}.csv.gz"), "row_count": len(month_rows)} for month, month_rows in monthly.items()},
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _write_derivatives_sync_summary(self, *, as_of: str) -> None:
        self.derivatives_root.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "success",
            "generated_at_utc": f"{as_of}T03:05:00Z",
            "external_root": str(self.derivatives_root),
            "mode": "refresh",
            "symbols": ["ETHUSDT", "JTOUSDT", "SUIUSDT"],
            "intervals": ["4h", "1d"],
            "sync_results": [],
        }
        (self.derivatives_root / "last_sync_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
