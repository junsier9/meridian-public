from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from enhengclaw.providers.providers import CEXProviderPayload, OnchainProviderPayload


REQUIRED_TOP_LEVEL_KEYS = {"provider", "retrieved_at", "scenario_tag", "instrument", "events"}


@dataclass(slots=True)
class DriftFinding:
    severity: str
    code: str
    message: str


@dataclass(slots=True)
class DriftSummary:
    top_level_keys: list[str]
    events_count: int
    raw_http_present: bool
    metadata_provider_matches: bool
    metadata_scenario_matches: bool
    metadata_record_count_matches: bool
    metadata_timestamp_matches: bool
    latest_kline_close: str | None
    latest_kline_lag_minutes: float | None


@dataclass(slots=True)
class DriftReport:
    status: str
    summary: DriftSummary
    findings: list[DriftFinding] = field(default_factory=list)

    @property
    def should_reject(self) -> bool:
        return any(finding.severity == "error" for finding in self.findings)

    @property
    def is_drifted(self) -> bool:
        return bool(self.findings)


class CEXDriftInspector:
    metadata_time_skew_tolerance = timedelta(minutes=5)
    hard_stale_lag = timedelta(hours=2)
    soft_stale_lag = timedelta(minutes=30)

    def inspect(self, payload: CEXProviderPayload) -> DriftReport:
        raw = payload.raw_payload
        findings: list[DriftFinding] = []
        top_level_keys = sorted(str(key) for key in raw.keys()) if isinstance(raw, dict) else []
        events = raw.get("events", []) if isinstance(raw, dict) else []
        events_count = len(events) if isinstance(events, list) else 0
        raw_http = raw.get("raw_http") if isinstance(raw, dict) else None

        missing_keys = sorted(REQUIRED_TOP_LEVEL_KEYS - set(top_level_keys))
        if missing_keys:
            findings.append(
                DriftFinding("error", "missing_top_level_keys", f"missing required top-level keys: {', '.join(missing_keys)}")
            )

        raw_http_present = isinstance(raw_http, dict)
        if not raw_http_present:
            findings.append(DriftFinding("warning", "missing_raw_http", "raw_http block is missing"))

        metadata_provider_matches = payload.metadata.provider_name == str(raw.get("provider")) if isinstance(raw, dict) else False
        metadata_scenario_matches = payload.metadata.scenario == str(raw.get("scenario_tag")) if isinstance(raw, dict) else False
        metadata_record_count_matches = payload.metadata.raw_record_count == events_count
        metadata_timestamp_matches = False
        latest_kline_close: str | None = None
        latest_kline_lag_minutes: float | None = None

        if not metadata_provider_matches:
            findings.append(DriftFinding("error", "provider_mismatch", "metadata.provider_name does not match raw provider"))
        if not metadata_scenario_matches:
            findings.append(DriftFinding("error", "scenario_mismatch", "metadata.scenario does not match raw scenario_tag"))
        if not metadata_record_count_matches:
            findings.append(DriftFinding("error", "record_count_mismatch", "metadata.raw_record_count does not match events length"))

        raw_retrieved_at = self._parse_datetime(raw.get("retrieved_at")) if isinstance(raw, dict) else None
        if raw_retrieved_at is not None:
            metadata_timestamp_matches = abs(payload.metadata.retrieved_at - raw_retrieved_at) <= self.metadata_time_skew_tolerance
            if not metadata_timestamp_matches:
                findings.append(
                    DriftFinding("error", "retrieved_at_skew", "metadata.retrieved_at is inconsistent with raw retrieved_at")
                )
        else:
            findings.append(DriftFinding("error", "invalid_retrieved_at", "raw retrieved_at is missing or invalid"))

        if not isinstance(events, list):
            findings.append(DriftFinding("error", "events_not_list", "events is not a list"))
        else:
            if events_count == 0:
                findings.append(DriftFinding("warning", "empty_events", "events list is empty"))
            elif events_count < 2:
                findings.append(DriftFinding("warning", "partial_events", "events list contains fewer than two entries"))

        if raw_http_present:
            latest_kline_close, latest_kline_lag_minutes, kline_finding = self._inspect_kline_sanity(
                payload.metadata.retrieved_at,
                raw_http,
            )
            if kline_finding is not None:
                findings.append(kline_finding)

        status = "error" if any(finding.severity == "error" for finding in findings) else "warning" if findings else "ok"
        return DriftReport(
            status=status,
            summary=DriftSummary(
                top_level_keys=top_level_keys,
                events_count=events_count,
                raw_http_present=raw_http_present,
                metadata_provider_matches=metadata_provider_matches,
                metadata_scenario_matches=metadata_scenario_matches,
                metadata_record_count_matches=metadata_record_count_matches,
                metadata_timestamp_matches=metadata_timestamp_matches,
                latest_kline_close=latest_kline_close,
                latest_kline_lag_minutes=latest_kline_lag_minutes,
            ),
            findings=findings,
        )

    def _inspect_kline_sanity(
        self,
        retrieved_at: datetime,
        raw_http: dict[str, Any],
    ) -> tuple[str | None, float | None, DriftFinding | None]:
        klines = raw_http.get("klines")
        if not isinstance(klines, list) or not klines:
            return None, None, DriftFinding("warning", "missing_klines", "raw_http.klines is missing or empty")
        latest = klines[-1]
        if not isinstance(latest, list) or len(latest) <= 6:
            return None, None, DriftFinding("error", "invalid_kline_shape", "latest kline does not contain a close timestamp")
        try:
            close_time_ms = int(latest[6])
        except (TypeError, ValueError):
            return None, None, DriftFinding("error", "invalid_kline_close_time", "latest kline close timestamp is not int-like")

        close_dt = datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)
        lag = retrieved_at - close_dt
        lag_minutes = round(lag.total_seconds() / 60, 2)
        if close_dt - retrieved_at > self.metadata_time_skew_tolerance:
            return close_dt.isoformat(), lag_minutes, DriftFinding(
                "error",
                "future_kline_close",
                "latest kline close timestamp is ahead of provider retrieved_at",
            )
        if lag > self.hard_stale_lag:
            return close_dt.isoformat(), lag_minutes, DriftFinding(
                "error",
                "stale_kline_close",
                "latest kline close timestamp is too old relative to provider retrieved_at",
            )
        if lag > self.soft_stale_lag:
            return close_dt.isoformat(), lag_minutes, DriftFinding(
                "warning",
                "lagging_kline_close",
                "latest kline close timestamp is lagging behind provider retrieved_at",
            )
        return close_dt.isoformat(), lag_minutes, None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None


@dataclass(slots=True)
class OnchainDriftSummary:
    row_keys: list[str]
    row_count: int
    raw_http_present: bool
    metadata_provider_matches: bool
    metadata_record_count_matches: bool
    metadata_timestamp_matches: bool


@dataclass(slots=True)
class OnchainDriftReport:
    status: str
    summary: OnchainDriftSummary
    findings: list[DriftFinding] = field(default_factory=list)

    @property
    def should_reject(self) -> bool:
        return any(finding.severity == "error" for finding in self.findings)

    @property
    def is_drifted(self) -> bool:
        return bool(self.findings)


class OnchainDriftInspector:
    metadata_time_skew_tolerance = timedelta(minutes=5)

    def inspect(self, payload: OnchainProviderPayload) -> OnchainDriftReport:
        rows = payload.raw_payload
        findings: list[DriftFinding] = []
        row_count = len(rows) if isinstance(rows, list) else 0
        row_keys = sorted(str(key) for key in rows[0].keys()) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else []

        if not isinstance(rows, list):
            findings.append(DriftFinding("error", "rows_not_list", "onchain raw_payload is not a list"))
        elif row_count == 0:
            findings.append(DriftFinding("warning", "empty_rows", "onchain raw_payload has no rows"))

        metadata_record_count_matches = payload.metadata.raw_record_count == row_count
        if not metadata_record_count_matches:
            findings.append(DriftFinding("error", "record_count_mismatch", "metadata.raw_record_count does not match row count"))

        metadata_provider_matches = True
        metadata_timestamp_matches = True
        raw_http_present = False

        if isinstance(rows, list):
            for idx, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    findings.append(DriftFinding("error", "invalid_row", f"row #{idx} is not an object"))
                    continue
                provider_name = str(row.get("provider", ""))
                if provider_name != payload.metadata.provider_name:
                    metadata_provider_matches = False
                row_retrieved_at = self._parse_datetime(row.get("retrieved_at"))
                if row_retrieved_at is None or abs(payload.metadata.retrieved_at - row_retrieved_at) > self.metadata_time_skew_tolerance:
                    metadata_timestamp_matches = False
                if any(key.startswith("raw_http_") and str(value).strip() for key, value in row.items()):
                    raw_http_present = True

        if not metadata_provider_matches:
            findings.append(DriftFinding("error", "provider_mismatch", "metadata.provider_name does not match row provider values"))
        if not metadata_timestamp_matches:
            findings.append(DriftFinding("error", "retrieved_at_skew", "metadata.retrieved_at is inconsistent with row retrieved_at values"))
        if not raw_http_present and row_count > 0:
            findings.append(DriftFinding("warning", "missing_raw_http", "onchain rows do not include raw_http_* fields"))

        status = "error" if any(finding.severity == "error" for finding in findings) else "warning" if findings else "ok"
        return OnchainDriftReport(
            status=status,
            summary=OnchainDriftSummary(
                row_keys=row_keys,
                row_count=row_count,
                raw_http_present=raw_http_present,
                metadata_provider_matches=metadata_provider_matches,
                metadata_record_count_matches=metadata_record_count_matches,
                metadata_timestamp_matches=metadata_timestamp_matches,
            ),
            findings=findings,
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
