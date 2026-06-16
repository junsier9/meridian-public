from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.frozen_frontier_contract import (  # noqa: E402
    CARRY_FORWARD_SENTINEL_FACTOR,
    file_sha256 as contract_file_sha256,
    frontier_spec_hash,
    load_frozen_frontier,
)
from scripts.governance.run_frontier_contract_governance_gate import (  # noqa: E402
    APPROVE_FRONTIER_CONTRACT_GOVERNANCE,
    LIVE_TIMER_CONFIG,
    build_frontier_contract_governance_gate,
)


_NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
REAL_CONFIG = ROOT / LIVE_TIMER_CONFIG
REAL_WEIGHTS = (
    ROOT / "config" / "quant_research" / "frontier_12factor"
    / "v5_rw_bridge_no_overlay_h10d__2026-05-02-54814da2622b__frozen_frontier_weights.json"
)


class FrontierContractGovernanceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="frontier-contract-gov-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_on_real_live_config(self) -> None:
        before = contract_file_sha256(REAL_CONFIG)
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(REAL_CONFIG), output_root=self.temp_dir / "real"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 0, summary["blockers"])
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["carry_forward_absent"])
        self.assertEqual(summary["contract_evidence"]["weights_feature_count"], 12)
        self.assertFalse(summary["frontier_enable_flip_performed"])
        # The gate is read-only: the live config is byte-identical afterwards.
        self.assertEqual(contract_file_sha256(REAL_CONFIG), before)

    def test_blocks_on_pinned_weights_sha_mismatch(self) -> None:
        host_config = self._host_config_from_real(weights_overrides={"weights_file_sha256": "0" * 64})
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(host_config), output_root=self.temp_dir / "sha-mismatch"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("weights_contract_valid", summary["blockers"])

    def test_blocks_on_carry_forward_signature(self) -> None:
        # A frozen vector whose sentinel factor is >= 0 IS the forbidden carry-forward signature.
        tampered_weights = self._tampered_weights_file(sentinel_value=0.0184)
        new_file_sha = contract_file_sha256(tampered_weights)
        new_spec = frontier_spec_hash(load_frozen_frontier(tampered_weights))
        host_config = self._host_config_from_real(
            weights_overrides={
                "weights_contract_path": str(tampered_weights),
                "weights_file_sha256": new_file_sha,
                "weights_spec_hash": new_spec,
            }
        )
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(host_config), output_root=self.temp_dir / "carry-forward"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertFalse(summary["carry_forward_absent"])
        self.assertIn("carry_forward_absent", summary["blockers"])
        # The carry-forward signature is surfaced in the contract readback.
        self.assertTrue(
            any(
                b.startswith("frontier_carry_forward_signature_detected")
                for b in summary["contract_evidence"]["weights_validation_blockers"]
            )
        )

    def test_blocks_on_scoring_config_sha_mismatch(self) -> None:
        host_config = self._host_config_from_real(weights_overrides={"scoring_config_sha256": "0" * 64})
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(host_config), output_root=self.temp_dir / "scoring-mismatch"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("scoring_config_sha256_matches_on_disk", summary["blockers"])

    def test_blocks_when_overlay_enabled_but_contract_missing(self) -> None:
        host_config = self._host_config_from_real(
            overlay_overrides={"contract_path": str(self.temp_dir / "does_not_exist.json")}
        )
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(host_config), output_root=self.temp_dir / "overlay-missing"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("overlay_contract_valid", summary["blockers"])

    def test_blocks_when_frontier_block_absent(self) -> None:
        host_config = self.temp_dir / "no_frontier.yaml"
        host_config.write_text(yaml.safe_dump({"strategy": {"rebalance_interval_days": 10}}), encoding="utf-8")
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(host_config=str(host_config), output_root=self.temp_dir / "no-block"),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("frontier_block_present", summary["blockers"])

    def test_wrong_owner_decision_blocks(self) -> None:
        summary, exit_code = build_frontier_contract_governance_gate(
            self._args(
                host_config=str(REAL_CONFIG),
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_everything_now",
            ),
            now_fn=lambda: _NOW,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_frontier_contract_governance_recorded", summary["blockers"])

    # ----- helpers -----
    def _args(
        self,
        *,
        host_config: str,
        output_root: Path,
        owner_decision: str = APPROVE_FRONTIER_CONTRACT_GOVERNANCE,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            host_config=host_config,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _host_config_from_real(
        self, *, weights_overrides: dict | None = None, overlay_overrides: dict | None = None
    ) -> Path:
        cfg = yaml.safe_load(REAL_CONFIG.read_text(encoding="utf-8"))
        frontier = dict(cfg["strategy"]["frontier"])
        # The real block uses repo-relative contract paths; make them absolute so the temp
        # config resolves them regardless of cwd.
        for key in ("weights_contract_path", "scoring_config_path"):
            frontier[key] = str(ROOT / frontier[key])
        overlay = dict(frontier.get("overlay") or {})
        if overlay.get("contract_path"):
            overlay["contract_path"] = str(ROOT / overlay["contract_path"])
        overlay.update(overlay_overrides or {})
        frontier["overlay"] = overlay
        frontier.update(weights_overrides or {})
        out = self.temp_dir / "host_config.yaml"
        out.write_text(yaml.safe_dump({"strategy": {"frontier": frontier}}), encoding="utf-8")
        return out

    def _tampered_weights_file(self, *, sentinel_value: float) -> Path:
        contract = dict(load_frozen_frontier(REAL_WEIGHTS))
        weights = dict(contract["feature_weights"])
        weights[CARRY_FORWARD_SENTINEL_FACTOR] = sentinel_value
        contract["feature_weights"] = weights
        # Keep the embedded spec hash internally consistent so ONLY the carry-forward guard trips.
        contract["frozen_frontier_spec_hash"] = frontier_spec_hash(contract)
        out = self.temp_dir / "tampered_weights.json"
        out.write_text(json.dumps(contract, indent=2), encoding="utf-8")
        return out


if __name__ == "__main__":
    unittest.main()
