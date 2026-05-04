# Apparatus — Orchestrator prompts

## Provenance note (read first)

The original Claude Code session that spawned the four research forks at
**2026-05-01 ~10:21 EDT** was not transcript-captured to this repo. The
exact verbatim prompts therefore do not exist in this codebase, and the
earlier version of this doc carried `[prompt verbatim]` placeholders
that were never circled back on — exactly the kind of theater this
project is built to refuse.

What this repo does have, and what is sufficient to reproduce the work:

1. **The actual fork outputs**, captured at session time and committed:
   - [`docs/research/01_rxnorm.md`](../research/01_rxnorm.md) — Fork 1
   - [`docs/research/02_orange_book.md`](../research/02_orange_book.md) — Fork 2
   - [`docs/research/03_primekg_qkg.md`](../research/03_primekg_qkg.md) — Fork 3
   - [`docs/research/04_ltc_domain.md`](../research/04_ltc_domain.md) — Fork 4

2. **Reconstructed prompts** below, derived from the fork outputs by
   working backward from "what was asked produces this dossier". Each
   reconstruction is clearly marked **RECONSTRUCTED — not verbatim**.
   They are correct in shape, scope, and constraints but not character-
   identical to what the original session sent.

3. **The orchestration pattern** itself, which is the part that
   transfers: parallel forks in a single tool-call block, isolated
   contexts, bounded outputs, explicit falsification clauses. This is
   reproducible regardless of exact wording.

A reviewing engineer can use the reconstructed prompts as a starting
point and tune from the dossier outputs to match their own domain.

---

## Why fork-based research first

The forks ran concurrently, each in an isolated context window,
returning compact synthesis to the parent. This is the cheapest form of
compaction — sub-agent contexts don't pollute the parent's reasoning
trace, and outputs are bounded by explicit word caps.

- Each fork shares the parent's prompt cache (cheap)
- Each fork's tool-call output stays in its own context (clean)
- Each fork returns synthesis only (small token footprint on parent)
- Parallel launch in one tool-call block (low wall-clock)

This is the same reasoning Eric (Anthropic) describes in the
*vibe-coding-in-prod* talk: Claude as PM, leaf-node agents do bounded
work, output is verifiable.

---

## Fork 1 — RxNorm / RxNav

**Goal:** nail down the API surface for drug name → RxCUI → equivalents.

**Output produced:** [`docs/research/01_rxnorm.md`](../research/01_rxnorm.md)
(2.2KB, endpoint table + auth/rate, offline release path, gotchas,
paste-ready recipes, recommendation).

### Reconstructed prompt (NOT VERBATIM)

```
Research the RxNorm / RxNav public API for the substituterx prototype.
Word cap: 600. Citations required for every endpoint.

Cover:
1. The endpoint surface for: name → RxCUI exact, fuzzy/spell-correct
   match, RxCUI → related (by TTY), RxCUI → properties, RxCUI → NDCs,
   spelling suggestions. Verify each one live against rxnav.nlm.nih.gov
   with curl examples and real responses.
2. Therapeutic equivalence: does RxNav carry FDA AB codes? If not, how
   do we bridge to Orange Book? Be specific about the relation graph.
3. Auth, rate limits, attribution requirements, terms of use.
4. Offline / monthly release: file naming, format (RRF), license terms
   (UMLS vs Prescribable Content). Which subset does a no-license
   prototype use?
5. Gotchas a naive consumer will hit: TTY hierarchy traps, suppressed
   concepts, ingredient-form pairs that LOOK equivalent but aren't
   (succinate vs tartrate, HCl vs HBr salts), pack-vs-product handling,
   approximateTerm empty-result idiom.
6. Paste-ready bash/curl recipes the prototype can adapt directly.
7. Bottom-line recommendation for the prototype: hybrid live REST +
   offline RRF, or one-or-the-other? What gets cached, with what TTL?

Constraint: every endpoint claim must be backed by a verified live
response. If a claim cannot be verified, say so and skip it rather
than fabricating.
```

---

## Fork 2 — FDA Orange Book

**Goal:** schema, TE codes, RxNorm bridge, dangerous-substitution traps.

**Output produced:** [`docs/research/02_orange_book.md`](../research/02_orange_book.md)
(5.9KB, download/format, products.txt schema, TE-code substitution
rules, RxNorm bridge via NDC, license, update cadence, AB-equivalents
pseudocode, five dangerous substitution traps for the eval).

### Reconstructed prompt (NOT VERBATIM)

```
Research the FDA Orange Book for the substituterx prototype. Word cap:
700. Citations required.

Cover:
1. Where to download the data files. Format (delimiter, encoding, file
   names). Mirrors that are easier to fetch than the FDA page.
2. The columns of products.txt that matter for substitution decisions.
   Which is the unique key (Appl_No + Product_No)? What's the canonical
   "this is substitutable" signal?
3. TE codes — the actual substitution rule. Walk through:
     - A-rated codes (AA, AB, AB1/2/3/4 subset rule, AN, AO, AP, AT)
     - B-rated codes — explicit list, what each means
     - The AB1↔AB2 subset trap (Cardizem CD vs Dilacor XR)
     - "TE starts with A AND same Ingredient/Strength/DF AND same
       numeric subset" as the substitution rule
4. Bridge to RxNorm. There's no native key — what's the path?
   (NDC join via openFDA + RxNav.) Reverse path (RxCUI → OB)?
5. License (FDA public domain), citation requirement, version pinning.
6. Update cadence. How stale can the snapshot be before we should
   abstain?
7. Pseudocode for the AB-equivalents query that the validator will
   execute against the OB join.
8. **Five dangerous substitution traps** that should drive the
   prototype's red-team eval cases. For each, name the drug pair, why
   it's dangerous, and what the validator should catch. Include
   metoprolol succinate↔tartrate, the diltiazem ER subset trap,
   levothyroxine NTI, warfarin↔DOACs, bupropion XL↔SR.

Constraint: this fork's main job is producing the eval seed cases for
the prototype. If the FDA page documents a feature differently than how
some third-party explainer describes it, prefer the FDA page.
```

---

## Fork 3 — PrimeKG + QKG paper repo

**Goal:** data source for the knowledge graph; locate the QKG paper's GitHub repo.

**Output produced:** [`docs/research/03_primekg_qkg.md`](../research/03_primekg_qkg.md)
(3.4KB). PrimeKG section: VERIFIED with project URL, repo, Dataverse
DOI, schema, drug-relevant relations, DuckDB loading code. QKG section:
**NOT FOUND** — three searches documented, fork explicitly stopped
rather than fabricating, per the falsification clause below.

### Reconstructed prompt (NOT VERBATIM)

```
Research two things for the substituterx prototype. Word cap: 800.
Citations required.

Part A — PrimeKG (Harvard mims-harvard/PrimeKG):
1. Where is it? Project page, repo, paper citation, dataset DOI.
2. License — code, dataset.
3. Schema: node types and counts, edge types and counts, the relation
   names that matter for drug-side reasoning (indication, contra-
   indication, off-label, drug-drug, drug-protein, drug-effect).
4. CSV column structure. Drug node identifier (DrugBank? RxNorm?). If
   it's not RxNorm, what's the crosswalk path?
5. Loading: pandas + DuckDB-on-CSV vs full ingest. Subset extraction
   (e.g. diabetes subgraph) for prototype scale.

Part B — The QKG paper's GitHub repo:
1. Find the GitHub repo for "Quantum Knowledge Graph: Modeling
   Context-Dependent Triplet Validity" (Liu et al., 2026). The video
   walkthrough referenced one but didn't show the URL.
2. Try at least three independent search strategies (arXiv, GitHub UI,
   web search).

**FALSIFICATION CLAUSE — non-negotiable per project Never-Fabricate
rule:** if the QKG repo doesn't show up in 2-3 reasonable searches,
explicitly say "NOT FOUND" with the search terms tried, and STOP.
DO NOT guess a URL. DO NOT fabricate a repo path. The prototype
will build against the paper's *described* architecture if needed;
that is acceptable.

Adjacent work that IS verifiable (e.g., arXiv papers on
schema-aware-planning + hybrid KG verification, quantum-embeddings on
KGs) is fine to surface as "useful context, not the QKG repo".
```

---

## Fork 4 — LTC pharmacy substitution domain

**Goal:** regulatory framing, DAW codes, real high-risk substitution scenarios, the existing LTC dispensing-platform ecosystem fit.

**Output produced:** [`docs/research/04_ltc_domain.md`](../research/04_ltc_domain.md)
(5.4KB). This fork's findings drove the entire prototype reframing
from "advisor" to "explainer" — see SPEC §1. The reframe is the most
load-bearing scope decision in the project.

### Reconstructed prompt (NOT VERBATIM)

```
Research the LTC (long-term care) pharmacy substitution domain for the
substituterx prototype. Word cap: 800. Citations required.

Cover:
1. Workflow: who actually decides on substitution? In an LTC facility,
   what are the role boundaries between caregiver, nurse, pharmacist,
   prescriber? What does the caregiver actually see — bottle, MAR,
   both? What protocol applies on bottle/MAR mismatch?
2. DAW (Dispense As Written) codes. The full NCPDP table (0-9),
   what each means, which are hard blocks vs soft signals.
3. Regulatory framing. Is "caregiver-facing substitution advisor" even
   a viable scope? If not, what's the closest defensible scope that
   actually helps the caregiver without crossing scope-of-practice?
   This question is the most important one in the whole prompt — if
   the answer is "advisor doesn't work, reframe as explainer",
   surface that hard.
4. State substitution laws — high-level synthesis. Permissive vs
   mandatory regimes. NTI carve-outs. Biologic/biosimilar
   interchangeability rules.
5. Five high-risk LTC-specific substitution scenarios that should
   drive eval cases (overlap allowed with Fork 2's pharmacology-side
   list, but framed for the LTC population: elderly, polypharmacy,
   long-stay, NTI-sensitive).
6. HIPAA framing for a synthetic-data prototype. Disclaimer language.
   Citation expectations on every recommendation.
7. Adjacency: do existing LTC-pharmacy dispensing platforms already
   have a caregiver-facing explainer? If yes, what gap remains? If no,
   what's the defensible niche?

Constraint: this fork has the highest scope-shifting potential. If the
research surfaces a clear "the original framing is wrong, reframe as
X" finding, lead with that. The prototype will be reshaped around
this fork's conclusions.
```

---

## Output disposition

Fork outputs land in `docs/research/01_rxnorm.md`,
`02_orange_book.md`, `03_primekg_qkg.md`, `04_ltc_domain.md`. Parent
synthesizes those four into `docs/spec/SPEC.md` with explicit citations
to each finding. Anything not in the four research files does not
enter the spec — the falsification rule applies at the synthesis layer
too.

Fork 4's "reframe as explainer, not advisor" finding is the single
most load-bearing scope decision in the project — every subsequent
choice about agent contracts, the abstain path, and the
"call the pharmacy" UX flows from it. This is documented in SPEC §1
and PROCESS.md §0.

---

## On the "captured verbatim" claim

The earlier version of this doc opened with "Captured verbatim so a
reviewing engineer can reproduce the workflow." That claim was
load-bearing on a property the doc did not actually have. Pointing
that out and rewriting it is the same discipline that produced the 21
fixes documented in [`AI_DEV_PROCESS.md`](AI_DEV_PROCESS.md): a
reviewer noticed the gap, the gap was confirmed against git history,
the doc was rewritten to match what we actually have. No theater.
