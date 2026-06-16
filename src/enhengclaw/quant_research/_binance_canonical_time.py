from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _date_to_ms(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp() * 1000)


def _ms_to_date(value: int) -> date:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC).date()


def _date_utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(
        pd.to_numeric(values, errors="coerce").astype("Int64"),
        unit="ms",
        utc=True,
    ).dt.date.astype(str)
