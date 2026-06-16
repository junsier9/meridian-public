from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.process_cryptonewsdataset_llm import (
    _build_strong_model_review_candidates,
    _compute_quality_score,
    _domain_kind,
    _llm_user_prompt,
    _research_effective_at,
    _safe_int,
    _safe_text,
    _split_currencies,
)


class QuantCryptoNewsDatasetProcessingTests(unittest.TestCase):
    def test_domain_kind_classifies_social_official_and_editorial(self) -> None:
        self.assertEqual(_domain_kind("twitter.com"), "social")
        self.assertEqual(_domain_kind("blog.binance.com"), "official")
        self.assertEqual(_domain_kind("cointelegraph.com"), "editorial")

    def test_research_effective_at_moves_to_next_utc_day(self) -> None:
        ts = pd.Timestamp("2025-01-05T16:32:10Z")
        self.assertEqual(_research_effective_at(ts), "2025-01-06T00:00:00Z")

    def test_split_currencies_handles_null_and_duplicates(self) -> None:
        self.assertEqual(_split_currencies(None), [])
        self.assertEqual(_split_currencies("btc,ETH,BTC"), ["BTC", "ETH"])

    def test_safe_helpers_handle_pandas_na(self) -> None:
        self.assertEqual(_safe_text(pd.NA), "")
        self.assertEqual(_safe_int(pd.NA), 0)
        self.assertEqual(_domain_kind(pd.NA), "unknown")

    def test_quality_score_prefers_complete_editorial_rows(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "reaction_sum": 10,
                    "description": "Some description",
                    "sourceUrl": "https://example.com",
                    "source_kind": "editorial",
                },
                {
                    "reaction_sum": 2,
                    "description": pd.NA,
                    "sourceUrl": pd.NA,
                    "source_kind": "social",
                },
            ]
        )
        scores = _compute_quality_score(frame)
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))

    def test_llm_prompt_handles_nullable_fields(self) -> None:
        row = pd.Series(
            {
                "title": "Test title",
                "description": pd.NA,
                "sourceUrl": pd.NA,
                "sourceDomain": pd.NA,
                "source_kind": "editorial",
                "newsDatetime": pd.Timestamp("2025-01-05T16:32:10Z"),
                "currencies_list": pd.NA,
                "reaction_sum": pd.NA,
                "engagement_sum": pd.NA,
                "important": pd.NA,
                "positive": pd.NA,
                "negative": pd.NA,
            }
        )
        prompt = _llm_user_prompt(row)
        self.assertIn('"title": "Test title"', prompt)
        self.assertIn('"currencies": ""', prompt)
        self.assertIn('"reaction_sum": 0', prompt)

    def test_strong_model_review_candidates_prioritize_decision_critical_rows(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "id": 1,
                    "selection_rank": 1,
                    "quality_score": 0.95,
                    "reaction_sum": 30,
                    "event_type": "etf",
                    "repricing_type": "real_repricing",
                    "short_veto_flag": True,
                    "source_kind": "editorial",
                    "is_actionable_event": True,
                    "market_impact_magnitude": 5,
                },
                {
                    "id": 2,
                    "selection_rank": 2,
                    "quality_score": 0.70,
                    "reaction_sum": 8,
                    "event_type": "other",
                    "repricing_type": "hype",
                    "short_veto_flag": False,
                    "source_kind": "editorial",
                    "is_actionable_event": False,
                    "market_impact_magnitude": 1,
                },
                {
                    "id": 3,
                    "selection_rank": 3,
                    "quality_score": 0.88,
                    "reaction_sum": 15,
                    "event_type": "other",
                    "repricing_type": "mixed",
                    "short_veto_flag": False,
                    "source_kind": "official",
                    "is_actionable_event": True,
                    "market_impact_magnitude": 3,
                },
            ]
        )
        candidates = _build_strong_model_review_candidates(frame)
        self.assertEqual(set(candidates["id"].tolist()), {1, 3})
        row1 = candidates.loc[candidates["id"].eq(1)].iloc[0]
        row3 = candidates.loc[candidates["id"].eq(3)].iloc[0]
        self.assertEqual(int(row1["strong_model_review_priority"]), 7)
        self.assertEqual(int(row3["strong_model_review_priority"]), 8)
        self.assertIn("short_veto_guardrail", row1["strong_model_review_reasons"])
        self.assertIn("official_source", row3["strong_model_review_reasons"])


if __name__ == "__main__":
    unittest.main()
