#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_GENESIS_STATUSES = {"mainnet_position_genesis_snapshot", "position_genesis_snapshot"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - remote artifact parser
        return {"__read_error__": f"{type(exc).__name__}:{exc}"}


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fnum(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def all_true(checks: dict[str, bool]) -> bool:
    return all(bool(value) for value in checks.values())


def int_field(payload: dict[str, Any], key: str, *, default: int = -1) -> int:
    try:
        return int(payload[key])
    except Exception:
        return default


class MeridianPositionReferenceApply:
    def __init__(self, args: argparse.Namespace) -> None:
        self.label = str(args.label)
        self.meridian_root = Path(args.meridian_root)
        self.meridian_repo = self.meridian_root / "repo"
        self.meridian_venv = self.meridian_root / "venv"
        self.meridian_python = self.meridian_venv / "bin/python"
        self.meridian_wrapper = self.meridian_root / "bin/with-live-env"
        self.meridian_config = Path(args.meridian_config)
        self.meridian_parent = self.meridian_repo / (
            "artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate"
        )
        self.legacy_parent = Path(args.legacy_parent)
        self.expected_legacy_ref = Path(args.expected_legacy_ref)
        self.inventory_proof_root = Path(args.inventory_proof_root)
        self.proof_root = self.meridian_root / "proof_artifacts/meridian_position_reference_fix_window" / self.label
        self.ref_name = self.label.replace("-meridian-equivalent-genesis-apply", "-meridian-equivalent-genesis-snapshot")
        self.reference_dir = self.meridian_parent / "position_reference" / self.ref_name
        self.approval_text = str(args.approval_text)
        self.related_units = [
            "enhengclaw-mainnet-supervisor-live.service",
            "enhengclaw-mainnet-supervisor-live.timer",
            "enhengclaw-mainnet-health-monitor.service",
            "enhengclaw-mainnet-health-monitor.timer",
            "meridian-alpha-mainnet-supervisor-live.service",
            "meridian-alpha-mainnet-supervisor-live.timer",
            "meridian-alpha-mainnet-health-monitor.service",
            "meridian-alpha-mainnet-health-monitor.timer",
        ]

    def run_capture(self, name: str, command: list[str], *, cwd: Path | None = None) -> int:
        stdout = self.proof_root / f"{name}.stdout.txt"
        stderr = self.proof_root / f"{name}.stderr.txt"
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            completed = subprocess.run(command, cwd=str(cwd or self.meridian_repo), text=True, stdout=out, stderr=err)
        (self.proof_root / f"{name}.exit_code.txt").write_text(str(completed.returncode), encoding="utf-8")
        return int(completed.returncode)

    def system_snapshot(self, name: str) -> dict[str, Any]:
        timers_path = self.proof_root / f"{name}_systemd_timers.txt"
        units_path = self.proof_root / f"{name}_unit_states.txt"
        with timers_path.open("w", encoding="utf-8") as out:
            subprocess.run(
                ["systemctl", "list-timers", "--all", "enhengclaw-mainnet*", "meridian-alpha-mainnet*"],
                text=True,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        states: dict[str, dict[str, str]] = {}
        with units_path.open("w", encoding="utf-8") as out:
            for unit in self.related_units:
                out.write(f"### {unit}\n")
                completed = subprocess.run(
                    [
                        "systemctl",
                        "show",
                        unit,
                        "-p",
                        "LoadState",
                        "-p",
                        "ActiveState",
                        "-p",
                        "SubState",
                        "-p",
                        "UnitFileState",
                        "-p",
                        "FragmentPath",
                        "--no-pager",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                out.write(completed.stdout)
                state: dict[str, str] = {}
                for line in completed.stdout.splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        state[key] = value
                states[unit] = state
        timer_text = timers_path.read_text(encoding="utf-8", errors="replace")
        return {
            "timers_path": str(timers_path),
            "unit_states_path": str(units_path),
            "timers_zero": "0 timers listed" in timer_text,
            "active_related_units": [unit for unit, state in states.items() if state.get("ActiveState") == "active"],
            "enabled_related_units": [unit for unit, state in states.items() if state.get("UnitFileState") == "enabled"],
            "states": states,
        }

    def csv_positions(self, path: Path) -> dict[str, float]:
        expected: dict[str, float] = {}
        if not path.exists():
            return expected
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = str(row.get("symbol") or "").upper().strip()
                if not symbol:
                    continue
                amount = row.get("expected_position_amt") or row.get("positionAmt") or row.get("position_amt") or 0
                expected[symbol] = fnum(amount)
        return expected

    def json_positions(self, path: Path) -> dict[str, float]:
        expected: dict[str, float] = {}
        if not path.exists():
            return expected
        payload = read_json(path)
        for row in list(payload.get("positions") or payload.get("open_positions_redacted") or []):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            amount = row.get("expected_position_amt") or row.get("positionAmt") or row.get("position_amt") or 0
            expected[symbol] = fnum(amount)
        return expected

    def single_candidate(self, path: Path) -> dict[str, Any]:
        summary = read_json(path / "run_summary.json") if (path / "run_summary.json").exists() else {}
        expected: dict[str, float] = {}
        if (path / "fills.csv").exists():
            with (path / "fills.csv").open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol") or "").upper().strip()
                    if not symbol:
                        continue
                    quantity = fnum(row.get("quantity"))
                    side = str(row.get("side") or "").upper()
                    expected[symbol] = expected.get(symbol, 0.0) + (quantity if side == "BUY" else -quantity)
        blockers: list[str] = []
        if summary.get("status") != "mainnet_single_run_orders_submitted":
            blockers.append(f"invalid_summary_status:{summary.get('status') or 'missing'}")
        if not expected:
            blockers.append("expected_positions_empty")
        if not (path / "target_positions.csv").exists():
            blockers.append("target_positions_missing")
        return {
            "name": path.name,
            "path": str(path),
            "kind": "mainnet_single_run",
            "valid": not blockers,
            "blockers": blockers,
            "expected_positions": dict(sorted(expected.items())),
        }

    def delta_candidate(self, path: Path) -> dict[str, Any]:
        summary = read_json(path / "run_summary.json") if (path / "run_summary.json").exists() else {}
        reconciliation = read_json(path / "reconciliation.json") if (path / "reconciliation.json").exists() else {}
        expected = {str(key).upper(): fnum(value) for key, value in dict(reconciliation.get("expected_positions") or {}).items()}
        source = "reconciliation.expected_positions"
        if not expected:
            account_after = read_json(path / "account_after.json") if (path / "account_after.json").exists() else {}
            for row in list(account_after.get("open_positions_redacted") or []):
                if isinstance(row, dict) and row.get("symbol"):
                    expected[str(row["symbol"]).upper()] = fnum(row.get("positionAmt"))
            if expected:
                source = "account_after.open_positions_redacted"
        blockers: list[str] = []
        if summary.get("status") != "mainnet_delta_orders_submitted":
            blockers.append(f"invalid_summary_status:{summary.get('status') or 'missing'}")
        if summary.get("reconciliation_status") != "reconciled":
            blockers.append(f"invalid_summary_reconciliation_status:{summary.get('reconciliation_status') or 'missing'}")
        if reconciliation.get("status") != "reconciled":
            blockers.append(f"invalid_reconciliation_status:{reconciliation.get('status') or 'missing'}")
        if not expected:
            blockers.append("expected_positions_empty")
        return {
            "name": path.name,
            "path": str(path),
            "kind": "mainnet_delta_execution",
            "valid": not blockers,
            "blockers": blockers,
            "expected_positions": dict(sorted(expected.items())),
            "position_source": source,
            "files": {
                "run_summary.json": sha256(path / "run_summary.json"),
                "reconciliation.json": sha256(path / "reconciliation.json"),
                "account_after.json": sha256(path / "account_after.json"),
            },
        }

    def genesis_candidate(self, path: Path) -> dict[str, Any]:
        summary = read_json(path / "run_summary.json") if (path / "run_summary.json").exists() else {}
        expected = self.csv_positions(path / "reference_positions.csv") or self.json_positions(path / "genesis_snapshot.json")
        blockers: list[str] = []
        if summary.get("status") not in VALID_GENESIS_STATUSES:
            blockers.append(f"invalid_status:{summary.get('status') or 'missing'}")
        if not expected:
            blockers.append("expected_positions_empty")
        return {
            "name": path.name,
            "path": str(path),
            "kind": "genesis_snapshot",
            "valid": not blockers,
            "blockers": blockers,
            "expected_positions": dict(sorted(expected.items())),
        }

    def resolve_reference(self, parent: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        candidates: list[dict[str, Any]] = []
        all_items: list[dict[str, Any]] = []
        if parent.exists():
            for child in parent.iterdir():
                if child.is_dir() and child.name.endswith("-mainnet-single-run"):
                    item = self.single_candidate(child)
                    all_items.append(item)
                    if item["valid"]:
                        candidates.append(item)
        delta_root = parent / "mainnet_delta_execution"
        if delta_root.exists():
            for child in delta_root.iterdir():
                if child.is_dir() and child.name.endswith("-mainnet-delta-execution"):
                    item = self.delta_candidate(child)
                    all_items.append(item)
                    if item["valid"]:
                        candidates.append(item)
        genesis_root = parent / "position_reference"
        if genesis_root.exists():
            for child in genesis_root.iterdir():
                if child.is_dir() and child.name.endswith("-genesis-snapshot"):
                    item = self.genesis_candidate(child)
                    all_items.append(item)
                    if item["valid"]:
                        candidates.append(item)
        selected = sorted(candidates, key=lambda item: item["name"])[-1] if candidates else None
        return selected, all_items

    def monitor_cmd(self, extra: list[str]) -> list[str]:
        return [
            str(self.meridian_wrapper),
            "/usr/bin/env",
            f"PYTHONPATH={self.meridian_repo / 'src'}",
            "PYTHONNOUSERSITE=1",
            f"VIRTUAL_ENV={self.meridian_venv}",
            f"PATH={self.meridian_venv / 'bin'}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            str(self.meridian_python),
            str(self.meridian_repo / "scripts/live_trading/run_hv_balanced_mainnet_position_monitor.py"),
            "--config",
            str(self.meridian_config),
            *extra,
        ]

    def parse_monitor_stdout(self, name: str) -> dict[str, Any]:
        stdout = self.proof_root / f"{name}.stdout.txt"
        try:
            payload = json.loads(stdout.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {"__parse_error__": f"{type(exc).__name__}:{exc}", "stdout_path": str(stdout)}
        write_json(self.proof_root / f"{name}.summary.json", payload)
        return payload

    def monitor_pass_checks(self, name: str, summary: dict[str, Any], *, expected_reference: Path) -> dict[str, bool]:
        checks = {
            "status_passed": summary.get("status") == "passed_live_position_monitor",
            "blockers_empty": list(summary.get("blockers") or []) == [],
            "read_only_true": summary.get("read_only") is True,
            "open_order_count_zero": int_field(summary, "open_order_count") == 0,
            "open_position_count_11": int_field(summary, "open_position_count") == 11,
            "orders_submitted_zero": int_field(summary, "orders_submitted") == 0,
            "orders_canceled_zero": int_field(summary, "orders_canceled") == 0,
            "account_settings_changed_zero": int_field(summary, "account_settings_changed") == 0,
            "reference_run_matches_expected": str(Path(str(summary.get("reference_run") or "")).resolve())
            == str(expected_reference.resolve()),
        }
        write_json(self.proof_root / f"{name}.validation.json", {"checks": checks, "summary": summary})
        return checks

    def write_reference(self, selected_legacy: dict[str, Any], pre_summary: dict[str, Any]) -> None:
        expected_positions = dict(sorted(selected_legacy.get("expected_positions", {}).items()))
        self.reference_dir.mkdir(parents=True, exist_ok=False)
        rows = [{"symbol": symbol, "expected_position_amt": amount} for symbol, amount in expected_positions.items()]
        with (self.reference_dir / "reference_positions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "expected_position_amt"])
            writer.writeheader()
            writer.writerows(rows)
        genesis_snapshot = {
            "status": "mainnet_position_genesis_snapshot",
            "created_utc": utc_now(),
            "positions": rows,
            "position_count": len(rows),
            "source": {
                "kind": selected_legacy.get("kind"),
                "reference_run": selected_legacy.get("path"),
                "files": selected_legacy.get("files"),
                "read_only_inventory_proof_root": str(self.inventory_proof_root),
                "precheck_position_monitor_summary": str(self.proof_root / "precheck_legacy_reference_monitor.summary.json"),
            },
            "mutation_boundary": {
                "timer_enable_start_attempted": False,
                "service_start_attempted": False,
                "order_or_cancel_attempted": False,
                "accepted_evidence_update_attempted": False,
            },
        }
        write_json(self.reference_dir / "genesis_snapshot.json", genesis_snapshot)
        write_json(
            self.reference_dir / "run_summary.json",
            {
                "status": "mainnet_position_genesis_snapshot",
                "run_id": self.ref_name,
                "created_utc": utc_now(),
                "artifact_root": str(self.reference_dir),
                "position_count": len(rows),
                "source_reference_run": selected_legacy.get("path"),
                "source_reference_kind": selected_legacy.get("kind"),
                "source_file_hashes": selected_legacy.get("files"),
                "read_only_inventory_proof_root": str(self.inventory_proof_root),
                "fix_window_proof_root": str(self.proof_root),
                "precheck_position_monitor_artifact": pre_summary.get("artifact_root"),
                "orders_submitted": 0,
                "orders_canceled": 0,
                "order_test_calls": 0,
                "timer_enable_start_attempted": False,
                "service_start_attempted": False,
                "accepted_evidence_update_attempted": False,
            },
        )
        write_json(
            self.reference_dir / "provenance.json",
            {
                "status": "meridian_equivalent_genesis_reference_created",
                "created_utc": utc_now(),
                "approval_text": self.approval_text,
                "reference_dir": str(self.reference_dir),
                "source_reference": selected_legacy,
                "read_only_inventory_proof_root": str(self.inventory_proof_root),
                "fix_window_proof_root": str(self.proof_root),
                "design_review_summary": str(self.proof_root / "design_review_summary.json"),
                "precheck_legacy_reference_monitor_summary": str(
                    self.proof_root / "precheck_legacy_reference_monitor.summary.json"
                ),
            },
        )
        manifest_lines = []
        for path in sorted(p for p in self.reference_dir.iterdir() if p.is_file() and p.name != "manifest.sha256"):
            manifest_lines.append(f"{sha256(path)}  {path.name}")
        (self.reference_dir / "manifest.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
        write_json(
            self.proof_root / "reference_generation_summary.json",
            {
                "reference_created": True,
                "reference_dir": str(self.reference_dir),
                "position_count": len(rows),
                "positions": expected_positions,
                "manifest_sha256": sha256(self.reference_dir / "manifest.sha256"),
            },
        )

    def run(self) -> int:
        self.proof_root.mkdir(parents=True, exist_ok=True)
        write_json(
            self.proof_root / "window_metadata.json",
            {
                "status": "started",
                "label": self.label,
                "created_utc": utc_now(),
                "host": subprocess.run(["hostname"], text=True, stdout=subprocess.PIPE).stdout.strip(),
                "proof_root": str(self.proof_root),
                "approval_text": self.approval_text,
                "scope": "operator-approved position-reference apply only",
                "non_goals": [
                    "no timer handoff",
                    "no timer enable/start",
                    "no service start",
                    "no live delta arm",
                    "no order submit/cancel/test",
                    "no accepted evidence update",
                ],
            },
        )
        write_json(
            self.proof_root / "design_review_summary.json",
            {
                "status": "design_review_passed_no_hard_blockers",
                "reviewed_doc": "docs/MERIDIAN_POSITION_REFERENCE_FIX_WINDOW.md",
                "hard_blockers": [],
                "required_boundary": (
                    "generate Meridian equivalent genesis reference only; verify explicit and implicit "
                    "position monitor; no timer handoff"
                ),
                "reviewed_utc": utc_now(),
            },
        )
        project_state_before = sha256(self.meridian_repo / "PROJECT_STATE.md")
        pre_system = self.system_snapshot("pre_apply")
        selected_legacy, legacy_items = self.resolve_reference(self.legacy_parent)
        write_json(
            self.proof_root / "precheck_legacy_reference_selection.json",
            {
                "selected": selected_legacy,
                "selected_path_matches_inventory": bool(
                    selected_legacy and Path(str(selected_legacy["path"])) == self.expected_legacy_ref
                ),
                "expected_inventory_selected_path": str(self.expected_legacy_ref),
                "valid_candidate_count": len([item for item in legacy_items if item.get("valid")]),
            },
        )

        precheck_blockers: list[str] = []
        if not selected_legacy:
            precheck_blockers.append("no_valid_legacy_reference")
        elif Path(str(selected_legacy["path"])) != self.expected_legacy_ref:
            precheck_blockers.append("legacy_selected_reference_drifted_from_readonly_inventory")
        if selected_legacy and len(selected_legacy.get("expected_positions") or {}) != 11:
            precheck_blockers.append("legacy_selected_reference_position_count_not_11")
        if self.reference_dir.exists():
            precheck_blockers.append(f"reference_dir_already_exists:{self.reference_dir}")
        if not self.meridian_wrapper.exists() or not os.access(self.meridian_wrapper, os.X_OK):
            precheck_blockers.append(f"meridian_wrapper_missing_or_not_executable:{self.meridian_wrapper}")
        if not self.meridian_python.exists() or not os.access(self.meridian_python, os.X_OK):
            precheck_blockers.append(f"meridian_python_missing_or_not_executable:{self.meridian_python}")
        if not self.meridian_config.exists():
            precheck_blockers.append(f"meridian_config_missing:{self.meridian_config}")
        if not pre_system["timers_zero"]:
            precheck_blockers.append("pre_apply_timers_not_zero")
        if pre_system["active_related_units"]:
            precheck_blockers.append("pre_apply_related_units_active:" + ",".join(pre_system["active_related_units"]))
        write_json(self.proof_root / "precheck_static_summary.json", {"blockers": precheck_blockers, "passed": not precheck_blockers})

        reference_created = False
        reference_moved_to: str | None = None
        monitor_results: dict[str, Any] = {}
        checks: dict[str, bool] = {
            "design_review_passed": True,
            "pre_apply_timers_zero": bool(pre_system["timers_zero"]),
            "pre_apply_related_units_inactive": not bool(pre_system["active_related_units"]),
            "legacy_reference_selected": selected_legacy is not None,
            "legacy_reference_matches_inventory": bool(
                selected_legacy and Path(str(selected_legacy["path"])) == self.expected_legacy_ref
            ),
            "legacy_reference_position_count_11": bool(
                selected_legacy and len(selected_legacy.get("expected_positions") or {}) == 11
            ),
            "reference_dir_absent_before_apply": not self.reference_dir.exists(),
        }

        if not precheck_blockers:
            pre_rc = self.run_capture(
                "precheck_legacy_reference_monitor",
                self.monitor_cmd(["--reference-run", str(self.expected_legacy_ref)]),
            )
            pre_summary = self.parse_monitor_stdout("precheck_legacy_reference_monitor")
            pre_checks = self.monitor_pass_checks(
                "precheck_legacy_reference_monitor",
                pre_summary,
                expected_reference=self.expected_legacy_ref,
            )
            checks["precheck_legacy_monitor_exit_zero"] = pre_rc == 0
            checks["precheck_legacy_monitor_passed"] = all_true(pre_checks)
            monitor_results["precheck_legacy_reference_monitor"] = {
                "exit_code": pre_rc,
                "summary": pre_summary,
                "checks": pre_checks,
            }
        else:
            checks["precheck_legacy_monitor_exit_zero"] = False
            checks["precheck_legacy_monitor_passed"] = False

        if checks.get("precheck_legacy_monitor_passed") and selected_legacy:
            self.write_reference(selected_legacy, monitor_results["precheck_legacy_reference_monitor"]["summary"])
            reference_created = True
            checks["reference_created"] = True
            checks["reference_position_count_11"] = len(selected_legacy.get("expected_positions") or {}) == 11
        else:
            checks["reference_created"] = False
            checks["reference_position_count_11"] = False

        if reference_created:
            explicit_rc = self.run_capture(
                "explicit_new_reference_monitor",
                self.monitor_cmd(["--reference-run", str(self.reference_dir)]),
            )
            explicit_summary = self.parse_monitor_stdout("explicit_new_reference_monitor")
            explicit_checks = self.monitor_pass_checks(
                "explicit_new_reference_monitor",
                explicit_summary,
                expected_reference=self.reference_dir,
            )
            checks["explicit_monitor_exit_zero"] = explicit_rc == 0
            checks["explicit_monitor_passed"] = all_true(explicit_checks)
            monitor_results["explicit_new_reference_monitor"] = {
                "exit_code": explicit_rc,
                "summary": explicit_summary,
                "checks": explicit_checks,
            }

            implicit_rc = self.run_capture("implicit_meridian_reference_monitor", self.monitor_cmd([]))
            implicit_summary = self.parse_monitor_stdout("implicit_meridian_reference_monitor")
            implicit_checks = self.monitor_pass_checks(
                "implicit_meridian_reference_monitor",
                implicit_summary,
                expected_reference=self.reference_dir,
            )
            checks["implicit_monitor_exit_zero"] = implicit_rc == 0
            checks["implicit_monitor_passed"] = all_true(implicit_checks)
            monitor_results["implicit_meridian_reference_monitor"] = {
                "exit_code": implicit_rc,
                "summary": implicit_summary,
                "checks": implicit_checks,
            }

            selected_meridian, meridian_items = self.resolve_reference(self.meridian_parent)
            write_json(
                self.proof_root / "post_apply_meridian_reference_selection.json",
                {
                    "selected": selected_meridian,
                    "valid_candidate_count": len([item for item in meridian_items if item.get("valid")]),
                    "selected_is_new_reference": bool(
                        selected_meridian and Path(str(selected_meridian["path"])) == self.reference_dir
                    ),
                },
            )
            checks["meridian_selected_reference_is_new_reference"] = bool(
                selected_meridian and Path(str(selected_meridian["path"])) == self.reference_dir
            )
        else:
            checks["explicit_monitor_exit_zero"] = False
            checks["explicit_monitor_passed"] = False
            checks["implicit_monitor_exit_zero"] = False
            checks["implicit_monitor_passed"] = False
            checks["meridian_selected_reference_is_new_reference"] = False

        post_system = self.system_snapshot("post_verify")
        project_state_after = sha256(self.meridian_repo / "PROJECT_STATE.md")
        checks["post_verify_timers_zero"] = bool(post_system["timers_zero"])
        checks["post_verify_related_units_inactive"] = not bool(post_system["active_related_units"])
        checks["project_state_unchanged"] = project_state_before == project_state_after
        side_effect_checks = []
        for result in monitor_results.values():
            summary = result.get("summary") or {}
            side_effect_checks.extend(
                [
                    int(summary.get("orders_submitted") or 0) == 0,
                    int(summary.get("orders_canceled") or 0) == 0,
                    int(summary.get("account_settings_changed") or 0) == 0,
                ]
            )
        checks["all_monitor_side_effect_counts_zero"] = all(side_effect_checks) if side_effect_checks else False

        passed = all_true(checks)
        rollback = {"attempted": False, "reason": None, "moved_to": None}
        if reference_created and not passed and self.reference_dir.exists():
            rejected_dir = self.proof_root / "rejected_reference" / self.reference_dir.name
            rejected_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(self.reference_dir), str(rejected_dir))
            reference_moved_to = str(rejected_dir)
            rollback = {
                "attempted": True,
                "reason": "verification_or_boundary_check_failed",
                "moved_to": reference_moved_to,
            }
            selected_after_rollback, after_items = self.resolve_reference(self.meridian_parent)
            write_json(
                self.proof_root / "post_rollback_meridian_reference_selection.json",
                {
                    "selected": selected_after_rollback,
                    "valid_candidate_count": len([item for item in after_items if item.get("valid")]),
                },
            )

        acceptance = {
            "status": "passed" if passed else "failed_rolled_back" if rollback["attempted"] else "failed_no_apply",
            "passed": passed,
            "created_utc": utc_now(),
            "proof_root": str(self.proof_root),
            "reference_dir": str(self.reference_dir),
            "reference_created": reference_created,
            "reference_moved_to": reference_moved_to,
            "checks": checks,
            "false_checks": sorted([key for key, value in checks.items() if not value]),
            "rollback": rollback,
            "project_state_sha256_before": project_state_before,
            "project_state_sha256_after": project_state_after,
            "pre_system": pre_system,
            "post_system": post_system,
            "monitor_results": monitor_results,
            "mutation_boundary": {
                "timer_handoff_attempted": False,
                "timer_enable_start_attempted": False,
                "service_start_attempted": False,
                "live_delta_arm_attempted": False,
                "order_submit_cancel_test_attempted": False,
                "accepted_evidence_update_attempted": False,
            },
            "next_boundary": "fresh serialized remote read-only handoff precheck required before any timer handoff decision",
        }
        write_json(self.proof_root / "position_reference_fix_acceptance.json", acceptance)
        print(
            json.dumps(
                {
                    "status": acceptance["status"],
                    "passed": passed,
                    "false_checks": acceptance["false_checks"],
                    "proof_root": str(self.proof_root),
                    "reference_dir": str(self.reference_dir),
                    "reference_moved_to": reference_moved_to,
                    "precheck_legacy_status": monitor_results.get("precheck_legacy_reference_monitor", {})
                    .get("summary", {})
                    .get("status"),
                    "explicit_status": monitor_results.get("explicit_new_reference_monitor", {}).get("summary", {}).get("status"),
                    "implicit_status": monitor_results.get("implicit_meridian_reference_monitor", {})
                    .get("summary", {})
                    .get("status"),
                    "implicit_reference_run": monitor_results.get("implicit_meridian_reference_monitor", {})
                    .get("summary", {})
                    .get("reference_run"),
                    "timers_zero_after": post_system["timers_zero"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if passed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a Meridian equivalent position genesis reference and verify explicit/implicit "
            "mainnet position-monitor resolution. This script must not enable timers or submit orders."
        )
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--meridian-root", default="/root/meridian_alpha_live_runner")
    parser.add_argument(
        "--meridian-config",
        default="/root/meridian_alpha_live_runner/repo/config/live_trading/"
        "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml",
    )
    parser.add_argument(
        "--legacy-parent",
        default="/root/enhengclaw_live_runner/repo/artifacts/live_trading/"
        "hv_balanced_binance_usdm_live_2x_full_balance_candidate",
    )
    parser.add_argument(
        "--expected-legacy-ref",
        default="/root/enhengclaw_live_runner/repo/artifacts/live_trading/"
        "hv_balanced_binance_usdm_live_2x_full_balance_candidate/mainnet_delta_execution/"
        "20260531T073949118198Z-mainnet-delta-execution",
    )
    parser.add_argument(
        "--inventory-proof-root",
        default="/root/meridian_alpha_live_runner/proof_artifacts/meridian_position_reference_fix_window/"
        "20260531T130527Z-position-reference-readonly-inventory",
    )
    parser.add_argument(
        "--approval-text",
        default=(
            "User requested review of the fix-window design, then opening a separate operator-approved "
            "position-reference apply window that only generates a Meridian equivalent genesis reference "
            "and runs explicit/implicit position monitor verification, with no timer handoff."
        ),
    )
    return parser.parse_args()


def main() -> int:
    return MeridianPositionReferenceApply(parse_args()).run()


if __name__ == "__main__":
    raise SystemExit(main())
