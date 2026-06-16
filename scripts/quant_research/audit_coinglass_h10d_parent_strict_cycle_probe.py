from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.historical_h10d_diagnostics.audit_coinglass_h10d_parent_strict_cycle_probe import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
