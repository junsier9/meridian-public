from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10akv_p10akx_read_only_position_relation_corridor import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P10AKV_PARENT,
    P10AKX_CONTRACT,
    P10AKY_RESOLUTION_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    latest_match,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10aky_p10ala_position_relation_resolution_corridor.v1"
P10AKY_CONTRACT = "hv_balanced_12factor_p10aky_define_position_relation_resolution_scope.v1"
P10AKZ_CONTRACT = "hv_balanced_12factor_p10akz_position_relation_resolution_proposal_package.v1"
P10ALA_CONTRACT = "hv_balanced_12factor_p10ala_review_position_relation_resolution_proposal.v1"

DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10aky_p10ala_position_relation_resolution_corridor"

P10AKZ_GATE = "P10AKZ_prepare_candidate_position_relation_resolution_proposal_only_if_separately_requested"
P10ALA_GATE = "P10ALA_review_candidate_position_relation_resolution_proposal_only_if_separately_requested"
P10ALB_GATE = "P10ALB_owner_select_candidate_position_relation_resolution_path_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AKY-P10ALA. This is local/proof-only: define the candidate "
            "side vs existing position resolution scope, prepare a resolution "
            "proposal, and review it. It does not call remote APIs, submit/"
            "cancel orders, run timer/supervisor, mutate live config/operator/"
            "executor state, or select a resolution path."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10akx-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10akx",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p10akx_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(P10AKV_PARENT, "*/p10akx_scope/summary.json")


def source_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def p10akx_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AKX_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10akx_post_relation_proof_scope_ready") is True
        and summary.get("fresh_relation_executable_under_revised_terms") is False
        and summary.get("next_scope_requires_position_relation_resolution") is True
        and summary.get("allowed_next_gate") == P10AKY_RESOLUTION_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("live_order_submission_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
    )


def no_execution_matrix() -> dict[str, Any]:
    return {
        "proof_artifacts_only": True,
        "remote_api_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "timer_path_load_authorized": False,
        "timer_path_load_performed": False,
        "supervisor_invocation_authorized": False,
        "supervisor_invocation_performed": False,
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
        "executor_input_mutation_performed": False,
        "target_plan_replacement_performed": False,
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "live_order_submission_authorized": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def load_relation_context(p10akx: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    p10akw_path = source_path(p10akx, "p10akw_summary")
    p10akw = load_optional(p10akw_path)
    p10akv_path = source_path(p10akw, "p10akv_summary")
    p10akv = load_optional(p10akv_path)
    relation = dict(p10akv.get("fresh_position_relation") or {})
    return {
        "p10akw_summary_path": str(p10akw_path),
        "p10akv_summary_path": str(p10akv_path),
        "fresh_position_relation": relation,
        "fresh_relation_executable_under_revised_terms": bool(
            p10akv.get("fresh_relation_executable_under_revised_terms")
        ),
        "future_execution_precheck_ready_under_revised_terms": bool(
            p10akv.get("future_execution_precheck_ready_under_revised_terms")
        ),
    }, p10akv_path


def build_p10aky(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akx_path: Path,
    p10akx: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    checks = {
        "owner_decision_p10aky_recorded": True,
        "p10akx_ready_for_resolution_scope": p10akx_ready(p10akx),
        "scope_only": True,
        "no_order_no_remote_no_timer": True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10aky_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10aky_define_candidate_position_relation_resolution_scope_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "scope_only": True,
        "authorizes_resolution_proposal": status == "ready",
        "authorizes_resolution_path_selection": False,
        "authorizes_live_order": False,
    }
    scope = {
        "contract_version": "hv_balanced_12factor_p10aky_scope.v1",
        "status": status,
        "blockers": blockers,
        "scope": "define_candidate_side_vs_existing_position_resolution_scope_no_order_no_remote_no_timer",
        "resolution_paths_to_compare": [
            "wait_for_relation_to_be_flat_or_same_direction_then_rerun_read_only_proof",
            "regenerate_candidate_target_plan_against_current_account_position_then_rerun_parity",
            "define_separate_owner_approved_reduce_only_reduction_canary_terms",
        ],
        "must_not_select_path_inside_p10aky": True,
        "must_not_do": [
            "remote account read",
            "live order or cancel",
            "target-plan replacement",
            "candidate executor path execution",
            "timer/supervisor path load",
            "live config/operator/executor mutation",
        ],
    }
    phase_dir = write_phase(root, "p10aky_scope", {"owner_decision": owner_decision, "scope": scope})
    summary = {
        "contract_version": P10AKY_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10aky_position_relation_resolution_scope_ready": status == "ready",
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {"p10akx_summary": evidence_file(p10akx_path)},
        "allowed_next_gate": P10AKZ_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "prepare_position_relation_resolution_proposal_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "scope": str(phase_dir / "proof" / "scope.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10akz(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10aky_path: Path,
    p10aky: dict[str, Any],
    relation_context: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    relation = dict(relation_context.get("fresh_position_relation") or {})
    relation_name = str(relation.get("relation") or "")
    current_relation_requires_resolution = relation_name in {
        "opposite_direction_reduce_existing_long",
        "opposite_direction_reduce_existing_short",
        "unknown_or_unsupported_position_relation",
    }
    proposal = {
        "contract_version": "hv_balanced_12factor_p10akz_position_relation_resolution_proposal.v1",
        "status": "ready",
        "current_relation": relation,
        "current_relation_requires_resolution": current_relation_requires_resolution,
        "paths": [
            {
                "path_id": "wait_for_executable_relation",
                "description": "Do not trade; rerun fresh read-only position-relation proof later and proceed only if relation becomes flat or same-direction.",
                "can_lead_to_live_order_without_new_owner_path_selection": False,
                "requires_remote_read_before_next_execution_gate": True,
                "live_order_authorized_now": False,
            },
            {
                "path_id": "target_plan_position_alignment_refresh",
                "description": "Regenerate candidate target-plan/replacement proof with current account position as an explicit input, then rerun research-to-live parity and relation proof.",
                "can_lead_to_live_order_without_new_owner_path_selection": False,
                "requires_parity_rerun": True,
                "live_order_authorized_now": False,
            },
            {
                "path_id": "separate_reduce_only_reduction_canary",
                "description": "Create a separate owner-approved canary class for intentional risk-reducing orders against an existing position; restoration is not attempted and must be accepted explicitly.",
                "can_lead_to_live_order_without_new_owner_path_selection": False,
                "requires_new_terms": [
                    "reduceOnly=true",
                    "quantity capped by current position, candidate delta, and max notional",
                    "post-only GTX only if exchange accepts reduceOnly+GTX; otherwise blocked",
                    "no non-reduce-only restoration",
                    "one cycle only, no continuous automation",
                    "post-run reconciliation and fresh position fingerprint",
                ],
                "live_order_authorized_now": False,
            },
        ],
        "recommended_next_gate": P10ALB_GATE,
        "recommended_next_gate_reason": "owner must select a resolution path before any further readiness or execution package",
        "does_not_authorize_execution": True,
    }
    checks = {
        "p10aky_ready": p10aky.get("status") == "ready" and p10aky.get("allowed_next_gate") == P10AKZ_GATE,
        "current_relation_loaded": bool(relation_name),
        "current_relation_requires_resolution": current_relation_requires_resolution,
        "proposal_has_three_paths": len(proposal["paths"]) == 3,
        "proposal_does_not_authorize_execution": proposal["does_not_authorize_execution"] is True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    proposal["status"] = status
    proposal["blockers"] = blockers
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akz_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akz_prepare_candidate_position_relation_resolution_proposal_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "proposal_only": True,
        "authorizes_path_selection": False,
        "authorizes_live_order": False,
    }
    phase_dir = write_phase(root, "p10akz_resolution_proposal", {"owner_decision": owner_decision, "proposal": proposal})
    summary = {
        "contract_version": P10AKZ_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akz_position_relation_resolution_proposal_ready": status == "ready",
        "current_relation": relation_name,
        "current_relation_requires_resolution": current_relation_requires_resolution,
        "resolution_path_selected": False,
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {
            "p10aky_summary": evidence_file(p10aky_path),
            "p10akv_summary": evidence_file(Path(str(relation_context.get("p10akv_summary_path") or ""))),
        },
        "allowed_next_gate": P10ALA_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_position_relation_resolution_proposal_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "proposal": str(phase_dir / "proof" / "proposal.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10ala(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akz_path: Path,
    p10akz: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    proposal_path = Path(str(dict(p10akz.get("output_files") or {}).get("proposal") or ""))
    proposal = load_optional(proposal_path)
    checks = {
        "owner_decision_p10ala_recorded": True,
        "p10akz_ready": p10akz.get("status") == "ready" and p10akz.get("allowed_next_gate") == P10ALA_GATE,
        "proposal_file_exists": proposal_path.exists() and proposal_path.is_file(),
        "proposal_has_three_paths": len(proposal.get("paths") or []) == 3,
        "proposal_recommends_owner_path_selection": proposal.get("recommended_next_gate") == P10ALB_GATE,
        "proposal_does_not_authorize_execution": proposal.get("does_not_authorize_execution") is True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10ala_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ala_review_position_relation_resolution_proposal_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only": True,
        "authorizes_owner_path_selection_gate": status == "ready",
        "authorizes_live_order": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10ala_review.v1",
        "status": status,
        "blockers": blockers,
        "conclusion": (
            "resolution_proposal_sufficient_for_owner_path_selection_gate_not_for_order"
            if status == "ready"
            else "resolution_proposal_not_sufficient"
        ),
        "path_selection_required": True,
        "does_not_authorize": [
            "selecting a resolution path inside P10ALA",
            "live order",
            "remote read",
            "timer/supervisor path load",
            "candidate executor path execution",
            "live config/operator/executor mutation",
        ],
    }
    phase_dir = write_phase(root, "p10ala_review", {"owner_decision": owner_decision, "review": review})
    summary = {
        "contract_version": P10ALA_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ala_review_position_relation_resolution_proposal_ready": status == "ready",
        "resolution_path_selection_required": status == "ready",
        "resolution_path_selected": False,
        "p10ala_sufficient_for_live_order": False,
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {
            "p10akz_summary": evidence_file(p10akz_path),
            "proposal": evidence_file(proposal_path),
        },
        "allowed_next_gate": P10ALB_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_select_one_position_relation_resolution_path_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "review": str(phase_dir / "proof" / "review.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def run_corridor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)

    p10akx_path = latest_p10akx_summary(args.p10akx_summary)
    p10akx = load_optional(p10akx_path)
    relation_context, _ = load_relation_context(p10akx)
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10aky, p10aky_path = build_p10aky(
        root=root,
        run_id=run_id,
        now=started,
        args=args,
        p10akx_path=p10akx_path,
        p10akx=p10akx,
    )
    steps.append({"gate": "P10AKY", "status": p10aky.get("status"), "summary": evidence_file(p10aky_path)})
    if p10aky.get("status") != "ready":
        blockers.append("p10aky_blocked")
        status = "blocked"

    p10akz: dict[str, Any] = {}
    p10akz_path = root / "p10akz_resolution_proposal" / "summary.json"
    if status == "ready":
        p10akz, p10akz_path = build_p10akz(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10aky_path=p10aky_path,
            p10aky=p10aky,
            relation_context=relation_context,
        )
        steps.append({"gate": "P10AKZ", "status": p10akz.get("status"), "summary": evidence_file(p10akz_path)})
        if p10akz.get("status") != "ready":
            blockers.append("p10akz_blocked")
            status = "blocked"

    p10ala: dict[str, Any] = {}
    p10ala_path = root / "p10ala_review" / "summary.json"
    if status == "ready":
        p10ala, p10ala_path = build_p10ala(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10akz_path=p10akz_path,
            p10akz=p10akz,
        )
        steps.append({"gate": "P10ALA", "status": p10ala.get("status"), "summary": evidence_file(p10ala_path)})
        if p10ala.get("status") != "ready":
            blockers.append("p10ala_blocked")
            status = "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10aky_p10ala_position_relation_resolution_corridor_ready": status == "ready",
        "corridor_scope": "P10AKY scope + P10AKZ proposal + P10ALA review",
        "steps": steps,
        "current_relation": str(dict(relation_context.get("fresh_position_relation") or {}).get("relation") or ""),
        "resolution_path_selection_required": status == "ready",
        "resolution_path_selected": False,
        "blockers": blockers,
        **no_execution_matrix(),
        "source_evidence": {"p10akx_summary": evidence_file(p10akx_path)},
        "allowed_next_gate": str(p10ala.get("allowed_next_gate") or "") if status == "ready" else "",
        "allowed_next_gate_scope": str(p10ala.get("allowed_next_gate_scope") or "") if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(root / "summary.json")},
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_corridor(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"current_relation={summary['current_relation']}")
    print("summary=" + summary["output_files"]["summary"])
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
