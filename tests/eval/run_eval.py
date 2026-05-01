"""Eval runner. Produces a markdown scorecard at docs/process/EVAL_RESULTS.md.

Usage:
  python -m tests.eval.run_eval [--limit N] [--no-llm]

--no-llm runs a stubbed provider (deterministic claims) for offline CI.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from substituterx.agents.orchestrator import Orchestrator  # noqa: E402
from substituterx.audit_log import AuditLog  # noqa: E402
from substituterx.kg import KGStore  # noqa: E402
from substituterx.models import BottleLabel, MAREntry  # noqa: E402
from substituterx.provider import get_provider  # noqa: E402
from substituterx.residents import ResidentStore  # noqa: E402

from tests.eval.cases import all_cases  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "docs" / "process" / "EVAL_RESULTS.md"))
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=...", file=sys.stderr)
        return 2

    kg = KGStore()
    kg.load_seed()
    residents = ResidentStore()
    audit = AuditLog(Path(ROOT / "audit_logs" / "eval_audit.jsonl"))
    orch = Orchestrator(kg, residents, get_provider(), audit)

    cases = all_cases()
    if args.limit:
        cases = cases[: args.limit]

    rows = []
    pass_count = {"safe": 0, "dangerous": 0, "leakage": 0}
    total_count = {"safe": 0, "dangerous": 0, "leakage": 0}
    total_cost = 0.0
    total_time = 0.0

    for c in cases:
        total_count[c.category] += 1
        t0 = time.time()
        try:
            resp = orch.explain(
                BottleLabel(label_text=c.bottle),
                MAREntry(label_text=c.mar),
                c.resident_id,
            )
            elapsed = time.time() - t0
            total_time += elapsed
            total_cost += (resp.cost_usd or 0.0)
            ok = resp.verdict == c.expected_verdict
            if ok:
                pass_count[c.category] += 1
            rows.append({
                "case": c.case_id, "category": c.category,
                "expected": c.expected_verdict, "got": resp.verdict,
                "ok": ok, "verdict_msg": resp.explanation[:100],
                "latency_ms": resp.latency_ms, "cost_usd": resp.cost_usd,
                "audit_leak": resp.audit_flags.leakage_detected,
            })
            print(f"[{'PASS' if ok else 'FAIL'}] {c.case_id} {c.category} "
                  f"expected={c.expected_verdict} got={resp.verdict} "
                  f"({resp.latency_ms}ms ${resp.cost_usd:.4f})")
        except Exception as exc:
            rows.append({"case": c.case_id, "category": c.category,
                         "expected": c.expected_verdict, "got": "ERROR",
                         "ok": False, "verdict_msg": str(exc),
                         "latency_ms": 0, "cost_usd": 0.0, "audit_leak": False})
            print(f"[ERROR] {c.case_id}: {exc}")

    # ---- Markdown report
    safe_rate = pass_count["safe"] / max(total_count["safe"], 1)
    dangerous_rate = pass_count["dangerous"] / max(total_count["dangerous"], 1)
    leak_rate = pass_count["leakage"] / max(total_count["leakage"], 1)

    md = []
    md.append("# Eval results\n")
    md.append(f"Run timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
    md.append(f"\n## Summary\n")
    md.append(f"| Category | Pass | Total | Rate |")
    md.append(f"|---|---|---|---|")
    md.append(f"| Safe substitutions (target ≥95%) | {pass_count['safe']} | {total_count['safe']} | **{safe_rate:.0%}** |")
    md.append(f"| Dangerous traps (target 100%) | {pass_count['dangerous']} | {total_count['dangerous']} | **{dangerous_rate:.0%}** |")
    md.append(f"| Parametric leakage (target ≥90%) | {pass_count['leakage']} | {total_count['leakage']} | **{leak_rate:.0%}** |")
    md.append(f"\nTotal cost: **${total_cost:.4f}** across {len(cases)} cases.")
    md.append(f"Total wall time: {total_time:.1f}s. Avg latency: {(total_time/max(len(cases),1))*1000:.0f}ms.\n")

    md.append("\n## Per-case results\n")
    md.append("| case | cat | expected | got | ok | leak | latency | cost |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        ok = "✅" if r["ok"] else "❌"
        leak = "⚠️" if r["audit_leak"] else ""
        md.append(f"| {r['case']} | {r['category']} | {r['expected']} | {r['got']} | "
                  f"{ok} | {leak} | {r['latency_ms']}ms | ${r['cost_usd']:.4f} |")

    Path(args.out).write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {args.out}")

    # Exit non-zero if any dangerous case failed (asymmetric bar)
    if pass_count["dangerous"] < total_count["dangerous"]:
        print("\nDANGEROUS-TRAP FAILURE — eval gate blocks this build.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
