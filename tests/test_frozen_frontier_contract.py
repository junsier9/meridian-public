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

from enhengclaw.live_trading.frozen_frontier_contract import (  # noqa: E402
    CARRY_FORWARD_SENTINEL_FACTOR,
    file_sha256,
    frontier_enabled,
    frontier_spec_hash,
    load_frozen_frontier,
    validate_frontier_contract,
)

REAL = (
    ROOT
    / "config"
    / "quant_research"
    / "frontier_12factor"
    / "v5_rw_bridge_no_overlay_h10d__2026-05-02-54814da2622b__frozen_frontier_weights.json"
)


class FrozenFrontierContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="frozen-frontier-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.assertTrue(REAL.exists(), f"frozen frontier contract missing: {REAL}")

    def test_real_contract_validates_ready(self) -> None:
        result = validate_frontier_contract(
            path=REAL,
            expected_file_sha256=file_sha256(REAL),
            expected_spec_hash=frontier_spec_hash(load_frozen_frontier(REAL)),
        )
        self.assertEqual(result["status"], "ready", result["blockers"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["feature_count"], 12)
        self.assertAlmostEqual(result["abs_sum"], 1.0, places=6)

    def test_file_sha_mismatch_blocks(self) -> None:
        result = validate_frontier_contract(
            path=REAL, expected_file_sha256="deadbeef" * 8
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(b.startswith("frontier_file_sha256_mismatch") for b in result["blockers"]))

    def test_spec_hash_mismatch_blocks(self) -> None:
        result = validate_frontier_contract(
            path=REAL, expected_spec_hash="0" * 64
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(b.startswith("frontier_spec_hash_mismatch") for b in result["blockers"]))

    def test_carry_forward_signature_blocks(self) -> None:
        c = load_frozen_frontier(REAL)
        c["feature_weights"][CARRY_FORWARD_SENTINEL_FACTOR] = 0.0184  # the forbidden sign flip
        c["frozen_frontier_spec_hash"] = frontier_spec_hash(c)
        p = self.temp_dir / "carry_forward.json"
        p.write_text(json.dumps(c, indent=2), encoding="utf-8")
        result = validate_frontier_contract(path=p, expected_spec_hash=frontier_spec_hash(c))
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(
            any(b.startswith("frontier_carry_forward_signature_detected") for b in result["blockers"]),
            result["blockers"],
        )

    def test_feature_count_not_12_blocks(self) -> None:
        c = load_frozen_frontier(REAL)
        dropped = c["feature_columns"].pop()
        c["feature_weights"].pop(dropped, None)
        c["frozen_frontier_spec_hash"] = frontier_spec_hash(c)
        p = self.temp_dir / "eleven.json"
        p.write_text(json.dumps(c, indent=2), encoding="utf-8")
        result = validate_frontier_contract(path=p)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(b.startswith("frontier_feature_count_not_12") for b in result["blockers"]))

    def test_missing_path(self) -> None:
        soft = validate_frontier_contract(path=None, require_configured=False)
        self.assertEqual(soft["status"], "not_configured")
        self.assertTrue(soft["passed"])
        hard = validate_frontier_contract(path=None, require_configured=True)
        self.assertEqual(hard["status"], "blocked")
        self.assertIn("frontier_contract_path_missing", hard["blockers"])

    def test_frontier_enabled_flag(self) -> None:
        self.assertTrue(frontier_enabled({"strategy": {"frontier": {"enabled": True}}}))
        self.assertFalse(frontier_enabled({"strategy": {"frontier": {"enabled": False}}}))
        self.assertFalse(frontier_enabled({"strategy": {"frontier": {}}}))
        self.assertFalse(frontier_enabled({}))


if __name__ == "__main__":
    unittest.main()
