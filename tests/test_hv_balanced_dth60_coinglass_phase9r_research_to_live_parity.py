from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QUANT_SCRIPT_DIR = ROOT / "scripts" / "quant_research"
H10D_SCRIPT_DIR = QUANT_SCRIPT_DIR / "h10d_current_diagnostics"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(QUANT_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(QUANT_SCRIPT_DIR))
if str(H10D_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(H10D_SCRIPT_DIR))

import run_dth60_frozen_q90_top20_forward_validation as frozen_forward  # noqa: E402
import run_dth60_overlay_robustness_validation as robust  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase3_parity import (  # noqa: E402
    TARGET_FACTOR,
    contribution_column_name,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9r_research_to_live_parity import (  # noqa: E402
    SCORER_MODE_LIVE_CANONICAL,
    compare_factor_contributions,
    compare_target_weight_traces,
    expected_factor_contribution,
    expected_target_contribution,
    live_trigger_from_research_thresholds,
    score_live_candidate_from_research_window,
    target_weight_trace,
    validate_research_scorer_contract,
)


FEATURE_WEIGHTS = {
    "distance_to_high_60": 0.5,
    "distance_to_high_5": 0.3,
    "realized_volatility_5": -0.2,
}
TWELVE_FACTOR_WEIGHTS = {
    "intraday_realized_vol_4h_to_1d_smooth_60": -0.08,
    "realized_volatility_5": -0.07,
    "distance_to_high_60": 0.12,
    "distance_to_high_5": 0.09,
    "coinglass_top_trader_long_pct_smooth_5": -0.06,
    "liquidity_stress_qv_iv": -0.05,
    "momentum_decay_5_20": 0.04,
    "coinglass_taker_imb_intraday_dispersion_24h": 0.03,
    "quality_funding_oi": -0.11,
    "downside_upside_vol_ratio_30": 0.10,
    "funding_basis_residual_implied_repo_30": 0.13,
    "settlement_cycle_premium_60d": -0.12,
}


class HvBalancedDth60CoinglassPhase9rResearchToLiveParityTests(unittest.TestCase):
    def test_live_trigger_matches_research_robust_mask(self) -> None:
        panel = self._panel()
        definition = {
            item["label"]: item for item in frozen_forward.build_definitions()
        }[frozen_forward.FROZEN_LABEL]
        thresholds = {
            "shock_co_occurrence_index_q90": 5.0,
            "co_jump_count_3d_q90": 50.0,
        }

        live_trigger, live_multiplier, branch_frame = live_trigger_from_research_thresholds(
            panel,
            shock_quantile=float(definition["shock_quantile"]),
            crowded_top_fraction=float(definition["crowded_top_fraction"]),
            thresholds=thresholds,
        )
        research_trigger = robust.robust_trigger_mask(panel, variant=definition, thresholds=thresholds)

        self.assertEqual(live_trigger.tolist(), research_trigger.tolist())
        np.testing.assert_allclose(
            live_multiplier.to_numpy(),
            np.where(research_trigger.to_numpy(), 0.0, 1.0),
            rtol=0.0,
            atol=0.0,
        )
        self.assertTrue(branch_frame["live_shock_branch_trigger"].any())
        self.assertTrue(branch_frame["live_crowded_branch_trigger"].any())

    def test_research_contract_scorer_reproduces_research_score_and_target_contribution(self) -> None:
        panel = self._panel()
        definition = {
            item["label"]: item for item in frozen_forward.build_definitions()
        }[frozen_forward.FROZEN_LABEL]
        thresholds = {
            "shock_co_occurrence_index_q90": 5.0,
            "co_jump_count_3d_q90": 50.0,
        }
        research_scored, _ = robust.score_frame_with_robust_overlay(
            panel,
            factor_weights=FEATURE_WEIGHTS,
            variant=definition,
            thresholds=thresholds,
        )
        live_trigger, live_multiplier, _ = live_trigger_from_research_thresholds(
            panel,
            shock_quantile=float(definition["shock_quantile"]),
            crowded_top_fraction=float(definition["crowded_top_fraction"]),
            thresholds=thresholds,
        )
        live_scored = score_live_candidate_from_research_window(
            panel,
            weights=FEATURE_WEIGHTS,
            trigger=live_trigger,
            multiplier=live_multiplier,
        )
        expected_contribution = expected_target_contribution(
            panel,
            weights=FEATURE_WEIGHTS,
            multiplier=research_scored["dth60_overlay_multiplier"],
        )

        np.testing.assert_allclose(
            live_scored[contribution_column_name(TARGET_FACTOR)].to_numpy(),
            expected_contribution.to_numpy(),
            rtol=0.0,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            live_scored["score"].to_numpy(),
            research_scored["score"].to_numpy(),
            rtol=0.0,
            atol=1e-12,
        )

        self.assertEqual(
            research_scored["dth60_overlay_triggered"].astype(bool).tolist(),
            live_trigger.tolist(),
        )

    def test_live_canonical_mode_surfaces_research_zscore_contract_drift(self) -> None:
        panel = self._panel()
        definition = {
            item["label"]: item for item in frozen_forward.build_definitions()
        }[frozen_forward.FROZEN_LABEL]
        thresholds = {
            "shock_co_occurrence_index_q90": 5.0,
            "co_jump_count_3d_q90": 50.0,
        }
        research_scored, _ = robust.score_frame_with_robust_overlay(
            panel,
            factor_weights=FEATURE_WEIGHTS,
            variant=definition,
            thresholds=thresholds,
        )
        live_trigger, live_multiplier, _ = live_trigger_from_research_thresholds(
            panel,
            shock_quantile=float(definition["shock_quantile"]),
            crowded_top_fraction=float(definition["crowded_top_fraction"]),
            thresholds=thresholds,
        )
        live_scored = score_live_candidate_from_research_window(
            panel,
            weights=FEATURE_WEIGHTS,
            trigger=live_trigger,
            multiplier=live_multiplier,
            scorer_mode=SCORER_MODE_LIVE_CANONICAL,
        )
        expected_contribution = expected_target_contribution(
            panel,
            weights=FEATURE_WEIGHTS,
            multiplier=research_scored["dth60_overlay_multiplier"],
        )
        contribution_diff = (
            live_scored[contribution_column_name(TARGET_FACTOR)] - expected_contribution
        ).abs()

        self.assertGreater(float(contribution_diff.max()), 0.0)

    def test_twelve_factor_research_contract_and_contribution_parity_are_explicit(self) -> None:
        panel = self._panel()
        definition = {
            item["label"]: item for item in frozen_forward.build_definitions()
        }[frozen_forward.FROZEN_LABEL]
        thresholds = {
            "shock_co_occurrence_index_q90": 5.0,
            "co_jump_count_3d_q90": 50.0,
        }
        contract = {
            "required_feature_columns": list(TWELVE_FACTOR_WEIGHTS),
            "target_horizon_bars": 10,
            "factor_formula": (
                "For each train split/window: compute daily cross-sectional Spearman IC of each "
                "required factor z-score versus target_execution_forward_return, convert to IR, "
                "normalize signed |IR| weights to abs-sum 1.0, then final_score = tanh(...)."
            ),
            "portfolio_construction_baseline": {
                "target_engine": "multiphase_equal_sleeve",
                "phase_offsets_days": list(range(10)),
                "sleeve_weight": 0.1,
            },
            "overlay_id": None,
        }
        context = {
            "active_factor_columns": list(TWELVE_FACTOR_WEIGHTS),
            "feature_columns": list(TWELVE_FACTOR_WEIGHTS),
            "frame": panel,
        }
        constraints = {
            "top_long_count": 3,
            "bottom_short_count": 3,
            "short_allowed": True,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
        }
        split_contract = {"target_horizon_bars": 10, "realization_step_bars": 10}
        checks = validate_research_scorer_contract(
            contract=contract,
            context=context,
            split_contract=split_contract,
            constraints=constraints,
        )
        self.assertEqual(checks["status"], "ready")
        self.assertTrue(checks["checks"]["required_feature_count_is_12"])
        self.assertTrue(checks["checks"]["active_factor_columns_equal_required_features_in_order"])

        live_trigger, live_multiplier, _ = live_trigger_from_research_thresholds(
            panel,
            shock_quantile=float(definition["shock_quantile"]),
            crowded_top_fraction=float(definition["crowded_top_fraction"]),
            thresholds=thresholds,
        )
        live_scored = score_live_candidate_from_research_window(
            panel,
            weights=TWELVE_FACTOR_WEIGHTS,
            trigger=live_trigger,
            multiplier=live_multiplier,
        )
        stats, rows, mismatches = compare_factor_contributions(
            panel,
            live_scored,
            weights=TWELVE_FACTOR_WEIGHTS,
            factor_columns=list(TWELVE_FACTOR_WEIGHTS),
            target_factor=TARGET_FACTOR,
            multiplier=live_multiplier,
            window_id="w0",
            tolerance=1e-12,
            sample_limit=20,
        )

        self.assertEqual(stats["factor_count"], 12)
        self.assertEqual(len(rows), 12)
        self.assertEqual(stats["mismatch_count"], 0)
        self.assertTrue(mismatches.empty)
        for factor in TWELVE_FACTOR_WEIGHTS:
            expected = expected_factor_contribution(
                panel,
                weights=TWELVE_FACTOR_WEIGHTS,
                factor=factor,
                target_factor=TARGET_FACTOR,
                multiplier=live_multiplier,
            )
            np.testing.assert_allclose(
                live_scored[f"contribution_{factor}"].to_numpy(),
                expected.to_numpy(),
                rtol=0.0,
                atol=1e-12,
            )

        drifted = live_scored.copy(deep=True)
        drifted.loc[0, "contribution_quality_funding_oi"] += 0.25
        drift_stats, _, drift_mismatches = compare_factor_contributions(
            panel,
            drifted,
            weights=TWELVE_FACTOR_WEIGHTS,
            factor_columns=list(TWELVE_FACTOR_WEIGHTS),
            target_factor=TARGET_FACTOR,
            multiplier=live_multiplier,
            window_id="w0",
            tolerance=1e-12,
            sample_limit=20,
        )
        self.assertEqual(drift_stats["mismatch_count"], 1)
        self.assertFalse(drift_mismatches.empty)
        self.assertEqual(drift_mismatches.iloc[0]["factor"], "quality_funding_oi")

    def test_target_weight_trace_matches_identical_scores_and_detects_drift(self) -> None:
        scored = pd.DataFrame(
            {
                "timestamp_ms": [1, 1, 1, 1],
                "subject": ["A", "B", "C", "D"],
                "score": [0.8, 0.4, -0.2, -0.7],
            }
        )
        constraints = {
            "top_long_count": 2,
            "bottom_short_count": 1,
            "long_leverage": 0.6,
            "short_allowed": True,
            "short_leverage": 0.3,
        }
        split_contract = {"realization_step_bars": 1}
        research_trace = target_weight_trace(
            scored,
            constraints=constraints,
            split_contract=split_contract,
            window_id="w0",
        )
        live_trace = target_weight_trace(
            scored,
            constraints=constraints,
            split_contract=split_contract,
            window_id="w0",
        )
        stats, mismatches = compare_target_weight_traces(research_trace, live_trace, tolerance=1e-12)

        self.assertEqual(stats["mismatch_count"], 0)
        self.assertTrue(mismatches.empty)

        drifted = scored.copy(deep=True)
        drifted.loc[drifted["subject"].eq("D"), "score"] = 0.95
        drifted_trace = target_weight_trace(
            drifted,
            constraints=constraints,
            split_contract=split_contract,
            window_id="w0",
        )
        drift_stats, drift_mismatches = compare_target_weight_traces(
            research_trace,
            drifted_trace,
            tolerance=1e-12,
        )

        self.assertGreater(drift_stats["mismatch_count"], 0)
        self.assertFalse(drift_mismatches.empty)

    def _panel(self) -> pd.DataFrame:
        rows = []
        for ts_index, timestamp_ms in enumerate([1_780_704_000_000, 1_780_790_400_000]):
            shock = 1.0 if ts_index == 0 else 6.0
            co_jump = 10.0 if ts_index == 0 else 60.0
            for symbol_index in range(5):
                rows.append(
                    {
                        "timestamp_ms": timestamp_ms,
                        "subject": f"SYM{symbol_index}",
                        "shock_co_occurrence_index": shock,
                        "co_jump_count_3d": co_jump,
                        "coinglass_top_trader_long_pct_smooth_5": 50.0 + symbol_index,
                        "distance_to_high_60": 0.1 + symbol_index * 0.2,
                        "distance_to_high_5": 1.0 + symbol_index * 0.1 + ts_index * 0.05,
                        "realized_volatility_5": 0.5 - symbol_index * 0.03 + ts_index * 0.02,
                        "intraday_realized_vol_4h_to_1d_smooth_60": 0.2 + symbol_index * 0.04 + ts_index * 0.01,
                        "liquidity_stress_qv_iv": 0.3 + symbol_index * 0.02 - ts_index * 0.01,
                        "momentum_decay_5_20": -0.2 + symbol_index * 0.05 + ts_index * 0.02,
                        "coinglass_taker_imb_intraday_dispersion_24h": 0.15 + symbol_index * 0.03,
                        "quality_funding_oi": 0.4 - symbol_index * 0.04 + ts_index * 0.01,
                        "downside_upside_vol_ratio_30": 0.8 + symbol_index * 0.06 - ts_index * 0.03,
                        "funding_basis_residual_implied_repo_30": -0.1 + symbol_index * 0.07,
                        "settlement_cycle_premium_60d": 0.05 - symbol_index * 0.02 + ts_index * 0.04,
                    }
                )
        return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
