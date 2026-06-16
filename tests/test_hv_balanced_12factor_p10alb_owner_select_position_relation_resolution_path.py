from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
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

from scripts.live_trading.run_hv_balanced_12factor_p10alb_owner_select_position_relation_resolution_path import (  # noqa: E402
    APPROVE_P10ALB,
    NEXT_GATE_BY_PATH,
    P10ALB_GATE,
    VALID_PATHS,
    build_p10alb_owner_select_path,
)


_NOW = datetime(2026, 6, 9, 20, 0, tzinfo=UTC)


class P10albOwnerSelectPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10alb-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_records_selected_path_without_executing(self) -> None:
        p10ala = self._write_ready_p10ala()

        summary, exit_code = build_p10alb_owner_select_path(
            self._args(
                p10ala,
                selected_path="separate_reduce_only_reduction_canary",
                output_root=self.temp_dir / "out" / "ready",
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["resolution_path_selected"])
        self.assertEqual(summary["selected_resolution_path"], "separate_reduce_only_reduction_canary")
        self.assertEqual(
            summary["allowed_next_gate"],
            NEXT_GATE_BY_PATH["separate_reduce_only_reduction_canary"],
        )
        # Authorizes nothing executable.
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_api_called"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_each_valid_path_maps_to_its_followup_gate(self) -> None:
        p10ala = self._write_ready_p10ala()
        for path in VALID_PATHS:
            summary, exit_code = build_p10alb_owner_select_path(
                self._args(p10ala, selected_path=path, output_root=self.temp_dir / "out" / path),
                now_fn=lambda: _NOW,
            )
            self.assertEqual(exit_code, 0, path)
            self.assertEqual(summary["selected_resolution_path"], path)
            self.assertEqual(summary["allowed_next_gate"], NEXT_GATE_BY_PATH[path])

    def test_invalid_path_blocks(self) -> None:
        p10ala = self._write_ready_p10ala()

        summary, exit_code = build_p10alb_owner_select_path(
            self._args(p10ala, selected_path="flatten_everything_now", output_root=self.temp_dir / "out" / "bad"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("selected_path_is_one_of_three", summary["blockers"])
        self.assertEqual(summary["selected_resolution_path"], "")

    def test_blocks_when_p10ala_not_ready(self) -> None:
        p10ala = self._write_ready_p10ala(status="blocked")

        summary, exit_code = build_p10alb_owner_select_path(
            self._args(p10ala, selected_path="wait_for_executable_relation", output_root=self.temp_dir / "out" / "blocked"),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p10ala_review_ready", summary["blockers"])

    def test_wrong_owner_decision_blocks(self) -> None:
        p10ala = self._write_ready_p10ala()

        summary, exit_code = build_p10alb_owner_select_path(
            self._args(
                p10ala,
                selected_path="wait_for_executable_relation",
                output_root=self.temp_dir / "out" / "wrong-owner",
                owner_decision="approve_and_execute",
            ),
            now_fn=lambda: _NOW,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p10alb_recorded", summary["blockers"])

    def _args(
        self,
        p10ala_summary: Path,
        *,
        selected_path: str,
        output_root: Path,
        owner_decision: str = APPROVE_P10ALB,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            p10ala_summary=str(p10ala_summary),
            selected_path=selected_path,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p10ala(self, *, status: str = "ready") -> Path:
        path = self.temp_dir / "p10ala_summary.json"
        path.write_text(
            json.dumps(
                {
                    "contract_version": "hv_balanced_12factor_p10ala_review_position_relation_resolution_proposal.v1",
                    "status": status,
                    "resolution_path_selection_required": status == "ready",
                    "allowed_next_gate": P10ALB_GATE if status == "ready" else "",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
