from __future__ import annotations

import hashlib
import json


def stable_hash(payload: object) -> str:
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
