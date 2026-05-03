"""Regression test: Trendslop "Hybrid Trap" resistance.

Romasanta, Thomas & Levina (HBR, March 2026) document that LLMs offered both/and
options frequently hedge by recommending both. The Reasoner could analogously hedge
by emitting both `is_generic_of` AND `is_therapeutic_alt_of` claims for the same
RxCUI pair.

The contract `Orchestrator._decide` enforces is: when both relations are supported,
`equivalent` (via `is_generic_of`) wins — the system never returns a "hybrid" verdict.
This test locks that behaviour in.

Cross-reference: docs/research/05_genai_persuasion_and_trendslop.md §"Improvement 5".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from substituterx.agents.orchestrator import Orchestrator
from substituterx.audit_log import AuditLog
from substituterx.kg import KGStore
from substituterx.models import (
    AuditReport,
    EdgeVerdict,
    Mechanism,
    ReasonerClaims,
    ResidentContextVector,
)
from substituterx.provider import MockProvider
from substituterx.residents import ResidentStore


@pytest.fixture
def orch(tmp_path: Path) -> Orchestrator:
    kg = KGStore()
    kg.load_seed()
    residents = ResidentStore()
    audit = AuditLog(tmp_path / "audit.jsonl")
    return Orchestrator(kg, residents, MockProvider(), audit)


@pytest.fixture
def resident_ctx() -> ResidentContextVector:
    return ResidentContextVector(
        resident_id="R-TEST",
        age=72,
        sex="F",
        allergies=[],
        current_meds_rxcui=[],
        conditions=[],
        egfr=80.0,
        nti_sensitive=False,
    )


def _verdict(edge_id: str, relation: str, status: str = "supported") -> EdgeVerdict:
    return EdgeVerdict(
        edge_id=edge_id,
        relation=relation,
        subject="X",
        object="Y",
        status=status,  # type: ignore[arg-type]
        reasoning=f"({relation}) constraints satisfied",
        citations=[],
        constraint_items_evaluated=[],
    )


def test_hybrid_trap_generic_wins_over_therapeutic(
    orch: Orchestrator, resident_ctx: ResidentContextVector
) -> None:
    """If the Reasoner hedges by emitting both is_generic_of AND is_therapeutic_alt_of
    for the same pair, and both edges resolve to supported, the verdict must be
    `equivalent` via the generic mechanism — not `abstain`, not a hybrid."""
    claims = ReasonerClaims(equivalent=None, mechanism=Mechanism.UNKNOWN,
                            structured_claims=[], confidence=0.0)
    audit = AuditReport(leakage_detected=False)
    active = [
        _verdict("E-GEN", "is_generic_of", "supported"),
        _verdict("E-THER", "is_therapeutic_alt_of", "supported"),
    ]

    verdict, mechanism, _explanation, abstain_reason = orch._decide(
        claims, active, audit, resident_ctx,
    )

    assert verdict == "equivalent"
    assert mechanism == Mechanism.GENERIC
    assert abstain_reason is None


def test_hybrid_trap_therapeutic_only_still_abstains(
    orch: Orchestrator, resident_ctx: ResidentContextVector
) -> None:
    """Sanity: if the generic edge is contradicted (or absent) and only therapeutic
    remains, the verdict must abstain — confirms the rank order isn't masking a
    genuine therapeutic-interchange decision."""
    claims = ReasonerClaims(equivalent=None, mechanism=Mechanism.UNKNOWN,
                            structured_claims=[], confidence=0.0)
    audit = AuditReport(leakage_detected=False)
    active = [
        _verdict("E-THER", "is_therapeutic_alt_of", "supported"),
    ]

    verdict, mechanism, _explanation, abstain_reason = orch._decide(
        claims, active, audit, resident_ctx,
    )

    assert verdict == "abstain"
    assert mechanism == Mechanism.THERAPEUTIC_INTERCHANGE
    assert abstain_reason == "therapeutic_interchange_requires_prescriber"


def test_hybrid_trap_red_flag_overrides_generic(
    orch: Orchestrator, resident_ctx: ResidentContextVector
) -> None:
    """Sanity: red-flag relations beat is_generic_of even when generic is supported.
    A Reasoner that hedges generic + nti_pair_unsafe must still abstain."""
    claims = ReasonerClaims(equivalent=None, mechanism=Mechanism.UNKNOWN,
                            structured_claims=[], confidence=0.0)
    audit = AuditReport(leakage_detected=False)
    active = [
        _verdict("E-GEN", "is_generic_of", "supported"),
        _verdict("E-NTI", "nti_pair_unsafe", "contradicted"),
    ]

    verdict, _mechanism, explanation, abstain_reason = orch._decide(
        claims, active, audit, resident_ctx,
    )

    assert verdict == "abstain"
    assert "Call the pharmacy" in explanation
    assert abstain_reason  # populated with the red-flag reasons
