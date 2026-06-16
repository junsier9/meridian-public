from __future__ import annotations

from typing import Any

from .fixed_set_comparison import pairwise_lookup


ALPHA_EXPERIMENT_CARD_CONTRACT_VERSION = "quant_alpha_experiment_card.v1"
CANONICAL_PARENT_LABEL = "v5_rw_bridge_no_overlay_h10d"
LEGACY_COMPARATOR_LABEL = "v6_h10d"
REQUIRED_STATISTICAL_FALSIFICATION_TESTS = {
    "symbol_holdout": "symbol_holdout_failed",
    "delayed_execution": "delay_stress_failed",
    "cost_stress": "cost_stress_failed",
    "liquidity_bucket_consistency": "liquidity_bucket_consistency_failed",
}
NOT_MEASURED_FAIL_CLOSED = "not_measured_fail_closed"


def build_alpha_experiment_card(
    *,
    experiment_id: str,
    strategy_id: str,
    fixed_set_comparison: dict[str, Any] | None,
    statistical_falsification: dict[str, Any] | None,
    overlay_ablation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixed_set = dict(fixed_set_comparison or {})
    falsification = dict(statistical_falsification or {})
    promotion_gate = dict(fixed_set.get("promotion_gate") or {})
    candidate_label = str(fixed_set.get("candidate_label") or strategy_id or experiment_id).strip()
    pairwise_results = list(fixed_set.get("pairwise_results") or [])
    canonical_parent_pairwise = pairwise_lookup(
        pairwise_results=pairwise_results,
        candidate_a=candidate_label,
        candidate_b=CANONICAL_PARENT_LABEL,
    )
    legacy_pairwise = pairwise_lookup(
        pairwise_results=pairwise_results,
        candidate_a=candidate_label,
        candidate_b=LEGACY_COMPARATOR_LABEL,
    )
    legacy_only_effective = bool(
        legacy_pairwise
        and float(legacy_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0) > 0.0
        and (
            canonical_parent_pairwise is None
            or float(canonical_parent_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0) <= 0.0
        )
    )
    falsification_test_states = {
        test_name: _falsification_test_state(falsification=falsification, test_name=test_name)
        for test_name in REQUIRED_STATISTICAL_FALSIFICATION_TESTS
    }
    symbol_holdout_passed = bool(falsification_test_states["symbol_holdout"]["passed"])
    delay_stress_passed = bool(falsification_test_states["delayed_execution"]["passed"])
    cost_stress_passed = bool(falsification_test_states["cost_stress"]["passed"])
    liquidity_bucket_consistency_passed = bool(
        falsification_test_states["liquidity_bucket_consistency"]["passed"]
    )
    fixed_set_fields_complete = (
        fixed_set.get("status") == "computed"
        and bool(fixed_set.get("artifact_paths"))
        and bool(promotion_gate)
    )
    overlay_ablation_required = _overlay_ablation_required(candidate_label=candidate_label, strategy_id=strategy_id)
    promotion_gate_fields_complete = fixed_set_fields_complete and (
        bool(overlay_ablation) or not overlay_ablation_required
    )
    blocker_codes: list[str] = []
    if legacy_only_effective:
        blocker_codes.append("legacy_only_effective")
    for test_name, state in falsification_test_states.items():
        if state["status"] == NOT_MEASURED_FAIL_CLOSED:
            blocker_codes.append(f"{test_name}_{NOT_MEASURED_FAIL_CLOSED}")
        elif not bool(state["passed"]):
            blocker_codes.append(REQUIRED_STATISTICAL_FALSIFICATION_TESTS[test_name])
    if not bool(promotion_gate.get("passed")):
        blocker_codes.extend(
            str(item).strip()
            for item in list(promotion_gate.get("blocker_codes") or [])
            if str(item).strip()
        )
    if not promotion_gate_fields_complete:
        blocker_codes.append("promotion_gate_fields_incomplete")
    go_no_go = not blocker_codes
    return {
        "contract_version": ALPHA_EXPERIMENT_CARD_CONTRACT_VERSION,
        "experiment_id": str(experiment_id),
        "strategy_id": str(strategy_id),
        "candidate_label": candidate_label,
        "legacy_only_effective": legacy_only_effective,
        "symbol_holdout_passed": symbol_holdout_passed,
        "delay_stress_passed": delay_stress_passed,
        "cost_stress_passed": cost_stress_passed,
        "liquidity_bucket_consistency_passed": liquidity_bucket_consistency_passed,
        "statistical_falsification_applicable": _falsification_applicable(falsification),
        "statistical_falsification_reason": str(falsification.get("reason") or ""),
        "statistical_falsification_test_states": falsification_test_states,
        "statistical_falsification_missing_tests": [
            test_name
            for test_name, state in falsification_test_states.items()
            if state["status"] == NOT_MEASURED_FAIL_CLOSED
        ],
        "promotion_gate_fields_complete": promotion_gate_fields_complete,
        "go_no_go": go_no_go,
        "status": "go" if go_no_go else "no_go",
        "blocker_codes": sorted(set(blocker_codes)),
        "canonical_parent_pairwise": canonical_parent_pairwise,
        "legacy_pairwise": legacy_pairwise,
        "promotion_gate": promotion_gate,
        "statistical_falsification_status": str(falsification.get("status") or ""),
        "overlay_ablation_present": bool(overlay_ablation),
        "overlay_ablation_required": overlay_ablation_required,
    }


def _overlay_ablation_required(*, candidate_label: str, strategy_id: str) -> bool:
    identifier = f"{candidate_label} {strategy_id}".lower()
    return "no_overlay" not in identifier


def _falsification_applicable(falsification: dict[str, Any]) -> bool | None:
    if "applicable" in falsification:
        return bool(falsification.get("applicable"))
    return None if not falsification else True


def _falsification_test_state(
    *,
    falsification: dict[str, Any],
    test_name: str,
) -> dict[str, Any]:
    tests = dict(falsification.get("tests") or {})
    if test_name not in tests:
        return {
            "passed": False,
            "status": NOT_MEASURED_FAIL_CLOSED,
            "reason": str(falsification.get("reason") or "test_missing"),
        }
    payload = dict(tests.get(test_name) or {})
    passed = bool(payload.get("passed"))
    return {
        "passed": passed,
        "status": "passed" if passed else "failed",
        "reason": str(payload.get("reason") or ""),
    }
