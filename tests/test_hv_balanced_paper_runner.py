from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256
from enhengclaw.live_trading.paper_runner import PAPER_ORDER_SUBMISSION_POLICY, run_paper_controlled_from_args


class HvBalancedPaperRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-paper-runner-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_paper_runner_generates_targets_intents_risk_gate_and_paper_fills(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        with _forbid_exchange_order_endpoints():
            summary, exit_code = run_paper_controlled_from_args(
                Namespace(
                    config=str(config_path),
                    mode="live",
                    as_of="now",
                    fixture_panel=str(panel_path),
                    symbols="",
                    public_market_data=False,
                    i_understand_this_is_live=True,
                )
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["mode"], "paper")
        self.assertTrue(summary["paper_only"])
        self.assertEqual(summary["exchange_order_submission"], "disabled")
        self.assertEqual(summary["order_submission_policy"], PAPER_ORDER_SUBMISSION_POLICY)
        self.assertEqual(summary["status"], "paper_executed")
        artifact_root = Path(summary["artifact_root"])
        risk_gate = json.loads((artifact_root / "risk_gate.json").read_text(encoding="utf-8"))
        execution_plan = pd.read_csv(artifact_root / "execution_plan.csv")
        target_positions = pd.read_csv(artifact_root / "target_positions.csv")
        fills = pd.read_csv(artifact_root / "fills.csv")
        paper_execution = json.loads((artifact_root / "paper_execution.json").read_text(encoding="utf-8"))
        reconciliation = json.loads((artifact_root / "reconciliation.json").read_text(encoding="utf-8"))
        run_summary = json.loads((artifact_root / "run_summary.json").read_text(encoding="utf-8"))
        runner_guard = json.loads((artifact_root / "paper_controlled_runner.json").read_text(encoding="utf-8"))
        sizing_report = pd.read_csv(artifact_root / "order_sizing_report.csv")
        sizing_summary = json.loads((artifact_root / "min_executable_capital_report.json").read_text(encoding="utf-8"))

        self.assertTrue(risk_gate["passed"])
        self.assertEqual(risk_gate["mode"], "paper")
        self.assertGreater(len(target_positions), 0)
        self.assertGreater(len(execution_plan), 0)
        self.assertEqual(len(execution_plan), len(fills))
        self.assertTrue(fills["liquidity"].eq("TAKER_SIM").all())
        self.assertEqual(paper_execution["status"], "filled")
        self.assertEqual(reconciliation["status"], "paper_simulated")
        self.assertTrue(run_summary["paper_only"])
        self.assertEqual(runner_guard["exchange_order_submission"], "disabled")
        self.assertGreater(len(sizing_report), 0)
        self.assertEqual(sizing_summary["status"], "passed")

    def test_paper_runner_can_use_public_data_without_signed_order_methods(self) -> None:
        config_path = self._config_path(public_market_data=True)
        symbol_filters = {
            f"{subject}USDT": {"step_size": 0.001, "min_qty": 0.0, "min_notional": 0.0}
            for subject in ["L1", "L2", "L3", "S1", "S2", "S3"]
        }

        with _forbid_exchange_order_endpoints(), patch(
            "enhengclaw.live_trading.cli.fetch_public_live_feature_panel",
            return_value=(
                _fixture_panel(),
                {"source": "unit_test_public_rest", "row_count": 6},
                symbol_filters,
            ),
        ) as fetch_panel:
            summary, exit_code = run_paper_controlled_from_args(
                Namespace(
                    config=str(config_path),
                    as_of="now",
                    fixture_panel="",
                    symbols="BTCUSDT,ETHUSDT",
                    public_market_data=False,
                )
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "paper_executed")
        self.assertEqual(summary["mode"], "paper")
        fetch_panel.assert_called_once()

    def _config_path(self, *, public_market_data: bool = False) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm.yaml"
        sqlite_path = (self.temp_dir / "state.sqlite3").as_posix()
        artifact_root = (self.temp_dir / "runs").as_posix()
        frozen_config = self.temp_dir / "frozen_hv_balanced.json"
        payload = json.loads(
            (ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json").read_text(
                encoding="utf-8-sig"
            )
        )
        payload["pit_data_eligibility_policy"] = {"mode": "disabled"}
        frozen_config.write_text(json.dumps(payload), encoding="utf-8")
        frozen_hash = file_sha256(frozen_config)
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    f"  frozen_config_path: {frozen_config.as_posix()}",
                    f"  frozen_config_sha256: {frozen_hash}",
                    "  rebalance_interval_days: 10",
                    "capital:",
                    "  allocated_capital_usdt: 100.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_allocated_capital_usdt: 100.0",
                    "  max_gross_notional_usdt: 100.0",
                    "  max_symbol_notional_usdt: 20.0",
                    "market_data:",
                    f"  public_data_enabled: {str(public_market_data).lower()}",
                    "state:",
                    f"  sqlite_path: {sqlite_path}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _forbid_exchange_order_endpoints():
    return patch.multiple(
        "enhengclaw.live_trading.binance_usdm_client.BinanceUsdmClient",
        new_order=Mock(side_effect=AssertionError("new_order must not be called by paper runner")),
        new_order_test=Mock(side_effect=AssertionError("new_order_test must not be called by paper runner")),
        submit_manual_live_order_smoke=Mock(
            side_effect=AssertionError("submit_manual_live_order_smoke must not be called by paper runner")
        ),
        cancel_order=Mock(side_effect=AssertionError("cancel_order must not be called by paper runner")),
    )


def _fixture_panel() -> pd.DataFrame:
    rows = []
    for index, subject in enumerate(["L1", "L2", "L3", "S1", "S2", "S3"]):
        base = 0.10 + index * 0.01
        rows.append(
            {
                "timestamp_ms": 0,
                "subject": subject,
                "usdm_symbol": f"{subject}USDT",
                "perp_close": 100.0,
                "perp_quote_volume_usd": 10_000_000.0,
                "universe_active": True,
                "universe_rank": index + 1,
                "liquidity_bucket": "top_liquidity" if subject.startswith("L") else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                "intraday_realized_vol_4h_to_1d_smooth_60": base,
                "realized_volatility_5": base + 0.01,
                "distance_to_high_60": base + 0.02,
                "distance_to_high_5": -0.01 if subject.startswith("S") else -0.20,
                "downside_upside_vol_ratio_30": base + 0.03,
                "momentum_20": 0.05,
            }
        )
    return pd.DataFrame(rows)
