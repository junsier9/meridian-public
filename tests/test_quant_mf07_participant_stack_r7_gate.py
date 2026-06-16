from __future__ import annotations

import pandas as pd

from scripts.quant_research.audit_mf07_participant_stack_r7_gate import (
    _decision,
    _feature_group_coverage,
    _stage0_admission_summary,
)


def test_mf07_feature_group_coverage_reports_missing_and_min_coverage() -> None:
    frame = pd.DataFrame(
        {
            "top": [1.0, 2.0, None],
            "global": [1.0, 2.0, 3.0],
        }
    )

    coverage = _feature_group_coverage(
        frame,
        groups={"toy": ["top", "global", "missing"]},
    )

    assert coverage["toy"]["present_columns"] == ["top", "global"]
    assert coverage["toy"]["missing_columns"] == ["missing"]
    assert coverage["toy"]["present_fraction"] == 2 / 3
    assert coverage["toy"]["min_non_null_coverage"] == 2 / 3


def test_mf07_stage0_admission_requires_edge_changed_and_entered_quality() -> None:
    report = {
        "target_horizon_bars": 10,
        "evaluation": {
            "spk_raw": {},
            "good": {
                "vs_spk_raw": {
                    "short_basket_edge_vs_baseline_10d": 0.001,
                    "verdict": "stage0_positive",
                },
                "selection_vs_spk_raw": {
                    "changed_timestamp_fraction": 0.10,
                    "entered_edge_vs_exited_10d": 0.01,
                },
            },
            "too_sparse": {
                "vs_spk_raw": {
                    "short_basket_edge_vs_baseline_10d": 0.002,
                    "verdict": "stage0_positive",
                },
                "selection_vs_spk_raw": {
                    "changed_timestamp_fraction": 0.01,
                    "entered_edge_vs_exited_10d": 0.03,
                },
            },
        },
    }

    summary = _stage0_admission_summary(
        report,
        min_changed_timestamp_fraction=0.05,
        min_edge_vs_raw_spk=0.0005,
    )

    assert summary["kept_variant_count"] == 1
    assert summary["kept_variants"][0]["label"] == "good"


def test_mf07_decision_blocks_when_current_forms_fail_and_sidecars_missing() -> None:
    decision = _decision(
        daily_admission={"kept_variant_count": 0},
        subday_admission={"kept_variant_count": 0},
        feature_coverage={
            "top_global_position": {"missing_columns": [], "min_non_null_coverage": 1.0},
            "taker_flow": {"missing_columns": [], "min_non_null_coverage": 1.0},
            "cex_transfer_direction_partial": {"missing_columns": ["x"], "min_non_null_coverage": 0.0},
            "whale_transfer_direction_partial": {"missing_columns": ["y"], "min_non_null_coverage": 0.0},
            "etf_flow_regime": {"missing_columns": ["z"], "min_non_null_coverage": 0.0},
        },
        sidecars={
            "coinglass_etf_daily_state": {"exists": False},
            "coinglass_onchain_exchange_transfers": {"exists": False},
            "coinglass_whale_transfers": {"exists": False},
        },
        min_feature_coverage=0.90,
    )

    assert decision["alpha_rerun_allowed"] is False
    assert "daily_top_global_mf07_no_stage0_survivor" in decision["blocker_codes"]
    assert "missing_pit_etf_daily_sidecar" in decision["blocker_codes"]
    assert "etf_flow_regime_missing_required_columns" in decision["blocker_codes"]


def test_mf07_decision_distinguishes_sidecars_from_feature_integration() -> None:
    decision = _decision(
        daily_admission={"kept_variant_count": 1},
        subday_admission={"kept_variant_count": 1},
        feature_coverage={
            "cex_transfer_direction_partial": {"missing_columns": ["x"], "min_non_null_coverage": 0.0},
            "whale_transfer_direction_partial": {"missing_columns": ["y"], "min_non_null_coverage": 0.0},
            "etf_flow_regime": {"missing_columns": ["z"], "min_non_null_coverage": 0.0},
        },
        sidecars={
            "coinglass_etf_daily_state": {"exists": True},
            "coinglass_onchain_exchange_transfers": {"exists": True},
            "coinglass_whale_transfers": {"exists": True},
        },
        min_feature_coverage=0.90,
    )

    blockers = set(decision["blocker_codes"])
    assert "missing_pit_etf_daily_sidecar" not in blockers
    assert "etf_flow_regime_missing_required_columns" not in blockers
    assert "etf_flow_regime_sidecar_not_integrated_into_feature_panel" in blockers
    assert "cex_transfer_direction_partial_sidecar_not_integrated_into_feature_panel" in blockers
