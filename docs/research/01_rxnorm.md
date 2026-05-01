# 01 — RxNorm / RxNav API research

*Source: research fork, 2026-05-01. All endpoints verified live against rxnav.nlm.nih.gov.*

## Endpoints (verified)

**Base:** `https://rxnav.nlm.nih.gov/REST` — JSON via `.json` suffix.

| Need | Endpoint | Notes |
|---|---|---|
| Name → RxCUI (exact) | `GET /rxcui.json?name={str}&search={0\|1\|2}` | `search=2` enables normalized match. |
| Fuzzy / misspell | `GET /approximateTerm.json?term={str}&maxEntries=20&option=1` | Returns ranked candidates. Empty `inputTerm` = no hit. |
| RxCUI → related-by-TTY | `GET /rxcui/{rxcui}/related.json?tty=IN+PIN+SCDC+SCDF+SCD+SBD+GPCK+BPCK` | `+`-separated TTY list. |
| RxCUI → all properties | `GET /rxcui/{rxcui}/properties.json` | Includes `suppress` flag. |
| RxCUI → NDCs | `GET /rxcui/{rxcui}/ndcs.json` | Bridge to Orange Book. |
| Drug interactions | `GET /interaction/interaction.json?rxcui={rxcui}` | **Deprecated 2024.** Use a separate DDI source. |
| Spelling suggestions | `GET /spellingsuggestions.json?name={str}` | Cheap pre-pass. |

Verified live samples:
```bash
curl -s 'https://rxnav.nlm.nih.gov/REST/rxcui.json?name=metoprolol+succinate+25+mg'
# {"idGroup":{"rxnormId":["1370489"]}}

curl -s 'https://rxnav.nlm.nih.gov/REST/rxcui/866924/related.json?tty=SCD+SBD+GPCK+BPCK+IN'
# returns metoprolol IN 6918, SCD 866924 ...
```

## Therapeutic equivalence

**RxNav does not carry FDA AB-codes.** RxNorm TTY graph gives *clinical* equivalence (same ingredient + strength + dose form via SCD), not bioequivalence/AB-rating. **Join RxNorm RxCUIs → FDA Orange Book via NDC** for AB/BX/BC codes.

NDF-RT REST deprecated 2018; MED-RT lacks a public REST. Prototype path: RxNorm SCD-graph for clinical equivalence + Orange Book NDC join for AB-rating.

## Auth / rate / terms

- **No auth, no API key.** Public, free.
- Rate limit: **20 req/s per IP** (NLM-published). 429 on burst.
- Attribution: "U.S. National Library of Medicine. RxNorm/RxNav."
- Cache RxCUI→relatedGroup locally; release is monthly.

## Offline / monthly release

- Filename pattern: `RxNorm_full_MMDDYYYY.zip` (full, **UMLS license required**) or `RxNorm_full_prescribe_MMDDYYYY.zip` (**Current Prescribable Content, no license**).
- Format: pipe-delimited RRF (RXNCONSO, RXNREL, RXNSAT, RXNSTY).
- Source: `https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html`.

**Prototype decision: use Prescribable Content subset** — no license, faster, sufficient for caregiver-facing tool.

## Gotchas

- **TTY hierarchy:** `IN` → `SCDC` → `SCDF` → **`SCD`** ↔ **`SBD`**. For brand→generics: SBD → SCD via `consists_of`/`tradename_of`, or SBD → SCDC → siblings → SCD.
- **Packs (`GPCK`/`BPCK`):** multi-component (Z-Pak). Treat separately or you get false equivalences.
- **Suppressed concepts:** filter `suppress=Y` (RxNorm-suppressed) and `O` (obsolete).
- **Ingredient-form trap:** `metoprolol succinate` (IN 221124) vs `metoprolol tartrate` (IN 6918) are **different ingredients** in RxNorm — naive ingredient-match suggests equivalence; **they are not interchangeable**. Same trap: bupropion HCl IR/SR/XL, diltiazem CD/SR, nifedipine. **Build an `ingredient_form_pair_unsafe` constraint** for the KG.
- `approximateTerm` returns empty `inputTerm` (not error) on miss — handle explicitly.
- Combo products (lisinopril/HCTZ): one SCD with multiple SCDCs — surface all components.

## Paste-ready recipes

```bash
DRUG="lipitor 40mg"
curl -s "https://rxnav.nlm.nih.gov/REST/rxcui.json?name=$(jq -rn --arg s "$DRUG" '$s|@uri')&search=2"

RXCUI=617314
curl -s "https://rxnav.nlm.nih.gov/REST/rxcui/$RXCUI/related.json?tty=SCD+SCDC+IN" \
  | jq '.relatedGroup.conceptGroup[] | select(.tty=="SCD")'

curl -s "https://rxnav.nlm.nih.gov/REST/rxcui/$RXCUI/ndcs.json"
curl -s "https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term=lipator&maxEntries=5&option=1"
```

## Recommendation for prototype

Hybrid: **RxNav REST for live name→RxCUI + spelling fallback** + **Prescribable Content RRF loaded into DuckDB** for relation graph and offline AB-rating join with Orange Book. Disk-cache REST responses keyed by RxCUI (monthly TTL). Hard-code the `ingredient_form_pair_unsafe` list (succinate-ER vs tartrate-IR; bupropion HCl IR/SR/XL; etc.) as `constraint_items` on the corresponding KG edges.
