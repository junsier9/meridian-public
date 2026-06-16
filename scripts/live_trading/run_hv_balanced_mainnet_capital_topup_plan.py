#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.mainnet_rebalance_plan_runner import main  # noqa: E402


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if "--capital-topup" not in argv:
        argv.insert(0, "--capital-topup")
    raise SystemExit(main(argv))
