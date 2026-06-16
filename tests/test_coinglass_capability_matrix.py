from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from enhengclaw.quant_research.coinglass_capability_matrix import build_coinglass_capability_matrix


class CoinglassCapabilityMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coinglass-capability-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_build_matrix_writes_no_secret_artifacts(self) -> None:
        requested_urls: list[str] = []

        def fake_http(url: str):
            requested_urls.append(url)
            return {
                "code": "0",
                "msg": "success",
                "data": [
                    {
                        "time": 1_746_000_000_000,
                        "date": 1_746_000_000_000,
                        "txTime": 1_746_000_000_000,
                        "open": 1,
                        "high": 2,
                        "low": 1,
                        "close": 2,
                        "volume_usd": 100,
                    }
                ],
            }

        summary = build_coinglass_capability_matrix(output_root=self.temp_dir, http_get_json_fn=fake_http)

        self.assertEqual(summary["success_count"], summary["endpoint_count"])
        matrix_path = Path(summary["matrix_path"])
        samples_path = Path(summary["samples_path"])
        report_path = Path(summary["report_path"])
        self.assertTrue(matrix_path.exists())
        self.assertTrue(samples_path.exists())
        self.assertTrue(report_path.exists())

        combined = matrix_path.read_text(encoding="utf-8") + samples_path.read_text(encoding="utf-8") + report_path.read_text(encoding="utf-8")
        self.assertNotIn("CG-API-KEY", combined)
        self.assertNotIn("CoinglassAPI", combined)
        self.assertNotIn("COINGLASS_API_KEY", combined)
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertIn("spot_price_history", [item["endpoint_id"] for item in matrix["endpoints"]])
        self.assertGreater(len(requested_urls), matrix["endpoint_count"])


if __name__ == "__main__":
    unittest.main()
