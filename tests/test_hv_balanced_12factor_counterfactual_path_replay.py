from __future__ import annotations

from argparse import Namespace
from datetime import UTC, date, datetime, time, timedelta
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_12factor_counterfactual_path_replay import (  # noqa: E402
    DEFAULT_T0_SOURCE,
    run_counterfactual_path_replay,
)


REQUIRED_FACTORS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
]
SYMBOLS = [
    ("BTCUSDT", "BTC"),
    ("ETHUSDT", "ETH"),
    ("SOLUSDT", "SOL"),
    ("XRPUSDT", "XRP"),
    ("BNBUSDT", "BNB"),
    ("ADAUSDT", "ADA"),
]


class HvBalanced12FactorCounterfactualPathReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="counterfactual-replay-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_replays_daily_multiphase_counterfactual_target_path(self) -> None:
        bundle = self._write_bundle(start=date(2026, 1, 1), end=date(2026, 1, 20))

        summary, exit_code = run_counterfactual_path_replay(
            self._args(
                bundle,
                output_root=self.temp_dir / "proof_artifacts" / "ready",
                start_t0_utc="2026-01-15T06:26:14Z",
                end_decision_utc="2026-01-20T12:00:00Z",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["counterfactual_path_replay_ready"])
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["timer_invoked"])
        self.assertFalse(summary["supervisor_invoked"])
        self.assertFalse(summary["executor_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fills_observed"], 0)
        self.assertEqual(summary["complete_12factor_provider_date_count"], 20)
        self.assertEqual(summary["wfo_contract"]["missing_weight_window_count"], 0)
        self.assertEqual(summary["path_result"]["daily_target_row_count"], 36)
        self.assertEqual(summary["path_result"]["sleeve_trace_row_count"], 360)

        targets = pd.read_csv(summary["output_files"]["daily_counterfactual_target_weights"])
        latest = targets.loc[targets["decision_date_utc"].eq("2026-01-20")]
        self.assertEqual(len(latest), len(SYMBOLS))
        self.assertEqual(set(latest["active_sleeve_count"].unique()), {10})
        self.assertAlmostEqual(float(latest["target_gross_weight"].iloc[0]), 1.0, places=12)
        self.assertAlmostEqual(float(latest["target_net_weight"].iloc[0]), 0.0, places=12)

        latest_plan = _load_json(Path(summary["output_files"]["latest_counterfactual_target_plan"]))
        self.assertEqual(latest_plan["decision_date_utc"], "2026-01-20")
        self.assertEqual(len(latest_plan["positions"]), len(SYMBOLS))
        self.assertEqual(latest_plan["orders_submitted"], 0)

    def test_blocks_when_settlement_history_is_missing_for_t0_path(self) -> None:
        bundle = self._write_bundle(
            start=date(2026, 1, 1),
            end=date(2026, 1, 20),
            omit_factor="settlement_cycle_premium_60d",
        )

        summary, exit_code = run_counterfactual_path_replay(
            self._args(
                bundle,
                output_root=self.temp_dir / "proof_artifacts" / "missing-settlement",
                start_t0_utc="2026-01-15T06:26:14Z",
                end_decision_utc="2026-01-20T12:00:00Z",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("factor_history_missing:settlement_cycle_premium_60d", summary["blockers"])
        self.assertIn("p10a_rows_missing_contract_factors", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)
        latest_plan = _load_json(Path(summary["output_files"]["latest_counterfactual_target_plan"]))
        self.assertEqual(latest_plan["positions"], [])

    def test_blocks_when_wfo_test_window_does_not_cover_replay_period(self) -> None:
        bundle = self._write_bundle(
            start=date(2026, 1, 1),
            end=date(2026, 1, 20),
            wfo_test_end=date(2026, 1, 10),
        )

        summary, exit_code = run_counterfactual_path_replay(
            self._args(
                bundle,
                output_root=self.temp_dir / "proof_artifacts" / "missing-wfo",
                start_t0_utc="2026-01-15T06:26:14Z",
                end_decision_utc="2026-01-20T12:00:00Z",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("wfo_weight_window_missing_for_live_period", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_latest_wfo_carry_forward_contract_can_cover_live_period_when_explicit(self) -> None:
        bundle = self._write_bundle(
            start=date(2026, 1, 1),
            end=date(2026, 1, 20),
            wfo_test_end=date(2026, 1, 10),
        )

        summary, exit_code = run_counterfactual_path_replay(
            self._args(
                bundle,
                output_root=self.temp_dir / "proof_artifacts" / "carry-forward-wfo",
                start_t0_utc="2026-01-15T06:26:14Z",
                end_decision_utc="2026-01-20T12:00:00Z",
                strict_wfo_window=False,
                allow_latest_wfo_carry_forward=True,
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["wfo_contract"]["frozen_contract_status"], "ready")
        self.assertEqual(
            summary["wfo_contract"]["frozen_contract_mode"],
            "latest_wfo_carry_forward_frozen_live_period",
        )
        contract = _load_json(Path(summary["output_files"]["live_period_frozen_wfo_contract"]))
        self.assertTrue(contract["enabled"])
        self.assertEqual(contract["status"], "ready")
        self.assertFalse(contract["research_exact_parity"])
        self.assertEqual(contract["missing_weight_window_count"], 0)

    def _args(
        self,
        bundle: dict[str, Path],
        *,
        output_root: Path,
        start_t0_utc: str,
        end_decision_utc: str,
        strict_wfo_window: bool = True,
        allow_latest_wfo_carry_forward: bool = False,
    ) -> Namespace:
        return Namespace(
            p10a_summary=bundle["p10a_summary"],
            p9r_summary=bundle["p9r_summary"],
            output_root=output_root,
            start_t0_utc=start_t0_utc,
            t0_source=DEFAULT_T0_SOURCE,
            end_decision_utc=end_decision_utc,
            availability_lag_seconds=60,
            strict_wfo_window=strict_wfo_window,
            allow_latest_wfo_carry_forward=allow_latest_wfo_carry_forward,
            row_sample_limit=50,
        )

    def _write_bundle(
        self,
        *,
        start: date,
        end: date,
        omit_factor: str | None = None,
        wfo_test_end: date | None = None,
    ) -> dict[str, Path]:
        root = self.temp_dir / "bundle"
        p10a_root = root / "p10a"
        p9r_root = root / "p9r"
        p10a_root.mkdir(parents=True, exist_ok=True)
        p9r_root.mkdir(parents=True, exist_ok=True)
        p10a_rows = p10a_root / "pit_live_feature_candidate_rows.csv"
        p10a_summary = p10a_root / "summary.json"
        p9r_weights = p9r_root / "wfo_window_factor_weights.csv"
        p9r_windows = p9r_root / "window_row_parity.csv"
        p9r_contract = p9r_root / "research_scorer_contract.json"
        p9r_summary = p9r_root / "summary.json"

        rows = []
        for provider_day in _date_range(start, end):
            provider_ms = _provider_ms(provider_day)
            for symbol_index, (symbol, subject) in enumerate(SYMBOLS):
                for factor_index, factor in enumerate(REQUIRED_FACTORS):
                    if factor == omit_factor:
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "subject": subject,
                            "factor_id": factor,
                            "decision_time_utc": "2026-01-21T12:00:00Z",
                            "decision_time_ms": _decision_ms(end + timedelta(days=1)),
                            "provider_timestamp_utc": datetime.fromtimestamp(provider_ms / 1000, tz=UTC)
                            .isoformat(timespec="seconds")
                            .replace("+00:00", "Z"),
                            "provider_timestamp_ms": provider_ms,
                            "available_at_ms": provider_ms + 60_000,
                            "value": float(symbol_index + 1) + float(factor_index) / 100.0,
                            "value_ready": True,
                            "source": "unit_test",
                        }
                    )
        pd.DataFrame(rows).to_csv(p10a_rows, index=False)

        contract = {
            "contract_version": "research_h10d_12_factor_scorer_contract.v1",
            "required_feature_columns": REQUIRED_FACTORS,
            "required_feature_count": len(REQUIRED_FACTORS),
            "profile_constraints": {
                "top_long_count": 3,
                "bottom_short_count": 3,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "max_gross_leverage": 1.0,
            },
            "portfolio_construction_baseline": {
                "target_engine": "multiphase_equal_sleeve",
                "phase_offsets_days": list(range(10)),
                "rebalance_interval_days_per_sleeve": 10,
                "sleeve_weight": 0.1,
                "per_sleeve_long_short_k": 3,
                "aggregate_rule": "sum_equal_weight_sleeve_targets",
            },
        }
        _write_json(p9r_contract, contract)
        _write_json(
            p10a_summary,
            {
                "status": "ready",
                "decision_time_utc": "2026-01-21T12:00:00Z",
                "availability_lag_seconds": 60,
                "artifacts": {
                    "pit_live_feature_candidate_rows": str(p10a_rows),
                    "summary": str(p10a_summary),
                },
                "candidate_executed": False,
                "executor_invoked": False,
                "orders_submitted": 0,
                "fills_observed": 0,
            },
        )

        weight_rows = []
        window_rows = []
        for phase in range(10):
            window_id = f"phase={phase}|train_end=2025-12-01T00:00:00Z|validation_end=2025-12-31T00:00:00Z"
            window_rows.append(
                {
                    "window_id": window_id,
                    "phase_offset_days": phase,
                    "phase_start_date_utc": (start + timedelta(days=phase)).isoformat(),
                    "train_end_utc": "2025-12-01T00:00:00Z",
                    "validation_end_utc": "2025-12-31T00:00:00Z",
                    "test_start_utc": start.isoformat() + "T00:00:00Z",
                    "test_end_utc": (wfo_test_end or end).isoformat() + "T00:00:00Z",
                    "test_row_count": len(SYMBOLS),
                    "trigger_mismatch_count": 0,
                    "multiplier_max_abs_diff": 0.0,
                    "target_contribution_max_abs_diff": 0.0,
                    "score_max_abs_diff": 0.0,
                }
            )
            for factor_index, factor in enumerate(REQUIRED_FACTORS):
                weight_rows.append(
                    {
                        "window_id": window_id,
                        "phase_offset_days": phase,
                        "train_end_utc": "2025-12-01T00:00:00Z",
                        "validation_end_utc": "2025-12-31T00:00:00Z",
                        "factor": factor,
                        "weight": 1.0 if factor_index == 0 else 0.0,
                        "abs_weight_sum": 1.0,
                        "missing_weight": False,
                    }
                )
        pd.DataFrame(weight_rows).to_csv(p9r_weights, index=False)
        pd.DataFrame(window_rows).to_csv(p9r_windows, index=False)
        _write_json(
            p9r_summary,
            {
                "status": "ready",
                "research_scorer_contract": contract,
                "output_files": {
                    "wfo_window_factor_weights": str(p9r_weights),
                    "window_row_parity": str(p9r_windows),
                    "research_scorer_contract": str(p9r_contract),
                    "summary": str(p9r_summary),
                },
                "orders_submitted": 0,
                "fills_observed": 0,
            },
        )
        return {
            "p10a_summary": p10a_summary,
            "p9r_summary": p9r_summary,
        }


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _provider_ms(provider_day: date) -> int:
    stamp = datetime.combine(provider_day, time(23, 59, 59, 999000), tzinfo=UTC)
    return int(stamp.timestamp() * 1000)


def _decision_ms(decision_day: date) -> int:
    stamp = datetime.combine(decision_day, time(0, 1), tzinfo=UTC)
    return int(stamp.timestamp() * 1000)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
