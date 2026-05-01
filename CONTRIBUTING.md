# Contributing

This is a research prototype, not a production library — but PRs that strengthen the architecture or fix the eval are welcome.

## Dev setup

```bash
uv venv --python python3.11 .venv
uv pip install -e ".[dev]"
uv pip install streamlit
```

## Before opening a PR

```bash
# Asymmetric red-team gate (must pass on at least mock + ollama)
.venv/bin/python -m tests.eval.run_eval --ablation

# Lint
.venv/bin/ruff check src tests

# Type check (best-effort; pyright noise around src layout is benign)
```

A dangerous-trap regression in any provider mode blocks the build.

## Adding a new red-team case

1. Add the case to `tests/eval/cases.py` under the right category (`safe`, `dangerous`, or `leakage`).
2. If it requires KG support, add the drug to `data/seed_drugs.json` and any new edge to `data/seed_edges.json`. Edges carry `constraint_items` — see SPEC §5 for the schema.
3. Re-run `--ablation` and update `docs/process/EVAL_ABLATION.md`.

## Filing issues

Include:
- Provider mode (`mock` / `ollama` / `anthropic`)
- Model name
- The bottle / MAR / resident_id triple
- The audit log lines for the run (filter by `run_id`)

## Out of scope

- Real PHI ingest — synthetic data only.
- Prescribing / EHR write paths — read-only by design.
- Bundling third-party drug data with non-public-domain license terms.
