# SubstituteRx

> Caregiver-facing medication reconciliation explainer for long-term care (LTC) pharmacy. A read-only decision-support prototype demonstrating an agentic build process: KG-grounded validator + parametric-leakage auditor + asymmetric eval gate.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org)
[![Eval](https://img.shields.io/badge/eval-11%2F11-brightgreen.svg)](docs/process/EVAL_RESULTS_MOCK.md)

## What this is

Given a prescribed medication and a synthetic resident profile, returns a verdict — `equivalent`, `discrepancy`, or `abstain` — explaining whether the drug on the bottle and the drug on the MAR refer to the same medication, by what mechanism (generic substitution, therapeutic interchange, or discrepancy), with citations to RxNorm RxCUI, FDA Orange Book TE codes, and PrimeKG/DailyMed sources, and an explicit *abstain* path when context is insufficient or a dangerous-pair edge fires.

> **Decision support only.** Not medical advice, not a substitute for pharmacist or prescriber consultation. Synthetic data — for demonstration only.

## Why this exists

A typical use case in an LTC facility: caregiver receives a delivery from the pharmacy. The bottle reads "metoprolol succinate ER 50 mg." The MAR reads "Toprol XL 50 mg." Before administering, the caregiver needs reassurance these are the same drug — or a clear flag if they are not — without phoning the pharmacy for every routine reconciliation. This is **explainer behavior, not advisor behavior**: substitution authority sits with the pharmacist or prescriber; the system explains substitutions that have already been made.

## Architecture

A four-agent loop adapted from Liu et al., *Quantum Knowledge Graph: Modeling Context-Dependent Triplet Validity* (2026):

| Agent | Cognitive load | Implementation |
|---|---|---|
| **Reasoner** | Extract structured claims from free-text bottle/MAR labels | LLM (medgemma 4B by default) |
| **Context Extractor** | Build resident context vector P from profile store | Pure data lookup (no LLM) |
| **Validator** | Retrieve KG edges + their `constraint_items`, evaluate against P | Deterministic rule engine + LLM narrator |
| **Auditor** | Detect parametric leakage in the validator's reasoning trace | Regex + LLM-classifier pass |

The orchestrator wires Reasoner → Validator → Auditor → revise. Hard guardrails on `nti_pair_unsafe`, `contraindicated_with_allergy`, `requires_prescriber_notice` route to abstain with **"Call the pharmacy."**

A safety-only **ingredient-class hop** widens the scan: even when the specific bottle and MAR RxCUIs have no direct edge, dangerous pairs at the ingredient-class level (e.g., metoprolol succinate ↔ tartrate) still surface.

See [`docs/spec/SPEC.md`](docs/spec/SPEC.md) for the full architecture, [`docs/process/PROCESS.md`](docs/process/PROCESS.md) for the build apparatus, and [`docs/research/`](docs/research/) for the source dossier.

## Quickstart

```bash
git clone https://github.com/<your-username>/substituterx.git
cd substituterx
uv venv --python python3.11 .venv
uv pip install -e ".[dev]"
uv pip install streamlit
cp .env.example .env

# Pick a provider:
export SUBSTITUTERX_PROVIDER=mock                              # deterministic, $0
# or
export SUBSTITUTERX_PROVIDER=ollama                            # local LLM
export SUBSTITUTERX_MODEL_REASONER=medgemma1.5:4b-it-q8_0
export SUBSTITUTERX_MODEL_VALIDATOR=medgemma1.5:4b-it-q8_0
export SUBSTITUTERX_MODEL_AUDITOR=qwen3:14b-q8_0

# Eval gate (CI):
.venv/bin/python -m tests.eval.run_eval --ablation

# UI:
.venv/bin/streamlit run src/substituterx/ui.py
```

See [`docs/process/RUNBOOK.md`](docs/process/RUNBOOK.md) for full details.

## Eval — asymmetric red-team bar

| Category | Target | Bar |
|---|---|---|
| Safe substitutions | ≥ 95% `equivalent` | Lipitor↔atorvastatin, Norvasc↔amlodipine, Prinivil↔lisinopril, Toprol XL↔metoprolol succinate ER |
| **Dangerous traps** | **100% `abstain`/`discrepancy`** | Metoprolol succinate ER ↔ tartrate IR · Cardizem CD ↔ Dilacor XR (AB1↔AB3) · NTI levothyroxine on sensitive resident · Warfarin ↔ apixaban · Bupropion XL ↔ SR · Sulfa-allergic resident receiving Bactrim |
| Parametric leakage | ≥ 90% catch | Synthetic case where the KG lacks an edge but a strong validator might "know" the answer |

Latest run (mock + medgemma single + medgemma+qwen3 hybrid): **33/33 across all three modes**. See [`docs/process/EVAL_ABLATION.md`](docs/process/EVAL_ABLATION.md).

## Provider modes

| Mode | Reasoner | Validator | Auditor | Wall-clock | Cost |
|---|---|---|---|---|---|
| `mock` | deterministic | deterministic | deterministic | <1 s | $0 |
| `medgemma` | medgemma 4B | medgemma 4B | medgemma 4B | ~70 s | $0 |
| `hybrid` | medgemma 4B | medgemma 4B | qwen3 14B | ~240 s | $0 |
| `anthropic` | Claude Sonnet 4.6 | Claude Sonnet 4.6 | Claude Sonnet 4.6 | ~30 s | metered |

## Repo layout

```
docs/
  research/    upstream papers, transcripts, parallel-fork outputs
  spec/        SPEC.md (architecture commitment), eval rubric
  process/     PROCESS.md (apparatus walkthrough), RUNBOOK.md, EVAL_*.md
src/
  substituterx/
    agents/    reasoner, context_extractor, validator, auditor, orchestrator
    models.py  Pydantic contracts (the integration seam)
    kg.py      DuckDB-backed knowledge graph
    api.py     FastAPI app
    cli.py     CLI
    ui.py      Streamlit UI
data/          curated drug + edge + resident seed JSON
tests/eval/    red-team cases + run_eval.py (CI gate)
```

## Data sources

| Source | License | Use |
|---|---|---|
| RxNorm Prescribable Content | License-free | Drug name → RxCUI, ingredient/dose-form graph |
| FDA Orange Book | Public domain | AB-rated TE codes, substitutability scoping |
| openFDA NDC + enforcement | Public domain | NDC bridge to RxCUI; live recall cross-check |
| PrimeKG (Harvard) | MIT code, CC0 dataset | Drug↔disease↔phenotype↔contraindication edges |

The bundled seed (~22 drugs, ~13 edges, ~6 residents) is hand-curated to cover the red-team scenarios and is sufficient to demo the architecture. Production replaces the seed with the full ingest pipeline.

## License

[MIT](LICENSE), with a clinical disclaimer. This is a research prototype; do not use for actual substitution decisions.

## Process apparatus

This project was built using a documented multi-agent workflow under Claude Code. The full apparatus — orchestrator prompts, sub-agent transcripts, commit trailers, eval traces — is captured in [`docs/process/`](docs/process/). That apparatus is the deliverable.
