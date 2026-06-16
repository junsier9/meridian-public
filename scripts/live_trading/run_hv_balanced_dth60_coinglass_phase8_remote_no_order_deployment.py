from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import (  # noqa: E402
    TARGET_CONTRIBUTION,
    evidence_file,
    is_zero_order,
    load_json,
    no_live_mutation,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase8_remote_no_order_deployment.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase8_remote_proof_artifacts_no_order_deployment"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate P8 remote proof-artifacts no-order deployment evidence for "
            "the hv_balanced DTH60/CoinGlass candidate."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p7-summary", required=True)
    parser.add_argument("--phase2-summary", required=True)
    parser.add_argument("--phase2b-summary", required=True)
    parser.add_argument("--remote-phase3-summary", required=True)
    parser.add_argument("--remote-phase4-summary", required=True)
    parser.add_argument("--pre-control-snapshot", required=True)
    parser.add_argument("--post-control-snapshot", required=True)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def control_state_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    systemd = dict(snapshot.get("systemd") or {})
    operator_state = snapshot.get("operator_state") or []
    if isinstance(operator_state, list):
        operator = {str(row.get("key")): str(row.get("value")) for row in operator_state}
    else:
        operator = dict(operator_state)
    return {
        "remote_live_config_sha256": snapshot.get("remote_live_config_sha256"),
        "systemd": systemd,
        "operator_state": operator,
    }


def build_phase8_summary(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id

    paths = {
        "p7_summary": resolve_path(args.p7_summary),
        "phase2_summary": resolve_path(args.phase2_summary),
        "phase2b_summary": resolve_path(args.phase2b_summary),
        "remote_phase3_summary": resolve_path(args.remote_phase3_summary),
        "remote_phase4_summary": resolve_path(args.remote_phase4_summary),
        "pre_control_snapshot": resolve_path(args.pre_control_snapshot),
        "post_control_snapshot": resolve_path(args.post_control_snapshot),
    }
    p7 = load_json(paths["p7_summary"])
    phase2 = load_json(paths["phase2_summary"])
    phase2b = load_json(paths["phase2b_summary"])
    phase3 = load_json(paths["remote_phase3_summary"])
    phase4 = load_json(paths["remote_phase4_summary"])
    pre = load_json(paths["pre_control_snapshot"])
    post = load_json(paths["post_control_snapshot"])

    pre_digest = control_state_digest(pre)
    post_digest = control_state_digest(post)
    control_plane_unchanged = pre_digest == post_digest
    phase3_target_boundary_ok = (
        phase3.get("changed_contribution_columns") == [TARGET_CONTRIBUTION]
        and not phase3.get("changed_non_target_contribution_columns")
        and float(phase3.get("non_target_contribution_max_abs_diff_enabled_vs_disabled") or 0.0) == 0.0
    )
    gates = {
        "p7_ready": p7.get("status") == "ready",
        "p7_draft_only_not_applied": p7.get("applied_to_live") is False,
        "p7_no_order_authority": p7.get("eligible_for_live_order_submission") is False,
        "fresh_phase2_ready": phase2.get("status") == "ready",
        "fresh_phase2_no_future_stale_zero_fill": all(
            phase2.get(key) is True for key in (
                "no_future_fill_proven",
                "no_stale_fill_proven",
                "no_zero_fill_proven",
            )
        ),
        "fresh_phase2b_ready": phase2b.get("status") == "ready",
        "fresh_phase2b_no_future_stale_zero_fill": all(
            phase2b.get(key) is True for key in (
                "no_future_fill_proven",
                "no_stale_fill_proven",
                "no_zero_fill_proven",
            )
        ),
        "remote_phase3_ready": phase3.get("status") == "ready",
        "remote_phase3_combined_trigger_proven": phase3.get("combined_candidate_trigger_proven") is True,
        "remote_phase3_overlay_only_target_contribution": phase3_target_boundary_ok,
        "remote_phase3_no_live_mutation": no_live_mutation(phase3),
        "remote_phase4_ready": phase4.get("status") == "ready",
        "remote_phase4_same_timestamp_context": phase4.get("same_timestamp_context_proven") is True,
        "remote_phase4_same_risk_inputs": phase4.get("same_risk_inputs_proven") is True,
        "remote_phase4_same_symbol_set": phase4.get("same_symbol_set_proven") is True,
        "remote_phase4_same_portfolio_engine": phase4.get("same_portfolio_engine_proven") is True,
        "remote_phase4_plan_only_risk_gates_passed": (
            phase4.get("baseline_plan_only_risk_gate_status") == "passed"
            and phase4.get("candidate_plan_only_risk_gate_status") == "passed"
        ),
        "remote_phase4_zero_orders_fills": is_zero_order(phase4),
        "remote_phase4_no_live_mutation": no_live_mutation(phase4),
        "remote_control_plane_unchanged": control_plane_unchanged,
        "remote_post_no_p8_mutation_observed": post.get("p8_remote_mutation_observed") is False,
    }
    ready = all(bool(value) for value in gates.values())
    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": "ready" if ready else "blocked",
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "source_evidence": {key: evidence_file(path) for key, path in paths.items()},
        "remote_phase3": {
            "run_id": phase3.get("run_id"),
            "generated_at_utc": phase3.get("generated_at_utc"),
            "status": phase3.get("status"),
            "changed_contribution_columns": phase3.get("changed_contribution_columns"),
            "non_target_contribution_max_abs_diff_enabled_vs_disabled": phase3.get(
                "non_target_contribution_max_abs_diff_enabled_vs_disabled"
            ),
        },
        "remote_phase4": {
            "run_id": phase4.get("run_id"),
            "generated_at_utc": phase4.get("generated_at_utc"),
            "status": phase4.get("status"),
            "same_timestamp_context_proven": phase4.get("same_timestamp_context_proven"),
            "same_risk_inputs_proven": phase4.get("same_risk_inputs_proven"),
            "target_weight_delta_symbol_count": phase4.get("target_weight_delta_symbol_count"),
            "absolute_target_weight_delta_sum": phase4.get("absolute_target_weight_delta_sum"),
            "orders_submitted": phase4.get("orders_submitted"),
            "fill_count": phase4.get("fill_count"),
            "mainnet_order_submission_authorized": phase4.get("mainnet_order_submission_authorized"),
        },
        "control_plane": {
            "pre": pre_digest,
            "post": post_digest,
            "unchanged": control_plane_unchanged,
        },
        "gates": gates,
        "eligible_for_remote_no_order_shadow_observation": ready,
        "eligible_for_live_order_submission": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "blockers": [] if ready else [key for key, value in gates.items() if not value],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", summary)
    (output_root / "remote_no_order_deployment.md").write_text(render_markdown(summary), encoding="utf-8")
    summary["output_files"] = {
        "summary": str(output_root / "summary.json"),
        "remote_no_order_deployment_md": str(output_root / "remote_no_order_deployment.md"),
    }
    write_json(output_root / "summary.json", summary)
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P8 Remote Proof-Artifacts No-Order Deployment",
        "",
        f"Status: `{summary['status']}`",
        f"Generated: `{summary['generated_at_utc']}`",
        "",
        "## Boundary",
        "",
        "- Remote execution occurred only under proof_artifacts.",
        "- The live supervisor timer path did not load the candidate overlay.",
        "- Order submission remains disabled.",
        "",
        "## Gates",
        "",
    ]
    for key, value in summary["gates"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend([
        "",
        "## Remote Phase 4",
        "",
        f"- run_id: `{summary['remote_phase4']['run_id']}`",
        f"- same_risk_inputs_proven: `{summary['remote_phase4']['same_risk_inputs_proven']}`",
        f"- orders_submitted: `{summary['remote_phase4']['orders_submitted']}`",
        f"- fill_count: `{summary['remote_phase4']['fill_count']}`",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase8_summary(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
