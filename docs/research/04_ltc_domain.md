# 04 — LTC pharmacy substitution domain research

*Source: research fork, 2026-05-01. **This fork's findings drove the prototype reframing — see SPEC §1.***

## 1. Workflow: who decides

**Caregivers/nurses never substitute.** Substitution authority:
- **Pharmacist** — performs generic substitution under state law unless prescriber blocks (DAW 0)
- **Prescriber** — initiates therapeutic interchange, or blocks via DAW

The MAR (Medication Administration Record) is the caregiver's source of truth. They administer what the MAR says; bottle/MAR mismatch protocol = **call the pharmacy**, not interpret.

**the LTC pharmacy management platform's AI order-entry tool** (verified): "AI that reads, populates, and streamlines order entry" — prescriber→pharmacist intake automation (OCR/NLP over scripts populating dispensing). **Not** caregiver-facing. Adjacent the pharmacy↔facility comms channel = facility↔pharmacy comms (where caregiver questions actually flow). the pharmacist-led MRR tooling = pharmacist-led MRR. Other modules: adjacent modules cover document workflow, analytics, mobile barcode, and delivery. **No existing in-house product targets the caregiver explainer use case.**

## 2. DAW codes (NCPDP)

| Code | Meaning |
|---|---|
| 0 | No DAW — substitution allowed (default, ~95%) |
| 1 | Prescriber **blocks** ("brand medically necessary") |
| 2 | Patient requested brand |
| 3 | Pharmacist selected brand |
| 4 | Generic not in stock |
| 5 | Brand dispensed as generic (multi-source brand priced as generic) |
| 6 | Override |
| 7 | Brand mandated by law |
| 8 | Generic not available in market |
| 9 | Other |

DAW 1 = prescriber hard block. DAW 2 = patient block. Both override pharmacist default substitution authority.

## 3. Regulatory framing — **CORRECTED USER STORY**

> Caregiver receives delivery. Bottle reads "metoprolol succinate ER 50mg," MAR reads "Toprol XL 50mg." Caregiver needs reassurance these are the same drug **before administering**, or to flag a discrepancy.

The system **does not recommend substitutes**. It **explains substitutions the pharmacist already made**, applies resident context to flag any clinical concern, and routes ambiguous cases to "Call pharmacy." **Reframe as explainer, not advisor** — dodges scope-of-practice issues entirely.

## 4. State substitution laws (synthesized)

All 50 + DC permit generic substitution. Two regimes:
- **Permissive** (most): pharmacist *may* substitute unless DAW blocks.
- **Mandatory** (NY, FL historically, KY): pharmacist *must* dispense generic unless DAW blocks.
- **Patient consent** rules vary; LTC has carve-outs.
- **NTI carve-outs** in ~10 states require extra consent for narrow-therapeutic-index drugs: warfarin, levothyroxine, lithium, phenytoin, digoxin, theophylline, carbamazepine.
- **Biologics/biosimilars**: separate "interchangeable" designation under BPCIA.

Source: FDA Orange Book preamble + NABP model rules. Verify per-state via NABP DB before any production claim.

## 5. Five high-risk LTC substitution scenarios

1. **Levothyroxine** — Synthroid ↔ generic ↔ Tirosint: AB-rated but within-spec bioequivalence variation can shift TSH in elderly; ATA/AACE recommend brand consistency.
2. **Metoprolol succinate ER (Toprol XL) ↔ tartrate IR**: different dosing frequency (qd vs bid), different indication set (succinate is HFrEF-indicated, tartrate is not). ER↔IR is **not** a generic substitution; classic ISMP confused-pair / transcription-error class.
3. **Warfarin ↔ DOACs (apixaban/rivaroxaban)**: never a generic equivalent; therapeutic interchange requires prescriber. Real LTC harm cases documented. Brand warfarin (Coumadin/Jantoven) consistency matters within-NTI.
4. **Bupropion XL 300 ↔ SR 150 BID**: 2012 FDA withdrew Teva generic approval for non-bioequivalence; LTC psychiatric population sensitive to formulation changes.
5. **Clozapine** brand↔generic: REMS-registered; switching requires re-baseline ANC monitoring. Lithium carbonate IR↔ER and lamotrigine brand↔generic also flagged in psychogeriatric literature.

ISMP confused-pair canon also includes: hydroxyzine/hydralazine, glyburide/glipizide, fentanyl patches across mcg/hr strengths.

## 6. HIPAA / disclaimer language

Synthetic data only → HIPAA N/A, but UI mirrors production:

> **Decision support only. Not medical advice, not a substitute for pharmacist or prescriber consultation. Always verify against the current MAR and call your dispensing pharmacy with any discrepancy. This system uses synthetic data for demonstration.**

Persistent banner + per-result footer. Every recommendation surfaces citations (RxNorm RXCUI, Orange Book TE code, DailyMed SPL ID). Abstain path required for incomplete context, NTI/REMS drugs.

## 7. Differentiation vs. existing in-house

Nothing in their portfolio targets the caregiver. the pharmacy↔facility comms channel is the channel but not a clinical-explainer agent. **Defensible niche: caregiver-side explainer with resident-context-aware safety check**, grounded in the same RxNorm/Orange Book sources the dispensing side uses.

in-house production scale (verified): 800 pharmacies / 49 states / 2M patients / 15K daily users.

Sources: the LTC dispensing-platform vendor site (verified), the prospective employer's site (verified), NCPDP DAW (training), FDA Orange Book preamble (training), ISMP confused-name list (training, fetch 403).
