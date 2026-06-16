from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    CAP_RUNTIME_EXECUTE,
    WORKER_LEASE_ID_ENV,
    WORKER_MODE_ENV,
    WORKER_PERMIT_PATH_ENV,
    ExecutionLeaseError,
    acquire_execution_lease,
    release_execution_lease,
)
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
)
from enhengclaw.governance.provider_selection import MODE_DEFAULT, ProviderRuntimeBinding
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeRunRequest, runtime_run_request_to_record
from enhengclaw.orchestration.shadow_ingestion_runner import (
    build_parser as build_shadow_ingestion_parser,
    main as shadow_ingestion_main,
    shadow_ingestion_request_from_args,
)
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


@dataclass(frozen=True, slots=True)
class AttackResult:
    name: str
    poc: str
    blocked: bool
    detail: str


def main() -> int:
    attacks: list[Callable[[], AttackResult]] = [
        attack_runtime_worker_direct_dispatch,
        attack_ingestion_worker_missing_permit,
        attack_runtime_worker_malformed_request_boundary,
        attack_ingestion_worker_malformed_request_boundary,
        attack_permit_concurrent_reuse,
        attack_permit_replay_after_release,
        attack_provider_private_helper_manual_spoof,
        attack_provider_subclass_manual_spoof,
        attack_legacy_controller_api_manual_spoof,
        attack_shadow_ingestion_controller_direct_provider,
    ]
    results = [attack() for attack in attacks]
    failures = [result for result in results if not result.blocked]
    for result in results:
        verdict = "BLOCKED" if result.blocked else "BYPASSED"
        print(f"{result.name}: {verdict}")
        print(f"  PoC: {result.poc}")
        print(f"  Detail: {result.detail}")
    if failures:
        print("REDTEAM RESULT: FAILED")
        return 1
    print("REDTEAM RESULT: ALL ATTACKS FAILED")
    print("CURRENT PHASE STATUS: PASS")
    return 0


def attack_runtime_worker_direct_dispatch() -> AttackResult:
    from enhengclaw.orchestration.runtime_worker import _dispatch

    poc = (
        "import runtime_worker._dispatch, manually acquire lease, forge worker env, "
        "call _dispatch('run_new', request_payload, permit=permit) in controller process"
    )
    try:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="redteam-runtime-dispatch",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            request_payload = runtime_run_request_to_record(
                RuntimeRunRequest(
                    mode="create",
                    object_id="redteam-runtime-dispatch",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=sample_signals("redteam-runtime-dispatch"),
                )
            )
            with manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.attack.runtime_worker_dispatch",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            ):
                _dispatch("run_new", request_payload, permit=permit)
    except Exception as exc:  # noqa: BLE001 - report exact block point
        return AttackResult("runtime_worker_direct_dispatch", poc, True, f"{type(exc).__name__}: {exc}")
    return AttackResult("runtime_worker_direct_dispatch", poc, False, "runtime worker dispatch executed in controller process")


def attack_ingestion_worker_missing_permit() -> AttackResult:
    poc = "launch ingestion_worker directly without --permit and without ENHENGCLAW_EXECUTION_PERMIT_PATH"
    with tempfile.TemporaryDirectory() as tmpdir:
        request_path = Path(tmpdir) / "request.json"
        artifacts_root = Path(tmpdir) / "artifacts"
        request_payload = shadow_ingestion_request_from_args(
            build_shadow_ingestion_parser().parse_args(
                [
                    "--artifacts-root",
                    str(artifacts_root),
                    "--run-seconds",
                    "0.1",
                    "--log-level",
                    "ERROR",
                ]
            )
        )
        request_path.write_text(
            json.dumps(request_payload, indent=2),
            encoding="utf-8",
        )
        env = pythonpath_env(
            {
                "BINANCE_API_KEY": "dummy-binance-key",
                "ALCHEMY_API_KEY": "dummy-alchemy-key",
                "ENHENGCLAW_EXECUTION_PERMIT_PATH": "",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "enhengclaw.orchestration.ingestion_worker",
                "--request",
                str(request_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
        )
        if completed.returncode != 0:
            return AttackResult(
                "ingestion_worker_missing_permit",
                poc,
                True,
                (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}",
            )
        return AttackResult("ingestion_worker_missing_permit", poc, False, "ingestion worker started without permit")


def attack_runtime_worker_malformed_request_boundary() -> AttackResult:
    poc = "launch runtime_worker with malformed run_new request missing object_type/scope"
    with execution_testbed() as bed:
        permit_path, _ = bed.issue_permit(
            slug="redteam-runtime-malformed",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / "request.json"
            response_path = Path(tmpdir) / "response.json"
            request_path.write_text(
                json.dumps({"mode": "create", "object_id": "malformed-runtime", "signals": []}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "enhengclaw.orchestration.runtime_worker",
                    "--method",
                    "run_new",
                    "--permit",
                    str(permit_path),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=pythonpath_env(),
            )
            if completed.returncode != 0 and not response_path.exists():
                return AttackResult(
                    "runtime_worker_malformed_request_boundary",
                    poc,
                    True,
                    (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}",
                )
            return AttackResult(
                "runtime_worker_malformed_request_boundary",
                poc,
                False,
                "runtime worker accepted malformed request payload",
            )


def attack_ingestion_worker_malformed_request_boundary() -> AttackResult:
    poc = "launch ingestion_worker with malformed request missing artifacts_root"
    with execution_testbed() as bed:
        permit_path, _ = bed.issue_permit(
            slug="redteam-ingestion-malformed",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / "request.json"
            request_path.write_text(json.dumps({"run_seconds": 0.1}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "enhengclaw.orchestration.ingestion_worker",
                    "--permit",
                    str(permit_path),
                    "--request",
                    str(request_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=pythonpath_env(
                    {
                        "BINANCE_API_KEY": "dummy-binance-key",
                        "ALCHEMY_API_KEY": "dummy-alchemy-key",
                    }
                ),
            )
            if completed.returncode != 0:
                return AttackResult(
                    "ingestion_worker_malformed_request_boundary",
                    poc,
                    True,
                    (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}",
                )
            return AttackResult(
                "ingestion_worker_malformed_request_boundary",
                poc,
                False,
                "ingestion worker accepted malformed request payload",
            )


def attack_permit_concurrent_reuse() -> AttackResult:
    poc = "race two acquire_execution_lease calls against the same permit from parallel threads"
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="redteam-concurrency",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()
        leases = []

        def _attempt(name: str) -> None:
            barrier.wait()
            try:
                lease = acquire_execution_lease(
                    permit,
                    permit_path=permit_path,
                    operation=f"runtime.redteam.concurrent.{name}",
                    requested_scope="spot+perp",
                    required_capabilities={CAP_RUNTIME_EXECUTE},
                )
            except Exception as exc:  # noqa: BLE001 - exact result matters
                with lock:
                    results.append(type(exc).__name__)
                return
            with lock:
                results.append("acquired")
                leases.append(lease)

        threads = [threading.Thread(target=_attempt, args=(label,), daemon=True) for label in ("one", "two")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        for lease in leases:
            release_execution_lease(lease, status="completed")

        if results.count("acquired") == 1 and results.count("ExecutionLeaseError") == 1:
            return AttackResult("permit_concurrent_reuse", poc, True, f"results={results}")
        return AttackResult("permit_concurrent_reuse", poc, False, f"concurrency race bypassed: results={results}")


def attack_permit_replay_after_release() -> AttackResult:
    poc = "acquire lease, release it, then attempt second acquire on the same permit"
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="redteam-replay",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        lease = acquire_execution_lease(
            permit,
            permit_path=permit_path,
            operation="runtime.redteam.replay.initial",
            requested_scope="spot+perp",
            required_capabilities={CAP_RUNTIME_EXECUTE},
        )
        release_execution_lease(lease, status="completed")
        try:
            acquire_execution_lease(
                permit,
                permit_path=permit_path,
                operation="runtime.redteam.replay.second",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            )
        except ExecutionLeaseError as exc:
            return AttackResult("permit_replay_after_release", poc, True, f"{type(exc).__name__}: {exc}")
        return AttackResult("permit_replay_after_release", poc, False, "permit was reusable after release")


def attack_provider_private_helper_manual_spoof() -> AttackResult:
    poc = "inherit valid permit, spoof worker env, call OfflineReplayCEXProvider._load_snapshot directly"
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="redteam-provider-helper",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        request = ProviderRequest(
            object_id="redteam-provider-helper",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
        provider = OfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
        try:
            with manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.redteam.provider_helper",
                requested_scope="spot+perp",
                required_capabilities={CAP_PROVIDER_FETCH},
            ):
                provider._load_snapshot(request)
        except Exception as exc:  # noqa: BLE001
            return AttackResult("provider_private_helper_manual_spoof", poc, True, f"{type(exc).__name__}: {exc}")
        return AttackResult("provider_private_helper_manual_spoof", poc, False, "provider private helper bypassed worker contract")


def attack_provider_subclass_manual_spoof() -> AttackResult:
    class ProbeOfflineReplayCEXProvider(OfflineReplayCEXProvider):
        pass

    poc = "subclass OfflineReplayCEXProvider and invoke inherited fetch under forged worker env"
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="redteam-provider-subclass",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        request = ProviderRequest(
            object_id="redteam-provider-subclass",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
        provider = ProbeOfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
        try:
            with manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.redteam.provider_subclass",
                requested_scope="spot+perp",
                required_capabilities={CAP_PROVIDER_FETCH},
            ):
                provider.fetch(request)
        except Exception as exc:  # noqa: BLE001
            return AttackResult("provider_subclass_manual_spoof", poc, True, f"{type(exc).__name__}: {exc}")
        return AttackResult("provider_subclass_manual_spoof", poc, False, "provider subclass inherited fetch bypassed worker contract")


def attack_legacy_controller_api_manual_spoof() -> AttackResult:
    poc = "spoof worker env with valid lease and call RuntimeOrchestrator.run_new_from_provider_bindings in controller process"
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="redteam-legacy-api",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        runtime = RuntimeOrchestrator(execution_permit=permit)
        portfolio_report = ProviderPortfolioPolicy().evaluate_all(
            [
                ProviderPortfolioInput(
                    provider_name="binance-public-cex",
                    provider_type="cex",
                    current_status=STATUS_ACTIVE,
                    contribution_ledger=None,
                    promotion_report=None,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="binance-public-cex",
                        status="ok",
                        finding_count=0,
                        error_count=0,
                        warning_count=0,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="binance-public-cex",
                        passed=True,
                        scenario_count=1,
                        notes=["green"],
                    ),
                )
            ]
        )
        provider_bindings = [
            ProviderRuntimeBinding(
                provider_name="binance-public-cex",
                provider_type="cex",
                adapter=object(),
            )
        ]
        try:
            with manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.redteam.legacy_api",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            ):
                runtime.run_new_from_provider_bindings(
                    object_id="redteam-legacy-api",
                    object_type=ObjectType.ASSET,
                    subject="AIX",
                    scope="spot+perp",
                    scenario="bullish_publish",
                    portfolio_report=portfolio_report,
                    provider_bindings=provider_bindings,
                    selection_mode=MODE_DEFAULT,
                )
        except Exception as exc:  # noqa: BLE001
            return AttackResult("legacy_controller_api_manual_spoof", poc, True, f"{type(exc).__name__}: {exc}")
        return AttackResult("legacy_controller_api_manual_spoof", poc, False, "legacy controller API became callable again")


def attack_shadow_ingestion_controller_direct_provider() -> AttackResult:
    poc = "invoke shadow_ingestion_main while stubbing worker launch and verify no replay/quarantine side effects are created"
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir) / "artifacts"
        fake_permit = Path(tmpdir) / "missing_execution_permit.json"
        captured: dict[str, object] = {}

        class _FakeStream:
            def to_payload(self) -> dict[str, object]:
                return {"byte_count": 0, "contains_nul": False, "line_count": 0}

        class _FakeAuditResult:
            returncode = 0
            worker_pid = os.getpid()
            stdout = _FakeStream()
            stderr = _FakeStream()

        def _fake_run(command: list[str], *, env: dict[str, str], run_root: Path):
            request_path = Path(command[command.index("--request") + 1])
            captured["payload"] = json.loads(request_path.read_text(encoding="utf-8"))
            return _FakeAuditResult()

        from unittest.mock import patch

        with patch("enhengclaw.orchestration.shadow_ingestion_runner.audited_subprocess_run", new=_fake_run):
            exit_code = shadow_ingestion_main(
                [
                    "--artifacts-root",
                    str(artifacts_root),
                    "--execution-permit",
                    str(fake_permit),
                    "--run-seconds",
                    "1",
                ]
            )
        if (
            exit_code == 0
            and not (artifacts_root / "live_replay").exists()
            and not (artifacts_root / "live_quarantine").exists()
            and dict(captured.get("payload", {})).get("payload", {}).get("artifacts_root") == str(artifacts_root.resolve())
        ):
            return AttackResult(
                "shadow_ingestion_controller_direct_provider",
                poc,
                True,
                "controller only serialized request payload and delegated to ingestion_worker",
            )
        return AttackResult(
            "shadow_ingestion_controller_direct_provider",
            poc,
            False,
            "shadow ingestion controller touched provider side effects directly",
        )


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class manual_worker_lease:
    def __init__(
        self,
        *,
        permit,
        permit_path: Path,
        operation: str,
        requested_scope: str,
        required_capabilities: set[str],
    ) -> None:
        self.permit = permit
        self.permit_path = permit_path
        self.operation = operation
        self.requested_scope = requested_scope
        self.required_capabilities = required_capabilities
        self.lease = None
        self.saved_env: dict[str, str | None] = {}

    def __enter__(self):
        self.lease = acquire_execution_lease(
            self.permit,
            permit_path=self.permit_path,
            operation=self.operation,
            requested_scope=self.requested_scope,
            required_capabilities=self.required_capabilities,
        )
        self.saved_env = {
            WORKER_MODE_ENV: os.getenv(WORKER_MODE_ENV),
            WORKER_LEASE_ID_ENV: os.getenv(WORKER_LEASE_ID_ENV),
            WORKER_PERMIT_PATH_ENV: os.getenv(WORKER_PERMIT_PATH_ENV),
        }
        os.environ[WORKER_MODE_ENV] = "1"
        os.environ[WORKER_LEASE_ID_ENV] = self.lease.lease_id
        os.environ[WORKER_PERMIT_PATH_ENV] = str(self.permit_path)
        return self.lease

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.lease is not None:
            try:
                release_execution_lease(self.lease, status="completed")
            except ExecutionLeaseError:
                pass
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
