"""Runs one agent with: human control gate, circuit breaker, trust-tier policy, injection shield, logging."""
import json
import time

import agents
import shield
import store
import telemetry
import trust
from breaker import Breaker, CircuitBreakerOpen
from semantic import SemanticLoopDetector

PRICE_PER_M = 3.0  # USD per 1M tokens - placeholder price, replace with your provider's


def finish(run_id, agent_id, status, reason, event):
    """End a run. The trust score is updated BEFORE the status, so anything that
    sees the final status also sees the new score."""
    if event:
        trust.record(agent_id, run_id, event, reason or event)
    store.update(run_id, status=status, reason=reason)
    r = store.get(run_id)
    telemetry.run_finished(run_id, status, reason, r["total_tokens"], r["total_cost"])


def gate(run_id):
    """Honour pause / kill. Returns False if the run was killed."""
    while True:
        r = store.get(run_id)
        if r["control"] == "kill":
            return False
        if r["control"] == "pause":
            if r["status"] != "paused":
                store.update(run_id, status="paused")
            time.sleep(0.05)
            continue
        if r["status"] == "paused":
            store.update(run_id, status="running")
        return True


def wait_for_approval(run_id, agent_id, tool, args, tier, why):
    """Hold an action until a human approves or rejects. Returns 'approve', 'reject' or 'kill'."""
    store.update(run_id, status="waiting_approval", decision=None,
                 pending=json.dumps({"tool": tool, "args": args, "tier": tier, "why": why}))
    while True:
        r = store.get(run_id)
        if r["control"] == "kill":
            return "kill"
        if r["decision"] in ("approve", "reject"):
            decision = r["decision"]
            store.update(run_id, status="running", pending=None, decision=None)
            trust.record(agent_id, run_id, "approved" if decision == "approve" else "rejected",
                         f"human {decision}d {tool}")
            return decision
        time.sleep(0.05)


def run_agent(run_id, agent_name, agent_id, budget, breaker_on, delay=0.0,
              shield_on=True, semantic_on=True, max_steps=50):
    breaker = Breaker(budget_usd=budget, price_per_m=PRICE_PER_M, max_steps=max_steps,
                      semantic=SemanticLoopDetector() if semantic_on else None)
    gen = agents.AGENTS[agent_name](lambda: store.get(run_id)["memory"])
    total_tokens = 0
    step_no = 0
    result = None
    started = False
    try:
        store.update(run_id, status="running")
        telemetry.run_started(run_id, agent_id, agent_name)
        while True:
            try:
                tool, args, tokens = gen.send(result) if started else next(gen)
            except StopIteration:
                break
            started = True
            step_no += 1
            if not gate(run_id):
                finish(run_id, agent_id, "killed", "killed by human", "killed")
                return
            # human override replaces this step's tool call (used once)
            r = store.get(run_id)
            if r["override"]:
                tool, args = r["override"]["tool"], r["override"]["args"]
                store.update(run_id, override=None)
            # circuit breaker
            if breaker_on:
                try:
                    breaker.check(tool, args, tokens)
                except CircuitBreakerOpen as e:
                    finish(run_id, agent_id, "tripped", str(e), "tripped")
                    return
            # trust-tier policy: does this action need a human?
            status = "ok"
            tier = trust.tier_for(store.trust_score(agent_id))
            ask, why = trust.needs_approval(tool, args, tier)
            if ask:
                decision = wait_for_approval(run_id, agent_id, tool, args, tier, why)
                if decision == "kill":
                    finish(run_id, agent_id, "killed", "killed by human", "killed")
                    return
                if decision == "reject":
                    store.add_step(run_id, step_no, tool, args, "DENIED by human", 0, 0.0, "rejected")
                    telemetry.step(run_id, step_no, tool, 0, 0.0, "rejected", store.trust_score(agent_id))
                    result ="DENIED by human: this action was rejected, do not retry it"
                    continue
                status = "approved"
            # run the tool
            fn = agents.TOOLS.get(tool)
            if fn is None:
                result, status = f"ERROR: unknown tool '{tool}'", "error"
            else:
                try:
                    result = str(fn(**args))
                except TypeError as e:
                    result, status = f"ERROR: bad arguments for {tool}: {e}", "error"
            total_tokens += tokens
            cost = tokens / 1_000_000 * PRICE_PER_M
            total_cost = total_tokens / 1_000_000 * PRICE_PER_M
            # injection shield: scan what the tool returned BEFORE the agent sees it
            hits = shield.scan(result) if shield_on else []
            if hits:
                store.add_step(run_id, step_no, tool, args,
                               f"[BLOCKED: {', '.join(hits)}] {result[:160]}", tokens, cost, "quarantined")
                store.update(run_id, total_tokens=total_tokens, total_cost=total_cost)
                telemetry.step(run_id, step_no, tool, tokens, cost, "quarantined", store.trust_score(agent_id))
                finish(run_id, agent_id, "quarantined",
                       f"prompt injection in {tool} output: {', '.join(hits)}", "injection")
                return
            store.add_step(run_id, step_no, tool, args, result, tokens, cost, status)
            store.update(run_id, total_tokens=total_tokens, total_cost=total_cost)
            telemetry.step(run_id, step_no, tool, tokens, cost, status, store.trust_score(agent_id))
            if delay:
                time.sleep(delay)
        finish(run_id, agent_id, "done", None, "completed")
    except Exception as e:  # never let a thread die silently
        store.update(run_id, status="error", reason=repr(e))
        telemetry.run_finished(run_id, "error", repr(e))
