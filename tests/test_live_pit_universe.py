from __future__ import annotations

import argparse
import copy
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading import mainnet_rebalance_plan_runner as runner
from enhengclaw.live_trading.live_pit_universe import (
    LIVE_UNIVERSE_SCHEMA,
    MODE_FIXED,
    MODE_PIT_ROLLING,
    UNIVERSE_CHANGE_LOG_SCHEMA,
    apply_live_pit_universe,
    build_universe_change_log,
    evaluate_universe_churn_gate,
    find_prior_live_universe_artifact,
    live_selection_mode,
    resolve_live_universe_policy,
    write_universe_change_log,
)


_START = datetime(2026, 3, 1, tzinfo=UTC)


def _panel_from_daily(daily_qv_by_symbol: dict[str, list[float]]) -> pd.DataFrame:
    """Build a [timestamp_ms, subject, usdm_symbol, perp_close, perp_quote_volume_usd] panel
    from per-symbol daily quote-volume sequences (one entry per UTC day from _START)."""
    rows: list[dict[str, object]] = []
    for symbol, volumes in daily_qv_by_symbol.items():
        for day, quote_volume in enumerate(volumes):
            timestamp_ms = int((_START + timedelta(days=day)).timestamp() * 1000)
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "subject": symbol[:-4] if symbol.endswith("USDT") else symbol,
                    "usdm_symbol": symbol,
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": float(quote_volume),
                }
            )
    return pd.DataFrame(rows)


def _flat_candidates(count: int, *, days: int = 40, base: float = 1_000_000_000.0) -> dict[str, list[float]]:
    """`count` candidates with strictly-decreasing-by-index, flat-over-time liquidity."""
    return {f"C{idx:02d}USDT": [base - idx * 1_000_000.0] * days for idx in range(count)}


def _pit_config(candidate_symbols: list[str], **overrides: object) -> dict[str, object]:
    policy = {
        "live_selection_mode": MODE_PIT_ROLLING,
        "top_n": 20,
        "coverage_threshold": 0.85,
        "lookback_days": 30,
        "hysteresis_band": 0,
        "candidate_symbols": candidate_symbols,
    }
    policy.update(overrides)
    return {"universe_policy": policy}


class LiveUniversePolicyResolutionTests(unittest.TestCase):
    def test_absent_key_resolves_fixed(self) -> None:
        self.assertEqual(live_selection_mode({}), MODE_FIXED)
        self.assertTrue(resolve_live_universe_policy({}).is_fixed)

    def test_research_selection_mode_alone_does_not_auto_flip(self) -> None:
        # The pinned frozen config carries selection_mode=rolling_quote_volume + lookback_days=30
        # but NO live_selection_mode. Honouring it would silently flip live behaviour; it must not.
        frozen_like = {
            "universe_policy": {
                "selection_mode": "rolling_quote_volume",
                "lookback_days": 30,
                "top_n": 20,
                "preset": "binance_pit_top_mid_20",
            }
        }
        self.assertEqual(live_selection_mode(frozen_like), MODE_FIXED)
        self.assertTrue(resolve_live_universe_policy(frozen_like).is_fixed)

    def test_pit_rolling_resolution_is_validated_and_bound(self) -> None:
        resolution = resolve_live_universe_policy(_pit_config(list(_flat_candidates(25))))
        self.assertTrue(resolution.is_pit_rolling)
        self.assertEqual(resolution.top_n, 20)
        self.assertEqual(len(resolution.candidate_symbols), 25)
        self.assertEqual(resolution.candidate_symbols, sorted(resolution.candidate_symbols))
        self.assertIsNotNone(resolution.policy_binding)

    def test_candidate_pool_below_top_n_blocks(self) -> None:
        resolution = resolve_live_universe_policy(_pit_config(list(_flat_candidates(10))))
        self.assertTrue(resolution.is_blocked)
        self.assertTrue(any("candidate_symbols_below_top_n" in blocker for blocker in resolution.blockers))

    def test_invalid_parameters_block(self) -> None:
        resolution = resolve_live_universe_policy(
            _pit_config(list(_flat_candidates(25)), coverage_threshold=1.5, lookback_days=0, top_n=-1)
        )
        self.assertTrue(resolution.is_blocked)
        self.assertTrue(any("coverage_threshold_out_of_range" in b for b in resolution.blockers))
        self.assertTrue(any("lookback_days_not_positive" in b for b in resolution.blockers))

    def test_invalid_numeric_string_blocks_instead_of_defaulting(self) -> None:
        resolution = resolve_live_universe_policy(
            _pit_config(list(_flat_candidates(25)), top_n="not-an-int", coverage_threshold="nan")
        )
        self.assertTrue(resolution.is_blocked)
        self.assertTrue(any("universe_top_n_invalid" in blocker for blocker in resolution.blockers))
        self.assertTrue(any("universe_coverage_threshold_not_finite" in blocker for blocker in resolution.blockers))

    def test_candidate_symbols_must_be_explicit_unique_yaml_list(self) -> None:
        string_resolution = resolve_live_universe_policy(_pit_config("BTCUSDT,ETHUSDT"))  # type: ignore[arg-type]
        self.assertTrue(string_resolution.is_blocked)
        self.assertIn("universe_candidate_symbols_must_be_yaml_list", string_resolution.blockers)

        duplicate_resolution = resolve_live_universe_policy(_pit_config(["BTCUSDT", "BTCUSDT"] * 11))
        self.assertTrue(duplicate_resolution.is_blocked)
        self.assertIn("universe_candidate_symbols_duplicate:BTCUSDT", duplicate_resolution.blockers)

    def test_non_usdt_candidate_blocks(self) -> None:
        candidates = list(_flat_candidates(20)) + ["BTCUSDC"]
        resolution = resolve_live_universe_policy(_pit_config(candidates))
        self.assertTrue(resolution.is_blocked)
        self.assertTrue(any("not_usdt_perp" in blocker for blocker in resolution.blockers))

    def test_churn_gate_policy_is_validated_and_bound(self) -> None:
        candidates = list(_flat_candidates(25))
        gate = {
            "enabled": True,
            "max_entered_count": 4,
            "max_exited_count": 4,
            "max_churn_count": 8,
            "max_churn_ratio": 0.4,
            "bootstrap_reference_symbols": candidates[:20],
        }
        resolution = resolve_live_universe_policy(_pit_config(candidates, churn_gate=gate))
        self.assertTrue(resolution.is_pit_rolling)
        self.assertEqual(resolution.churn_gate["max_entered_count"], 4)
        self.assertEqual(resolution.churn_gate["bootstrap_reference_symbols"], sorted(candidates[:20]))

    def test_churn_gate_reference_must_be_admitted_top_n(self) -> None:
        candidates = list(_flat_candidates(25))
        gate = {
            "enabled": True,
            "max_churn_count": 8,
            "bootstrap_reference_symbols": ["BTCUSDT", "ETHUSDT"],
        }
        resolution = resolve_live_universe_policy(_pit_config(candidates, churn_gate=gate))
        self.assertTrue(resolution.is_blocked)
        self.assertTrue(any("bootstrap_reference_size_not_top_n" in b for b in resolution.blockers))
        self.assertTrue(any("bootstrap_reference_not_candidate" in b for b in resolution.blockers))


class ApplyLivePitUniverseTests(unittest.TestCase):
    def test_selects_top_n_and_drops_lowest_liquidity(self) -> None:
        candidates = _flat_candidates(22)
        resolution = resolve_live_universe_policy(_pit_config(list(candidates)))
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)

        self.assertEqual(result.blockers, [])
        self.assertEqual(result.artifact["active_count"], 20)
        self.assertTrue(result.artifact["size_invariant_ok"])
        dropped = set(candidates) - set(result.artifact["active_symbols"])
        # The two least-liquid (highest index) candidates are excluded.
        self.assertEqual(dropped, {"C20USDT", "C21USDT"})
        self.assertEqual(result.artifact["schema"], LIVE_UNIVERSE_SCHEMA)
        self.assertEqual(result.artifact["status"], "ok")

    def test_decision_row_has_exactly_top_n_active(self) -> None:
        candidates = _flat_candidates(25)
        resolution = resolve_live_universe_policy(_pit_config(list(candidates)))
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        decision_ts = int(pd.to_numeric(result.panel["timestamp_ms"], errors="coerce").max())
        decision_rows = result.panel.loc[
            pd.to_numeric(result.panel["timestamp_ms"], errors="coerce").eq(decision_ts)
        ]
        active = decision_rows.loc[decision_rows["universe_active"].astype(bool)]
        # size==top_n holds so the dth60 q90 thresholds (derived over a top-20 universe) stay valid.
        self.assertEqual(len(active), 20)
        ranks = sorted(int(value) for value in active["universe_rank"].tolist())
        self.assertEqual(ranks, list(range(1, 21)))

    def test_no_look_ahead_membership_is_point_in_time(self) -> None:
        # LATEUSDT is illiquid early and only becomes liquid on the last 2 days. With a 1-day
        # lookback its early rows must NOT be selected (no future leakage); late rows are.
        days = 6
        candidates = {
            "AAAUSDT": [1_000.0] * days,
            "BBBUSDT": [900.0, 900.0, 900.0, 900.0, 1.0, 1.0],
            "LATEUSDT": [1.0, 1.0, 1.0, 1.0, 5_000.0, 5_000.0],
        }
        resolution = resolve_live_universe_policy(
            _pit_config(list(candidates), top_n=2, coverage_threshold=1.0, lookback_days=1)
        )
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        panel = result.panel
        early_ts = int((_START + timedelta(days=0)).timestamp() * 1000)
        late_ts = int((_START + timedelta(days=days - 1)).timestamp() * 1000)
        early_active = set(
            panel.loc[
                pd.to_numeric(panel["timestamp_ms"], errors="coerce").eq(early_ts) & panel["universe_active"].astype(bool),
                "usdm_symbol",
            ]
        )
        late_active = set(
            panel.loc[
                pd.to_numeric(panel["timestamp_ms"], errors="coerce").eq(late_ts) & panel["universe_active"].astype(bool),
                "usdm_symbol",
            ]
        )
        self.assertNotIn("LATEUSDT", early_active)  # no look-ahead
        self.assertIn("LATEUSDT", late_active)  # picked once liquid, PIT

    def test_size_gate_blocks_below_top_n(self) -> None:
        # Only 1 of 3 candidates has any liquidity (others zero => never eligible), so the
        # decision row cannot reach top_n=3 => fail closed with active_size_not_3.
        candidates = {
            "AAAUSDT": [1_000.0] * 35,
            "BBBUSDT": [0.0] * 35,
            "CCCUSDT": [0.0] * 35,
        }
        resolution = resolve_live_universe_policy(
            _pit_config(list(candidates), top_n=3, coverage_threshold=0.85, lookback_days=30)
        )
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        self.assertTrue(any(blocker.startswith("active_size_not_3:") for blocker in result.blockers))
        self.assertFalse(result.artifact["size_invariant_ok"])

    def test_gate_binds_to_supplied_decision_row(self) -> None:
        # The gate/binding follow decision_time_ms: an early row (inside the partial-lookback
        # warmup => coverage below threshold => <top_n eligible) fails closed, while the latest
        # bar (full 30d window) passes — proving "决策时 size==20" binds the scored row, not just
        # the latest bar.
        candidates = _flat_candidates(22, days=40)
        resolution = resolve_live_universe_policy(_pit_config(list(candidates)))
        panel = _panel_from_daily(candidates)
        early_ts = int((_START + timedelta(days=3)).timestamp() * 1000)

        gated_early = apply_live_pit_universe(panel, resolution=resolution, decision_time_ms=early_ts)
        self.assertTrue(any(b.startswith("active_size_not_20:") for b in gated_early.blockers))
        self.assertEqual(gated_early.artifact["decision_time_ms"], early_ts)

        gated_latest = apply_live_pit_universe(panel, resolution=resolution)  # default => latest bar
        self.assertEqual(gated_latest.blockers, [])
        self.assertEqual(gated_latest.artifact["active_count"], 20)

    def test_new_symbol_not_admitted_fails_closed(self) -> None:
        candidates = _flat_candidates(22)
        resolution = resolve_live_universe_policy(_pit_config(list(candidates)))
        # A drift symbol NOT in the admitted allowlist appears in the panel ranking first.
        drift = _panel_from_daily({"XXXUSDT": [9_000_000_000.0] * 40})
        panel = pd.concat([_panel_from_daily(candidates), drift], ignore_index=True)
        result = apply_live_pit_universe(panel, resolution=resolution)
        self.assertIn("new_symbol_not_admitted:XXXUSDT", result.blockers)

    def test_binding_is_deterministic_and_membership_sensitive(self) -> None:
        candidates = _flat_candidates(22)
        resolution = resolve_live_universe_policy(_pit_config(list(candidates)))
        first = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        second = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        self.assertEqual(first.artifact["universe_binding"], second.artifact["universe_binding"])

        # Swapping liquidity so a different symbol enters changes the binding.
        shuffled = dict(candidates)
        shuffled["C21USDT"] = [9_000_000_000.0] * 40  # least-liquid candidate becomes most liquid
        shuffled_result = apply_live_pit_universe(_panel_from_daily(shuffled), resolution=resolution)
        self.assertNotEqual(first.artifact["universe_binding"], shuffled_result.artifact["universe_binding"])
        self.assertIn("C21USDT", shuffled_result.artifact["active_symbols"])


class HysteresisTests(unittest.TestCase):
    def _crossing_panel(self) -> dict[str, list[float]]:
        # A always rank1. B leads C for days 0-5, then C overtakes B for days 6-11 (lookback=1).
        return {
            "AAAUSDT": [1_000.0] * 12,
            "BBBUSDT": [100.0] * 6 + [10.0] * 6,
            "CCCUSDT": [10.0] * 6 + [100.0] * 6,
        }

    def test_band_zero_churns_membership(self) -> None:
        candidates = self._crossing_panel()
        resolution = resolve_live_universe_policy(
            _pit_config(list(candidates), top_n=2, coverage_threshold=1.0, lookback_days=1, hysteresis_band=0)
        )
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        # On the last day C outranks B => without a band, B is churned out.
        self.assertEqual(set(result.artifact["active_symbols"]), {"AAAUSDT", "CCCUSDT"})
        self.assertEqual(result.artifact["active_count"], 2)

    def test_band_retains_incumbent_and_keeps_size(self) -> None:
        candidates = self._crossing_panel()
        resolution = resolve_live_universe_policy(
            _pit_config(list(candidates), top_n=2, coverage_threshold=1.0, lookback_days=1, hysteresis_band=1)
        )
        result = apply_live_pit_universe(_panel_from_daily(candidates), resolution=resolution)
        # B is an incumbent slipping to rank 3 <= top_n + band; hysteresis retains it (no churn).
        self.assertEqual(set(result.artifact["active_symbols"]), {"AAAUSDT", "BBBUSDT"})
        self.assertEqual(result.artifact["active_count"], 2)
        self.assertEqual(result.blockers, [])


class LoadPanelWiringTests(unittest.TestCase):
    """The wiring chokepoint: _load_panel is fixed (byte-identical) unless pit_rolling is armed."""

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(fixture_panel="", symbols="", public_market_data=True, as_of="now")

    def _baseline_panel(self) -> pd.DataFrame:
        # A panel as fetch_public_live_feature_panel would return: already carries the fixed
        # per-day universe marking. Two timestamps, 3 symbols.
        rows = []
        for day in range(2):
            ts = int((_START + timedelta(days=day)).timestamp() * 1000)
            for symbol, qv, active, rank in (
                ("BTCUSDT", 100.0, True, 1.0),
                ("ETHUSDT", 90.0, True, 2.0),
                ("DOGEUSDT", 80.0, True, 3.0),
            ):
                rows.append(
                    {
                        "timestamp_ms": ts,
                        "subject": symbol[:-4],
                        "usdm_symbol": symbol,
                        "perp_close": 100.0,
                        "perp_quote_volume_usd": qv,
                        "universe_active": active,
                        "universe_rank": rank,
                        "liquidity_bucket": "top_liquidity",
                    }
                )
        return pd.DataFrame(rows)

    def test_fixed_mode_load_panel_is_byte_identical(self) -> None:
        baseline = self._baseline_panel()
        captured: dict[str, object] = {}

        def fake_fetch(*, client, config, symbols, daily_limit, four_hour_limit):
            captured["symbols"] = list(symbols)
            return baseline.copy(), {"source": "fake"}, {"BTCUSDT": {}}

        payload = {"market_data": {"public_data_enabled": True, "symbols": "BTCUSDT,ETHUSDT,DOGEUSDT"}}
        with mock.patch.object(runner, "fetch_public_live_feature_panel", fake_fetch):
            panel, audit, _filters = runner._load_panel(
                args=self._args(),
                payload=payload,
                frozen_config={"universe_policy": {"selection_mode": "rolling_quote_volume", "top_n": 20}},
                market_client_factory=lambda base_url: object(),
                frontier=None,
            )
        # No PIT marking, no new audit keys => byte-for-byte baseline.
        pd.testing.assert_frame_equal(panel, baseline)
        self.assertNotIn("universe_blockers", audit)
        self.assertNotIn("live_universe", audit)
        self.assertEqual(captured["symbols"], ["BTCUSDT", "ETHUSDT", "DOGEUSDT"])

    def test_live_config_universe_policy_overrides_frozen_research_policy(self) -> None:
        candidates = _flat_candidates(22)
        candidate_panel = _panel_from_daily(candidates)
        captured: dict[str, object] = {}

        def fake_fetch(*, client, config, symbols, daily_limit, four_hour_limit):
            captured["symbols"] = list(symbols)
            captured["universe_policy"] = dict(config.get("universe_policy") or {})
            return candidate_panel.copy(), {"source": "fake"}, {}

        live_policy = dict(_pit_config(list(candidates))["universe_policy"])
        payload = {
            "market_data": {"public_data_enabled": True, "symbols": "IGNORED_IN_PIT"},
            "universe_policy": live_policy,
        }
        frozen_config = {
            "universe_policy": {
                "selection_mode": "rolling_quote_volume",
                "top_n": 20,
                "preset": "binance_pit_top_mid_20",
            }
        }
        with mock.patch.object(runner, "fetch_public_live_feature_panel", fake_fetch):
            _panel, audit, _filters = runner._load_panel(
                args=self._args(),
                payload=payload,
                frozen_config=frozen_config,
                market_client_factory=lambda base_url: object(),
                frontier=None,
            )

        self.assertEqual(captured["symbols"], sorted(candidates))
        self.assertEqual(captured["universe_policy"]["live_selection_mode"], MODE_PIT_ROLLING)
        self.assertEqual(audit["universe_blockers"], [])
        self.assertEqual(audit["live_universe"]["active_count"], 20)

    def test_pit_rolling_mode_load_panel_remarks_and_wires_artifact(self) -> None:
        candidates = _flat_candidates(22)
        candidate_panel = _panel_from_daily(candidates)
        captured: dict[str, object] = {}

        def fake_fetch(*, client, config, symbols, daily_limit, four_hour_limit):
            captured["symbols"] = list(symbols)
            return candidate_panel.copy(), {"source": "fake"}, {}

        payload = {"market_data": {"public_data_enabled": True, "symbols": "IGNORED_IN_PIT"}}
        frozen_config = _pit_config(list(candidates))
        with mock.patch.object(runner, "fetch_public_live_feature_panel", fake_fetch):
            panel, audit, _filters = runner._load_panel(
                args=self._args(),
                payload=payload,
                frozen_config=frozen_config,
                market_client_factory=lambda base_url: object(),
                frontier=None,
            )
        # pit_rolling fetches the hash-pinned candidate pool, not payload market_data.symbols.
        self.assertEqual(captured["symbols"], sorted(candidates))
        self.assertEqual(audit["universe_blockers"], [])
        self.assertEqual(audit["live_universe"]["active_count"], 20)
        self.assertTrue(audit["live_universe"]["size_invariant_ok"])
        self.assertIn("universe_binding", audit["live_universe"])
        # The panel was re-marked by the PIT selector (not the fixed per-day marking).
        from enhengclaw.live_trading.live_pit_universe import PIT_SELECTION_RULE

        self.assertTrue((panel["universe_selection_rule"] == PIT_SELECTION_RULE).all())
        decision_ts = int(pd.to_numeric(panel["timestamp_ms"], errors="coerce").max())
        decision_active = panel.loc[
            pd.to_numeric(panel["timestamp_ms"], errors="coerce").eq(decision_ts) & panel["universe_active"].astype(bool)
        ]
        self.assertEqual(len(decision_active), 20)

    def test_blocked_policy_surfaces_universe_blockers(self) -> None:
        candidate_panel = _panel_from_daily(_flat_candidates(5))

        def fake_fetch(*, client, config, symbols, daily_limit, four_hour_limit):
            return candidate_panel.copy(), {"source": "fake"}, {}

        payload = {"market_data": {"public_data_enabled": True}}
        # candidate pool (5) < top_n (20) => blocked policy.
        frozen_config = _pit_config(list(_flat_candidates(5)))
        with mock.patch.object(runner, "fetch_public_live_feature_panel", fake_fetch):
            _panel, audit, _filters = runner._load_panel(
                args=self._args(),
                payload=payload,
                frozen_config=frozen_config,
                market_client_factory=lambda base_url: object(),
                frontier=None,
            )
        self.assertTrue(any("candidate_symbols_below_top_n" in b for b in audit["universe_blockers"]))
        self.assertEqual(audit["live_universe"]["status"], "blocked")


class UniverseChangeLogTests(unittest.TestCase):
    """build_universe_change_log is a PURE read-only audit diff (never fed back to selection)."""

    def test_no_prior_marks_all_entered(self) -> None:
        current = {
            "active_symbols": ["BUSDT", "AUSDT"],
            "decision_time_ms": 200,
            "decision_date_utc": "2026-03-02",
            "status": "ok",
            "universe_binding": "sha-cur",
        }
        log = build_universe_change_log(current=current, prior=None)
        self.assertFalse(log["has_prior"])
        self.assertEqual(log["entered"], ["AUSDT", "BUSDT"])  # sorted
        self.assertEqual(log["exited"], [])
        self.assertEqual(log["retained"], [])
        self.assertEqual(log["churn_count"], 2)
        self.assertEqual(log["churn_ratio"], 1.0)
        self.assertEqual(log["schema"], UNIVERSE_CHANGE_LOG_SCHEMA)

    def test_diff_entered_exited_retained(self) -> None:
        prior = {
            "active_symbols": ["AUSDT", "BUSDT", "CUSDT"],
            "decision_time_ms": 100,
            "decision_date_utc": "2026-03-01",
            "status": "ok",
            "universe_binding": "sha-prior",
        }
        current = {
            "active_symbols": ["BUSDT", "CUSDT", "DUSDT"],
            "decision_time_ms": 200,
            "decision_date_utc": "2026-03-02",
            "status": "ok",
            "universe_binding": "sha-cur",
        }
        log = build_universe_change_log(current=current, prior=prior)
        self.assertTrue(log["has_prior"])
        self.assertEqual(log["entered"], ["DUSDT"])
        self.assertEqual(log["exited"], ["AUSDT"])
        self.assertEqual(log["retained"], ["BUSDT", "CUSDT"])
        self.assertEqual(log["churn_count"], 2)
        self.assertAlmostEqual(log["churn_ratio"], 2.0 / 3.0)
        self.assertTrue(log["binding_changed"])
        self.assertEqual(log["prior_decision_date_utc"], "2026-03-01")

    def test_identical_membership_zero_churn(self) -> None:
        prior = {"active_symbols": ["AUSDT", "BUSDT"], "universe_binding": "same"}
        current = {"active_symbols": ["BUSDT", "AUSDT"], "universe_binding": "same"}
        log = build_universe_change_log(current=current, prior=prior)
        self.assertEqual(log["churn_count"], 0)
        self.assertEqual(log["entered"], [])
        self.assertEqual(log["exited"], [])
        self.assertEqual(log["retained"], ["AUSDT", "BUSDT"])
        self.assertFalse(log["binding_changed"])

    def test_is_pure_does_not_mutate_inputs(self) -> None:
        current = {"active_symbols": ["AUSDT"]}
        prior = {"active_symbols": ["BUSDT"]}
        cur_copy, prior_copy = copy.deepcopy(current), copy.deepcopy(prior)
        build_universe_change_log(current=current, prior=prior)
        self.assertEqual(current, cur_copy)
        self.assertEqual(prior, prior_copy)


class UniverseChurnGateTests(unittest.TestCase):
    def _current(self, *, active: list[str], gate: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "active_symbols": active,
            "decision_time_ms": 123,
            "decision_date_utc": "2026-03-02",
            "churn_gate": gate,
        }

    def test_disabled_gate_is_noop(self) -> None:
        verdict = evaluate_universe_churn_gate(current={"churn_gate": {"enabled": False}}, prior=None)
        self.assertEqual(verdict["status"], "disabled")
        self.assertEqual(verdict["blockers"], [])

    def test_bootstrap_reference_allows_staged_four_in_four_out(self) -> None:
        baseline = [f"C{idx:02d}USDT" for idx in range(20)]
        active = baseline[:16] + ["N00USDT", "N01USDT", "N02USDT", "N03USDT"]
        gate = {
            "enabled": True,
            "max_entered_count": 4,
            "max_exited_count": 4,
            "max_churn_count": 8,
            "max_churn_ratio": 0.4,
            "bootstrap_reference_symbols": baseline,
        }
        verdict = evaluate_universe_churn_gate(current=self._current(active=active, gate=gate), prior=None)
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual(verdict["reference_source"], "bootstrap_reference_symbols")
        self.assertEqual(verdict["entered_count"], 4)
        self.assertEqual(verdict["exited_count"], 4)
        self.assertEqual(verdict["churn_count"], 8)

    def test_churn_over_limit_blocks(self) -> None:
        prior = {"active_symbols": [f"C{idx:02d}USDT" for idx in range(20)], "universe_binding": "prior"}
        active = [f"C{idx:02d}USDT" for idx in range(14)] + [f"N{idx:02d}USDT" for idx in range(6)]
        gate = {
            "enabled": True,
            "max_entered_count": 4,
            "max_exited_count": 4,
            "max_churn_count": 8,
            "max_churn_ratio": 0.4,
            "bootstrap_reference_symbols": prior["active_symbols"],
        }
        verdict = evaluate_universe_churn_gate(current=self._current(active=active, gate=gate), prior=prior)
        self.assertEqual(verdict["status"], "blocked")
        self.assertEqual(verdict["reference_source"], "prior_live_universe_artifact")
        self.assertTrue(any("entered_count_exceeds_max" in blocker for blocker in verdict["blockers"]))
        self.assertTrue(any("churn_count_exceeds_max" in blocker for blocker in verdict["blockers"]))

    def test_enabled_without_prior_or_bootstrap_blocks(self) -> None:
        verdict = evaluate_universe_churn_gate(
            current=self._current(active=["BTCUSDT"], gate={"enabled": True, "max_churn_count": 1}),
            prior=None,
        )
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("universe_churn_gate_missing_prior_or_bootstrap_reference", verdict["blockers"])


class FindPriorLiveUniverseArtifactTests(unittest.TestCase):
    """Defensive discovery of the immediately-preceding run's live_universe.json (audit only)."""

    def _write(self, directory: Path, active: list[str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "live_universe.json").write_text(
            json.dumps({"active_symbols": active}), encoding="utf-8"
        )

    def test_picks_most_recent_strictly_prior_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "mainnet_rebalance_plan"
            self._write(parent / "20260301T000000Z-run", ["OLD"])
            self._write(parent / "20260302T000000Z-run", ["MID"])
            self._write(parent / "20260303T120000Z-run", ["PRIOR"])
            current_run = "20260304T000000Z-run"
            run_root = parent / current_run
            # The current run's own artifact already exists when the diff runs; it must be
            # excluded by NAME (run_id-prefixed ordering), not by absence of the file.
            self._write(run_root, ["CURRENT"])
            prior = find_prior_live_universe_artifact(run_root=run_root, run_id=current_run)
            self.assertIsNotNone(prior)
            self.assertEqual(prior["active_symbols"], ["PRIOR"])

    def test_excludes_current_and_future_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "mainnet_rebalance_plan"
            current_run = "20260304T000000Z-run"
            self._write(parent / current_run, ["CURRENT"])
            self._write(parent / "20260305T000000Z-run", ["FUTURE"])
            run_root = parent / current_run
            self.assertIsNone(find_prior_live_universe_artifact(run_root=run_root, run_id=current_run))

    def test_no_prior_or_missing_parent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "mainnet_rebalance_plan" / "20260304T000000Z-run"
            run_root.mkdir(parents=True)
            self.assertIsNone(
                find_prior_live_universe_artifact(run_root=run_root, run_id="20260304T000000Z-run")
            )

    def test_round_trip_prior_artifact_feeds_change_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "mainnet_rebalance_plan"
            self._write(parent / "20260303T000000Z-run", ["AUSDT", "BUSDT"])
            current_run = "20260304T000000Z-run"
            run_root = parent / current_run
            run_root.mkdir(parents=True)
            prior = find_prior_live_universe_artifact(run_root=run_root, run_id=current_run)
            log = build_universe_change_log(
                current={"active_symbols": ["BUSDT", "CUSDT"]}, prior=prior
            )
            self.assertEqual(log["entered"], ["CUSDT"])
            self.assertEqual(log["exited"], ["AUSDT"])
            self.assertEqual(log["retained"], ["BUSDT"])


class WriteUniverseChangeLogTests(unittest.TestCase):
    """The best-effort writer: writes the audit artifact, but never raises and never blocks."""

    def test_writes_artifact_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "mainnet_rebalance_plan" / "20260304T000000Z-run"
            run_root.mkdir(parents=True)
            write_universe_change_log(
                run_root=run_root,
                run_id="20260304T000000Z-run",
                live_universe={"active_symbols": ["AUSDT", "BUSDT"], "status": "ok"},
            )
            written = json.loads((run_root / "universe_change_log.json").read_text(encoding="utf-8"))
            self.assertFalse(written["has_prior"])
            self.assertEqual(written["entered"], ["AUSDT", "BUSDT"])

    def test_write_failure_is_swallowed_never_raises(self) -> None:
        # A disk/permission failure must NOT propagate (the audit trail is non-critical) and must
        # leave no partial artifact. The plan run proceeds; no blocker is introduced.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "mainnet_rebalance_plan" / "20260304T000000Z-run"
            run_root.mkdir(parents=True)
            with mock.patch(
                "enhengclaw.live_trading.live_pit_universe.write_json",
                side_effect=OSError("disk full"),
            ):
                write_universe_change_log(  # must not raise
                    run_root=run_root,
                    run_id="20260304T000000Z-run",
                    live_universe={"active_symbols": ["AUSDT"]},
                )
            self.assertFalse((run_root / "universe_change_log.json").exists())


if __name__ == "__main__":
    unittest.main()
