#!/usr/bin/env python3
"""Establish a FLAT position genesis reference so the live position-monitor / core-loop
reconcile passes against a flat account.

Context: when the account is flattened out-of-band, the position monitor still resolves the
last non-flat reference (e.g. the prior delta execution) and reports `position_mismatch:
expected=<nonzero>:actual=0`, which blocks the core loop. A valid reference must be NON-EMPTY,
so "flat" is expressed as a genesis reference listing every universe symbol at
`expected_position_amt = 0.0` (NOT an empty reference, which the resolver rejects).

Read-only to the exchange: it confirms flat via the read-only position monitor (GET-only) and
writes ONLY a position-reference artifact. It NEVER submits/cancels orders, enables timers, or
arms live_delta. Default is a DRY-RUN (confirm flat + print the plan, write nothing); pass
`--apply` to write the reference and re-verify that the monitor now PASSES (rolls the reference
back if it does not).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for _p in (ROOT, SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from enhengclaw.live_trading.config import load_live_trading_config  # noqa: E402

GENESIS_STATUS = "mainnet_position_genesis_snapshot"
MONITOR = "scripts/live_trading/run_hv_balanced_mainnet_position_monitor.py"


def _as_int(value: object, default: int = -1) -> int:
    # NB: do NOT use `value or default` — a legitimate 0 (flat account) is falsy.
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def run_monitor(config: str, reference: str | None = None) -> tuple[dict, int]:
    cmd = [sys.executable, str(ROOT / MONITOR), "--config", config]
    if reference:
        cmd += ["--reference-run", reference]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    try:
        return json.loads(proc.stdout), proc.returncode
    except Exception:
        return {"__parse_error__": (proc.stdout[-400:] + proc.stderr[-400:])}, proc.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Establish a flat position genesis reference (read-only to the exchange).")
    ap.add_argument("--config", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--apply", action="store_true", help="Write the reference + re-verify. Without it, dry-run only.")
    args = ap.parse_args(argv)

    live = load_live_trading_config(args.config)
    payload = live.payload
    symbols = sorted(
        s.strip().upper()
        for s in str(dict(payload.get("market_data") or {}).get("symbols") or "").split(",")
        if s.strip()
    )
    parent = live.artifact_root.parent
    now = datetime.now(UTC)
    label = args.label or f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-flat-reconcile"
    ref_name = f"{label}-genesis-snapshot"
    ref_dir = parent / "position_reference" / ref_name

    # 1) Read-only confirm the account is FLAT (no positions, no open orders, no orders submitted).
    pre, _ = run_monitor(args.config)
    open_pos = _as_int(pre.get("open_position_count"))
    open_ord = _as_int(pre.get("open_order_count"))
    flat = open_pos == 0 and open_ord == 0 and _as_int(pre.get("orders_submitted"), 0) == 0
    print(json.dumps({
        "step": "precheck_flat", "flat": flat, "open_position_count": open_pos,
        "open_order_count": open_ord, "current_status": pre.get("status"),
        "current_reference": pre.get("reference_run"),
    }, indent=2))
    if not flat:
        print("ABORT: account is NOT flat (or unreadable); refusing to write a flat reference.")
        return 2
    if not symbols:
        print("ABORT: no universe symbols in config.market_data.symbols")
        return 2

    rows = [{"symbol": s, "expected_position_amt": 0.0} for s in symbols]
    if not args.apply:
        print(json.dumps({
            "step": "dry_run", "would_write_reference": str(ref_dir),
            "flat_expected_symbols": symbols, "symbol_count": len(symbols),
            "note": "re-run with --apply to write the reference + re-verify the monitor passes",
        }, indent=2))
        return 0

    if ref_dir.exists():
        print(f"ABORT: reference dir already exists: {ref_dir}")
        return 2
    iso = now.isoformat().replace("+00:00", "Z")
    ref_dir.mkdir(parents=True, exist_ok=False)
    with (ref_dir / "reference_positions.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["symbol", "expected_position_amt"])
        writer.writeheader()
        writer.writerows(rows)
    (ref_dir / "genesis_snapshot.json").write_text(json.dumps({
        "status": GENESIS_STATUS, "created_utc": iso, "baseline": "flat",
        "positions": rows, "position_count": len(rows),
        "source": {"kind": "flat_reconcile", "precheck_monitor_status": pre.get("status"),
                   "precheck_open_position_count": open_pos, "precheck_reference": pre.get("reference_run")},
        "mutation_boundary": {"order_or_cancel_attempted": False, "timer_enable_start_attempted": False,
                              "live_delta_arm_attempted": False},
    }, indent=2, sort_keys=True), encoding="utf-8")
    (ref_dir / "run_summary.json").write_text(json.dumps({
        "status": GENESIS_STATUS, "run_id": ref_name, "created_utc": iso, "baseline": "flat",
        "artifact_root": str(ref_dir), "position_count": len(rows),
        "orders_submitted": 0, "orders_canceled": 0, "order_test_calls": 0,
        "timer_enable_start_attempted": False, "live_delta_arm_attempted": False,
    }, indent=2, sort_keys=True), encoding="utf-8")

    # 2) Re-verify: the monitor must now resolve THIS flat reference and PASS.
    post, _ = run_monitor(args.config)
    ref_is_new = Path(str(post.get("reference_run") or "")).resolve() == ref_dir.resolve()
    passed = post.get("status") == "passed_live_position_monitor" and list(post.get("blockers") or []) == [] and ref_is_new
    print(json.dumps({
        "step": "verify", "passed": passed, "monitor_status": post.get("status"),
        "blocker_count": len(post.get("blockers") or []), "reference_run": post.get("reference_run"),
        "reference_is_new_flat": ref_is_new, "orders_submitted": post.get("orders_submitted"),
    }, indent=2))
    if not passed:
        rejected = ref_dir.parent / ("REJECTED-" + ref_name)
        shutil.move(str(ref_dir), str(rejected))
        print(json.dumps({"step": "rollback", "moved_to": str(rejected),
                          "reason": "monitor did not pass against the new flat reference",
                          "blockers": list(post.get("blockers") or [])[:12]}, indent=2))
        return 2
    print(f"OK: flat reconcile reference established at {ref_dir}; position monitor PASSES from flat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
