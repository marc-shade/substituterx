# 05 — GenAI persuasion + strategy trendslop

*Source: research fork follow-up, 2026-05-03. Two papers landed in the same week; both bear directly on the Validator → Auditor seam.*

## A. Power Persuader (HBS WP 26-021) — VERIFIED from full PDF

**Citation.** Randazzo, S., Joshi, A., Kellogg, K. C., Lifshitz, H., Dell'Acqua, F., & Lakhani, K. R. (2025). *GenAI as a Power Persuader: How Professionals Get Persuasion Bombed When They Attempt to Validate LLMs.* Harvard Business School Working Paper 26-021. SSRN 5678644.

**Setup.** Field study, 72 BCG consultants, custom platform on top of GPT-4 (April 2023 via OpenAI API). Task: recommend to CEO which of three brands (Kleding Man / Woman / Kids) to invest in. 4,339 prompts logged. 132 distinct validation instances coded grounded-theory.

**Three professional validation strategies.**
1. **Fact-Checking** — "Please review your work."
2. **Exposing** — pointing out a factual contradiction in the model's output.
3. **Pushing Back** — disagreeing and asking the model to reconsider.

**Three GenAI persuasion modes (Aristotle's frame), 14 tactics total.**
- **Ethos** (credibility, 5): Apologizing, Correcting, Effort Transparency, Hedging, Deflecting.
- **Logos** (logic, 4): Agree-and-counterpoint, Comparing, Using Data-Insight, Problem-Solution Structure.
- **Pathos** (emotion, 5): Affirming, Energizing, Emphasizing Inclusivity, Mirroring, Visioning.

**Two failure mechanisms ("persuasion bombing").**
1. *Intensity ramp* — when challenged, the model fires more tactics simultaneously (PS8: 2 tactics pre-validation → 5 tactics post-pushback).
2. *Tactic-type shift* — when fact-checked, the model abandons logos and pivots to ethos defense (apology + correction + deflection) rather than addressing substance (PS9).

**Headline framing.** GenAI is a *power persuader*: validation does not yield disclosure of limitations, it yields more insistent persuasion. Authors propose **persuasion as a fourth barrier** to human-AI collaboration (alongside opacity, automation complacency, and accuracy).

**Authors' recommendations to system designers (not just users).**
- Limit emotionally-charged or definitive language at the model layer.
- Surface counterpoints and uncertainties by default.
- Use **AI-critic agents** (Saunders et al., 2022) — separate-model parallel oversight.
- Shift validation responsibility from the user alone to the deployer + developer.

**Limitation.** Only *internal validation* (chat-loop) studied. Whether *external validation* (recompute the math in Excel; ask a different model) defeats persuasion bombing is open.

## B. Strategy Trendslop (HBR, March 2026) — VERIFIED from full HBR article body

**Citation.** Romasanta, A., Thomas, L. D. W., & Levina, N. (2026). *Researchers Asked LLMs for Strategic Advice. They Got "Trendslop" in Return.* Harvard Business Review, March 16, 2026.

**Setup.** Seven leading LLMs (ChatGPT, Claude, DeepSeek, GPT-5 via API, Gemini, Grok, Mistral). Seven binary strategic tensions. 50 runs per model per tension for the baseline figure; >15,000 trials manipulating prompts; >15,000 additional trials manipulating context.

**The seven tensions.** Exploration↔Exploitation; Centralization↔Decentralization; Short-term↔Long-term; Competition↔Collaboration; Radical↔Incremental Innovation; Differentiation↔Commoditization; Automation↔Augmentation.

**Findings.**
- All models cluster toward the *culturally fashionable* side (differentiation, augmentation, long-term, decentralization, collaboration, incremental). Only Exploration↔Exploitation shows real cross-model variation.
- Prompt manipulation moved differentiation/augmentation responses by **<2%** from baseline. Other tensions moved ~22%, but **~19% of that came from option-order flipping alone** — i.e., the bias is partly position-sensitive noise, not reasoned movement.
- Adding rich industry context shifted answers ~11% from baseline. Bias persists across "tech startup, multinational, hospital, nonprofit, Chinese firm, etc."
- When a "both / hybrid" option was allowed: 63% trendy / 24% hybrid / 12% unfashionable. Per-tension hybrid rates: differentiation 96%, augmentation 93%, collaboration 78%, long-term 62%; *radical-vs-incremental 41% hybrid; explore-vs-exploit 56% hybrid* — the "Hybrid Trap."

**Mechanism.** LLMs predict the most socially-desirable next token from training data. "Differentiation," "collaboration," "augmentation" sit in positive contexts on the open internet; "commoditization," "centralization," "automation" sit in negative ones. The model optimizes the *positive emotional valence of words in everyday language* in lieu of context-specific strategic analysis.

**Authors' recommendations.**
- Use LLMs to *expand options*, not make choices.
- Actively counteract known biases — explicitly prompt for the unfashionable side.
- Surface concrete success / failure cases for each side before deciding.
- **Treat hybrid recommendations as red flags** (Porter's "stuck in the middle").
- Keep records — biases drift across model versions.

---

## How this maps to SPEC.md and the validator chain

The two papers describe the failure modes the SPEC's Validator + Auditor pair was already designed to mitigate. Most of the architecture *is validated*. A few specific gaps surface only after reading the tactic taxonomies.

### Validates (architecture choices the research independently recommends)

| Architecture choice | Paper recommendation it satisfies |
|---|---|
| **LLM never decides substitution** — every verdict from deterministic constraint evaluators in `validator.py:_eval_constraint`. The LLM only *narrates* already-evaluated rules (`VALIDATOR_REASONING_SYSTEM` prompt explicitly forbids invoking external clinical knowledge). | Trendslop §"Use LLMs to expand options, not make choices." Power Persuader's call for "limiting overly definitive language at the model layer." |
| **Auditor is a separate agent** with its own model (hybrid mode runs medgemma-4B Validator vs qwen3-14B Auditor — different model family). Regex pre-pass on numbers, LLM-classifier second pass. | Power Persuader §"AI-critic agents (Saunders et al., 2022)" + "parallel agents or complementary oversight." This is exactly the parallel-agent pattern the paper argues human-in-the-loop alone cannot substitute for. |
| **Asymmetric guardrail in `_decide`**: red-flag relations (`nti_pair_unsafe`, `contraindicated_with_allergy`, `requires_prescriber_notice`) → abstain unconditionally. >30% auditor-downgrade ratio → abstain. No edges → abstain. | Power Persuader §"shift the burden of validation away from users alone to the deployer/developer." The caregiver never has to argue the LLM down — the system pre-decides abstain on the dangerous cases. |
| **Three-verdict output** — `equivalent` / `discrepancy` / `abstain`. No "hybrid" verdict. Therapeutic-alternative edges always route to abstain. | Trendslop §"Hybrid Trap." SPEC's enum-bounded verdict literally precludes the failure mode. |
| **Caregiver scope = explainer, not advisor** (Fork 4 reframing in `04_ltc_domain.md`). The caregiver receives a verdict; substitution authority sits with the pharmacist. | Power Persuader closing line: *"GenAI's acting as a 'power persuader' raises doubts about the use of human-in-the-loop solutions to society's greatest problems."* SubstituteRx never asks the caregiver to validate raw LLM output. |
| **Ingredient-class hop** (`orchestrator.py:124-160`) widens the safety scan even when no direct edge exists. Hop-edges are *never downgraded by the Auditor* (`hop_edge_ids` set in `orchestrator.py:169-175`). | Trendslop §"actively counteract potential biases." The hop is a structural devil's-advocate pass against the Reasoner's possibly biased predicate selection. |
| **Audit log captures full reasoning trail** including model assignments per agent (`orchestrator.py:58-62`). | Trendslop §"Remain alert to changing biases. Maintain a record of all results." Power Persuader §"Future research is needed to investigate alternative algorithmic design logics" implies provenance. |

### Gaps the papers expose (improvements ranked by value)

**1. Auditor doesn't catch *stylistic* ethos leakage.** *(High value, small change.)* — **LANDED 2026-05-03.**

The previous `AUDITOR_SYSTEM` prompt looked for unsourced numbers, named entities, and clinical facts. Power Persuader's "Effort Transparency" tactic ("After thorough analysis…", "Upon careful evaluation…") and "Apologizing"/"Correcting" tactics are *unsourced credibility claims* — not numbers, but parametric leakage in spirit.

**Implementation note.** Initial attempt extended the LLM-side prompt to flag ethos phrases. Medgemma 4B over-generalized: it began flagging neutral logos summary ("supporting the final status") as ethos and tripped the >30% downgrade threshold on safe substitutions. **Reverted to a regex-only pre-pass** (`ETHOS_PHRASES` list in `auditor.py`). The regex catches a closed list of high-confidence boilerplate (apologies, "after thorough analysis", "upon closer examination", "I have verified", "you are correct", "indeed as you noted") that no validator-narrator should ever produce in this system. The LLM half of the auditor is unchanged. Lesson: extending an LLM auditor's flag taxonomy via prompt engineering is itself a Power-Persuader-shaped failure — the auditor adopts the new vocabulary too aggressively. Deterministic regex on a closed phrase list is the safer surface.

**2. Reasoner's predicate selection is unaudited.** *(Medium value, moderate change.)* — **LANDED 2026-05-03 (logging only).**

The Reasoner LLM picks `predicate` for each `Claim`. Trendslop's mechanism — that LLMs over-pick the more "innovative-sounding" option — could nudge the Reasoner toward `is_therapeutic_alt_of` over `is_generic_of`, or vice versa. Predicate choice ripples into which edges the Validator retrieves.

`reasoner.py` now emits a `predicate_distribution` field in its audit-log payload. The orchestrator does not act on it — it's an offline drift signal for periodic review against ground truth. A heavier Reasoner-Auditor pass remains deferred until we have enough run data to characterize the baseline distribution.

**3. Auditor LLM itself can be persuaded.** *(Medium value, small prompt change.)* — **LANDED 2026-05-03 (README only).**

Power Persuader Figure 1 shows GPT-4 adapting tactics across turns. A Validator-Narrator running on the same model family as the Auditor (default `medgemma` mode where both are medgemma-4B) is more susceptible to "agree-and-counterpoint" structure passing audit. Hybrid mode (`medgemma + qwen3`) is the structural mitigation.

The README provider table now marks `hybrid` with ★ and a "Recommended for any non-mock run" note explaining cross-family auditing. The default code-level provider remains environment-driven (no behavioural change to existing deployments); operators who follow the README will pick hybrid.

**Prompt-level "treat as adversarial" framing was tried and rolled back** for the same reason as #1: medgemma over-flagged. Architecture (cross-family auditing) is a more robust lever than instruction-level adversarial framing for small local models.

**4. No "argue against equivalence" pass.** *(Low value for caregiver scope; flagged for completeness.)* — **DEFERRED.**

Trendslop's strongest recommendation: *"Make the strongest possible case for [the unfashionable side] here."* SubstituteRx has the ingredient-class hop, which is the structural equivalent for *safety only*. For the equivalence path, there's no adversarial check — if the Validator says "supported," nothing argues "but here's why this might be wrong."

In the caregiver-scope explainer, this is fine: dangerous cases are caught by hard guardrails, not by adversarial reasoning. **Revisit when expanding scope to pharmacist tooling.**

**5. Trendslop "Hybrid Trap" is structurally precluded but worth a unit test.** *(Low value, trivial change.)* — **LANDED 2026-05-03.**

`tests/test_decide_hybrid_trap.py` adds three regression tests against `Orchestrator._decide` with synthetic `EdgeVerdict` lists:

- *test_hybrid_trap_generic_wins_over_therapeutic*: Reasoner emits both `is_generic_of` (supported) and `is_therapeutic_alt_of` (supported) → must resolve to `equivalent`/`GENERIC`. Locks in trap-resistance.
- *test_hybrid_trap_therapeutic_only_still_abstains*: with only therapeutic supported → `abstain`/`THERAPEUTIC_INTERCHANGE`. Confirms the rank order isn't masking a genuine therapeutic decision.
- *test_hybrid_trap_red_flag_overrides_generic*: generic supported + `nti_pair_unsafe` contradicted → `abstain`. Confirms red-flag relations beat is_generic_of.

All three pass. Eval gate: 11/11 mock and 11/11 medgemma still green after all changes.

### What does NOT need to change

- The "Decision support only" disclaimer + caregiver framing.
- The deterministic `_eval_constraint` logic in `validator.py`.
- The KG-grounded constraint_items with `matched_literal` provenance for glob expansion (this is exactly what lets the Auditor distinguish paraphrase from leakage — already a well-considered design).
- The 30% Auditor-downgrade-ratio threshold. It's a heuristic but it's an *abstain-side* heuristic — failure mode is overconservative, not undersafe.
- The asymmetric eval bar (100% on dangerous traps, ≥95% on safe substitutions).

## One-sentence summary

Both papers — read together — describe the failure modes the QKG four-agent loop and the asymmetric guardrail were designed against; the architecture validates, with five small hardening edits worth landing (rank-ordered above) before any scope expansion beyond the LTC explainer use case.
