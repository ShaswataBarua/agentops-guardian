# Submission text (adapt to the form's fields)

Check the real form first: the field names and length limits were not visible to me. Replace the [brackets].

**Project name:** AgentOps: Earned Autonomy for AI Agents

**Track / challenge:** InfraSphere AI > AgentOps ("Reliable, governable agent systems"; details: MCP + observability + evaluation)

**One-line pitch:** A control layer that stops runaway AI agents and lets each agent earn its permissions through a trust score, like a credit limit.

**Problem:** Businesses want AI agents to act (refund, email, update records) but cannot trust them to run unsupervised. A single loop can burn the budget, and a poisoned email can trick an agent into a large refund. Today the choice is "full human review of everything" or "hope".

**Solution:** A layer between the agent and its tools. (1) A circuit breaker stops exact, cycling and reworded loops and enforces step and budget caps. (2) A trust score from 0 to 100 sets autonomy tiers: new agents need approval for refunds, trusted agents refund up to $100 alone, senior agents up to $500. Clean runs raise the score; trips, kills and attacks lower it, and every change is explained in plain English. (3) A shield scans tool outputs for hidden instructions before the agent sees them. (4) Humans can pause, kill, approve, reject, edit memory or override a tool call from a dashboard or through an MCP server.

**What is new:** Permissions that follow an agent's track record automatically (earned and lost), instead of fixed role-based rules. Reworded-loop detection and injection scanning sit in the same layer, so one trust score reflects all of an agent's behaviour.

**Technology (all free / open source):** Python, FastAPI, SQLite, Google Gemini free tier (optional), Model Context Protocol, OpenTelemetry, Hugging Face Spaces.

**Evidence:** 62 automated tests. A measured comparison (`eval/compare.py`): the full loop detector caught 7 of 8 loop types versus 3 of 8 for an exact-repeat rule, with 0 false alarms on 7 normal runs; the shield caught 8 of 12 attacks with 0 false alarms on 10 harmless messages. The test cases were written by the team, so these figures are optimistic and not a real-world accuracy claim.

**Impact / business model:** [Fill in with your own research.] Suggested angle: companies deploying agents pay per monitored agent per month; the value is avoided runaway cost and avoided incidents. Do not state a market size unless you can cite a source.

**Limitations (state them):** Semantic detection uses a small synonym table, not a sentence-embedding model. The shield is rule-based and missed 4 of 12 test attacks. The Gemini agent [has / has not] been verified against the live API. Trust-score constants are starting values, not tuned on production agents.

**Links:** Live demo [Hugging Face URL] | Code [GitHub URL] | Video [link]

**Team:** [Names, roles, NRB collaborator if any]
