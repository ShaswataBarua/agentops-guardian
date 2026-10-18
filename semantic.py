"""Semantic loop detection: catches loops where the agent REWORDS the same step.

    "check order 1004" -> "look up order #1004" -> "what is the status of order 1004?"

An exact-match hash misses these. Each step is split into
  * entities : numbers and e-mail addresses (WHAT the step is about)
  * intent   : the remaining words, mapped to concepts (WHAT the step does)
Two steps count as "the same" only if their entities are identical AND their intent is
similar. Requiring identical entities matters: "look up order 1002" then "look up order
1003" is normal work (sweeping many orders), not a loop, even though the words are alike.

HONEST LIMIT: the intent comparison below is a small hand-made word->concept table, so it
only knows the synonyms listed in CONCEPTS. The upgrade is a real sentence-embedding model:
replace `describe()` and `similarity()` (the only two functions that look at words) and
everything else stays the same. That upgrade is NOT included or tested here.
"""
import math
import re
from collections import deque

from breaker import stable_args

STOPWORDS = set("""a an the of for to is are was were be been what whats which who please again once more up on in
at about me my us our your you we i it its this that these those with and or by from as do does did can could would
should will have has had how any also just now still agent body id number no detail details info information""".split())

CONCEPTS = {}
for _concept, _words in {
    "lookup": "check look lookup retrieve fetch find get search query show view read verify status track inspect review",
    "refund": "refund reimburse reimbursement repay payback",
    "email": "email mail message notify notification",
}.items():
    for _w in _words.split():
        CONCEPTS[_w] = _concept

ENTITY_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\d+(?:\.\d+)?")


def _stem(w):
    if w in CONCEPTS:
        return CONCEPTS[w]
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    for suffix in ("ing", "ed"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            w = w[: -len(suffix)]
            break
    return CONCEPTS.get(w, w)


def describe(tool, args):
    """Return (intent concepts, entities) for one step."""
    text = tool + " " + " ".join(f"{k} {v}" for k, v in stable_args(args).items())
    text = text.replace("_", " ").lower()
    entities = frozenset(re.sub(r"\.0+$", "", e) for e in ENTITY_RE.findall(text))
    words = ENTITY_RE.sub(" ", text)
    concepts = frozenset(_stem(w) for w in re.findall(r"[a-z]+", words) if w not in STOPWORDS)
    return concepts, entities


def similarity(a, b):
    """Cosine similarity of two concept sets (1.0 = same, 0.0 = nothing shared)."""
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


class SemanticLoopDetector:
    def __init__(self, window=6, repeat_limit=3, sim_with_entities=0.75, sim_no_entities=0.9):
        self.window = window
        self.repeat_limit = repeat_limit
        self.sim_with_entities = sim_with_entities  # threshold when the step names something specific
        self.sim_no_entities = sim_no_entities      # stricter threshold when it does not
        self.recent = deque(maxlen=window)

    def check(self, tool, args):
        """Returns a reason string if this step completes a semantic loop, else None."""
        intent, ents = describe(tool, args)
        threshold = self.sim_with_entities if ents else self.sim_no_entities
        prior = list(self.recent)[-(self.window - 1):] if self.window > 1 else []
        similar = 1 + sum(1 for (i, e) in prior if e == ents and similarity(i, intent) >= threshold)
        self.recent.append((intent, ents))
        if similar >= self.repeat_limit:
            return f"semantic loop: {similar} reworded steps about the same thing ({tool})"
        return None
