from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
import importlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.schemas.evidence_agent import EvidenceSignalDraft
from enhengclaw.agents.owner_state import (
    CapabilityStatus,
    DelegateCallContext,
    DelegateCapabilityRecord,
    OwnerArtifactWriter,
    OwnerRunRecord,
    OwnerRunState,
    OwnerWorkSpec,
    build_owner_run_id,
    compute_delegate_capability_id,
    compute_spec_fingerprint,
)
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_evidence_signal,
)
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.execution_control import (
    ALLOW_WRITABLE_TRUST_ROOT_ENV,
    CAP_PROVIDER_FETCH,
    CAP_RUNTIME_EXECUTE,
    GlobalFreezeActiveError,
    LEASE_REGISTRY_PATH_ENV,
    MissingExecutionPermitError,
    TRUST_ROOT_DIR_ENV,
    ExecutionLeaseError,
    clear_global_freeze,
    issue_execution_permit,
    load_execution_permit,
    trigger_global_freeze,
)
from enhengclaw.core.session import RUNTIME_SESSION_ROOT_ENV
from enhengclaw.core.signals import Signal
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest
import enhengclaw.core.execution_control as execution_control_module


class ExecutionControlEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)
        self.trust_root = root / "trust-root"
        self.trust_root.mkdir(parents=True, exist_ok=True)
        self.session_root = root / "runtime-sessions"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.lease_registry_path = root / "execution-leases.sqlite3"
        self.signing_private_key = root / "execution_signer"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(self.signing_private_key),
            ],
            check=True,
            capture_output=True,
        )
        public_key = self.signing_private_key.with_suffix(".pub").read_text(encoding="utf-8").strip()
        (self.trust_root / "allowed_signers").write_text(
            f"execution-permit {public_key}\n",
            encoding="utf-8",
        )
        self._saved_env = {
            TRUST_ROOT_DIR_ENV: os.getenv(TRUST_ROOT_DIR_ENV),
            ALLOW_WRITABLE_TRUST_ROOT_ENV: os.getenv(ALLOW_WRITABLE_TRUST_ROOT_ENV),
            LEASE_REGISTRY_PATH_ENV: os.getenv(LEASE_REGISTRY_PATH_ENV),
            RUNTIME_SESSION_ROOT_ENV: os.getenv(RUNTIME_SESSION_ROOT_ENV),
        }
        os.environ[TRUST_ROOT_DIR_ENV] = str(self.trust_root)
        os.environ[ALLOW_WRITABLE_TRUST_ROOT_ENV] = "1"
        os.environ[LEASE_REGISTRY_PATH_ENV] = str(self.lease_registry_path)
        os.environ[RUNTIME_SESSION_ROOT_ENV] = str(self.session_root)
        self.addCleanup(self._restore_env)

    def test_runtime_requires_execution_permit(self) -> None:
        with self.assertRaises(MissingExecutionPermitError):
            RuntimeOrchestrator().run_new(
                object_id="no-permit-runtime",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=self._signals("no-permit"),
            )

    def test_cross_platform_ref_path_coerces_windows_path_for_posix_validation(self) -> None:
        with patch.object(execution_control_module.os, "name", "posix"):
            resolved = execution_control_module._coerce_cross_platform_ref_path(
                r"C:\Users\user\AppData\Local\EnhengClaw\openclaw_live_market_observer\permit\owner_review.json"
            )
        self.assertEqual(
            resolved.as_posix(),
            "/mnt/c/Users/user/AppData/Local/EnhengClaw/openclaw_live_market_observer/permit/owner_review.json",
        )

    def test_evidence_agent_direct_submit_requires_owner_context(self) -> None:
        with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
            submit_evidence_signal(
                runtime=RuntimeOrchestrator(),
                object_id="no-permit-evidence",
                signal=EvidenceSignalDraft(
                    input_id="no-permit-evidence",
                    subject="AIX",
                    predicate="followup_signal",
                    value="bounded follow-up evidence without a permit",
                    confidence_hint=66,
                ),
            )

    def test_runtime_public_module_exposes_only_owner_first_surface(self) -> None:
        runtime_module = importlib.import_module("enhengclaw.orchestration.runtime")
        self.assertFalse(hasattr(runtime_module, "RuntimeOrchestrator"))
        self.assertEqual(
            tuple(runtime_module.__all__),
            (
                "GovernedAgentOrchestrator",
                "GovernedWriteRequest",
                "GovernedWriteResult",
                "InvalidOwnerRunTransitionError",
            ),
        )

    def test_evidence_agent_direct_submit_rejects_legacy_delegate_context(self) -> None:
        with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
            submit_evidence_signal(
                runtime=RuntimeOrchestrator(),
                object_id="legacy-context-evidence",
                signal=EvidenceSignalDraft(
                    input_id="legacy-context-evidence",
                    subject="AIX",
                    predicate="followup_signal",
                    value="legacy DelegateCallContext should no longer authorize a delegate write",
                    confidence_hint=66,
                ),
                call_context=DelegateCallContext(
                    initiated_by="forged-controller",
                    owner_run_id="forged-run",
                    spec_version=1,
                    step_id="forged-step",
                    idempotency_key="forged-idempotency",
                    requested_delegate_id="evidence_agent",
                ),
            )

    def test_evidence_agent_direct_submit_rejects_forged_or_stale_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RuntimeOrchestrator()
            artifact_store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            run_id = build_owner_run_id(requested_delegate_id="risk_signal_agent", object_id="forged-capability-aix")
            spec = OwnerWorkSpec(
                run_id=run_id,
                owner_agent_id="rulebook_owner",
                requested_delegate_id="risk_signal_agent",
                object_id="forged-capability-aix",
                subject="AIX",
                scope="spot+perp",
                user_intent="Reject forged capability use across delegates.",
            )
            artifact_store.write_spec(spec)
            artifact_store.write_run_state(
                OwnerRunRecord(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    requested_delegate_id="risk_signal_agent",
                    object_id="forged-capability-aix",
                    subject="AIX",
                    scope="spot+perp",
                    state=OwnerRunState.DELEGATED.value,
                    spec_version=1,
                    spec_fingerprint=compute_spec_fingerprint(spec),
                    current_step_id="risk_signal_agent:1:abc",
                    current_idempotency_key="idem-abc",
                )
            )
            capability_id = compute_delegate_capability_id(
                owner_run_id=run_id,
                requested_delegate_id="risk_signal_agent",
                spec_version=1,
                step_id="risk_signal_agent:1:abc",
                idempotency_key="idem-abc",
                object_id="forged-capability-aix",
                subject="AIX",
                scope="spot+perp",
            )
            artifact_store.write_capability(
                DelegateCapabilityRecord(
                    capability_id=capability_id,
                    owner_run_id=run_id,
                    requested_delegate_id="risk_signal_agent",
                    spec_version=1,
                    step_id="risk_signal_agent:1:abc",
                    idempotency_key="idem-abc",
                    object_id="forged-capability-aix",
                    subject="AIX",
                    scope="spot+perp",
                    status=CapabilityStatus.STALE.value,
                )
            )

            with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                submit_evidence_signal(
                    runtime=runtime,
                    object_id="forged-capability-aix",
                    signal=EvidenceSignalDraft(
                        input_id="forged-capability-evidence",
                        subject="AIX",
                        predicate="followup_signal",
                        value="capabilities issued for another delegate or stale runs must be rejected",
                        confidence_hint=66,
                    ),
                    delegate_capability=capability_id,
                    artifact_store=artifact_store,
                )

    def test_provider_fetch_requires_worker_execution_boundary(self) -> None:
        provider = OfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
        with self.assertRaises(ExecutionLeaseError):
            provider.fetch(
                ProviderRequest(
                    object_id="no-permit-provider",
                    object_type=ObjectType.ASSET,
                    subject="AIX",
                    scope="spot+perp",
                    scenario="bullish_publish",
                )
            )
        with self.assertRaises(ExecutionLeaseError):
            provider._load_snapshot(
                ProviderRequest(
                    object_id="no-permit-helper",
                    object_type=ObjectType.ASSET,
                    subject="AIX",
                    scope="spot+perp",
                    scenario="bullish_publish",
                )
            )

    def test_valid_permit_dispatches_runtime_through_worker(self) -> None:
        permit = self._issue_permit(
            root=Path(self.tempdir.name) / "permit-runtime",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        result = RuntimeOrchestrator(execution_permit=permit).run_new(
            object_id="permit-runtime",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=self._signals("permit"),
        )
        self.assertIn(result.decision.decision, {"publish", "monitoring"})
        self.assertTrue((self.session_root / "permit-runtime.json").exists())

    def test_controller_cannot_call_runtime_kernel_directly(self) -> None:
        with self.assertRaises(RuntimeBoundaryError):
            RuntimeOrchestrator()._run_new_impl(
                object_id="direct-kernel-call",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=self._signals("direct"),
            )

    def test_permit_replay_is_blocked_after_first_consumption(self) -> None:
        permit = self._issue_permit(
            root=Path(self.tempdir.name) / "permit-replay",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        orchestrator = RuntimeOrchestrator(execution_permit=permit)
        orchestrator.run_new(
            object_id="replay-first",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=self._signals("first"),
        )
        with self.assertRaises(RuntimeBoundaryError) as ctx:
            orchestrator.run_new(
                object_id="replay-second",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=self._signals("second"),
            )
        self.assertIn("already consumed", str(ctx.exception))

    def test_global_freeze_blocks_before_worker_dispatch(self) -> None:
        freeze_path = Path(self.tempdir.name) / "global-freeze.json"
        permit = self._issue_permit(
            root=Path(self.tempdir.name) / "permit-freeze",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
            global_freeze_path=freeze_path,
        )
        trigger_global_freeze(reason="test freeze", freeze_path=freeze_path)
        try:
            with self.assertRaises(GlobalFreezeActiveError):
                RuntimeOrchestrator(execution_permit=permit).run_new(
                    object_id="frozen-runtime",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=self._signals("freeze"),
                )
        finally:
            clear_global_freeze(freeze_path)

    def _issue_permit(
        self,
        *,
        root: Path,
        scope: str,
        capabilities: list[str],
        allowed_operations: list[str],
        global_freeze_path: Path | None = None,
    ):
        root.mkdir(parents=True, exist_ok=True)
        owner_review = root / "owner_review.json"
        owner_review.write_text(
            '{"status":"passed","scope":"%s"}' % scope,
            encoding="utf-8",
        )
        batch_approval = root / "batch_approval.json"
        batch_approval.write_text(
            '{"batch_id":"batch-test","scope":"%s","approved":true,"timestamp_utc":"%s"}'
            % (scope, datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")),
            encoding="utf-8",
        )
        permit_path = root / "execution_permit.json"
        issue_execution_permit(
            permit_path=permit_path,
            signing_private_key_path=self.signing_private_key,
            batch_id="batch-test",
            scope=scope,
            issued_by="test-suite",
            owner_review_ref=owner_review,
            batch_approval_ref=batch_approval,
            allowed_operations=allowed_operations,
            capabilities=capabilities,
            expires_at_utc=datetime.now(UTC) + timedelta(hours=1),
            global_freeze_path=global_freeze_path,
        )
        return load_execution_permit(permit_path)

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _signals(self, prefix: str) -> list[Signal]:
        return [
            Signal(
                f"{prefix}-1",
                ObjectType.ASSET,
                "AIX",
                "spot_breakout",
                "spot volume expansion",
                ClaimType.MEASUREMENT,
                Direction.BULLISH,
                SourceFamily.CEX,
                EvidenceLevel.E4,
                82,
                time_horizon=TimeHorizon.INTRADAY,
            ),
            Signal(
                f"{prefix}-2",
                ObjectType.ASSET,
                "AIX",
                "wallet_buy",
                "smart money buying",
                ClaimType.FLOW,
                Direction.BULLISH,
                SourceFamily.ONCHAIN,
                EvidenceLevel.E4,
                78,
                time_horizon=TimeHorizon.INTRADAY,
            ),
        ]


if __name__ == "__main__":
    unittest.main()
