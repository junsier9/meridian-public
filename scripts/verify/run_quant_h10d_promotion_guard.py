from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.promotion import h10d_promotion_evidence_blockers


PROMOTABLE_MARKERS = {"eligible", "promotion_gate_candidate", "promotable"}
MANIFEST_ROOT = ROOT / "src" / "enhengclaw" / "quant_research"
ARTIFACT_EXPERIMENTS_ROOT = ROOT / "artifacts" / "quant_research" / "experiments"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _promotable_h10d_manifests() -> list[tuple[Path, dict[str, Any], dict[str, Any]]]:
    manifests: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for path in sorted(MANIFEST_ROOT.glob("cross_sectional_hypothesis_batch_manifest_alpha_ontology_*h10d.json")):
        payload = _read_json(path)
        promotion_eligibility = str(payload.get("promotion_eligibility") or "").strip()
        if promotion_eligibility not in PROMOTABLE_MARKERS:
            continue
        entries = [dict(item) for item in list(payload.get("entries") or []) if isinstance(item, dict)]
        if not entries:
            manifests.append((path, payload, {}))
            continue
        entry = entries[0]
        if int(entry.get("target_horizon_bars", 0) or 0) == 10:
            manifests.append((path, payload, entry))
    return manifests


def _matching_alpha_cards(strategy_id: str) -> list[Path]:
    matches: list[Path] = []
    if not ARTIFACT_EXPERIMENTS_ROOT.exists():
        return matches
    for path in sorted(ARTIFACT_EXPERIMENTS_ROOT.glob("*/alpha_card.json")):
        try:
            alpha_card = _read_json(path)
        except Exception:
            continue
        if str(alpha_card.get("strategy_id") or "").strip() == strategy_id:
            matches.append(path)
    return sorted(matches, key=lambda item: item.stat().st_mtime, reverse=True)


def main() -> int:
    blockers: list[str] = []
    checked: list[dict[str, str]] = []
    for manifest_path, manifest, entry in _promotable_h10d_manifests():
        strategy_id = str(entry.get("candidate_id") or "").strip()
        if not strategy_id:
            blockers.append(f"{manifest_path}: missing entry.candidate_id for promotable h10d manifest")
            continue
        alpha_card_paths = _matching_alpha_cards(strategy_id)
        if not alpha_card_paths:
            blockers.append(f"{manifest_path}: no alpha_card found for strategy_id={strategy_id}")
            continue
        alpha_card_path = alpha_card_paths[0]
        alpha_card = _read_json(alpha_card_path)
        evidence_blockers = h10d_promotion_evidence_blockers(
            alpha_card=alpha_card,
            strategy_entry={
                "research_lane": str(entry.get("research_lane", alpha_card.get("research_lane")) or ""),
            },
            require_applicable=True,
        )
        if evidence_blockers:
            blockers.extend(f"{manifest_path}: {blocker}" for blocker in evidence_blockers)
        checked.append(
            {
                "manifest": str(manifest_path.relative_to(ROOT)),
                "strategy_id": strategy_id,
                "alpha_card": str(alpha_card_path.relative_to(ROOT)),
                "promotion_eligibility": str(manifest.get("promotion_eligibility") or ""),
            }
        )
    payload = {
        "passed": not blockers,
        "checked_count": len(checked),
        "checked": checked,
        "blockers": blockers,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
