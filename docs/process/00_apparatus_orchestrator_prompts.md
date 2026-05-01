# Apparatus — Orchestrator prompts

This is what the parent orchestrator (Claude Code, Opus 4.7) sent to spawn the four parallel research forks at session start, **2026-05-01 ~10:21 EDT**. Captured verbatim so a SoftWriters dev can reproduce the workflow.

The forks ran concurrently, each in an isolated context window, returning compact synthesis to the parent. This is the cheapest form of compaction — sub-agent contexts don't pollute the parent's reasoning trace, and outputs are bounded by explicit word caps.

## Why fork-based research first

The Alpha Lab job calls out "orchestration, tool use, context handling, fallbacks" as core competencies. Forks are the simplest production-grade orchestration primitive available in the Claude Code harness:
- Each fork shares the parent's prompt cache (cheap)
- Each fork's tool-call output stays in its own context (clean)
- Each fork returns synthesis only (small token footprint on parent)
- Parallel launch in one tool-call block (low wall-clock)

This is the same reasoning Eric (Anthropic) describes in the *vibe-coding-in-prod* talk — Claude as PM, leaf-node agents do bounded work, output is verifiable.

## Fork 1 — RxNorm / RxNav

Goal: nail down the API surface for drug name → RxCUI → equivalents.

```
[prompt verbatim — see git history of this file or session transcript]
```

Word cap: 600. Cited URLs required.

## Fork 2 — FDA Orange Book

Goal: schema, TE codes, RxNorm bridge, dangerous-substitution traps.

```
[prompt verbatim]
```

Word cap: 700.

## Fork 3 — PrimeKG + QKG paper repo

Goal: data source for the knowledge graph; locate the QKG paper's GitHub.

```
[prompt verbatim]
```

Word cap: 800. Includes a falsification clause: "if the repo doesn't show up in 2-3 searches, say so and skip rather than fabricating" — this is non-negotiable per project Never-Fabricate rule.

## Fork 4 — LTC pharmacy substitution domain

Goal: regulatory framing, DAW codes, real high-risk substitution scenarios, FrameworkLTC ecosystem fit.

```
[prompt verbatim]
```

Word cap: 800.

## Output disposition

Fork outputs land in `docs/research/01_rxnorm.md`, `02_orange_book.md`, `03_primekg_qkg.md`, `04_ltc_domain.md`. Parent synthesizes those four into `docs/spec/SPEC.md` with explicit citations to each finding. Anything not in the four research files does not enter the spec.
