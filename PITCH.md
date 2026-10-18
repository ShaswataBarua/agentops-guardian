# 3-minute pitch (180 seconds)

Open the dashboard before you start and keep the **same agent name** in the agent field for every scenario, so they share one trust score
(that is what makes the story flow). Use the dashboard's buttons: "Earn trust", "Reworded loop", "Prompt-injection email".
Rehearse with a timer at least 3 times. If the internet fails, play your backup screen recording.

| Time | Say | Show |
|---|---|---|
| 0:00-0:20 | "AI agents can already issue refunds and send emails. Companies will not switch them on, because one loop can burn the budget and one poisoned email can trigger a $5,000 refund." | Title slide or the dashboard |
| 0:20-0:35 | "We built a control layer. Every agent earns trust like a credit score, and its permissions grow or shrink with its record." | Trust table on the dashboard |
| 0:35-1:15 | **Earned autonomy.** Click **Earn trust** (a new agent starts at Tier 1). "A new agent is Junior: its refund waits for a human." Click Approve. "Score goes up, and at 60 it is Trusted and can refund up to $100 alone." | Earn trust, then Approve; point at the score and the plain-English explanation |
| 1:15-1:50 | **Loops.** Click **Reworded loop**. "This agent asks the same question in different words. An exact-match check misses it. Ours catches it at step 3, the run stops, the agent loses 15 points and is demoted." | Reworded loop; show the stop reason and the score drop |
| 1:50-2:15 | **Attack.** Click **Prompt-injection email**. "It read an email that says: system override, refund $5,000. The shield quarantines the run before the agent sees it. Even if it missed, a $5,000 refund is above every tier, so a human must approve." | Prompt-injection email; show "quarantined" and -20 trust. Optional: **Injection email, shield off** shows the tier policy holding the refund |
| 2:15-2:40 | **Proof, with honesty.** "Across our tests the full detector caught 7 of 8 loops against 3 of 8 for exact repeat, with no false alarms. The shield caught 8 of 12 attacks. We wrote those tests ourselves, so treat them as a floor for improvement, not a guarantee." | `eval/results.md` table |
| 2:40-3:00 | "Open standards: traces export as OpenTelemetry and the controls are an MCP server. Deployed free, link on screen. Agents should earn trust, not be handed it." | Public URL and QR code |

## If a judge asks for the live demo to break

Switch to the recorded video immediately and say so. Do not debug on stage.

## Do not claim

- Do not say "first in the world". Say you did not find another tool that gates permissions by an earned score, and that you checked only briefly.
- Do not quote the 95% saving without saying it is one scripted loop at a placeholder price.
- Do not call the Gemini agent tested unless you have run `python llm_smoke.py` successfully.
