from __future__ import annotations


EXPERIMENT_STATUS_PASS = "pass"
EXPERIMENT_STATUS_FAIL = "fail"
EXPERIMENT_STATUS_QUARANTINED = "quarantined"
EXPERIMENT_STATUS_INVALIDATED = "invalidated"
EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX = "needs_rerun_after_overlap_fix"
EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX = "pipeline_unreliable_pending_single_asset_fix"
EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN = "superseded_by_overlap_rerun"

NON_DECISIVE_EXPERIMENT_STATUSES = {
    EXPERIMENT_STATUS_INVALIDATED,
    EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
    EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
    EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN,
}


def is_pass_experiment_status(status: str | None) -> bool:
    return str(status or "").strip() == EXPERIMENT_STATUS_PASS


def is_quarantined_experiment_status(status: str | None) -> bool:
    return str(status or "").strip() == EXPERIMENT_STATUS_QUARANTINED


def is_rerun_required_experiment_status(status: str | None) -> bool:
    return str(status or "").strip() == EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX


def is_pipeline_unreliable_pending_single_asset_fix(status: str | None) -> bool:
    return str(status or "").strip() == EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX


def counts_as_daily_failure(status: str | None) -> bool:
    return str(status or "").strip() == EXPERIMENT_STATUS_FAIL


def counts_as_sandbox_accepted(status: str | None) -> bool:
    normalized = str(status or "").strip()
    return normalized not in {
        EXPERIMENT_STATUS_QUARANTINED,
        EXPERIMENT_STATUS_INVALIDATED,
        EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
        EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
        EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN,
    }
