"""Groq LLM client — constraint extraction and reranking.

Groq serves open-weight models on custom inference hardware behind an
OpenAI-compatible API. Two reasons it suits this pipeline:

* Latency. Reranking sits on the request path, so a reranker that answers in
  200ms instead of 2s is the difference between search feeling instant and
  feeling broken.
* No embedding dependency. Groq deliberately does not host embedding models,
  which is fine here — recall is served by the local ONNX model, so the two
  halves of the pipeline have entirely independent failure modes.

Same contract as every other provider in this codebase: return None on
failure, never raise into a request.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("savora.groq")

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def is_configured() -> bool:
    return bool(settings.GROQ_API_KEY.strip())


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any] | None:
    """Ask Groq for a JSON object. Returns None if anything goes wrong."""
    if not is_configured():
        return None

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 1024,
        # OpenAI-compatible JSON mode: the model is constrained to emit a
        # syntactically valid JSON object.
        "response_format": {"type": "json_object"},
    }

    try:
        response = httpx.post(
            f"{settings.GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("Groq transport error: %s", exc)
        return None

    if response.status_code != 200:
        logger.warning("Groq HTTP %s: %s", response.status_code, response.text[:200])
        return None

    try:
        text = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Unexpected Groq response shape: %s", exc)
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON mode makes this unlikely, but a stray fence shouldn't break a
        # request — extract the first {...} block and try again.
        match = _JSON_BLOCK.search(text)
        if not match:
            logger.warning("Groq returned non-JSON: %r", text[:200])
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("Groq returned unparseable JSON")
            return None


def health() -> dict[str, Any]:
    if not is_configured():
        return {"configured": False, "reachable": False, "reason": "no GROQ_API_KEY set"}
    result = generate_json('Reply with exactly this JSON: {"ok": true}')
    return {
        "configured": True,
        "reachable": result is not None,
        "model": settings.GROQ_MODEL,
    }
