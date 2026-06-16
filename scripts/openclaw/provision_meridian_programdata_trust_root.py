from __future__ import annotations

import argparse
from datetime import UTC, datetime
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

from enhengclaw.compat.naming import env_aliases, pop_env_aliases
from enhengclaw.core.execution_control import TRUST_ROOT_DIR_ENV, load_execution_permit, resolve_allowed_signers_path
from scripts.openclaw._market_observer_live_inputs import (
    publish_allowed_signers,
)


CONFIRM_BOUNDARY = "I_UNDERSTAND_THIS_DOES_NOT_UPDATE_ACCEPTED_EVIDENCE"
DEFAULT_SUMMARY_ROOT_NAME = "programdata_trust_root_proofs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or apply the disabled Meridian ProgramData trust-root provisioning proof."
    )
    parser.add_argument(
        "--target-trust-root",
        type=Path,
        default=None,
        help="Target trust root. Defaults to C:\\ProgramData\\MeridianAlpha\\trust on Windows-style hosts.",
    )
    parser.add_argument(
        "--public-key-path",
        type=Path,
        required=True,
        help="Signer public key to publish as the disabled Meridian allowed_signers source.",
    )
    parser.add_argument(
        "--permit-path",
        type=Path,
        default=None,
        help="Optional permit to validate against the new trust root after publishing.",
    )
    parser.add_argument(
        "--summary-root",
        type=Path,
        default=None,
        help="Optional proof summary root. Defaults to %%LOCALAPPDATA%%\\MeridianAlpha\\programdata_trust_root_proofs\\<timestamp>.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually publish and validate the disabled trust root. Omit for plan-only mode.",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow overwriting an existing target allowed_signers file.",
    )
    parser.add_argument(
        "--confirm-boundary",
        default="",
        help=f"Required with --apply: {CONFIRM_BOUNDARY}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = provision_meridian_programdata_trust_root(
        target_trust_root=args.target_trust_root,
        public_key_path=args.public_key_path,
        permit_path=args.permit_path,
        summary_root=args.summary_root,
        apply=args.apply,
        allow_existing=args.allow_existing,
        confirm_boundary=args.confirm_boundary,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] in {"planned", "success"} else 1


def provision_meridian_programdata_trust_root(
    *,
    target_trust_root: Path | None,
    public_key_path: Path,
    permit_path: Path | None = None,
    summary_root: Path | None = None,
    apply: bool = False,
    allow_existing: bool = False,
    confirm_boundary: str = "",
) -> dict[str, Any]:
    resolved_target = resolve_target_trust_root(target_trust_root)
    resolved_public_key = public_key_path.expanduser().resolve()
    resolved_permit = None if permit_path is None else permit_path.expanduser().resolve()
    resolved_summary_root = resolve_summary_root(summary_root)
    summary_path = resolved_summary_root / "meridian_programdata_trust_root_proof_summary.json"
    allowed_signers_path = resolved_target / "allowed_signers"
    target_exists = resolved_target.exists()
    existing_entries = _list_existing_entries(resolved_target)

    summary: dict[str, Any] = {
        "status": "planned",
        "generated_at_utc": _utc_now(),
        "window": "meridian_programdata_trust_root_disabled_proof",
        "target_trust_root": str(resolved_target),
        "allowed_signers_path": str(allowed_signers_path),
        "public_key_path": str(resolved_public_key),
        "permit_path": None if resolved_permit is None else str(resolved_permit),
        "summary_path": str(summary_path),
        "apply": apply,
        "allow_existing": allow_existing,
        "target_exists_before": target_exists,
        "target_existing_entries": existing_entries,
        "disabled_by_default": True,
        "default_trust_root_changed": False,
        "persistent_environment_changed": False,
        "scheduled_tasks_updated": False,
        "accepted_evidence_paths_updated": False,
        "project_state_updated": False,
        "copies_legacy_evidence": False,
        "rollback_boundary": "remove only this target trust root after confirming no accepted evidence or scheduled task references it",
    }

    if not apply:
        return summary
    if confirm_boundary != CONFIRM_BOUNDARY:
        summary["status"] = "failed"
        summary["error"] = f"--confirm-boundary must equal {CONFIRM_BOUNDARY}"
        return summary
    if existing_entries and not allow_existing:
        summary["status"] = "failed"
        summary["error"] = "target trust root is not empty; rerun with --allow-existing only after reviewing rollback risk"
        return summary

    public_key = _read_public_key(resolved_public_key)
    publish_allowed_signers(
        trust_root_dir=resolved_target,
        allowed_signers_path=allowed_signers_path,
        public_key=public_key,
    )
    validation = validate_disabled_trust_root(
        trust_root_dir=resolved_target,
        permit_path=resolved_permit,
    )
    summary.update(
        {
            "status": "success",
            "applied_at_utc": _utc_now(),
            "trust_root_mode": "explicit_trust_root",
            "trust_root_override_applied": True,
            "trust_root_validation": validation,
        }
    )
    _write_json(summary_path, summary)
    return summary


def resolve_target_trust_root(target_trust_root: Path | None) -> Path:
    if target_trust_root is not None:
        return target_trust_root.expanduser().resolve()
    base = Path(os.getenv("PROGRAMDATA") or (Path.home() / "AppData" / "Local"))
    return (base / "MeridianAlpha" / "trust").resolve()


def resolve_summary_root(summary_root: Path | None) -> Path:
    if summary_root is not None:
        return summary_root.expanduser().resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return (base / "MeridianAlpha" / DEFAULT_SUMMARY_ROOT_NAME / timestamp).resolve()


def validate_disabled_trust_root(*, trust_root_dir: Path, permit_path: Path | None) -> dict[str, Any]:
    saved_env = _capture_env(TRUST_ROOT_DIR_ENV, "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT")
    try:
        pop_env_aliases(os.environ, TRUST_ROOT_DIR_ENV)
        pop_env_aliases(os.environ, "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT")
        os.environ["MERIDIAN_ALPHA_TRUST_ROOT_DIR"] = str(trust_root_dir)
        allowed_signers = resolve_allowed_signers_path()
        validation: dict[str, Any] = {
            "status": "passed",
            "validated_with_env": "MERIDIAN_ALPHA_TRUST_ROOT_DIR",
            "allowed_signers_path": str(allowed_signers),
            "permit_validation": "skipped",
        }
        if permit_path is not None:
            permit = load_execution_permit(permit_path)
            validation.update(
                {
                    "permit_validation": "passed",
                    "permit_id": permit.permit_id,
                    "permit_scope": permit.scope,
                }
            )
        return validation
    finally:
        _restore_env(saved_env)


def _read_public_key(public_key_path: Path) -> str:
    if not public_key_path.exists():
        raise FileNotFoundError(f"public key does not exist: {public_key_path}")
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    if not public_key.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-")):
        raise ValueError(f"public key does not look like an OpenSSH public key: {public_key_path}")
    return public_key


def _list_existing_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return sorted(item.name for item in path.iterdir())
    except OSError as exc:
        return [f"<unable-to-list:{type(exc).__name__}>"]


def _capture_env(*names: str) -> dict[str, str | None]:
    keys = sorted({alias for name in names for alias in env_aliases(name)})
    return {key: os.environ.get(key) for key in keys}


def _restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
