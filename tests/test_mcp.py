import asyncio
import os
import tempfile
import time

import pytest

pytest.importorskip("mcp")
os.environ.setdefault("AGENTOPS_DB", tempfile.mktemp(suffix=".db"))  # before importing api

from fastapi.testclient import TestClient  # noqa: E402

import mcp_server  # noqa: E402
from api import app  # noqa: E402

client = TestClient(app)
mcp_server.set_client(client)

EXPECTED = {"get_policy", "list_agents", "get_agent_trust", "list_runs", "get_run", "pause_run",
            "resume_run", "kill_run", "approve_action", "reject_action", "edit_run_memory",
            "override_tool_call"}


def wait_status(run_id, states, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        run = mcp_server.get_run(run_id)["run"]
        if run["status"] in states:
            return run
        time.sleep(0.03)
    raise AssertionError(f"never reached {states}; last={run['status']}")


def test_tools_are_registered_and_none_can_change_trust():
    result = mcp_server.mcp.list_tools()
    tools = asyncio.run(result) if asyncio.iscoroutine(result) else result
    names = {t.name for t in tools}
    assert EXPECTED <= names
    assert not any(n.startswith(("set_", "raise_", "grant_")) for n in names)


def test_approve_a_held_action_through_mcp():
    rid = client.post("/runs", json={"agent": "refunder", "agent_id": "mcp-approve-bot"}).json()["run_id"]
    run = wait_status(rid, {"waiting_approval"})
    assert run["pending"]["args"]["amount"] == 250
    assert mcp_server.approve_action(rid) == {"ok": True}
    wait_status(rid, {"done"})
    assert mcp_server.get_agent_trust("mcp-approve-bot")["score"] == 60      # 50 + 2 approved + 8 completed


def test_pause_resume_kill_through_mcp():
    rid = client.post("/runs", json={"agent": "looper", "agent_id": "mcp-kill-bot",
                                     "breaker": False, "delay": 0.05}).json()["run_id"]
    wait_status(rid, {"running"})
    mcp_server.pause_run(rid)
    wait_status(rid, {"paused"})
    mcp_server.resume_run(rid)
    wait_status(rid, {"running"})
    mcp_server.kill_run(rid)
    run = wait_status(rid, {"killed"})
    assert run["reason"] == "killed by human"


def test_errors_come_back_as_data_not_crashes():
    assert mcp_server.get_run("nope")["error"] == 404
    assert mcp_server.override_tool_call("nope", "send_email", {})["error"] == 404


def test_list_and_policy_tools():
    assert mcp_server.get_policy()["start_score"] == 50
    assert isinstance(mcp_server.list_runs(), list)
    assert isinstance(mcp_server.list_agents(), list)
