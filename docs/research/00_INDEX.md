# Research dossier — index

These four files are the synthesis returned by the parallel research forks dispatched at session start (2026-05-01). Each fork ran in an isolated context window with a fixed word cap and citation requirement. See `../process/00_apparatus_orchestrator_prompts.md` for the orchestrator prompts used to dispatch them.

| File | Topic | Word cap | Critical takeaway |
|---|---|---|---|
| [01_rxnorm.md](01_rxnorm.md) | RxNorm / RxNav API surface | 600 | RxNav doesn't carry AB-codes; bridge to Orange Book via NDC. metoprolol succinate vs tartrate are different RxNorm ingredients — naive ingredient-match is dangerous. |
| [02_orange_book.md](02_orange_book.md) | FDA Orange Book schema + TE codes | 700 | A-rated → substitutable; B-rated → never. AB1↔AB2 subset rule (Cardizem CD vs Dilacor XR). 5 dangerous-substitution traps named. |
| [03_primekg_qkg.md](03_primekg_qkg.md) | PrimeKG + QKG paper repo | 800 | PrimeKG schema verified (29 relations, ~129K nodes, drugs keyed to DrugBank). **QKG paper repo could not be located — built against the paper's described architecture instead, per Never-Fabricate rule.** |
| [04_ltc_domain.md](04_ltc_domain.md) | LTC pharmacy substitution domain | 800 | **The decisive reframing: caregivers don't substitute. The product is an EXPLAINER for bottle-vs-MAR reconciliation, not an advisor.** DAW codes documented; the existing LTC dispensing-platform ecosystem mapped. |
| [05_genai_persuasion_and_trendslop.md](05_genai_persuasion_and_trendslop.md) | GenAI persuasion (HBS WP 26-021) + strategy trendslop (HBR Mar 2026) | — | Two May-2026 papers map directly onto the Validator→Auditor seam. Architecture validates; five small hardening edits identified (Auditor stylistic-ethos check, hybrid as default, Reasoner predicate diversity log, hybrid-trap eval case, devil's-advocate deferred). |

Plus: [transcript_qkg_paper_video.txt](transcript_qkg_paper_video.txt) — the foundational direction (Liu et al., *Quantum Knowledge Graph: Modeling Context-Dependent Triplet Validity*, Apr 28 2026), as discussed in the Discover AI YouTube walk-through. The architecture pattern adopted here is the four-agent loop described in that paper.
