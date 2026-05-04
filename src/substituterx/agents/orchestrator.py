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
    BottleLabel, MAREntry, Claim, Citation, ExplainResponse, Mechanism, AuditReport,
    EdgeVerdict, new_run_id,
)
from ..residents import ResidentStore
from .auditor import AuditorAgent
from .extractor import ContextExtractorAgent
from .reasoner import ReasonerAgent
from .validator import ValidatorAgent, _aggregate, _eval_constraint


def _data_versions_from(kg: KGStore) -> dict[str, str]:
    """Read the actively-loaded seed's data_versions from the KG. Falls back to
    `unknown` markers if the seed didn't declare any (so the response field is
    never silently wrong about what's loaded)."""
    return dict(kg.data_versions) or {
        "rxnorm": "unknown", "orange_book": "unknown", "primekg": "unknown",
    }


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
        provider,  # default provider; per-agent overrides resolved here
        audit: AuditLog,
    ) -> None:
        self.kg = kg
        self.residents = residents
        self.audit = audit
        # Per-agent model selection: each agent can override via SUBSTITUTERX_MODEL_<ROLE>.
        # Falls back to the default provider if no override set.
        from ..provider import get_provider
        import os
        def _agent_provider(role: str):
            if os.environ.get(f"SUBSTITUTERX_MODEL_{role.upper()}"):
                return get_provider(role)
            return provider
        self.reasoner = ReasonerAgent(_agent_provider("reasoner"), audit)
        self.extractor = ContextExtractorAgent(residents, audit)
        self.validator = ValidatorAgent(kg, _agent_provider("validator"), audit)
        self.auditor = AuditorAgent(_agent_provider("auditor"), audit)
        # Capture the actual model assignments for the audit trail
        audit.emit("orchestrator-init", "orchestrator", "model_assignment", {
            "reasoner": getattr(self.reasoner.provider, "model", "unknown"),
            "validator": getattr(self.validator.provider, "model", "unknown"),
            "auditor": getattr(self.auditor.provider, "model", "unknown"),
        })

    def explain(
        self, bottle: BottleLabel, mar: MAREntry, resident_id: str,
        progress=None,
    ) -> ExplainResponse:
        """progress: optional callable(stage:str, detail:str) for UI progress reporting."""
        run_id = new_run_id()
        t0 = time.time()
        total_cost = 0.0

        def _p(stage: str, detail: str = ""):
            if progress:
                progress(stage, detail)

        _p("begin", "")
        self.audit.emit(run_id, "orchestrator", "begin", {
            "bottle": bottle.model_dump(), "mar": mar.model_dump(), "resident_id": resident_id,
        })

        # ---- Resolve RxCUIs from labels via local KG (production: RxNav approximateTerm fallback).
        _p("resolve", f"bottle={bottle.label_text!r} mar={mar.label_text!r}")
        bottle.rxcui = bottle.rxcui or _resolve_rxcui(bottle, self.kg)
        mar.rxcui = mar.rxcui or _resolve_rxcui(mar, self.kg)

        # ---- Context Extractor
        _p("context_extractor", f"resident={resident_id}")
        ctx = self.extractor.extract(run_id, resident_id)
        if ctx is None:
            return self._abstain(run_id, t0, total_cost,
                                 "resident context not found",
                                 "Resident profile is unavailable; cannot reason about safety.")

        # ---- Reasoner
        _p("reasoner", getattr(self.reasoner.provider, "model", "?"))
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
        _p("validator", getattr(self.validator.provider, "model", "?"))
        validator_report, m2 = self.validator.validate(run_id, claims.structured_claims, ctx)
        total_cost += m2.get("cost_usd", 0.0)

        # ---- Safety widening: ingredient-class hop for red-flag edges.
        # Even when the specific bottle/MAR RxCUIs have no direct edge, dangerous pairs
        # at the ingredient-class level (e.g. metoprolol tartrate ↔ succinate) must surface.
        if bottle.rxcui and mar.rxcui:
            hop_edges = self.kg.safety_edges_across_ingredients(bottle.rxcui, mar.rxcui)
            if hop_edges:
                bottle_drug = self.kg.get_drug(bottle.rxcui)
                mar_drug = self.kg.get_drug(mar.rxcui)
                bottle_ing = bottle_drug.ingredient_in if bottle_drug else "unknown"
                mar_ing = mar_drug.ingredient_in if mar_drug else "unknown"
                for edge in hop_edges:
                    if any(v.edge_id == edge.edge_id for v in validator_report.edge_verdicts):
                        continue
                    sibling_explanation = (
                        f"Ingredient-class hop: bottle ({bottle_ing}) "
                        f"and MAR ({mar_ing}) share a "
                        f"{edge.relation} relation — "
                        + "; ".join(f"{ci.get('key')}={ci.get('value')}" for ci in edge.constraint_items)
                    )
                    validator_report.edge_verdicts.append(EdgeVerdict(  # noqa: F821 — module-level import
                        edge_id=edge.edge_id, relation=edge.relation,
                        subject=edge.subject, object=edge.object,
                        status="contradicted",
                        reasoning=sibling_explanation,
                        citations=[Citation(**c) for c in edge.citations],
                        constraint_items_evaluated=[
                            {"key": ci.get("key"), "value": ci.get("value"),
                             "status": "contradicted", "reasoning": "ingredient-class hop",
                             "matched_literal": ""}
                            for ci in edge.constraint_items
                        ],
                    ))
                self.audit.emit(run_id, "orchestrator", "ingredient_class_hop", {
                    "bottle_rxcui": bottle.rxcui, "mar_rxcui": mar.rxcui,
                    "hop_edges": [e.edge_id for e in hop_edges],
                })

        # ---- Resident-anchored safety widening.
        # Edges whose `object` is a non-drug string (allergy name, organ-function
        # marker like 'egfr', etc.) are NOT retrieved by `edges_between(a, b)`.
        # We retrieve them per-anchor-drug here and evaluate each `constraint_item`
        # against the resident context using the validator's own constraint
        # evaluator — same logic, same canned reasoning. If the aggregate is
        # contradicted, surface the edge as a contradicted EdgeVerdict so the
        # red-flag path catches it.
        for drug_rxcui in [r for r in (bottle.rxcui, mar.rxcui) if r]:
            drug_anchor = self.kg.get_drug(drug_rxcui)
            for edge in self.kg.safety_edges_anchored_on(drug_rxcui):
                if any(v.edge_id == edge.edge_id for v in validator_report.edge_verdicts):
                    continue
                evals: list[dict] = []
                statuses: list[str] = []
                for ci in edge.constraint_items:
                    key = ci.get("key", "")
                    val = ci.get("value")
                    status, reason, matched = _eval_constraint(
                        key, val, drug_anchor, None, ctx,
                    )
                    evals.append({
                        "key": key, "value": val, "status": status,
                        "reasoning": reason, "matched_literal": matched,
                    })
                    statuses.append(status)
                final_status = _aggregate(statuses)
                if final_status != "contradicted":
                    continue
                validator_report.edge_verdicts.append(EdgeVerdict(
                    edge_id=edge.edge_id, relation=edge.relation,
                    subject=edge.subject, object=edge.object,
                    status="contradicted",
                    reasoning="; ".join(e["reasoning"] for e in evals)
                              or f"{edge.relation} contraindicated for resident",
                    citations=[Citation(**c) for c in edge.citations],
                    constraint_items_evaluated=evals,
                ))
                self.audit.emit(run_id, "orchestrator", "safety_widening", {
                    "drug_rxcui": drug_rxcui, "edge_id": edge.edge_id,
                    "relation": edge.relation, "evals": evals,
                })

        # ---- Auditor
        _p("auditor", getattr(self.auditor.provider, "model", "?"))
        audit_report, m3 = self.auditor.review(run_id, validator_report)
        total_cost += m3.get("cost_usd", 0.0)

        # ---- Filter downgraded edges (but never downgrade ingredient-class hop red flags;
        # those are deterministic safety widenings, not LLM-narrated claims).
        hop_edge_ids = {e.edge_id for e in (
            self.kg.safety_edges_across_ingredients(bottle.rxcui, mar.rxcui)
            if bottle.rxcui and mar.rxcui else []
        )}
        active_verdicts = [v for v in validator_report.edge_verdicts
                           if v.edge_id not in audit_report.downgraded_edge_ids
                           or v.edge_id in hop_edge_ids]
        _p("decide", "")

        # ---- Decide
        verdict, mechanism, explanation, abstain_reason = self._decide(
            claims, active_verdicts, audit_report, ctx,
            bottle_rxcui=bottle.rxcui, mar_rxcui=mar.rxcui,
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
            data_versions=_data_versions_from(self.kg),
            latency_ms=latency_ms,
            cost_usd=round(total_cost, 6),
        )
        self.audit.emit(run_id, "orchestrator", "complete", {
            "response": response.model_dump(), "latency_ms": latency_ms, "cost_usd": total_cost,
        })
        return response

    # ---------- decision logic (SPEC §6.5) ----------

    def _decide(
        self, claims, active_verdicts: list[EdgeVerdict], audit: AuditReport, ctx,
        *, bottle_rxcui: str | None = None, mar_rxcui: str | None = None,
    ):
        # Hard guardrails: any contradicted nti_pair_unsafe or contraindicated_with_allergy
        # or requires_prescriber_notice → abstain.
        red_flag_relations = {"nti_pair_unsafe", "contraindicated_with_allergy",
                              "requires_prescriber_notice", "dose_adjust_renal"}
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

        # Same-RxNorm-concept fast path. If bottle and MAR resolve to identical RxCUIs
        # and no contradicted edge fired, they are literally the same drug — no KG edge
        # is needed to assert equivalence. Red-flag/auditor-downgrade paths above already
        # took precedence, so this can only fire on a clean run.
        if bottle_rxcui and mar_rxcui and bottle_rxcui == mar_rxcui \
                and not any(v.status == "contradicted" for v in active_verdicts):
            return "equivalent", Mechanism.GENERIC, \
                   f"Bottle and MAR resolve to the same RxNorm concept (RxCUI {bottle_rxcui}).", \
                   None

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
            data_versions=_data_versions_from(self.kg),
            latency_ms=latency_ms,
            cost_usd=round(cost, 6),
        )
        self.audit.emit(run_id, "orchestrator", "abstain_early", {"reason": reason})
        return resp
