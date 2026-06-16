from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhengclaw.quant_research.contracts import read_json


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE_CONFIG_PATH = ROOT / "config" / "live_trading" / "hv_balanced_binance_usdm.yaml"
DEFAULT_FROZEN_CONFIG_PATH = (
    ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"
)
LIVE_MODES = frozenset({"plan_only", "paper", "testnet", "live"})


@dataclass(frozen=True, slots=True)
class LiveTradingConfig:
    path: Path
    payload: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        value = self.payload.get(name)
        return dict(value) if isinstance(value, dict) else {}

    @property
    def strategy_config_path(self) -> Path:
        strategy = self.section("strategy")
        raw = str(strategy.get("frozen_config_path") or DEFAULT_FROZEN_CONFIG_PATH).strip()
        return resolve_repo_path(raw)

    @property
    def artifact_root(self) -> Path:
        state = self.section("state")
        raw = str(state.get("artifact_root") or "artifacts/live_trading/hv_balanced_binance_usdm/runs")
        return resolve_repo_path(raw)

    @property
    def sqlite_path(self) -> Path:
        state = self.section("state")
        raw = str(state.get("sqlite_path") or "artifacts/live_trading/hv_balanced_binance_usdm/state/live_trading.sqlite3")
        return resolve_repo_path(raw)


def resolve_repo_path(path_ref: str | Path) -> Path:
    candidate = Path(path_ref).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def load_live_trading_config(path: str | Path = DEFAULT_LIVE_CONFIG_PATH) -> LiveTradingConfig:
    resolved = resolve_repo_path(path)
    payload = _read_config_payload(resolved)
    return LiveTradingConfig(path=resolved, payload=payload)


def load_frozen_strategy_config(path: str | Path) -> dict[str, Any]:
    return dict(read_json(resolve_repo_path(path)))


def _read_config_payload(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return dict(read_json(path))
    return _parse_simple_yaml(path.read_text(encoding="utf-8-sig"))


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    lines: list[tuple[str, int, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        lines.append((raw_line, indent, stripped))

    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]
    for idx, (raw_line, indent, stripped) in enumerate(lines):
        if stripped.startswith("- "):
            while stack and indent <= stack[-1][0]:
                stack.pop()
            if not stack or not isinstance(stack[-1][1], list):
                raise ValueError(f"unsupported YAML list line: {raw_line!r}")
            stack[-1][1].append(_parse_scalar(stripped[2:].strip()))
            continue
        if ":" not in stripped:
            raise ValueError(f"unsupported YAML line: {raw_line!r}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"invalid YAML indentation near: {raw_line!r}")
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            raise ValueError(f"unsupported YAML nested mapping in list near: {raw_line!r}")
        if not value:
            next_stripped = lines[idx + 1][2] if idx + 1 < len(lines) else ""
            child: dict[str, Any] | list[Any] = [] if next_stripped.startswith("- ") else {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str) -> Any:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if (normalized.startswith('"') and normalized.endswith('"')) or (
        normalized.startswith("'") and normalized.endswith("'")
    ):
        return normalized[1:-1]
    try:
        if any(char in normalized for char in (".", "e", "E")):
            return float(normalized)
        return int(normalized)
    except ValueError:
        return normalized
