"""Prepare and optionally sync a Tardis Deribit options_chain research store.

Default mode is dry-run: build a partition plan and write a local plan report
without retaining raw vendor rows. To download raw `OPTIONS.csv.gz` files, pass
both `--execute` and `--confirm-retain-raw-vendor-data`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.provider_probes.probe_tardis_deribit_options_surface import (  # noqa: E402
    _check_tardis_api_key_info,
    _dataset_url,
    _parse_iso_date,
    _resolve_tardis_key,
)


CONTRACT_VERSION = "quant_tardis_deribit_options_chain_history_store.v1"
DEFAULT_STORE_NAME = "tardis_deribit_options_chain"
DEFAULT_REPORT_DIR = ROOT / "artifacts" / "quant_research" / "factor_reports"
RAW_RETENTION_CONFIRMATION = "I_UNDERSTAND_RAW_TARDIS_OPTIONS_CHAIN_WILL_BE_RETAINED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or sync Tardis Deribit options_chain raw gzip partitions into an external research store."
    )
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--from-date", type=_parse_iso_date, required=True)
    parser.add_argument("--to-date", type=_parse_iso_date, required=True)
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help=(
            "External store root. Defaults to E:\\EnhengClawData\\market_history\\"
            "tardis_deribit_options_chain when E: exists; otherwise LOCALAPPDATA."
        ),
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent partition downloads in execute mode.")
    parser.add_argument("--summary-only", action="store_true", help="Print a compact summary instead of all partitions.")
    parser.add_argument(
        "--skip-store-manifest",
        action="store_true",
        help="Do not write the shared external-store manifest; useful for disjoint parallel segment workers.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download existing partitions in execute mode.")
    parser.add_argument("--execute", action="store_true", help="Download raw vendor partitions instead of dry-run.")
    parser.add_argument(
        "--confirm-retain-raw-vendor-data",
        default="",
        help=f"Required with --execute. Exact value: {RAW_RETENTION_CONFIRMATION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.to_date < args.from_date:
        raise SystemExit("--to-date must be >= --from-date")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be positive")

    external_root = resolve_external_root(args.external_root)
    _assert_external_root_outside_repo(external_root)
    dates = _date_range(args.from_date, args.to_date)
    report_path = args.report_dir / args.as_of / "tardis_deribit_options_chain_history_store_summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if args.execute:
        if args.confirm_retain_raw_vendor_data != RAW_RETENTION_CONFIRMATION:
            raise SystemExit(
                "--execute requires --confirm-retain-raw-vendor-data "
                f"{RAW_RETENTION_CONFIRMATION!r}"
            )
        api_key, credential_debug, credential_candidates = _resolve_tardis_key()
        api_key, auth_check = _select_accepted_tardis_key(
            api_key=api_key,
            credential_candidates=credential_candidates,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        api_key = None
        credential_debug = _dry_run_credential_debug()
        auth_check = None

    partitions = [
        _partition_plan(external_root=external_root, current_date=current_date)
        for current_date in dates
    ]
    if args.execute:
        assert api_key is not None
        _download_missing_partitions(
            api_key=api_key,
            partitions=partitions,
            timeout_seconds=args.timeout_seconds,
            force=bool(args.force),
            max_workers=int(args.max_workers),
        )
    else:
        for partition in partitions:
            partition["action"] = "skip_existing" if partition["exists"] else "dry_run_download"

    summary = _build_summary(
        as_of=args.as_of,
        external_root=external_root,
        from_date=args.from_date,
        to_date=args.to_date,
        execute=args.execute,
        force=args.force,
        partitions=partitions,
        credential_debug=credential_debug,
        auth_check=auth_check,
    )
    _write_json(report_path, summary)
    if args.execute and args.skip_store_manifest:
        summary["manifest_write"] = {"skipped": True, "success": None}
        _write_json(report_path, summary)
    elif args.execute:
        try:
            _write_store_manifest(external_root=external_root, summary=summary)
            summary["manifest_write"] = {
                "skipped": False,
                "success": True,
                "path": str(store_manifest_path(external_root=external_root)),
            }
        except Exception as exc:  # noqa: BLE001
            summary["success"] = False
            summary["manifest_write"] = {
                "skipped": False,
                "success": False,
                "path": str(store_manifest_path(external_root=external_root)),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }
        _write_json(report_path, summary)
    printable = _compact_summary(summary) if args.summary_only else summary
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0 if summary["success"] else 1


def resolve_external_root(external_root: Path | None) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    e_root = Path("E:/EnhengClawData/market_history") / DEFAULT_STORE_NAME
    if Path("E:/").exists():
        return e_root.resolve()
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / "market_history" / DEFAULT_STORE_NAME).resolve()
    return (Path.home() / "AppData" / "Local" / "EnhengClaw" / "market_history" / DEFAULT_STORE_NAME).resolve()


def _assert_external_root_outside_repo(external_root: Path) -> None:
    root = ROOT.resolve()
    try:
        external_root.resolve().relative_to(root)
    except ValueError:
        return
    raise RuntimeError(
        f"external raw vendor store must stay outside the repo; got {external_root}"
    )


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _partition_plan(*, external_root: Path, current_date: date) -> dict[str, Any]:
    path = partition_path(external_root=external_root, current_date=current_date)
    stat = path.stat() if path.exists() else None
    return {
        "date": current_date.isoformat(),
        "url": _dataset_url(current_date.isoformat()),
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": int(stat.st_size) if stat else 0,
        "last_write_time_utc": (
            datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat() if stat else None
        ),
    }


def partition_path(*, external_root: Path, current_date: date) -> Path:
    return (
        external_root
        / "raw"
        / "deribit"
        / "options_chain"
        / f"{current_date:%Y}"
        / f"{current_date:%m}"
        / f"{current_date:%d}"
        / "OPTIONS.csv.gz"
    )


def _download_partition(
    *,
    api_key: str,
    current_date: date,
    partition_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for online Tardis history sync") from exc

    url = _dataset_url(current_date.isoformat())
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept-Encoding": "identity",
        },
        stream=True,
        timeout=timeout_seconds,
    )
    if response.status_code != 200:
        excerpt = response.text[:500] if response.text else ""
        response.close()
        return {
            "action": "download_failed",
            "http_status": response.status_code,
            "body_excerpt": excerpt,
            "downloaded": False,
        }

    partition_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = partition_path.with_name(partition_path.name + ".tmp")
    sha = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                sha.update(chunk)
                size += len(chunk)
        temp_path.replace(partition_path)
    finally:
        response.close()
        if temp_path.exists():
            temp_path.unlink()
    return {
        "action": "downloaded",
        "downloaded": True,
        "http_status": response.status_code,
        "size_bytes": size,
        "sha256": sha.hexdigest(),
        "source": "tardis_dataset",
    }


def _download_missing_partitions(
    *,
    api_key: str,
    partitions: list[dict[str, Any]],
    timeout_seconds: float,
    force: bool,
    max_workers: int,
) -> None:
    targets: list[tuple[int, dict[str, Any]]] = []
    for index, partition in enumerate(partitions):
        if force or not bool(partition["exists"]):
            targets.append((index, partition))
        else:
            partition["action"] = "skip_existing"
            partition["downloaded"] = False

    if not targets:
        return

    if max_workers == 1:
        for index, partition in targets:
            partitions[index].update(
                _download_partition_for_plan(
                    api_key=api_key,
                    partition=partition,
                    timeout_seconds=timeout_seconds,
                )
            )
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _download_partition_for_plan,
                api_key=api_key,
                partition=partition,
                timeout_seconds=timeout_seconds,
            ): index
            for index, partition in targets
        }
        for future in as_completed(futures):
            partitions[futures[future]].update(future.result())


def _download_partition_for_plan(
    *,
    api_key: str,
    partition: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        current_date = date.fromisoformat(str(partition["date"]))
        return _download_partition(
            api_key=api_key,
            current_date=current_date,
            partition_path=Path(str(partition["path"])),
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "download_failed",
            "downloaded": False,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }


def _select_accepted_tardis_key(
    *,
    api_key: str | None,
    credential_candidates: list[Any],
    timeout_seconds: float,
) -> tuple[str, dict[str, object]]:
    candidates = [candidate for candidate in credential_candidates if getattr(candidate, "value", "")]
    if not candidates and api_key:
        candidates = [type("_Candidate", (), {"value": api_key, "env_var": "unknown", "scope": "unknown"})()]
    if not candidates:
        raise RuntimeError("Tardis API key not found in supported environment variables")
    checks = []
    for candidate in candidates:
        auth_check = _check_tardis_api_key_info(
            api_key=str(candidate.value),
            timeout_seconds=timeout_seconds,
        )
        sanitized = {
            "env_var": getattr(candidate, "env_var", None),
            "scope": getattr(candidate, "scope", None),
            "value_length": len(str(candidate.value)),
            "accepted": bool(auth_check.get("accepted")),
            "status_code": auth_check.get("status_code"),
        }
        checks.append(sanitized)
        if auth_check.get("accepted"):
            auth_check.update(
                {
                    "env_var": getattr(candidate, "env_var", None),
                    "scope": getattr(candidate, "scope", None),
                    "value_length": len(str(candidate.value)),
                    "candidate_checks": checks,
                }
            )
            return str(candidate.value), auth_check
    raise RuntimeError(f"No accepted Tardis API key candidate: {checks}")


def _dry_run_credential_debug() -> dict[str, object]:
    _api_key, debug, _candidates = _resolve_tardis_key()
    return _sanitize_credential_debug(debug)


def _sanitize_credential_debug(debug: dict[str, object] | None) -> dict[str, object] | None:
    if debug is None:
        return None
    sanitized = dict(debug)
    sanitized.pop("candidate_readback", None)
    return sanitized


def _build_summary(
    *,
    as_of: str,
    external_root: Path,
    from_date: date,
    to_date: date,
    execute: bool,
    force: bool,
    partitions: list[dict[str, Any]],
    credential_debug: dict[str, object] | None,
    auth_check: dict[str, object] | None,
) -> dict[str, Any]:
    downloaded = [item for item in partitions if item.get("downloaded")]
    failed = [item for item in partitions if item.get("action") == "download_failed"]
    missing_after = [item for item in partitions if not Path(str(item["path"])).exists()]
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "mode": "execute" if execute else "dry_run",
        "success": not failed and (not execute or not missing_after),
        "external_root": str(external_root),
        "raw_vendor_data_retained": bool(execute),
        "force": bool(force),
        "exchange": "deribit",
        "dataset": "options_chain",
        "date_start": from_date.isoformat(),
        "date_end": to_date.isoformat(),
        "date_count": len(partitions),
        "downloaded_count": len(downloaded),
        "failed_count": len(failed),
        "existing_or_downloaded_count": sum(1 for item in partitions if Path(str(item["path"])).exists()),
        "partition_layout": "raw/deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz",
        "manifest_path": str(store_manifest_path(external_root=external_root)),
        "credential_debug": credential_debug,
        "auth_check": _sanitize_auth_check(auth_check),
        "partitions": partitions,
    }


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: summary.get(key)
        for key in (
            "contract_version",
            "generated_at_utc",
            "as_of",
            "mode",
            "success",
            "external_root",
            "raw_vendor_data_retained",
            "force",
            "exchange",
            "dataset",
            "date_start",
            "date_end",
            "date_count",
            "downloaded_count",
            "failed_count",
            "existing_or_downloaded_count",
            "partition_layout",
            "manifest_path",
            "auth_check",
        )
    }


def _sanitize_auth_check(auth_check: dict[str, object] | None) -> dict[str, object] | None:
    if auth_check is None:
        return None
    keep = {
        "endpoint",
        "status_code",
        "accepted",
        "env_var",
        "scope",
        "value_length",
        "candidate_checks",
        "top_level_keys",
    }
    return {key: value for key, value in auth_check.items() if key in keep}


def store_manifest_path(*, external_root: Path) -> Path:
    return external_root / "manifests" / "deribit_options_chain_manifest.json"


def _write_store_manifest(*, external_root: Path, summary: dict[str, Any]) -> None:
    manifest_path = store_manifest_path(external_root=external_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "updated_at_utc": summary["generated_at_utc"],
        "external_root": summary["external_root"],
        "exchange": summary["exchange"],
        "dataset": summary["dataset"],
        "partition_layout": summary["partition_layout"],
        "last_sync_summary": {
            key: summary[key]
            for key in (
                "as_of",
                "mode",
                "success",
                "date_start",
                "date_end",
                "date_count",
                "downloaded_count",
                "failed_count",
                "existing_or_downloaded_count",
            )
        },
    }
    _write_json(manifest_path, manifest)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
