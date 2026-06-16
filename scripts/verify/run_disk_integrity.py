from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    failures: list[str] = []
    targets = list((ROOT / "src").rglob("*.py")) + list((ROOT / "config").rglob("*.json"))
    for path in sorted(targets):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            failures.append(f"{path}: unable to read ({exc})")
            continue
        if b"\x00" in raw:
            failures.append(f"{path}: contains NUL byte(s)")
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            failures.append(f"{path}: UTF-8 decode failed ({exc})")
    if failures:
        for failure in failures:
            print(f"[disk-integrity] FAIL {failure}")
        return 1
    print("[disk-integrity] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
