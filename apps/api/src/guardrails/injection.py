"""Prompt-injection detection and hardening.

Defense-in-depth against prompt hijacking, applied in plain Python before and
around every model interaction:

1. **Normalization** (:func:`normalize`) — inbound text is Unicode-NFKC
   normalized and stripped of zero-width/invisible characters before scanning,
   so obfuscated payloads (fullwidth letters, zero-width joiners inside
   "i g n o r e") can't slip past the pattern layer.
2. **Pattern scan** (:func:`detect_injection`) — regex patterns covering
   system-override, role-hijack, prompt-exfiltration, chat-template smuggling,
   and obfuscation markers. A match short-circuits the whole pipeline to
   ``REFUSE`` — the model is never invoked.
3. **Tool-output scan** (:func:`scan_tool_result`) — external API responses are
   untrusted (indirect prompt injection); researcher facts are scanned and
   offending strings sanitized before they reach the responder's prompt.
4. **Outbound leak scan** (:func:`detect_prompt_leak`) — the drafted reply is
   checked for signs the model is echoing its instructions or an injected
   payload back to the customer.

This layered approach is deliberately conservative (favoring recall on obvious
attacks) — it is bounded, deterministic, and fully testable with zero API keys.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width and invisible code points commonly used to split trigger words:
# ZWSP, ZWNJ, ZWJ, word joiner, BOM, soft hyphen, and bidi control characters.
_INVISIBLE_CHARS = re.compile(
    "[\u200b\u200c\u200d\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)

# Patterns targeting system-override / role-hijack / prompt-exfil / smuggling.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|context)", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(instructions|rules|prompt)?", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.I),
    re.compile(r"\bact\s+as\s+(a|an|if)\b", re.I),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.I),
    re.compile(
        r"(reveal|show|print|repeat|expose|leak|output|display)\s+(me\s+)?(your\s+)?(the\s+)?"
        r"(system\s+prompt|initial\s+prompt|instructions|prompt|api\s+key|secret|credentials)",
        re.I,
    ),
    re.compile(r"\bnew\s+(instructions|system\s+prompt|rules)\b", re.I),
    re.compile(r"\boverride\s+(your|the|all)\s+(instructions|rules|safety|guardrails)", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bDAN\b(?:\s+mode)?"),
    re.compile(r"</?(system|assistant|user)>", re.I),  # role-tag smuggling
    re.compile(r"\[/?(INST|SYS|SYSTEM)\]", re.I),  # chat-template smuggling
    re.compile(r"```[\s\S]*?(system|assistant)\s*:", re.I),  # code-fence role smuggling
    # Additional hijack families:
    re.compile(r"\b(repeat|echo|say)\s+(everything|all|the\s+text)\s+(above|before)", re.I),
    re.compile(r"\bwhat\s+(are|were)\s+your\s+(instructions|rules|system\s+prompt)", re.I),
    re.compile(r"\btranslate\s+(everything|the\s+text)\s+above\b", re.I),
    re.compile(r"\bstop\s+being\s+(a|an)\b", re.I),
    re.compile(r"\b(admin|root|sudo|superuser)\s+(mode|access|override)\b", re.I),
    re.compile(r"\bfrom\s+now\s+on\s+you\s+(are|will|must)\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"\bhypothetically\s+you\s+(are|could|can)\b", re.I),
    re.compile(r"<\|[a-z_]+\|>", re.I),  # special-token smuggling (<|im_start|> etc.)
    re.compile(r"\bbase64\s*(decode|:)\s*[A-Za-z0-9+/=]{16,}", re.I),  # encoded payloads
    re.compile(r"\bexecute\s+(this|the\s+following)\s+(code|command|instruction)", re.I),
    re.compile(r"\bcall\s+(the\s+)?tool\s+['\"]?\w+['\"]?\s+with\b", re.I),  # tool coercion
]

# Signals that a ticket is outside the supported support domain and should be
# refused before the LLM pipeline runs. Conservative: only obvious, unsupported
# requests (subscriptions, account deletion, etc.) are caught here; anything
# ambiguous still falls to the classifier and the 'other' -> REFUSE fallback.
_OUT_OF_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcancel\b.*\bsubscription\b|\bsubscription\b.*\bcancel\b", re.I),
    re.compile(r"\bunsubscribe\b|\bunsubscribe\s+me\b", re.I),
    re.compile(r"\bdelete\b.*\baccount\b|\bclose\b.*\baccount\b", re.I),
    re.compile(r"\bbilling\b.*\bdispute\b|\bchargeback\b", re.I),
]

# Signals that a *drafted reply* is leaking instructions or complying with an
# injected payload — checked outbound, where the vocabulary differs from the
# inbound attack patterns (the model narrating its own configuration).
_LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bmy\s+(system\s+prompt|instructions)\s+(is|are|say)", re.I),
    re.compile(r"\bI\s+(was|am)\s+(told|instructed|programmed)\s+to\b", re.I),
    re.compile(r"\bas\s+an?\s+AI\s+(language\s+)?model,?\s+my\s+instructions\b", re.I),
    re.compile(r"</?(system|assistant)>", re.I),
    re.compile(r"<\|[a-z_]+\|>", re.I),
    re.compile(r"\b(api[_\s]?key|secret[_\s]?key|password)\s*[:=]\s*\S+", re.I),
]


def normalize(text: str) -> str:
    """NFKC-normalize and strip invisible characters before scanning.

    Defeats fullwidth/compatibility-form obfuscation (``ｉｇｎｏｒｅ``) and
    zero-width splitting (``ig​nore``) of trigger words.
    """
    if not text:
        return ""
    return _INVISIBLE_CHARS.sub("", unicodedata.normalize("NFKC", text))


def detect_injection(text: str) -> tuple[bool, str | None]:
    """Return ``(is_injection, matched_pattern)`` for inbound ticket text.

    ``matched_pattern`` is the human-readable regex source of the first match,
    suitable for logging as an escalation/refusal reason. Input is normalized
    first, so obfuscated variants of the trigger phrases still match.
    """
    if not text:
        return False, None
    cleaned = normalize(text)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            return True, pattern.pattern
    return False, None


def detect_out_of_scope(text: str) -> tuple[bool, str | None]:
    """Return ``(is_out_of_scope, matched_pattern)`` for inbound ticket text.

    Conservative pre-LLM filter for obvious unsupported requests. Anything not
    matched here still falls to the classifier, where ``Category.OTHER`` becomes
    a REFUSE decision.
    """
    if not text:
        return False, None
    cleaned = normalize(text)
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(cleaned):
            return True, pattern.pattern
    return False, None


def is_injection(text: str) -> bool:
    return detect_injection(text)[0]


def scan_tool_result(result: object) -> tuple[bool, object]:
    """Scan an external tool result for embedded injection payloads.

    External APIs are untrusted input (the classic *indirect* prompt-injection
    vector: an attacker plants "ignore previous instructions" inside a product
    title, and the agent reads it as data). Returns ``(flagged, sanitized)``
    where flagged strings are replaced with a quarantine marker so the payload
    never reaches the responder's prompt.
    """
    flagged = False

    def _clean(value: object) -> object:
        nonlocal flagged
        if isinstance(value, str):
            if is_injection(value):
                flagged = True
                return "[QUARANTINED: injection pattern in external data]"
            return value
        if isinstance(value, dict):
            return {k: _clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_clean(v) for v in value]
        return value

    # _clean must run before `flagged` is read — tuple elements evaluate
    # left-to-right, so `return flagged, _clean(...)` would always report False.
    sanitized = _clean(result)
    return flagged, sanitized


def detect_prompt_leak(text: str | None) -> tuple[bool, str | None]:
    """Return ``(is_leaking, matched_pattern)`` for an outbound draft."""
    if not text:
        return False, None
    cleaned = normalize(text)
    for pattern in _LEAK_PATTERNS:
        if pattern.search(cleaned):
            return True, pattern.pattern
    return False, None
