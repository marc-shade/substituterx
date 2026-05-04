# SubstituteRx

> Caregiver-facing medication reconciliation explainer for long-term care (LTC) pharmacy. A read-only decision-support prototype demonstrating an agentic build process: KG-grounded validator + parametric-leakage auditor + asymmetric eval gate.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org)
[![Eval](https://img.shields.io/badge/eval-11%2F11-brightgreen.svg)](docs/process/EVAL_RESULTS_MOCK.md)
[![ruff](https://img.shields.io/badge/ruff-clean-brightgreen.svg)](https://docs.astral.sh/ruff/)
[![vulture](https://img.shields.io/badge/vulture-clean-brightgreen.svg)](https://github.com/jendrikseipp/vulture)
[![deptry](https://img.shields.io/badge/deptry-clean-brightgreen.svg)](https://deptry.com)
[![radon MI](https://img.shields.io/badge/radon%20MI-A-brightgreen.svg)](https://radon.readthedocs.io)

## What this is

Given a prescribed medication and a synthetic resident profile, returns a verdict — `equivalent`, `discrepancy`, or `abstain` — explaining whether the drug on the bottle and the drug on the MAR refer to the same medication, by what mechanism (generic substitution, therapeutic interchange, or discrepancy), with citations to RxNorm RxCUI, FDA Orange Book TE codes, and PrimeKG/DailyMed sources, and an explicit *abstain* path when context is insufficient or a dangerous-pair edge fires.

> **Decision support only.** Not medical advice, not a substitute for pharmacist or prescriber consultation. Synthetic data — for demonstration only.

## Why this exists

A typical use case in an LTC facility: caregiver receives a delivery from the pharmacy. The bottle reads "metoprolol succinate ER 50 mg." The MAR reads "Toprol XL 50 mg." Before administering, the caregiver needs reassurance these are the same drug — or a clear flag if they are not — without phoning the pharmacy for every routine reconciliation. This is **explainer behavior, not advisor behavior**: substitution authority sits with the pharmacist or prescriber; the system explains substitutions that have already been made.

## Architecture

A four-agent loop adapted from Liu et al., *Quantum Knowledge Graph: Modeling Context-Dependent Triplet Validity* (2026):

| Agent | Cognitive load | Implementation |
|---|---|---|
| **Reasoner** | Extract structured claims from free-text bottle/MAR labels | Local LLM (medgemma 4B by default) |
| **Context Extractor** | Build resident context vector P from profile store | Pure data lookup (no LLM) |
| **Validator** | Retrieve KG edges + their `constraint_items`, evaluate against P | Deterministic rule engine + local-LLM narrator |
| **Auditor** | Detect parametric leakage in the validator's reasoning trace | Regex + local-LLM classifier pass |

**Local-only by design.** The application ships no cloud LLM client. All inference
runs against your configured Ollama host (default `http://localhost:11434`) or the
deterministic Mock provider. The contract is enforced by `tests/test_local_only.py`
and verified by `scripts/verify_local_only.sh` — see [§Local-only verification](#local-only-verification) below.

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

# Pick a provider (both run on your machine — no cloud calls):
export SUBSTITUTERX_PROVIDER=mock                              # deterministic, $0
# or
export SUBSTITUTERX_PROVIDER=ollama                            # local LLM via Ollama
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

## Provider modes (all local)

| Mode | Reasoner | Validator | Auditor | Wall-clock | Cost |
|---|---|---|---|---|---|
| `mock` | deterministic | deterministic | deterministic | <1 s | $0 |
| `medgemma` | medgemma 4B | medgemma 4B | medgemma 4B | ~70 s | $0 |
| **`hybrid`** ★ | medgemma 4B | medgemma 4B | qwen3 14B | ~240 s | $0 |

★ **Recommended for any non-mock run.** Cross-family auditing — qwen3 reviewing medgemma's narration — reduces shared rhetorical priors. Same-family setups risk the Auditor accepting "agree-and-counterpoint" or effort-transparency phrasing the Validator inserted under stress (see `docs/research/05_genai_persuasion_and_trendslop.md`).

## Local-only verification

This codebase ships **no cloud LLM client** by design. Safety, security, and privacy
guarantees fall out of that single property: no API keys, no usage metering, no
prompt or PHI ever leaves the operator's machine.

The contract is enforced and verifiable:

```bash
# 1) No cloud SDK in dependencies, no AnthropicProvider/AzureProvider in source.
.venv/bin/python -m pytest tests/test_local_only.py -v

# 2) End-to-end: run the eval gate with the wider network blocked.
#    Only the configured Ollama host (default 127.0.0.1:11434) is reachable.
bash scripts/verify_local_only.sh
```

`tests/test_local_only.py` asserts: `anthropic` is not importable, `provider.py`
defines no class whose name contains `Anthropic`/`Azure`/`OpenAI`, and `get_provider`
only ever returns `OllamaProvider` or `MockProvider`. Any future regression would
fail the gate before merge.

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

## Code quality

After the eval bar was met, the codebase was put through a five-tool static-analysis sweep:

```bash
uvx ruff@latest check src tests       # lint, unused imports/vars, stale-noqa
uvx vulture --min-confidence 70 src tests   # dead funcs/classes/attrs
uvx deptry .                          # unused / missing / transitive deps
uvx radon mi src tests -s             # maintainability index
.venv/bin/python -m tests.eval.run_eval --mode mock   # red-team eval gate
```

Result: **all clean.** ruff passes, vulture clean, deptry clean, every file A-rated for maintainability, eval 11/11. See [`docs/process/PROCESS.md` §11](docs/process/PROCESS.md) for the full cleanup notes including which D-rated cyclomatic blocks were kept on purpose and why.

## Process apparatus

This project was built using a documented multi-agent workflow under Claude Code. The full apparatus — orchestrator prompts, sub-agent transcripts, commit trailers, eval traces, post-build code-quality sweep — is captured in [`docs/process/`](docs/process/). That apparatus is the deliverable.

### How we don't ship vibe-coded slop

The most load-bearing process artifact is [**`docs/process/AI_DEV_PROCESS.md`**](docs/process/AI_DEV_PROCESS.md). It walks through the *six rounds of post-build theater hunting* that found and fixed 21 distinct bugs (7 of them safety-critical "right answer, wrong reason" cases the original eval gate could not detect), the regression locks that prevent them from reappearing, and the verification gates that produce green status one can cite rather than infer.

Every fix in that history is traceable to a commit, a falsifying scenario, and a test that fails without it. The methodology is the showcase.
