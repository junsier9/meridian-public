from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_int(value: str) -> int:
    return int(hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8], 16)
