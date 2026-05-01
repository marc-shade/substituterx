"""Auditor agent (SPEC §6.4). The QKG paper's central guardrail.

Scans the validator's reasoning trace for parametric leakage — claims that aren't
grounded in the retrieved constraint_items. Uses a regex pass + an LLM-classifier pass.
"""
from __future__ import annotations

import re

from ..audit_log import AuditLog
from ..models import AuditFlag, AuditReport, ValidatorReport
from ..provider import AnthropicProvider


AUDITOR_SYSTEM = """You are the Auditor agent. You will see the validator's reasoning trace
and the list of constraint_items the validator was supposed to evaluate.

Your job: detect PARAMETRIC LEAKAGE — claims in the validator's reasoning that are
NOT supported by the listed constraint_items. The validator must cite only what it
retrieved; if it invokes outside medical knowledge, flag the edge.

Be strict. If a numeric threshold or a clinical fact appears in the validator's reasoning
but does not appear in any constraint_item for that edge, the edge is leaked.

Output JSON only:
{
  "leakage_detected": true|false,
  "downgraded_edge_ids": ["E001", ...],
  "flags": [{"edge_id":"...","reason":"unsourced_threshold|unsourced_entity|classifier_judged_parametric","detail":"..."}]
}
"""

# Number pattern: any standalone number including thresholds like 30, 0.1, 65, etc.
NUM_RE = re.compile(r"\b\d+(\.\d+)?\b")


class AuditorAgent:
    def __init__(self, provider: AnthropicProvider, audit: AuditLog) -> None:
        self.provider = provider
        self.audit = audit

    def review(self, run_id: str, validator_report: ValidatorReport) -> tuple[AuditReport, dict]:
        # ---- Pass 1: regex — every number in reasoning must appear in some constraint_item.
        regex_flags: list[AuditFlag] = []
        for v in validator_report.edge_verdicts:
            allowed = set()
            for ci in v.constraint_items_evaluated:
                allowed.update(NUM_RE.findall(str(ci.get("value", ""))))
                allowed.update(NUM_RE.findall(str(ci.get("reasoning", ""))))
            for num in NUM_RE.findall(v.reasoning):
                # Numbers in citations are fine (e.g., RxCUI). Skip identifiers.
                if num in allowed:
                    continue
                # Allow trivial numbers (1, 2) and well-known IDs that appear in citations.
                if any(num in c.identifier for c in v.citations):
                    continue
                if num in {"1", "2"}:
                    continue
                regex_flags.append(AuditFlag(
                    edge_id=v.edge_id,
                    reason="unsourced_threshold",
                    detail=f"number {num} appears in validator reasoning but not in any constraint_item",
                ))

        # ---- Pass 2: LLM classifier
        if validator_report.edge_verdicts:
            user = "\n\n".join(
                f"Edge {v.edge_id} ({v.relation})\n"
                f"constraint_items: {v.constraint_items_evaluated}\n"
                f"validator reasoning: {v.reasoning}"
                for v in validator_report.edge_verdicts
            )
            try:
                parsed, result = self.provider.call_json(
                    AUDITOR_SYSTEM, user,
                    schema_hint='{"leakage_detected":bool,"downgraded_edge_ids":["..."],"flags":[{"edge_id":"...","reason":"...","detail":"..."}]}',
                    max_tokens=600,
                )
                meta = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd, "model": result.model}
                llm_flags = [AuditFlag(**f) for f in parsed.get("flags", [])]
                downgraded = list(set(parsed.get("downgraded_edge_ids", []) +
                                      [f.edge_id for f in regex_flags]))
            except Exception as exc:
                meta = {"error": str(exc), "cost_usd": 0.0}
                llm_flags = []
                downgraded = list({f.edge_id for f in regex_flags})
        else:
            meta = {"cost_usd": 0.0}
            llm_flags = []
            downgraded = []

        report = AuditReport(
            leakage_detected=bool(downgraded),
            downgraded_edge_ids=downgraded,
            flags=regex_flags + llm_flags,
        )
        self.audit.emit(run_id, "auditor", "review", {
            "report": report.model_dump(), **meta,
        })
        return report, meta
