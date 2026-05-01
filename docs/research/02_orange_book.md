# 02 — FDA Orange Book research

*Source: research fork, 2026-05-01.*

## 1. Download

- Page: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files
- Format: ASCII, **tilde (`~`) delimited**, three files: `products.txt`, `patent.txt`, `exclusivity.txt`.
- Instructions PDF: https://www.accessdata.fda.gov/drugsatfda_docs/ob/OrangeBookDataFileDownloadInstructions.pdf
- Mirrors: coderx.io/source-data/orange-book, Kaggle `thedevastator/fda-orange-book-drug-data`, data.gov entry.

### `products.txt` — relevant columns
`Ingredient` (semicolon-separated for combos), `DF;Route`, `Trade_Name`, `Applicant`, `Strength`, **`Appl_Type`** (`N`=brand NDA, `A`=ANDA generic), **`Appl_No`** (6-digit), **`Product_No`** (3-digit; `Appl_No`+`Product_No` = unique key), **`TE_Code`**, `Approval_Date`, `RLD` (Reference Listed Drug), `RS` (Reference Standard), `Type` (Rx/OTC/DISCN).

For substitution prototype: only `products.txt` matters.

## 2. TE Codes — the substitution rule

**A-rated → substitutable** (subject to state law):
- `AA` — conventional non-problem dosage forms.
- `AB` — actual in-vivo / in-vitro BE study.
- `AB1, AB2, AB3, AB4` — **subset rule**: substitute *only within the same numbered subset*. AB1 ↔ AB1 OK; AB1 ↔ AB2 **NOT OK**. Famous trap: Cardizem CD vs Dilacor XR (both diltiazem ER).
- `AN` solutions/powders for aerosolization, `AO` injectable oils, `AP` injectable aqueous, `AT` topicals.

**B-rated → DO NOT substitute** without prescriber consent:
- `BC` ER tablets/caps with BE concerns, `BD` documented BE problems, `BE` delayed-release concerns, `BN` nebulizer, `BP` potential BE issues, `BR` suppositories/enemas systemic, `BS` standards deficiencies, `BT` topicals BE issues, **`BX` insufficient data → treat as non-substitutable**, `B*` under regulatory review.

**Substitution rule:** TE code starts with `A` AND candidate matches `Ingredient + Strength + DF` AND same numeric subset (`AB1`↔`AB1`).

## 3. Bridge to RxNorm (no native key)

- **Best path:** OB Product → **NDC** (openFDA `/drug/ndc.json` keyed by `application_number+product_number`) → **RxCUI** (RxNav `/REST/ndcstatus.json?ndc=…`).
- **Pragmatic fallback:** normalize `Ingredient + Strength + DF` and call RxNav `/REST/approximateTerm.json` — decent recall, watch precision on combos and ER vs IR.
- **Reverse (RxCUI known):** RxNav `getAllRelatedInfo` → SCD/SBD → NDC list → join to OB.
- Reference SQL: jpryda gist (NDC↔RxCUI), fabkury/ndc_map.

For prototype: build a one-time bridge table (OB `Appl_No+Product_No` → NDC11 → RxCUI[SCD]) cached in DuckDB. ~50–100 drugs trivial.

## 4. License

FDA-published data is **U.S. Government public domain** (data.gov confirms). Cite version date. No FDA endorsement implied.

## 5. Update cadence + staleness mitigation

**Monthly.** For LTC dispensing, monthly is borderline (recalls/withdrawals/new ANDA approvals between snapshots). Mitigations:
- Pin `data_version` in every output.
- Cross-check live recalls via openFDA enforcement endpoint at query time.
- UI surfaces "as-of" date; abstain if `today - data_version > 35 days`.

## 6. Pseudocode — AB-rated equivalents

```python
def equivalents(rxcui_or_ndc):
    ndc = to_ndc11(rxcui_or_ndc)
    seed = ob_products.where(ndc_set.contains(ndc)).first()
    if not seed: return abstain("no OB match")

    if not seed.TE_Code.startswith("A"):
        return abstain(f"seed is {seed.TE_Code} — non-substitutable")

    subset = re.match(r"AB(\d+)", seed.TE_Code)
    candidates = ob_products.where(
        Ingredient == seed.Ingredient,
        Strength   == seed.Strength,
        DF_Route   == seed.DF_Route,
        TE_Code.startswith("A"),
        Type != "DISCN",
    )
    if subset:
        candidates = candidates.where(TE_Code == seed.TE_Code)  # SAME subset only
    return [c for c in candidates if c.Appl_No != seed.Appl_No]
```

The validator agent layers patient-context constraints **on top of** this candidate set — never the other way around.

## 7. Five dangerous substitution traps (red-team eval cases)

1. **Metoprolol succinate ER (Toprol-XL) ↔ metoprolol tartrate IR.** Different salt + form, different kinetics, different indications.
2. **Diltiazem ER products** (Cardizem CD, Cardizem LA, Tiazac, Dilacor XR). Classic `AB1`/`AB2` subset trap.
3. **Levothyroxine** — NTI; AB-rated but TSH-sensitive; many states require prescriber notification on switch.
4. **Warfarin ↔ DOACs.** Not interchangeable. Different monitoring, reversal, renal dosing.
5. **Bupropion 300 SR vs XL**, **HBr vs HCl salts** — FDA pulled an AB rating in 2012 for Budeprion XL 300 generic.

Honorable mentions: cyclosporine modified vs non-modified (Sandimmune vs Neoral, AB1/AB2), tacrolimus (NTI), phenytoin (NTI), insulin glargine biosimilars, conjugated estrogens (no AB rating exists).

## Bottom line for the build

TE-code filter on `products.txt` gives the *candidate set*; the agentic validator layers (a) NTI-drug allow-list rules, (b) subset-equality enforcement, (c) live recall check, (d) patient-context constraints (renal/hepatic/allergy/interactions). **Orange Book alone never authorizes a substitution recommendation — it scopes it.**

## Sources

- https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files
- https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-preface
- https://www.drugpatentwatch.com/blog/decoding-the-fda-orange-books-therapeutic-equivalence-te-codes-for-generic-drug-substitution-strategy/
- https://catalog.data.gov/dataset/approved-drug-products-with-therapuetic-equivalence-evaluations-orange-book
- https://www.nlm.nih.gov/research/umls/user_education/quick_tours/RxNorm/ndc_rxcui/NDC_RXCUI_DrugName.html
- https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getNDCProperties.html
- https://open.fda.gov/apis/drug/ndc/
- https://open.fda.gov/apis/drug/enforcement/
