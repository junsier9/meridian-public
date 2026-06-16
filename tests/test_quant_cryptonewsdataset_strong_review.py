from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.review_cryptonewsdataset_strong_model import _build_adjudicated_frame, _changed_fields, _safe_list


class QuantCryptoNewsStrongReviewTests(unittest.TestCase):
    def test_changed_fields_detects_differences(self) -> None:
        row = pd.Series(
            {
                "repricing_type": "hype",
                "short_veto_flag": False,
                "event_type": "other",
                "narrative_tags": ["ethereum"],
                "news_kind": "analysis",
                "market_impact_direction": "neutral",
                "market_impact_magnitude": 1,
                "subject_link_strength": 3,
                "tradability_risk": "low",
                "decay_horizon_days": 3,
                "is_actionable_event": False,
                "summary": "mini",
                "rationale": "mini rationale",
            }
        )
        strong_payload = {
            "repricing_type": "real_repricing",
            "short_veto_flag": True,
            "event_type": "other",
            "narrative_tags": ["ethereum"],
            "news_kind": "analysis",
            "market_impact_direction": "bullish",
            "market_impact_magnitude": 4,
            "subject_link_strength": 4,
            "tradability_risk": "medium",
            "decay_horizon_days": 10,
            "is_actionable_event": True,
            "summary": "strong",
            "rationale": "strong rationale",
        }
        changed = _changed_fields(row, strong_payload)
        self.assertIn("repricing_type", changed)
        self.assertIn("short_veto_flag", changed)
        self.assertIn("summary", changed)

    def test_build_adjudicated_frame_prefers_strong_labels_for_reviewed_rows(self) -> None:
        mini = pd.DataFrame(
            [
                {
                    "id": 1,
                    "news_kind": "analysis",
                    "event_type": "other",
                    "market_impact_direction": "neutral",
                    "market_impact_magnitude": 1,
                    "repricing_type": "hype",
                    "subject_link_strength": 2,
                    "tradability_risk": "low",
                    "decay_horizon_days": 3,
                    "is_actionable_event": False,
                    "short_veto_flag": False,
                    "narrative_tags": ["ethereum"],
                    "summary": "mini summary",
                    "rationale": "mini rationale",
                },
                {
                    "id": 2,
                    "news_kind": "reporting",
                    "event_type": "etf",
                    "market_impact_direction": "bullish",
                    "market_impact_magnitude": 4,
                    "repricing_type": "real_repricing",
                    "subject_link_strength": 5,
                    "tradability_risk": "medium",
                    "decay_horizon_days": 20,
                    "is_actionable_event": True,
                    "short_veto_flag": True,
                    "narrative_tags": ["bitcoin", "etf"],
                    "summary": "mini summary 2",
                    "rationale": "mini rationale 2",
                },
            ]
        )
        review = pd.DataFrame(
            [
                {
                    "id": 1,
                    "strong_review_model": "gpt-5",
                    "mini_vs_strong_change_count": 2,
                    "mini_vs_strong_any_change": True,
                    "strong_news_kind": "hard_event",
                    "strong_event_type": "regulatory",
                    "strong_market_impact_direction": "bearish",
                    "strong_market_impact_magnitude": 5,
                    "strong_repricing_type": "real_repricing",
                    "strong_subject_link_strength": 4,
                    "strong_tradability_risk": "high",
                    "strong_decay_horizon_days": 10,
                    "strong_is_actionable_event": True,
                    "strong_short_veto_flag": True,
                    "strong_narrative_tags": ["ethereum", "regulation"],
                    "strong_summary": "strong summary",
                    "strong_rationale": "strong rationale",
                }
            ]
        )
        adjudicated = _build_adjudicated_frame(mini, review)
        reviewed = adjudicated.loc[adjudicated["id"].eq(1)].iloc[0]
        untouched = adjudicated.loc[adjudicated["id"].eq(2)].iloc[0]
        self.assertEqual(reviewed["final_label_source"], "strong_review")
        self.assertEqual(reviewed["final_repricing_type"], "real_repricing")
        self.assertEqual(reviewed["final_short_veto_flag"], True)
        self.assertEqual(untouched["final_label_source"], "mini")
        self.assertEqual(untouched["final_repricing_type"], "real_repricing")

    def test_safe_list_and_changed_fields_handle_array_values(self) -> None:
        self.assertEqual(_safe_list(np.array(["BTC", "ETH"])), ["BTC", "ETH"])
        row = pd.Series(
            {
                "news_kind": "analysis",
                "event_type": "other",
                "market_impact_direction": "neutral",
                "market_impact_magnitude": 1,
                "repricing_type": "hype",
                "subject_link_strength": 2,
                "tradability_risk": "low",
                "decay_horizon_days": 3,
                "is_actionable_event": False,
                "short_veto_flag": False,
                "narrative_tags": np.array(["ethereum", "defi"]),
                "summary": "mini summary",
                "rationale": "mini rationale",
            }
        )
        strong_payload = {
            "news_kind": "analysis",
            "event_type": "other",
            "market_impact_direction": "neutral",
            "market_impact_magnitude": 1,
            "repricing_type": "hype",
            "subject_link_strength": 2,
            "tradability_risk": "low",
            "decay_horizon_days": 3,
            "is_actionable_event": False,
            "short_veto_flag": False,
            "narrative_tags": ["ethereum", "defi"],
            "summary": "mini summary",
            "rationale": "mini rationale",
        }
        self.assertEqual(_changed_fields(row, strong_payload), [])


if __name__ == "__main__":
    unittest.main()
