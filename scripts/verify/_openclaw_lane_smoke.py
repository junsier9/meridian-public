from __future__ import annotations

from scripts.verify._openclaw_continue_existing_live import run_continue_existing_recorded_gate
from scripts.verify._openclaw_continue_existing_support import lane_config


def run_lane_smoke(*, lane_id: str, wsl_smoke: str | None = None) -> int:
    del wsl_smoke
    return run_continue_existing_recorded_gate(lane_config(lane_id))
