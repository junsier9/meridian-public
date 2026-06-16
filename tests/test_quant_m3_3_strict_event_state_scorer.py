from __future__ import annotations

import pandas as pd

from enhengclaw.quant_research.deterministic_core import feature_group_for_column
from enhengclaw.quant_research.feature_admission import feature_admission_status
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score
from enhengclaw.quant_research.falsification_runner import (
    SUPPORTED_INCREMENTAL_MODEL_FAMILIES,
    SUPPORTED_SUBLANE_PARENT_MODEL_FAMILIES,
)
from enhengclaw.quant_research.hypothesis_batch import _materialize_strict_strategy_entry
from enhengclaw.quant_research.lab import _select_strategy_feature_columns


def _selected_shorts(frame: pd.DataFrame) -> set[str]:
    scored = frame.copy()
    scored["score"] = xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score(scored)
    return set(scored.sort_values("score", ascending=False).tail(3)["subject"].astype(str))


def test_m3_3_strict_event_state_scorer_replaces_only_no_hype_tail_candidate() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1] * 8,
            "subject": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "distance_to_high_60": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            "m3_3_event_state_hype_pressure_v1": [0.0] * 8,
            "m3_3_event_state_confirmed_quality_v1": [0.0] * 8,
            "m3_3_event_state_short_quality_v1": [0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0],
            "m3_3_event_state_noise_ratio_v1": [0.0] * 8,
        }
    )

    assert _selected_shorts(frame) == {"E", "F", "G"}

    hype_frame = frame.copy()
    hype_frame.loc[hype_frame["subject"].eq("E"), "m3_3_event_state_hype_pressure_v1"] = 1.0

    assert _selected_shorts(hype_frame) == {"F", "G", "H"}


def test_m3_3_event_state_columns_are_admitted_events() -> None:
    assert feature_group_for_column("m3_3_event_state_short_quality_v1") == "events"
    assert feature_admission_status("m3_3_event_state_short_quality_v1") == "admitted"


def test_m3_3_required_columns_can_be_forced_into_full_validation_selection() -> None:
    selected = _select_strategy_feature_columns(
        strategy_entry={
            "feature_groups": ["structure"],
            "include_required_feature_columns_in_selection": True,
            "required_feature_columns": ["m3_3_event_state_short_quality_v1"],
        },
        numeric_feature_columns=["distance_to_high_60", "m3_3_event_state_short_quality_v1"],
    )

    assert "distance_to_high_60" in selected
    assert "m3_3_event_state_short_quality_v1" in selected


def test_r1a_top_liquidity_ex_trx_is_supported_sublane_wrapper() -> None:
    assert (
        SUPPORTED_SUBLANE_PARENT_MODEL_FAMILIES["r1a_top_liquidity_ex_trx_h10d"]
        == "xs_alpha_ontology_v5_h10d_rw_bridge"
    )


def test_m3_3_required_column_selection_flag_survives_strict_strategy_materialization() -> None:
    strategy = _materialize_strict_strategy_entry(
        {
            "candidate_id": "candidate",
            "base_mechanism_id": "base",
            "horizon_id": "h10d",
            "target_horizon_bars": 10,
            "label_contract_id": "forward_return_execution_aligned.v1",
            "universe_filter": {},
            "model_family": "xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0",
            "strategy_profile": "long_short_rank",
            "feature_selection_mode": "",
            "include_required_feature_columns_in_selection": True,
            "feature_groups": ["events"],
            "required_feature_columns": ["m3_3_event_state_short_quality_v1"],
            "profile_constraints": {},
            "spec_hash": "hash",
            "requires_derivatives_features": False,
            "thesis_profile": {},
        }
    )

    assert strategy["include_required_feature_columns_in_selection"] is True


def test_m3_3_strict_event_state_is_supported_by_statistical_falsification() -> None:
    assert (
        "xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0"
        in SUPPORTED_INCREMENTAL_MODEL_FAMILIES
    )
