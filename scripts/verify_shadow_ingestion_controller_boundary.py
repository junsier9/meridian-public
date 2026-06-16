from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.orchestration.shadow_ingestion_runner import main as shadow_ingestion_main
from enhengclaw.orchestration.worker_operations import StreamCaptureMetrics, SubprocessAuditResult


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir) / "artifacts"
        fake_permit = Path(tmpdir) / "missing_execution_permit.json"
        captured: dict[str, object] = {}

        def _fake_run(command: list[str], *, env: dict[str, str], run_root: Path):
            request_path = Path(command[command.index("--request") + 1])
            captured["command"] = list(command)
            captured["payload"] = json.loads(request_path.read_text(encoding="utf-8"))
            captured["request_path"] = request_path
            captured["env"] = dict(env)
            captured["run_root"] = run_root
            return SubprocessAuditResult(
                returncode=0,
                worker_pid=31337,
                stdout=StreamCaptureMetrics("stdout", 0, 0, False, 0),
                stderr=StreamCaptureMetrics("stderr", 0, 0, False, 0),
            )

        with patch(
            "enhengclaw.orchestration.shadow_ingestion_runner.audited_subprocess_run",
            new=_fake_run,
        ):
            exit_code = shadow_ingestion_main(
                [
                    "--artifacts-root",
                    str(artifacts_root),
                    "--execution-permit",
                    str(fake_permit),
                    "--run-seconds",
                    "5",
                ]
            )

        assert exit_code == 0, f"controller returned unexpected exit code: {exit_code}"
        command = captured["command"]
        payload = captured["payload"]
        request_path = Path(captured["request_path"])

        assert command[0] == sys.executable, f"unexpected worker executable: {command[0]}"
        assert command[1:3] == ["-m", "enhengclaw.orchestration.ingestion_worker"], command
        assert payload["schema_version"] == "worker-request.v1", payload
        assert payload["request_kind"] == "ingestion", payload
        assert payload["payload"]["artifacts_root"] == str(artifacts_root.resolve()), payload
        assert not (artifacts_root / "live_replay").exists(), "controller wrote live_replay artifacts directly"
        assert not (artifacts_root / "live_quarantine").exists(), "controller wrote live_quarantine artifacts directly"
        assert not request_path.exists(), "controller did not clean up serialized request"

    print("OK: shadow_ingest CLI only serialized a request and delegated execution to ingestion_worker.")
    print("OK: without launching the worker, the CLI process wrote no ingestion artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
