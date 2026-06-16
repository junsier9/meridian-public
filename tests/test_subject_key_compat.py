from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.domain.identity.subject_key import (
    SubjectKey as DomainSubjectKey,
    ensure_subject_key_matches as domain_ensure_subject_key_matches,
    normalize_subject_fragment as domain_normalize_subject_fragment,
    parse_subject_key_fragment as domain_parse_subject_key_fragment,
    subject_key_hourly_jsonl_path as domain_subject_key_hourly_jsonl_path,
    subject_key_path as domain_subject_key_path,
)
from enhengclaw.utils.subject_keys import (
    SubjectKey as ShimSubjectKey,
    ensure_subject_key_matches as shim_ensure_subject_key_matches,
    normalize_subject_fragment as shim_normalize_subject_fragment,
    parse_subject_key_fragment as shim_parse_subject_key_fragment,
    subject_key_hourly_jsonl_path as shim_subject_key_hourly_jsonl_path,
    subject_key_path as shim_subject_key_path,
)


class SubjectKeyCompatTests(unittest.TestCase):
    def test_old_and_new_import_paths_share_same_behavior_and_class(self) -> None:
        self.assertIs(DomainSubjectKey, ShimSubjectKey)
        self.assertIs(domain_normalize_subject_fragment, shim_normalize_subject_fragment)
        self.assertIs(domain_parse_subject_key_fragment, shim_parse_subject_key_fragment)
        self.assertIs(domain_subject_key_path, shim_subject_key_path)
        self.assertIs(domain_subject_key_hourly_jsonl_path, shim_subject_key_hourly_jsonl_path)
        self.assertIs(domain_ensure_subject_key_matches, shim_ensure_subject_key_matches)

        subject_key = DomainSubjectKey.build(symbol="BTCUSDT", venue="Binance", instrument_type="Spot")
        self.assertEqual(subject_key.as_tuple(), ("btcusdt", "binance", "spot"))
        self.assertEqual(subject_key.as_stable_string(), "BTCUSDT.binance.spot")
        self.assertEqual(
            subject_key.as_path_fragment(),
            "symbol=btcusdt__venue=binance__instrument_type=spot",
        )

        parsed = domain_parse_subject_key_fragment(subject_key.as_path_fragment())
        self.assertEqual(parsed, subject_key)
        shim_ensure_subject_key_matches(subject_key, ShimSubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot"), context="compat")

    def test_path_helpers_preserve_existing_partition_layout(self) -> None:
        subject_key = ShimSubjectKey.build(symbol="ETH", venue="alchemy", instrument_type="onchain")
        root = Path("C:/freeze-root")
        timestamp = datetime(2026, 4, 9, 8, 30, tzinfo=timezone.utc)

        self.assertEqual(
            domain_subject_key_path(root, "baseline", subject_key, "payload.json").as_posix(),
            "C:/freeze-root/baseline/symbol=eth__venue=alchemy__instrument_type=onchain/payload.json",
        )
        self.assertEqual(
            shim_subject_key_hourly_jsonl_path(root, subject_key, timestamp).as_posix(),
            "C:/freeze-root/ETH.alchemy.onchain/2026-04-09/08.jsonl",
        )


if __name__ == "__main__":
    unittest.main()
