from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.compat.naming import getenv_compat, materialize_env_alias, pop_env_aliases
from enhengclaw.core.execution_control import (
    CAP_RUNTIME_EXECUTE,
    TRUST_ROOT_DIR_ENV,
    default_trust_root_dir,
    issue_execution_permit,
    load_execution_permit,
)
from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from scripts.verify._openclaw_continue_existing_support import (
    OPENCLAW_LANE_CONFIGS,
    api_key_env_candidates,
    required_live_env_names,
)


DEFAULT_EXTERNAL_ROOT_NAME = "openclaw_live_market_observer"
DEFAULT_BATCH_ID = "openclaw-market-observer-live"
DEFAULT_ISSUED_BY = "openclaw-operator"
DEFAULT_SCOPE = "*"
DEFAULT_ALLOWED_OPERATIONS = ("runtime.*",)
DEFAULT_CAPABILITIES = (CAP_RUNTIME_EXECUTE,)
DEFAULT_EXPIRES_AFTER_HOURS = 24
DEFAULT_TRUST_ROOT_MODE = "readonly_programdata"
EXPLICIT_TRUST_ROOT_MODE = "explicit_trust_root"

OPENCLAW_ENV = "OPENCLAW"
OPENCLAW_BASE_URL_ENV = "OPENCLAW_BASE_URL"
OPENCLAW_MODEL_NAME_ENV = "OPENCLAW_MODEL_NAME"
OPENCLAW_MODEL_TIMEOUT_SECONDS_ENV = "OPENCLAW_MODEL_TIMEOUT_SECONDS"
MODEL_BASE_URL_ENV = "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL"
MODEL_NAME_ENV = "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME"
MODEL_API_KEY_ENV = "ENHENGCLAW_MARKET_OBSERVER_API_KEY"
MODEL_TIMEOUT_ENV = "ENHENGCLAW_MARKET_OBSERVER_MODEL_TIMEOUT_SECONDS"
DEFAULT_MODEL_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL_NAME = "gpt-5.4"
DEFAULT_MODEL_TIMEOUT_SECONDS = "30"
WINDOWS_SYSTEM_SID = "*S-1-5-18"
WINDOWS_ADMINISTRATORS_SID = "*S-1-5-32-544"
LIVE_ENV_MODE = "unified_openclaw_baseline"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision repeatable external live inputs for market_observer.")
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help="External provisioning root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\openclaw_live_market_observer.",
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
    summary = provision_market_observer_live_inputs(
        external_root=args.external_root,
        trust_root_dir=args.trust_root_dir,
        expires_after_hours=args.expires_after_hours,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def provision_market_observer_live_inputs(
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
    }
    batch_approval_payload = {
        "batch_id": DEFAULT_BATCH_ID,
        "scope": DEFAULT_SCOPE,
        "approved": True,
        "timestamp_utc": generated_at,
        "generated_by": DEFAULT_ISSUED_BY,
    }
    _write_json(owner_review_path, owner_review_payload)
    _write_json(batch_approval_path, batch_approval_payload)

    expires_at_utc = datetime.now(UTC) + timedelta(hours=expires_after_hours)
    _ensure_writable(permit_root)
    _ensure_writable(permit_path)
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

    trust_root_validation = "failed"
    with _temporary_env({TRUST_ROOT_DIR_ENV: str(resolved_trust_root)}):
        loaded_permit = load_execution_permit(permit_path)
    trust_root_validation = "passed"

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
        "trust_root_validation": trust_root_validation,
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
        "compatibility_overrides": {},
        "expires_after_hours": expires_after_hours,
    }
    summary = with_evidence_metadata(
        summary,
        evidence_family="openclaw_operator_provisioning",
        contract_version="openclaw_operator_provisioning.v1",
        repo_root=ROOT,
    )
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


def resolve_trust_root_dir(*, trust_root_dir: Path | None, base_env: dict[str, str] | None = None) -> Path:
    if trust_root_dir is not None:
        return trust_root_dir.expanduser().resolve()
    if base_env is None:
        return default_trust_root_dir()
    programdata = str(base_env.get("PROGRAMDATA", "")).strip()
    if programdata:
        base = Path(programdata)
    else:
        base = Path.home() / "AppData" / "Local"
    return (base / "EnhengClaw" / "trust").resolve()


def describe_trust_root_source(*, trust_root_dir: Path | None) -> dict[str, bool | str]:
    if trust_root_dir is not None:
        return {
            "trust_root_mode": EXPLICIT_TRUST_ROOT_MODE,
            "trust_root_override_applied": True,
        }
    return {
        "trust_root_mode": DEFAULT_TRUST_ROOT_MODE,
        "trust_root_override_applied": False,
    }


def _market_observer_live_env_names() -> tuple[str, str, str]:
    return (MODEL_BASE_URL_ENV, MODEL_NAME_ENV, MODEL_API_KEY_ENV)


def openclaw_bundle_live_env_specs() -> dict[str, tuple[str, str, str]]:
    specs: dict[str, tuple[str, str, str]] = {
        "market_observer": _market_observer_live_env_names(),
    }
    for config in OPENCLAW_LANE_CONFIGS:
        specs[config.lane_id] = required_live_env_names(config)
    return specs


def _openclaw_bundle_api_key_env_candidates() -> dict[str, tuple[str, ...]]:
    candidates: dict[str, tuple[str, ...]] = {
        "market_observer": (MODEL_API_KEY_ENV,),
    }
    for config in OPENCLAW_LANE_CONFIGS:
        candidates[config.lane_id] = api_key_env_candidates(config)
    return candidates


def resolve_openclaw_bundle_operator_env(
    base_env: dict[str, str] | None = None,
    *,
    fail_closed: bool = True,
) -> tuple[dict[str, str], dict[str, Any]]:
    env = dict(os.environ if base_env is None else base_env)
    openclaw_key = str(env.get(OPENCLAW_ENV, "")).strip()
    shared_base_url = str(env.get(OPENCLAW_BASE_URL_ENV, "")).strip() or DEFAULT_MODEL_BASE_URL
    shared_model_name = str(env.get(OPENCLAW_MODEL_NAME_ENV, "")).strip() or DEFAULT_MODEL_NAME
    shared_timeout_seconds = str(env.get(OPENCLAW_MODEL_TIMEOUT_SECONDS_ENV, "")).strip() or DEFAULT_MODEL_TIMEOUT_SECONDS
    mapping_used_by_lane: dict[str, bool] = {}
    dedicated_env_preserved_by_lane: dict[str, bool] = {}
    defaulted_base_url_by_lane: dict[str, bool] = {}
    defaulted_model_name_by_lane: dict[str, bool] = {}
    defaulted_timeout_by_lane: dict[str, bool] = {}
    missing_api_key_envs_by_lane: dict[str, str] = {}
    api_key_candidates_by_lane = _openclaw_bundle_api_key_env_candidates()
    for lane_id, (base_url_name, model_name_name, api_key_name) in openclaw_bundle_live_env_specs().items():
        timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
        base_url_value = str(getenv_compat(base_url_name, "", env=env) or "").strip()
        model_name_value = str(getenv_compat(model_name_name, "", env=env) or "").strip()
        api_key_value = ""
        for candidate_name in api_key_candidates_by_lane.get(lane_id, (api_key_name,)):
            api_key_value = str(getenv_compat(candidate_name, "", env=env) or "").strip()
            if api_key_value:
                break
        timeout_value = str(getenv_compat(timeout_name, "", env=env) or "").strip()
        has_base_url = bool(base_url_value)
        has_model_name = bool(model_name_value)
        has_api_key = bool(api_key_value)
        has_timeout = bool(timeout_value)
        dedicated_env_preserved_by_lane[lane_id] = has_base_url or has_model_name or has_api_key
        if has_base_url:
            materialize_env_alias(env, base_url_name, base_url_value)
            defaulted_base_url_by_lane[lane_id] = False
        else:
            materialize_env_alias(env, base_url_name, shared_base_url)
            defaulted_base_url_by_lane[lane_id] = True
        if has_model_name:
            materialize_env_alias(env, model_name_name, model_name_value)
            defaulted_model_name_by_lane[lane_id] = False
        else:
            materialize_env_alias(env, model_name_name, shared_model_name)
            defaulted_model_name_by_lane[lane_id] = True
        if has_timeout:
            materialize_env_alias(env, timeout_name, timeout_value)
            defaulted_timeout_by_lane[lane_id] = False
        else:
            materialize_env_alias(env, timeout_name, shared_timeout_seconds)
            defaulted_timeout_by_lane[lane_id] = True
        if has_api_key:
            materialize_env_alias(env, api_key_name, api_key_value)
            mapping_used_by_lane[lane_id] = False
            continue
        if openclaw_key:
            materialize_env_alias(env, api_key_name, openclaw_key)
            mapping_used_by_lane[lane_id] = True
            continue
        mapping_used_by_lane[lane_id] = False
        missing_api_key_envs_by_lane[lane_id] = api_key_name
    pop_env_aliases(env, "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT")
    if fail_closed and missing_api_key_envs_by_lane:
        missing_names = ", ".join(missing_api_key_envs_by_lane.values())
        raise RuntimeError(
            "operator workflow requires OPENCLAW or dedicated API keys for all live lanes; missing: "
            f"{missing_names}"
        )
    metadata = {
        "live_env_mode": LIVE_ENV_MODE,
        "openclaw_mapping_used": any(mapping_used_by_lane.values()),
        "openclaw_mapping_used_by_lane": mapping_used_by_lane,
        "dedicated_env_preserved_by_lane": dedicated_env_preserved_by_lane,
        "defaulted_base_url_by_lane": defaulted_base_url_by_lane,
        "defaulted_model_name_by_lane": defaulted_model_name_by_lane,
        "defaulted_timeout_by_lane": defaulted_timeout_by_lane,
        "missing_api_key_envs_by_lane": missing_api_key_envs_by_lane,
        "model_base_url": env[MODEL_BASE_URL_ENV],
        "model_name": env[MODEL_NAME_ENV],
        "model_timeout_seconds": env[MODEL_TIMEOUT_ENV],
        "shared_openclaw_base_url": shared_base_url,
        "shared_openclaw_model_name": shared_model_name,
        "shared_openclaw_model_timeout_seconds": shared_timeout_seconds,
        "trust_root_override_applied": False,
    }
    return env, metadata


def resolve_market_observer_operator_env(base_env: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    return resolve_openclaw_bundle_operator_env(base_env=base_env, fail_closed=True)


def ensure_signer_keypair(signing_private_key: Path) -> bool:
    signing_private_key.parent.mkdir(parents=True, exist_ok=True)
    public_key_path = signing_private_key.with_suffix(".pub")
    if signing_private_key.exists() and public_key_path.exists():
        return False
    if signing_private_key.exists() and not public_key_path.exists():
        completed = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(signing_private_key)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"failed to derive signer public key: {_process_detail(completed)}")
        public_key_path.write_text(completed.stdout.strip() + "\n", encoding="utf-8")
        return False
    completed = subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-f",
            str(signing_private_key),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to create signer keypair: {_process_detail(completed)}")
    return True


def publish_allowed_signers(
    *,
    trust_root_dir: Path,
    allowed_signers_path: Path,
    public_key: str,
) -> None:
    trust_root_dir.mkdir(parents=True, exist_ok=True)
    unlock_trust_root_for_publication(trust_root_dir, allowed_signers_path)
    temp_path = allowed_signers_path.with_name(f"{allowed_signers_path.name}.tmp")
    try:
        temp_path.write_text(f"execution-permit {public_key}\n", encoding="utf-8")
        os.replace(temp_path, allowed_signers_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    lock_trust_root_readonly(trust_root_dir, allowed_signers_path)


def unlock_trust_root_for_publication(trust_root_dir: Path, allowed_signers_path: Path) -> None:
    trust_root_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        identity = _require_windows_identity()
        _run_windows_acl(["icacls", str(trust_root_dir), "/remove:d", identity])
        _run_windows_acl(["icacls", str(trust_root_dir), "/grant:r", f"{identity}:(OI)(CI)(F)"])
        subprocess.run(["attrib", "-R", str(trust_root_dir)], check=False, capture_output=True, text=True)
        if allowed_signers_path.exists():
            _run_windows_acl(["icacls", str(allowed_signers_path), "/remove:d", identity])
            _run_windows_acl(["icacls", str(allowed_signers_path), "/grant:r", f"{identity}:(F)"])
            subprocess.run(["attrib", "-R", str(allowed_signers_path)], check=False, capture_output=True, text=True)
        return
    os.chmod(trust_root_dir, 0o755)
    if allowed_signers_path.exists():
        os.chmod(allowed_signers_path, 0o644)


def lock_trust_root_readonly(trust_root_dir: Path, allowed_signers_path: Path) -> None:
    if os.name == "nt":
        identity = _require_windows_identity()
        _run_windows_acl(["icacls", str(trust_root_dir), "/inheritance:r"])
        _run_windows_acl(
            [
                "icacls",
                str(trust_root_dir),
                "/grant:r",
                f"{WINDOWS_SYSTEM_SID}:(OI)(CI)(F)",
                f"{WINDOWS_ADMINISTRATORS_SID}:(OI)(CI)(F)",
                f"{identity}:(RX)",
            ]
        )
        _run_windows_acl(["icacls", str(trust_root_dir), "/deny", f"{identity}:(W)"])
        _run_windows_acl(["icacls", str(allowed_signers_path), "/inheritance:r"])
        _run_windows_acl(
            [
                "icacls",
                str(allowed_signers_path),
                "/grant:r",
                f"{WINDOWS_SYSTEM_SID}:(F)",
                f"{WINDOWS_ADMINISTRATORS_SID}:(F)",
                f"{identity}:(R)",
            ]
        )
        subprocess.run(["attrib", "+R", str(allowed_signers_path)], check=False, capture_output=True, text=True)
        subprocess.run(["attrib", "+R", str(trust_root_dir)], check=False, capture_output=True, text=True)
        return
    os.chmod(allowed_signers_path, 0o444)
    os.chmod(trust_root_dir, 0o555)


@contextmanager
def _temporary_env(values: dict[str, str]) -> Any:
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_writable(path.parent)
    _ensure_writable(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _ensure_writable(path: Path) -> None:
    if not path.exists():
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["attrib", "-R", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            identity = _current_windows_identity()
            if identity is not None:
                subprocess.run(
                    ["icacls", str(path), "/remove:d", identity],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["icacls", str(path), "/grant:r", f"{identity}:(F)"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        else:
            os.chmod(path, 0o666 if path.is_file() else 0o777)
    except OSError:
        return


def _run_windows_acl(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"windows acl command failed: {command!r}: {_process_detail(completed)}")


def _require_windows_identity() -> str:
    identity = _current_windows_identity()
    if identity is None:
        raise RuntimeError("unable to resolve current Windows identity for trust-root hardening")
    return identity


def _process_detail(result: subprocess.CompletedProcess[str]) -> str:
    stderr = (result.stderr or "").strip()
    if stderr:
        return stderr
    stdout = (result.stdout or "").strip()
    if stdout:
        return stdout
    return f"exit code {result.returncode}"


def _current_windows_identity() -> str | None:
    if os.name != "nt":
        return None
    completed = subprocess.run(
        ["whoami"],
        check=False,
        capture_output=True,
        text=True,
    )
    identity = (completed.stdout or "").strip()
    return identity or None


if __name__ == "__main__":
    raise SystemExit(main())
