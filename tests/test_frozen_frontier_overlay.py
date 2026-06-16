from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.frozen_frontier_overlay import (  # noqa: E402
    compute_overlay_trigger,
    file_sha256,
    load_overlay_contract,
    overlay_spec_hash,
    validate_overlay_contract,
    validate_thresholds_pit,
)

REAL = (
    ROOT / "config" / "quant_research" / "frontier_12factor"
    / "dth60_hybrid_shock_q90_or_crowded_top20_zero__overlay.frozen.json"
)


class FrozenFrontierOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="frontier-overlay-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.assertTrue(REAL.exists(), f"overlay contract missing: {REAL}")

    def test_real_overlay_validates_ready(self) -> None:
        result = validate_overlay_contract(
            path=REAL,
            expected_file_sha256=file_sha256(REAL),
            expected_spec_hash=overlay_spec_hash(load_overlay_contract(REAL)),
        )
        self.assertEqual(result["status"], "ready", result["blockers"])

    def test_has_own_weights_blocks(self) -> None:
        c = load_overlay_contract(REAL)
        c["has_own_factor_weights"] = True
        c["overlay_spec_hash"] = overlay_spec_hash(c)
        p = self.temp_dir / "own_weights.json"
        p.write_text(json.dumps(c), encoding="utf-8")
        result = validate_overlay_contract(path=p)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("overlay_must_not_carry_own_factor_weights", result["blockers"])

    def test_requires_input_panel_false_blocks(self) -> None:
        c = load_overlay_contract(REAL)
        c["threshold_contract"]["requires_input_panel"] = False
        c["overlay_spec_hash"] = overlay_spec_hash(c)
        p = self.temp_dir / "no_panel.json"
        p.write_text(json.dumps(c), encoding="utf-8")
        result = validate_overlay_contract(path=p, expected_spec_hash=overlay_spec_hash(c))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("overlay_threshold_contract_must_require_input_panel", result["blockers"])

    def test_trigger_shock_branch(self) -> None:
        t = compute_overlay_trigger(
            shock_co_occurrence_index=0.5, co_jump_count_3d=0, shock_q90=0.3, co_jump_q90=20,
            distance_to_high_60_rank_pct=0.1, coinglass_top_trader_rank_pct=0.1,
        )
        self.assertTrue(t["triggered"]) ; self.assertTrue(t["shock_branch"]) ; self.assertEqual(t["target_multiplier"], 0.0)

    def test_trigger_cojump_branch(self) -> None:
        t = compute_overlay_trigger(
            shock_co_occurrence_index=0.0, co_jump_count_3d=25, shock_q90=0.3, co_jump_q90=20,
            distance_to_high_60_rank_pct=0.1, coinglass_top_trader_rank_pct=0.1,
        )
        self.assertTrue(t["triggered"]) ; self.assertTrue(t["cojump_branch"])

    def test_trigger_crowded_branch_needs_both(self) -> None:
        both = compute_overlay_trigger(
            shock_co_occurrence_index=0.0, co_jump_count_3d=0, shock_q90=0.3, co_jump_q90=20,
            distance_to_high_60_rank_pct=0.80, coinglass_top_trader_rank_pct=0.85,
        )
        self.assertTrue(both["triggered"]) ; self.assertTrue(both["crowded_branch"])
        only_one = compute_overlay_trigger(
            shock_co_occurrence_index=0.0, co_jump_count_3d=0, shock_q90=0.3, co_jump_q90=20,
            distance_to_high_60_rank_pct=0.80, coinglass_top_trader_rank_pct=0.50,
        )
        self.assertFalse(only_one["triggered"]) ; self.assertEqual(only_one["target_multiplier"], 1.0)

    def test_trigger_none(self) -> None:
        t = compute_overlay_trigger(
            shock_co_occurrence_index=0.0, co_jump_count_3d=0, shock_q90=0.3, co_jump_q90=20,
            distance_to_high_60_rank_pct=0.1, coinglass_top_trader_rank_pct=0.1,
        )
        self.assertFalse(t["triggered"]) ; self.assertEqual(t["target_multiplier"], 1.0)

    def test_thresholds_pit_synthetic_blocks(self) -> None:
        bad = validate_thresholds_pit({
            "from_input_panel": False, "train_includes_decision_row": False,
            "current_row_excluded": True, "shock_co_occurrence_index_q90": 0.0, "co_jump_count_3d_q90": 2.0,
        })
        self.assertIn("overlay_thresholds_not_from_input_panel", bad)
        good = validate_thresholds_pit({
            "from_input_panel": True, "train_includes_decision_row": False,
            "current_row_excluded": True, "shock_co_occurrence_index_q90": 0.42, "co_jump_count_3d_q90": 9.0,
        })
        self.assertEqual(good, [])

    def test_thresholds_pit_decision_leak_blocks(self) -> None:
        leak = validate_thresholds_pit({
            "from_input_panel": True, "train_includes_decision_row": True,
            "current_row_excluded": False, "shock_co_occurrence_index_q90": 0.42, "co_jump_count_3d_q90": 9.0,
        })
        self.assertIn("overlay_thresholds_train_includes_decision_row", leak)
        self.assertIn("overlay_thresholds_current_row_not_excluded", leak)


if __name__ == "__main__":
    unittest.main()
