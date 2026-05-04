"""Auditor agent (SPEC §6.4). The QKG paper's central guardrail.

Scans the validator's reasoning trace for parametric leakage — claims that aren't
grounded in the retrieved constraint_items. Uses a regex pass + an LLM-classifier pass.
"""
from __future__ import annotations

import re

from ..audit_log import AuditLog
from ..models import AuditFlag, AuditReport, ValidatorReport
from ..provider import LLMProvider


AUDITOR_SYSTEM = """You are the Auditor agent. You will see the validator's reasoning trace
and the list of constraint_items it evaluated. Each constraint_item carries:
  - `key`: the constraint type (e.g. te_code_required, ingredient_match, egfr_threshold)
  - `value`: the constraint value, which MAY be a glob/pattern (e.g. "A*") or a list
  - `matched_literal`: the concrete value from the resident or drug that satisfied the pattern
    (e.g. for value="A*" against TE code "AB", matched_literal="AB")

Your job: detect PARAMETRIC LEAKAGE — claims that introduce numbers, named entities, or
clinical facts that have NO basis in any constraint_item.

Recognize these as GROUNDED, not leakage:
  - Glob expansions of pattern values. value="A*" supports narration mentioning AA, AB,
    AB1, AB2, AB3, AB4, AN, AO, AP, AT, "A-rated", "A-prefixed", "FDA A-rated".
  - Paraphrase of `matched_literal` (the validator may say "TE code AB" if matched_literal is "AB").
  - Paraphrase of constraint key/value pairs (e.g. validator may write "ingredients match"
    when ingredient_match is supported with the actual ingredient name).
  - Restating threshold comparisons (e.g. "eGFR 48 ≥ 30 threshold" if egfr_threshold=30 and
    matched_literal=48).

Flag ONLY when the validator references a number, drug name, condition, threshold, or
mechanism that has NO support in any constraint_item's value, key, or matched_literal.

Output JSON only:
{
  "leakage_detected": true|false,
  "downgraded_edge_ids": ["E001", ...],
  "flags": [{"edge_id":"...","reason":"unsourced_threshold|unsourced_entity|classifier_judged_parametric","detail":"..."}]
}
"""

# Number pattern: any standalone number including thresholds like 30, 0.1, 65, etc.
NUM_RE = re.compile(r"\b\d+(\.\d+)?\b")

# Ethos / effort-transparency boilerplate that LLMs use to assert credibility without
# evidence. Catalogued from Randazzo et al. 2025, Table 1 ("GenAI's Use of Ethos Tactics").
# Patterns are intentionally narrow (anchored on the giveaway adjective + verb) to avoid
# false positives on legitimate analytical phrasing like "the analysis shows…".
ETHOS_PHRASES = [
    re.compile(r"\bafter\s+(?:a\s+)?thorough\s+(?:analysis|review|evaluation|examination)\b", re.I),
    re.compile(r"\bafter\s+(?:a\s+)?careful\s+(?:analysis|review|evaluation|examination)\b", re.I),
    re.compile(r"\bupon\s+closer\s+(?:examination|inspection|review)\b", re.I),
    re.compile(r"\brigorous\s+(?:analysis|review|evaluation)\s+(?:shows|confirms|indicates)\b", re.I),
    re.compile(r"\bi\s+have\s+(?:verified|confirmed|carefully\s+reviewed)\b", re.I),
    re.compile(r"\bi\s+apologi[sz]e\s+for\b", re.I),
    re.compile(r"\bcareful\s+evaluation\s+(?:shows|confirms|indicates)\b", re.I),
    re.compile(r"\byou\s+are\s+(?:absolutely\s+)?correct\b", re.I),
    re.compile(r"\byour\s+point\s+is\s+(?:valid|well\s+taken)\b", re.I),
    re.compile(r"\bindeed,?\s+as\s+you\s+(?:noted|mentioned|pointed\s+out)\b", re.I),
]


class AuditorAgent:
    def __init__(self, provider: LLMProvider, audit: AuditLog) -> None:
        self.provider = provider
        self.audit = audit

    def review(self, run_id: str, validator_report: ValidatorReport) -> tuple[AuditReport, dict]:
        # ---- Pass 1: regex — every number in reasoning must appear in some constraint_item.
        regex_flags: list[AuditFlag] = []
        for v in validator_report.edge_verdicts:
            allowed = set()
            ci_reasoning_blob = ""
            for ci in v.constraint_items_evaluated:
                allowed.update(NUM_RE.findall(str(ci.get("value", ""))))
                allowed.update(NUM_RE.findall(str(ci.get("reasoning", ""))))
                ci_reasoning_blob += " " + str(ci.get("reasoning", ""))
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

            # Stylistic-ethos pre-pass: catch credibility-asserting boilerplate that isn't
            # echoed by any constraint_item.reasoning. (If the validator says "I have verified"
            # AND the constraint_item.reasoning literally narrates the verification, allow it.)
            for pat in ETHOS_PHRASES:
                m = pat.search(v.reasoning)
                if not m:
                    continue
                phrase = m.group(0)
                if pat.search(ci_reasoning_blob):
                    # The same effort claim appears in a constraint_item; grounded.
                    continue
                regex_flags.append(AuditFlag(
                    edge_id=v.edge_id,
                    reason="unsourced_ethos_phrase",
                    detail=f"credibility/effort phrase {phrase!r} not anchored in any constraint_item",
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
