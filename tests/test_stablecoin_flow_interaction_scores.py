from __future__ import annotations

import unittest

import pandas as pd

from enhengclaw.quant_research.features import (
    xs_alpha_ontology_v11_absorb_qshare_h10d_score,
    xs_alpha_ontology_v11_drain_rs_h10d_score,
    xs_alpha_ontology_v11_flow_blend_h10d_score,
)


def _base_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_ms": [1_700_000_000_000] * 3,
            "subject": ["A", "B", "C"],
            "liquidity_bucket": ["top_liquidity", "top_liquidity", "mid_liquidity"],
            "quote_share_change_30d": [1.0, 0.0, -1.0],
            "relative_strength_20": [1.0, 0.0, 1.0],
            "stablecoin_flow_signal_ready": [1.0, 1.0, 1.0],
            "stablecoin_labeled_coverage_ratio": [0.08, 0.08, 0.08],
            "stablecoin_exchange_netflow_ratio": [0.02, 0.02, 0.02],
            "stablecoin_exchange_absorption_score_v1": [1.2, 1.2, 1.2],
            "stablecoin_whale_exchange_stress_score_v1": [0.0, 0.0, 0.0],
        }
    )


class StablecoinFlowInteractionScoreTests(unittest.TestCase):
    def test_absorption_quote_share_promotes_share_gainers(self) -> None:
        frame = _base_frame()
        score = xs_alpha_ontology_v11_absorb_qshare_h10d_score(frame)
        ordered = list(frame.assign(score=score).sort_values("score", ascending=False)["subject"])
        self.assertEqual(ordered[0], "A")
        self.assertEqual(ordered[-1], "C")

    def test_drain_relative_strength_penalizes_recent_leaders(self) -> None:
        frame = _base_frame()
        frame["stablecoin_exchange_netflow_ratio"] = -0.02
        frame["stablecoin_exchange_absorption_score_v1"] = -1.3
        frame["relative_strength_20"] = [1.0, 0.2, -1.0]
        score = xs_alpha_ontology_v11_drain_rs_h10d_score(frame)
        ordered = list(frame.assign(score=score).sort_values("score", ascending=False)["subject"])
        self.assertEqual(ordered[0], "C")
        self.assertEqual(ordered[-1], "A")

    def test_flow_blend_hits_mid_liquidity_name_harder_under_whale_stress(self) -> None:
        frame = _base_frame()
        frame["stablecoin_exchange_netflow_ratio"] = -0.03
        frame["stablecoin_exchange_absorption_score_v1"] = -1.1
        frame["stablecoin_whale_exchange_stress_score_v1"] = 1.4
        frame["quote_share_change_30d"] = [1.0, 1.0, 1.0]
        frame["relative_strength_20"] = [1.0, 1.0, 1.0]
        score = xs_alpha_ontology_v11_flow_blend_h10d_score(frame)
        ordered = list(frame.assign(score=score).sort_values("score", ascending=False)["subject"])
        self.assertEqual(ordered[-1], "C")


if __name__ == "__main__":
    unittest.main()
