"""Prompt-injection shield: scans text that came back from a tool (an email, a web page, a
database row) for hidden instructions aimed at the AI, before the agent sees it.

Rule-based on purpose: free, instant, and easy to explain. HONEST LIMIT: it recognises known
attack phrasings. A new, cleverly worded attack can get through, which is why the trust tiers
still require human approval for big refunds even if the shield misses (defence in depth).
"""
import re
import unicodedata

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")

PATTERNS = [
    ("override-phrase", r"\b(system|admin|administrator|developer)\s+(override|message|instruction|command)s?\b"),
    ("ignore-instructions",
     r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|your|all|any|the)\b"
     r"[^.\n]{0,40}\b(instructions?|rules?|polic(?:y|ies)|guidelines?|guidance|restrictions?|limits?)\b"),
    ("role-hijack",
     r"\byou are now (?:an? |the )?(?:unrestricted|unfiltered|jailbroken|different|new|dan|admin)\b"
     r"|\bnew instructions?\s*:|\bfrom now on you (?:must|will|shall|are)\b"),
    ("secrecy", r"\b(do not|don't|never)\s+(tell|inform|notify|alert|mention)\b[^.\n]{0,30}"
                r"\b(user|human|operator|customer|anyone|supervisor)\b"),
    ("money-to-account",
     r"\b(refund|transfer|send|wire|pay)\b[^.\n]{0,25}\$\s?\d[\d,]*[^.\n]{0,30}\b(to|into)\b[^.\n]{0,30}"
     r"\b(account|acct|iban|wallet)\b"),
    ("exfiltrate", r"\b(forward|send|email)\b[^.\n]{0,40}\b(all|every)\b[^.\n]{0,30}"
                   r"\b(emails?|data|records?|passwords?|customers?|credentials)\b"),
]
_COMPILED = [(name, re.compile(rx, re.I)) for name, rx in PATTERNS]


def scan(text):
    """Return the list of attack patterns found in `text` (empty list = looks clean)."""
    if not text:
        return []
    hits = []
    if ZERO_WIDTH.search(text):
        hits.append("hidden-characters")
    cleaned = unicodedata.normalize("NFKC", ZERO_WIDTH.sub("", text))
    for name, rx in _COMPILED:
        if rx.search(cleaned):
            hits.append(name)
    return hits
