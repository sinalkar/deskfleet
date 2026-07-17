"""Token counting and USD cost estimation via tiktoken.

Costing is best-effort and model-aware. If ``tiktoken`` cannot resolve an
encoding for the configured model it falls back to ``cl100k_base``. Prices are a
small static table (USD per 1K tokens) covering common OpenAI-compatible models;
unknown models fall back to the gpt-4o-mini rate.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # tiktoken is a hard dep, but keep import defensive for minimal envs.
    import tiktoken

    _HAS_TIKTOKEN = True
except Exception:  # pragma: no cover
    _HAS_TIKTOKEN = False

# USD per 1K tokens: (prompt, completion)
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}
_DEFAULT_PRICE = _PRICE_TABLE["gpt-4o-mini"]


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 8),
        )


def _encoding_for(model: str):
    if not _HAS_TIKTOKEN:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:  # pragma: no cover
            return None


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens in ``text`` for ``model`` (approximate word-based fallback)."""
    if not text:
        return 0
    enc = _encoding_for(model)
    if enc is None:  # pragma: no cover - only when tiktoken unavailable
        return max(1, len(text.split()))
    return len(enc.encode(text))


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o-mini") -> float:
    prompt_rate, completion_rate = _PRICE_TABLE.get(model, _DEFAULT_PRICE)
    cost = (prompt_tokens / 1000.0) * prompt_rate + (completion_tokens / 1000.0) * completion_rate
    return round(cost, 8)


def usage_for(prompt_text: str, completion_text: str, model: str = "gpt-4o-mini") -> Usage:
    """Build a :class:`Usage` from raw prompt/completion strings."""
    p = count_tokens(prompt_text, model)
    c = count_tokens(completion_text, model)
    return Usage(prompt_tokens=p, completion_tokens=c, cost_usd=estimate_cost(p, c, model))
