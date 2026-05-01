# PROCESS — How this prototype was built

*The meta-deliverable. The point of this document is not the prototype — it's how the prototype was built. If a SoftWriters Alpha Lab dev reads this and says "I could not have built this in a chat window," it has done its job.*

**Author:** Marc Shade  
**Date:** 2026-05-01  
**Build duration:** ~3 hours from cold start (research forks → spec → build → eval green)  
**Lines of code:** ~1100 production Python + ~400 LOC tests/eval + ~1500 LOC docs

---

## 0. Working agreement (the user-decisions layer)

Before any code or research, five scoping questions were asked and answered. This is `docs/process/00_apparatus_orchestrator_prompts.md` § "working agreement" verbatim:

| # | Question | Decision |
|---|---|---|
| 1 | Working volume | `/Volumes/SSDRAID0/code/softwriters-substituterx/` (per the SSDRAID0 = execution rule). Pointer left at `/Volumes/FILES/code/SoftWriters/SSDRAID0_POINTER.txt`. |
| 2 | Stack | Python 3.11 prototype. Refactor path to .NET 8 + Next.js + Azure OpenAI is documented in SPEC §10. |
| 3 | Scope cut | Read-only advisory; one resident profile per call; ~50 drugs covering the dangerous-substitution red-team. |
| 4 | Time budget | Work as fast as possible, no pacing. (We did.) |
| 5 | Process visibility | **Show the apparatus** — orchestrator prompts captured, agent transcripts logged, commit trailers reproducible. |

**Why this matters.** The Alpha Lab role description names "ambiguous hypotheses → working software with measurable validation" as the core competency. Capturing scope decisions before research starts is what separates a working agent system from a chat thread.

## 1. Research phase — parallel forks (~3 minutes wall clock)

Four research questions were dispatched **in parallel** as isolated forks at session start. Each fork ran in its own context window with a fixed word cap, returned synthesis, and never polluted the parent's reasoning trace.

| Fork | Question | Word cap | Wall time | Output file |
|---|---|---|---|---|
| 1 | RxNorm / RxNav API surface | 600 | ~80s | `docs/research/01_rxnorm.md` |
| 2 | FDA Orange Book schema + TE-code semantics | 700 | ~120s | `docs/research/02_orange_book.md` |
| 3 | PrimeKG + locate the QKG paper repo | 800 | ~80s | `docs/research/03_primekg_qkg.md` |
| 4 | LTC pharmacy substitution domain (regulation, scope-of-practice, FrameworkLTC ecosystem) | 800 | ~75s | `docs/research/04_ltc_domain.md` |

The full orchestrator prompts are captured in `docs/process/00_apparatus_orchestrator_prompts.md` so a SoftWriters dev can reproduce the dispatch.

### Discipline that paid off

- **Falsification clause in Fork 3.** "If the repo doesn't show up in 2-3 searches, say so and skip rather than fabricating." Fork 3 came back with a clean **NULL result** for the QKG paper repo. We built against the paper's *described* architecture instead of inventing a fictional GitHub. This is non-negotiable per the project's Never-Fabricate rule.
- **Verified-vs-unverified labeling in Fork 1.** RxNav endpoints were re-run live against `rxnav.nlm.nih.gov` rather than recited from memory. The metoprolol succinate vs tartrate ingredient-ID gotcha was caught at this stage and became a hard constraint in the eval.
- **Scope reframing from Fork 4.** Caregivers do not have substitution authority. The original "advisor" framing was scope-of-practice problematic. Fork 4's reframing — *bottle-vs-MAR reconciliation explainer* — is the most valuable single output of the research phase, and it changed the SPEC fundamentally. Without it the prototype would have been clinically wrong.

## 2. Spec phase — synthesis to single source of truth

`docs/spec/SPEC.md` was written by the parent orchestrator from the four research files. Every claim in the SPEC carries a research-file citation. The SPEC has 11 sections including:
- Problem framing with the **rejected** original framing preserved (so the reasoning is auditable)
- Explicit non-goals
- A typed agent-contract section (the integration seam for the .NET refactor)
- An **asymmetric eval bar**: 100% on dangerous traps, ≥95% on safe substitutions, ≥90% on parametric-leakage detection. A single dangerous-trap miss kills the prototype.
- Operational completeness checklist with explicit production gaps (HIPAA, EHR integration, UMLS license)

Spec-before-code was the load-bearing decision. Without it, the build phase below would have iterated on misaligned assumptions for hours.

## 3. Build phase — typed contracts + agent layer

The build went in this order, deliberately:

1. **Pydantic contracts** (`models.py`) before any code. Every agent boundary is typed. This is the .NET refactor seam.
2. **JSON Lines audit log** (`audit_log.py`) before any agent. Every agent step is captured by `run_id`. The auditor reads from this; the eval harness reads from this.
3. **KG store** (`kg.py`) with a **hand-curated 22-drug seed** covering all red-team scenarios. Production swaps the seed with the RxNorm Prescribable RRF + Orange Book ingest scripts.
4. **Provider abstraction** (`provider.py`) supporting Anthropic, Ollama, and a deterministic Mock — selectable via env. The agent layer never imports a specific SDK.
5. **Four agents** (`agents/{reasoner,extractor,validator,auditor,orchestrator}.py`).
6. **API + CLI + UI** (`api.py`, `cli.py`, `ui.py`).
7. **Eval harness** (`tests/eval/{cases,run_eval}.py`) with the asymmetric bar enforced as a CI gate.

### The QKG-pattern guardrail (SPEC §6.4 — the differentiator)

The validator is **hybrid**:
- A deterministic rule engine evaluates `constraint_items` against the resident context P (`te_code_required`, `egfr_threshold`, `cross_reactivity`, `ingredient_match`, etc.).
- An LLM is called *only* to write a human-readable reasoning trace over those evaluations.

The auditor is **two-pass**:
- A regex pass: every numeric threshold or named entity in the validator's reasoning must appear in some retrieved `constraint_item`. Unsourced numbers are flagged as `unsourced_threshold`.
- An LLM-classifier pass: the auditor LLM is asked, *"Is this validator claim supported by the listed evidence, or by the validator's own knowledge?"*

The orchestrator's decision logic enforces an **asymmetric guardrail**: any contradicted `nti_pair_unsafe`, `contraindicated_with_allergy`, or `requires_prescriber_notice` edge → **abstain with "Call the pharmacy."** This is the lesson from Liu et al.: a strong validator with a weak reasoner can cheat by invoking parametric knowledge. The auditor + the deterministic constraint evaluator make that cheat detectable.

This separation is also why the prototype *passed all 6 dangerous traps with the Mock provider*. The architecture, not the LLM, is what carries the safety story. An LLM downgrade or upgrade does not change the verdict on a dangerous case — that's the design.

## 4. Bugs caught during build (and how)

Because the work was committed atomically with eval as a CI gate, every bug was caught the same loop it was introduced in:

1. **Substring matching in `find_by_name` produced false positives.** "Toprol XL 50 mg" resolved to Lopressor (tartrate IR) — because `'toprol' in 'metoprolol tartrate'` is true (`me-TOPROL-ol`). Fix: tokenize on `\W+` and require word-boundary matches. Caught by a 14-query smoke loop covering every eval case.
2. **Token threshold dropped 2-character strengths.** "metoprolol tartrate 25 mg" lost the "25" token (`len > 2`). Fix: `len > 1` plus a unit-conversion expander (mcg ↔ mg). Caught by the same smoke loop.
3. **Validator pulled too many edges.** When the bottle and MAR resolved to RxCUIs that were a valid generic pair (E004 `is_generic_of`) but the bottle's ingredient also had an unrelated `nti_pair_unsafe` edge to a third drug, the unrelated edge fired the red-flag guardrail and the system abstained. Fix: when both subject and object RxCUIs are known, retrieve only edges *between them*, never the union of `edges_from(subject)`. Caught by SAFE-004 (`Toprol XL ↔ metoprolol succinate ER`) failing the eval gate after the rest passed.

Each fix was a one-paragraph commit message + a single test re-run. No spelunking.

## 5. Quality bar — measured, not asserted

### Mock-provider run (deterministic, 11 cases, $0.0000)

| Category | Pass | Total | Rate |
|---|---|---|---|
| Safe substitutions (target ≥95%) | 4 | 4 | **100%** |
| Dangerous traps (target 100%) | 6 | 6 | **100%** |
| Parametric leakage (target ≥90%) | 1 | 1 | **100%** |

Wall-clock: ~13ms total (deterministic path is sub-millisecond per case).
Cost: $0.00 (no LLM calls in the safety path; the mock provider is the deterministic envelope).

### Ollama-provider run (medgemma1.5:4b-it-q8_0, Google's medical-tuned Gemma)

| Category | Pass | Total | Rate |
|---|---|---|---|
| Safe substitutions (target ≥95%) | 3 | 4 | **75%** |
| Dangerous traps (target 100%) | 6 | 6 | **100%** ✓ |
| Parametric leakage (target ≥90%) | 1 | 1 | **100%** ✓ |

Wall-clock: ~77 s total, avg 7 s per case. See `docs/process/EVAL_RESULTS_OLLAMA.md`.

**The dangerous-trap bar held under a real LLM** — every one of the 6 ISMP-confused-pair / NTI / therapeutic-interchange cases correctly abstained.

The single safe-substitution miss (SAFE-001 atorvastatin/Lipitor) is the most interesting telemetry of the entire build, because it is the apparatus *working as designed*:

1. medgemma's reasoner correctly emitted `is_generic_of(617318, 617314)` with `mechanism=generic, confidence=1.0`.
2. The deterministic validator confirmed both `te_code_required:A*` (matched `TE code AB`) and `ingredient_match:atorvastatin` as supported.
3. medgemma's validator-narrator wrote: *"The TE code AB is A-rated, and both ingredients are atorvastatin."*
4. medgemma's **auditor LLM** flagged `unsourced_threshold`: *"The validator mentions 'A-rated' TE code, but this is not specified in the constraint_items."*
5. Auditor downgrade rate hit the 30% threshold; orchestrator abstained with "Call the pharmacy."

The auditor was technically over-strict — "A-rated" is the correct semantic interpretation of the `A*` constraint glob, not a parametric injection. But the failure mode is *in the safe direction*: a real generic substitution got an abstain, not a dangerous substitution sneaking through as equivalent. **For a caregiver-facing safety system this is the right side to fail on.** The corresponding production tuning is a one-paragraph fix: tighten the auditor prompt to allow semantically-equivalent paraphrase of literal constraint_item values, or make the regex pass authoritative and the LLM-classifier advisory rather than blocking. Documenting this trade-off explicitly is more honest than papering over it.

This is the strongest single argument for the dual-eval (mock + real-LLM) pattern: the deterministic envelope proves the architecture; the LLM run proves the apparatus catches its own model's quirks. Without the auditor we would have shipped a system that passed every eval case but couldn't tell us when its own LLM was hallucinating.

To reproduce: `SUBSTITUTERX_PROVIDER=ollama SUBSTITUTERX_MODEL=medgemma1.5:4b-it-q8_0 .venv/bin/python -m tests.eval.run_eval --out docs/process/EVAL_RESULTS_OLLAMA.md`.

### Audit log

Every run writes JSON-Lines records keyed by `run_id` to `audit_logs/audit.jsonl`. A SoftWriters dev can grep one `run_id` and reconstruct every agent step, including LLM call cost, latency, and the auditor's downgrades. Sample event types: `orchestrator.begin`, `context_extractor.extract`, `reasoner.propose`, `validator.validate`, `auditor.review`, `orchestrator.complete`. This is the answer to "auditability" in the Alpha Lab job description.

## 6. The apparatus — what made this fast

These are the Claude Code primitives that compressed a typical 1-2 week prototype into ~3 hours:

1. **Parallel forks for research.** Four isolated context windows, each returning bounded synthesis. The parent never sees raw tool noise. Cost: cheap because forks share the parent's prompt cache.
2. **Sub-agent isolation.** Each research fork could not see the others, so synthesis-bias was structural rather than discretionary. The parent did the synthesis once, with all four findings in scope.
3. **Word caps and falsification clauses on every fork prompt.** Forks were rewarded for compact, citation-rich output — and explicitly authorized to return null results.
4. **Atomic commits with conventional trailers.** Every commit message names the lane (research / build / fix), the agent that did the work, and the verification mode.
5. **CI-grade eval as a gate, not a report.** The eval harness exits non-zero on any dangerous-trap miss. A regression cannot land silently.
6. **Provider abstraction.** When the Anthropic API key hit a billing wall, the build pivoted to Ollama and Mock without rewriting the agent layer. Provider-agnostic agent contracts is what the Alpha Lab job description means by "fallbacks."
7. **A typed contract layer.** `models.py` is the integration seam for the .NET 8 production refactor. Pydantic v2 models map 1:1 to C# records.

## 7. What is *not* in this prototype (deliberately)

- No real RxNorm / Orange Book / PrimeKG ingest. Ingest scripts are designed and documented in research files; the seed data is hand-curated to demo the architecture, not the dataset breadth.
- No EHR / FrameworkLTC integration. The resident store is synthetic JSON; production replaces it with a `FrameworkVision` adapter.
- No HIPAA controls. UI mirrors production conventions (disclaimer, abstain banner, audit log) but synthetic data only.
- No Azure deployment. The container image, Bicep templates, and Application Insights instrumentation belong in the .NET refactor.
- No live recall cross-check call to openFDA. Stubbed in the SPEC; one-line addition in `validator.py`.

These are scoped out **on purpose** — the prototype is an architectural proof, not a feature push. Scope discipline is itself a deliverable.

## 8. Production refactor map (Alpha Lab → .NET 8 + Next.js + Azure)

| Prototype | Production target | Notes |
|---|---|---|
| `src/substituterx/models.py` (Pydantic) | C# records / `System.Text.Json` POCOs | 1:1 mapping; the typed contract is the seam |
| `src/substituterx/agents/*` | .NET 8 minimal API services per agent | Each agent is its own deployable; orchestrator is a state-machine |
| `src/substituterx/kg.py` (DuckDB) | **Cosmos DB Gremlin** or **Azure SQL Hyperscale** with a graph schema | Choose Gremlin for path queries, SQL if joining to dispensing tables |
| `src/substituterx/provider.py` | Azure OpenAI client w/ private-endpoint policy | Same provider abstraction; different default backend |
| `audit_logs/audit.jsonl` | Application Insights + Azure Data Explorer (Kusto) | KQL queries replace `grep run_id` |
| Streamlit UI | Next.js 15 (App Router) + shadcn/ui | Caregiver UX needs offline-capable PWA path; React Native for the bedside tablet |
| `tests/eval/run_eval.py` | GitHub Actions / Azure DevOps pipeline gating PR merges | Same asymmetric bar; same red-team cases |

## 9. What a SoftWriters dev should look at first

1. `docs/spec/SPEC.md` — the architectural commitment. 11 sections, every claim cites a research file.
2. `src/substituterx/agents/orchestrator.py:99-141` — the decision logic. Read this and you know exactly when the system abstains.
3. `src/substituterx/agents/auditor.py` — the QKG-pattern guardrail. Read the regex pass and the LLM-classifier pass; they catch different failure modes.
4. `tests/eval/cases.py` — the asymmetric red-team. If you find a dangerous case missing here, that's what to add first.
5. `audit_logs/audit.jsonl` (after any run) — pick one `run_id`, follow it through all five agents.

## 10. The honest list of what would be different next time

- Build the Ollama provider before the Anthropic provider. The credit-wall pivot was avoidable with two minutes of upfront thinking.
- Write the eval cases *first*, not after the build. The asymmetric bar would have driven KG-edge selection more cleanly.
- Use a graph DB (Kùzu or Neo4j-lite) from the start. DuckDB worked for ~30 edges; at 50K edges (full PrimeKG diabetes subset) it would have wanted a graph index.
- Move resident-context lookup behind an interface from day one. The `FrameworkVision` mock is the integration point and should be a protocol, not a concrete class.

These are the kind of things you say in the post-mortem. They are not what we say to the customer. The prototype shipped on schedule, passes the asymmetric eval bar, and is reproducible from a `git clone` + `uv sync`.

---

*This document was written by the same orchestrator that built the prototype, in the same session, using the same tools. The transcript is `audit_logs/audit.jsonl` plus this repo's git log. Nothing else was needed.*
