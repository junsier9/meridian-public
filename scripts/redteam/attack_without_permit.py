from __future__ import annotations

from datetime import UTC, datetime, timedelta
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.execution_control import CAP_RUNTIME_EXECUTE, issue_execution_permit, load_execution_permit
from enhengclaw.core.signals import Signal
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest


def main() -> int:
    attacks = {
        "runtime_direct": attack_runtime_direct,
        "provider_direct": attack_provider_direct,
        "shadow_ingest_cli": attack_shadow_ingest_cli,
        "forged_permit_runtime": attack_forged_permit_runtime,
    }
    failures = 0
    for name, attack in attacks.items():
        try:
            attack()
        except Exception as exc:  # noqa: BLE001 - red-team probe wants the concrete block reason
            print(f"{name}: BLOCKED -> {type(exc).__name__}: {exc}")
        else:
            failures += 1
            print(f"{name}: BYPASSED")
    return 1 if failures else 0


def attack_runtime_direct() -> None:
    RuntimeOrchestrator().run_new(
        object_id="attack-runtime-direct",
        object_type=ObjectType.ASSET,
        scope="spot+perp",
        signals=[
            Signal(
                "attack-1",
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
            )
        ],
    )


def attack_provider_direct() -> None:
    OfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots").fetch(
        ProviderRequest(
            object_id="attack-provider-direct",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
    )


def attack_shadow_ingest_cli() -> None:
    artifacts_root = ROOT / "artifacts" / "attack_without_permit"
    subprocess.run(
        [
            "shadow-ingest",
            "--artifacts-root",
            str(artifacts_root),
            "--run-seconds",
            "0.1",
            "--log-level",
            "ERROR",
        ],
        check=True,
        cwd=ROOT,
    )


def attack_forged_permit_runtime() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        private_key = root / "forged_signer"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(private_key),
            ],
            check=True,
            capture_output=True,
        )
        owner_review = root / "owner_review.json"
        owner_review.write_text('{"status":"passed","scope":"spot+perp"}', encoding="utf-8")
        batch_approval = root / "batch_approval.json"
        batch_approval.write_text(
            '{"batch_id":"attack-batch","scope":"spot+perp","approved":true,"timestamp_utc":"%s"}'
            % datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            encoding="utf-8",
        )
        permit_path = root / "execution_permit.json"
        issue_execution_permit(
            permit_path=permit_path,
            signing_private_key_path=private_key,
            batch_id="attack-batch",
            scope="spot+perp",
            issued_by="red-team-local",
            owner_review_ref=owner_review,
            batch_approval_ref=batch_approval,
            allowed_operations=["runtime.*"],
            capabilities=[CAP_RUNTIME_EXECUTE],
            expires_at_utc=datetime.now(UTC) + timedelta(minutes=5),
        )
        permit = load_execution_permit(permit_path)
        RuntimeOrchestrator(execution_permit=permit).run_new(
            object_id="attack-forged-permit",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=[
                Signal(
                    "attack-forged-1",
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
                )
            ],
        )


if __name__ == "__main__":
    raise SystemExit(main())
