from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.utils.binance_http import BinanceHttpError, binance_get_json


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


class BinanceHttpTests(unittest.TestCase):
    def test_retries_retryable_429_then_succeeds(self) -> None:
        attempts: list[str] = []
        sleeps: list[float] = []

        def fake_urlopen(request, timeout):
            attempts.append(str(request.full_url))
            if len(attempts) == 1:
                raise HTTPError(
                    url=request.full_url,
                    code=429,
                    msg="Too Many Requests",
                    hdrs=None,
                    fp=io.BytesIO(b'{"code":-1003,"msg":"Too many requests"}'),
                )
            return _FakeResponse(json.dumps({"status": "ok"}).encode("utf-8"))

        payload = binance_get_json(
            "https://api.binance.com/api/v3/time",
            urlopen_fn=fake_urlopen,
            sleep_fn=sleeps.append,
            max_attempts=3,
            backoff_seconds=0.5,
        )

        self.assertEqual(payload, {"status": "ok"})
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleeps, [0.5])

    def test_non_retryable_400_fails_without_retry(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            attempts.append(str(request.full_url))
            raise HTTPError(
                url=request.full_url,
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"code":-1100,"msg":"Bad request"}'),
            )

        with self.assertRaises(BinanceHttpError) as exc_context:
            binance_get_json(
                "https://api.binance.com/api/v3/ticker",
                urlopen_fn=fake_urlopen,
                sleep_fn=lambda _: None,
                max_attempts=3,
            )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(exc_context.exception.status_code, 400)
        self.assertFalse(exc_context.exception.retryable)


if __name__ == "__main__":
    unittest.main()
