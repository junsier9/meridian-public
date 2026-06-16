from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_MERIDIAN_SUPERVISOR_TIMER = "meridian-alpha-mainnet-supervisor-live.timer"


def int_field(data: dict[str, Any], key: str, *, default: int | None = None) -> int | None:
    value = data.get(key, default)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def health_timer_name(summary: dict[str, Any]) -> str:
    timer_status = summary.get("systemd_timer_status")
    if isinstance(timer_status, dict):
        nested_name = str(timer_status.get("timer_name") or "").strip()
        if nested_name:
            return nested_name
    return str(summary.get("systemd_timer_name") or "").strip()


def health_supervisor_open_orders_zero(summary: dict[str, Any]) -> bool:
    supervisor_runs = summary.get("supervisor_runs")
    if not isinstance(supervisor_runs, list) or not supervisor_runs:
        return False
    for item in supervisor_runs:
        if not isinstance(item, dict):
            return False
        if int_field(item, "open_order_count", default=-1) != 0:
            return False
    return True


def build_post_arm_health_checks(
    summary: dict[str, Any],
    *,
    expected_timer: str = EXPECTED_MERIDIAN_SUPERVISOR_TIMER,
) -> dict[str, bool]:
    timer_status = summary.get("systemd_timer_status")
    if not isinstance(timer_status, dict):
        timer_status = {}

    return {
        "health_passed": summary.get("status") == "mainnet_health_monitor_passed",
        "health_zero_critical": int_field(summary, "critical_alert_count", default=-1) == 0,
        "health_live_capable_mode": summary.get("no_order_expected") is False,
        "health_live_delta_still_armed": summary.get("live_delta_armed_after") is True,
        "health_no_orders_from_monitor": int_field(summary, "orders_submitted", default=-1) == 0,
        "health_no_fills_from_monitor": int_field(summary, "fill_count", default=-1) == 0,
        "health_timer_status_ok": timer_status.get("status") == "ok",
        "health_timer_name_meridian": health_timer_name(summary) == expected_timer,
        "health_supervisor_open_orders_zero": health_supervisor_open_orders_zero(summary),
    }


def build_prearm_baseline_health_checks(
    summary: dict[str, Any],
    *,
    expected_timer: str = EXPECTED_MERIDIAN_SUPERVISOR_TIMER,
) -> dict[str, bool]:
    timer_status = summary.get("systemd_timer_status")
    if not isinstance(timer_status, dict):
        timer_status = {}

    return {
        "health_passed": summary.get("status") == "mainnet_health_monitor_passed",
        "health_zero_critical": int_field(summary, "critical_alert_count", default=-1) == 0,
        "health_no_order_expected_mode": summary.get("no_order_expected") is True,
        "health_live_delta_disarmed": summary.get("live_delta_armed_after") is False,
        "health_no_orders_from_monitor": int_field(summary, "orders_submitted", default=-1) == 0,
        "health_no_fills_from_monitor": int_field(summary, "fill_count", default=-1) == 0,
        "health_timer_status_ok": timer_status.get("status") == "ok",
        "health_timer_name_meridian": health_timer_name(summary) == expected_timer,
        "health_supervisor_open_orders_zero": health_supervisor_open_orders_zero(summary),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Meridian health summary fields for the proof driver."
    )
    parser.add_argument("--health-summary", required=True, help="Path to a mainnet health monitor run_summary.json")
    parser.add_argument(
        "--mode",
        choices=["post-arm", "prearm-baseline"],
        default="post-arm",
        help="Health-summary proof contract to evaluate.",
    )
    parser.add_argument(
        "--expected-timer",
        default=EXPECTED_MERIDIAN_SUPERVISOR_TIMER,
        help="Expected Meridian supervisor timer name.",
    )
    args = parser.parse_args(argv)

    if args.health_summary == "-":
        summary = json.load(sys.stdin)
    else:
        summary = json.loads(Path(args.health_summary).read_text(encoding="utf-8"))
    if args.mode == "prearm-baseline":
        checks = build_prearm_baseline_health_checks(summary, expected_timer=args.expected_timer)
    else:
        checks = build_post_arm_health_checks(summary, expected_timer=args.expected_timer)
    output = {
        "status": "passed" if all(checks.values()) else "failed",
        "mode": args.mode,
        "checks": checks,
        "timer_name": health_timer_name(summary),
        "expected_timer": args.expected_timer,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
