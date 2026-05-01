"""Context Extractor (SPEC §6.2). Pure data lookup. No LLM call."""
from __future__ import annotations

from ..audit_log import AuditLog
from ..models import ResidentContextVector
from ..residents import ResidentStore


class ContextExtractorAgent:
    def __init__(self, store: ResidentStore, audit: AuditLog) -> None:
        self.store = store
        self.audit = audit

    def extract(self, run_id: str, resident_id: str) -> ResidentContextVector | None:
        ctx = self.store.get(resident_id)
        self.audit.emit(run_id, "context_extractor", "extract", {
            "resident_id": resident_id,
            "found": ctx is not None,
            "context": ctx.model_dump() if ctx else None,
        })
        return ctx
