# Runbook — How to run SubstituteRx

## Prereqs

- Python 3.11 (`/opt/homebrew/opt/python@3.11/bin/python3.11` on macOS)
- `uv` for dependency management
- Optional: local Ollama (`ollama serve`) with `mistral-small3.2:latest` or any reasoning-capable model
- Optional: Anthropic API key (will be billed; off by default)

## First-time setup

```bash
cd /Volumes/SSDRAID0/code/substituterx
uv venv --python python3.11 .venv
uv pip install -e ".[dev]"
uv pip install streamlit
cp .env.example .env
```

## The three provider modes

```bash
# Mock (deterministic, $0, sub-millisecond — best for CI gates and demo recording)
export SUBSTITUTERX_PROVIDER=mock

# Ollama local (free, no auth, ~5-15s/call depending on model)
export SUBSTITUTERX_PROVIDER=ollama
export SUBSTITUTERX_MODEL=mistral-small3.2:latest

# Anthropic (billable; explicit opt-in only)
export SUBSTITUTERX_PROVIDER=anthropic
export SUBSTITUTERX_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...

# Auto (default): tries Ollama first, falls back to Mock; never auto-bills Anthropic
unset SUBSTITUTERX_PROVIDER
```

## Run the eval gate

```bash
.venv/bin/python -m tests.eval.run_eval
# Exit code: 0 if all dangerous traps pass; non-zero on any miss.
# Writes docs/process/EVAL_RESULTS.md (and EVAL_RESULTS_OLLAMA.md when SUBSTITUTERX_PROVIDER=ollama).
```

## CLI smoke test

```bash
.venv/bin/python -m substituterx.cli "atorvastatin 40 mg" "Lipitor 40 mg" R-0004
.venv/bin/python -m substituterx.cli "metoprolol tartrate 25 mg" "Toprol XL 50 mg" R-0001  # → abstain (dangerous trap)
```

## API server

```bash
.venv/bin/uvicorn substituterx.api:app --reload --port 8001
curl http://localhost:8001/health
curl -X POST http://localhost:8001/api/explain -H 'content-type: application/json' \
  -d '{"bottle":{"label_text":"atorvastatin 40 mg"},"mar":{"label_text":"Lipitor 40 mg"},"resident_id":"R-0004"}'
```

## Caregiver UI

```bash
.venv/bin/streamlit run src/substituterx/ui.py
# Opens http://localhost:8501 with the disclaimer banner, drug+resident form, and results
```

## Inspect a run

```bash
# Find a run_id from any response, then trace it through the audit log:
RUN_ID=01j...
jq -c "select(.run_id == \"$RUN_ID\")" audit_logs/audit.jsonl
```

## Reset between demo recordings

```bash
rm -f audit_logs/*.jsonl
```
