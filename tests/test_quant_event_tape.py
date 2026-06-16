from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.event_tape import (
    EVENT_CONFIRMATION_CONFIRMED,
    EVENT_CONFIRMATION_NARRATIVE_ONLY,
    EVENT_CONFIRMATION_OFFICIAL,
    EVENT_SCOPE_MARKET,
    EVENT_SCOPE_SUBJECT,
    EventTapeRecord,
    has_recent_confirmed_event,
    load_event_tape,
    recent_events_for_subject,
    summarize_event_tape,
    write_event_tape,
)


class QuantEventTapeTests(unittest.TestCase):
    def test_event_tape_round_trip_and_summary(self) -> None:
        records = [
            EventTapeRecord.from_payload(
                {
                    "event_id": "binance-listing-abc-2026-04-21",
                    "observed_at_utc": "2026-04-21T10:00:00Z",
                    "effective_at_utc": "2026-04-21T10:00:00Z",
                    "scope": EVENT_SCOPE_SUBJECT,
                    "category": "exchange_listing",
                    "confirmation_level": EVENT_CONFIRMATION_OFFICIAL,
                    "source_kind": "official_exchange",
                    "source_ref": "https://example.com/listing",
                    "title": "ABC listing announcement",
                    "subjects": ["ABC"],
                    "narrative_tags": [],
                    "metadata": {"venue": "binance"},
                }
            ),
            EventTapeRecord.from_payload(
                {
                    "event_id": "fomc-2026-04-22",
                    "observed_at_utc": "2026-04-22T18:00:00Z",
                    "effective_at_utc": "2026-04-22T18:00:00Z",
                    "scope": EVENT_SCOPE_MARKET,
                    "category": "macro",
                    "confirmation_level": EVENT_CONFIRMATION_CONFIRMED,
                    "source_kind": "calendar",
                    "source_ref": "https://example.com/fomc",
                    "title": "FOMC decision",
                    "subjects": [],
                    "narrative_tags": [],
                    "metadata": {"region": "US"},
                }
            ),
        ]
        with tempfile.TemporaryDirectory(prefix="event-tape-") as tmp_dir:
            path = Path(tmp_dir) / "event_tape.jsonl"
            write_event_tape(path, records)
            loaded = load_event_tape(path)
        self.assertEqual([item.event_id for item in loaded], [item.event_id for item in records])
        summary = summarize_event_tape(loaded)
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["subject_count"], 1)
        self.assertEqual(summary["category_counts"]["exchange_listing"], 1)
        self.assertEqual(summary["scope_counts"][EVENT_SCOPE_MARKET], 1)

    def test_recent_events_filter_future_rows_with_replay_safety(self) -> None:
        records = [
            EventTapeRecord.from_payload(
                {
                    "event_id": "reg-abc-now",
                    "observed_at_utc": "2026-04-24T00:00:00Z",
                    "effective_at_utc": "2026-04-24T00:00:00Z",
                    "scope": EVENT_SCOPE_SUBJECT,
                    "category": "regulatory",
                    "confirmation_level": EVENT_CONFIRMATION_CONFIRMED,
                    "source_kind": "regulator",
                    "source_ref": "https://example.com/reg-abc-now",
                    "title": "ABC regulatory notice",
                    "subjects": ["ABC"],
                    "narrative_tags": [],
                    "metadata": {},
                }
            ),
            EventTapeRecord.from_payload(
                {
                    "event_id": "reg-abc-future",
                    "observed_at_utc": "2026-04-27T00:00:00Z",
                    "effective_at_utc": "2026-04-27T00:00:00Z",
                    "scope": EVENT_SCOPE_SUBJECT,
                    "category": "regulatory",
                    "confirmation_level": EVENT_CONFIRMATION_CONFIRMED,
                    "source_kind": "regulator",
                    "source_ref": "https://example.com/reg-abc-future",
                    "title": "ABC future regulatory notice",
                    "subjects": ["ABC"],
                    "narrative_tags": [],
                    "metadata": {},
                }
            ),
        ]
        recent = recent_events_for_subject(
            records,
            subject="ABC",
            as_of_utc="2026-04-25T00:00:00Z",
            lookback_days=5,
        )
        self.assertEqual([item.event_id for item in recent], ["reg-abc-now"])

    def test_has_recent_confirmed_event_includes_market_scope(self) -> None:
        records = [
            EventTapeRecord.from_payload(
                {
                    "event_id": "macro-shock",
                    "observed_at_utc": "2026-04-24T12:00:00Z",
                    "effective_at_utc": "2026-04-24T12:00:00Z",
                    "scope": EVENT_SCOPE_MARKET,
                    "category": "macro",
                    "confirmation_level": EVENT_CONFIRMATION_OFFICIAL,
                    "source_kind": "calendar",
                    "source_ref": "https://example.com/macro",
                    "title": "Macro calendar event",
                    "subjects": [],
                    "narrative_tags": [],
                    "metadata": {},
                }
            )
        ]
        self.assertTrue(
            has_recent_confirmed_event(
                records,
                subject="SOL",
                as_of_utc=datetime(2026, 4, 25, tzinfo=UTC),
                lookback_days=2,
            )
        )
        self.assertFalse(
            has_recent_confirmed_event(
                records,
                subject="SOL",
                as_of_utc=datetime(2026, 4, 25, tzinfo=UTC),
                lookback_days=2,
                include_market_scope=False,
            )
        )

    def test_narrative_only_events_require_tags(self) -> None:
        with self.assertRaises(ValueError):
            EventTapeRecord.from_payload(
                {
                    "event_id": "narrative-empty",
                    "observed_at_utc": "2026-04-24T12:00:00Z",
                    "effective_at_utc": "2026-04-24T12:00:00Z",
                    "scope": EVENT_SCOPE_SUBJECT,
                    "category": "other",
                    "confirmation_level": EVENT_CONFIRMATION_NARRATIVE_ONLY,
                    "source_kind": "social",
                    "source_ref": "https://example.com/post",
                    "title": "Narrative-only mention",
                    "subjects": ["XYZ"],
                    "narrative_tags": [],
                    "metadata": {},
                }
            )
