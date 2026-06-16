from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLLING_PIT_RUNNER = (
    REPO_ROOT
    / "scripts"
    / "quant_research"
    / "parallel_1h"
    / "build_tardis_intraday_rolling_pit_core_universe_plan.py"
)


def test_rolling_pit_monthly_freeze_dry_run_writes_plan_artifacts(tmp_path: Path) -> None:
    source_root = tmp_path / "quant_inputs"
    source_root.mkdir(parents=True)
    source_path = write_pit_quant_input(
        root=source_root,
        as_of="2026-05-31",
        candidates=[
            pit_candidate("BTC", 1),
            pit_candidate("ETH", 2),
            pit_candidate("SOL", 3),
            pit_candidate("XRP", 4),
            pit_candidate("DOGE", 21),
            pit_candidate("BNB", 22),
            pit_candidate("ADA", 23),
            pit_candidate("LINK", 24),
            pit_candidate("NEAR", 51),
            pit_candidate("UNI", 52),
            pit_candidate("AAVE", 53),
            pit_candidate("LTC", 54),
            pit_candidate("PEPE", 55, usdm_symbol=None),
            pit_candidate("USDC", 56, is_stablecoin=True),
        ],
        payload_overrides={"top100_complete": True},
    )
    output_root = tmp_path / "rolling_pit_plan"

    result = subprocess.run(
        [
            sys.executable,
            str(ROLLING_PIT_RUNNER),
            "--as-of",
            "unit-test-rolling-pit-v1",
            "--source-universe",
            str(source_path),
            "--evaluation-from-month",
            "2025-01",
            "--evaluation-to-month",
            "2025-02",
            "--latest-partial-month-end",
            "2025-02-28",
            "--target-symbols",
            "12",
            "--min-symbols",
            "12",
            "--min-non-btc-eth-symbols",
            "8",
            "--min-liquidity-buckets",
            "3",
            "--distinct-months-min",
            "2",
            "--bucket-targets",
            "top_liquidity=4,mid_liquidity=4,tail_liquidity=4",
            "--partition-plan-detail",
            "summary",
            "--partition-sample-limit",
            "5",
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    summary_path = output_root / "rolling_pit_core_stage_a_summary.json"
    freeze_plan_path = output_root / "rolling_pit_core_monthly_freeze_plan.json"
    raw_manifest_path = output_root / "rolling_pit_core_raw_staging_manifest.json"
    normalized_manifest_path = output_root / "rolling_pit_core_normalized_manifest.json"
    input_audit_path = output_root / "rolling_pit_core_stage_a_input_audit.json"

    assert summary_path.exists()
    assert freeze_plan_path.exists()
    assert raw_manifest_path.exists()
    assert normalized_manifest_path.exists()
    assert input_audit_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "dry_run_plan_written_waiting_for_monthly_raw_selection_metrics"
    assert summary["evaluation_month_count"] == 2
    assert summary["candidate_seed_symbol_count"] == 12
    assert summary["monthly_freeze_artifact_count"] == 2
    assert summary["dry_run_only"] is True
    assert summary["candidate_seed_pit_valid_for_historical_selection"] is False
    assert summary["stage_a_monthly_universe_masks_ready"] is False
    assert summary["downloads_executed_by_runner"] is False
    assert summary["raw_scan_executed_by_runner"] is False
    assert summary["normalization_executed_by_runner"] is False
    assert summary["stage_a_proof_computed"] is False
    assert summary["stage_b_return_ablation_allowed"] is False
    assert summary["strategy_pnl_computed"] is False
    assert summary["trading_action_authorized"] is False
    assert "monthly_raw_selection_metrics_present" in summary["blocking_gates"]

    freeze_plan = json.loads(freeze_plan_path.read_text(encoding="utf-8"))
    assert freeze_plan["months"][0]["evaluation_month"] == "2025-01"
    assert freeze_plan["months"][0]["freeze_date"] == "2024-12-31"
    assert freeze_plan["months"][0]["selection_lookback_start"] == "2024-10-03"
    assert freeze_plan["months"][1]["evaluation_month"] == "2025-02"
    assert freeze_plan["months"][1]["freeze_date"] == "2025-01-31"
    assert freeze_plan["months"][1]["selection_lookback_start"] == "2024-11-03"

    jan_audit_path = output_root / "monthly_freezes" / "2025-01" / "monthly_universe_selection_audit.json"
    jan_symbols_path = output_root / "monthly_freezes" / "2025-01" / "selected_symbols.csv"
    assert jan_audit_path.exists()
    assert jan_symbols_path.exists()
    jan_audit = json.loads(jan_audit_path.read_text(encoding="utf-8"))
    assert jan_audit["selection_status"] == "dry_run_proxy_selection_not_pit_valid_pending_monthly_raw_metrics"
    assert jan_audit["stage_a_monthly_universe_mask_ready"] is False
    assert jan_audit["selected_symbol_count_stage_a_eligible"] == 0
    assert "stage_a_eligible" in jan_symbols_path.read_text(encoding="utf-8").splitlines()[0]

    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    assert raw_manifest["manifest_kind"] == "dry_run_raw_staging_plan_no_download"
    assert raw_manifest["partition_records_materialized"] is False
    assert len(raw_manifest["sample_partitions"]) == 5
    assert raw_manifest["planned_non_dedup_raw_partition_count"] == 12_180
    assert raw_manifest["planned_unique_raw_partition_count"] == 7_860
    assert raw_manifest["monthly_plans"][0]["selection_raw_partition_count"] == 12 * 90 * 4
    assert raw_manifest["monthly_plans"][0]["evaluation_raw_partition_count"] == 12 * 31 * 5
    assert raw_manifest["monthly_plans"][1]["selection_raw_partition_count"] == 12 * 90 * 4
    assert raw_manifest["monthly_plans"][1]["evaluation_raw_partition_count"] == 12 * 28 * 5
    assert raw_manifest["downloads_executed_by_runner"] is False
    assert raw_manifest["raw_scan_executed_by_runner"] is False

    normalized_manifest = json.loads(normalized_manifest_path.read_text(encoding="utf-8"))
    assert normalized_manifest["manifest_kind"] == "dry_run_normalized_columnar_plan_no_normalization"
    assert normalized_manifest["planned_candidate_seed_normalized_partition_count"] == 12 * (31 + 28)
    assert normalized_manifest["normalization_executed_by_runner"] is False
    assert normalized_manifest["stage_a_proof_computed"] is False

    input_audit = json.loads(input_audit_path.read_text(encoding="utf-8"))
    assert input_audit["input_mode"] == "not_run_dry_run_plan_only"
    assert input_audit["stage_a_monthly_universe_masks_ready"] is False
    assert input_audit["stage_a_proof_computed"] is False
