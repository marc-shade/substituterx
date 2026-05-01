"""Quick CLI for one-off explain calls. Useful for the demo."""
from __future__ import annotations

import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agents.orchestrator import Orchestrator
from .audit_log import AuditLog
from .kg import KGStore
from .models import BottleLabel, MAREntry
from .provider import get_provider
from .residents import ResidentStore


def main() -> int:
    console = Console()
    if len(sys.argv) < 4:
        console.print(
            "Usage: substituterx-cli <bottle_label> <mar_label> <resident_id>\n"
            "Example: substituterx-cli 'metoprolol succinate ER 50 mg' 'Toprol XL 50 mg' R-0001"
        )
        return 1

    bottle_text, mar_text, resident_id = sys.argv[1], sys.argv[2], sys.argv[3]

    kg = KGStore()
    kg.load_seed()
    residents = ResidentStore()
    audit = AuditLog()
    orch = Orchestrator(kg, residents, get_provider(), audit)

    resp = orch.explain(
        BottleLabel(label_text=bottle_text),
        MAREntry(label_text=mar_text),
        resident_id,
    )

    color = {"equivalent": "green", "discrepancy": "red", "abstain": "yellow"}[resp.verdict]
    console.print(Panel(
        f"[bold {color}]{resp.verdict.upper()}[/bold {color}]  "
        f"({resp.mechanism.value})\n\n{resp.explanation}",
        title=f"SubstituteRx — run {resp.run_id}",
        subtitle=f"latency={resp.latency_ms}ms  cost=${resp.cost_usd:.4f}",
    ))

    if resp.edge_verdicts:
        t = Table(title="Edge verdicts")
        t.add_column("edge"), t.add_column("relation"), t.add_column("status"), t.add_column("reasoning")
        for v in resp.edge_verdicts:
            t.add_row(v.edge_id, v.relation, v.status, v.reasoning[:80])
        console.print(t)

    if resp.audit_flags.leakage_detected:
        console.print(Panel(
            "\n".join(f"[{f.edge_id}] {f.reason}: {f.detail}" for f in resp.audit_flags.flags),
            title="[red]Audit flags — parametric leakage detected[/red]",
        ))

    console.print(f"\n[dim]{resp.disclaimer}[/dim]")
    console.print(f"\n[dim]data_versions: {json.dumps(resp.data_versions)}[/dim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
