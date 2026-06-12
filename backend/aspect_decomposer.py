"""
aspect_decomposer.py
Break a user query into 3–6 distinct sub-aspects.

Uses the free LLM client (Ollama / Groq / Gemini).
Falls back to a built-in rule-based decomposer that needs ZERO API key.
"""

import re
from typing import List

from llm_client import llm_json_chat

# ── Rule-based fallback ───────────────────────────────────────────────────────
# Conjunctions and question words that hint at multiple aspects
_SPLIT_PATTERNS = re.compile(
    r"\b(and|also|as well as|additionally|furthermore|plus|"
    r"what about|how about|along with)\b",
    re.IGNORECASE,
)

_QUESTION_WORDS = re.compile(
    r"\b(what|how|when|where|who|why|which|"
    r"how many|how much|how long|how often)\b",
    re.IGNORECASE,
)

def _rule_based_decompose(query: str) -> List[str]:
    """
    Heuristic decomposition — no LLM needed.
    Splits on conjunctions and question words, cleans up each sub-phrase.
    """
    # Split on conjunction markers
    parts = _SPLIT_PATTERNS.split(query)
    # Remove the matched separators themselves (odd indices are the separators)
    parts = [p.strip() for p in parts if p.strip() and not _SPLIT_PATTERNS.fullmatch(p.strip())]

    # If only one part, try splitting on '?' boundaries
    if len(parts) <= 1:
        parts = [p.strip() for p in query.split("?") if p.strip()]

    # Filter very short fragments (< 4 words)
    parts = [p for p in parts if len(p.split()) >= 3]

    if not parts:
        parts = [query]

    # Cap at 6, deduplicate while preserving order
    seen, unique = set(), []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique[:6]


# ── LLM system prompt ─────────────────────────────────────────────────────────
_SYSTEM = (
    "You are a query analyst for RAG system auditing. "
    "Break the user query into 3 to 6 distinct sub-aspects that a retrieval "
    "system must cover to fully answer it. "
    "Each aspect should be a short phrase of 5–10 words. "
    "Return ONLY a JSON array of strings — no markdown, no commentary."
)


def decompose_query(query: str) -> List[str]:
    """
    Decompose a user query into semantic sub-aspects.

    Tries the configured free LLM first; falls back to rule-based decomposition
    if the LLM is unavailable or returns an unusable response.

    Args:
        query: The user's original question.

    Returns:
        List of 3–6 aspect strings.
    """
    print(f"[aspect_decomposer] Decomposing: {query[:100]}")

    # ── Attempt LLM decomposition ──────────────────────────────────────────
    data = llm_json_chat(
        system=_SYSTEM,
        user=f"Query: {query}\n\nExtract sub-aspects as a JSON array:",
    )

    if isinstance(data, list) and all(isinstance(a, str) for a in data) and len(data) >= 1:
        aspects = [a.strip() for a in data if a.strip()][:6]
        print(f"[aspect_decomposer] LLM returned {len(aspects)} aspects: {aspects}")
        return aspects

    # ── Fallback: rule-based ───────────────────────────────────────────────
    print("[aspect_decomposer] LLM unavailable — using rule-based decomposer.")
    aspects = _rule_based_decompose(query)
    print(f"[aspect_decomposer] Rule-based: {aspects}")
    return aspects
