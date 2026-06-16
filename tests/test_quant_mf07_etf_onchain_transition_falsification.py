from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_mf07_etf_onchain_transition_falsification import (
    _add_sidecar_transition_flags,
    _decision,
    _stage0_pass,
)


def test_mf07_sidecar_transition_flags_require_participant_and_pit_context() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1, 2, 3],
            "mf07_any_participant_stress_flag": [True, True, False],
            "mf07_high_abs_tt_retail_gap_flag": [True, False, False],
            "mf07_low_top_global_corr_flag": [False, True, False],
            "mf07_high_tt_velocity_flag": [False, False, True],
            "total_btc_eth_etf_flow_usd_10d_sum": [-10.0, 10.0, -10.0],
            "total_btc_eth_etf_flow_usd_z30": [-1.2, 1.1, -0.5],
            "whale_net_to_exchange_usd_z30": [0.2, -1.3, 1.4],
            "whale_transfer_total_usd_z30": [0.0, 0.0, 2.0],
            "exchange_transfer_total_usd_z30": [None, 1.5, 0.0],
        }
    )

    out, meta = _add_sidecar_transition_flags(frame)

    assert out["cg_risk_off_state"].tolist() == [True, False, True]
    assert out["cg_risk_on_state"].tolist() == [False, True, False]
    assert out["r7_any_mf07_stress_cg_risk_off_flag"].tolist() == [True, False, False]
    assert out["r7_any_mf07_stress_cg_risk_on_flag"].tolist() == [False, True, False]
    assert out["r7_high_gap_cg_risk_off_flag"].tolist() == [True, False, False]
    assert out["r7_low_corr_cg_risk_off_flag"].tolist() == [False, False, False]
    assert meta["exchange_activity_quarantined"] is True


def test_mf07_transition_stage0_pass_requires_edge_change_and_entered_quality() -> None:
    payload = {
        "vs_spk_raw": {"short_basket_edge_vs_baseline_10d": 0.001},
        "selection_vs_spk_raw": {
            "changed_timestamp_fraction": 0.06,
            "entered_edge_vs_exited_10d": 0.01,
        },
    }

    assert _stage0_pass(
        payload,
        target_horizon_bars=10,
        min_edge_vs_raw_spk=0.0005,
        min_changed_timestamp_fraction=0.05,
        min_entered_edge_vs_exited=0.0,
    )

    payload["selection_vs_spk_raw"]["changed_timestamp_fraction"] = 0.01
    assert not _stage0_pass(
        payload,
        target_horizon_bars=10,
        min_edge_vs_raw_spk=0.0005,
        min_changed_timestamp_fraction=0.05,
        min_entered_edge_vs_exited=0.0,
    )


def test_mf07_transition_decision_fail_closes_without_stage0_survivors() -> None:
    decision = _decision(
        evaluations={"candidate": {"stage0_pass": False}},
        strict_results={"candidate": {"status": "not_run", "blocker_codes": ["stage0_not_positive"]}},
    )

    assert decision["status"] == "failed"
    assert decision["alpha_rerun_allowed"] is False
    assert decision["manifest_ab_allowed"] is False
    assert decision["strict_cleared_variants"] == []
    assert "no_stage0_positive_mf07_etf_onchain_transition" in decision["blocker_codes"]
