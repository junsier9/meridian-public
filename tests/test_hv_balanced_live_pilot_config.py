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

from enhengclaw.live_trading.config import _parse_simple_yaml, load_live_trading_config  # noqa: E402


LIVE_PILOT_CONFIG = ROOT / "config" / "live_trading" / "hv_balanced_binance_usdm_live_pilot.yaml"
EXECUTABLE_CANDIDATE_CONFIG = (
    ROOT / "config" / "live_trading" / "hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml"
)
FULL_BALANCE_2X_CANDIDATE_CONFIG = (
    ROOT / "config" / "live_trading" / "hv_balanced_binance_usdm_live_2x_full_balance_candidate.yaml"
)


class HvBalancedLivePilotConfigTests(unittest.TestCase):
    def test_simple_yaml_parser_supports_scalar_block_lists(self) -> None:
        payload = _parse_simple_yaml(
            "\n".join(
                [
                    "universe_policy:",
                    "  live_selection_mode: pit_rolling",
                    "  candidate_symbols:",
                    "    - BTCUSDT",
                    "    - ETHUSDT",
                    "  churn_gate:",
                    "    enabled: true",
                    "    bootstrap_reference_symbols:",
                    "      - BTCUSDT",
                    "      - ETHUSDT",
                ]
            )
        )
        self.assertEqual(payload["universe_policy"]["candidate_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(
            payload["universe_policy"]["churn_gate"]["bootstrap_reference_symbols"],
            ["BTCUSDT", "ETHUSDT"],
        )

    def test_mainnet_live_pilot_config_is_separate_and_fail_closed_by_default(self) -> None:
        config = load_live_trading_config(LIVE_PILOT_CONFIG)
        payload = config.payload
        binance = payload["binance"]
        capital = payload["capital"]
        risk = payload["risk"]

        self.assertEqual(binance["venue"], "usdm_futures")
        self.assertEqual(binance["position_mode"], "one_way")
        self.assertEqual(binance["api_key_env"], "Trade")
        self.assertEqual(binance["api_secret_env"], "Secret_Key")
        self.assertFalse(risk["trading_enabled"])
        self.assertTrue(risk["require_manual_live_confirm"])
        self.assertLessEqual(capital["allocated_capital_usdt"], 60.0)
        self.assertLessEqual(capital["max_order_notional_usdt"], 12.0)
        self.assertLessEqual(capital["max_symbol_notional_usdt"], 12.0)
        self.assertNotIn("max_daily_realized_loss_usdt", risk)
        self.assertNotIn("max_daily_realized_loss_enforcement", risk)
        self.assertNotIn("daily_realized_pnl_income_types", risk)
        self.assertEqual(risk["max_allocated_capital_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_gross_notional_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_symbol_notional_usdt"], capital["max_symbol_notional_usdt"])
        self.assertEqual(risk["max_order_notional_usdt"], capital["max_order_notional_usdt"])
        self.assertIn("hv_balanced_binance_usdm_live_pilot", str(config.sqlite_path))
        self.assertIn("hv_balanced_binance_usdm_live_pilot", str(config.artifact_root))
        self.assertNotIn("testnet", str(config.path).lower())
        self.assertNotIn("shadow_loop", str(config.sqlite_path))

    def test_live_pilot_config_does_not_embed_secret_material(self) -> None:
        raw = LIVE_PILOT_CONFIG.read_text(encoding="utf-8")

        self.assertIn("api_key_env: Trade", raw)
        self.assertIn("api_secret_env: Secret_Key", raw)
        self.assertNotIn("api_key:", raw)
        self.assertNotIn("api_secret:", raw)
        self.assertNotIn("secret_key:", raw.lower())

    def test_executable_candidate_config_is_review_only_and_disabled_by_default(self) -> None:
        config = load_live_trading_config(EXECUTABLE_CANDIDATE_CONFIG)
        payload = config.payload
        binance = payload["binance"]
        capital = payload["capital"]
        risk = payload["risk"]

        self.assertEqual(binance["venue"], "usdm_futures")
        self.assertEqual(binance["position_mode"], "one_way")
        self.assertEqual(binance["api_key_env"], "Trade")
        self.assertEqual(binance["api_secret_env"], "Secret_Key")
        self.assertFalse(risk["trading_enabled"])
        self.assertTrue(risk["require_manual_live_confirm"])
        self.assertGreaterEqual(capital["allocated_capital_usdt"], 480.0)
        self.assertEqual(capital["allocated_capital_usdt"], 500.0)
        self.assertEqual(capital["max_symbol_notional_usdt"], 100.0)
        self.assertEqual(capital["max_order_notional_usdt"], 100.0)
        self.assertNotIn("max_daily_realized_loss_usdt", risk)
        self.assertNotIn("max_daily_realized_loss_enforcement", risk)
        self.assertNotIn("daily_realized_pnl_income_types", risk)
        self.assertAlmostEqual(risk["min_available_balance_after_plan_usdt"], 100.0)
        self.assertAlmostEqual(risk["min_available_balance_ratio_after_plan"], 0.05)
        self.assertAlmostEqual(risk["min_margin_cushion_after_plan_usdt"], 100.0)
        self.assertEqual(risk["max_allocated_capital_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_gross_notional_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_symbol_notional_usdt"], capital["max_symbol_notional_usdt"])
        self.assertEqual(risk["max_order_notional_usdt"], capital["max_order_notional_usdt"])
        self.assertIn("hv_balanced_binance_usdm_live_pilot_executable_candidate", str(config.sqlite_path))
        self.assertIn("hv_balanced_binance_usdm_live_pilot_executable_candidate", str(config.artifact_root))
        self.assertNotEqual(config.sqlite_path, load_live_trading_config(LIVE_PILOT_CONFIG).sqlite_path)
        self.assertNotIn("testnet", str(config.path).lower())
        self.assertNotIn("shadow_loop", str(config.sqlite_path))

    def test_executable_candidate_config_does_not_embed_secret_material(self) -> None:
        raw = EXECUTABLE_CANDIDATE_CONFIG.read_text(encoding="utf-8")

        self.assertIn("api_key_env: Trade", raw)
        self.assertIn("api_secret_env: Secret_Key", raw)
        self.assertNotIn("api_key:", raw)
        self.assertNotIn("api_secret:", raw)
        self.assertNotIn("secret_key:", raw.lower())

    def test_full_balance_2x_candidate_config_is_review_only_and_disabled_by_default(self) -> None:
        config = load_live_trading_config(FULL_BALANCE_2X_CANDIDATE_CONFIG)
        payload = config.payload
        binance = payload["binance"]
        capital = payload["capital"]
        risk = payload["risk"]

        self.assertEqual(binance["venue"], "usdm_futures")
        self.assertEqual(binance["position_mode"], "one_way")
        self.assertEqual(binance["margin_type"], "cross")
        self.assertEqual(binance["max_leverage"], 2)
        self.assertEqual(binance["api_key_env"], "Trade")
        self.assertEqual(binance["api_secret_env"], "Secret_Key")
        self.assertTrue(capital["review_only"])
        self.assertEqual(capital["sizing_basis"], "total_wallet_balance_usdt_x_2")
        self.assertAlmostEqual(capital["total_wallet_balance_usdt_snapshot"], 1500.0)
        self.assertAlmostEqual(capital["allocated_capital_usdt"], 3000.0)
        self.assertEqual(capital["max_gross_leverage"], 2.0)
        self.assertEqual(capital["max_symbol_notional_usdt"], 600.0)
        self.assertEqual(capital["max_order_notional_usdt"], 600.0)
        self.assertFalse(risk["trading_enabled"])
        self.assertTrue(risk["require_manual_live_confirm"])
        self.assertTrue(risk["review_only_candidate"])
        self.assertTrue(risk["full_balance_2x_candidate"])
        self.assertNotIn("max_daily_realized_loss_usdt", risk)
        self.assertNotIn("max_daily_realized_loss_enforcement", risk)
        self.assertNotIn("daily_realized_pnl_income_types", risk)
        self.assertAlmostEqual(risk["min_available_balance_after_plan_usdt"], 100.0)
        self.assertAlmostEqual(risk["min_available_balance_ratio_after_plan"], 0.05)
        self.assertAlmostEqual(risk["min_margin_cushion_after_plan_usdt"], 100.0)
        self.assertEqual(risk["max_allocated_capital_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_gross_notional_usdt"], capital["allocated_capital_usdt"])
        self.assertEqual(risk["max_symbol_notional_usdt"], capital["max_symbol_notional_usdt"])
        self.assertEqual(risk["max_order_notional_usdt"], capital["max_order_notional_usdt"])
        self.assertIn("hv_balanced_binance_usdm_live_2x_full_balance_candidate", str(config.sqlite_path))
        self.assertIn("hv_balanced_binance_usdm_live_2x_full_balance_candidate", str(config.artifact_root))
        self.assertNotEqual(config.sqlite_path, load_live_trading_config(EXECUTABLE_CANDIDATE_CONFIG).sqlite_path)
        self.assertNotIn("testnet", str(config.path).lower())
        self.assertNotIn("shadow_loop", str(config.sqlite_path))

    def test_full_balance_2x_candidate_config_does_not_embed_secret_material(self) -> None:
        raw = FULL_BALANCE_2X_CANDIDATE_CONFIG.read_text(encoding="utf-8")

        self.assertIn("api_key_env: Trade", raw)
        self.assertIn("api_secret_env: Secret_Key", raw)
        self.assertNotIn("api_key:", raw)
        self.assertNotIn("api_secret:", raw)
        self.assertNotIn("secret_key:", raw.lower())


if __name__ == "__main__":
    unittest.main()
