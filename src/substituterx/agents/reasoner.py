"""Reasoner agent (SPEC §6.1).

Takes the bottle label + MAR entry text and proposes structured claims about whether
they are equivalent, plus the substitution mechanism. The LLM extracts structure;
it does NOT make the substitution decision — the validator does, against the KG.
"""
from __future__ import annotations

from collections import Counter

from ..audit_log import AuditLog
from ..models import (
    BottleLabel, MAREntry, ReasonerClaims, Mechanism, Claim,
)
from ..provider import LLMProvider


SYSTEM = """You are the Reasoner agent in a four-agent medication-reconciliation pipeline.

Your job: given a bottle label and a MAR entry, propose STRUCTURED CLAIMS about whether
the bottle drug and the MAR drug refer to the same medication, and by what mechanism
(generic substitution, therapeutic interchange, or discrepancy).

You do NOT decide if the substitution is safe. You ONLY extract structured claims.
A separate Validator agent will check each claim against an authoritative drug graph.

Rules:
- Be conservative. If you cannot confidently resolve an RxCUI, set it to null and let the validator search.
- Identify the substitution mechanism honestly: generic | therapeutic_interchange | discrepancy | unknown.
- For each claim, write an `evidence_request` describing what the validator must verify
  (e.g., "verify atorvastatin SCD 617318 is generic of Lipitor SBD 617314 with TE code A*").
- Confidence must reflect your structural certainty, not medical judgment.
"""

SCHEMA = """{
  "equivalent": true | false | null,
  "mechanism": "generic" | "therapeutic_interchange" | "discrepancy" | "unknown",
  "structured_claims": [
    {
      "subject_rxcui": "string-or-null",
      "predicate": "is_generic_of | is_therapeutic_alt_of | is_same_drug_as | nti_pair_unsafe | unknown",
      "object_rxcui": "string-or-null",
      "object_str": "string-or-null",
      "rationale": "...",
      "evidence_request": "..."
    }
  ],
  "confidence": 0.0
}"""


class ReasonerAgent:
    def __init__(self, provider: LLMProvider, audit: AuditLog) -> None:
        self.provider = provider
        self.audit = audit

    def propose(
        self, run_id: str, bottle: BottleLabel, mar: MAREntry,
    ) -> tuple[ReasonerClaims, dict]:
        user = (
            f"Bottle label: {bottle.label_text!r}\n"
            f"Bottle NDC: {bottle.ndc or 'unknown'}\n"
            f"Bottle RxCUI hint: {bottle.rxcui or 'unknown'}\n\n"
            f"MAR label: {mar.label_text!r}\n"
            f"MAR RxCUI hint: {mar.rxcui or 'unknown'}\n\n"
            "Propose structured claims and the substitution mechanism."
        )
        # The reasoner's job is structural extraction. Both the LLM call and the
        # downstream Pydantic parsing can fail (network, schema mismatch, garbage
        # JSON). Falling back to empty claims is the *safe* path: the orchestrator's
        # `augment_claim` step adds a bottle↔MAR claim from the KG-resolved RxCUIs,
        # the validator runs against that, and the safety widenings still fire. A
        # raised exception would 500 the API instead — heavier than necessary.
        try:
            parsed, result = self.provider.call_json(SYSTEM, user, SCHEMA, max_tokens=800)
            claims = ReasonerClaims(
                equivalent=parsed.get("equivalent"),
                mechanism=Mechanism(parsed.get("mechanism", "unknown")),
                structured_claims=[Claim(**c) for c in parsed.get("structured_claims", [])],
                confidence=float(parsed.get("confidence", 0.0)),
            )
            meta = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                    "model": result.model, "cost_usd": result.cost_usd}
        except Exception as exc:
            claims = ReasonerClaims(
                equivalent=None, mechanism=Mechanism.UNKNOWN,
                structured_claims=[], confidence=0.0,
            )
            meta = {"error": str(exc), "model": getattr(self.provider, "model", "?"),
                    "cost_usd": 0.0}
        # Predicate distribution per run — surfaces Trendslop-style pull on which
        # relation the LLM proposes (Romasanta et al., HBR 2026). The orchestrator does
        # not act on this; it's an audit-trail signal for offline drift detection.
        meta["predicate_distribution"] = dict(
            Counter(c.predicate for c in claims.structured_claims)
        )
        self.audit.emit(run_id, "reasoner", "propose", {
            "bottle": bottle.model_dump(), "mar": mar.model_dump(),
            "claims": claims.model_dump(), **meta,
        })
        return claims, meta
