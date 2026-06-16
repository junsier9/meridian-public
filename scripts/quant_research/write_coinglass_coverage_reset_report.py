from __future__ import annotations

from importlib import import_module
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_IMPL = import_module("scripts.quant_research.coinglass_diagnostics.write_coinglass_coverage_reset_report")
globals().update(
    {
        name: getattr(_IMPL, name)
        for name in dir(_IMPL)
        if not (name.startswith("__") and name.endswith("__"))
    }
)


if __name__ == "__main__":
    raise SystemExit(_IMPL.main())
