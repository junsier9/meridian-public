from __future__ import annotations

import compileall
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify"


def main() -> int:
    if not compileall.compile_dir(str(ROOT / "src"), quiet=1):
        print("[local-integrity] FAIL compileall src")
        return 1
    print("[local-integrity] PASS compileall src")

    json_paths: set[Path] = set((ROOT / "config").rglob("*.json"))
    quant_root = ROOT / "artifacts" / "quant_research"
    if quant_root.exists():
        json_paths.update(quant_root.rglob("*.json"))
    for path in sorted(json_paths):
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            print(f"[local-integrity] FAIL json parse {path}: {exc}")
            return 1
    print("[local-integrity] PASS json parse")

    for command in (
        [sys.executable, str(VERIFY / "run_disk_integrity.py")],
        [sys.executable, str(VERIFY / "run_quant_h10d_promotion_guard.py")],
        [sys.executable, str(VERIFY / "run_bridge_summary_contract_check.py")],
    ):
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print("[local-integrity] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
