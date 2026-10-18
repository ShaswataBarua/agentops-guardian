"""MCP server: lets an MCP client (Claude Desktop, Cursor, MCP Inspector...) supervise AgentOps runs.

Start the API first:   uvicorn api:app
Then run this server:  python mcp_server.py            (stdio transport)
Try it in a browser:   npx @modelcontextprotocol/inspector python mcp_server.py
Point it at another host with:  AGENTOPS_URL=https://your-space.hf.space python mcp_server.py

SECURITY: give this server to the HUMAN SUPERVISOR's client, never to the agent being
supervised. It can approve actions and kill runs; an agent that could call approve_action on
its own request would defeat the whole point. There is deliberately NO tool that changes a
trust score: trust is earned from events, and nothing here can hand it out.
"""
import os

import httpx

try:  # MCP SDK 2.x renamed FastMCP to MCPServer (same .tool() and .run())
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:  # MCP SDK 1.x
        from mcp.server.fastmcp import FastMCP
    except ImportError:  # some 1.x versions export it from mcp.server
        from mcp.server import FastMCP

BASE = os.environ.get("AGENTOPS_URL", "http://localhost:8000")
_client = None


def client():
    global _client
    if _client is None:
        _client = httpx.Client(base_url=BASE, timeout=10)
    return _client


def set_client(c):
    """Swap the HTTP client (the tests pass FastAPI's TestClient here)."""
    global _client
    _client = c


def _call(method, path, **kwargs):
    r = client().request(method, path, **kwargs)
    if r.status_code >= 400:
        return {"error": r.status_code, "detail": r.text}
    return r.json()


mcp = FastMCP("agentops")


@mcp.tool()
def get_policy() -> dict:
    """Show the trust rules: starting score, score changes per event, and what each tier may do alone."""
    return _call("GET", "/policy")


@mcp.tool()
def list_agents() -> list:
    """List every agent with its trust score, tier and a plain-English explanation of why."""
    return _call("GET", "/agents")


@mcp.tool()
def get_agent_trust(agent_id: str) -> dict:
    """One agent's trust score, tier and full history of score changes with reasons."""
    return _call("GET", f"/agents/{agent_id}")


@mcp.tool()
def list_runs() -> list:
    """List runs, newest first, with status, stop reason, tokens and cost."""
    return _call("GET", "/runs")


@mcp.tool()
def get_run(run_id: str) -> dict:
    """One run: status, stop reason, pending approval (if any), cost, and its last 20 steps."""
    data = _call("GET", f"/runs/{run_id}")
    if "steps" in data:
        data["total_steps"] = len(data["steps"])
        data["steps"] = data["steps"][-20:]
    return data


@mcp.tool()
def pause_run(run_id: str) -> dict:
    """Freeze a run before its next step. Resume it with resume_run."""
    return _call("POST", f"/runs/{run_id}/pause")


@mcp.tool()
def resume_run(run_id: str) -> dict:
    """Continue a paused run."""
    return _call("POST", f"/runs/{run_id}/resume")


@mcp.tool()
def kill_run(run_id: str) -> dict:
    """Stop a run for good. The agent loses trust for being killed."""
    return _call("POST", f"/runs/{run_id}/kill")


@mcp.tool()
def approve_action(run_id: str) -> dict:
    """Approve the action a run is waiting on (see pending in get_run)."""
    return _call("POST", f"/runs/{run_id}/approve")


@mcp.tool()
def reject_action(run_id: str) -> dict:
    """Reject the action a run is waiting on. The agent is told it was denied."""
    return _call("POST", f"/runs/{run_id}/reject")


@mcp.tool()
def edit_run_memory(run_id: str, memory: dict) -> dict:
    """Merge new values into the run's memory. The agent reads them on its next step."""
    return _call("PATCH", f"/runs/{run_id}/memory", json={"memory": memory})


@mcp.tool()
def override_tool_call(run_id: str, tool: str, args: dict) -> dict:
    """Replace the agent's NEXT tool call with this one (used once). tool must be a known tool name."""
    return _call("POST", f"/runs/{run_id}/override", json={"tool": tool, "args": args})


if __name__ == "__main__":
    mcp.run()
