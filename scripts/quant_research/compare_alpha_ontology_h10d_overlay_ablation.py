from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.historical_h10d_diagnostics.compare_alpha_ontology_h10d_overlay_ablation import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
