"""Thin Gemini client: embeddings + JSON-mode chat.

Deliberately written against the REST API with httpx instead of the
google-generativeai SDK. Two reasons: one less dependency to install on the
demo machine, and every failure mode (timeout, 429, malformed JSON) surfaces
as a plain exception we can catch and downgrade on, rather than being
wrapped in SDK-specific error types.

Every public function here returns None on failure instead of raising. The
caller treats None as "this capability is unavailable right now" and takes
the fallback path.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("savora.gemini")

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class GeminiUnavailable(Exception):
    """Raised internally when the API cannot serve a request."""


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.GEMINI_BASE_URL}/{path}"
    try:
        response = httpx.post(
            url,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:  # network down, DNS, timeout
        raise GeminiUnavailable(f"transport error: {exc}") from exc
    if response.status_code != 200:
        raise GeminiUnavailable(
            f"HTTP {response.status_code}: {response.text[:200]}"
        )
    return response.json()


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
    """Embed a batch of texts. Returns None if the API is unusable."""
    if not settings.has_gemini or not texts:
        return None
    model = f"models/{settings.GEMINI_EMBED_MODEL}"
    payload = {
        "requests": [
            {
                "model": model,
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
            }
            for text in texts
        ]
    }
    try:
        data = _post(f"{model}:batchEmbedContents", payload)
        vectors = [e["values"] for e in data["embeddings"]]
        if len(vectors) != len(texts):
            raise GeminiUnavailable("embedding count mismatch")
        return vectors
    except (GeminiUnavailable, KeyError, TypeError) as exc:
        logger.warning("embedding failed, falling back to lexical: %s", exc)
        return None


def embed_query(text: str) -> list[float] | None:
    vectors = embed_texts([text], task_type="RETRIEVAL_QUERY")
    return vectors[0] if vectors else None


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any] | None:
    """Ask Gemini for a JSON object. Returns None if anything goes wrong.

    We request responseMimeType=application/json, but still defensively
    extract the first {...} block: models occasionally wrap JSON in prose or
    a markdown fence even in JSON mode, and a demo should not fall over
    because of a stray backtick.
    """
    if not settings.has_gemini:
        return None
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
        },
    }
    try:
        data = _post(f"models/{settings.GEMINI_CHAT_MODEL}:generateContent", payload)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (GeminiUnavailable, KeyError, IndexError, TypeError) as exc:
        logger.warning("generation failed: %s", exc)
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if not match:
            logger.warning("model returned non-JSON: %r", text[:200])
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("model returned unparseable JSON")
            return None


def health() -> dict[str, Any]:
    """Cheap liveness probe used by /api/ai/health and the admin UI badge."""
    if not settings.has_gemini:
        return {"configured": False, "reachable": False, "reason": "no API key set"}
    vector = embed_query("health check")
    return {
        "configured": True,
        "reachable": vector is not None,
        "embedding_dimensions": len(vector) if vector else 0,
        "chat_model": settings.GEMINI_CHAT_MODEL,
        "embed_model": settings.GEMINI_EMBED_MODEL,
    }
