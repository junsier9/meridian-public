from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.mainnet_health_monitor import (  # noqa: E402
    _auto_rearm_disarm_is_recoverable,
)


def test_budget_cycle_disarm_not_recoverable_even_if_config_omits_fragment():
    # Operator config lists fragments that do NOT include unattended_budget; the
    # force-add must still make a budget disarm terminal.
    health_cfg = {"auto_rearm_blocked_blocker_fragments": "heartbeat_residue,open_orders"}
    disarm = {"alert_codes": [], "blockers": ["unattended_budget_cycle_exhausted:6>=6"]}
    out = _auto_rearm_disarm_is_recoverable(disarm, health_cfg=health_cfg)
    assert out["status"] == "blocked_hard_disarm_reason"
    assert any("unattended_budget" in f for f in out["blocked_blocker_fragments"])


def test_budget_turnover_disarm_not_recoverable():
    disarm = {"alert_codes": [], "blockers": ["unattended_budget_turnover_exhausted:650.00>600.00"]}
    out = _auto_rearm_disarm_is_recoverable(disarm, health_cfg={})
    assert out["status"] == "blocked_hard_disarm_reason"


def test_budget_orphan_disarm_not_recoverable():
    disarm = {"alert_codes": [], "blockers": ["unattended_budget_unreconciled_prior_cycle"]}
    out = _auto_rearm_disarm_is_recoverable(disarm, health_cfg={})
    assert out["status"] == "blocked_hard_disarm_reason"


def test_no_open_epoch_disarm_not_recoverable():
    disarm = {"alert_codes": [], "blockers": ["unattended_budget_no_open_epoch"]}
    out = _auto_rearm_disarm_is_recoverable(disarm, health_cfg={})
    assert out["status"] == "blocked_hard_disarm_reason"


def test_benign_disarm_still_recoverable():
    disarm = {"alert_codes": [], "blockers": ["some_transient_recoverable_condition"]}
    out = _auto_rearm_disarm_is_recoverable(disarm, health_cfg={})
    assert out["status"] == "passed"
