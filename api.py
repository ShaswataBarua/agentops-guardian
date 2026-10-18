"""Control API + dashboard. Run:  uvicorn api:app --reload
Dashboard: http://localhost:8000      API docs: http://localhost:8000/docs"""
import json
import os
import threading
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

import agents  # noqa: E402
import runner  # noqa: E402
import store  # noqa: E402
import telemetry  # noqa: E402
import trust  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="AgentOps Control API")
store.init()
telemetry.setup()  # on only if OTEL_EXPORTER_OTLP_ENDPOINT is set


class StartRun(BaseModel):
    agent: str = "looper"              # see GET /scripts
    agent_id: Optional[str] = None     # which agent identity owns the trust score (default: the script name)
    breaker: bool = True
    shield: bool = True                # scan tool results for prompt injection
    semantic: bool = True              # catch reworded loops
    budget: float = 0.05               # USD cap per run
    max_steps: int = 50                # hard cap on steps per run
    delay: float = 0.0                 # seconds between steps (use 0.4 to watch it live)
    task: Optional[str] = None         # instruction for the real LLM agent (gemini_support)


class MemoryEdit(BaseModel):
    memory: dict


class Override(BaseModel):
    tool: str
    args: dict


class TrustSet(BaseModel):
    score: int


def _run_or_404(run_id):
    r = store.get(run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    return r


# ------------------------------------------------------------------ dashboard
@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(HERE, "dashboard.html"))


# ------------------------------------------------------------------ runs
@app.get("/scripts")
def scripts():
    return [{"name": n, "description": agents.AGENT_INFO.get(n, ""),
             "available": n != "gemini_support" or bool(os.environ.get("GEMINI_API_KEY"))}
            for n in agents.AGENTS]


@app.post("/runs")
def start_run(req: StartRun):
    if req.agent not in agents.AGENTS:
        raise HTTPException(400, f"agent must be one of {list(agents.AGENTS)}")
    if req.agent == "gemini_support" and not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(400, "gemini_support needs GEMINI_API_KEY (put it in a .env file and restart)")
    agent_id = req.agent_id or req.agent
    run_id = uuid.uuid4().hex[:8]
    store.create_run(run_id, req.agent, agent_id, req.budget, req.breaker)
    if req.task:
        store.update(run_id, memory=json.dumps({"task": req.task}))
    threading.Thread(target=runner.run_agent,
                     args=(run_id, req.agent, agent_id, req.budget, req.breaker, req.delay,
                           req.shield, req.semantic, req.max_steps),
                     daemon=True).start()
    return {"run_id": run_id, "agent_id": agent_id}


@app.get("/runs")
def list_runs():
    return store.list_runs()


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    return {"run": _run_or_404(run_id), "steps": store.steps(run_id)}


@app.post("/runs/{run_id}/pause")
def pause(run_id: str):
    _run_or_404(run_id)
    store.update(run_id, control="pause")
    return {"ok": True}


@app.post("/runs/{run_id}/resume")
def resume(run_id: str):
    _run_or_404(run_id)
    store.update(run_id, control="run")
    return {"ok": True}


@app.post("/runs/{run_id}/kill")
def kill(run_id: str):
    _run_or_404(run_id)
    store.update(run_id, control="kill")
    return {"ok": True}


@app.post("/runs/{run_id}/approve")
def approve(run_id: str):
    _run_or_404(run_id)
    store.update(run_id, decision="approve")
    return {"ok": True}


@app.post("/runs/{run_id}/reject")
def reject(run_id: str):
    _run_or_404(run_id)
    store.update(run_id, decision="reject")
    return {"ok": True}


@app.patch("/runs/{run_id}/memory")
def edit_memory(run_id: str, body: MemoryEdit):
    r = _run_or_404(run_id)
    merged = {**r["memory"], **body.memory}
    store.update(run_id, memory=json.dumps(merged))
    return {"memory": merged}


@app.post("/runs/{run_id}/override")
def override(run_id: str, body: Override):
    _run_or_404(run_id)
    if body.tool not in agents.TOOLS:
        raise HTTPException(400, f"tool must be one of {list(agents.TOOLS)}")
    store.update(run_id, override=json.dumps(body.model_dump()))
    return {"ok": True}


# ------------------------------------------------------------------ trust
@app.get("/policy")
def policy():
    """The tier table, so a dashboard can show what each tier may do."""
    return {"start_score": store.TRUST_START,
            "score_changes": trust.DELTAS,
            "tiers": [{"tier": t, "name": trust.TIER_NAMES[t],
                       "refund_limit_without_approval": trust.REFUND_LIMIT.get(t)}
                      for t in range(4)]}


@app.get("/agents")
def list_agents():
    return [trust.summary(a) for a in store.agent_ids()]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    return {**trust.summary(agent_id), "history": store.trust_history(agent_id)}


@app.post("/agents/{agent_id}/trust")
def set_trust(agent_id: str, body: TrustSet):
    """Set a score by hand (demos and tests)."""
    trust.set_score(agent_id, body.score)
    return trust.summary(agent_id)
