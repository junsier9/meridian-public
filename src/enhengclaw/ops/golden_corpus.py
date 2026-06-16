from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GoldenReplayEntry:
    category: str
    scenario: str
    file_path: Path
    category_root: Path


class GoldenReplayCorpus:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[3] / "fixtures" / "golden_corpus" / "cex"
        )

    def iter_entries(self) -> list[GoldenReplayEntry]:
        entries: list[GoldenReplayEntry] = []
        if not self.root.exists():
            return entries
        for category_dir in sorted(path for path in self.root.iterdir() if path.is_dir()):
            for scenario_dir in sorted(path for path in category_dir.iterdir() if path.is_dir()):
                file_path = scenario_dir / "cex_snapshot.json"
                if not file_path.exists():
                    continue
                entries.append(
                    GoldenReplayEntry(
                        category=category_dir.name,
                        scenario=scenario_dir.name,
                        file_path=file_path,
                        category_root=category_dir,
                    )
                )
        return entries

    def category_root(self, category: str) -> Path:
        return self.root / category
