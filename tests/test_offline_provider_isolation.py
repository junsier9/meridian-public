from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.adapters.adapters import AdapterValidationError
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path
from tests.test_helpers import enter_runtime_worker


class OfflineProviderIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-offline-provider-isolation")

    def _request(self, *, subject: str = "AIX", scenario: str = "bullish_publish") -> ProviderRequest:
        return ProviderRequest(
            object_id=f"offline-{subject.lower()}",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope="spot+perp",
            scenario=scenario,
        )

    def _write_cex_snapshot(self, root: Path, *, request: ProviderRequest, observed_subject: str) -> Path:
        path = subject_key_path(
            root,
            request.scenario,
            SubjectKey.build(
                symbol=request.subject,
                venue="snapshot-cex-lab",
                instrument_type="cex",
            ),
            "cex_snapshot.json",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "provider": "offline-cex-replay",
                    "retrieved_at": "2026-04-07T00:00:00Z",
                    "scenario_tag": request.scenario,
                    "instrument": f"{request.subject.upper()}USDT",
                    "events": [
                        {
                            "event_id": f"{request.subject.lower()}-spot-24h",
                            "event_name": "spot_24h_momentum",
                            "payload": {"asset": observed_subject, "summary": "test event", "metrics": {}},
                            "mapping": {
                                "claimKind": "measurement",
                                "bias": "bullish",
                                "evidence": "E4",
                                "confidenceScore": 70,
                                "horizon": "intraday",
                            },
                            "extra": {"venue": "Snapshot", "market_type": "spot"},
                        }
                    ],
                    "raw_http": {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def test_fetch_uses_subject_namespaced_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            aix_request = self._request(subject="AIX")
            btc_request = self._request(subject="BTC")
            self._write_cex_snapshot(root, request=aix_request, observed_subject="AIX")
            self._write_cex_snapshot(root, request=btc_request, observed_subject="BTC")

            payload = OfflineReplayCEXProvider(root).fetch(aix_request)
            self.assertEqual(payload.raw_payload["events"][0]["payload"]["asset"], "AIX")

    def test_cross_subject_payload_raises_hard_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request = self._request(subject="BTC", scenario="cross_subject")
            self._write_cex_snapshot(root, request=request, observed_subject="AIX")

            with self.assertRaises(ValueError):
                OfflineReplayCEXProvider(root).fetch(request)

    def test_subject_key_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario_root = root / "collision_case"
            collision_dirs = [
                scenario_root / "symbol=aix!__venue=snapshot-cex-lab__instrument_type=cex",
                scenario_root / "symbol=aix@__venue=snapshot-cex-lab__instrument_type=cex",
            ]
            for directory in collision_dirs:
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "cex_snapshot.json").write_text(
                    json.dumps(
                        {
                            "provider": "offline-cex-replay",
                            "retrieved_at": "2026-04-07T00:00:00Z",
                            "scenario_tag": "collision_case",
                            "instrument": "AIXUSDT",
                            "events": [],
                            "raw_http": {},
                        }
                    ),
                    encoding="utf-8",
                )

            with self.assertRaises(AdapterValidationError):
                OfflineReplayCEXProvider(root).fetch(self._request(scenario="collision_case"))


if __name__ == "__main__":
    unittest.main()
