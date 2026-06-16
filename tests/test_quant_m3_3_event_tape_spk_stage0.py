from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.quant_research.evaluate_m3_3_event_tape_spk_stage0 import _explode_news_tape


def test_explode_news_tape_handles_numpy_currency_arrays() -> None:
    news = pd.DataFrame(
        [
            {
                "currencies": np.asarray(["ETH", "LINK"]),
                "research_effective_at_utc": "2026-01-02T00:00:00Z",
                "final_short_veto_flag": True,
                "final_repricing_type": "real_repricing",
                "final_market_impact_direction": "bullish",
                "final_market_impact_magnitude": 3.0,
                "final_subject_link_strength": 4.0,
                "final_is_actionable_event": True,
                "final_event_type": "etf",
                "final_news_kind": "hard_event",
            }
        ]
    )

    tape = _explode_news_tape(news, lookback_days=2)

    assert set(tape["subject"]) == {"ETH", "LINK"}
    assert set(tape["date_utc"]) == {"2026-01-02", "2026-01-03"}
    assert int(tape["m3_3_event_tape_confirmed_short_veto_flag_10d"].sum()) == 4
