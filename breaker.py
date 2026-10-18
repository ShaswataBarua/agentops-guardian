"""Circuit breaker: stops looping, cycling, over-budget and runaway agents.

Rules, checked on every step (first one that fires stops the run):
  1. loop     same call (tool + meaningful args) 3+ times in the last 6 steps
  2. cycle    a 3- or 4-step pattern repeated twice in a row (A,B,C,A,B,C). Two-step patterns
              (A,B,A,B) are already caught by rule 1. Cycles longer than 4 steps are NOT caught.
  3. semantic same intent AND same entities, reworded, 3+ times (see semantic.py; optional)
  4. steps    more than max_steps steps in one run
  5. budget   cumulative cost above the budget cap
"""
import hashlib
import json
from collections import deque

# Arguments that change on every call without changing what the call means.
# A retry counter must not make a repeated call look "different".
VOLATILE_KEYS = {"attempt", "retry", "retries", "nonce", "timestamp", "ts", "request_id", "trace_id"}


class CircuitBreakerOpen(Exception):
    pass


def stable_args(args):
    return {k: v for k, v in args.items() if str(k).lower() not in VOLATILE_KEYS}


def fingerprint(tool, args):
    raw = tool + json.dumps(stable_args(args), sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


class Breaker:
    def __init__(self, window=6, repeat_limit=3, budget_usd=0.05, price_per_m=3.0,
                 max_steps=50, cycle_lengths=(3, 4), cycle_repeats=2, semantic=None):
        self.recent = deque(maxlen=window)          # last N step fingerprints
        self.repeat_limit = repeat_limit            # same call this many times in the window -> trip
        self.budget = budget_usd                    # max cost for one run
        self.price = price_per_m                    # USD per 1M tokens (placeholder price)
        self.max_steps = max_steps                  # hard cap on steps per run
        self.cycle_lengths = tuple(cycle_lengths)   # pattern lengths to look for; () turns the rule off
        self.cycle_repeats = cycle_repeats
        self.history = deque(maxlen=max(self.cycle_lengths, default=1) * cycle_repeats)
        self.semantic = semantic                    # optional SemanticLoopDetector
        self.tokens = 0
        self.steps = 0

    def _cycle(self):
        """Length of a repeating multi-step pattern at the end of the history, or None."""
        h = list(self.history)
        for k in self.cycle_lengths:
            need = k * self.cycle_repeats
            if len(h) < need:
                continue
            tail = h[-need:]
            pattern = tail[:k]
            if len(set(pattern)) > 1 and all(tail[i] == pattern[i % k] for i in range(need)):
                return k
        return None

    def check(self, tool, args, tokens):
        self.steps += 1
        fp = fingerprint(tool, args)
        self.recent.append(fp)
        self.history.append(fp)
        self.tokens += tokens
        cost = self.tokens / 1_000_000 * self.price

        if list(self.recent).count(fp) >= self.repeat_limit:
            raise CircuitBreakerOpen(f"loop: {tool} repeated {self.repeat_limit}x")
        k = self._cycle()
        if k:
            raise CircuitBreakerOpen(f"cycle: {k}-step pattern repeated {self.cycle_repeats}x")
        if self.semantic is not None:
            reason = self.semantic.check(tool, args)
            if reason:
                raise CircuitBreakerOpen(reason)
        if self.steps > self.max_steps:
            raise CircuitBreakerOpen(f"step limit: more than {self.max_steps} steps")
        if cost > self.budget:
            raise CircuitBreakerOpen(f"budget: ${cost:.4f} > ${self.budget}")
