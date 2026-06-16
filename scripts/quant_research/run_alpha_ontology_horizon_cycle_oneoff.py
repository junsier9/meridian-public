from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.alpha_ontology_cycles.run_alpha_ontology_horizon_cycle_oneoff import (  # noqa: E402
    _patch_hypothesis_batch_for_variant,
    main,
)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
