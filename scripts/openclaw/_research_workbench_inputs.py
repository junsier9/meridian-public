from __future__ import annotations

from datetime import UTC, datetime, timedelta
import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import CAP_RUNTIME_EXECUTE, TRUST_ROOT_DIR_ENV, issue_execution_permit, load_execution_permit
from scripts.openclaw._market_observer_live_inputs import (
    DEFAULT_ALLOWED_OPERATIONS,
    DEFAULT_EXPIRES_AFTER_HOURS,
    DEFAULT_ISSUED_BY,
    DEFAULT_SCOPE,
    OPENCLAW_ENV,
    describe_trust_root_source,
    ensure_signer_keypair,
    publish_allowed_signers,
    resolve_openclaw_bundle_operator_env,
    resolve_trust_root_dir,
    _temporary_env,
    _utc_now,
    _write_json,
)


DEFAULT_EXTERNAL_ROOT_NAME = "openclaw_research_workbench"
DEFAULT_BATCH_ID = "openclaw-research-workbench"
DEFAULT_CAPABILITIES = (CAP_RUNTIME_EXECUTE,)
LIVE_ENV_MODE = "unified_openclaw_baseline"
RESEARCH_REQUIRED_LANES = (
    "market_observer",
    "evidence_agent",
    "risk_signal_agent",
    "research_synthesizer",
    "research_lead",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision repeatable external research inputs for scheduled OpenClaw workbench runs.")
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help="External provisioning root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\openclaw_research_workbench.",
    )
    parser.add_argument(
        "--trust-root-dir",
        type=Path,
        default=None,
        help="Published read-only trust root. Defaults to C:\\ProgramData\\EnhengClaw\\trust.",
    )
    parser.add_argument(
        "--expires-after-hours",
        type=int,
        default=DEFAULT_EXPIRES_AFTER_HOURS,
        help="Permit lifetime in hours. Defaults to 24.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = provision_openclaw_research_inputs(
        external_root=args.external_root,
        trust_root_dir=args.trust_root_dir,
        expires_after_hours=args.expires_after_hours,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def provision_openclaw_research_inputs(
    *,
    external_root: Path | None = None,
    trust_root_dir: Path | None = None,
    expires_after_hours: int = DEFAULT_EXPIRES_AFTER_HOURS,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_root(external_root=external_root, base_env=base_env)
    resolved_trust_root = resolve_trust_root_dir(trust_root_dir=trust_root_dir, base_env=base_env)
    trust_root_meta = describe_trust_root_source(trust_root_dir=trust_root_dir)
    signer_root = resolved_root / "signer"
    permit_root = resolved_root / "permit"
    retained_root = resolved_root / "retained"
    summary_path = resolved_root / "provision_summary.json"

    signing_private_key = signer_root / "execution_signer"
    signing_public_key = signing_private_key.with_suffix(".pub")
    owner_review_path = permit_root / "owner_review.json"
    batch_approval_path = permit_root / "batch_approval.json"
    permit_path = permit_root / "execution_permit.json"
    allowed_signers_path = resolved_trust_root / "allowed_signers"

    for root in (signer_root, permit_root, retained_root):
        root.mkdir(parents=True, exist_ok=True)

    signer_created = ensure_signer_keypair(signing_private_key)
    public_key = signing_public_key.read_text(encoding="utf-8").strip()
    publish_allowed_signers(
        trust_root_dir=resolved_trust_root,
        allowed_signers_path=allowed_signers_path,
        public_key=public_key,
    )

    generated_at = _utc_now()
    owner_review_payload = {
        "status": "passed",
        "scope": DEFAULT_SCOPE,
        "generated_by": DEFAULT_ISSUED_BY,
        "generated_at_utc": generated_at,
        "workflow": "scheduled_research",
    }
    batch_approval_payload = {
        "batch_id": DEFAULT_BATCH_ID,
        "scope": DEFAULT_SCOPE,
        "approved": True,
        "timestamp_utc": generated_at,
        "generated_by": DEFAULT_ISSUED_BY,
        "workflow": "scheduled_research",
    }
    _write_json(owner_review_path, owner_review_payload)
    _write_json(batch_approval_path, batch_approval_payload)

    expires_at_utc = datetime.now(UTC) + timedelta(hours=expires_after_hours)
    issue_execution_permit(
        permit_path=permit_path,
        signing_private_key_path=signing_private_key,
        batch_id=DEFAULT_BATCH_ID,
        scope=DEFAULT_SCOPE,
        issued_by=DEFAULT_ISSUED_BY,
        owner_review_ref=owner_review_path,
        batch_approval_ref=batch_approval_path,
        allowed_operations=list(DEFAULT_ALLOWED_OPERATIONS),
        capabilities=list(DEFAULT_CAPABILITIES),
        expires_at_utc=expires_at_utc,
    )

    with _temporary_env({TRUST_ROOT_DIR_ENV: str(resolved_trust_root)}):
        loaded_permit = load_execution_permit(permit_path)

    summary = {
        "status": "success",
        "generated_at_utc": _utc_now(),
        "external_root": str(resolved_root),
        "summary_path": str(summary_path),
        "signer_root": str(signer_root),
        "signing_private_key_path": str(signing_private_key),
        "signing_public_key_path": str(signing_public_key),
        "signer_reused": not signer_created,
        "trust_root_dir": str(resolved_trust_root),
        "trust_root_mode": trust_root_meta["trust_root_mode"],
        "allowed_signers_path": str(allowed_signers_path),
        "trust_root_override_applied": trust_root_meta["trust_root_override_applied"],
        "trust_root_validation": "passed",
        "permit_root": str(permit_root),
        "permit_path": str(permit_path),
        "owner_review_path": str(owner_review_path),
        "batch_approval_path": str(batch_approval_path),
        "retained_root": str(retained_root),
        "permit_id": loaded_permit.permit_id,
        "issued_at_utc": loaded_permit.issued_at_utc.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": loaded_permit.expires_at_utc.isoformat().replace("+00:00", "Z"),
        "scope": loaded_permit.scope,
        "capabilities": list(loaded_permit.capabilities),
        "allowed_operations": list(loaded_permit.allowed_operations),
        "batch_id": loaded_permit.batch_id,
        "issued_by": loaded_permit.issued_by,
        "workflow": "scheduled_research",
        "expires_after_hours": expires_after_hours,
    }
    _write_json(summary_path, summary)
    return summary


def resolve_external_root(*, external_root: Path | None, base_env: dict[str, str] | None = None) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    env = os.environ if base_env is None else base_env
    localappdata = str(env.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()
    return (Path.home() / ".local" / "share" / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()


def resolve_openclaw_research_operator_env(base_env: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    env, metadata = resolve_openclaw_bundle_operator_env(base_env=base_env, fail_closed=False)
    missing_required = {
        lane_id: env_name
        for lane_id, env_name in metadata["missing_api_key_envs_by_lane"].items()
        if lane_id in RESEARCH_REQUIRED_LANES
    }
    if missing_required:
        missing_names = ", ".join(missing_required.values())
        raise RuntimeError(
            "scheduled research workflow requires OPENCLAW or dedicated API keys for market_observer, "
            f"evidence_agent, risk_signal_agent, research_synthesizer, and research_lead; missing: {missing_names}"
        )
    metadata = dict(metadata)
    metadata["workflow"] = "scheduled_research"
    metadata["openclaw_env_var"] = OPENCLAW_ENV
    metadata["live_env_mode"] = LIVE_ENV_MODE
    metadata["missing_api_key_envs_by_lane"] = missing_required
    return env, metadata


if __name__ == "__main__":
    raise SystemExit(main())
