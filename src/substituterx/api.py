"""FastAPI app exposing the explain endpoint (SPEC §7)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from .audit_log import AuditLog
from .agents.orchestrator import Orchestrator
from .kg import KGStore
from .models import ExplainRequest, ExplainResponse
from .provider import get_provider
from .residents import ResidentStore


logger = logging.getLogger(__name__)
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


@app.get("/audit/{run_id}")
def audit(run_id: str):
    """Return the JSON-Lines audit trail for a single run_id. Useful for operator
    debugging: `curl /audit/<run_id>` returns every agent step recorded for that
    run. Reads from `SUBSTITUTERX_AUDIT_LOG` (default `./audit_logs/audit.jsonl`).
    """
    if not run_id or len(run_id) > 64 or not run_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid run_id")
    return {"run_id": run_id, "events": _state["audit"].read_run(run_id)}


@app.post("/api/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest):
    try:
        return _state["orchestrator"].explain(req.bottle, req.mar, req.resident_id)
    except Exception as exc:
        # Don't echo internal exception text back to the client — could leak schema,
        # paths, or stack details. Log it server-side and return a generic 500 so
        # operators can correlate via the audit log run_id.
        logger.exception("explain pipeline failure")
        raise HTTPException(
            status_code=500,
            detail="Internal pipeline failure — see server logs.",
        ) from exc
