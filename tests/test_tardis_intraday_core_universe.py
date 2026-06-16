from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_UNIVERSE_RUNNER = (
    REPO_ROOT
    / "scripts"
    / "quant_research"
    / "parallel_1h"
    / "build_tardis_intraday_liquid_perp_core_universe.py"
)


def test_intraday_core_universe_freeze_writes_scope_artifacts(tmp_path: Path) -> None:
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
            pit_candidate("NEW", 57, first_perp_bar_utc="2026-06-02T00:00:00Z"),
            pit_candidate("YOUNG", 58, listing_age_days_as_of=30),
        ],
        payload_overrides={"top100_complete": True},
    )
    output_root = tmp_path / "core_universe"

    result = subprocess.run(
        [
            sys.executable,
            str(CORE_UNIVERSE_RUNNER),
            "--as-of",
            "unit-test-core-v1",
            "--source-universe",
            str(source_path),
            "--proof-from-date",
            "2026-06-01",
            "--proof-to-date",
            "2026-06-02",
            "--target-symbols",
            "12",
            "--min-symbols",
            "12",
            "--min-non-btc-eth-symbols",
            "8",
            "--min-liquidity-buckets",
            "3",
            "--distinct-months-min",
            "1",
            "--bucket-targets",
            "top_liquidity=4,mid_liquidity=4,tail_liquidity=4",
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    summary_path = output_root / "intraday_liquid_perp_core_universe_summary.json"
    selection_path = output_root / "intraday_liquid_perp_core_universe_selection.json"
    staging_plan_path = output_root / "intraday_liquid_perp_core_universe_staging_plan.json"
    assert summary_path.exists()
    assert selection_path.exists()
    assert staging_plan_path.exists()
    assert (output_root / "intraday_liquid_perp_core_universe_symbols.csv").exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "frozen_scope_passed_stage_a_ready"
    assert summary["selected_symbol_count"] == 12
    assert summary["non_btc_eth_symbol_count"] == 10
    assert sorted(summary["liquidity_buckets"]) == ["mid_liquidity", "tail_liquidity", "top_liquidity"]
    assert summary["stage_a_universe_scope_ready"] is True
    assert summary["historical_stage_a_scope_ready"] is True
    assert summary["generalized_intraday_baseline_allowed"] is False
    assert summary["stage_a_proof_computed"] is False
    assert summary["stage_b_return_ablation_allowed"] is False
    assert summary["strategy_pnl_computed"] is False
    assert summary["trading_action_authorized"] is False
    assert summary["downloads_executed_by_runner"] is False
    assert summary["raw_scan_executed_by_runner"] is False

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    excluded_by_symbol = {item["symbol"]: item["exclude_reason"] for item in selection["excluded"]}
    assert excluded_by_symbol["PEPEUSDT"] == "missing_usdm_symbol"
    assert excluded_by_symbol["USDCUSDT"] == "stablecoin"
    assert excluded_by_symbol["NEWUSDT"] == "first_perp_after_proof_start"
    assert excluded_by_symbol["YOUNGUSDT"] == "listing_age_below_minimum"

    staging_plan = json.loads(staging_plan_path.read_text(encoding="utf-8"))
    assert staging_plan["expected_raw_partition_count"] == 12 * 5 * 2
    assert staging_plan["expected_columnar_partition_count"] == 12 * 2
    assert staging_plan["expected_incremental_raw_partitions_beyond_btc_eth"] == 10 * 5 * 2
    assert staging_plan["stage_a_proof_computed"] is False
    assert staging_plan["trading_action_authorized"] is False
