from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_2_etf_onchain_sidecar_falsification import (
    _build_decision,
    _build_sidecar_states,
    _derive_candidate_states,
    _pre_registered_sidecar_specs,
)


def test_m3_2_coinglass_sidecar_states_are_pit_missing_fail_closed() -> None:
    frame = pd.DataFrame(
        {
            "total_btc_eth_etf_flow_usd_10d_sum": [100.0, -50.0, None],
            "total_btc_eth_etf_flow_usd_z30": [1.5, -1.5, None],
            "whale_net_to_exchange_usd_z30": [-1.2, 1.3, None],
            "exchange_transfer_total_usd_z30": [0.2, 1.4, None],
        }
    )

    out = _build_sidecar_states(frame)

    assert out["cg_etf_10d_inflow_confirm_state"].tolist() == [1.0, 0.0, 0.0]
    assert out["cg_etf_10d_outflow_confirm_state"].tolist() == [0.0, 1.0, 0.0]
    assert out["cg_whale_to_exchange_stress_state"].tolist() == [0.0, 1.0, 0.0]
    assert out["cg_exchange_activity_shock_quarantine_state"].tolist() == [0.0, 1.0, 0.0]
    assert out["cg_participant_risk_off_confirm_state"].tolist() == [0.0, 1.0, 0.0]


def test_m3_2_coinglass_candidate_state_narrows_base_boundary() -> None:
    spec = _pre_registered_sidecar_specs()[0]
    frame = pd.DataFrame(
        {
            spec.base_state_column: [1.0, 1.0, 0.0, 1.0],
            spec.confirm_state_column: [1.0, 0.0, 1.0, None],
        }
    )

    out = _derive_candidate_states(frame, [spec])

    assert out[spec.derived_state_column].tolist() == [1.0, 0.0, 0.0, 0.0]


def test_m3_2_coinglass_specs_keep_exchange_feed_quarantined() -> None:
    confirm_columns = {spec.confirm_state_column for spec in _pre_registered_sidecar_specs()}

    assert "cg_exchange_activity_shock_quarantine_state" not in confirm_columns
    assert {
        "tron_impulse_short_high_beta_rs",
        "tron_heat_short_high_rs",
        "rebound_long_idio",
        "sell_pressure_short_high_beta_rs",
    } == {spec.parent_label for spec in _pre_registered_sidecar_specs()}


def test_m3_2_coinglass_decision_fail_closes_failed_strict_gate() -> None:
    decision = _build_decision(
        stage0_evaluations={
            "candidate_a": {"comparison_vs_parent": {"verdict": "stage0_positive"}},
            "candidate_b": {"comparison_vs_parent": {"verdict": "stage0_at_par"}},
        },
        strict_results={
            "candidate_a": {
                "status": "failed",
                "blocker_codes": ["liquidity_bucket_consistency_failed"],
            },
            "candidate_b": {"status": "not_run", "blocker_codes": ["stage0_not_positive"]},
        },
    )

    assert decision["status"] == "failed"
    assert decision["alpha_rerun_allowed"] is False
    assert decision["manifest_ab_allowed"] is False
    assert decision["stage0_positive_variants"] == ["candidate_a"]
    assert decision["strict_cleared_variants"] == []
    assert "candidate_a_liquidity_bucket_consistency_failed" in decision["blocker_codes"]
