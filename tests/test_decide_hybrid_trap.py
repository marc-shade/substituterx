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


# ---- Same-RxCUI fast path (orchestrator.py:_decide) -----------------------

def test_same_rxcui_fast_path_returns_equivalent(
    orch: Orchestrator, resident_ctx: ResidentContextVector
) -> None:
    """Bottle and MAR resolving to the same RxCUI must return equivalent — no KG
    edge links a→a, but the drugs are literally the same. Without this fast path,
    the system would abstain `no_kg_evidence` on identical-drug labels (real bug
    discovered during browser E2E)."""
    claims = ReasonerClaims(equivalent=None, mechanism=Mechanism.UNKNOWN,
                            structured_claims=[], confidence=0.0)
    audit = AuditReport(leakage_detected=False)

    verdict, mechanism, explanation, abstain_reason = orch._decide(
        claims, [], audit, resident_ctx,
        bottle_rxcui="617318", mar_rxcui="617318",
    )

    assert verdict == "equivalent"
    assert mechanism == Mechanism.GENERIC
    assert "617318" in explanation
    assert "RxNorm concept" in explanation
    assert abstain_reason is None


def test_find_by_name_rejects_unknown_drug_with_unit_collision(
    orch: Orchestrator,
) -> None:
    """Bug 11 regression: query 'tacrolimus 1 mg' must not silently resolve
    to levothyroxine just because '1' and 'mg' appear in the levothyroxine seed
    name. The fix requires ≥1 informative (alpha, len≥4) token to match. The
    orchestrator must abstain on tacrolimus rather than fabricate a verdict."""
    from substituterx.models import BottleLabel, MAREntry

    assert orch.kg.find_by_name("tacrolimus 1 mg") is None
    assert orch.kg.find_by_name("Prograf 1 mg") is None
    # Single-word legitimate queries still resolve.
    assert orch.kg.find_by_name("Lipitor") is not None
    assert orch.kg.find_by_name("atorvastatin") is not None

    resp = orch.explain(
        BottleLabel(label_text="tacrolimus 1 mg"),
        MAREntry(label_text="Prograf 1 mg"),
        "R-0001",
    )
    assert resp.verdict == "abstain"
    assert resp.abstain_reason == "no_kg_evidence"


def test_paranoid_auditor_cannot_downgrade_safety_widening(
    orch: Orchestrator,
) -> None:
    """Bug 14 regression: deterministic safety-widening edges (E030 allergy,
    E050 renal) must NEVER be filtered out by the auditor's downgrade pass.
    Their reasoning is built from constraint_items + resident context, not
    LLM narration, so 'parametric leakage' doesn't apply.

    Without the deterministic-edge bypass, a calibration-broken or adversarial
    auditor that selectively downgrades the safety edge could silently bypass
    the red-flag check (especially if the >30% downgrade-ratio threshold isn't
    triggered)."""
    from substituterx.agents.auditor import AuditorAgent
    from substituterx.models import AuditFlag, AuditReport, BottleLabel, MAREntry, ValidatorReport

    class _DowngradeOnly:
        """Selectively downgrades only the safety edge — keeps the ratio low so
        the >30% threshold doesn't catch it. Tests the edge-id-level bypass."""
        provider = MockProvider()

        def review(self, run_id: str, validator_report: ValidatorReport):
            target = next(
                (v for v in validator_report.edge_verdicts
                 if v.relation == "contraindicated_with_allergy"),
                None,
            )
            if target is None:
                return AuditReport(leakage_detected=False), {"cost_usd": 0.0}
            return AuditReport(
                leakage_detected=True,
                downgraded_edge_ids=[target.edge_id],
                flags=[AuditFlag(
                    edge_id=target.edge_id,
                    reason="classifier_judged_parametric",
                    detail="adversarial test stub",
                )],
            ), {"cost_usd": 0.0}

    # Replace the auditor for this test only; everything else stays mock.
    orch.auditor = _DowngradeOnly()  # type: ignore[assignment]

    resp = orch.explain(
        BottleLabel(label_text="Bactrim DS 800/160 mg"),
        MAREntry(label_text="Bactrim DS 800/160 mg"),
        "R-0004",
    )
    edge_ids = {v.edge_id for v in resp.edge_verdicts}
    assert "E030" in edge_ids, (
        f"E030 must survive auditor downgrade via deterministic-edge bypass; "
        f"got active edges {edge_ids}"
    )
    e030 = next(v for v in resp.edge_verdicts if v.edge_id == "E030")
    assert e030.status == "contradicted"
    assert resp.verdict == "abstain", (
        "Sulfa-allergic resident receiving Bactrim must abstain even if the "
        "auditor tries to downgrade the allergy edge."
    )

    # Restore for any subsequent test using this orch instance
    orch.auditor = AuditorAgent(orch.auditor.provider if hasattr(orch.auditor, "provider")
                                else orch.reasoner.provider, orch.audit)


def test_reasoner_llm_failure_falls_back_to_safe_path(
    orch: Orchestrator,
) -> None:
    """Bug 15 regression: when the reasoner's LLM call raises (network outage,
    JSON parse failure, schema mismatch), the orchestrator must NOT 500. The
    reasoner falls back to empty claims; the orchestrator's `augment_claim`
    step adds a bottle↔MAR claim from the KG-resolved RxCUIs and the verdict
    flows through normally."""
    from substituterx.models import BottleLabel, MAREntry

    class _FailingProvider:
        model = "always-explodes"
        def call(self, *_args, **_kwargs):
            raise RuntimeError("simulated network outage")
        def call_json(self, *_args, **_kwargs):
            raise RuntimeError("simulated JSON failure")

    orch.reasoner.provider = _FailingProvider()  # type: ignore[assignment]

    # SAFE-001 path. Reasoner explodes; orchestrator must still resolve
    # via KG, run validator on E001, and return equivalent.
    resp = orch.explain(
        BottleLabel(label_text="atorvastatin 40 mg"),
        MAREntry(label_text="Lipitor 40 mg"),
        "R-0001",
    )
    assert resp.verdict == "equivalent"
    assert any(v.edge_id == "E001" for v in resp.edge_verdicts)


def test_data_versions_match_seed_metadata(orch: Orchestrator) -> None:
    """Bug 13 regression: response.data_versions must reflect what the seed
    actually loaded, not a hardcoded constant that can drift."""
    from substituterx.models import BottleLabel, MAREntry

    resp = orch.explain(
        BottleLabel(label_text="atorvastatin 40 mg"),
        MAREntry(label_text="Lipitor 40 mg"),
        "R-0001",
    )
    assert resp.data_versions == orch.kg.data_versions
    assert resp.data_versions, "kg.data_versions empty — seed _meta missing or unread"


def test_renal_dose_adjust_fires_when_egfr_below_threshold(
    orch: Orchestrator, tmp_path: Path
) -> None:
    """Bug 6 regression: edges with relation `dose_adjust_renal` and object='egfr'
    were never retrieved by `edges_between(a,b)`. After the safety-widening fix,
    a resident with eGFR < threshold receiving the same drug on bottle and MAR
    must abstain."""
    from substituterx.models import BottleLabel, MAREntry, ResidentContextVector

    class _Stub:
        def __init__(self, ctx: ResidentContextVector):
            self._ctx = ctx
        def get(self, _rid):
            return self._ctx
        def all_ids(self):
            return ["R-LOW"]

    low_egfr = ResidentContextVector(
        resident_id="R-LOW", age=80, sex="M", allergies=[], current_meds_rxcui=[],
        conditions=["ckd"], egfr=22.0, nti_sensitive=False,
    )
    orch_low = Orchestrator(
        orch.kg, _Stub(low_egfr), orch.reasoner.provider,  # type: ignore[arg-type]
        AuditLog(tmp_path / "renal.jsonl"),
    )
    resp = orch_low.explain(
        BottleLabel(label_text="apixaban 5 mg"),
        MAREntry(label_text="Eliquis 5 mg"),
        "R-LOW",
    )
    assert resp.verdict == "abstain"
    edge_ids = {v.edge_id for v in resp.edge_verdicts}
    assert "E050" in edge_ids, f"E050 (renal dose-adjust) must surface, got {edge_ids}"
    assert resp.abstain_reason and "dose_adjust_renal" in resp.abstain_reason


def test_allergy_edge_fires_when_resident_has_matching_allergy(
    orch: Orchestrator,
) -> None:
    """End-to-end allergy regression: bottle and MAR identical Bactrim labels →
    same RxCUI → without the allergy widening, the same-RxCUI fast path would
    return equivalent. Resident R-0004 has a sulfa allergy. The orchestrator must
    fire edge E030 (contraindicated_with_allergy) and abstain.

    This test covers the bug discovered when DANGER-006 stopped passing: edges
    of shape (subject=drug_rxcui, object=allergy_string) are not retrieved by
    `edges_between(a, a)`, so `kg.allergy_contraindication_edges` + the
    orchestrator's allergy-widening pass are required for safety."""
    from substituterx.models import BottleLabel, MAREntry

    resp = orch.explain(
        BottleLabel(label_text="Bactrim DS 800/160 mg"),
        MAREntry(label_text="Bactrim DS 800/160 mg"),
        "R-0004",
    )

    assert resp.verdict == "abstain"
    edge_ids = {v.edge_id for v in resp.edge_verdicts}
    assert "E030" in edge_ids, (
        f"E030 (sulfa contraindication) must surface, got edges={edge_ids}"
    )
    e030 = next(v for v in resp.edge_verdicts if v.edge_id == "E030")
    assert e030.status == "contradicted"
    assert e030.relation == "contraindicated_with_allergy"
    assert resp.abstain_reason and "contraindicated_with_allergy" in resp.abstain_reason


def test_same_rxcui_fast_path_yields_to_red_flag(
    orch: Orchestrator, resident_ctx: ResidentContextVector
) -> None:
    """Even when bottle and MAR have the same RxCUI, a red-flag verdict
    (e.g. contraindicated_with_allergy) must still abstain — the resident's
    safety constraint takes precedence over the equivalence shortcut."""
    claims = ReasonerClaims(equivalent=None, mechanism=Mechanism.UNKNOWN,
                            structured_claims=[], confidence=0.0)
    audit = AuditReport(leakage_detected=False)
    active = [_verdict("E-ALLERGY", "contraindicated_with_allergy", "contradicted")]

    verdict, _mechanism, explanation, abstain_reason = orch._decide(
        claims, active, audit, resident_ctx,
        bottle_rxcui="617318", mar_rxcui="617318",
    )

    assert verdict == "abstain"
    assert "Call the pharmacy" in explanation
    assert abstain_reason
