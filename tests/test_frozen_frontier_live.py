"""Integration + parity tests for the live wiring of the FROZEN 12-factor frontier.

Covers, end to end and default-off-first:
  * resolution: dormant (default-off), fail-closed-when-armed, armed_ready on real
    contracts, scoring-config drift, kill-switch terminal disarm, synthetic-overlay block;
  * snapshot hook: default-off byte-identical, frontier-blocked fail-closed, armed 12-factor
    scoring, overlay contribution masking;
  * parity: live frontier score == the canonical scorer with the frozen weights (+overlay),
    and the vectorised overlay trigger == the frozen contract's scalar trigger;
  * single-phase == multiphase scoring (no split-brain);
  * arm→submit binding in the delta-execution submit gate.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.frozen_frontier_contract import (  # noqa: E402
    file_sha256 as contract_file_sha256,
    frontier_spec_hash,
    load_frozen_frontier,
)
from enhengclaw.live_trading.frozen_frontier_overlay import (  # noqa: E402
    OVERLAY_ID,
    compute_overlay_trigger,
    load_overlay_contract,
    overlay_spec_hash,
)
from enhengclaw.live_trading.frozen_frontier_live import (  # noqa: E402
    FrontierResolution,
    resolve_frontier_live_plan,
)
from enhengclaw.live_trading.hv_balanced_live_signal import (  # noqa: E402
    OVERLAY_TARGET_FACTOR,
    _frontier_overlay_contribution_multipliers,
    augment_panel_with_overlay_shock_gauges,
    build_live_hv_balanced_snapshot,
)
from enhengclaw.quant_research.features import build_cross_sectional_features  # noqa: E402
from enhengclaw.live_trading.mainnet_delta_execution_runner import _frontier_submit_gate  # noqa: E402
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import (  # noqa: E402
    build_multiphase_target_portfolio,
)
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import score_binance_ohlcv_core  # noqa: E402

FRONTIER_DIR = ROOT / "config" / "quant_research" / "frontier_12factor"
REAL_WEIGHTS = FRONTIER_DIR / "v5_rw_bridge_no_overlay_h10d__2026-05-02-54814da2622b__frozen_frontier_weights.json"
REAL_SCORING = FRONTIER_DIR / "v5_rw_bridge_no_overlay_h10d_12factor_frontier_scoring.json"
REAL_OVERLAY = FRONTIER_DIR / "dth60_hybrid_shock_q90_or_crowded_top20_zero__overlay.frozen.json"
BASELINE_CONFIG = ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"

REAL_PIT_THRESHOLDS = {
    "from_input_panel": True,
    "train_includes_decision_row": False,
    "current_row_excluded": True,
    "shock_co_occurrence_index_q90": 0.42,
    "co_jump_count_3d_q90": 9.0,
}


def _armed_payload(*, overlay: bool = False, thresholds: dict | None = None) -> dict:
    """A live-config payload that resolves to armed_ready against the REAL contracts."""
    contract = load_frozen_frontier(REAL_WEIGHTS)
    frontier: dict = {
        "enabled": True,
        "weights_contract_path": str(REAL_WEIGHTS.relative_to(ROOT)).replace("\\", "/"),
        "weights_file_sha256": contract_file_sha256(REAL_WEIGHTS),
        "weights_spec_hash": frontier_spec_hash(contract),
        "scoring_config_path": str(REAL_SCORING.relative_to(ROOT)).replace("\\", "/"),
        "scoring_config_sha256": contract_file_sha256(REAL_SCORING),
    }
    if overlay:
        frontier["overlay"] = {
            "enabled": True,
            "contract_path": str(REAL_OVERLAY.relative_to(ROOT)).replace("\\", "/"),
            "file_sha256": contract_file_sha256(REAL_OVERLAY),
            "spec_hash": overlay_spec_hash(load_overlay_contract(REAL_OVERLAY)),
            "thresholds": dict(thresholds or REAL_PIT_THRESHOLDS),
        }
    return {"strategy": {"frontier": frontier}}


def _effective_config() -> tuple[dict, dict]:
    contract = load_frozen_frontier(REAL_WEIGHTS)
    cfg = json.loads(REAL_SCORING.read_text(encoding="utf-8-sig"))
    cfg["pit_data_eligibility_policy"] = {"mode": "disabled"}  # skip rolling-history eligibility in tests
    cfg["feature_columns"] = list(contract["feature_columns"])
    cfg["feature_weights"] = dict(contract["feature_weights"])
    return cfg, contract


def _armed_resolution(*, overlay: bool = False, thresholds: dict | None = None) -> FrontierResolution:
    cfg, contract = _effective_config()
    return FrontierResolution(
        status="armed_ready",
        enabled=True,
        overlay_enabled=overlay,
        arm_binding="testbind",
        feature_columns=list(contract["feature_columns"]),
        weights_spec_hash=str(contract.get("frozen_frontier_spec_hash") or ""),
        effective_config_sha256="testsha",
        effective_config=cfg,
        overlay_thresholds=dict(thresholds or REAL_PIT_THRESHOLDS) if overlay else None,
    )


def _panel_12(timestamp_ms: int = 0, *, crowded: tuple[str, ...] = ()) -> pd.DataFrame:
    subjects = ["L1", "L2", "L3", "S1", "S2", "S3"]
    rows = []
    for index, subject in enumerate(subjects):
        base = 0.10 + index * 0.01
        is_crowded = subject in crowded
        rows.append(
            {
                "timestamp_ms": timestamp_ms,
                "subject": subject,
                "usdm_symbol": f"{subject}USDT",
                "perp_close": 100.0 + index,
                "perp_quote_volume_usd": 10_000_000.0,
                "universe_active": True,
                "universe_rank": index + 1,
                "liquidity_bucket": "top_liquidity" if subject.startswith("L") else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                # 12 frozen-frontier factors
                "intraday_realized_vol_4h_to_1d_smooth_60": base,
                "realized_volatility_5": base + 0.01,
                "distance_to_high_60": 0.90 if is_crowded else base + 0.02,
                "distance_to_high_5": -0.01 if subject.startswith("S") else -0.20,
                "coinglass_top_trader_long_pct_smooth_5": 0.95 if is_crowded else 0.10 + index * 0.02,
                "liquidity_stress_qv_iv": base + 0.015,
                "momentum_decay_5_20": 0.01 * index,
                "coinglass_taker_imb_intraday_dispersion_24h": 0.05 + 0.01 * index,
                "quality_funding_oi": 0.02 * index,
                "downside_upside_vol_ratio_30": base + 0.03,
                "funding_basis_residual_implied_repo_30": -0.01 * (index + 1),
                "settlement_cycle_premium_60d": 0.001 * index,
                # risk-brake input + overlay shock gauges
                "momentum_20": 0.05,
                "shock_co_occurrence_index": 0.0,
                "co_jump_count_3d": 0.0,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------
class FrontierResolutionTests(unittest.TestCase):
    def test_default_off_is_dormant_and_side_effect_free(self) -> None:
        res = resolve_frontier_live_plan({})
        self.assertEqual(res.status, "dormant")
        self.assertTrue(res.is_dormant)
        self.assertIsNone(res.arm_binding)
        self.assertIsNone(res.effective_config)
        # An explicit false flag is still dormant.
        self.assertTrue(resolve_frontier_live_plan({"strategy": {"frontier": {"enabled": False}}}).is_dormant)

    def test_armed_ready_on_real_contracts(self) -> None:
        res = resolve_frontier_live_plan(_armed_payload(), operator_state={"paused": False})
        self.assertEqual(res.status, "armed_ready", res.blockers)
        self.assertEqual(len(res.feature_columns), 12)
        self.assertIsNotNone(res.arm_binding)
        self.assertIsNotNone(res.effective_config)
        # The contract pins the weights verbatim into the effective config.
        contract = load_frozen_frontier(REAL_WEIGHTS)
        self.assertEqual(res.effective_config["feature_weights"], contract["feature_weights"])
        self.assertEqual(sorted(res.effective_config["feature_columns"]), sorted(contract["feature_columns"]))

    def test_armed_overlay_with_real_pit_thresholds(self) -> None:
        res = resolve_frontier_live_plan(_armed_payload(overlay=True), operator_state={"paused": False})
        self.assertEqual(res.status, "armed_ready", res.blockers)
        self.assertTrue(res.overlay_enabled)
        self.assertEqual(str(res.overlay_contract.get("overlay_id")), OVERLAY_ID)

    def test_fail_closed_when_armed_but_hashes_unpinned(self) -> None:
        res = resolve_frontier_live_plan({"strategy": {"frontier": {"enabled": True}}}, operator_state={"paused": False})
        self.assertEqual(res.status, "blocked")
        self.assertIn("frontier_weights_file_sha256_not_pinned", res.blockers)
        self.assertIn("frontier_weights_spec_hash_not_pinned", res.blockers)
        self.assertIn("frontier_scoring_config_path_missing", res.blockers)

    def test_fail_closed_on_scoring_config_sha_mismatch(self) -> None:
        payload = _armed_payload()
        payload["strategy"]["frontier"]["scoring_config_sha256"] = "0" * 64
        res = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any(b.startswith("frontier_scoring_config_sha256_mismatch") for b in res.blockers), res.blockers)

    def test_fail_closed_on_baseline_scoring_config(self) -> None:
        # Pointing at the 5-factor baseline must be rejected (not marked + column mismatch).
        payload = _armed_payload()
        payload["strategy"]["frontier"]["scoring_config_path"] = str(BASELINE_CONFIG.relative_to(ROOT)).replace("\\", "/")
        payload["strategy"]["frontier"]["scoring_config_sha256"] = contract_file_sha256(BASELINE_CONFIG)
        res = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        self.assertEqual(res.status, "blocked")
        self.assertIn("frontier_scoring_config_not_marked_frontier", res.blockers)
        self.assertIn("frontier_scoring_config_columns_mismatch_with_weight_contract", res.blockers)

    def test_kill_switch_is_terminal_disarm(self) -> None:
        res = resolve_frontier_live_plan(
            _armed_payload(),
            operator_state={"paused": True, "last_action_type": "kill-switch"},
        )
        self.assertEqual(res.status, "blocked")
        self.assertTrue(res.terminal_disarm)
        self.assertTrue(any(b.startswith("frontier_terminal_disarm_operator_paused_or_kill_switch") for b in res.blockers))

    def test_unavailable_operator_state_when_armed_fails_closed(self) -> None:
        res = resolve_frontier_live_plan(_armed_payload(), operator_state=None)
        self.assertEqual(res.status, "blocked")
        self.assertIn("frontier_operator_state_unavailable", res.blockers)

    def test_arm_binding_covers_overlay_threshold_values(self) -> None:
        # A post-arm edit of the live q90 threshold VALUES must change the arm binding,
        # even though the overlay CONTRACT file (and its spec_hash) is unchanged.
        base = resolve_frontier_live_plan(_armed_payload(overlay=True), operator_state={"paused": False})
        again = resolve_frontier_live_plan(_armed_payload(overlay=True), operator_state={"paused": False})
        edited = resolve_frontier_live_plan(
            _armed_payload(overlay=True, thresholds={**REAL_PIT_THRESHOLDS, "co_jump_count_3d_q90": 5.0}),
            operator_state={"paused": False},
        )
        self.assertEqual(base.status, "armed_ready", base.blockers)
        self.assertEqual(edited.status, "armed_ready", edited.blockers)
        # Same overlay contract + spec_hash on both, but the value edit changed the binding.
        self.assertEqual(base.overlay_spec_hash, edited.overlay_spec_hash)
        self.assertEqual(base.arm_binding, again.arm_binding)  # stable for identical thresholds
        self.assertNotEqual(base.arm_binding, edited.arm_binding)

    def test_arm_binding_threshold_view_is_exact_int_float_agnostic_no_collision(self) -> None:
        def _bind(thresholds: dict) -> str:
            res = resolve_frontier_live_plan(
                _armed_payload(overlay=True, thresholds=thresholds), operator_state={"paused": False}
            )
            self.assertEqual(res.status, "armed_ready", res.blockers)
            return res.arm_binding

        # int 9 and float 9.0 are the SAME value -> identical binding (YAML 4 vs 4.0 robustness).
        self.assertEqual(
            _bind({**REAL_PIT_THRESHOLDS, "co_jump_count_3d_q90": 9}),
            _bind({**REAL_PIT_THRESHOLDS, "co_jump_count_3d_q90": 9.0}),
        )
        # A sub-1e-12 edit is NOT lost to rounding: float.hex() distinguishes every double.
        self.assertNotEqual(
            _bind({**REAL_PIT_THRESHOLDS, "shock_co_occurrence_index_q90": 0.42}),
            _bind({**REAL_PIT_THRESHOLDS, "shock_co_occurrence_index_q90": 0.42 + 1e-13}),
        )

    def test_synthetic_overlay_thresholds_blocked(self) -> None:
        synthetic = {**REAL_PIT_THRESHOLDS, "from_input_panel": False}
        res = resolve_frontier_live_plan(
            _armed_payload(overlay=True, thresholds=synthetic), operator_state={"paused": False}
        )
        self.assertEqual(res.status, "blocked")
        self.assertIn("overlay_thresholds_not_from_input_panel", res.blockers)


# --------------------------------------------------------------------------------------
# Snapshot hook
# --------------------------------------------------------------------------------------
class FrontierSnapshotHookTests(unittest.TestCase):
    def _baseline_config(self) -> dict:
        cfg = json.loads(BASELINE_CONFIG.read_text(encoding="utf-8-sig"))
        cfg["pit_data_eligibility_policy"] = {"mode": "disabled"}
        return cfg

    def test_default_off_is_byte_identical(self) -> None:
        cfg = self._baseline_config()
        panel = _panel_12()
        none_snap = build_live_hv_balanced_snapshot(panel, config=cfg, config_sha256="x", decision_time_ms=0)
        dormant_snap = build_live_hv_balanced_snapshot(
            panel, config=cfg, config_sha256="x", decision_time_ms=0, frontier=resolve_frontier_live_plan({})
        )
        self.assertEqual(none_snap.status, "ok", none_snap.blockers)
        pd.testing.assert_series_equal(
            none_snap.scores["score"].reset_index(drop=True),
            dormant_snap.scores["score"].reset_index(drop=True),
        )
        self.assertEqual(none_snap.config_sha256, "x")

    def test_blocked_frontier_fails_closed(self) -> None:
        cfg = self._baseline_config()
        blocked = FrontierResolution(
            status="blocked", enabled=True, overlay_enabled=False, blockers=["frontier_weights_spec_hash_not_pinned"]
        )
        snap = build_live_hv_balanced_snapshot(_panel_12(), config=cfg, config_sha256="x", decision_time_ms=0, frontier=blocked)
        self.assertEqual(snap.status, "blocked")
        self.assertIn("frontier_blocked:frontier_weights_spec_hash_not_pinned", snap.blockers)

    def test_armed_scores_twelve_factors_with_parity(self) -> None:
        res = _armed_resolution()
        panel = _panel_12()
        snap = build_live_hv_balanced_snapshot(
            panel, config=self._baseline_config(), config_sha256="x", decision_time_ms=0, frontier=res
        )
        self.assertEqual(snap.status, "ok", snap.blockers)
        self.assertEqual(snap.config_sha256, "testsha")
        self.assertTrue(snap.strategy_label.startswith("v5_rw_bridge_no_overlay_h10d_12factor"))
        # Parity: the live score is exactly the canonical scorer with the frozen weights.
        reference = score_binance_ohlcv_core(
            panel.copy(),
            feature_columns=res.feature_columns,
            feature_weights=res.effective_config["feature_weights"],
            require_complete_feature_set=True,
            enforce_alpha_purity=False,
        )
        np.testing.assert_allclose(
            snap.scores.sort_values("subject")["score"].to_numpy(),
            reference.to_numpy()[np.argsort(panel["subject"].to_numpy())],
            rtol=0, atol=1e-12,
        )

    def test_overlay_masks_only_dth60_contribution_with_parity(self) -> None:
        # Force the crowded branch for L1 (high dth60 rank AND high crowded rank).
        panel = _panel_12(crowded=("L1",))
        cfg = self._baseline_config()
        no_overlay = build_live_hv_balanced_snapshot(
            panel, config=cfg, config_sha256="x", decision_time_ms=0, frontier=_armed_resolution(overlay=False)
        )
        # Use thresholds high enough that ONLY the crowded branch can fire.
        thresholds = {**REAL_PIT_THRESHOLDS, "shock_co_occurrence_index_q90": 1e9, "co_jump_count_3d_q90": 1e9}
        overlaid = build_live_hv_balanced_snapshot(
            panel, config=cfg, config_sha256="x", decision_time_ms=0,
            frontier=_armed_resolution(overlay=True, thresholds=thresholds),
        )
        self.assertEqual(overlaid.status, "ok", overlaid.blockers)
        # The overlay changes the cross-sectional outcome.
        self.assertFalse(
            np.allclose(
                no_overlay.scores.sort_values("subject")["score"].to_numpy(),
                overlaid.scores.sort_values("subject")["score"].to_numpy(),
            )
        )
        # Parity: overlaid live score == canonical scorer with the same contribution mask.
        res = _armed_resolution(overlay=True, thresholds=thresholds)
        mult = _frontier_overlay_contribution_multipliers(panel.copy(), thresholds=thresholds)
        reference = score_binance_ohlcv_core(
            panel.copy(),
            feature_columns=res.feature_columns,
            feature_weights=res.effective_config["feature_weights"],
            require_complete_feature_set=True,
            enforce_alpha_purity=False,
            contribution_multipliers=mult,
        )
        np.testing.assert_allclose(
            overlaid.scores.sort_values("subject")["score"].to_numpy(),
            reference.to_numpy()[np.argsort(panel["subject"].to_numpy())],
            rtol=0, atol=1e-12,
        )

    def test_overlay_blocks_when_gauge_columns_missing(self) -> None:
        panel = _panel_12().drop(columns=["shock_co_occurrence_index"])
        snap = build_live_hv_balanced_snapshot(
            panel, config=self._baseline_config(), config_sha256="x", decision_time_ms=0,
            frontier=_armed_resolution(overlay=True),
        )
        self.assertEqual(snap.status, "blocked")
        self.assertTrue(any(b.startswith("frontier_overlay_gauge_columns_missing") for b in snap.blockers))

    def test_vectorised_trigger_matches_contract_scalar(self) -> None:
        panel = _panel_12(crowded=("L1",))
        thresholds = {**REAL_PIT_THRESHOLDS, "shock_co_occurrence_index_q90": 0.3, "co_jump_count_3d_q90": 5.0}
        mult = _frontier_overlay_contribution_multipliers(panel.copy(), thresholds=thresholds)[OVERLAY_TARGET_FACTOR]
        from enhengclaw.quant_research._binance_canonical_normalization import _timestamp_percentile_rank

        ts = panel["timestamp_ms"]
        dh_rank = _timestamp_percentile_rank(panel[OVERLAY_TARGET_FACTOR], ts)
        tt_rank = _timestamp_percentile_rank(panel["coinglass_top_trader_long_pct_smooth_5"], ts)
        for idx in panel.index:
            scalar = compute_overlay_trigger(
                shock_co_occurrence_index=panel.loc[idx, "shock_co_occurrence_index"],
                co_jump_count_3d=panel.loc[idx, "co_jump_count_3d"],
                shock_q90=thresholds["shock_co_occurrence_index_q90"],
                co_jump_q90=thresholds["co_jump_count_3d_q90"],
                distance_to_high_60_rank_pct=dh_rank.loc[idx],
                coinglass_top_trader_rank_pct=tt_rank.loc[idx],
            )
            self.assertEqual(mult.loc[idx], scalar["target_multiplier"])


# --------------------------------------------------------------------------------------
# Single-phase == multiphase (no split-brain)
# --------------------------------------------------------------------------------------
class FrontierSinglePhaseMultiphaseParityTests(unittest.TestCase):
    def test_single_and_multiphase_score_identically(self) -> None:
        res = _armed_resolution()
        panel = _panel_12()
        cfg = json.loads(BASELINE_CONFIG.read_text(encoding="utf-8-sig"))
        single_snap = build_live_hv_balanced_snapshot(
            panel, config=cfg, config_sha256="x", decision_time_ms=0, frontier=res
        )
        single_portfolio = build_target_portfolio(single_snap, config=res.effective_config, allocated_capital_usdt=1000.0)
        single_scores = {p.subject: round(float(p.score), 12) for p in single_portfolio.positions}

        _, context = build_multiphase_target_portfolio(
            panel,
            config=cfg,
            config_sha256="x",
            allocated_capital_usdt=1000.0,
            phase_contexts=[{"phase_offset_days": 0, "decision_time_ms": 0, "blockers": []}],
            rebalance_interval_days=10,
            rebalance_epoch_ms=0,
            frontier=res,
        )
        multi_scores = {row["subject"]: round(float(row["score"]), 12) for row in context["sleeve_targets"]}
        self.assertTrue(single_scores)
        self.assertEqual(single_scores, multi_scores)


# --------------------------------------------------------------------------------------
# arm→submit binding (delta-execution submit gate)
# --------------------------------------------------------------------------------------
class FrontierSubmitGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="frontier-submit-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_plan_frontier(self, payload: dict) -> None:
        (self.tmp / "frontier_plan.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_absent_is_not_applicable(self) -> None:
        gate = _frontier_submit_gate(plan={"plan_root": str(self.tmp)}, payload={}, operator_state={"paused": False})
        self.assertEqual(gate["status"], "not_applicable")
        self.assertEqual(gate["blockers"], [])

    def test_dormant_is_not_applicable(self) -> None:
        self._write_plan_frontier({"status": "dormant"})
        gate = _frontier_submit_gate(plan={"plan_root": str(self.tmp)}, payload={}, operator_state={"paused": False})
        self.assertEqual(gate["status"], "not_applicable")
        self.assertEqual(gate["blockers"], [])

    def test_plan_blocked_at_arm_blocks_submit(self) -> None:
        self._write_plan_frontier({"status": "blocked", "arm_binding": None})
        gate = _frontier_submit_gate(plan={"plan_root": str(self.tmp)}, payload={}, operator_state={"paused": False})
        self.assertEqual(gate["status"], "blocked")
        self.assertIn("frontier_plan_was_blocked_at_arm", gate["blockers"])

    def test_binding_match_passes(self) -> None:
        payload = _armed_payload()
        armed = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        self.assertEqual(armed.status, "armed_ready", armed.blockers)
        self._write_plan_frontier(armed.to_artifact())
        gate = _frontier_submit_gate(
            plan={"plan_root": str(self.tmp)}, payload=payload, operator_state={"paused": False}
        )
        self.assertEqual(gate["status"], "armed_ready", gate["blockers"])
        self.assertEqual(gate["blockers"], [])

    def test_binding_mismatch_blocks(self) -> None:
        payload = _armed_payload()
        armed = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        tampered = armed.to_artifact()
        tampered["arm_binding"] = "deadbeef"  # forged binding
        self._write_plan_frontier(tampered)
        gate = _frontier_submit_gate(
            plan={"plan_root": str(self.tmp)}, payload=payload, operator_state={"paused": False}
        )
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(b.startswith("frontier_arm_submit_binding_mismatch") for b in gate["blockers"]))

    def test_overlay_threshold_edit_after_arm_blocks_submit(self) -> None:
        # Arm with the overlay on, persist the plan, then edit a live q90 threshold. The
        # submit gate must refuse on binding drift (the threshold values are now bound).
        payload = _armed_payload(overlay=True)
        armed = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        self.assertEqual(armed.status, "armed_ready", armed.blockers)
        self._write_plan_frontier(armed.to_artifact())
        tampered_payload = _armed_payload(overlay=True)
        tampered_payload["strategy"]["frontier"]["overlay"]["thresholds"]["shock_co_occurrence_index_q90"] = 0.99
        gate = _frontier_submit_gate(
            plan={"plan_root": str(self.tmp)}, payload=tampered_payload, operator_state={"paused": False}
        )
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(b.startswith("frontier_arm_submit_binding_mismatch") for b in gate["blockers"]))

    def test_kill_switch_at_submit_blocks(self) -> None:
        payload = _armed_payload()
        armed = resolve_frontier_live_plan(payload, operator_state={"paused": False})
        self._write_plan_frontier(armed.to_artifact())
        gate = _frontier_submit_gate(
            plan={"plan_root": str(self.tmp)}, payload=payload,
            operator_state={"paused": True, "last_action_type": "kill-switch"},
        )
        self.assertEqual(gate["status"], "blocked")
        self.assertIn("frontier_terminal_disarm_at_submit", gate["blockers"])
        self.assertIn("frontier_disarmed_or_invalid_since_plan", gate["blockers"])


def _research_grade_panel(*, n_subjects: int = 8, n_days: int = 90, seed: int = 7) -> pd.DataFrame:
    """A gap-free multi-subject daily panel carrying every column build_cross_sectional_features
    needs, so the research bundle is the ground-truth oracle for the shock gauges."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D", tz="UTC")
    rows = []
    for s_i in range(n_subjects):
        subject = f"S{s_i}"
        px = 100.0 + s_i
        for day in dates:
            px *= 1.0 + rng.normal(0, 0.03)
            rows.append(
                {
                    "timestamp_ms": int(day.timestamp() * 1000),
                    "date_utc": day.date().isoformat(),
                    "subject": subject,
                    "usdm_symbol": f"{subject}USDT",
                    "symbol": f"{subject}USDT",
                    "spot_open": px * 0.999, "spot_high": px * 1.01, "spot_low": px * 0.99,
                    "spot_close": px, "spot_volume": 1e6, "spot_quote_volume": 1e7, "spot_trade_count": 1000,
                    "perp_close": px * 1.001, "perp_quote_volume_usd": 1e7, "quote_volume_usd": 1e7,
                    "volume": 1e6, "close": px, "open_interest": 5e6, "funding_rate": 0.0001, "basis_proxy": 0.001,
                }
            )
    return pd.DataFrame(rows)


class OverlayShockGaugeParityTests(unittest.TestCase):
    def test_gauges_byte_match_research_bundle(self) -> None:
        panel = _research_grade_panel()
        oracle = build_cross_sectional_features(panel)
        mine = augment_panel_with_overlay_shock_gauges(panel)
        key = ["subject", "timestamp_ms"]
        merged = oracle[key + ["shock_co_occurrence_index", "co_jump_count_3d"]].merge(
            mine[key + ["shock_co_occurrence_index", "co_jump_count_3d"]], on=key, suffixes=("_o", "_m")
        )
        # The bundle drops only the final label-warm-down timestamp; every shared row must match.
        self.assertGreater(len(merged), 0)
        self.assertGreater(int((merged["shock_co_occurrence_index_o"] > 0).sum()), 0)  # gauge is exercised
        for col in ("shock_co_occurrence_index", "co_jump_count_3d"):
            np.testing.assert_allclose(
                merged[f"{col}_o"].to_numpy(), merged[f"{col}_m"].to_numpy(), rtol=0, atol=1e-12
            )

    def test_returns_unchanged_when_inputs_absent(self) -> None:
        # No subject/return_1/spot_close -> fail-closed: panel returned unchanged.
        bare = pd.DataFrame({"timestamp_ms": [0, 0], "subject": ["A", "B"]})
        out = augment_panel_with_overlay_shock_gauges(bare)
        self.assertNotIn("shock_co_occurrence_index", out.columns)
        self.assertTrue(out.equals(bare))

    def test_fails_closed_when_spot_close_incomplete_at_decision_row(self) -> None:
        # #8: a symbol whose live spot fetch failed is NaN after the merge. Its shock gauges would
        # be NaN->0 (biased low) and the overlay would silently fail to mask it. If ANY subject in
        # the decision (latest-timestamp) cross-section lacks a finite spot_close, emit NO gauges so
        # the snapshot fails closed via frontier_overlay_gauge_columns_missing.
        panel = _research_grade_panel(n_subjects=4, n_days=40)
        # full coverage still emits the gauges
        self.assertIn("shock_co_occurrence_index", augment_panel_with_overlay_shock_gauges(panel).columns)
        latest_ts = panel["timestamp_ms"].max()
        holed_subject = panel["subject"].iloc[0]
        holed = panel.copy()
        holed.loc[
            (holed["timestamp_ms"] == latest_ts) & (holed["subject"] == holed_subject), "spot_close"
        ] = np.nan
        out = augment_panel_with_overlay_shock_gauges(holed)
        self.assertNotIn("shock_co_occurrence_index", out.columns)
        self.assertNotIn("co_jump_count_3d", out.columns)
        self.assertTrue(out.equals(holed))

    def test_ignores_existing_return_1_uses_spot_close(self) -> None:
        # A pre-existing (perp-style) return_1 that DIFFERS from spot_close.pct_change() MUST be
        # ignored — the live overlay is research-defined on spot_close. This closes the footgun where
        # the live panel's perp-derived return_1 would silently mis-source the gauge.
        panel = _research_grade_panel(n_subjects=4, n_days=40)
        bogus_ret = panel.groupby("subject")["spot_close"].transform(lambda s: s.pct_change()) + 0.05
        with_bogus = augment_panel_with_overlay_shock_gauges(panel.assign(return_1=bogus_ret))
        from_spot = augment_panel_with_overlay_shock_gauges(panel)
        key = ["subject", "timestamp_ms"]
        a = with_bogus.sort_values(key).reset_index(drop=True)
        b = from_spot.sort_values(key).reset_index(drop=True)
        np.testing.assert_allclose(
            a["shock_co_occurrence_index"].to_numpy(), b["shock_co_occurrence_index"].to_numpy(), rtol=0, atol=1e-12
        )
        np.testing.assert_allclose(
            a["co_jump_count_3d"].to_numpy(), b["co_jump_count_3d"].to_numpy(), rtol=0, atol=1e-12
        )


_SIDECAR_FACTORS = [
    "coinglass_top_trader_long_pct_smooth_5",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
]


class LoadPanelFrontierExtensionTests(unittest.TestCase):
    """The shared _load_panel extends the panel ONLY for an armed frontier:
      * 12-factor sidecars whenever armed (guarded fail-closed import);
      * spot_close + overlay gauges only when the overlay is enabled.
    None / dormant / blocked leave the (panel, audit, filters) tuple byte-identical (default-off)."""

    def _base_panel(self) -> pd.DataFrame:
        dates = pd.date_range("2026-01-01", periods=40, freq="D", tz="UTC")
        rows = []
        for subject in ["L1", "L2", "L3", "S1", "S2"]:
            px = 100.0
            for day in dates:
                px *= 1.01
                rows.append(
                    {
                        "timestamp_ms": int(day.timestamp() * 1000),
                        "subject": subject,
                        "date_utc": day.date().isoformat(),
                        "perp_close": px,  # NB: NO spot_close — the spot fetch must bring it in
                        "perp_quote_volume_usd": 1e7,
                    }
                )
        df = pd.DataFrame(rows)
        # Mirror reality: the live base panel ALWAYS carries a PERP-derived return_1
        # (add_binance_ohlcv_core_features). The overlay must NOT use it — it must use the
        # freshly-fetched spot_close. This exercises that perp-vs-spot mismatch.
        df["return_1"] = df.groupby("subject")["perp_close"].transform(lambda s: s.pct_change())
        return df

    def _fake_sidecar(self, *, blockers=None):
        def _fn(*, panel, symbols, decision_time, args, now_fn):
            out = panel.copy()
            for col in _SIDECAR_FACTORS:
                out[col] = 0.1
            return out, {"status": "ready" if not blockers else "blocked", "blockers": list(blockers or [])}

        return _fn

    def _call(self, frontier, *, import_raises=False, sidecar=None, spot=None):
        import contextlib
        import types
        from unittest import mock
        from enhengclaw.live_trading import mainnet_rebalance_plan_runner as runner

        base = self._base_panel()
        args = types.SimpleNamespace(fixture_panel="", public_market_data=True, symbols="", config="", as_of="now")
        payload = {"market_data": {"daily_limit": 40}}
        spot_frame = spot if spot is not None else base[["subject", "date_utc"]].assign(
            spot_close=base["perp_close"].to_numpy() * 0.999
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                runner, "fetch_public_live_feature_panel", return_value=(base.copy(), {"source": "mock"}, {})
            ))
            if import_raises:
                stack.enter_context(mock.patch.object(
                    runner, "_import_append_live_12factor_sidecars", side_effect=ImportError("no scripts pkg")
                ))
            else:
                stack.enter_context(mock.patch.object(
                    runner, "_import_append_live_12factor_sidecars", return_value=(sidecar or self._fake_sidecar())
                ))
            stack.enter_context(mock.patch.object(runner, "fetch_live_spot_close_frame", return_value=spot_frame))
            return runner._load_panel(
                args=args, payload=payload, frozen_config={},
                market_client_factory=lambda **k: object(), frontier=frontier,
            )

    def test_none_dormant_blocked_leave_panel_untouched(self) -> None:
        blocked = FrontierResolution(status="blocked", enabled=True, overlay_enabled=True, blockers=["frontier_x"])
        for frontier in (None, resolve_frontier_live_plan({}), blocked):
            panel, audit, _ = self._call(frontier)
            self.assertNotIn("coinglass_top_trader_long_pct_smooth_5", panel.columns)
            self.assertNotIn("shock_co_occurrence_index", panel.columns)
            self.assertNotIn("frontier_sidecars", audit)
            self.assertNotIn("overlay_shock_gauges_augmented", audit)

    def test_armed_no_overlay_appends_sidecars_only(self) -> None:
        panel, audit, _ = self._call(_armed_resolution(overlay=False))
        for col in _SIDECAR_FACTORS:
            self.assertIn(col, panel.columns)
        self.assertEqual(audit["frontier_sidecars"]["status"], "ready")
        self.assertNotIn("spot_close", panel.columns)  # spot only fetched when overlay on
        self.assertNotIn("shock_co_occurrence_index", panel.columns)

    def test_armed_overlay_appends_sidecars_spot_and_gauges(self) -> None:
        panel, audit, _ = self._call(_armed_resolution(overlay=True))
        self.assertIn("coinglass_top_trader_long_pct_smooth_5", panel.columns)
        self.assertIn("spot_close", panel.columns)  # merged in by the spot fetch
        self.assertIn("shock_co_occurrence_index", panel.columns)
        self.assertIn("co_jump_count_3d", panel.columns)
        self.assertTrue(audit["overlay_shock_gauges_augmented"])

    def test_armed_overlay_spot_outage_fails_closed(self) -> None:
        # Spot fetch returns empty: even though the base panel carries a perp return_1, the gauge must
        # NOT compute (it requires spot_close) and a blocker must be raised — never a perp approximation.
        empty_spot = pd.DataFrame(columns=["subject", "date_utc", "spot_close"])
        panel, audit, _ = self._call(_armed_resolution(overlay=True), spot=empty_spot)
        self.assertNotIn("spot_close", panel.columns)
        self.assertNotIn("shock_co_occurrence_index", panel.columns)  # gauge fails closed
        self.assertIn("frontier_overlay_spot_close_unavailable", audit["frontier_feature_blockers"])

    def test_sidecar_import_unavailable_fails_closed(self) -> None:
        panel, audit, _ = self._call(_armed_resolution(overlay=True), import_raises=True)
        self.assertIn("sidecar_builder_import_unavailable", audit["frontier_feature_blockers"])
        self.assertNotIn("coinglass_top_trader_long_pct_smooth_5", panel.columns)  # panel unchanged
        self.assertNotIn("spot_close", panel.columns)

    def test_sidecar_blockers_propagate_to_audit(self) -> None:
        panel, audit, _ = self._call(
            _armed_resolution(overlay=False), sidecar=self._fake_sidecar(blockers=["coinglass_x_missing"])
        )
        self.assertIn("coinglass_x_missing", audit["frontier_feature_blockers"])


class SpotCloseFetchTests(unittest.TestCase):
    """fetch_live_spot_close_frame bridges the overlay gauge's spot_close dependency onto the
    perp-only live panel. Symbols without a spot pair must be skipped (fail-closed), not zero-filled."""

    def test_shape_and_skip_missing_pair(self) -> None:
        from enhengclaw.live_trading.market_data import fetch_live_spot_close_frame

        class _Resp:
            def __init__(self, payload):
                self.payload = payload

        class _FakeClient:
            def spot_klines(self, *, symbol, interval, limit, start_time=None, end_time=None):
                if symbol == "BADZZZ":
                    raise RuntimeError("no spot pair")
                base = 1_700_000_000_000
                payload = [
                    [base + i * 86_400_000, "1", "2", "0.5", str(100.0 + i), "10",
                     base + i * 86_400_000 + 86_399_999, "1000", 50, "5", "500"]
                    for i in range(3)
                ]
                return _Resp(payload)

        df = fetch_live_spot_close_frame(client=_FakeClient(), symbols=["BTCUSDT", "ETHUSDT", "BADZZZ"], daily_limit=3)
        self.assertEqual(list(df.columns), ["subject", "date_utc", "spot_close"])
        self.assertEqual(sorted(df["subject"].unique()), ["BTC", "ETH"])  # BADZZZ skipped, not zero-filled
        self.assertEqual(len(df), 6)  # 2 symbols x 3 days
        self.assertTrue((df["spot_close"] > 0).all())

    def test_empty_symbols_returns_typed_empty(self) -> None:
        from enhengclaw.live_trading.market_data import fetch_live_spot_close_frame

        df = fetch_live_spot_close_frame(client=object(), symbols=[], daily_limit=3)
        self.assertEqual(list(df.columns), ["subject", "date_utc", "spot_close"])
        self.assertTrue(df.empty)


if __name__ == "__main__":
    unittest.main()
