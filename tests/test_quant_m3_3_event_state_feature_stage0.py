from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_3_event_state_feature_stage0 import _add_event_state_features


def test_add_event_state_features_builds_quality_and_noise_scores() -> None:
    frame = pd.DataFrame(
        {
            "m3_3_event_tape_hype_count_10d": [2.0, 0.0],
            "m3_3_event_tape_confirmed_short_veto_count_10d": [1.0, 0.0],
            "m3_3_event_tape_real_repricing_count_10d": [2.0, 0.0],
            "m3_3_event_tape_short_veto_count_10d": [1.0, 0.0],
            "m3_3_event_tape_any_actionable_count_10d": [4.0, 0.0],
            "m3_3_event_tape_max_subject_link_strength_10d": [3.0, 0.0],
            "m3_3_event_tape_max_market_impact_magnitude_10d": [2.0, 0.0],
        }
    )

    out = _add_event_state_features(frame)

    assert out["m3_3_event_state_hype_pressure_v1"].tolist() == [2.0, 0.0]
    assert out["m3_3_event_state_confirmed_quality_v1"].tolist() == [4.0, 0.0]
    assert out["m3_3_event_state_noise_ratio_v1"].tolist() == [0.5, 0.0]
    assert out["m3_3_event_state_short_quality_v1"].round(6).tolist() == [1.0, 0.0]
