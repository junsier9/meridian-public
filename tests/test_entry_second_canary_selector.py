from __future__ import annotations

import csv
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

from enhengclaw.live_trading.entry_second_canary_selector import (  # noqa: E402
    build_entry_second_canary_selector_result,
    build_owner_payload_template,
    default_selector_contract,
    validate_owner_payload_binding,
)
from scripts.live_trading.run_entry_second_canary_selector_dry_run import (  # noqa: E402
    run_entry_second_canary_selector_dry_run,
)


class EntrySecondCanarySelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="entry-second-selector-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_selector_filters_threshold_jitter_and_selects_deterministic_subset_under_cap(self) -> None:
        sample_1 = self._write_plan("sample-1", active_stage="entry_second", rows=_sample_one_rows())
        sample_2 = self._write_plan("sample-2", active_stage="entry_second", rows=_sample_two_rows())

        result = build_entry_second_canary_selector_result(plan_roots=[sample_1, sample_2])

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["eligible_symbols"], ["AAVEUSDT", "ENAUSDT", "FILUSDT", "ZECUSDT"])
        self.assertEqual(result["selected_symbols"], ["AAVEUSDT", "ENAUSDT"])
        self.assertAlmostEqual(result["selected_turnover_usdt"], 63.70743)
        by_symbol = {row["symbol"]: row for row in result["results_by_symbol"]}
        self.assertEqual(by_symbol["BNBUSDT"]["status"], "filtered")
        self.assertIn("all_required_samples_entry_second", by_symbol["BNBUSDT"]["blockers"])
        self.assertIn("latest_notional_above_buffer", by_symbol["BNBUSDT"]["blockers"])
        self.assertEqual(by_symbol["WLDUSDT"]["status"], "filtered")
        self.assertIn("latest_notional_above_buffer", by_symbol["WLDUSDT"]["blockers"])
        self.assertEqual(by_symbol["XRPUSDT"]["status"], "filtered")

    def test_selector_blocks_when_latest_full_plan_stage_is_reduce_first(self) -> None:
        sample = self._write_plan("reduce-first", active_stage="reduce_first", rows=_reduce_first_rows())

        result = build_entry_second_canary_selector_result(plan_roots=[sample])

        self.assertEqual(result["status"], "blocked")
        self.assertIn("latest_full_plan_stage_not_entry_second:reduce_first", result["blockers"])
        self.assertIn("no_selected_orders_after_filter", result["blockers"])
        self.assertEqual(result["selected_symbols"], [])

    def test_owner_payload_binding_passes_for_template_and_blocks_tampered_hash(self) -> None:
        sample_1 = self._write_plan("sample-1", active_stage="entry_second", rows=_sample_one_rows())
        sample_2 = self._write_plan("sample-2", active_stage="entry_second", rows=_sample_two_rows())
        result = build_entry_second_canary_selector_result(plan_roots=[sample_1, sample_2])

        template = build_owner_payload_template(result)
        binding = validate_owner_payload_binding(owner_payload=template, selector_output=result)
        tampered = dict(template)
        tampered["selector_output_sha256"] = "0" * 64
        tampered_binding = validate_owner_payload_binding(owner_payload=tampered, selector_output=result)

        self.assertEqual(binding["status"], "passed")
        self.assertEqual(tampered_binding["status"], "blocked")
        self.assertIn("selector_output_sha256_mismatch", tampered_binding["blockers"])

    def test_dry_run_gate_writes_owner_template_and_keeps_non_authorizations(self) -> None:
        sample_1 = self._write_plan("sample-1", active_stage="entry_second", rows=_sample_one_rows())
        sample_2 = self._write_plan("sample-2", active_stage="entry_second", rows=_sample_two_rows())

        summary = run_entry_second_canary_selector_dry_run(
            plan_roots=[sample_1, sample_2],
            output_root=self.temp_dir / "out",
            run_label="fixture",
            now=datetime(2026, 6, 11, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["selected_symbols"], ["AAVEUSDT", "ENAUSDT"])
        self.assertFalse(summary["non_authorizations"]["arm_live_delta"])
        self.assertFalse(summary["non_authorizations"]["live_order_submission"])
        self.assertTrue(Path(summary["output_files"]["owner_payload_template"]).exists())

    def _write_plan(self, name: str, *, active_stage: str, rows: list[dict[str, object]]) -> Path:
        root = self.temp_dir / name
        root.mkdir(parents=True, exist_ok=True)
        phase_counts: dict[str, int] = {}
        for row in rows:
            phase = str(row["execution_phase"])
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
        (root / "summary.json").write_text(
            json.dumps(
                {
                    "active_execution_phase": active_stage,
                    "phase_counts": phase_counts,
                    "planned_delta_order_count": int(sum(str(row["execution_phase"]) == active_stage for row in rows)),
                    "risk_gate_status": "passed",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with (root / "order_sizing_report.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(_base_row().keys()))
            writer.writeheader()
            for row in rows:
                payload = _base_row()
                payload.update(row)
                writer.writerow(payload)
        return root


def _base_row() -> dict[str, object]:
    return {
        "seq": 1,
        "symbol": "AAVEUSDT",
        "side": "SELL",
        "execution_phase": "entry_second",
        "delta_classification": "increase_same_side",
        "reduce_only": False,
        "executable": True,
        "blockers": "",
        "rounded_quantity": 0.1,
        "rounded_notional_usdt": 6.0,
        "min_executable_notional_usdt": 5.0,
        "current_position_amt": -45.9,
        "target_position_amt": -46.0,
        "delta_position_amt": -0.1,
    }


def _sample_one_rows() -> list[dict[str, object]]:
    return [
        _row("AAVEUSDT", 1, "SELL", "entry_second", "increase_same_side", True, "", 6.298, 6.273),
        _row("BCHUSDT", 2, "BUY", "dust_noop", "dust_residual", False, "notional_below_min:BCHUSDT", 9.8026267949, 20.0),
        _row(
            "BNBUSDT",
            3,
            "BUY",
            "dust_noop",
            "dust_residual",
            False,
            "notional_below_min:BNBUSDT;quantity_below_min:BNBUSDT",
            0.0,
            5.9785358762,
        ),
        _row("BTCUSDT", 4, "SELL", "dust_noop", "dust_residual", False, "notional_below_min:BTCUSDT;quantity_below_min:BTCUSDT", 0.0, 62.0),
        _row("ENAUSDT", 5, "SELL", "entry_second", "increase_same_side", True, "", 26.24404375, 5.0),
        _row("ETHUSDT", 6, "BUY", "dust_noop", "dust_residual", False, "notional_below_min:ETHUSDT", 11.46474, 20.0),
        _row("FILUSDT", 7, "SELL", "entry_second", "increase_same_side", True, "", 5.928905128, 5.0),
        _row("WLDUSDT", 8, "SELL", "dust_noop", "dust_residual", False, "notional_below_min:WLDUSDT", 4.4244, 5.0),
        _row("XRPUSDT", 9, "BUY", "dust_noop", "dust_residual", False, "notional_below_min:XRPUSDT", 3.3255, 5.0),
        _row("ZECUSDT", 10, "BUY", "entry_second", "increase_same_side", True, "", 17.5476, 5.0),
    ]


def _sample_two_rows() -> list[dict[str, object]]:
    return [
        _row("AAVEUSDT", 1, "SELL", "entry_second", "increase_same_side", True, "", 18.819, 6.273),
        _row("BCHUSDT", 2, "BUY", "dust_noop", "dust_residual", False, "notional_below_min:BCHUSDT", 9.39013, 20.0),
        _row("BNBUSDT", 3, "BUY", "entry_second", "increase_same_side", True, "", 5.9785358762, 5.9785358762),
        _row("BTCUSDT", 4, "SELL", "dust_noop", "dust_residual", False, "notional_below_min:BTCUSDT;quantity_below_min:BTCUSDT", 0.0, 62.3937),
        _row("ENAUSDT", 5, "SELL", "entry_second", "increase_same_side", True, "", 44.88843, 5.0),
        _row("ETHUSDT", 6, "BUY", "dust_noop", "dust_residual", False, "notional_below_min:ETHUSDT", 14.70798, 20.0),
        _row("FILUSDT", 7, "SELL", "entry_second", "increase_same_side", True, "", 27.118, 5.0),
        _row("WLDUSDT", 8, "SELL", "entry_second", "increase_same_side", True, "", 7.314, 5.0),
        _row("XRPUSDT", 9, "BUY", "entry_second", "increase_same_side", True, "", 5.08500284, 5.0),
        _row("ZECUSDT", 10, "BUY", "entry_second", "increase_same_side", True, "", 27.77016, 5.0),
    ]


def _reduce_first_rows() -> list[dict[str, object]]:
    return [
        _row("AAVEUSDT", 1, "BUY", "reduce_first", "reduce_same_side", True, "", 51.4768, 6.4, reduce_only=True),
        _row("ENAUSDT", 5, "BUY", "reduce_first", "reduce_same_side", True, "", 49.0805, 5.0, reduce_only=True),
    ]


def _row(
    symbol: str,
    seq: int,
    side: str,
    phase: str,
    classification: str,
    executable: bool,
    blockers: str,
    notional: float,
    min_executable: float,
    *,
    reduce_only: bool = False,
) -> dict[str, object]:
    return {
        "seq": seq,
        "symbol": symbol,
        "side": side,
        "execution_phase": phase,
        "delta_classification": classification,
        "reduce_only": reduce_only,
        "executable": executable,
        "blockers": blockers,
        "rounded_quantity": 1.0,
        "rounded_notional_usdt": notional,
        "min_executable_notional_usdt": min_executable,
        "current_position_amt": 1.0,
        "target_position_amt": 2.0,
        "delta_position_amt": 1.0,
    }


if __name__ == "__main__":
    unittest.main()
