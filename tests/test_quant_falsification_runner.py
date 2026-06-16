from __future__ import annotations

import pandas as pd
import unittest
from unittest import mock
import numpy as np

from enhengclaw.quant_research.falsification_runner import (
    _iteration_count,
    _period_frame,
    _shuffle_frame_columns_within_timestamp,
    _time_shift_scores_by_subject,
    run_statistical_falsification,
)


class StatisticalFalsificationRunnerTests(unittest.TestCase):
    def test_period_frame_derives_timestamp_utc_from_timestamp_ms(self) -> None:
        period_frame = _period_frame(
            {"periods": [{"timestamp_ms": 1_714_953_600_000, "net_period_return": 0.01}]},
            label="candidate",
        )

        self.assertEqual(list(period_frame.columns), ["candidate_label", "timestamp_ms", "timestamp_utc", "net_period_return"])
        self.assertEqual(period_frame.iloc[0]["candidate_label"], "candidate")
        self.assertEqual(period_frame.iloc[0]["timestamp_ms"], 1_714_953_600_000)
        self.assertEqual(period_frame.iloc[0]["timestamp_utc"], "2024-05-06T00:00:00Z")
        self.assertAlmostEqual(float(period_frame.iloc[0]["net_period_return"]), 0.01)

    def test_time_shift_scores_by_subject_handles_non_contiguous_index(self) -> None:
        frame = pd.DataFrame(
            {
                "subject": ["AAA", "AAA", "BBB", "BBB"],
                "timestamp_ms": [1, 2, 1, 2],
                "score": [0.1, 0.2, -0.3, -0.4],
            },
            index=[10, 20, 30, 40],
        )

        shifted = _time_shift_scores_by_subject(frame=frame, rng=np.random.default_rng(7))

        self.assertEqual(list(shifted.index), [0, 1, 2, 3])
        self.assertEqual(sorted(shifted.loc[shifted["subject"] == "AAA", "score"].tolist()), [0.1, 0.2])
        self.assertEqual(sorted(shifted.loc[shifted["subject"] == "BBB", "score"].tolist()), [-0.4, -0.3])

    def test_shuffle_frame_columns_within_timestamp_handles_non_contiguous_index(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp_ms": [1, 1, 2, 2],
                "subject": ["AAA", "BBB", "AAA", "BBB"],
                "score": [0.1, 0.2, 0.3, 0.4],
            },
            index=[11, 21, 31, 41],
        )

        shuffled = _shuffle_frame_columns_within_timestamp(
            frame=frame,
            columns=["score"],
            rng=np.random.default_rng(11),
        )

        self.assertEqual(list(shuffled.index), [0, 1, 2, 3])
        self.assertEqual(sorted(shuffled.loc[shuffled["timestamp_ms"] == 1, "score"].tolist()), [0.1, 0.2])
        self.assertEqual(sorted(shuffled.loc[shuffled["timestamp_ms"] == 2, "score"].tolist()), [0.3, 0.4])

    def test_runner_skips_unsupported_experiment(self) -> None:
        result = run_statistical_falsification(
            experiment_spec={
                "model_family": "xs_alpha_ontology_v5",
                "label_contract_id": "forward_return_ranking.v1",
                "shape": "cross_sectional",
            },
            strategy_entry={"strategy_id": "demo"},
            prediction_bundle={},
            train_df=pd.DataFrame(),
            validation_df=pd.DataFrame(),
            test_df=pd.DataFrame(),
            feature_columns=[],
            target_column="target_up",
            constraints={},
            split_realization_contract={"bar_interval_ms": 86_400_000, "realization_step_bars": 10},
            execution_cost_model={},
            reference_capital_usd=None,
            capacity_limits=None,
            fit_and_score_fn=lambda **_: {},
            backtest_cross_sectional_fn=lambda *_args, **_kwargs: {},
        )

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["applicable"])

    def test_iteration_count_uses_positive_env_override(self) -> None:
        with mock.patch.dict("os.environ", {"ENHENGCLAW_TEST_ITERATIONS": "7"}):
            self.assertEqual(
                _iteration_count(env_name="ENHENGCLAW_TEST_ITERATIONS", default=120),
                7,
            )

        with mock.patch.dict("os.environ", {"ENHENGCLAW_TEST_ITERATIONS": "bad"}):
            self.assertEqual(
                _iteration_count(env_name="ENHENGCLAW_TEST_ITERATIONS", default=120),
                120,
            )


if __name__ == "__main__":
    unittest.main()
