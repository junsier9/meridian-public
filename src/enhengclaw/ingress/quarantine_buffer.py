from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from enhengclaw.ingress.schema_validator import AgentIngressContext
from enhengclaw.utils.subject_keys import subject_key_path


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    input_id: str
    path: str
    reason: str


class QuarantineBuffer:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "agent_ingress" / "quarantine"
        )

    def write(
        self,
        *,
        context: AgentIngressContext,
        input_id: str,
        payload: Any,
        reason: str,
    ) -> QuarantineRecord:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_name = f"{stamp}_{self._safe_fragment(input_id)}.json"
        path = subject_key_path(self.root, context.scenario, context.subject_key, file_name)
        self._ensure_directory(path.parent)
        self._write_json(
            path,
            {
                "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "context": {
                    "object_id": context.object_id,
                    "object_type": context.object_type.value,
                    "subject": context.subject,
                    "scope": context.scope,
                    "scenario": context.scenario,
                    "subject_key": context.subject_key.as_path_fragment(),
                },
                "input_id": input_id,
                "reason": reason,
                "payload": payload,
            },
        )
        return QuarantineRecord(input_id=input_id, path=str(path), reason=reason)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        with open(self._io_path(path), "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
            )

    def _ensure_directory(self, path: Path) -> None:
        os.makedirs(self._io_path(path), exist_ok=True)

    def _io_path(self, path: Path) -> str:
        text = str(path)
        if os.name != "nt" or len(text) < 240:
            return text
        if text.startswith("\\\\?\\"):
            return text
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text[2:]
        return "\\\\?\\" + text

    def _safe_fragment(self, value: str) -> str:
        fragment = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        return fragment or "unknown"
