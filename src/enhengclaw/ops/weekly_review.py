from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WeeklyDaySummary:
    date_utc: str
    present: bool
    run_count: int
    batch_count: int
    symbols_run: list[str]
    decision_distribution: dict[str, int]
    status_distribution: dict[str, int]
    provider_selection_distribution: dict[str, int]
    fail_closed_count: int
    runtime_unavailable_count: int
    debug_override_count: int
    raw_payload_files_count: int
    replay_compatible_records_count: int
    rejected_provider_frequency: dict[str, int]
    rejected_provider_reason_frequency: dict[str, int]


@dataclass(frozen=True, slots=True)
class OperatorChecklist:
    default_runtime_unavailable_any_day: bool
    debug_override_seen: bool
    provider_selection_anomaly: bool
    review_new_raw_payloads: bool
    review_new_replay_records: bool
    golden_corpus_candidates_present: bool
    notes: list[str]


@dataclass(frozen=True, slots=True)
class WeeklyReviewPack:
    start_date_utc: str
    end_date_utc: str
    generated_at_utc: str
    total_run_count: int
    total_batch_count: int
    symbols_seen: list[str]
    decision_distribution_by_day: dict[str, dict[str, int]]
    status_distribution_by_day: dict[str, dict[str, int]]
    provider_selection_distribution_by_day: dict[str, dict[str, int]]
    fail_closed_trend: dict[str, int]
    runtime_unavailable_trend: dict[str, int]
    debug_override_usage_by_day: dict[str, int]
    rejected_provider_trend: dict[str, dict[str, int]]
    rejected_provider_reason_trend: dict[str, dict[str, int]]
    missing_daily_packs: list[str]
    days: list[WeeklyDaySummary]
    operator_checklist: OperatorChecklist


@dataclass(frozen=True, slots=True)
class WeeklyReviewArtifacts:
    output_root: str
    json_path: str
    markdown_path: str | None


@dataclass(frozen=True, slots=True)
class WeeklyReviewResult:
    pack: WeeklyReviewPack
    artifacts: WeeklyReviewArtifacts


class WeeklyReviewBuilder:
    def __init__(
        self,
        *,
        daily_review_packs_root: str | Path,
        output_root: str | Path | None = None,
    ) -> None:
        self.daily_review_packs_root = Path(daily_review_packs_root)
        self.output_root = (
            Path(output_root)
            if output_root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "weekly_review_packs"
        )

    def build_and_write(
        self,
        *,
        start_date_utc: str | date,
        end_date_utc: str | date,
        write_markdown: bool = False,
    ) -> WeeklyReviewResult:
        start_date = self._normalize_date(start_date_utc)
        end_date = self._normalize_date(end_date_utc)
        pack = self.build(start_date_utc=start_date, end_date_utc=end_date)
        output_dir = self.output_root / f"{start_date.isoformat()}_{end_date.isoformat()}"
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = output_dir / "weekly_review.json"
        json_path.write_text(json.dumps(asdict(pack), indent=2), encoding="utf-8")

        markdown_path: Path | None = None
        if write_markdown:
            markdown_path = output_dir / "weekly_review_summary.md"
            markdown_path.write_text(self.render_markdown(pack), encoding="utf-8")

        return WeeklyReviewResult(
            pack=pack,
            artifacts=WeeklyReviewArtifacts(
                output_root=str(output_dir),
                json_path=str(json_path),
                markdown_path=None if markdown_path is None else str(markdown_path),
            ),
        )

    def build(
        self,
        *,
        start_date_utc: str | date,
        end_date_utc: str | date,
    ) -> WeeklyReviewPack:
        start_date = self._normalize_date(start_date_utc)
        end_date = self._normalize_date(end_date_utc)
        if end_date < start_date:
            raise ValueError("end_date_utc must be on or after start_date_utc")

        day_summaries: list[WeeklyDaySummary] = []
        missing_daily_packs: list[str] = []

        cursor = start_date
        while cursor <= end_date:
            pack = self._load_daily_pack(cursor)
            if pack is None:
                missing_daily_packs.append(cursor.isoformat())
                day_summaries.append(self._empty_day(cursor))
            else:
                day_summaries.append(self._day_from_pack(pack))
            cursor += timedelta(days=1)

        decision_distribution_by_day = {
            day.date_utc: dict(day.decision_distribution) for day in day_summaries
        }
        status_distribution_by_day = {
            day.date_utc: dict(day.status_distribution) for day in day_summaries
        }
        provider_selection_distribution_by_day = {
            day.date_utc: dict(day.provider_selection_distribution) for day in day_summaries
        }
        fail_closed_trend = {day.date_utc: day.fail_closed_count for day in day_summaries}
        runtime_unavailable_trend = {day.date_utc: day.runtime_unavailable_count for day in day_summaries}
        debug_override_usage_by_day = {day.date_utc: day.debug_override_count for day in day_summaries}
        rejected_provider_trend = {
            day.date_utc: dict(day.rejected_provider_frequency) for day in day_summaries
        }
        rejected_provider_reason_trend = {
            day.date_utc: dict(day.rejected_provider_reason_frequency) for day in day_summaries
        }

        checklist = self._build_checklist(day_summaries, missing_daily_packs)

        return WeeklyReviewPack(
            start_date_utc=start_date.isoformat(),
            end_date_utc=end_date.isoformat(),
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            total_run_count=sum(day.run_count for day in day_summaries),
            total_batch_count=sum(day.batch_count for day in day_summaries),
            symbols_seen=sorted({symbol for day in day_summaries for symbol in day.symbols_run}),
            decision_distribution_by_day=decision_distribution_by_day,
            status_distribution_by_day=status_distribution_by_day,
            provider_selection_distribution_by_day=provider_selection_distribution_by_day,
            fail_closed_trend=fail_closed_trend,
            runtime_unavailable_trend=runtime_unavailable_trend,
            debug_override_usage_by_day=debug_override_usage_by_day,
            rejected_provider_trend=rejected_provider_trend,
            rejected_provider_reason_trend=rejected_provider_reason_trend,
            missing_daily_packs=missing_daily_packs,
            days=day_summaries,
            operator_checklist=checklist,
        )

    def render_markdown(self, pack: WeeklyReviewPack) -> str:
        lines = [
            f"# Weekly Review - {pack.start_date_utc} to {pack.end_date_utc}",
            "",
            f"- Total run count: {pack.total_run_count}",
            f"- Total batch count: {pack.total_batch_count}",
            f"- Symbols seen: {', '.join(pack.symbols_seen) if pack.symbols_seen else '(none)'}",
            f"- Missing daily packs: {', '.join(pack.missing_daily_packs) if pack.missing_daily_packs else '(none)'}",
            "",
            "## Trends",
            f"- Fail closed trend: {self._format_day_counter(pack.fail_closed_trend)}",
            f"- Runtime unavailable trend: {self._format_day_counter(pack.runtime_unavailable_trend)}",
            f"- Debug override usage: {self._format_day_counter(pack.debug_override_usage_by_day)}",
            "",
            "## Operator Checklist",
            f"- Default runtime unavailable any day: {pack.operator_checklist.default_runtime_unavailable_any_day}",
            f"- Debug override seen: {pack.operator_checklist.debug_override_seen}",
            f"- Provider selection anomaly: {pack.operator_checklist.provider_selection_anomaly}",
            f"- Review new raw payloads: {pack.operator_checklist.review_new_raw_payloads}",
            f"- Review new replay records: {pack.operator_checklist.review_new_replay_records}",
            f"- Golden corpus candidates present: {pack.operator_checklist.golden_corpus_candidates_present}",
            f"- Notes: {'; '.join(pack.operator_checklist.notes) if pack.operator_checklist.notes else '(none)'}",
        ]
        return "\n".join(lines) + "\n"

    def _load_daily_pack(self, day: date) -> dict[str, Any] | None:
        path = self.daily_review_packs_root / day.isoformat() / "daily_review_pack.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _empty_day(self, day: date) -> WeeklyDaySummary:
        return WeeklyDaySummary(
            date_utc=day.isoformat(),
            present=False,
            run_count=0,
            batch_count=0,
            symbols_run=[],
            decision_distribution={},
            status_distribution={},
            provider_selection_distribution={},
            fail_closed_count=0,
            runtime_unavailable_count=0,
            debug_override_count=0,
            raw_payload_files_count=0,
            replay_compatible_records_count=0,
            rejected_provider_frequency={},
            rejected_provider_reason_frequency={},
        )

    def _day_from_pack(self, pack: dict[str, Any]) -> WeeklyDaySummary:
        return WeeklyDaySummary(
            date_utc=str(pack.get("date_utc", "")),
            present=True,
            run_count=int(pack.get("run_count", 0)),
            batch_count=int(pack.get("batch_count", 0)),
            symbols_run=[str(item) for item in pack.get("symbols_run", [])],
            decision_distribution={str(k): int(v) for k, v in pack.get("decision_distribution", {}).items()},
            status_distribution={str(k): int(v) for k, v in pack.get("status_distribution", {}).items()},
            provider_selection_distribution={
                str(k): int(v) for k, v in pack.get("provider_selection_distribution", {}).items()
            },
            fail_closed_count=int(pack.get("fail_closed_count", 0)),
            runtime_unavailable_count=len(pack.get("runtime_unavailable_runs", [])),
            debug_override_count=int(pack.get("debug_override_count", 0)),
            raw_payload_files_count=int(pack.get("raw_payload_files_count", 0)),
            replay_compatible_records_count=int(pack.get("replay_compatible_records_count", 0)),
            rejected_provider_frequency={
                str(k): int(v) for k, v in pack.get("rejected_provider_frequency", {}).items()
            },
            rejected_provider_reason_frequency={
                str(k): int(v) for k, v in pack.get("rejected_provider_reason_frequency", {}).items()
            },
        )

    def _build_checklist(
        self,
        day_summaries: list[WeeklyDaySummary],
        missing_daily_packs: list[str],
    ) -> OperatorChecklist:
        default_runtime_unavailable_any_day = any(day.fail_closed_count > 0 for day in day_summaries)
        debug_override_seen = any(day.debug_override_count > 0 for day in day_summaries)
        provider_selection_patterns = {
            tuple(sorted(day.provider_selection_distribution.items()))
            for day in day_summaries
            if day.present and day.run_count > 0
        }
        provider_selection_anomaly = len(provider_selection_patterns) > 1
        review_new_raw_payloads = any(day.raw_payload_files_count > 0 for day in day_summaries)
        review_new_replay_records = any(day.replay_compatible_records_count > 0 for day in day_summaries)
        golden_corpus_candidates_present = any(
            day.runtime_unavailable_count > 0
            or day.fail_closed_count > 0
            or day.status_distribution.get("error", 0) > 0
            for day in day_summaries
        )

        notes: list[str] = []
        if default_runtime_unavailable_any_day:
            notes.append("default runtime became unavailable on at least one day; inspect provider selection and provider health")
        if debug_override_seen:
            notes.append("debug override was used; treat those runs as non-normal operations")
        if provider_selection_anomaly:
            notes.append("provider selection distribution shifted across the review window")
        if review_new_raw_payloads or review_new_replay_records:
            notes.append("new raw payload or replay-compatible records were generated and merit spot-checking")
        if golden_corpus_candidates_present:
            notes.append("abnormal runs exist and may deserve promotion into the golden corpus")
        if missing_daily_packs:
            notes.append("some daily review packs are missing inside the requested range")

        return OperatorChecklist(
            default_runtime_unavailable_any_day=default_runtime_unavailable_any_day,
            debug_override_seen=debug_override_seen,
            provider_selection_anomaly=provider_selection_anomaly,
            review_new_raw_payloads=review_new_raw_payloads,
            review_new_replay_records=review_new_replay_records,
            golden_corpus_candidates_present=golden_corpus_candidates_present,
            notes=notes,
        )

    def _normalize_date(self, value: str | date) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def _format_day_counter(self, values: dict[str, int]) -> str:
        if not values:
            return "(none)"
        return ", ".join(f"{day}={count}" for day, count in sorted(values.items()))
