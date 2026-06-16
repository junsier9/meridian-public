from __future__ import annotations

from datetime import UTC, datetime
import re


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _default_run_id(*, strategy_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "-", strategy_label).strip("-")
    return f"{stamp}-{safe_label}"


def _today_compact() -> str:
    return datetime.now(UTC).strftime("%Y_%m_%d")
