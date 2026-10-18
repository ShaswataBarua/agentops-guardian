import seed_demo
import store
import trust
from test_all import client  # noqa: F401  (importing sets up the shared test database)


def test_seed_is_idempotent_and_labelled():
    first = seed_demo.seed()
    assert first == 4
    assert seed_demo.seed() == 0                                   # second run adds nothing
    assert store.trust_score("demo-support-bot") == 60
    assert trust.tier_for(60) == 2
    assert store.trust_score("demo-rogue-bot") == 15
    assert all("(demo seed)" in e["reason"] for e in store.trust_history("demo-rogue-bot"))
