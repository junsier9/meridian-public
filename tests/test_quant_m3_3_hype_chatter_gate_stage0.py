from __future__ import annotations

import pandas as pd

from enhengclaw.quant_research.features import (
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
)


def _base_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_ms": [1] * 7,
            "date_utc": ["2026-01-02"] * 7,
            "subject": ["A", "B", "C", "D", "E", "F", "G"],
            "liquidity_bucket": [
                "top_liquidity",
                "top_liquidity",
                "top_liquidity",
                "top_liquidity",
                "mid_liquidity",
                "mid_liquidity",
                "mid_liquidity",
            ],
            "post_pump_stall_core_score_3d": [0.0, 0.0, 0.0, 0.0, -5.0, -4.0, -3.0],
            "forward_1d_log_return": [0.0] * 7,
            "forward_10d_log_return": [0.0] * 7,
            "m3_3_event_tape_hype_flag_10d": [0, 0, 0, 0, 1, 0, 0],
        }
    )


def test_hype_candidate_veto_blocks_flagged_replacement_candidate() -> None:
    panel = _base_panel()

    def base_raw_score(frame: pd.DataFrame) -> pd.Series:
        return pd.Series([3.0, 2.0, 1.0, 0.0, 0.1, -0.2, -0.3], index=frame.index)

    no_veto_panel = panel.copy()
    no_veto_panel["m3_3_event_tape_hype_flag_10d"] = 0
    no_veto_score = _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        no_veto_panel,
        base_raw_score_fn=base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
    )
    veto_score = _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        panel,
        base_raw_score_fn=base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="m3_3_event_tape_hype_flag_10d",
    )

    no_veto_shorts = set(panel.assign(score=no_veto_score).sort_values("score", ascending=False).tail(3)["subject"])
    veto_shorts = set(panel.assign(score=veto_score).sort_values("score", ascending=False).tail(3)["subject"])

    assert "E" in no_veto_shorts
    assert "E" not in veto_shorts
    assert "D" in veto_shorts
