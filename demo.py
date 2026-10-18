"""Step-6/7 demo: no server needed. Run:  python demo.py"""
from breaker import Breaker, CircuitBreakerOpen
from agents import looper


def run(use_breaker):
    b = Breaker()
    used = 0
    for step, (tool, args, tokens) in enumerate(looper(lambda: {}), 1):
        if use_breaker:
            try:
                b.check(tool, args, tokens)
            except CircuitBreakerOpen as e:
                print(f"STOPPED at step {step}: {e}")
                break
        used += tokens
    print(f"breaker={use_breaker} tokens={used} cost=${used / 1_000_000 * 3.0:.3f}")


run(False)
run(True)
