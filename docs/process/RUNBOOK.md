# Runbook — How to run SubstituteRx

## Prereqs

- Python **3.11** (3.12+ should work but is not the test target)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Optional: local [Ollama](https://ollama.com) with at least one reasoning-capable model
- Optional: Anthropic API key (billable; off by default)

## First-time setup

```bash
git clone https://github.com/<your-username>/substituterx.git
cd substituterx
uv venv --python python3.11 .venv
uv pip install -e ".[dev]"
uv pip install streamlit
cp .env.example .env
```

## Provider modes

The agent layer is provider-agnostic. Pick one:

```bash
# Mock — deterministic rule-based provider. $0, sub-millisecond.
# Best for CI gates and demo recording. No LLM in the safety path.
export SUBSTITUTERX_PROVIDER=mock

# Ollama — local LLM. Free, no auth, ~5-15s per call depending on model.
export SUBSTITUTERX_PROVIDER=ollama
export SUBSTITUTERX_MODEL=mistral-small3.2:latest

# Per-agent overrides (recommended for production-shape demo)
export SUBSTITUTERX_MODEL_REASONER=medgemma1.5:4b-it-q8_0
export SUBSTITUTERX_MODEL_VALIDATOR=medgemma1.5:4b-it-q8_0
export SUBSTITUTERX_MODEL_AUDITOR=qwen3:14b-q8_0

# Anthropic — billable; explicit opt-in only.
export SUBSTITUTERX_PROVIDER=anthropic
export SUBSTITUTERX_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...

# Auto (default): tries Ollama first, falls back to Mock.
# Never auto-bills Anthropic.
unset SUBSTITUTERX_PROVIDER
```

## Eval gate (asymmetric red-team)

```bash
# Single-mode (current env)
.venv/bin/python -m tests.eval.run_eval --mode mock
.venv/bin/python -m tests.eval.run_eval --mode hybrid     # medgemma + qwen3:14b
.venv/bin/python -m tests.eval.run_eval --mode medgemma   # single model

# All three modes back-to-back with side-by-side comparison
.venv/bin/python -m tests.eval.run_eval --ablation
```

The runner exits non-zero on **any** dangerous-trap miss. CI-grade gate.

## CLI smoke test

```bash
.venv/bin/python -m substituterx.cli "atorvastatin 40 mg" "Lipitor 40 mg" R-0004
.venv/bin/python -m substituterx.cli "metoprolol tartrate 25 mg" "Toprol XL 50 mg" R-0001
# → equivalent — generic
# → abstain — discrepancy (ingredient-class hop fires)
```

## API server

```bash
.venv/bin/uvicorn substituterx.api:app --reload --port 8001
curl http://localhost:8001/health
curl -X POST http://localhost:8001/api/explain -H 'content-type: application/json' \
  -d '{"bottle":{"label_text":"atorvastatin 40 mg"},"mar":{"label_text":"Lipitor 40 mg"},"resident_id":"R-0004"}'
```

## Caregiver UI (Streamlit)

```bash
.venv/bin/streamlit run src/substituterx/ui.py
# http://localhost:8501
```

The UI displays the live agent progress, edge verdicts with KG citations, the auditor's parametric-leakage scan result, and a per-run telemetry panel including model assignment.

## Inspect a run

```bash
# Each response carries a run_id. Trace it:
RUN_ID=<paste from a response>
jq -c "select(.run_id == \"$RUN_ID\")" audit_logs/audit.jsonl
```

## Reset between demo recordings

```bash
rm -f audit_logs/*.jsonl
```

## Repo layout

```
docs/
  research/    upstream papers, transcripts, fork outputs
  spec/        SPEC.md, ARCHITECTURE.md, eval rubric
  process/     PROCESS.md — how the agentic system built this
src/           Python package (substituterx/)
data/          KG ingest seed + synthetic resident profiles
tests/         eval harness + red-team cases
```
