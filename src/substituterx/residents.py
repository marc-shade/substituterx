"""Resident profile store. Synthetic data only (SPEC §2.3 — no PHI)."""
from __future__ import annotations

import json
from pathlib import Path

from .models import ResidentContextVector


SEED_PATH = Path(__file__).parent.parent.parent / "data" / "seed_residents.json"


class ResidentStore:
    def __init__(self, seed_path: Path | None = None) -> None:
        data = json.loads((seed_path or SEED_PATH).read_text())
        self._by_id = {r["resident_id"]: r for r in data["residents"]}

    def get(self, resident_id: str) -> ResidentContextVector | None:
        raw = self._by_id.get(resident_id)
        if not raw:
            return None
        return ResidentContextVector(**raw)

    def all_ids(self) -> list[str]:
        return sorted(self._by_id.keys())
