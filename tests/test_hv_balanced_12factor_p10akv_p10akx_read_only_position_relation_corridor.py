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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10aks_p10aku_revised_nonflat_terms_corridor import (  # noqa: E402
    P10AKU_CONTRACT,
    P10AKV_GATE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10akv_p10akx_read_only_position_relation_corridor import (  # noqa: E402
    P10AKY_RESOLUTION_GATE,
    run_corridor,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    CommandResult,
)


class HvBalanced12FactorP10akvP10akxReadOnlyPositionRelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10akv-p10akx-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_corridor_reviews_fresh_blocked_relation_and_defines_resolution_scope(self) -> None:
        p10aku = self._write_ready_inputs()
        runner = SequenceCommandRunner([_remote_proof(relation="opposite_direction_reduce_existing_long", executable=False)])

        summary, exit_code = run_corridor(
            self._args(
                p10aku_summary=p10aku,
                output_root=self.temp_dir / "proof_artifacts" / "p10akv-ready",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 23, 30, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p10akv_p10akx_read_only_position_relation_corridor_ready"])
        self.assertFalse(summary["fresh_relation_executable_under_revised_terms"])
        self.assertTrue(summary["next_scope_requires_position_relation_resolution"])
        self.assertEqual(summary["allowed_next_gate"], P10AKY_RESOLUTION_GATE)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["live_order_submission_performed"])
        self.assertFalse(summary["timer_path_load_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(runner.call_count, 1)
        self.assertIn("remote_read_only_position_relation_proof", runner.commands[0])

        p10akv_summary = _load_json(Path(summary["steps"][0]["summary"]["path"]))
        self.assertTrue(p10akv_summary["p10akv_read_only_fresh_position_relation_proof_ready"])
        self.assertFalse(p10akv_summary["future_execution_precheck_ready_under_revised_terms"])
        self.assertEqual(
            p10akv_summary["fresh_position_relation"]["relation"],
            "opposite_direction_reduce_existing_long",
        )

    def test_bad_p10aku_blocks_before_remote_command(self) -> None:
        p10aku = self._write_ready_inputs()
        payload = _load_json(p10aku)
        payload["status"] = "blocked"
        payload["blockers"] = ["synthetic"]
        _write_json(p10aku, payload)
        runner = SequenceCommandRunner([])

        summary, exit_code = run_corridor(
            self._args(
                p10aku_summary=p10aku,
                output_root=self.temp_dir / "proof_artifacts" / "p10akv-blocked",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 23, 31, 0, tzinfo=UTC),
            command_runner=runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["blockers"], ["p10akv_blocked"])
        self.assertEqual(runner.call_count, 0)
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(self, *, p10aku_summary: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            p10aku_summary=str(p10aku_summary),
            remote_host="root@203.0.113.10",
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            expected_egress_ip="203.0.113.10",
            ssh_connect_timeout=10,
            owner="rulebook_owner",
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> Path:
        root = self.temp_dir / "inputs"
        terms = root / "p10akt" / "proof" / "execution_terms.json"
        p10akt = root / "p10akt" / "summary.json"
        p10aku = root / "p10aku" / "summary.json"
        _write_json(
            terms,
            {
                "contract_version": "hv_balanced_12factor_p10akt_revised_nonflat_canary_terms.v1",
                "status": "ready",
                "symbol": "BTCUSDT",
                "current_retained_position_relation": {"candidate_side": "SELL"},
                "allowed_position_relations": [
                    "flat_position_canary",
                    "same_direction_long_add",
                    "same_direction_short_add",
                ],
                "blocked_position_relations": [
                    "opposite_direction_reduce_existing_long",
                    "opposite_direction_reduce_existing_short",
                    "crossing_or_flipping_existing_position",
                    "unknown_or_unsupported_position_relation",
                ],
                "pre_submit_position_relation_required": True,
                "fresh_read_only_position_relation_proof_required_before_future_execution_gate": True,
                "does_not_authorize_execution": True,
                "market_orders_allowed": False,
                "continuous_automation": False,
            },
        )
        _write_json(p10akt, {"status": "ready", "output_files": {"execution_terms": str(terms)}})
        _write_json(
            p10aku,
            {
                "contract_version": P10AKU_CONTRACT,
                "status": "ready",
                "blockers": [],
                "p10aku_review_revised_nonflat_terms_ready": True,
                "terms_sufficient_for_future_read_only_position_relation_proof": True,
                "allowed_next_gate": P10AKV_GATE,
                "allowed_next_gate_must_be_separately_requested": True,
                "live_order_submission_authorized": False,
                "remote_execution_performed": False,
                "orders_submitted": 0,
                "source_evidence": {
                    "execution_terms": {"path": str(terms)},
                    "p10akt_summary": {"path": str(p10akt)},
                },
            },
        )
        return p10aku


class SequenceCommandRunner:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.commands: list[str] = []

    @property
    def call_count(self) -> int:
        return len(self.commands)

    def __call__(self, args: object) -> CommandResult:
        command = " ".join(str(item) for item in list(args))
        self.commands.append(command)
        if not self.payloads:
            raise AssertionError(f"unexpected command: {command[:300]}")
        return CommandResult(args=list(args), returncode=0, stdout=json.dumps(self.payloads.pop(0)), stderr="")


def _remote_proof(*, relation: str, executable: bool) -> dict[str, object]:
    stability = {
        "remote_live_config_sha256_stable": True,
        "live_supervisor_sha256_stable": True,
        "hook_sha256_stable": True,
        "operator_state_stable": True,
        "systemd_units_stable": True,
    }
    return {
        "contract_version": "hv_balanced_12factor_p10akv_remote_read_only_position_relation_proof.v1",
        "status": "ready",
        "blockers": [],
        "fresh_position_relation": {
            "relation": relation,
            "candidate_side": "SELL",
            "pre_position_amt": "0.013",
            "executable_under_revised_terms": executable,
            "relation_allowed_by_terms": executable,
            "relation_blocked_by_terms": not executable,
            "non_reduce_only_restoration_required": not executable,
            "non_reduce_only_restoration_authorized": False,
        },
        "fresh_relation_executable_under_revised_terms": executable,
        "fresh_open_order_count": 0,
        "fresh_open_order_count_zero": True,
        "control_stability": stability,
        "side_effects": {
            "http_methods_used": ["GET"],
            "only_http_get_endpoints": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "remote_files_written": 0,
            "remote_sync_performed": False,
            "timer_path_invoked": False,
            "supervisor_invoked": False,
            "candidate_executed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
        },
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
