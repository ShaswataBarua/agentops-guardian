"""SQLite storage for runs, steps and trust events."""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

DB = os.environ.get("AGENTOPS_DB", "agentops.db")
_lock = threading.Lock()

TRUST_START = 50  # every new agent starts here

RUN_COLUMNS = {"status", "reason", "control", "decision", "override", "memory", "pending",
               "total_tokens", "total_cost"}


@contextmanager
def db():
    with _lock:
        conn = sqlite3.connect(DB, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY, agent TEXT, agent_id TEXT, status TEXT, reason TEXT,
            budget REAL, breaker_on INTEGER,
            control TEXT DEFAULT 'run',      -- run | pause | kill
            decision TEXT,                   -- approve | reject (human answer)
            override TEXT,                   -- JSON {"tool":..., "args":...} for the next step
            memory TEXT DEFAULT '{}',        -- JSON dict the agent reads
            pending TEXT,                    -- JSON of the action waiting for approval
            total_tokens INTEGER DEFAULT 0, total_cost REAL DEFAULT 0, created REAL);
        CREATE TABLE IF NOT EXISTS steps(
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, step_no INTEGER,
            tool TEXT, args TEXT, result TEXT, tokens INTEGER, cost REAL, status TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS trust_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, run_id TEXT, event TEXT,
            delta INTEGER, score_after INTEGER, reason TEXT, ts REAL);
        """)


# ---------------------------------------------------------------- runs
def create_run(run_id, agent, agent_id, budget, breaker_on):
    with db() as c:
        c.execute("INSERT INTO runs(run_id,agent,agent_id,status,budget,breaker_on,created) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (run_id, agent, agent_id, "starting", budget, int(breaker_on), time.time()))


def update(run_id, **fields):
    bad = set(fields) - RUN_COLUMNS
    if bad:
        raise ValueError(f"unknown run fields: {bad}")
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE runs SET {sets} WHERE run_id=?", (*fields.values(), run_id))


def get(run_id):
    with db() as c:
        row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["memory"] = json.loads(d["memory"] or "{}")
    d["override"] = json.loads(d["override"]) if d["override"] else None
    d["pending"] = json.loads(d["pending"]) if d["pending"] else None
    return d


def list_runs():
    with db() as c:
        rows = c.execute("SELECT run_id,agent,agent_id,status,reason,total_tokens,total_cost FROM runs "
                         "ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


def add_step(run_id, step_no, tool, args, result, tokens, cost, status):
    with db() as c:
        c.execute("INSERT INTO steps(run_id,step_no,tool,args,result,tokens,cost,status,ts) "
                  "VALUES(?,?,?,?,?,?,?,?,?)",
                  (run_id, step_no, tool, json.dumps(args), result, tokens, cost, status, time.time()))


def steps(run_id):
    with db() as c:
        rows = c.execute("SELECT * FROM steps WHERE run_id=? ORDER BY step_no", (run_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["args"] = json.loads(d["args"])
        out.append(d)
    return out


# ---------------------------------------------------------------- trust
def trust_score(agent_id):
    with db() as c:
        row = c.execute("SELECT score_after FROM trust_events WHERE agent_id=? ORDER BY id DESC LIMIT 1",
                        (agent_id,)).fetchone()
    return row["score_after"] if row else TRUST_START


def add_trust_event(agent_id, run_id, event, delta, score_after, reason):
    with db() as c:
        c.execute("INSERT INTO trust_events(agent_id,run_id,event,delta,score_after,reason,ts) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (agent_id, run_id, event, delta, score_after, reason, time.time()))


def trust_history(agent_id):
    with db() as c:
        rows = c.execute("SELECT * FROM trust_events WHERE agent_id=? ORDER BY id", (agent_id,)).fetchall()
    return [dict(r) for r in rows]


def agent_ids():
    with db() as c:
        rows = c.execute("SELECT agent_id FROM runs UNION SELECT agent_id FROM trust_events").fetchall()
    return sorted(r["agent_id"] for r in rows if r["agent_id"])
