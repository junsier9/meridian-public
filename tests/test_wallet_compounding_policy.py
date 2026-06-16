"""Unit + invariance tests for wallet_compounding_policy (equity-tracking compounding +
fail-closed cap stack). Pure functions; no IO. The legacy-path byte-identity (flag off)
is covered by the existing plan-runner tests, not here."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.models import TargetPortfolio, TargetPosition
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.wallet_compounding_policy import (
    DEFAULT_K_ABS,
    deposit_admission_threshold_usdt,
    deposit_impact_tranche_count,
    leverage_policy_blockers,
    reserve_floor_usdt,
    resolve_effective_caps,
    resolve_sizing_equity,
)

_REWARD_CAP = {"reserve_floor_abs_usdt": 300.0, "reserve_floor_ratio": 0.03}


class ReserveFloorTests(unittest.TestCase):
    def test_reserve_floor_is_hybrid_max_abs_ratio(self):
        self.assertAlmostEqual(reserve_floor_usdt(_REWARD_CAP, 10000), 300.0)   # ratio 300 == abs 300
        self.assertAlmostEqual(reserve_floor_usdt(_REWARD_CAP, 40000), 1200.0)  # ratio 1200 > abs 300
        self.assertAlmostEqual(reserve_floor_usdt({"reserve_floor_usdt": 200.0}, 100000), 3000.0)


class SizingEquityTests(unittest.TestCase):
    def test_full_compounding_tracks_realized_profit_on_upside(self):
        cap = {**_REWARD_CAP, "principal_baseline_usdt": 10000, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        # reserve = max(300, 360) = 360; E = (10000-360) + 1.0*2000 = 11640
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["equity"], 11640.0)

    def test_partial_compounding_banks_part_of_profit(self):
        cap = {**_REWARD_CAP, "principal_baseline_usdt": 10000, "compounding_fraction": 0.5}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertAlmostEqual(r["equity"], 10640.0)  # (10000-360) + 0.5*2000

    def test_drawdown_de_risks_to_current_wallet_regardless_of_f(self):
        # Corrected formula: on a drawdown E tracks wallet DOWN (anti-martingale),
        # not anchored to principal. f does not matter on the downside.
        cap = {**_REWARD_CAP, "principal_baseline_usdt": 10000, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=8000)
        # reserve = max(300, 240) = 300; E = (min(8000,10000)-300) + 0 = 7700
        self.assertAlmostEqual(r["equity"], 7700.0)
        self.assertLess(r["equity"], 10000 - 300)  # strictly below a principal-anchored book

    def test_bootstrap_principal_unset_reduces_to_wallet_minus_reserve(self):
        r = resolve_sizing_equity(capital=dict(_REWARD_CAP), wallet_balance=10000)
        self.assertAlmostEqual(r["equity"], 9700.0)          # profit 0 => wallet - reserve
        self.assertAlmostEqual(r["principal_baseline"], 10000.0)

    def test_reserve_honored_when_principal_below_reserve(self):
        # Adversarial finding: with a stale-low pinned principal < reserve, the old formula
        # let E exceed wallet - reserve. The corrected formula caps E at wallet - reserve.
        cap = {**_REWARD_CAP, "principal_baseline_usdt": 200, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=10000.0)
        reserve = max(300.0, 0.03 * 10000.0)               # 332.8776
        self.assertLessEqual(r["equity"], 10000.0 - reserve + 1e-6)
        self.assertAlmostEqual(r["equity"], 10000.0 - reserve, places=4)

    def test_initial_capital_usdt_is_accepted_as_explicit_anchor_alias(self):
        # The clearer alias must behave identically to the legacy principal_baseline_usdt key.
        cap = {**_REWARD_CAP, "initial_capital_usdt": 10000, "compounding_fraction": 0.5}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["equity"], 10640.0)        # (10000-360) + 0.5*2000
        self.assertAlmostEqual(r["principal_baseline"], 10000.0)

    def test_both_anchor_keys_agree_is_ok(self):
        cap = {**_REWARD_CAP, "initial_capital_usdt": 10000,
               "principal_baseline_usdt": 10000, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["equity"], 11640.0)

    def test_conflicting_anchor_keys_fail_closed(self):
        cap = {**_REWARD_CAP, "initial_capital_usdt": 10000,
               "principal_baseline_usdt": 9000, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertFalse(r["ok"])
        self.assertIn("principal_anchor_keys_conflict", r["blockers"])
        self.assertEqual(r["equity"], 0.0)

    def test_partial_compounding_without_anchor_fails_closed(self):
        # Guard: f<1 signals anchored intent; an unset anchor must NOT silently follow the wallet.
        cap = {**_REWARD_CAP, "compounding_fraction": 0.5}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertFalse(r["ok"])
        self.assertIn("principal_anchor_required_for_partial_compounding", r["blockers"])
        self.assertEqual(r["equity"], 0.0)

    def test_full_compounding_without_anchor_bootstraps_no_block(self):
        # f==1 is the documented follow-wallet regime; an unset anchor is fine (guard inert).
        cap = {**_REWARD_CAP, "compounding_fraction": 1.0}
        r = resolve_sizing_equity(capital=cap, wallet_balance=12000)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["principal_baseline"], 12000.0)
        self.assertAlmostEqual(r["equity"], 11640.0)        # 12000 - max(300, 360)

    def test_wallet_unreadable_fails_closed(self):
        r = resolve_sizing_equity(capital=dict(_REWARD_CAP), wallet_balance=None)
        self.assertFalse(r["ok"])
        self.assertIn("wallet_balance_unreadable_or_negative", r["blockers"])
        self.assertFalse(resolve_sizing_equity(capital=dict(_REWARD_CAP), wallet_balance=-5)["ok"])


class EffectiveCapsTests(unittest.TestCase):
    def test_abs_ceiling_is_a_min_clamp_not_a_floor(self):
        eff = resolve_effective_caps(
            equity=30000, wallet_balance=10000,
            capital={"leverage_mult": 2.0},
            risk={"abs_max_gross_notional_usdt": 20000},
        )
        # book_equity 60000, op 23000, abs 20000 -> clamped DOWN to 20000 (legacy max() would lift)
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 20000.0)
        self.assertAlmostEqual(eff["risk_caps"]["abs_max_gross_notional_usdt"], 20000.0)

    def test_default_abs_ceiling_is_k_abs_times_wallet(self):
        eff = resolve_effective_caps(
            equity=100000, wallet_balance=10000, capital={"leverage_mult": 2.0}, risk={},
        )
        self.assertAlmostEqual(eff["diagnostics"]["abs_ceiling_usdt"], DEFAULT_K_ABS * 10000)
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 23000.0)  # op binds

    def test_growth_limiter_caps_per_cycle_increase(self):
        eff = resolve_effective_caps(
            equity=40000, wallet_balance=40000,
            capital={"leverage_mult": 2.0, "max_book_growth_per_cycle": 0.15},
            risk={"abs_max_gross_notional_usdt": 160000},
            applied_book_prev=20000,
        )
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 23000.0)  # 20000*1.15
        self.assertTrue(eff["diagnostics"]["growth_clamped"])

    def test_deposit_override_relaxes_growth_within_abs(self):
        eff = resolve_effective_caps(
            equity=40000, wallet_balance=40000,
            capital={"leverage_mult": 2.0, "max_book_growth_per_cycle": 0.15},
            risk={"abs_max_gross_notional_usdt": 160000},
            applied_book_prev=20000, deposit_growth_override=0.45,
        )
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 29000.0)  # 20000*1.45

    def test_abs_ceiling_inviolable_even_under_deposit_override(self):
        eff = resolve_effective_caps(
            equity=1_000_000, wallet_balance=40000,
            capital={"leverage_mult": 2.0, "max_book_growth_per_cycle": 0.15},
            risk={"abs_max_gross_notional_usdt": 50000},
            applied_book_prev=40000, deposit_growth_override=100.0,
        )
        self.assertLessEqual(eff["risk_caps"]["max_gross_notional_usdt"], 50000.0 + 1e-6)

    def test_unresolved_abs_ceiling_fails_closed(self):
        eff = resolve_effective_caps(
            equity=10000, wallet_balance=0, capital={"leverage_mult": 2.0}, risk={},
        )
        self.assertIn("abs_max_gross_notional_unresolved", eff["blockers"])
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 0.0)

    def test_per_symbol_cap_is_min_of_weight_and_absolute(self):
        eff = resolve_effective_caps(
            equity=10000, wallet_balance=10000,
            capital={"leverage_mult": 2.0, "max_symbol_weight_cap": 0.35},
            risk={"abs_max_gross_notional_usdt": 40000, "abs_max_symbol_notional_usdt": 5000},
        )
        self.assertAlmostEqual(eff["risk_caps"]["max_symbol_notional_usdt"], 5000.0)  # abs binds < 7000

    def test_non_positive_book_emits_blocker_on_zero_equity(self):
        # Fail-closed: a 0 book (here equity=0) reads as "no cap" in risk_gate, so it MUST
        # surface a blocker instead of silently bypassing the operational cap.
        eff = resolve_effective_caps(
            equity=0, wallet_balance=10000,
            capital={"leverage_mult": 2.0}, risk={"abs_max_gross_notional_usdt": 40000},
        )
        self.assertIn("resolved_book_non_positive", eff["blockers"])
        self.assertAlmostEqual(eff["risk_caps"]["max_gross_notional_usdt"], 0.0)

    def test_non_positive_book_emits_blocker_on_zero_wallet_with_pinned_abs(self):
        # Adversarial finding #5: static path, stale/zero wallet, pinned (loose) abs ceiling.
        eff = resolve_effective_caps(
            equity=5000, wallet_balance=0,
            capital={"leverage_mult": 2.0}, risk={"abs_max_gross_notional_usdt": 30000},
        )
        self.assertIn("resolved_book_non_positive", eff["blockers"])

    def test_non_finite_leverage_mult_collapses_to_blocked_not_silent(self):
        # Adversarial finding #4 root: a non-finite leverage_mult must not silently size a book.
        eff = resolve_effective_caps(
            equity=float("inf"), wallet_balance=10000,
            capital={"leverage_mult": float("inf")}, risk={},
        )
        # _finite guards eq/lev -> book collapses to 0 -> blocked, never an uncapped NaN book.
        self.assertIn("resolved_book_non_positive", eff["blockers"])

    def test_k_abs_cannot_be_loosened_above_red_line(self):
        eff = resolve_effective_caps(
            equity=1e9, wallet_balance=10000,
            capital={"leverage_mult": 2.0}, risk={"abs_max_gross_leverage": 12.0},
        )
        self.assertAlmostEqual(eff["diagnostics"]["k_abs"], DEFAULT_K_ABS)             # clamped to 4
        self.assertAlmostEqual(eff["diagnostics"]["abs_ceiling_usdt"], 4.0 * 10000)

    def test_stale_high_abs_pin_clamped_to_wallet_relative(self):
        eff = resolve_effective_caps(
            equity=1e9, wallet_balance=10000,
            capital={"leverage_mult": 2.0}, risk={"abs_max_gross_notional_usdt": 500000},
        )
        # explicit 500000 pin must not exceed k_abs*wallet = 40000
        self.assertAlmostEqual(eff["diagnostics"]["abs_ceiling_usdt"], 40000.0)


class LeveragePolicyTests(unittest.TestCase):
    def test_unreadable_or_below_min_fails_closed(self):
        self.assertTrue(leverage_policy_blockers(None, symbol="BTCUSDT", max_allowed_leverage=2))
        self.assertTrue(leverage_policy_blockers(0, symbol="BTCUSDT", max_allowed_leverage=2))
        self.assertTrue(leverage_policy_blockers("x", symbol="BTCUSDT", max_allowed_leverage=2))

    def test_within_policy_passes_and_above_cap_blocks(self):
        self.assertEqual(leverage_policy_blockers(1, symbol="BTCUSDT", max_allowed_leverage=2), [])
        self.assertEqual(leverage_policy_blockers(2, symbol="BTCUSDT", max_allowed_leverage=2), [])
        blk = leverage_policy_blockers(3, symbol="BTCUSDT", max_allowed_leverage=2)
        self.assertTrue(blk and "leverage_above_max" in blk[0])


class DepositAdmissionTests(unittest.TestCase):
    def test_admission_threshold_hybrid(self):
        self.assertAlmostEqual(deposit_admission_threshold_usdt({}, 10000), 500.0)
        self.assertAlmostEqual(deposit_admission_threshold_usdt({}, 20000), 1000.0)

    def test_impact_one_shot_for_deep_symbol(self):
        out = deposit_impact_tranche_count(
            per_symbol_increment_usdt={"BTCUSDT": 2500.0},
            adv_usdt_by_symbol={"BTCUSDT": 100_000_000.0},
        )
        self.assertEqual(out["tranche_count"], 1)
        self.assertEqual(out["blockers"], [])

    def test_impact_splits_when_increment_large_vs_adv(self):
        out = deposit_impact_tranche_count(
            per_symbol_increment_usdt={"ALT": 50000.0},
            adv_usdt_by_symbol={"ALT": 500000.0},
            max_participation=0.02,
        )
        self.assertEqual(out["tranche_count"], 5)  # ceil(50000 / (0.02*500000))
        self.assertEqual(out["binding_symbol"], "ALT")

    def test_impact_missing_adv_fails_closed(self):
        out = deposit_impact_tranche_count(
            per_symbol_increment_usdt={"X": 1000.0}, adv_usdt_by_symbol={},
        )
        self.assertTrue(any(b.startswith("deposit_impact_adv_missing") for b in out["blockers"]))


def _portfolio(*, allocated: float, gross_weight: float, symbol_notional: float) -> TargetPortfolio:
    return TargetPortfolio(
        portfolio_id="p1", decision_id="d1", strategy_label="fixture",
        allocated_capital_usdt=allocated, portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0, target_gross_weight=gross_weight,
        target_net_weight=gross_weight, status="ok",
        positions=[TargetPosition(
            subject="BTC", usdm_symbol="BTCUSDT", side="long", score=1.0,
            target_weight=gross_weight, target_notional_usdt=symbol_notional,
            previous_target_weight=0.0, delta_target_weight=gross_weight,
            raw_short_multiplier=1.0, portfolio_drawdown_multiplier=1.0,
            selection_reason="top_long",
        )],
    )


class RiskGateV2PropagationTests(unittest.TestCase):
    def test_zero_v2_cap_with_positive_allocation_is_blocked_not_skipped(self):
        # THE BLOCKER FIX: caps collapse to 0.0 (read as "no cap") but the portfolio still
        # carries a positive raw allocation; the propagated wallet_v2 blocker must hard-block.
        config = {
            "capital": {"allocated_capital_usdt": 11000.0},
            "risk": {
                "trading_enabled": False,
                "max_allocated_capital_usdt": 0.0,        # 0 => skipped by the legacy comparison
                "max_gross_notional_usdt": 0.0,
                "abs_max_gross_notional_usdt": 30000.0,   # loose ceiling, would not catch it
                "_wallet_v2_blockers": ["resolved_book_non_positive"],
            },
        }
        result = evaluate_risk_gate(
            _portfolio(allocated=11000.0, gross_weight=1.0, symbol_notional=11000.0),
            mode="plan_only", config=config,
        )
        self.assertFalse(result.passed)
        self.assertIn("wallet_v2:resolved_book_non_positive", result.blockers)

    def test_absolute_gross_ceiling_blocks_oversized_book(self):
        config = {
            "capital": {"allocated_capital_usdt": 11000.0},
            "risk": {"trading_enabled": False, "abs_max_gross_notional_usdt": 5000.0},
        }
        result = evaluate_risk_gate(
            _portfolio(allocated=11000.0, gross_weight=1.0, symbol_notional=11000.0),
            mode="plan_only", config=config,
        )
        self.assertFalse(result.passed)
        self.assertIn("gross_notional_exceeds_absolute_ceiling", result.blockers)

    def test_legacy_payload_without_v2_keys_is_unaffected(self):
        # Regression invariance: absent abs_*/_wallet_v2_* keys => no new blockers.
        config = {
            "capital": {"allocated_capital_usdt": 100.0},
            "risk": {
                "trading_enabled": False,
                "max_allocated_capital_usdt": 100.0,
                "max_gross_notional_usdt": 100.0,
                "max_symbol_notional_usdt": 20.0,
            },
        }
        result = evaluate_risk_gate(
            _portfolio(allocated=100.0, gross_weight=0.1, symbol_notional=10.0),
            mode="plan_only", config=config,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.blockers, [])


if __name__ == "__main__":
    unittest.main()
