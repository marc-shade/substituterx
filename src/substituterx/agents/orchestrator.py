"""Orchestrator: wires Reasoner → ContextExtractor → Validator → Auditor → revise.

Per SPEC §6.5: if any nti_pair_unsafe / requires_prescriber_notice edge fires, OR the
auditor downgrades >30% of claims, OR resident context is missing, the system ABSTAINS
with a 'Call the pharmacy' rationale. This is the asymmetric guardrail.
"""
from __future__ import annotations

import time

from ..audit_log import AuditLog
from ..kg import KGStore
from ..models import (
    BottleLabel, MAREntry, Claim, ExplainResponse, Mechanism, AuditReport, EdgeVerdict,
    new_run_id,
)
from ..provider import AnthropicProvider
from ..residents import ResidentStore
from .auditor import AuditorAgent
from .extractor import ContextExtractorAgent
from .reasoner import ReasonerAgent
from .validator import ValidatorAgent


DATA_VERSIONS = {"rxnorm": "2026-04-curated", "orange_book": "2026-04-curated", "primekg": "v2.1-curated"}


def _resolve_rxcui(label: BottleLabel | MAREntry, kg: KGStore) -> str | None:
    if label.rxcui:
        return label.rxcui
    found = kg.find_by_name(label.label_text)
    return found.rxcui if found else None


class Orchestrator:
    def __init__(
        self,
        kg: KGStore,
        residents: ResidentStore,
        provider: AnthropicProvider,
        audit: AuditLog,
    ) -> None:
        self.kg = kg
        self.residents = residents
        self.audit = audit
        self.reasoner = ReasonerAgent(provider, audit)
        self.extractor = ContextExtractorAgent(residents, audit)
        self.validator = ValidatorAgent(kg, provider, audit)
        self.auditor = AuditorAgent(provider, audit)

    def explain(self, bottle: BottleLabel, mar: MAREntry, resident_id: str) -> ExplainResponse:
        run_id = new_run_id()
        t0 = time.time()
        total_cost = 0.0

        self.audit.emit(run_id, "orchestrator", "begin", {
            "bottle": bottle.model_dump(), "mar": mar.model_dump(), "resident_id": resident_id,
        })

        # ---- Resolve RxCUIs from labels via local KG (production: RxNav approximateTerm fallback).
        bottle.rxcui = bottle.rxcui or _resolve_rxcui(bottle, self.kg)
        mar.rxcui = mar.rxcui or _resolve_rxcui(mar, self.kg)

        # ---- Context Extractor
        ctx = self.extractor.extract(run_id, resident_id)
        if ctx is None:
            return self._abstain(run_id, t0, total_cost,
                                 "resident context not found",
                                 "Resident profile is unavailable; cannot reason about safety.")

        # ---- Reasoner
        claims, m1 = self.reasoner.propose(run_id, bottle, mar)
        total_cost += m1.get("cost_usd", 0.0)

        # ---- Augment with KG-resolved RxCUIs if reasoner produced none.
        # This is the deterministic safety net — the validator must always have
        # at least one concrete (subject, object) pair to query, so the abstain
        # path triggers correctly when no edges exist.
        has_resolved = any(c.subject_rxcui and (c.object_rxcui or c.object_str)
                           for c in claims.structured_claims)
        if not has_resolved and bottle.rxcui and mar.rxcui:
            claims.structured_claims.append(Claim(
                subject_rxcui=bottle.rxcui,
                predicate="unknown",
                object_rxcui=mar.rxcui,
                object_str=None,
                rationale="KG-resolved fallback: bottle and MAR RxCUIs identified by name match.",
                evidence_request=f"verify any relation between {bottle.rxcui} and {mar.rxcui}",
            ))
            self.audit.emit(run_id, "orchestrator", "augment_claim", {
                "subject": bottle.rxcui, "object": mar.rxcui,
            })

        # ---- Validator
        validator_report, m2 = self.validator.validate(run_id, claims.structured_claims, ctx)
        total_cost += m2.get("cost_usd", 0.0)

        # ---- Auditor
        audit_report, m3 = self.auditor.review(run_id, validator_report)
        total_cost += m3.get("cost_usd", 0.0)

        # ---- Filter downgraded edges
        active_verdicts = [v for v in validator_report.edge_verdicts
                           if v.edge_id not in audit_report.downgraded_edge_ids]

        # ---- Decide
        verdict, mechanism, explanation, abstain_reason = self._decide(
            claims, active_verdicts, audit_report, ctx,
        )

        latency_ms = int((time.time() - t0) * 1000)
        response = ExplainResponse(
            run_id=run_id,
            verdict=verdict,
            mechanism=mechanism,
            explanation=explanation,
            candidates=[],
            edge_verdicts=active_verdicts,
            audit_flags=audit_report,
            abstain_reason=abstain_reason,
            data_versions=DATA_VERSIONS,
            latency_ms=latency_ms,
            cost_usd=round(total_cost, 6),
        )
        self.audit.emit(run_id, "orchestrator", "complete", {
            "response": response.model_dump(), "latency_ms": latency_ms, "cost_usd": total_cost,
        })
        return response

    # ---------- decision logic (SPEC §6.5) ----------

    def _decide(self, claims, active_verdicts: list[EdgeVerdict], audit: AuditReport, ctx):
        # Hard guardrails: any contradicted nti_pair_unsafe or contraindicated_with_allergy
        # or requires_prescriber_notice → abstain.
        red_flag_relations = {"nti_pair_unsafe", "contraindicated_with_allergy",
                              "requires_prescriber_notice"}
        red_flags = [v for v in active_verdicts
                     if v.relation in red_flag_relations and v.status == "contradicted"]

        if red_flags:
            reasons = "; ".join(f"{v.relation}({v.subject}→{v.object}): {v.reasoning}"
                                for v in red_flags)
            return "abstain", Mechanism.DISCREPANCY, \
                   f"Red-flag edge fired. {reasons}. **Call the pharmacy.**", \
                   reasons

        # Auditor downgrade ratio
        total = len(active_verdicts) + len(audit.downgraded_edge_ids)
        if total and len(audit.downgraded_edge_ids) / total > 0.30:
            return "abstain", Mechanism.UNKNOWN, \
                   "More than 30% of validator claims were downgraded for parametric leakage. **Call the pharmacy.**", \
                   "auditor_downgrade_threshold_exceeded"

        # No active edges at all → can't claim equivalence
        if not active_verdicts:
            return "abstain", Mechanism.UNKNOWN, \
                   "No knowledge-graph edges link these two drugs. **Call the pharmacy.**", \
                   "no_kg_evidence"

        # Look for is_generic_of supported
        generic_supported = [v for v in active_verdicts
                             if v.relation == "is_generic_of" and v.status == "supported"]
        if generic_supported:
            edge = generic_supported[0]
            return "equivalent", Mechanism.GENERIC, \
                   f"These are AB-rated generic equivalents. {edge.reasoning}", None

        same_drug = [v for v in active_verdicts
                     if v.relation == "is_same_drug_as" and v.status == "supported"]
        if same_drug:
            return "equivalent", Mechanism.GENERIC, "These refer to the same drug.", None

        # Therapeutic interchange — always abstain (caregiver scope)
        therapeutic = [v for v in active_verdicts if v.relation == "is_therapeutic_alt_of"]
        if therapeutic:
            return "abstain", Mechanism.THERAPEUTIC_INTERCHANGE, \
                   "These are therapeutic alternatives, not generic equivalents. Substitution requires the prescriber. **Call the pharmacy.**", \
                   "therapeutic_interchange_requires_prescriber"

        return "abstain", Mechanism.UNKNOWN, \
               "Equivalence cannot be confirmed from available evidence. **Call the pharmacy.**", \
               "insufficient_evidence"

    def _abstain(self, run_id: str, t0: float, cost: float, reason: str, msg: str) -> ExplainResponse:
        latency_ms = int((time.time() - t0) * 1000)
        resp = ExplainResponse(
            run_id=run_id,
            verdict="abstain",
            mechanism=Mechanism.UNKNOWN,
            explanation=msg,
            audit_flags=AuditReport(leakage_detected=False),
            abstain_reason=reason,
            data_versions=DATA_VERSIONS,
            latency_ms=latency_ms,
            cost_usd=round(cost, 6),
        )
        self.audit.emit(run_id, "orchestrator", "abstain_early", {"reason": reason})
        return resp
