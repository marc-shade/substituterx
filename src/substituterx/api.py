"""FastAPI app exposing the explain endpoint (SPEC §7)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from .audit_log import AuditLog
from .agents.orchestrator import Orchestrator
from .kg import KGStore
from .models import ExplainRequest, ExplainResponse
from .provider import get_provider
from .residents import ResidentStore


_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    kg = KGStore()
    kg.load_seed()
    _state["kg"] = kg
    _state["residents"] = ResidentStore()
    _state["audit"] = AuditLog()
    _state["orchestrator"] = Orchestrator(
        kg, _state["residents"], get_provider(), _state["audit"],
    )
    yield


app = FastAPI(title="SubstituteRx", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "drugs": _state["kg"].con.execute(
        "SELECT COUNT(*) FROM drugs"
    ).fetchone()[0]}


@app.get("/residents")
def residents():
    return {"residents": _state["residents"].all_ids()}


@app.post("/api/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest):
    try:
        return _state["orchestrator"].explain(req.bottle, req.mar, req.resident_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
