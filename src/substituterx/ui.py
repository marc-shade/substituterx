"""Streamlit caregiver UI. Demo-grade only.

Run from the project root: streamlit run src/substituterx/ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st
from substituterx.agents.orchestrator import Orchestrator
from substituterx.audit_log import AuditLog
from substituterx.kg import KGStore
from substituterx.models import BottleLabel, MAREntry
from substituterx.provider import get_provider
from substituterx.residents import ResidentStore


@st.cache_resource
def get_orchestrator():
    kg = KGStore()
    kg.load_seed()
    residents = ResidentStore()
    orch = Orchestrator(kg, residents, get_provider(), AuditLog())
    model_assignment = {
        "reasoner": getattr(orch.reasoner.provider, "model", "?"),
        "validator": getattr(orch.validator.provider, "model", "?"),
        "auditor": getattr(orch.auditor.provider, "model", "?"),
    }
    return orch, residents, model_assignment


orch, residents, MODEL_ASSIGNMENT = get_orchestrator()


st.set_page_config(page_title="SubstituteRx", page_icon="💊", layout="wide")
st.title("💊 SubstituteRx — Caregiver Reconciliation Explainer")

st.warning(
    "**Decision support only.** Not medical advice, not a substitute for pharmacist or "
    "prescriber consultation. Always verify against the current MAR and call your "
    "dispensing pharmacy with any discrepancy. **Synthetic data — for demonstration only.**"
)

with st.sidebar:
    st.subheader("Agent model assignment")
    for role, model in MODEL_ASSIGNMENT.items():
        st.markdown(f"- **{role}** &nbsp; `{model}`")
    st.caption("Per-agent overrides via `SUBSTITUTERX_MODEL_<ROLE>` env vars.")

# Query-param deeplinking. Lets the operator share a URL that pre-fills the form
# (`?bottle=...&mar=...&resident=R-0004`) and lets headless test harnesses commit
# values that bypass the BaseWeb selectbox's React-state mismatch with raw DOM writes.
qp = st.query_params
_resident_options = residents.all_ids()
_qp_resident = qp.get("resident", "")
_default_resident_idx = (
    _resident_options.index(_qp_resident) if _qp_resident in _resident_options else 0
)

with st.form("reconciliation"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Bottle (delivered)")
        bottle_text = st.text_input(
            "Label text on the bottle",
            value=qp.get("bottle", "metoprolol succinate ER 50 mg"),
        )
    with col2:
        st.subheader("📋 MAR (orders)")
        mar_text = st.text_input(
            "MAR entry",
            value=qp.get("mar", "Toprol XL 50 mg"),
        )
    resident_id = st.selectbox("Resident", _resident_options, index=_default_resident_idx)
    submitted = st.form_submit_button("Reconcile", type="primary")

if submitted:
    # Per-agent live progress with st.status
    progress_box = st.status("Running pipeline…", expanded=True)
    stage_lines: list[str] = []

    LABELS = {
        "begin": "▸ Orchestrator starting",
        "resolve": "▸ Resolving RxCUIs from labels",
        "context_extractor": "▸ Loading resident context",
        "reasoner": "▸ Reasoner",
        "validator": "▸ Validator (KG-grounded constraint evaluation)",
        "auditor": "▸ Auditor (parametric-leakage scan)",
        "decide": "▸ Decision logic",
    }

    def progress_cb(stage: str, detail: str):
        label = LABELS.get(stage, f"▸ {stage}")
        line = label + (f" — `{detail}`" if detail else "")
        stage_lines.append(line)
        progress_box.update(label=line)
        progress_box.write(line)

    resp = orch.explain(
        BottleLabel(label_text=bottle_text),
        MAREntry(label_text=mar_text),
        resident_id,
        progress=progress_cb,
    )
    progress_box.update(state="complete", label=f"Pipeline complete in {resp.latency_ms} ms",
                        expanded=False)

    color = {"equivalent": "green", "discrepancy": "red", "abstain": "orange"}[resp.verdict]
    st.markdown(f"## :{color}[{resp.verdict.upper()}] — {resp.mechanism.value.replace('_',' ')}")
    st.write(resp.explanation)

    if resp.edge_verdicts:
        st.subheader("Edge verdicts (KG-grounded)")
        st.dataframe([
            {"edge": v.edge_id, "relation": v.relation,
             "subject→object": f"{v.subject}→{v.object}",
             "status": v.status, "reasoning": v.reasoning,
             "citations": ", ".join(c.identifier for c in v.citations)}
            for v in resp.edge_verdicts
        ], use_container_width=True)

    if resp.audit_flags.leakage_detected:
        st.error("⚠️ Auditor detected parametric leakage")
        st.json([f.model_dump() for f in resp.audit_flags.flags])
    else:
        st.success("✓ Auditor: no parametric leakage detected")

    with st.expander("Run telemetry", expanded=True):
        st.json({
            "run_id": resp.run_id,
            "latency_ms": resp.latency_ms,
            "cost_usd": resp.cost_usd,
            "data_versions": resp.data_versions,
            "model_assignment": MODEL_ASSIGNMENT,
        })

    st.caption(resp.disclaimer)
