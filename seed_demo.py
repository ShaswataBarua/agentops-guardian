"""Fill an empty database with a small, clearly labelled trust history so a fresh public demo
is not blank. Safe to run many times (skips agents that already have history).
Every seeded event says '(demo seed)' in its reason; nothing here is real agent behaviour."""
import store
import trust

SEEDS = {
    # agent_id: [(event, reason), ...]
    "demo-support-bot": [("approved", "human approved issue_refund (demo seed)"),
                         ("completed", "run completed (demo seed)")],          # 50 +2 +8 = 60, Tier 2
    "demo-rogue-bot": [("tripped", "loop: lookup_order repeated 3x (demo seed)"),
                       ("injection", "prompt injection in read_email output (demo seed)")],  # 50 -15 -20 = 15, Tier 0
}


def seed():
    store.init()
    added = 0
    for agent_id, events in SEEDS.items():
        if store.trust_history(agent_id):
            continue
        for event, reason in events:
            trust.record(agent_id, None, event, reason)
            added += 1
    return added


if __name__ == "__main__":
    print(f"seeded {seed()} events")
