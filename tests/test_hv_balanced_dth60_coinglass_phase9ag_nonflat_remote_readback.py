from __future__ import annotations

import json
from datetime import UTC, datetime
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9af_nonflat_execution_owner_gate import (  # noqa: E402
    P9AG_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    build_nonflat_position_reference_fixture,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    nonflat_account_read_ready,
    order_fill_trade_delta_zero,
    p9af_ready_for_p9ag,
    position_fingerprint_ready,
    position_fingerprints_stable,
    remote_p9ag_p9aa_command,
    remote_python_invocation,
)


class Phase9AGNonflatRemoteReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ag-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_nonflat_account_read_accepts_only_existing_position_blocker(self) -> None:
        self.assertTrue(nonflat_account_read_ready(_account_read(blockers=["mainnet_open_positions_exist:11"])))

    def test_nonflat_account_read_rejects_open_orders_and_extra_blockers(self) -> None:
        self.assertFalse(
            nonflat_account_read_ready(
                _account_read(
                    blockers=["mainnet_open_positions_exist:11", "mainnet_open_orders_exist:1"],
                    open_orders=1,
                )
            )
        )
        self.assertFalse(
            nonflat_account_read_ready(
                _account_read(blockers=["mainnet_open_positions_exist:11", "egress_ip_mismatch"])
            )
        )

    def test_position_fingerprints_require_stable_position_order_and_trade_hashes(self) -> None:
        pre = _fingerprint(position_hash="pos-a", order_hash="orders-a", trade_hash="trades-a")
        post = _fingerprint(position_hash="pos-a", order_hash="orders-a", trade_hash="trades-a")
        changed_trade = _fingerprint(position_hash="pos-a", order_hash="orders-a", trade_hash="trades-b")
        changed_position = _fingerprint(position_hash="pos-b", order_hash="orders-a", trade_hash="trades-a")

        self.assertTrue(position_fingerprint_ready(pre))
        self.assertTrue(position_fingerprints_stable(pre, post))
        self.assertFalse(position_fingerprints_stable(pre, changed_trade))
        self.assertFalse(position_fingerprints_stable(pre, changed_position))

    def test_zero_delta_requires_no_p9aa_orders_or_fills(self) -> None:
        pre = _fingerprint(position_hash="pos-a", order_hash="orders-a", trade_hash="trades-a")
        post = _fingerprint(position_hash="pos-a", order_hash="orders-a", trade_hash="trades-a")
        self.assertTrue(order_fill_trade_delta_zero(pre, post, {"orders_submitted": 0, "fill_count": 0}))
        self.assertFalse(order_fill_trade_delta_zero(pre, post, {"orders_submitted": 1, "fill_count": 0}))
        self.assertFalse(order_fill_trade_delta_zero(pre, post, {"orders_submitted": 0, "fill_count": 1}))

    def test_p9af_ready_for_p9ag_requires_prior_gate_to_remain_non_executing(self) -> None:
        ready = _p9af_summary(self.temp_dir, p9ag_authorized=False)
        self.assertTrue(p9af_ready_for_p9ag(ready))

        bad = _p9af_summary(self.temp_dir, p9ag_authorized=True)
        self.assertFalse(p9af_ready_for_p9ag(bad))

    def test_remote_python_invocation_uses_live_runner_venv_contract(self) -> None:
        command = remote_python_invocation(
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
        )

        self.assertIn("/root/meridian_alpha_live_runner/bin/with-live-env", command)
        self.assertIn("PYTHONPATH=/root/meridian_alpha_live_runner/repo/src", command)
        self.assertIn("VIRTUAL_ENV=/root/meridian_alpha_live_runner/venv", command)
        self.assertIn("PATH=/root/meridian_alpha_live_runner/venv/bin:", command)
        self.assertTrue(command.endswith("/root/meridian_alpha_live_runner/venv/bin/python"))

    def test_nonflat_reference_fixture_is_built_from_past_pre_fingerprint(self) -> None:
        source = self.temp_dir / "position_fingerprint_pre.json"
        _write_json(source, _position_source("2026-06-07T03:00:00Z"))

        reference, summary, blockers = build_nonflat_position_reference_fixture(
            source_path=source,
            proof_root=self.temp_dir / "proof_artifacts" / "p9aa" / "run",
            run_id="20260607T030100Z",
            generated_at=datetime(2026, 6, 7, 3, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(blockers, [])
        self.assertTrue(str(reference).endswith("-genesis-snapshot"))
        self.assertTrue((reference / "run_summary.json").exists())
        self.assertTrue((reference / "reference_positions.csv").exists())
        self.assertEqual(summary["status"], "position_genesis_snapshot")
        self.assertTrue(summary["read_only"])
        self.assertTrue(summary["proof_artifacts_only"])
        self.assertTrue(summary["source_created_before_p9aa"])
        self.assertEqual(summary["expected_position_count"], 1)
        self.assertIn("BTCUSDT", (reference / "reference_positions.csv").read_text(encoding="utf-8"))

    def test_nonflat_reference_fixture_rejects_future_source(self) -> None:
        source = self.temp_dir / "position_fingerprint_pre.json"
        _write_json(source, _position_source("2026-06-07T03:02:00Z"))

        _reference, _summary, blockers = build_nonflat_position_reference_fixture(
            source_path=source,
            proof_root=self.temp_dir / "proof_artifacts" / "p9aa" / "run",
            run_id="20260607T030100Z",
            generated_at=datetime(2026, 6, 7, 3, 1, 0, tzinfo=UTC),
        )

        self.assertIn("position_reference_source_not_point_in_time_safe", blockers)

    def test_remote_p9aa_command_passes_position_reference_source(self) -> None:
        command = remote_p9ag_p9aa_command(
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_live_env="/root/meridian_alpha_live_runner/bin/with-live-env",
            remote_python="/root/meridian_alpha_live_runner/venv/bin/python",
            remote_p9z_summary="/tmp/p9z.json",
            remote_config="/tmp/config.yaml",
            remote_p9aa_output="/tmp/p9aa",
            remote_position_reference_source="/tmp/position_fingerprint_pre.json",
            shadow_cycles=3,
        )

        self.assertIn("--position-reference-source /tmp/position_fingerprint_pre.json", command)
        self.assertIn("/root/meridian_alpha_live_runner/venv/bin/python", command)


def _account_read(*, blockers: list[str], open_orders: int = 0, open_positions: int = 11) -> dict[str, object]:
    return {
        "account_readable": True,
        "can_trade": True,
        "position_mode": "one_way",
        "egress_ip": "203.0.113.10",
        "expected_egress_ip": "203.0.113.10",
        "open_order_count": open_orders,
        "open_position_count": open_positions,
        "blockers": blockers,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }


def _fingerprint(*, position_hash: str, order_hash: str, trade_hash: str) -> dict[str, object]:
    rows = [
        {
            "symbol": "BTCUSDT",
            "positionSide": "BOTH",
            "positionAmt": "0.001",
            "entryPrice": "60000",
            "breakEvenPrice": "60000",
            "isolated": "false",
            "isolatedWallet": "0",
        }
    ]
    return {
        "status": "ready",
        "blockers": [],
        "account_readable": True,
        "position_mode": "one_way",
        "open_order_count": 0,
        "open_position_count": 1,
        "position_fingerprint": {
            "stable_hash": position_hash,
            "stable_rows": rows,
        },
        "order_history_fingerprint": {
            "history_hash": order_hash,
            "history": {"BTCUSDT": []},
        },
        "trade_history_fingerprint": {
            "history_hash": trade_hash,
            "history": {"BTCUSDT": []},
        },
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }


def _position_source(finished_at_utc: str) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ag_position_fingerprint.v1",
        "status": "ready",
        "blockers": [],
        "finished_at_utc": finished_at_utc,
        "open_order_count": 0,
        "open_position_count": 1,
        "position_fingerprint": {
            "stable_hash": "pos-a",
            "stable_rows": [
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "BOTH",
                    "positionAmt": "0.001",
                    "entryPrice": "60000",
                    "breakEvenPrice": "60000",
                    "isolated": "false",
                    "isolatedWallet": "0",
                }
            ],
        },
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }


def _p9af_summary(temp_dir: Path, *, p9ag_authorized: bool) -> dict[str, object]:
    matrix_path = temp_dir / ("p9af_matrix_authorized.json" if p9ag_authorized else "p9af_matrix_ready.json")
    _write_json(
        matrix_path,
        {
            "allowed_next_gate": P9AG_GATE,
            "p9ag_must_follow_p9ad_and_p9ae_contracts": True,
            "p9ag_acceptance_requirements": {
                "fresh_remote_account_read_same_run": True,
                "position_fingerprint_stability": True,
                "zero_open_orders_pre_and_post": True,
                "orders_submitted_delta": 0,
                "orders_canceled_delta": 0,
                "fills_delta": 0,
                "account_trade_delta": 0,
                "baseline_only_executor_input": True,
                "candidate_shadow_artifact_only": True,
                "remote_control_boundary_unchanged": True,
                "production_timer_service_loaded_or_modified": False,
            },
            "current_gate_authorizations": {
                "p9ag_execution": p9ag_authorized,
                "remote_sync": False,
                "remote_execution": False,
                "candidate_execution": False,
                "live_order_submission": False,
            },
        },
    )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9af_nonflat_execution_owner_gate.v1",
        "status": "ready",
        "blockers": [],
        "p9af_nonflat_execution_owner_gate_ready": True,
        "review_scope_discusses_actual_execution": True,
        "eligible_for_future_p9ag_nonflat_readback_execution_gate": True,
        "allowed_next_gate": P9AG_GATE,
        "nonflat_remote_no_order_readback_execution_authorized": False,
        "p9ag_execution_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "gates": {
            "p9ae_owner_gate_ready": True,
            "p9ag_execution_not_authorized_in_p9af": True,
            "remote_sync_not_authorized_in_p9af": True,
            "remote_execution_not_authorized_in_p9af": True,
        },
        "output_files": {"execution_decision_matrix": str(matrix_path)},
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
