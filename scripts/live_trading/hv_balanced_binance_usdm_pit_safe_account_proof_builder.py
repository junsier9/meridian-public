from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_binance_usdm_pit_safe_account_proof_builder.v1"
ACCOUNT_PROOF_CONTRACT_VERSION = (
    "hv_balanced_binance_usdm_pit_safe_read_only_account_proof.v1"
)
ACCOUNT_V2_ENDPOINT = "/fapi/v2/account"
ACCOUNT_V3_ENDPOINT = "/fapi/v3/account"
ACCOUNT_CONFIG_ENDPOINT = "/fapi/v1/accountConfig"
POSITION_MODE_ENDPOINT = "/fapi/v1/positionSide/dual"
OPEN_ORDERS_ENDPOINT = "/fapi/v1/openOrders"
API_RESTRICTIONS_ENDPOINT = "/sapi/v1/account/apiRestrictions"
CAN_TRADE_SOURCE = "/fapi/v2/account.canTrade"
BLOCKER_CAN_TRADE_FALSE = "canTrade_false"
BLOCKER_CAN_TRADE_MISSING = "canTrade_missing_from_endpoint"
DEFAULT_EXPECTED_EGRESS_IP = "203.0.113.10"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a PIT-safe Binance USD-M read-only account proof from retained "
            "endpoint payloads. This builder is local/fixture-only by default: it "
            "does not SSH, call Binance, place test orders, submit/cancel orders, "
            "run supervisor/timer paths, or mutate live state."
        )
    )
    parser.add_argument("--input-fixture", required=True)
    parser.add_argument("--output-root", default="")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def endpoint_payload(result: dict[str, Any]) -> Any:
    if "payload" in result:
        return result.get("payload")
    if "response" in result:
        return result.get("response")
    return {}


def endpoint_ok(result: dict[str, Any], expected_path: str) -> bool:
    return (
        result.get("status") == "ok"
        and result.get("method") == "GET"
        and result.get("path") == expected_path
    )


def as_rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in list(rows or []) if isinstance(row, dict)]


def norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def stable_rows(rows: Any, fields: list[str]) -> list[dict[str, str]]:
    normalized = []
    for row in as_rows(rows):
        normalized.append({field: norm(row.get(field)) for field in fields})
    return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))


def boolish(value: Any) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    return None


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def side_effects_zero(side_effects: dict[str, Any]) -> bool:
    methods = set(str(item).upper() for item in list(side_effects.get("http_methods_used") or []))
    return (
        (not methods or methods == {"GET"})
        and side_effects.get("only_http_get_endpoints", True) is True
        and int_zero(side_effects, "remote_files_written")
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and int_zero(side_effects, "orders_submitted")
        and int_zero(side_effects, "orders_canceled")
        and int_zero(side_effects, "order_test_calls")
        and int_zero(side_effects, "fill_count")
        and int_zero(side_effects, "trade_count")
    )


def can_trade_decision(account_v2: dict[str, Any]) -> tuple[bool | None, list[str]]:
    if "canTrade" not in account_v2:
        return None, [BLOCKER_CAN_TRADE_MISSING]
    can_trade = boolish(account_v2.get("canTrade"))
    if can_trade is True:
        return True, []
    return False, [BLOCKER_CAN_TRADE_FALSE]


def build_account_snapshot(
    endpoint_results: dict[str, Any],
    *,
    label: str,
    egress_ip: str,
    expected_egress_ip: str = DEFAULT_EXPECTED_EGRESS_IP,
) -> dict[str, Any]:
    account_v2_result = dict(endpoint_results.get("account_v2") or {})
    account_v3_result = dict(endpoint_results.get("account_v3") or {})
    account_config_result = dict(endpoint_results.get("account_config") or {})
    position_mode_result = dict(endpoint_results.get("position_mode") or {})
    open_orders_result = dict(endpoint_results.get("open_orders") or {})
    api_restrictions_result = dict(endpoint_results.get("api_restrictions") or {})

    account_v2 = dict(endpoint_payload(account_v2_result) or {})
    account_v3 = dict(endpoint_payload(account_v3_result) or {})
    account_config = dict(endpoint_payload(account_config_result) or {})
    position_mode_payload = dict(endpoint_payload(position_mode_result) or {})
    open_orders = as_rows(endpoint_payload(open_orders_result) or [])
    api_restrictions = dict(endpoint_payload(api_restrictions_result) or {})

    dual_side = position_mode_payload.get("dualSidePosition")
    position_mode = "hedge" if dual_side is True else "one_way" if dual_side is False else None
    can_trade, live_order_blockers = can_trade_decision(account_v2)
    positions_source = account_v3 if account_v3 else account_v2
    positions = as_rows(positions_source.get("positions") or [])
    position_fields = [
        "symbol",
        "positionSide",
        "positionAmt",
        "entryPrice",
        "breakEvenPrice",
        "isolated",
        "isolatedWallet",
    ]
    position_rows = []
    for row in positions:
        try:
            amount = float(row.get("positionAmt") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if abs(amount) > 1e-12:
            position_rows.append({field: norm(row.get(field)) for field in position_fields})
    position_rows = sorted(
        position_rows,
        key=lambda item: (item.get("symbol", ""), item.get("positionSide", "")),
    )

    balance_fields = ["asset", "walletBalance", "crossWalletBalance"]
    balance_rows = stable_rows(positions_source.get("assets") or [], balance_fields)
    open_order_fields = [
        "symbol",
        "orderId",
        "clientOrderId",
        "status",
        "side",
        "positionSide",
        "type",
        "origQty",
        "executedQty",
        "updateTime",
        "time",
    ]
    open_order_rows = stable_rows(open_orders, open_order_fields)

    blockers = []
    required = {
        "account_v2": (account_v2_result, ACCOUNT_V2_ENDPOINT),
        "account_v3": (account_v3_result, ACCOUNT_V3_ENDPOINT),
        "account_config": (account_config_result, ACCOUNT_CONFIG_ENDPOINT),
        "position_mode": (position_mode_result, POSITION_MODE_ENDPOINT),
        "open_orders": (open_orders_result, OPEN_ORDERS_ENDPOINT),
        "api_restrictions": (api_restrictions_result, API_RESTRICTIONS_ENDPOINT),
    }
    for name, (result, path) in required.items():
        if not endpoint_ok(result, path):
            blockers.append(f"read_only_endpoint_failed:{name}:{result.get('status_code', result.get('error_type', 'unknown'))}")
    if egress_ip != expected_egress_ip:
        blockers.append(f"egress_ip_mismatch:expected={expected_egress_ip}:actual={egress_ip}")
    if not account_v2:
        blockers.append("account_v2_read_missing")
    if not account_v3:
        blockers.append("account_v3_read_missing")
    if position_mode != "one_way":
        blockers.append(f"position_mode_mismatch:expected=one_way:actual={position_mode}")
    if len(open_order_rows) != 0:
        blockers.append(f"mainnet_open_orders_exist:{len(open_order_rows)}")

    return {
        "contract_version": "hv_balanced_binance_usdm_pit_safe_account_snapshot.v1",
        "label": label,
        "status": "ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "account_readable": bool(account_v2 and account_v3),
        "can_trade": can_trade,
        "can_trade_source": CAN_TRADE_SOURCE,
        "account_v2_has_canTrade": "canTrade" in account_v2,
        "account_v3_has_canTrade": "canTrade" in account_v3,
        "account_v3_canTrade_ignored_for_permission_decision": True,
        "future_live_order_readiness_blockers": sorted(set(live_order_blockers)),
        "position_mode": position_mode,
        "open_order_count": len(open_order_rows),
        "open_position_count": len(position_rows),
        "egress_ip": egress_ip,
        "expected_egress_ip": expected_egress_ip,
        "account_config": {
            "dual_side_position": dual_side,
            "fee_tier": account_config.get("feeTier"),
            "multi_assets_margin": account_config.get("multiAssetsMargin"),
            "trade_group_id": account_config.get("tradeGroupId"),
        },
        "api_restrictions_summary": {
            "ip_restrict": api_restrictions.get("ipRestrict"),
            "enable_futures": api_restrictions.get("enableFutures"),
            "enable_reading": api_restrictions.get("enableReading"),
            "enable_withdrawals": api_restrictions.get("enableWithdrawals"),
            "permits_universal_transfer": api_restrictions.get("permitsUniversalTransfer"),
        },
        "endpoint_schema": {
            "account_v2_path": ACCOUNT_V2_ENDPOINT,
            "account_v3_path": ACCOUNT_V3_ENDPOINT,
            "can_trade_decision_source": CAN_TRADE_SOURCE,
            "can_trade_missing_blocker": BLOCKER_CAN_TRADE_MISSING,
            "can_trade_false_blocker": BLOCKER_CAN_TRADE_FALSE,
            "account_v3_canTrade_must_not_clear_or_fail_permission": True,
        },
        "endpoint_results": {
            name: {
                "path": result.get("path"),
                "method": result.get("method"),
                "status": result.get("status"),
                "status_code": result.get("status_code"),
                "started_at_utc": result.get("started_at_utc"),
                "finished_at_utc": result.get("finished_at_utc"),
                "error_type": result.get("error_type"),
                "error": result.get("error"),
            }
            for name, (result, _path) in required.items()
        },
        "position_fingerprint": {
            "stable_fields": position_fields,
            "stable_rows": position_rows,
            "stable_hash": digest(position_rows),
        },
        "open_order_fingerprint": {
            "stable_fields": open_order_fields,
            "stable_rows": open_order_rows,
            "stable_hash": digest(open_order_rows),
        },
        "balance_fingerprint": {
            "stable_fields": balance_fields,
            "stable_rows": balance_rows,
            "stable_hash": digest(balance_rows),
        },
    }


def build_pit_safe_account_proof(
    fixture: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or utc_now()
    expected_egress_ip = str(fixture.get("expected_egress_ip") or DEFAULT_EXPECTED_EGRESS_IP)
    pre = build_account_snapshot(
        dict(fixture.get("pre_endpoint_results") or {}),
        label="pre",
        egress_ip=str(fixture.get("pre_egress_ip") or expected_egress_ip),
        expected_egress_ip=expected_egress_ip,
    )
    post = build_account_snapshot(
        dict(fixture.get("post_endpoint_results") or {}),
        label="post",
        egress_ip=str(fixture.get("post_egress_ip") or expected_egress_ip),
        expected_egress_ip=expected_egress_ip,
    )
    side_effects = dict(fixture.get("side_effects") or {})
    live_order_blockers = sorted(
        set(
            list(pre.get("future_live_order_readiness_blockers") or [])
            + list(post.get("future_live_order_readiness_blockers") or [])
        )
    )
    checks = {
        "pre_snapshot_ready": pre.get("status") == "ready",
        "post_snapshot_ready": post.get("status") == "ready",
        "can_trade_source_is_v2_account": pre.get("can_trade_source") == CAN_TRADE_SOURCE
        and post.get("can_trade_source") == CAN_TRADE_SOURCE,
        "account_v3_canTrade_ignored": pre.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True
        and post.get("account_v3_canTrade_ignored_for_permission_decision") is True,
        "can_trade_state_stable": pre.get("can_trade") == post.get("can_trade"),
        "position_fingerprint_stable": dict(pre.get("position_fingerprint") or {}).get("stable_hash")
        == dict(post.get("position_fingerprint") or {}).get("stable_hash"),
        "open_order_fingerprint_stable": dict(pre.get("open_order_fingerprint") or {}).get("stable_hash")
        == dict(post.get("open_order_fingerprint") or {}).get("stable_hash"),
        "balance_fingerprint_stable": dict(pre.get("balance_fingerprint") or {}).get("stable_hash")
        == dict(post.get("balance_fingerprint") or {}).get("stable_hash"),
        "open_order_count_zero_pre_post": int(pre.get("open_order_count") or 0) == 0
        and int(post.get("open_order_count") or 0) == 0,
        "side_effects_zero": side_effects_zero(side_effects),
    }
    collection_blockers = [key for key, value in checks.items() if not value]
    ready = not collection_blockers
    eligible_to_clear = (
        ready
        and not live_order_blockers
        and pre.get("can_trade") is True
        and post.get("can_trade") is True
    )
    if eligible_to_clear:
        reclassification = "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap"
    elif BLOCKER_CAN_TRADE_FALSE in live_order_blockers:
        reclassification = "account_side_permission_blocker"
    elif BLOCKER_CAN_TRADE_MISSING in live_order_blockers:
        reclassification = "account_v2_canTrade_missing_blocker"
    else:
        reclassification = "collection_blocked_before_permission_decision"

    return {
        "contract_version": ACCOUNT_PROOF_CONTRACT_VERSION,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": collection_blockers,
        "pit_safe_read_only_account_proof_ready": ready,
        "account_permission_source_corrected": True,
        "can_trade_source": CAN_TRADE_SOURCE,
        "account_v3_canTrade_ignored_for_permission_decision": True,
        "split_live_order_readiness_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "can_trade_pre": pre.get("can_trade"),
        "can_trade_post": post.get("can_trade"),
        "account_v2_has_canTrade_pre": pre.get("account_v2_has_canTrade"),
        "account_v2_has_canTrade_post": post.get("account_v2_has_canTrade"),
        "account_v3_has_canTrade_pre": pre.get("account_v3_has_canTrade"),
        "account_v3_has_canTrade_post": post.get("account_v3_has_canTrade"),
        "live_order_readiness_blockers": live_order_blockers,
        "eligible_to_clear_p9cf_account_can_trade_blocker": eligible_to_clear,
        "prior_p9ce_blocker_reclassification": reclassification,
        "remediation_required_if_canTrade_false": [
            "confirm Futures account is enabled",
            "confirm API key has Futures/trading permission",
            "confirm API key IP restriction includes 203.0.113.10",
            "recreate API key if it predates Futures-account enablement",
            "do not enable withdrawal permission",
        ],
        "pre": pre,
        "post": post,
        "checks": checks,
        "side_effects": side_effects,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def output_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path("artifacts/live_trading/pit_safe_account_proof_builder") / run_id


def render_markdown(proof: dict[str, Any]) -> str:
    lines = [
        "# PIT-Safe Binance USD-M Read-Only Account Proof",
        "",
        f"`Status: {proof['status']}`",
        "",
        "```text",
        f"can_trade_source = {proof['can_trade_source']}",
        f"can_trade_pre = {proof['can_trade_pre']}",
        f"can_trade_post = {proof['can_trade_post']}",
        "account_v3_canTrade_ignored_for_permission_decision = true",
        "eligible_to_clear_p9cf_account_can_trade_blocker = "
        f"{str(bool(proof['eligible_to_clear_p9cf_account_can_trade_blocker'])).lower()}",
        "live_order_readiness_blockers = "
        + ", ".join(proof["live_order_readiness_blockers"]),
        "orders_submitted = 0",
        "orders_canceled = 0",
        "fill_count = 0",
        "trade_count = 0",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = utc_now()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = output_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)
    fixture = load_json(resolve_path(args.input_fixture))
    proof = build_pit_safe_account_proof(fixture, generated_at=now)
    proof_path = root / "pit_safe_account_proof.json"
    summary_path = root / "summary.json"
    report_path = root / "pit_safe_account_proof.md"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": proof["status"],
        "blockers": proof["blockers"],
        "pit_safe_read_only_account_proof_ready": proof[
            "pit_safe_read_only_account_proof_ready"
        ],
        "eligible_to_clear_p9cf_account_can_trade_blocker": proof[
            "eligible_to_clear_p9cf_account_can_trade_blocker"
        ],
        "live_order_readiness_blockers": proof["live_order_readiness_blockers"],
        "can_trade_source": proof["can_trade_source"],
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "output_files": {
            "summary": str(summary_path),
            "pit_safe_account_proof": str(proof_path),
            "report": str(report_path),
        },
    }
    write_json(proof_path, proof)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(proof), encoding="utf-8")
    print(f"status={summary['status']}")
    print(f"summary={summary_path}")
    print(
        "eligible_to_clear_p9cf_account_can_trade_blocker="
        + str(bool(summary["eligible_to_clear_p9cf_account_can_trade_blocker"])).lower()
    )
    print("live_order_readiness_blockers=" + ",".join(summary["live_order_readiness_blockers"]))
    print("orders_submitted=0")
    print("fill_count=0")
    return 0 if summary["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
