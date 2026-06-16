from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
from typing import Any


WORKER_TEST_HOOK_ENV = "ENHENGCLAW_WORKER_TEST_HOOK_JSON"


@dataclass(frozen=True, slots=True)
class WorkerTestHooks:
    fail_before_permit: bool = False
    fail_after_permit: bool = False
    crash_after_lease: bool = False
    sleep_after_lease_seconds: float = 0.0
    disable_heartbeat: bool = False
    stdout_text: str = ""
    stderr_text: str = ""
    stdout_nul: bool = False
    stderr_nul: bool = False

    @classmethod
    def from_env(cls) -> WorkerTestHooks:
        raw = os.getenv(WORKER_TEST_HOOK_ENV, "").strip()
        if not raw:
            return cls()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"{WORKER_TEST_HOOK_ENV} must be a JSON object")
        return cls(
            fail_before_permit=bool(payload.get("fail_before_permit", False)),
            fail_after_permit=bool(payload.get("fail_after_permit", False)),
            crash_after_lease=bool(payload.get("crash_after_lease", False)),
            sleep_after_lease_seconds=float(payload.get("sleep_after_lease_seconds", 0.0)),
            disable_heartbeat=bool(payload.get("disable_heartbeat", False)),
            stdout_text=str(payload.get("stdout_text", "")),
            stderr_text=str(payload.get("stderr_text", "")),
            stdout_nul=bool(payload.get("stdout_nul", False)),
            stderr_nul=bool(payload.get("stderr_nul", False)),
        )

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.fail_before_permit,
                self.fail_after_permit,
                self.crash_after_lease,
                self.sleep_after_lease_seconds > 0,
                self.disable_heartbeat,
                bool(self.stdout_text),
                bool(self.stderr_text),
                self.stdout_nul,
                self.stderr_nul,
            )
        )


def emit_test_stream_output(hooks: WorkerTestHooks) -> None:
    if hooks.stdout_text:
        sys.stdout.write(hooks.stdout_text)
        if not hooks.stdout_text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    if hooks.stderr_text:
        sys.stderr.write(hooks.stderr_text)
        if not hooks.stderr_text.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()
    if hooks.stdout_nul:
        sys.stdout.buffer.write(b"\x00")
        sys.stdout.flush()
    if hooks.stderr_nul:
        sys.stderr.buffer.write(b"\x00")
        sys.stderr.flush()

