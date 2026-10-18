# Viva Q&A: answer these without notes

## 1. How does the loop detector work?
Each step is fingerprinted as a hash of `tool + arguments` (ignoring counters like `attempt`). Rules, first one that fires stops the run:
1. **Loop:** the same fingerprint 3 or more times in the last 6 steps.
2. **Cycle:** a 3 or 4 step pattern repeated twice in a row (A,B,C,A,B,C).
3. **Semantic:** the same entities (numbers, emails) and a similar intent, 3 or more times.
4. **Step limit** and 5. **Budget cap.**

**Worked example:** the looper calls `lookup_order(1004)` every step. Step 1 and 2 run. At step 3 the fingerprint has appeared 3 times in the window, so step 3 is blocked: 2 steps run.
Without the breaker it runs 40 steps: 40 x 2,000 = 80,000 tokens = 80,000 / 1,000,000 x $3 = $0.24. With it: 2 x 2,000 = 4,000 tokens = $0.012. Saving = (0.24 - 0.012) / 0.24 = 95%.

## 2. Why did a legitimate retry not trip it?
Retrying once makes only 2 identical calls, below the threshold of 3. Arguments like `attempt` and `retry` are ignored when fingerprinting, so a retry counter cannot hide a loop either.

## 3. Why does the semantic rule require identical entities?
"Look up order 1002" then "look up order 1003" are similar words but normal work (sweeping orders). The detector only calls steps "the same" if the entities (1002 vs 1003) match and the intent is similar.

## 4. Is the semantic detector real AI?
No, and say so. It maps words to concepts with a small hand-made table. It catches rewordings that use listed synonyms and missed the reworded policy question in our test. The upgrade is a sentence-embedding model replacing two functions in `semantic.py`; that is not built.

## 5. Why those trust numbers (+8, +2, -5, -10, -15, -20)?
They are starting values, not tuned or proven. The reasoning is the asymmetry: trust is slow to earn and quick to lose, like a credit score. A trip (-15) takes two clean runs (+16) to recover; an injection (-20) takes three (+24). They are in one dictionary, `DELTAS` in `trust.py`, so they are easy to change.

**Worked example:** a new agent starts at 50 (Tier 1). A human approves its refund (+2) and the run completes (+8): 50 + 2 + 8 = 60, which is Tier 2 (Trusted), so refunds up to $100 no longer need approval. Then a loop trips the breaker (-15): 60 - 15 = 45, back to Tier 1.

## 6. What stops the agent from approving its own actions?
Approval is a human decision made through the dashboard or the MCP server, which belongs to the supervisor, not the agent. The MCP server has no tool that sets a trust score.

## 7. How does the injection shield work, and what does it miss?
Rules scan every tool result for known attack patterns (override phrases, "ignore previous instructions", role hijacks, refund-amount instructions) after normalising text. In our test it caught 8 of 12 attacks and flagged 0 of 10 harmless messages. It missed leetspeak, an authority claim ("as the store owner..."), a French attack and a polite rewording. That is why tiers exist: even if the shield misses, a $5,000 refund is above every tier, so a human must approve it.

## 8. Your results look good. Why should we believe them?
Do not oversell. The test sequences and attack messages were written by us, so the results are optimistic. They show the rules do what we designed, not how they perform on real agents. The honest next step is testing on logs from real agents.

## 9. Does it work with a real LLM?
There is a Gemini agent using the same tools, and the code around it is tested with fake responses. [If you have run `python llm_smoke.py` successfully, say so. If not, say it has not been verified against the live API.]

## 10. What happens if two things happen at once (approve while a kill is pressed)?
A kill wins: the run checks the kill flag before acting on an approval. The run ends as `killed` and the agent loses 10 points.

## 11. What would you build next?
Real embeddings for semantic detection, tests on real agent logs, tuning the trust constants from data, detection of cycles longer than 4 steps, and multi-agent trust.

## 12. Where do the open standards come in?
MCP: the supervisor's controls are exposed as MCP tools. OpenTelemetry: every run is a trace and every step a span, viewable in Phoenix or Jaeger.
