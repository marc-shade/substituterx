# SubstituteRx

Caregiver-facing medication substitution advisor. Read-only decision-support prototype demonstrating an agentic build process for the SoftWriters Alpha Lab interview (2026-05-04).

## What this is

Given a prescribed medication and a resident profile, returns ranked substitution candidates (generic + AB-rated therapeutic alternatives) with a **per-candidate validity verdict** conditioned on the resident's allergies, organ function, and current med list. Every candidate carries citations (RxNorm, FDA Orange Book, DailyMed) and an explicit *abstain* path when context is insufficient.

## What this is NOT

- Not a prescribing tool. Not an EHR write path.
- Not a HIPAA-cleared production system. Synthetic resident data only.
- Not a replacement for pharmacist review.

## Architecture (one paragraph)

A four-agent loop adapted from Liu et al., *Quantum Knowledge Graph: Modeling Context-Dependent Triplet Validity* (Apr 2026). **Reasoner** proposes candidates. **Context Extractor** builds the resident profile vector P. **Validator** retrieves drug-graph edges with their attached *constraint items* and tests them against P, returning supported / contradicted / unknown with citations. **Auditor** scans validator reasoning traces for parametric leakage — claims not grounded in retrieved evidence are downgraded. The reasoner consumes the validator+auditor report and revises. See `docs/spec/SPEC.md`.

## Repo layout

```
docs/
  research/    upstream papers, transcripts, fork outputs
  spec/        SPEC.md, ARCHITECTURE.md, eval rubric
  process/     PROCESS.md — how the agentic system built this
src/           Python package (substituterx/)
data/          KG ingest outputs, synthetic resident profiles
tests/         eval harness + red-team cases
scripts/       data ingest + dev workflows
```

## Quickstart

```bash
uv sync
cp .env.example .env  # set ANTHROPIC_API_KEY or AZURE_OPENAI_*
python scripts/ingest_kg.py --subset diabetes_cardiac
uvicorn substituterx.api:app --reload
pytest tests/eval -v
```

## Process apparatus

This project was built using a documented multi-agent workflow under Claude Code. The full apparatus — orchestrator prompts, sub-agent transcripts, commit trailers, eval traces — is captured in `docs/process/`. That apparatus IS the deliverable for the Alpha Lab demo.
