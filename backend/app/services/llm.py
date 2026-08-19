"""LLM provider dispatcher — mirrors services/embeddings.py.

The pipeline uses an LLM for two things: extracting structured constraints
from a query, and reranking candidates with a reason. Both are
JSON-in/JSON-out, so a provider only needs to implement `generate_json`.

Resolution order for LLM_PROVIDER=auto:
    1. groq   — if GROQ_API_KEY is set
    2. gemini — if AI_ENABLED and GEMINI_API_KEY is set
    3. none   — rules-only constraints, no reranking

Groq is preferred in auto mode because reranking is on the request path and
its inference latency is materially lower.
"""
import logging
from typing import Any

from app.core.config import settings
from app.services import gemini, groq_llm

logger = logging.getLogger("savora.llm")


def active_provider() -> str:
    """Returns 'groq', 'gemini', or 'none'."""
    configured = (settings.LLM_PROVIDER or "auto").strip().lower()

    if configured == "groq":
        return "groq" if groq_llm.is_configured() else "none"
    if configured == "gemini":
        return "gemini" if settings.has_gemini else "none"
    if configured == "none":
        return "none"

    # auto
    if groq_llm.is_configured():
        return "groq"
    if settings.has_gemini:
        return "gemini"
    return "none"


def is_available() -> bool:
    return active_provider() != "none"


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any] | None:
    provider = active_provider()
    if provider == "groq":
        return groq_llm.generate_json(prompt, temperature=temperature)
    if provider == "gemini":
        return gemini.generate_json(prompt, temperature=temperature)
    return None


def health() -> dict:
    provider = active_provider()
    info: dict = {"provider": provider}
    if provider == "groq":
        info.update(groq_llm.health())
    elif provider == "gemini":
        info.update(gemini.health())
    else:
        info.update({"configured": False, "reachable": False,
                     "reason": "no LLM provider configured"})
    return info
