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

from scripts.live_trading.run_hv_balanced_12factor_p10akr_review_p10ak_blocker_resolution import (  # noqa: E402
    CONTRACT_VERSION as P10AKR_CONTRACT,
    P10AKS_GATE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10aks_p10aku_revised_nonflat_terms_corridor import (  # noqa: E402
    P10AKV_GATE,
    run_corridor,
)


class HvBalanced12FactorP10aksP10akuRevisedNonflatTermsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10aks-p10aku-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_corridor_defines_terms_but_blocks_current_long_plus_sell_relation(self) -> None:
        p10akr = self._write_p10akr_ready()

        summary, exit_code = run_corridor(
            self._args(
                p10akr_summary=p10akr,
                output_root=self.temp_dir / "proof_artifacts" / "p10aks-p10aku-ready",
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p10aks_p10aku_revised_nonflat_terms_corridor_ready"])
        self.assertFalse(summary["current_retained_relation_executable_under_revised_terms"])
        self.assertTrue(summary["terms_sufficient_for_future_read_only_position_relation_proof"])
        self.assertFalse(summary["terms_sufficient_for_additional_live_order_without_new_gate"])
        self.assertEqual(summary["allowed_next_gate"], P10AKV_GATE)
        self.assertFalse(summary["remote_api_called"])
        self.assertFalse(summary["live_order_submission_performed"])
        self.assertFalse(summary["timer_path_load_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual([step["status"] for step in summary["steps"]], ["ready", "ready", "ready"])

        terms_path = Path(summary["steps"][1]["summary"]["path"]).parent / "proof" / "execution_terms.json"
        terms = _load_json(terms_path)
        self.assertEqual(
            terms["current_retained_position_relation"]["relation"],
            "opposite_direction_reduce_existing_long",
        )
        self.assertFalse(terms["current_retained_relation_executable_under_revised_terms"])
        self.assertIn("flat_position_canary", terms["allowed_position_relations"])
        self.assertIn("same_direction_long_add", terms["allowed_position_relations"])
        self.assertIn("opposite_direction_reduce_existing_long", terms["blocked_position_relations"])
        self.assertTrue(terms["fresh_read_only_position_relation_proof_required_before_future_execution_gate"])
        self.assertTrue(terms["does_not_authorize_execution"])

    def test_bad_p10akr_blocks_after_scope_gate_without_terms(self) -> None:
        p10akr = self._write_p10akr_ready()
        payload = _load_json(p10akr)
        payload["status"] = "blocked"
        payload["blockers"] = ["synthetic"]
        _write_json(p10akr, payload)

        summary, exit_code = run_corridor(
            self._args(
                p10akr_summary=p10akr,
                output_root=self.temp_dir / "proof_artifacts" / "p10aks-p10aku-blocked",
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["blockers"], ["p10aks_blocked"])
        self.assertEqual(len(summary["steps"]), 1)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(self, *, p10akr_summary: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            p10akr_summary=str(p10akr_summary),
            owner="rulebook_owner",
            owner_decision_source="unit_test",
        )

    def _write_p10akr_ready(self) -> Path:
        root = self.temp_dir / "inputs" / "p10akr"
        manual_cancel = root / "source" / "manual_cancel.json"
        reduce_only_close = root / "source" / "reduce_only_close.json"
        p10akr = root / "summary.json"
        _write_json(
            manual_cancel,
            {
                "status": "blocked",
                "fill_qty": 0.001,
                "open_order_remaining": False,
                "post_order": {"payload": {"status": "FILLED"}},
            },
        )
        _write_json(
            reduce_only_close,
            {
                "status": "blocked",
                "pre_position_amt": 0.013,
                "post_position_amt": 0.013,
                "close_qty": 0.0,
                "entry_order": {"payload": {"side": "SELL"}},
                "open_orders_match": {"status": "ok", "payload": []},
            },
        )
        _write_json(
            p10akr,
            {
                "contract_version": P10AKR_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p10akr_blocker_resolution_review_ready": True,
                "allowed_next_gate": P10AKS_GATE,
                "allowed_next_gate_must_be_separately_requested": True,
                "live_order_submission_authorized": False,
                "candidate_executor_path_execution_authorized": False,
                "non_reduce_only_restoration_authorized": False,
                "non_reduce_only_restoration_required": True,
                "open_order_remaining_after_readback": False,
                "source_evidence": {
                    "manual_cancel_readback": {"path": str(manual_cancel)},
                    "reduce_only_close_readback": {"path": str(reduce_only_close)},
                },
            },
        )
        return p10akr


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
