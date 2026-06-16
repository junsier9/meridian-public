from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
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
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


class BoundaryFailClosedTests(unittest.TestCase):
    def test_runtime_private_kernel_rejects_manual_worker_env_spoof(self) -> None:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="runtime-spoof",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            with _manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.attack.manual_spoof",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            ):
                with self.assertRaises(RuntimeBoundaryError):
                    RuntimeOrchestrator(execution_permit=permit)._run_new_impl(
                        object_id="spoofed-runtime-kernel",
                        object_type=ObjectType.ASSET,
                        scope="spot+perp",
                        signals=sample_signals("spoofed-runtime"),
                    )

    def test_runtime_private_continue_kernel_rejects_manual_worker_env_spoof(self) -> None:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="runtime-continue-spoof",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            with _manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.attack.manual_continue_spoof",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            ):
                with self.assertRaises(RuntimeBoundaryError):
                    RuntimeOrchestrator(execution_permit=permit)._continue_existing_impl(
                        object_id="spoofed-runtime-continue",
                        signals=sample_signals("spoofed-runtime-continue"),
                    )

    def test_provider_private_helper_rejects_manual_worker_env_spoof(self) -> None:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="provider-helper-spoof",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            request = ProviderRequest(
                object_id="helper-spoof",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
            )
            provider = OfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
            with _manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="provider.attack.manual_spoof",
                requested_scope="spot+perp",
                required_capabilities={CAP_PROVIDER_FETCH},
            ):
                with self.assertRaises(ExecutionLeaseError):
                    provider._load_snapshot(request)

    def test_provider_subclass_inherited_fetch_rejects_manual_worker_env_spoof(self) -> None:
        class ProbeOfflineReplayCEXProvider(OfflineReplayCEXProvider):
            pass

        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="provider-subclass-spoof",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            request = ProviderRequest(
                object_id="subclass-spoof",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
            )
            provider = ProbeOfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
            with _manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="provider.attack.subclass_spoof",
                requested_scope="spot+perp",
                required_capabilities={CAP_PROVIDER_FETCH},
            ):
                with self.assertRaises(ExecutionLeaseError):
                    provider.fetch(request)

    def test_legacy_controller_api_rejects_manual_worker_env_spoof(self) -> None:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="legacy-api-spoof",
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
            with _manual_worker_lease(
                permit=permit,
                permit_path=permit_path,
                operation="runtime.attack.legacy_api_spoof",
                requested_scope="spot+perp",
                required_capabilities={CAP_RUNTIME_EXECUTE},
            ):
                with self.assertRaises(RuntimeBoundaryError):
                    runtime.run_new_from_provider_bindings(
                        object_id="legacy-api-spoof",
                        object_type=ObjectType.ASSET,
                        subject="AIX",
                        scope="spot+perp",
                        scenario="bullish_publish",
                        portfolio_report=portfolio_report,
                        provider_bindings=provider_bindings,
                        selection_mode=MODE_DEFAULT,
                    )

    def test_concurrent_permit_reuse_is_fail_closed(self) -> None:
        with execution_testbed() as bed:
            permit_path, permit = bed.issue_permit(
                slug="lease-concurrency",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            barrier = threading.Barrier(2)
            results: list[tuple[str, str]] = []
            lock = threading.Lock()
            leases = []

            def _attempt(name: str) -> None:
                barrier.wait()
                try:
                    lease = acquire_execution_lease(
                        permit,
                        permit_path=permit_path,
                        operation=f"runtime.concurrent.{name}",
                        requested_scope="spot+perp",
                        required_capabilities={CAP_RUNTIME_EXECUTE},
                    )
                except Exception as exc:  # noqa: BLE001 - assertion needs exact failure class
                    with lock:
                        results.append((name, type(exc).__name__))
                    return
                with lock:
                    results.append((name, "acquired"))
                    leases.append(lease)

            threads = [
                threading.Thread(target=_attempt, args=("one",), daemon=True),
                threading.Thread(target=_attempt, args=("two",), daemon=True),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertEqual(sum(1 for _, status in results if status == "acquired"), 1, results)
            self.assertEqual(sum(1 for _, status in results if status == "ExecutionLeaseError"), 1, results)

            for lease in leases:
                release_execution_lease(lease, status="completed")

    def test_runtime_worker_malformed_request_fails_closed(self) -> None:
        with execution_testbed() as bed:
            permit_path, _ = bed.issue_permit(
                slug="runtime-malformed-request",
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
                    env=_pythonpath_env(),
                    cwd=ROOT,
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertFalse(response_path.exists())
                self.assertFalse((bed.session_root / "malformed-runtime.json").exists())

    def test_ingestion_worker_malformed_request_fails_closed(self) -> None:
        with execution_testbed() as bed:
            permit_path, _ = bed.issue_permit(
                slug="ingestion-malformed-request",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                artifacts_root = Path(tmpdir) / "artifacts"
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
                    env=_pythonpath_env(
                        {
                            "BINANCE_API_KEY": "dummy-binance-key",
                            "ALCHEMY_API_KEY": "dummy-alchemy-key",
                        }
                    ),
                    cwd=ROOT,
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertFalse((artifacts_root / "live_replay").exists())
                self.assertFalse((artifacts_root / "live_quarantine").exists())


def _pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class _manual_worker_lease:
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
    unittest.main()
