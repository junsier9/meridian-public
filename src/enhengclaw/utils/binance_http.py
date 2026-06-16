from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RETRYABLE_HTTP_STATUS_CODES = frozenset({418, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class BinanceHttpError(RuntimeError):
    url: str
    attempt: int
    max_attempts: int
    status_code: int | None
    reason: str
    detail: str | None = None

    @property
    def retryable(self) -> bool:
        return self.status_code in RETRYABLE_HTTP_STATUS_CODES or self.status_code is None

    def __str__(self) -> str:
        code = "network" if self.status_code is None else f"HTTP {self.status_code}"
        suffix = "" if not self.detail else f": {self.detail}"
        return f"{code} for Binance request {self.url} ({self.reason}){suffix}"


def binance_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    backoff_seconds: float = 0.25,
    urlopen_fn: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    raw = binance_get_bytes(
        url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
    )
    return json.loads(raw.decode("utf-8"))


def binance_get_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    backoff_seconds: float = 0.25,
    urlopen_fn: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bytes:
    opener = urlopen if urlopen_fn is None else urlopen_fn
    request = Request(url, headers={"User-Agent": "EnhengClaw/0.1", **(headers or {})})
    last_error: BinanceHttpError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with opener(request, timeout=timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = BinanceHttpError(
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=exc.code,
                reason="http_error",
                detail=detail,
            )
            if exc.code not in RETRYABLE_HTTP_STATUS_CODES or attempt >= max_attempts:
                raise last_error from exc
        except URLError as exc:
            last_error = BinanceHttpError(
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=None,
                reason="timeout" if isinstance(exc.reason, socket.timeout) else "url_error",
                detail=str(exc.reason),
            )
            if attempt >= max_attempts:
                raise last_error from exc
        except TimeoutError as exc:
            last_error = BinanceHttpError(
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=None,
                reason="timeout",
                detail=str(exc),
            )
            if attempt >= max_attempts:
                raise last_error from exc
        except OSError as exc:
            last_error = BinanceHttpError(
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=None,
                reason="os_error",
                detail=str(exc),
            )
            if attempt >= max_attempts:
                raise last_error from exc
        sleep_fn(backoff_seconds * attempt)

    assert last_error is not None
    raise last_error
