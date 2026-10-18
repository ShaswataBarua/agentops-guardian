"""Trust score + autonomy tiers: an agent earns (or loses) permissions from its track record.

Score is 0-100, every agent starts at 50. Events change it:
    completed run  +8      approved action +2
    tripped run   -15      rejected action -5      killed by human -10
    prompt injection caught in a tool result -20
Why these numbers: trust is slow to earn and quick to lose, like a credit score. One breaker
trip (-15) takes two completed runs (+16) to win back; an injection (-20) takes three (+24).
They are starting values you can change in DELTAS; they are not tuned on real agents.

Tiers (what the agent may do WITHOUT asking a human):
    Tier 0  score < 30   Probation : nothing, every action needs approval
    Tier 1  30 - 59      Junior    : lookups and emails; any refund needs approval
    Tier 2  60 - 79      Trusted   : refunds up to $100
    Tier 3  80 - 100     Senior    : refunds up to $500
"""
import store

DELTAS = {"completed": 8, "approved": 2, "tripped": -15, "rejected": -5, "killed": -10,
          "injection": -20, "manual": 0}

TIER_NAMES = {0: "Probation", 1: "Junior", 2: "Trusted", 3: "Senior"}
TIER_STARTS = {0: 0, 1: 30, 2: 60, 3: 80}
REFUND_LIMIT = {1: 0, 2: 100, 3: 500}  # max refund (USD) without approval, per tier


def tier_for(score):
    if score >= 80:
        return 3
    if score >= 60:
        return 2
    if score >= 30:
        return 1
    return 0


def clamp(x):
    return max(0, min(100, x))


def record(agent_id, run_id, event, reason):
    """Apply an event to the agent's score and save it. Returns the new score."""
    delta = DELTAS[event]
    new = clamp(store.trust_score(agent_id) + delta)
    store.add_trust_event(agent_id, run_id, event, delta, new, reason)
    return new


def set_score(agent_id, score):
    """Manual set (for demos and tests)."""
    new = clamp(int(score))
    store.add_trust_event(agent_id, None, "manual", new - store.trust_score(agent_id), new, "set manually")
    return new


def needs_approval(tool, args, tier):
    """Returns (True/False, human-readable reason)."""
    if tier == 0:
        return True, "Tier 0 (Probation): every action needs approval"
    if tool == "issue_refund":
        limit = REFUND_LIMIT[tier]
        amount = args.get("amount", 0)
        if amount > limit and limit == 0:
            return True, f"Tier {tier} ({TIER_NAMES[tier]}) may not refund without approval; this refund is ${amount}"
        if amount > limit:
            return True, f"Tier {tier} ({TIER_NAMES[tier]}) may refund up to ${limit}; this refund is ${amount}"
    return False, ""


def explain(agent_id):
    """One plain-English paragraph: where the score is, why, and what changes next."""
    score = store.trust_score(agent_id)
    tier = tier_for(score)
    parts = [f"Score {score}: Tier {tier} ({TIER_NAMES[tier]})."]
    hist = store.trust_history(agent_id)
    if hist:
        last = hist[-1]
        parts.append(f"Last change {last['delta']:+d}: {last['reason']}.")
    if tier < 3:
        parts.append(f"{TIER_STARTS[tier + 1] - score} more points to reach Tier {tier + 1}.")
    else:
        parts.append("Top tier.")
    if tier > 0:
        parts.append(f"Drops to Tier {tier - 1} below {TIER_STARTS[tier]}.")
    return " ".join(parts)


def summary(agent_id):
    score = store.trust_score(agent_id)
    tier = tier_for(score)
    return {"agent_id": agent_id, "score": score, "tier": tier, "tier_name": TIER_NAMES[tier],
            "next_tier_at": TIER_STARTS.get(tier + 1), "explanation": explain(agent_id)}
