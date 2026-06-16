from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    runpy.run_module(
        "scripts.quant_research.h10d_current_diagnostics.compute_multi_horizon_factor_audit",
        run_name="__main__",
    )
