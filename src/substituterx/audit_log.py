"""JSON-Lines audit log. Per SPEC §6 + §9: every agent step is captured by run_id.

The auditor reads from this; the eval harness reads from this; the demo UI reads from this.
This is the single source of truth for what happened during a run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path(os.environ.get("SUBSTITUTERX_AUDIT_LOG", "./audit_logs/audit.jsonl"))


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, run_id: str, agent: str, event: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "agent": agent,
            "event": event,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read_run(self, run_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["run_id"] == run_id:
                    out.append(rec)
        return out
