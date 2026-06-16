from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.frozen_frontier_contract import (  # noqa: E402
    CARRY_FORWARD_SENTINEL_FACTOR,
    REQUIRED_FEATURE_COUNT,
    file_sha256 as contract_file_sha256,
    frontier_config,
    frontier_enabled,
    validate_frontier_contract,
)
from enhengclaw.live_trading.frozen_frontier_overlay import (  # noqa: E402
    validate_overlay_contract,
    validate_thresholds_pit,
)
from enhengclaw.live_trading.frozen_frontier_live import (  # noqa: E402
    FRONTIER_SCORING_MARKER_KEY,
    FRONTIER_SCORING_MARKER_VALUE,
)


CONTRACT_VERSION = "project_governance_frontier_contract_governance_gate.v1"
APPROVE_FRONTIER_CONTRACT_GOVERNANCE = (
    "approve_frontier_contract_governance_validation_no_runtime_enablement"
)
DEFAULT_OUTPUT_PARENT = "artifacts/governance/frontier_contract_governance_gate"

LIVE_TIMER_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
CARRY_FORWARD_BLOCKER_PREFIX = "frontier_carry_forward_signature_detected"

NEXT_GATE = "Restricted_unattended_gate_or_owner_arm_checklist_only_if_separately_requested"
NEXT_GATE_SCOPE = (
    "frontier_contract_is_pinned_carry_forward_free_and_structurally_valid_a_"
    "prerequisite_for_flipping_strategy_frontier_enabled_no_runtime_enablement_here"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bind the live frozen-frontier CONTRACT state into governance READY: verify the "
            "live config's strategy.frontier block exists, its weight/scoring/overlay contracts "
            "are sha-pinned and the pins match the on-disk files, the frozen vector is the "
            "12-factor frontier (not the baseline) and is CARRY-FORWARD-FREE (the forbidden "
            "diagnostic vector is rejected), and the overlay (if enabled) is pinned with PIT "
            "thresholds. Proof-only: it reads config + contract files and never mutates "
            "anything, never flips strategy.frontier.enabled, and enables no runtime order "
            "flow. It validates the contract whether the frontier is dormant or armed, so it "
            "is a prerequisite the owner can satisfy BEFORE the coordinated enable."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--host-config", default=LIVE_TIMER_CONFIG)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_FRONTIER_CONTRACT_GOVERNANCE)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:frontier_contract_governance_gate",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def load_yaml_optional(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def build_frontier_contract_governance_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "frontier_contract_governance" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    owner_decision_ok = str(args.owner_decision) == APPROVE_FRONTIER_CONTRACT_GOVERNANCE
    host_config = load_yaml_optional(args.host_config)
    cfg = frontier_config(host_config)
    enabled = frontier_enabled(host_config)
    overlay_cfg = dict(cfg.get("overlay") or {})
    overlay_enabled = _flag(overlay_cfg.get("enabled"))

    # --- Frozen frontier weight contract (the binding identity + carry-forward guard). ---
    weights_path_raw = _clean(cfg.get("weights_contract_path"))
    weights_file_sha = _clean(cfg.get("weights_file_sha256"))
    weights_spec_hash = _clean(cfg.get("weights_spec_hash"))
    weights_result = validate_frontier_contract(
        path=resolve_path(weights_path_raw) if weights_path_raw else None,
        expected_file_sha256=weights_file_sha or None,
        expected_spec_hash=weights_spec_hash or None,
        require_configured=True,
    )
    weights_blockers = list(weights_result.get("blockers") or [])
    carry_forward_absent = not any(b.startswith(CARRY_FORWARD_BLOCKER_PREFIX) for b in weights_blockers)

    # --- 12-factor scoring config: sha-pinned, matches on disk, and marked frontier. ---
    scoring_path_raw = _clean(cfg.get("scoring_config_path"))
    scoring_sha_pinned = _clean(cfg.get("scoring_config_sha256"))
    scoring_path = resolve_path(scoring_path_raw) if scoring_path_raw else None
    scoring_on_disk_sha = (
        contract_file_sha256(scoring_path)
        if scoring_path and scoring_path.exists() and scoring_path.is_file()
        else ""
    )
    scoring_doc: dict[str, Any] = {}
    if scoring_path and scoring_path.exists() and scoring_path.is_file():
        try:
            scoring_doc = dict(json.loads(scoring_path.read_text(encoding="utf-8-sig")))
        except (ValueError, TypeError):
            scoring_doc = {}
    scoring_marker_ok = str(scoring_doc.get(FRONTIER_SCORING_MARKER_KEY) or "") == FRONTIER_SCORING_MARKER_VALUE
    scoring_columns = [str(c) for c in (scoring_doc.get("feature_columns") or [])]

    # --- Optional dth60 overlay: pinned contract + PIT (non-synthetic) thresholds. ---
    overlay_result: dict[str, Any] = {}
    overlay_threshold_blockers: list[str] = []
    if overlay_enabled:
        overlay_path_raw = _clean(overlay_cfg.get("contract_path"))
        overlay_result = validate_overlay_contract(
            path=resolve_path(overlay_path_raw) if overlay_path_raw else None,
            expected_file_sha256=_clean(overlay_cfg.get("file_sha256")) or None,
            expected_spec_hash=_clean(overlay_cfg.get("spec_hash")) or None,
            require_configured=True,
        )
        overlay_threshold_blockers = validate_thresholds_pit(dict(overlay_cfg.get("thresholds") or {}))

    checks = {
        "owner_decision_frontier_contract_governance_recorded": owner_decision_ok,
        "host_config_present": bool(host_config),
        "frontier_block_present": bool(cfg),
        "weights_contract_path_pinned": bool(weights_path_raw),
        "weights_file_sha256_pinned": bool(weights_file_sha),
        "weights_spec_hash_pinned": bool(weights_spec_hash),
        # validate_frontier_contract folds: file-sha match, spec-hash match, 12-factor count,
        # cols==weights keys, no future-label cols, abs_sum>0, provenance source_card_sha256.
        "weights_contract_valid": bool(weights_result.get("passed")),
        # Surfaced as a NAMED release condition (the owner's requirement): the frozen vector is
        # NOT the forbidden carry-forward signature (sentinel factor strictly negative).
        "carry_forward_absent": carry_forward_absent,
        "scoring_config_path_pinned": bool(scoring_path_raw),
        "scoring_config_sha256_pinned": bool(scoring_sha_pinned),
        "scoring_config_sha256_matches_on_disk": bool(
            scoring_on_disk_sha and scoring_sha_pinned and scoring_on_disk_sha == scoring_sha_pinned
        ),
        "scoring_config_marked_frontier": scoring_marker_ok,
        "scoring_config_feature_count_is_12": len(scoring_columns) == REQUIRED_FEATURE_COUNT,
    }
    if overlay_enabled:
        checks["overlay_contract_valid"] = bool(overlay_result.get("passed"))
        checks["overlay_thresholds_pit_valid"] = not overlay_threshold_blockers

    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers
    status = "ready" if ready else "blocked"

    contract_evidence = {
        "frontier_enabled_in_config": enabled,
        "overlay_enabled_in_config": overlay_enabled,
        "weights_contract_path": weights_path_raw,
        "weights_file_sha256_pinned": weights_file_sha,
        "weights_spec_hash_pinned": weights_spec_hash,
        "weights_file_sha256_on_disk": str(weights_result.get("file_sha256") or ""),
        "weights_spec_hash_on_disk": str(weights_result.get("spec_hash") or ""),
        "weights_feature_count": int(weights_result.get("feature_count") or 0),
        "weights_abs_sum": weights_result.get("abs_sum"),
        "weights_strategy_id": str(weights_result.get("strategy_id") or ""),
        "weights_source_card_id": str(weights_result.get("source_card_id") or ""),
        "weights_validation_blockers": sorted(weights_blockers),
        "carry_forward_sentinel_factor": CARRY_FORWARD_SENTINEL_FACTOR,
        "scoring_config_path": scoring_path_raw,
        "scoring_config_sha256_pinned": scoring_sha_pinned,
        "scoring_config_sha256_on_disk": scoring_on_disk_sha,
        "overlay_validation_blockers": sorted(overlay_result.get("blockers") or []),
        "overlay_threshold_blockers": sorted(overlay_threshold_blockers),
    }

    owner_record = {
        "contract_version": "project_governance_frontier_contract_governance_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "frontier_contract_governance_recorded": owner_decision_ok,
        "config_mutation_approved": False,
        "frontier_enable_flip_in_this_gate": False,
        "runtime_enablement_approved_now": False,
    }

    non_authorization = {
        "contract_version": "project_governance_frontier_contract_governance_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "frontier_contract_governance_recorded": ready,
            "frontier_enable_flip_in_this_gate": False,
            "host_config_mutation_in_this_gate": False,
            "contract_file_mutation_in_this_gate": False,
            "continuous_automated_order_flow": False,
            "timer_path_load": False,
            "live_order_submission": False,
            "candidate_execution": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }

    control = {
        "contract_version": "project_governance_frontier_contract_governance_control_readback.v1",
        "run_id": run_id,
        "scope": "contract_validation_record_only_no_mutation_no_enable",
        "host_config_changed": False,
        "contract_files_changed": False,
        "frontier_enabled_flipped": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "frontier_contract_readback": str(proof_root / "frontier_contract_readback.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "frontier_contract_governance_gate.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": status,
        "blockers": blockers,
        "frontier_contract_governance_gate_ready": ready,
        "frontier_contract_pinned_and_carry_forward_free": ready,
        "frontier_enabled_in_config": enabled,
        "overlay_enabled_in_config": overlay_enabled,
        "carry_forward_absent": carry_forward_absent,
        "frontier_enable_flip_performed": False,
        "host_config_mutation_performed": False,
        "continuous_automated_order_flow_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "allowed_next_gate": NEXT_GATE if ready else "",
        "allowed_next_gate_scope": NEXT_GATE_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": ready,
        "contract_evidence": contract_evidence,
        "source_evidence": {
            "host_config": evidence_file(args.host_config),
            "weights_contract": evidence_file(weights_path_raw),
            "scoring_config": evidence_file(scoring_path_raw),
            "overlay_contract": evidence_file(_clean(overlay_cfg.get("contract_path"))) if overlay_enabled else {
                "path": "", "exists": False, "sha256": ""
            },
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(
        Path(output_files["frontier_contract_readback"]),
        {
            "contract_version": "project_governance_frontier_contract_readback.v1",
            "run_id": run_id,
            "contract_evidence": contract_evidence,
            "checks": checks,
            "blockers": blockers,
        },
    )
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    ev = dict(summary.get("contract_evidence") or {})
    lines = [
        "# Frontier Contract Governance Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "Binds the live frozen-frontier CONTRACT state into governance READY: the weight / "
        "scoring / overlay contracts are sha-pinned and match the on-disk files, the frozen "
        "vector is the 12-factor frontier and is CARRY-FORWARD-FREE, and the overlay (if "
        "enabled) is pinned with PIT thresholds. Proof-only: no mutation, no enable flip, no "
        "runtime enablement.",
        "",
        "## Validation",
        "",
        "```text",
        f"frontier_contract_governance_gate_ready = {str(bool(summary['frontier_contract_governance_gate_ready'])).lower()}",
        f"carry_forward_absent = {str(bool(summary['carry_forward_absent'])).lower()}",
        f"frontier_enabled_in_config = {str(bool(summary['frontier_enabled_in_config'])).lower()}",
        f"overlay_enabled_in_config = {str(bool(summary['overlay_enabled_in_config'])).lower()}",
        f"weights_feature_count = {ev.get('weights_feature_count')}",
        f"weights_strategy_id = {ev.get('weights_strategy_id')}",
        "frontier_enable_flip_performed = false",
        "host_config_mutation_performed = false",
        "orders_submitted = 0",
        "```",
        "",
        "## Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        f"allowed_next_gate_must_be_separately_requested = {str(bool(summary['allowed_next_gate_must_be_separately_requested'])).lower()}",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_frontier_contract_governance_gate(parse_args(argv))
    print(
        "frontier_contract_governance_gate_ready="
        + str(bool(summary["frontier_contract_governance_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"carry_forward_absent={str(bool(summary['carry_forward_absent'])).lower()}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
