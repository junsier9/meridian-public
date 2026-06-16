from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import (
    ALLOW_WRITABLE_TRUST_ROOT_ENV,
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
    CAP_PROVIDER_SELECT_MANUAL_OVERRIDE,
    CAP_PROVIDER_SELECT_RETIRED_OVERRIDE,
    CAP_RUNTIME_EXECUTE,
    LEASE_REGISTRY_PATH_ENV,
    TRUST_ROOT_DIR_ENV,
    bind_execution_context,
    issue_execution_permit,
    load_execution_permit,
)
from enhengclaw.core.session import RUNTIME_SESSION_ROOT_ENV
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import (
    MODE_DEFAULT,
    MODE_INCLUDE_SHADOW,
    MODE_MANUAL_OVERRIDE,
    ProviderRuntimeBinding,
    ProviderSelectionGateway,
)
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator


class ProviderSelectionGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)
        trust_root = root / "trust-root"
        trust_root.mkdir(parents=True, exist_ok=True)
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
        (trust_root / "allowed_signers").write_text("execution-permit %s\n" % public_key, encoding="utf-8")
        self._saved_env = {
            TRUST_ROOT_DIR_ENV: os.getenv(TRUST_ROOT_DIR_ENV),
            ALLOW_WRITABLE_TRUST_ROOT_ENV: os.getenv(ALLOW_WRITABLE_TRUST_ROOT_ENV),
            LEASE_REGISTRY_PATH_ENV: os.getenv(LEASE_REGISTRY_PATH_ENV),
            RUNTIME_SESSION_ROOT_ENV: os.getenv(RUNTIME_SESSION_ROOT_ENV),
        }
        os.environ[TRUST_ROOT_DIR_ENV] = str(trust_root)
        os.environ[ALLOW_WRITABLE_TRUST_ROOT_ENV] = "1"
        os.environ[LEASE_REGISTRY_PATH_ENV] = str(root / "execution-leases.sqlite3")
        os.environ[RUNTIME_SESSION_ROOT_ENV] = str(root / "runtime-sessions")
        self.addCleanup(self._restore_env)
        self.gateway = ProviderSelectionGateway()
        self.portfolio_report = ProviderPortfolioPolicy().evaluate_all(
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
                        scenario_count=8,
                        notes=["green"],
                    ),
                ),
                ProviderPortfolioInput(
                    provider_name="real_onchain_provider_shadow",
                    provider_type="onchain",
                    current_status=STATUS_SHADOW_ONLY,
                    contribution_ledger=None,
                    promotion_report=None,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        status="warning",
                        finding_count=1,
                        error_count=0,
                        warning_count=1,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        passed=True,
                        scenario_count=5,
                        notes=["shadow"],
                    ),
                ),
            ]
        )
        self.retired_report = ProviderPortfolioPolicy().evaluate_all(
            [
                ProviderPortfolioInput(
                    provider_name="real_onchain_provider_shadow",
                    provider_type="onchain",
                    current_status=STATUS_RETIRED,
                    contribution_ledger=None,
                    promotion_report=None,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        status="error",
                        finding_count=1,
                        error_count=1,
                        warning_count=0,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        passed=False,
                        scenario_count=5,
                        notes=["retired"],
                    ),
                )
            ]
        )
        self.bindings = [
            ProviderRuntimeBinding(provider_name="binance-public-cex", provider_type="cex", adapter=object()),
            ProviderRuntimeBinding(provider_name="real_onchain_provider_shadow", provider_type="onchain", adapter=object()),
        ]

    def test_default_selection_uses_active_provider_only(self) -> None:
        selection = self.gateway.select(
            portfolio_report=self.portfolio_report,
            bindings=self.bindings,
            mode=MODE_DEFAULT,
        )
        self.assertEqual(selection.allowed_provider_names, ["binance-public-cex"])
        self.assertEqual(selection.rejected_provider_names, ["real_onchain_provider_shadow"])

    def test_include_shadow_requires_capability(self) -> None:
        permit = self._issue_permit(
            root=Path(self.tempdir.name) / "include-shadow",
            scope="spot+perp",
            capabilities=[
                CAP_PROVIDER_FETCH,
                CAP_RUNTIME_EXECUTE,
                CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
            ],
            allowed_operations=["runtime.*", "provider.*"],
        )
        with bind_execution_context(
            permit,
            operation="runtime.tests.provider_selection.include_shadow",
            requested_scope="spot+perp",
        ):
            selection = self.gateway.select(
                portfolio_report=self.portfolio_report,
                bindings=self.bindings,
                mode=MODE_INCLUDE_SHADOW,
            )
        self.assertCountEqual(
            selection.allowed_provider_names,
            ["binance-public-cex", "real_onchain_provider_shadow"],
        )

    def test_retired_provider_requires_both_override_capabilities(self) -> None:
        manual_only = self._issue_permit(
            root=Path(self.tempdir.name) / "manual-only",
            scope="spot+perp",
            capabilities=[
                CAP_PROVIDER_FETCH,
                CAP_RUNTIME_EXECUTE,
                CAP_PROVIDER_SELECT_MANUAL_OVERRIDE,
            ],
            allowed_operations=["runtime.*", "provider.*"],
        )
        with bind_execution_context(
            manual_only,
            operation="runtime.tests.provider_selection.manual_only",
            requested_scope="spot+perp",
        ):
            blocked = self.gateway.select(
                portfolio_report=self.retired_report,
                bindings=[self.bindings[1]],
                mode=MODE_MANUAL_OVERRIDE,
                manual_allowlist=["real_onchain_provider_shadow"],
            )
        self.assertEqual(blocked.allowed_provider_names, [])
        self.assertEqual(blocked.rejected_provider_names, ["real_onchain_provider_shadow"])

        retired_override = self._issue_permit(
            root=Path(self.tempdir.name) / "retired-override",
            scope="spot+perp",
            capabilities=[
                CAP_PROVIDER_FETCH,
                CAP_RUNTIME_EXECUTE,
                CAP_PROVIDER_SELECT_MANUAL_OVERRIDE,
                CAP_PROVIDER_SELECT_RETIRED_OVERRIDE,
            ],
            allowed_operations=["runtime.*", "provider.*"],
        )
        with bind_execution_context(
            retired_override,
            operation="runtime.tests.provider_selection.retired_override",
            requested_scope="spot+perp",
        ):
            allowed = self.gateway.select(
                portfolio_report=self.retired_report,
                bindings=[self.bindings[1]],
                mode=MODE_MANUAL_OVERRIDE,
                manual_allowlist=["real_onchain_provider_shadow"],
            )
        self.assertEqual(allowed.allowed_provider_names, ["real_onchain_provider_shadow"])

    def test_legacy_provider_binding_runtime_entry_is_controller_blocked(self) -> None:
        permit = self._issue_permit(
            root=Path(self.tempdir.name) / "legacy-entry",
            scope="spot+perp",
            capabilities=[CAP_PROVIDER_FETCH, CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*", "provider.*"],
        )
        with self.assertRaises(RuntimeBoundaryError):
            RuntimeOrchestrator(execution_permit=permit).run_new_from_provider_bindings(
                object_id="legacy-provider-entry",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                portfolio_report=self.portfolio_report,
                provider_bindings=self.bindings,
                selection_mode=MODE_DEFAULT,
            )

    def _issue_permit(
        self,
        *,
        root: Path,
        scope: str,
        capabilities: list[str],
        allowed_operations: list[str],
    ):
        root.mkdir(parents=True, exist_ok=True)
        owner_review = root / "owner_review.json"
        owner_review.write_text('{"status":"passed","scope":"%s"}' % scope, encoding="utf-8")
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
        )
        return load_execution_permit(permit_path)

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
