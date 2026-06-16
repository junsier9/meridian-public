from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

from enhengclaw.quant_research.label_builder import build_label_artifact


class LabelBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-label-builder-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _feature_frame(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        start = datetime(2025, 1, 1, tzinfo=UTC)
        for offset in range(70):
            timestamp = start + timedelta(days=offset)
            timestamp_ms = int(timestamp.timestamp() * 1000)
            for subject, base in (("AAA", 0.02), ("BBB", -0.01)):
                rows.append(
                    {
                        "timestamp_ms": timestamp_ms,
                        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                        "subject": subject,
                        "target_forward_return": base,
                        "target_up": int(base > 0),
                        "target_execution_forward_return": base + (0.001 if subject == "AAA" else -0.001),
                        "target_execution_up": int((base + (0.001 if subject == "AAA" else -0.001)) > 0),
                    }
                )
        return pd.DataFrame.from_records(rows)

    def test_exec_aligned_label_builder_writes_artifacts_and_cost_adjusts_returns(self) -> None:
        feature_root = self.temp_dir / "feature-set"
        features = self._feature_frame()

        artifact = build_label_artifact(
            features=features,
            feature_root=feature_root,
            feature_set_id="demo-feature-set",
            dataset_id="demo-dataset",
            shape="cross_sectional",
            dataset_profile="cross_sectional_daily_4h",
            label_contract_id="forward_return_execution_aligned.v1",
            source_commit_sha="deadbeef",
        )

        self.assertTrue((feature_root / "labels.csv.gz").exists())
        self.assertTrue((feature_root / "label_manifest.json").exists())
        self.assertIn("target_execution_forward_return_raw", features.columns)
        self.assertIn("target_execution_neutral_zone_threshold", features.columns)
        self.assertGreater(float(features["target_execution_roundtrip_cost_proxy"].iloc[0]), 0.0)
        self.assertEqual(artifact["raw_forward_return_column"], "target_execution_forward_return_raw")
        first_hash = artifact["label_hash"]

        features_2 = self._feature_frame()
        artifact_2 = build_label_artifact(
            features=features_2,
            feature_root=self.temp_dir / "feature-set-2",
            feature_set_id="demo-feature-set",
            dataset_id="demo-dataset",
            shape="cross_sectional",
            dataset_profile="cross_sectional_daily_4h",
            label_contract_id="forward_return_execution_aligned.v1",
            source_commit_sha="deadbeef",
        )
        self.assertEqual(first_hash, artifact_2["label_hash"])


if __name__ == "__main__":
    unittest.main()
