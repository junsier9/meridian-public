from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10akv_p10akx_read_only_position_relation_corridor import (  # noqa: E402
    P10AKX_CONTRACT,
    P10AKY_RESOLUTION_GATE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10aky_p10ala_position_relation_resolution_corridor import (  # noqa: E402
    P10ALB_GATE,
    run_corridor,
)


class HvBalanced12FactorP10akyP10alaPositionRelationResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10aky-p10ala-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_corridor_prepares_resolution_proposal_without_selecting_path(self) -> None:
        p10akx = self._write_ready_inputs()

        summary, exit_code = run_corridor(
            self._args(
                p10akx_summary=p10akx,
                output_root=self.temp_dir / "proof_artifacts" / "p10aky-ready",
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["current_relation"], "opposite_direction_reduce_existing_long")
        self.assertTrue(summary["resolution_path_selection_required"])
        self.assertFalse(summary["resolution_path_selected"])
        self.assertEqual(summary["allowed_next_gate"], P10ALB_GATE)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_api_called"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual([step["status"] for step in summary["steps"]], ["ready", "ready", "ready"])

        proposal_path = Path(summary["steps"][1]["summary"]["path"]).parent / "proof" / "proposal.json"
        proposal = _load_json(proposal_path)
        self.assertTrue(proposal["current_relation_requires_resolution"])
        self.assertEqual(len(proposal["paths"]), 3)
        self.assertEqual(proposal["recommended_next_gate"], P10ALB_GATE)
        self.assertTrue(proposal["does_not_authorize_execution"])
        self.assertIn(
            "separate_reduce_only_reduction_canary",
            [path["path_id"] for path in proposal["paths"]],
        )

    def test_bad_p10akx_blocks_before_proposal(self) -> None:
        p10akx = self._write_ready_inputs()
        payload = _load_json(p10akx)
        payload["status"] = "blocked"
        payload["blockers"] = ["synthetic"]
        _write_json(p10akx, payload)

        summary, exit_code = run_corridor(
            self._args(
                p10akx_summary=p10akx,
                output_root=self.temp_dir / "proof_artifacts" / "p10aky-blocked",
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["blockers"], ["p10aky_blocked"])
        self.assertEqual(len(summary["steps"]), 1)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, *, p10akx_summary: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            p10akx_summary=str(p10akx_summary),
            owner="rulebook_owner",
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> Path:
        root = self.temp_dir / "inputs"
        p10akv = root / "p10akv" / "summary.json"
        p10akw = root / "p10akw" / "summary.json"
        p10akx = root / "p10akx" / "summary.json"
        _write_json(
            p10akv,
            {
                "status": "ready",
                "fresh_relation_executable_under_revised_terms": False,
                "future_execution_precheck_ready_under_revised_terms": False,
                "fresh_position_relation": {
                    "relation": "opposite_direction_reduce_existing_long",
                    "candidate_side": "SELL",
                    "pre_position_amt": "0.013",
                    "executable_under_revised_terms": False,
                    "relation_blocked_by_terms": True,
                    "non_reduce_only_restoration_required": True,
                    "non_reduce_only_restoration_authorized": False,
                },
            },
        )
        _write_json(
            p10akw,
            {
                "status": "ready",
                "source_evidence": {"p10akv_summary": {"path": str(p10akv)}},
            },
        )
        _write_json(
            p10akx,
            {
                "contract_version": P10AKX_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p10akx_post_relation_proof_scope_ready": True,
                "fresh_relation_executable_under_revised_terms": False,
                "next_scope_requires_position_relation_resolution": True,
                "allowed_next_gate": P10AKY_RESOLUTION_GATE,
                "allowed_next_gate_must_be_separately_requested": True,
                "live_order_submission_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "source_evidence": {"p10akw_summary": {"path": str(p10akw)}},
            },
        )
        return p10akx


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
