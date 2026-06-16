from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID_PATTERN = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)")
REPLAY_COMPATIBLE_STEMS = {"cex_snapshot", "onchain_snapshot", "safety_snapshot"}


@dataclass(frozen=True, slots=True)
class DailyReviewRunEntry:
    run_id: str
    source: str
    symbol: str
    status: str
    decision: str | None
    selection_mode: str
    allowed_provider_names: list[str]
    rejected_provider_names: list[str]
    warnings: list[str]
    errors: list[str]
    fail_closed: bool
    debug_override_used: bool
    non_default_mode: bool
    raw_payload_file_count: int
    replay_compatible_record_count: int
    archive_path: str


@dataclass(frozen=True, slots=True)
class DailyReviewPack:
    date_utc: str
    generated_at_utc: str
    run_count: int
    batch_count: int
    symbols_run: list[str]
    decision_distribution: dict[str, int]
    status_distribution: dict[str, int]
    provider_selection_distribution: dict[str, int]
    selection_mode_distribution: dict[str, int]
    non_default_mode_count: int
    debug_override_count: int
    raw_payload_files_count: int
    replay_compatible_records_count: int
    runtime_unavailable_runs: list[str]
    error_runs: list[str]
    fail_closed_count: int
    rejected_provider_frequency: dict[str, int]
    rejected_provider_reason_frequency: dict[str, int]
    runs: list[DailyReviewRunEntry]


@dataclass(frozen=True, slots=True)
class DailyReviewPackArtifacts:
    output_root: str
    json_path: str
    markdown_path: str | None


@dataclass(frozen=True, slots=True)
class DailyReviewPackResult:
    pack: DailyReviewPack
    artifacts: DailyReviewPackArtifacts


class DailyReviewPackBuilder:
    def __init__(
        self,
        *,
        pilot_runs_root: str | Path,
        pilot_batches_root: str | Path,
        output_root: str | Path | None = None,
    ) -> None:
        self.pilot_runs_root = Path(pilot_runs_root)
        self.pilot_batches_root = Path(pilot_batches_root)
        self.output_root = (
            Path(output_root)
            if output_root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "daily_review_packs"
        )

    def build_and_write(self, *, date_utc: str | date, write_markdown: bool = False) -> DailyReviewPackResult:
        target_date = self._normalize_date(date_utc)
        pack = self.build(date_utc=target_date)
        day_root = self.output_root / target_date.isoformat()
        day_root.mkdir(parents=True, exist_ok=True)
        json_path = day_root / "daily_review_pack.json"
        json_path.write_text(json.dumps(asdict(pack), indent=2), encoding="utf-8")

        markdown_path: Path | None = None
        if write_markdown:
            markdown_path = day_root / "daily_review_summary.md"
            markdown_path.write_text(self.render_markdown(pack), encoding="utf-8")

        return DailyReviewPackResult(
            pack=pack,
            artifacts=DailyReviewPackArtifacts(
                output_root=str(day_root),
                json_path=str(json_path),
                markdown_path=None if markdown_path is None else str(markdown_path),
            ),
        )

    def build(self, *, date_utc: str | date) -> DailyReviewPack:
        target_date = self._normalize_date(date_utc)
        runs: list[DailyReviewRunEntry] = []
        batch_count = 0
        rejected_provider_counter: Counter[str] = Counter()
        rejected_reason_counter: Counter[str] = Counter()

        for run_dir in self._matching_directories(self.pilot_runs_root, target_date):
            entry, provider_counts = self._load_run_entry(run_dir, source="pilot_run")
            runs.append(entry)
            rejected_provider_counter.update(provider_counts["provider"])
            rejected_reason_counter.update(provider_counts["reason"])

        for batch_dir in self._matching_directories(self.pilot_batches_root, target_date):
            batch_count += 1
            batch_summary = self._read_json(batch_dir / "batch_summary.json")
            for run_info in batch_summary.get("runs", []):
                archive_path = Path(str(run_info.get("archive_path", "")))
                if archive_path.exists():
                    entry, provider_counts = self._load_run_entry(
                        archive_path,
                        source="pilot_batch_run",
                        batch_entry=run_info,
                    )
                else:
                    entry, provider_counts = self._entry_from_batch_only(run_info)
                runs.append(entry)
                rejected_provider_counter.update(provider_counts["provider"])
                rejected_reason_counter.update(provider_counts["reason"])

        decision_distribution = Counter((entry.decision or "none") for entry in runs)
        status_distribution = Counter(entry.status for entry in runs)
        provider_selection_distribution = Counter(self._selection_key(entry.allowed_provider_names) for entry in runs)
        selection_mode_distribution = Counter(entry.selection_mode for entry in runs)

        return DailyReviewPack(
            date_utc=target_date.isoformat(),
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            run_count=len(runs),
            batch_count=batch_count,
            symbols_run=sorted({entry.symbol for entry in runs if entry.symbol}),
            decision_distribution=dict(decision_distribution),
            status_distribution=dict(status_distribution),
            provider_selection_distribution=dict(provider_selection_distribution),
            selection_mode_distribution=dict(selection_mode_distribution),
            non_default_mode_count=sum(1 for entry in runs if entry.non_default_mode),
            debug_override_count=sum(1 for entry in runs if entry.debug_override_used),
            raw_payload_files_count=sum(entry.raw_payload_file_count for entry in runs),
            replay_compatible_records_count=sum(entry.replay_compatible_record_count for entry in runs),
            runtime_unavailable_runs=[entry.run_id for entry in runs if entry.status == "runtime_unavailable"],
            error_runs=[entry.run_id for entry in runs if entry.status == "error"],
            fail_closed_count=sum(1 for entry in runs if entry.fail_closed),
            rejected_provider_frequency=dict(rejected_provider_counter),
            rejected_provider_reason_frequency=dict(rejected_reason_counter),
            runs=runs,
        )

    def render_markdown(self, pack: DailyReviewPack) -> str:
        lines = [
            f"# Daily Review Pack - {pack.date_utc}",
            "",
            f"- Run count: {pack.run_count}",
            f"- Batch count: {pack.batch_count}",
            f"- Symbols run: {', '.join(pack.symbols_run) if pack.symbols_run else '(none)'}",
            f"- Decision distribution: {self._format_counter(pack.decision_distribution)}",
            f"- Status distribution: {self._format_counter(pack.status_distribution)}",
            f"- Provider selection distribution: {self._format_counter(pack.provider_selection_distribution)}",
            f"- Non-default mode count: {pack.non_default_mode_count}",
            f"- Debug override count: {pack.debug_override_count}",
            f"- Raw payload files: {pack.raw_payload_files_count}",
            f"- Replay-compatible records: {pack.replay_compatible_records_count}",
            f"- Fail closed count: {pack.fail_closed_count}",
            "",
            "## Exceptions",
            f"- runtime_unavailable runs: {', '.join(pack.runtime_unavailable_runs) if pack.runtime_unavailable_runs else '(none)'}",
            f"- error runs: {', '.join(pack.error_runs) if pack.error_runs else '(none)'}",
            f"- rejected provider frequency: {self._format_counter(pack.rejected_provider_frequency)}",
            f"- rejected provider reason frequency: {self._format_counter(pack.rejected_provider_reason_frequency)}",
        ]
        return "\n".join(lines) + "\n"

    def latest_available_date(self) -> date | None:
        dates: list[date] = []
        for root in (self.pilot_runs_root, self.pilot_batches_root):
            for directory in root.iterdir() if root.exists() else []:
                if not directory.is_dir():
                    continue
                extracted = self._extract_date(directory.name)
                if extracted is not None:
                    dates.append(extracted)
        return max(dates) if dates else None

    def _load_run_entry(
        self,
        run_dir: Path,
        *,
        source: str,
        batch_entry: dict[str, Any] | None = None,
    ) -> tuple[DailyReviewRunEntry, dict[str, Counter[str]]]:
        selection = self._read_json(run_dir / "provider_selection_result.json")
        warnings_errors = self._read_json(run_dir / "warnings_errors.json")
        runtime_result = self._read_json_optional(run_dir / "runtime_result.json")
        ops_report = self._read_json_optional(run_dir / "ops_report.json")

        warnings = list(warnings_errors.get("warnings", []))
        errors = list(warnings_errors.get("errors", []))
        status = (
            str(batch_entry.get("status"))
            if batch_entry is not None and batch_entry.get("status") is not None
            else self._infer_status(runtime_result=runtime_result, warnings=warnings, errors=errors)
        )
        decision = (
            str(batch_entry.get("decision"))
            if batch_entry is not None and batch_entry.get("decision") is not None
            else None if runtime_result is None else str(runtime_result.get("decision"))
        )
        selection_mode = str(selection.get("mode", "default"))
        allowed_provider_names = [str(item) for item in selection.get("allowed_provider_names", [])]
        rejected_provider_names = [str(item) for item in selection.get("rejected_provider_names", [])]
        raw_files = [item for item in (run_dir / "raw").rglob("*") if item.is_file()] if (run_dir / "raw").exists() else []
        symbol = self._infer_symbol(run_dir, runtime_result, batch_entry)
        rejected_provider_counter = Counter(
            str(item.get("provider_name", "unknown")) for item in selection.get("rejected", [])
        )
        rejected_reason_counter = Counter(str(item.get("reason", "unknown")) for item in selection.get("rejected", []))

        return (
            DailyReviewRunEntry(
                run_id=run_dir.name,
                source=source,
                symbol=symbol,
                status=status,
                decision=decision,
                selection_mode=selection_mode,
                allowed_provider_names=allowed_provider_names,
                rejected_provider_names=rejected_provider_names,
                warnings=warnings,
                errors=errors,
                fail_closed=self._is_fail_closed(warnings, errors),
                debug_override_used=self._is_debug_override_used(selection_mode, allowed_provider_names, ops_report),
                non_default_mode=selection_mode != "default",
                raw_payload_file_count=len(raw_files),
                replay_compatible_record_count=sum(1 for item in raw_files if self._is_replay_compatible(item)),
                archive_path=str(run_dir),
            ),
            {"provider": rejected_provider_counter, "reason": rejected_reason_counter},
        )

    def _entry_from_batch_only(self, batch_entry: dict[str, Any]) -> tuple[DailyReviewRunEntry, dict[str, Counter[str]]]:
        entry = DailyReviewRunEntry(
            run_id=Path(str(batch_entry.get("archive_path", "missing"))).name or "missing",
            source="pilot_batch_run_missing_artifact",
            symbol=str(batch_entry.get("symbol", "")),
            status=str(batch_entry.get("status", "error")),
            decision=None if batch_entry.get("decision") is None else str(batch_entry.get("decision")),
            selection_mode="unknown",
            allowed_provider_names=[],
            rejected_provider_names=[],
            warnings=[str(item) for item in batch_entry.get("warnings", [])],
            errors=[str(item) for item in batch_entry.get("errors", [])],
            fail_closed=False,
            debug_override_used=False,
            non_default_mode=False,
            raw_payload_file_count=0,
            replay_compatible_record_count=0,
            archive_path=str(batch_entry.get("archive_path", "")),
        )
        return entry, {"provider": Counter(), "reason": Counter()}

    def _matching_directories(self, root: Path, target_date: date) -> list[Path]:
        if not root.exists():
            return []
        matches: list[Path] = []
        for directory in root.iterdir():
            if not directory.is_dir():
                continue
            if self._extract_date(directory.name) == target_date:
                matches.append(directory)
        return sorted(matches)

    def _extract_date(self, name: str) -> date | None:
        match = RUN_ID_PATTERN.match(name)
        if match is None:
            return None
        stamp = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ")
        return stamp.date()

    def _normalize_date(self, value: str | date) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_json_optional(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return self._read_json(path)

    def _infer_status(
        self,
        *,
        runtime_result: dict[str, Any] | None,
        warnings: list[str],
        errors: list[str],
    ) -> str:
        if runtime_result is not None:
            return "ok"
        if self._is_fail_closed(warnings, errors):
            return "runtime_unavailable"
        if errors:
            return "error"
        return "runtime_unavailable"

    def _is_fail_closed(self, warnings: list[str], errors: list[str]) -> bool:
        haystack = " ".join([*warnings, *errors]).lower()
        return "fail closed" in haystack or "rejected all candidate providers" in haystack

    def _infer_symbol(
        self,
        run_dir: Path,
        runtime_result: dict[str, Any] | None,
        batch_entry: dict[str, Any] | None,
    ) -> str:
        if batch_entry is not None and batch_entry.get("symbol"):
            return str(batch_entry["symbol"]).upper()
        if runtime_result is not None:
            research_object = runtime_result.get("research_object", {})
            object_id = str(research_object.get("object_id", ""))
            if ":" in object_id:
                return object_id.split(":")[-1].upper()
        parts = run_dir.name.split("_")
        return parts[-1].upper() if parts else ""

    def _is_debug_override_used(
        self,
        selection_mode: str,
        allowed_provider_names: list[str],
        ops_report: dict[str, Any] | None,
    ) -> bool:
        if selection_mode != "manual_override" or ops_report is None:
            return False
        provider_status = {
            str(item.get("provider_name")): str(item.get("portfolio_status"))
            for item in ops_report.get("providers", [])
        }
        return any(provider_status.get(provider_name) == "retired" for provider_name in allowed_provider_names)

    def _is_replay_compatible(self, path: Path) -> bool:
        if path.suffix not in {".json", ".csv", ".ndjson"}:
            return False
        return path.stem in REPLAY_COMPATIBLE_STEMS or path.stem.endswith("_snapshot")

    def _selection_key(self, allowed_provider_names: list[str]) -> str:
        return "+".join(sorted(allowed_provider_names)) if allowed_provider_names else "(none)"

    def _format_counter(self, values: dict[str, int]) -> str:
        if not values:
            return "(none)"
        return ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
