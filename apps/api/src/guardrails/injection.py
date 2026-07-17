"""Prompt-injection detection.

A lightweight regex layer that runs on the **raw inbound ticket before any LLM
call**. A match short-circuits the whole pipeline to ``REFUSE`` — the model is
never invoked, so a hijack attempt cannot influence classification or drafting.

This is intentionally conservative (favoring recall on obvious attacks) rather
than a complete defense; it is one layer among several.
"""

from __future__ import annotations

import re

# Patterns targeting system-override / role-hijack / prompt-exfil / smuggling.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|context)", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(instructions|rules|prompt)?", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.I),
    re.compile(r"\bact\s+as\s+(a|an|if)\b", re.I),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.I),
    re.compile(r"(reveal|show|print|repeat|expose|leak)\s+(me\s+)?(your\s+)?(the\s+)?"
               r"(system\s+prompt|instructions|prompt|api\s+key|secret)", re.I),
    re.compile(r"\bnew\s+(instructions|system\s+prompt|rules)\b", re.I),
    re.compile(r"\boverride\s+(your|the|all)\s+(instructions|rules|safety|guardrails)", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bDAN\b(?:\s+mode)?", re.I),
    re.compile(r"</?(system|assistant|user)>", re.I),  # role-tag smuggling
    re.compile(r"\[/?(INST|SYS|SYSTEM)\]", re.I),  # chat-template smuggling
    re.compile(r"```[\s\S]*?(system|assistant)\s*:", re.I),  # code-fence role smuggling
]


def detect_injection(text: str) -> tuple[bool, str | None]:
    """Return ``(is_injection, matched_pattern)``.

    ``matched_pattern`` is the human-readable regex source of the first match,
    suitable for logging as an escalation/refusal reason.
    """
    if not text:
        return False, None
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True, pattern.pattern
    return False, None


def is_injection(text: str) -> bool:
    return detect_injection(text)[0]
