"""Streamlit caregiver UI. Demo-grade only.

Run from the project root: streamlit run src/substituterx/ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as __main__, not as a package member, so relative imports
# fail. Add the project src/ dir to sys.path and use absolute imports.
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
    return Orchestrator(kg, residents, get_provider(), AuditLog()), residents


orch, residents = get_orchestrator()


st.set_page_config(page_title="SubstituteRx", page_icon="💊", layout="wide")
st.title("💊 SubstituteRx — Caregiver Reconciliation Explainer")

st.warning(
    "**Decision support only.** Not medical advice, not a substitute for pharmacist or "
    "prescriber consultation. Always verify against the current MAR and call your "
    "dispensing pharmacy with any discrepancy. **Synthetic data — for demonstration only.**"
)

with st.form("reconciliation"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Bottle (delivered)")
        bottle_text = st.text_input("Label text on the bottle", value="metoprolol succinate ER 50 mg")
    with col2:
        st.subheader("📋 MAR (orders)")
        mar_text = st.text_input("MAR entry", value="Toprol XL 50 mg")
    resident_id = st.selectbox("Resident", residents.all_ids())
    submitted = st.form_submit_button("Reconcile", type="primary")

if submitted:
    with st.spinner("Reasoner → Validator → Auditor..."):
        resp = orch.explain(
            BottleLabel(label_text=bottle_text),
            MAREntry(label_text=mar_text),
            resident_id,
        )

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

    with st.expander("Run telemetry"):
        st.json({
            "run_id": resp.run_id,
            "latency_ms": resp.latency_ms,
            "cost_usd": resp.cost_usd,
            "data_versions": resp.data_versions,
        })

    st.caption(resp.disclaimer)
