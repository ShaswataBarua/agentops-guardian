import os
import tempfile
import time

os.environ["AGENTOPS_DB"] = tempfile.mktemp(suffix=".db")  # must be set before importing api

from fastapi.testclient import TestClient  # noqa: E402

from api import app  # noqa: E402
from breaker import Breaker, CircuitBreakerOpen  # noqa: E402

client = TestClient(app)
_n = 0


def start(agent, trust=70, agent_id=None, **kw):
    """Start a run. Each run gets its own agent identity with a seeded trust score
    (trust=None keeps the agent's existing score)."""
    global _n
    _n += 1
    aid = agent_id or f"{agent}-{_n}"
    if trust is not None:
        client.post(f"/agents/{aid}/trust", json={"score": trust})
    return client.post("/runs", json={"agent": agent, "agent_id": aid, **kw}).json()["run_id"]


def wait(run_id, states, timeout=8):
    end = time.time() + timeout
    data = None
    while time.time() < end:
        data = client.get(f"/runs/{run_id}").json()
        if data["run"]["status"] in states:
            return data
        time.sleep(0.03)
    raise AssertionError(f"run {run_id} never reached {states}; last={data['run']['status']}")


def score(agent_id):
    return client.get(f"/agents/{agent_id}").json()["score"]


def aid_of(data):
    return data["run"]["agent_id"]


# ------------------------------------------------------------ circuit breaker
def test_looper_trips_at_step_3():
    d = wait(start("looper"), {"tripped"})
    assert d["run"]["reason"].startswith("loop: lookup_order")
    assert len(d["steps"]) == 2          # steps 1-2 ran, step 3 was blocked
    assert d["run"]["total_tokens"] == 4000


def test_looper_without_breaker_runs_all_40():
    d = wait(start("looper", breaker=False), {"done"})
    assert len(d["steps"]) == 40
    assert d["run"]["total_tokens"] == 80000
    assert abs(d["run"]["total_cost"] - 0.24) < 1e-9


def test_pingpong_trips():
    d = wait(start("pingpong"), {"tripped"})
    assert d["run"]["reason"].startswith("loop:")
    assert len(d["steps"]) == 4          # tripped on step 5


def test_normal_does_not_trip():
    d = wait(start("normal"), {"done", "tripped"})
    assert d["run"]["status"] == "done"
    assert len(d["steps"]) == 4


def test_legit_retry_does_not_trip():
    d = wait(start("legit_retry"), {"done", "tripped"})
    assert d["run"]["status"] == "done"


def test_budget_trips():
    d = wait(start("normal", budget=0.001), {"tripped", "done"})
    assert d["run"]["status"] == "tripped"
    assert d["run"]["reason"].startswith("budget:")


def test_cycler_trips_on_cycle():
    d = wait(start("cycler"), {"tripped"})
    assert d["run"]["reason"].startswith("cycle:")
    assert len(d["steps"]) == 5          # blocked on step 6 (second A,B,C)


def test_cycler_without_breaker_runs_30_steps():
    d = wait(start("cycler", breaker=False), {"done"})
    assert len(d["steps"]) == 30
    assert d["run"]["total_tokens"] == 60000


def test_max_steps_limit():
    d = wait(start("normal", max_steps=3), {"tripped", "done"})      # normal has 4 steps
    assert d["run"]["status"] == "tripped"
    assert d["run"]["reason"].startswith("step limit")
    assert len(d["steps"]) == 3


def _first_trip(calls, **kw):
    b = Breaker(budget_usd=10, **kw)
    for i, (tool, args) in enumerate(calls, 1):
        try:
            b.check(tool, args, 100)
        except CircuitBreakerOpen as e:
            return i, str(e)
    return None, ""


def test_unit_cycles_of_3_and_4():
    a, b, c, d = [("t", {"n": i}) for i in range(4)]
    assert _first_trip([a, b, c] * 5)[0] == 6
    assert _first_trip([a, b, c, d] * 5)[0] == 8


def test_unit_known_limit_cycle_of_5_not_caught():
    calls = [("t", {"n": i}) for i in range(5)] * 5
    assert _first_trip(calls)[0] is None      # documented limit: cycles longer than 4 steps


def test_unit_unique_steps_never_trip_until_step_limit():
    calls = [("t", {"n": i}) for i in range(60)]
    assert _first_trip(calls, max_steps=100)[0] is None
    assert _first_trip(calls, max_steps=10)[0] == 11


# ------------------------------------------------------------ approvals
def test_approval_approve():
    rid = start("refunder")                                  # trust 70 = tier 2, limit $100
    d = wait(rid, {"waiting_approval"})
    assert d["run"]["pending"]["args"]["amount"] == 250
    assert "may refund up to $100" in d["run"]["pending"]["why"]
    client.post(f"/runs/{rid}/approve")
    d = wait(rid, {"done"})
    assert [s["status"] for s in d["steps"]] == ["ok", "approved", "ok"]


def test_approval_reject():
    rid = start("refunder")
    wait(rid, {"waiting_approval"})
    client.post(f"/runs/{rid}/reject")
    d = wait(rid, {"done"})
    assert [s["status"] for s in d["steps"]] == ["ok", "rejected", "ok"]
    assert d["steps"][1]["result"] == "DENIED by human"


# ------------------------------------------------------------ human control
def test_pause_resume_kill():
    rid = start("looper", breaker=False, delay=0.05)
    wait(rid, {"running"})
    client.post(f"/runs/{rid}/pause")
    d = wait(rid, {"paused"})
    n = len(d["steps"])
    time.sleep(0.3)
    assert len(client.get(f"/runs/{rid}").json()["steps"]) <= n + 1   # frozen
    client.post(f"/runs/{rid}/resume")
    wait(rid, {"running"})
    client.post(f"/runs/{rid}/kill")
    d = wait(rid, {"killed"})
    assert d["run"]["reason"] == "killed by human"
    assert len(d["steps"]) < 40


def test_memory_edit_and_override():
    rid = start("looper", breaker=False, delay=0.05)
    wait(rid, {"running"})
    client.patch(f"/runs/{rid}/memory", json={"memory": {"order_id": 2222}})
    client.post(f"/runs/{rid}/override", json={"tool": "send_email", "args": {"to": "x@y.com", "body": "hi"}})
    time.sleep(0.4)
    steps = client.get(f"/runs/{rid}").json()["steps"]
    assert any(s["tool"] == "send_email" for s in steps)               # override used once
    assert any(s["args"].get("order_id") == 2222 for s in steps)      # edited memory used
    client.post(f"/runs/{rid}/kill")
    wait(rid, {"killed"})


# ------------------------------------------------------------ trust score + tiers
def test_new_agent_starts_at_50_tier_1():
    client.post("/runs", json={"agent": "normal", "agent_id": "brand-new-bot", "breaker": False})
    a = client.get("/agents/brand-new-bot").json()
    assert a["score"] == 50 and a["tier"] == 1 and a["tier_name"] == "Junior"


def test_tier_boundaries():
    for s, tier in [(0, 0), (29, 0), (30, 1), (59, 1), (60, 2), (79, 2), (80, 3), (100, 3)]:
        client.post("/agents/boundary-bot/trust", json={"score": s})
        assert client.get("/agents/boundary-bot").json()["tier"] == tier, s


def test_tier2_small_refund_needs_no_approval():
    d = wait(start("normal", trust=70), {"done", "waiting_approval"})   # refund $20, limit $100
    assert d["run"]["status"] == "done"


def test_tier1_any_refund_needs_approval():
    rid = start("normal", trust=50)
    d = wait(rid, {"done", "waiting_approval"})
    assert d["run"]["status"] == "waiting_approval"
    assert d["run"]["pending"]["tool"] == "issue_refund"
    client.post(f"/runs/{rid}/kill")
    wait(rid, {"killed"})


def test_tier0_every_action_needs_approval():
    rid = start("normal", trust=10)
    d = wait(rid, {"done", "waiting_approval"})
    assert d["run"]["status"] == "waiting_approval"
    assert d["run"]["pending"]["tool"] == "lookup_order"              # even a harmless lookup
    client.post(f"/runs/{rid}/kill")
    wait(rid, {"killed"})


def test_tier3_big_refund_needs_no_approval():
    d = wait(start("refunder", trust=85), {"done", "waiting_approval"})   # $250 <= $500
    assert d["run"]["status"] == "done"


def test_score_rises_on_completed_run():
    d = wait(start("normal", trust=70), {"done"})
    assert score(aid_of(d)) == 78                                     # 70 + 8


def test_score_falls_when_breaker_trips():
    d = wait(start("looper", trust=70), {"tripped"})
    assert score(aid_of(d)) == 55                                     # 70 - 15


def test_score_falls_when_killed():
    rid = start("looper", trust=70, breaker=False, delay=0.05)
    wait(rid, {"running"})
    client.post(f"/runs/{rid}/kill")
    d = wait(rid, {"killed"})
    assert score(aid_of(d)) == 60                                     # 70 - 10


def test_approve_and_reject_change_score():
    d = wait_after_decision("approve")
    assert score(aid_of(d)) == 80                                     # 70 + 2 (approved) + 8 (completed)
    d = wait_after_decision("reject")
    assert score(aid_of(d)) == 73                                     # 70 - 5 (rejected) + 8 (completed)


def wait_after_decision(decision):
    rid = start("refunder", trust=70)
    wait(rid, {"waiting_approval"})
    client.post(f"/runs/{rid}/{decision}")
    return wait(rid, {"done"})


def test_promotion_unlocks_more_autonomy():
    """Junior agent (52) is supervised once, earns trust, then runs on its own."""
    aid = "promo-bot"
    client.post(f"/agents/{aid}/trust", json={"score": 52})
    r1 = start("normal", trust=None, agent_id=aid)
    wait(r1, {"waiting_approval"})                                    # tier 1: the $20 refund needs a human
    client.post(f"/runs/{r1}/approve")
    wait(r1, {"done"})
    a = client.get(f"/agents/{aid}").json()
    assert a["score"] == 62 and a["tier"] == 2                        # 52 + 2 + 8 -> promoted
    r2 = start("normal", trust=None, agent_id=aid)
    d = wait(r2, {"done", "waiting_approval"})
    assert d["run"]["status"] == "done"                               # no human needed this time


def test_demotion_removes_autonomy():
    """Trusted agent (62) loops, loses trust, and is supervised again."""
    aid = "demo-bot"
    client.post(f"/agents/{aid}/trust", json={"score": 62})
    wait(start("looper", trust=None, agent_id=aid), {"tripped"})
    a = client.get(f"/agents/{aid}").json()
    assert a["score"] == 47 and a["tier"] == 1                        # 62 - 15 -> demoted
    r2 = start("normal", trust=None, agent_id=aid)
    d = wait(r2, {"done", "waiting_approval"})
    assert d["run"]["status"] == "waiting_approval"
    client.post(f"/runs/{r2}/kill")
    wait(r2, {"killed"})


def test_trust_history_lists_reasons():
    d = wait(start("looper", trust=70), {"tripped"})
    hist = client.get(f"/agents/{aid_of(d)}").json()["history"]
    assert [h["event"] for h in hist] == ["manual", "tripped"]
    assert hist[-1]["delta"] == -15 and hist[-1]["reason"].startswith("loop:")


def test_dashboard_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "AgentOps" in r.text and "text/html" in r.headers["content-type"]


def test_policy_endpoint():
    p = client.get("/policy").json()
    assert p["start_score"] == 50
    assert [t["refund_limit_without_approval"] for t in p["tiers"]] == [None, 0, 100, 500]


# ============================================================ v3: new detectors, shield, LLM agent, dashboard
import sys  # noqa: E402

import agents  # noqa: E402
import llm_agent  # noqa: E402
import shield  # noqa: E402
from breaker import Breaker, CircuitBreakerOpen  # noqa: E402
from semantic import SemanticLoopDetector  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval"))
import compare  # noqa: E402


def feed(seq, **kw):
    """Feed (tool, args) steps to a Breaker. Returns the step number that tripped, or None."""
    b = Breaker(budget_usd=999, **kw)
    for i, (tool, args) in enumerate(seq, 1):
        try:
            b.check(tool, args, 2000)
        except CircuitBreakerOpen as e:
            feed.reason = str(e)
            return i
    return None


A, B_, C_ = ("lookup_order", {"order_id": 1004}), ("search_kb", {"query": "refund policy"}), \
    ("send_email", {"to": "ops@example.com", "body": "x"})


def test_cycle_rule_catches_abc_pattern():
    assert feed([A, B_, C_] * 4) == 6
    assert feed.reason == "cycle: 3-step pattern repeated 2x"


def test_cycle_rule_off_misses_abc_pattern():
    assert feed([A, B_, C_] * 4, cycle_lengths=()) is None


def test_no_false_cycle_on_one_and_a_half_repeats():
    assert feed([A, B_, C_, A, B_]) is None


def test_max_steps_rule():
    seq = [("lookup_order", {"order_id": 1000 + n}) for n in range(10)]
    assert feed(seq, max_steps=5) == 6
    assert feed.reason.startswith("step limit")


def test_retry_counter_does_not_hide_a_loop():
    seq = [("lookup_order", {"order_id": 1004, "attempt": n}) for n in range(1, 6)]
    assert feed(seq) == 3
    assert feed.reason.startswith("loop:")


def test_semantic_catches_reworded_loop_that_hash_misses():
    seq = [("search_kb", {"query": q}) for q in agents.PARAPHRASES]
    assert feed(seq, cycle_lengths=()) is None
    assert feed(seq, semantic=SemanticLoopDetector()) == 3
    assert feed.reason.startswith("semantic loop")


def test_semantic_ignores_different_orders():
    seq = [("lookup_order", {"order_id": 1000 + n}) for n in range(1, 12)]
    assert feed(seq, semantic=SemanticLoopDetector()) is None


def test_paraphraser_run_semantic_on_vs_off():
    on = wait(start("paraphraser"), {"tripped"})
    assert on["run"]["reason"].startswith("semantic loop")
    assert len(on["steps"]) == 2
    off = wait(start("paraphraser", semantic=False), {"tripped"})
    assert off["run"]["reason"].startswith("budget:")           # only the cost cap stops it, much later
    assert len(off["steps"]) == 9


def test_cycler_run_trips_before_semantic_rule():
    d = wait(start("cycler"), {"tripped"})
    assert d["run"]["reason"] == "cycle: 3-step pattern repeated 2x"   # the cycle rule fires first
    assert len(d["steps"]) == 5


def test_run_stops_at_max_steps():
    d = wait(start("normal", max_steps=2, trust=70), {"tripped"})
    assert d["run"]["reason"].startswith("step limit")
    assert len(d["steps"]) == 2


# ------------------------------------------------------------ injection shield
def test_shield_flags_attacks_and_passes_normal_mail():
    assert shield.scan(agents.INBOX[2])
    assert not shield.scan(agents.INBOX[1])
    assert not shield.scan(agents.INBOX[3])
    assert "hidden-characters" in shield.scan("hello​ world")
    assert not shield.scan("You are now my favourite shop! Great service.")


def test_injection_is_quarantined_and_trust_drops():
    d = wait(start("inbox_bot", trust=70), {"quarantined"})
    assert d["run"]["reason"].startswith("prompt injection in read_email output")
    assert [s["status"] for s in d["steps"]] == ["ok", "quarantined"]
    assert d["steps"][1]["result"].startswith("[BLOCKED:")
    assert not any(s["tool"] == "issue_refund" for s in d["steps"])   # the attack never ran
    assert score(aid_of(d)) == 50                                     # 70 - 20


def test_second_layer_holds_the_attack_when_shield_is_off():
    rid = start("inbox_bot", trust=85, shield=False)                  # Tier 3 may refund up to $500
    d = wait(rid, {"waiting_approval"})
    assert d["run"]["pending"]["args"]["amount"] == 5000
    assert "may refund up to $500" in d["run"]["pending"]["why"]
    client.post(f"/runs/{rid}/reject")
    d = wait(rid, {"done"})
    assert [s["status"] for s in d["steps"]] == ["ok", "ok", "rejected", "ok"]
    assert score(aid_of(d)) == 88                                     # 85 - 5 + 8


# ------------------------------------------------------------ robustness
def test_unknown_tool_and_bad_arguments_are_reported_not_fatal():
    def badtool(mem):
        yield "no_such_tool", {}, 100
        yield "lookup_order", {"order_idd": 1}, 100
        yield "lookup_order", {"order_id": 1}, 100
    agents.AGENTS["badtool"] = badtool
    try:
        d = wait(start("badtool"), {"done", "error"})
    finally:
        del agents.AGENTS["badtool"]
    assert d["run"]["status"] == "done"
    assert [s["status"] for s in d["steps"]] == ["error", "error", "ok"]
    assert d["steps"][0]["result"].startswith("ERROR: unknown tool")


def test_agent_receives_tool_results():
    seen = []

    def echo(mem):
        seen.append((yield "lookup_order", {"order_id": 7}, 100))
    agents.AGENTS["echo"] = echo
    try:
        wait(start("echo"), {"done"})
    finally:
        del agents.AGENTS["echo"]
    assert seen == ["order 7: delivered"]


# ------------------------------------------------------------ trust explanation
def test_trust_explanation_text():
    client.post("/agents/explain-bot/trust", json={"score": 70})
    text = client.get("/agents/explain-bot").json()["explanation"]
    assert "Tier 2 (Trusted)" in text and "10 more points to reach Tier 3" in text
    assert "Drops to Tier 1 below 60" in text


# ------------------------------------------------------------ Gemini agent (fake model, no network)
def test_gemini_parse_call_final_and_float_fix():
    call = llm_agent.GeminiClient.parse({
        "candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "lookup_order", "args": {"order_id": 1004.0}}},
            {"functionCall": {"name": "send_email", "args": {}}}]}}],
        "usageMetadata": {"totalTokenCount": 321}})
    assert call["kind"] == "call" and call["name"] == "lookup_order"
    assert call["args"] == {"order_id": 1004} and isinstance(call["args"]["order_id"], int)
    assert call["tokens"] == 321
    assert len(call["content"]["parts"]) == 1                          # only the first call is kept
    final = llm_agent.GeminiClient.parse({"candidates": [{"content": {"role": "model", "parts": [{"text": "Done."}]}}]})
    assert final["kind"] == "final" and final["text"] == "Done."


def test_gemini_client_retries_on_rate_limit_and_needs_key():
    calls, naps = [], []

    def post(url, headers, body):
        calls.append(url)
        if len(calls) < 3:
            raise RuntimeError("Gemini HTTP 429: quota")
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}}]}
    gc = llm_agent.GeminiClient(api_key="k", model="m", post=post, sleep=naps.append)
    assert gc.step([{"role": "user", "parts": [{"text": "hi"}]}])["kind"] == "final"
    assert len(calls) == 3 and naps == [2, 4] and calls[0].endswith("/models/m:generateContent")
    os.environ.pop("GEMINI_API_KEY", None)
    try:
        llm_agent.GeminiClient()
        assert False, "should require a key"
    except RuntimeError as e:
        assert "GEMINI_API_KEY" in str(e)


class FakeGemini:
    def __init__(self, outs):
        self.outs, self.sent = list(outs), []

    def step(self, contents):
        self.sent.append([dict(c) for c in contents])
        return self.outs.pop(0)


def test_gemini_agent_runs_through_the_breaker_and_gets_results_back(monkeypatch):
    def call(name, args, tokens):
        return {"kind": "call", "name": name, "args": args, "tokens": tokens,
                "content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}}
    fake = FakeGemini([call("lookup_order", {"order_id": 1006}, 900),
                       call("send_email", {"to": "e@example.com", "body": "hi"}, 800),
                       {"kind": "final", "text": "Done", "tokens": 100, "content": {"role": "model", "parts": []}}])
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm_agent, "make_client", lambda: fake)
    d = wait(start("gemini_support", task="Check order 1006 and email e@example.com"), {"done", "error"})
    assert d["run"]["status"] == "done"
    assert [s["tool"] for s in d["steps"]] == ["lookup_order", "send_email"]
    assert d["run"]["total_tokens"] == 1700
    assert fake.sent[0][0]["parts"][0]["text"] == "Check order 1006 and email e@example.com"
    last = fake.sent[1][-1]["parts"][0]["functionResponse"]
    assert last["name"] == "lookup_order" and last["response"]["result"] == "order 1006: delivered"


def test_gemini_agent_needs_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/runs", json={"agent": "gemini_support"})
    assert r.status_code == 400 and "GEMINI_API_KEY" in r.json()["detail"]
    gem = [s for s in client.get("/scripts").json() if s["name"] == "gemini_support"][0]
    assert gem["available"] is False


# ------------------------------------------------------------ dashboard + evaluation regression
def test_dashboard_page_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_evaluation_results_hold():
    rows, _ = compare.run_detector_eval()
    a, b, c = rows
    assert (a["loops_caught"], b["loops_caught"], c["loops_caught"]) == (3, 4, 7)
    assert all(r["false_alarms"] == 0 for r in rows)
    s = compare.run_shield_eval()
    assert s["caught"] == 8 and s["false_alarms"] == []

