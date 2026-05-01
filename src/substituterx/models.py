"""Pydantic contracts. Every agent boundary is typed.

Per SPEC §6: agents communicate via these models, every step is logged JSON-Lines.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


def new_run_id() -> str:
    return uuid.uuid4().hex[:16]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Inputs ----------

class BottleLabel(BaseModel):
    label_text: str
    ndc: str | None = None
    rxcui: str | None = None


class MAREntry(BaseModel):
    label_text: str
    rxcui: str | None = None


class ResidentRef(BaseModel):
    resident_id: str


# ---------- Resident context (§6.2) ----------

class ResidentContextVector(BaseModel):
    resident_id: str
    age: int
    sex: Literal["M", "F", "X"]
    allergies: list[str] = Field(default_factory=list)
    current_meds_rxcui: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    egfr: float | None = None  # mL/min/1.73m^2
    child_pugh: Literal["A", "B", "C", None] = None
    nti_sensitive: bool = False
    notes: str | None = None


# ---------- Reasoner (§6.1) ----------

class Mechanism(str, Enum):
    GENERIC = "generic"
    THERAPEUTIC_INTERCHANGE = "therapeutic_interchange"
    DISCREPANCY = "discrepancy"
    UNKNOWN = "unknown"


class Claim(BaseModel):
    subject_rxcui: str | None = None
    predicate: str
    object_rxcui: str | None = None
    object_str: str | None = None
    rationale: str
    evidence_request: str


class ReasonerClaims(BaseModel):
    equivalent: bool | None  # None = unknown
    mechanism: Mechanism
    structured_claims: list[Claim]
    confidence: float = Field(ge=0.0, le=1.0)


# ---------- Validator (§6.3) ----------

class Citation(BaseModel):
    source: Literal["rxnorm", "orange_book", "openfda_recall", "primekg", "dailymed"]
    identifier: str
    url: str | None = None


class EdgeVerdict(BaseModel):
    edge_id: str
    relation: str
    subject: str
    object: str
    status: Literal["supported", "contradicted", "unknown"]
    reasoning: str
    citations: list[Citation] = Field(default_factory=list)
    constraint_items_evaluated: list[dict] = Field(default_factory=list)


class ValidatorReport(BaseModel):
    edge_verdicts: list[EdgeVerdict]
    raw_reasoning_trace: str  # the auditor reads this


# ---------- Auditor (§6.4) ----------

class AuditFlag(BaseModel):
    edge_id: str
    reason: Literal["unsourced_threshold", "unsourced_entity", "classifier_judged_parametric"]
    detail: str


class AuditReport(BaseModel):
    leakage_detected: bool
    downgraded_edge_ids: list[str] = Field(default_factory=list)
    flags: list[AuditFlag] = Field(default_factory=list)


# ---------- Final response (§7) ----------

class CandidateDrug(BaseModel):
    rxcui: str
    name: str
    te_code: str | None
    why: str


class ExplainResponse(BaseModel):
    run_id: str
    verdict: Literal["equivalent", "discrepancy", "abstain"]
    mechanism: Mechanism
    explanation: str
    candidates: list[CandidateDrug] = Field(default_factory=list)
    edge_verdicts: list[EdgeVerdict] = Field(default_factory=list)
    audit_flags: AuditReport
    abstain_reason: str | None = None
    data_versions: dict[str, str]
    disclaimer: str = (
        "Decision support only. Not medical advice, not a substitute for pharmacist or "
        "prescriber consultation. Always verify against the current MAR and call your "
        "dispensing pharmacy with any discrepancy. This system uses synthetic data for "
        "demonstration."
    )
    latency_ms: int
    cost_usd: float | None = None


class ExplainRequest(BaseModel):
    bottle: BottleLabel
    mar: MAREntry
    resident_id: str
