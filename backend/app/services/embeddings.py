"""Embedding provider dispatcher.

The search pipeline asks for a vector; this module decides who produces it.
Adding a provider means adding a branch here — nothing in ai_search.py
changes.

Resolution order for EMBEDDING_PROVIDER=auto:
    1. gemini  — if AI_ENABLED and a key is configured
    2. local   — if fastembed is installed
    3. none    — search falls back to BM25

A provider is chosen once per request and not retried against another one on
failure: a predictable single path is easier to reason about (and to report
in `search_mode`) than a cascade.
"""
import logging

from app.core.config import settings
from app.services import gemini, local_embeddings

logger = logging.getLogger("savora.embeddings")


def active_provider() -> str:
    """Returns 'gemini', 'local', or 'none'."""
    configured = (settings.EMBEDDING_PROVIDER or "auto").strip().lower()

    if configured == "gemini":
        return "gemini" if settings.has_gemini else "none"
    if configured == "local":
        return "local" if local_embeddings.is_available() else "none"
    if configured == "none":
        return "none"

    # auto
    if settings.has_gemini:
        return "gemini"
    if local_embeddings.is_available():
        return "local"
    return "none"


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
    provider = active_provider()
    if provider == "gemini":
        return gemini.embed_texts(texts, task_type=task_type)
    if provider == "local":
        return local_embeddings.embed_texts(texts, task_type=task_type)
    return None


def embed_query(text: str) -> list[float] | None:
    provider = active_provider()
    if provider == "gemini":
        return gemini.embed_query(text)
    if provider == "local":
        return local_embeddings.embed_query(text)
    return None


def health() -> dict:
    provider = active_provider()
    info: dict = {"provider": provider}
    if provider == "gemini":
        info.update(gemini.health())
    elif provider == "local":
        info.update(local_embeddings.health())
    else:
        info.update({"available": False, "reason": "no embedding provider configured"})
    return info
