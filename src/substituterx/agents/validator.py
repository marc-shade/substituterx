"""Validator agent (SPEC §6.3).

Hybrid: deterministic rules evaluate constraint_items where possible; an LLM is
called only to produce a human-readable reasoning trace that the auditor will scan.

The validator NEVER decides substitution from its own knowledge — every verdict
is grounded in retrieved KG edges and their constraint_items.
"""
from __future__ import annotations

from ..audit_log import AuditLog
from ..kg import KGStore, Edge
from ..models import (
    Claim, Citation, EdgeVerdict, ResidentContextVector, ValidatorReport,
)
from ..provider import AnthropicProvider


# Deterministic constraint evaluators -----------------------------------------

def _eval_constraint(
    key: str, value, drug_subject, drug_object, P: ResidentContextVector
) -> tuple[str, str]:
    """Return (status, reasoning) for a single constraint_item.

    status: 'supported' | 'contradicted' | 'unknown'
    """
    if key == "te_code_required":
        # Pattern like "A*" — match any A-prefixed TE code on the candidate
        if drug_subject and drug_subject.te_code and drug_subject.te_code.startswith("A"):
            return "supported", f"TE code {drug_subject.te_code} is A-rated"
        return "contradicted", f"TE code {getattr(drug_subject,'te_code',None)} is not A-rated"

    if key == "ingredient_match":
        if drug_subject and drug_object and drug_subject.ingredient_in == drug_object.ingredient_in:
            return "supported", f"both ingredients = {value}"
        return "contradicted", "ingredients differ"

    if key == "dose_form_match":
        if drug_subject and drug_object and drug_subject.dose_form == drug_object.dose_form:
            return "supported", f"both dose forms = {value}"
        return "contradicted", "dose forms differ"

    if key == "egfr_threshold":
        if P.egfr is None:
            return "unknown", "resident eGFR not recorded"
        if P.egfr < float(value):
            return "contradicted", f"resident eGFR {P.egfr} < {value} — dose adjustment required"
        return "supported", f"resident eGFR {P.egfr} ≥ {value}"

    if key == "age_threshold":
        if P.age >= int(value):
            return "supported", f"resident age {P.age} ≥ {value} (NTI sensitivity applies)"
        return "supported", f"resident age {P.age} < {value} (threshold not triggered)"

    if key == "cross_reactivity":
        triggers = value if isinstance(value, list) else [value]
        hit = [a for a in P.allergies if a.lower() in [t.lower() for t in triggers]]
        if hit:
            return "contradicted", f"resident allergy {hit} cross-reacts with {triggers}"
        return "supported", "no allergy match"

    if key == "nti_class":
        if drug_subject and drug_subject.nti:
            return "supported", f"drug is NTI class={value}"
        return "supported", "NTI flag noted"

    if key == "requires_prescriber":
        return "contradicted" if str(value).lower() == "true" else "supported", \
               "therapeutic interchange requires prescriber"

    return "unknown", f"no deterministic evaluator for key={key}"


def _aggregate(statuses: list[str]) -> str:
    if "contradicted" in statuses:
        return "contradicted"
    if all(s == "supported" for s in statuses) and statuses:
        return "supported"
    return "unknown"


VALIDATOR_REASONING_SYSTEM = """You are the Validator-Narrator. You will receive a list of
edges with their constraint_items already evaluated against the resident context. Your job
is to write a 2-3 sentence reasoning trace per edge in clear caregiver language.

CRITICAL: cite ONLY the constraint_items in the input. Do NOT invoke clinical knowledge
that isn't in the constraint_items. The Auditor will flag any unsourced claim.

Output JSON: {"per_edge": [{"edge_id": "...", "reasoning": "..."}]}
"""


class ValidatorAgent:
    def __init__(self, kg: KGStore, provider: AnthropicProvider, audit: AuditLog) -> None:
        self.kg = kg
        self.provider = provider
        self.audit = audit

    def validate(
        self, run_id: str, claims: list[Claim], P: ResidentContextVector,
    ) -> tuple[ValidatorReport, dict]:
        verdicts: list[EdgeVerdict] = []
        edges_collected: list[Edge] = []

        for claim in claims:
            if not claim.subject_rxcui:
                continue
            edges: list[Edge] = []
            if claim.object_rxcui:
                # Both endpoints known: only retrieve edges BETWEEN them.
                edges.extend(self.kg.edges_between(claim.subject_rxcui, claim.object_rxcui))
            elif claim.predicate != "unknown":
                # Only-subject case: scope to the requested relation.
                edges.extend(self.kg.edges_from(claim.subject_rxcui, [claim.predicate]))
            edges = list({e.edge_id: e for e in edges}.values())
            edges_collected.extend(edges)

            for edge in edges:
                drug_s = self.kg.get_drug(edge.subject)
                drug_o = self.kg.get_drug(edge.object)
                evals = []
                statuses = []
                for ci in edge.constraint_items:
                    key = ci.get("key", "")
                    val = ci.get("value")
                    status, reason = _eval_constraint(key, val, drug_s, drug_o, P)
                    evals.append({"key": key, "value": val, "status": status, "reasoning": reason})
                    statuses.append(status)

                # Edge-level relation aggregation
                final_status = _aggregate(statuses)
                # nti_pair_unsafe and contraindicated_with_allergy edges are red flags:
                # presence alone is contradiction unless evaluators say otherwise.
                if edge.relation in ("nti_pair_unsafe", "contraindicated_with_allergy") and final_status != "contradicted":
                    final_status = "contradicted"
                if edge.relation == "requires_prescriber_notice":
                    final_status = "contradicted"

                verdicts.append(EdgeVerdict(
                    edge_id=edge.edge_id, relation=edge.relation,
                    subject=edge.subject, object=edge.object,
                    status=final_status,
                    reasoning="; ".join(e["reasoning"] for e in evals) or "no constraints to evaluate",
                    citations=[Citation(**c) for c in edge.citations],
                    constraint_items_evaluated=evals,
                ))

        # Now ask the LLM to write a unified reasoning trace — the auditor reads this.
        meta = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        if verdicts:
            user = "\n".join(
                f"Edge {v.edge_id} ({v.relation}: {v.subject} → {v.object}) "
                f"final_status={v.status}, evaluators={[e for e in v.constraint_items_evaluated]}"
                for v in verdicts
            )
            try:
                parsed, result = self.provider.call_json(
                    VALIDATOR_REASONING_SYSTEM, user,
                    schema_hint='{"per_edge":[{"edge_id":"...","reasoning":"..."}]}',
                    max_tokens=800,
                )
                meta = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd, "model": result.model}
                rmap = {p["edge_id"]: p["reasoning"] for p in parsed.get("per_edge", [])}
                trace_lines = []
                for v in verdicts:
                    if v.edge_id in rmap:
                        v.reasoning = rmap[v.edge_id]
                    trace_lines.append(f"[{v.edge_id}] {v.reasoning}")
                trace = "\n".join(trace_lines)
            except Exception as exc:
                trace = "\n".join(f"[{v.edge_id}] {v.reasoning}" for v in verdicts)
                meta["error"] = str(exc)
        else:
            trace = "(no edges retrieved)"

        report = ValidatorReport(edge_verdicts=verdicts, raw_reasoning_trace=trace)
        self.audit.emit(run_id, "validator", "validate", {
            "report": report.model_dump(), **meta,
        })
        return report, meta
