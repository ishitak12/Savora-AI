"""The Gemini-enabled path, exercised with a stubbed client.

The live API is not called in CI — no key, no spend, no flakiness. Instead
the three functions the pipeline depends on are stubbed, which lets us
assert the things that actually matter about the AI layer:

  * with embeddings + reranker available, the mode is 'semantic+rerank'
  * hallucinated item ids from the reranker are discarded
  * a reranker failure degrades to retrieval order instead of erroring
  * an embedding failure degrades to BM25 instead of erroring
  * the LLM cannot widen a price constraint the rules already fixed
"""
import hashlib
import json

import pytest

from app.core.config import settings
from app.services import ai_search, gemini


@pytest.fixture
def live_ai(monkeypatch):
    """Pretend a Gemini key is configured, with deterministic responses."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    # conftest pins the provider to 'none' so no test loads a real model;
    # these tests specifically exercise the hosted path.
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")

    def fake_embed_texts(texts, task_type="RETRIEVAL_DOCUMENT"):
        # A stable pseudo-embedding: hash the text into a small vector so
        # cosine similarity is deterministic across runs.
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255 for b in digest[:16]])
        return vectors

    monkeypatch.setattr(gemini, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(
        gemini, "embed_query", lambda text: fake_embed_texts([text])[0]
    )
    return monkeypatch


def _seed_embeddings(db_session):
    ai_search.refresh_embeddings(db_session)


def test_semantic_plus_rerank_is_the_happy_path(client, db_session, live_ai, monkeypatch):
    _seed_embeddings(db_session)

    def fake_generate_json(prompt, temperature=0.1):
        if "extract structured filters" in prompt.lower() or "max_price" in prompt:
            return {"max_price": None, "require_tags": [], "exclude_tags": []}
        return {"ranking": [{"id": 1, "score": 0.9, "reason": "hot chickpea curry"}]}

    monkeypatch.setattr(gemini, "generate_json", fake_generate_json)

    body = client.get("/api/search", params={"q": "spicy chickpeas"}).json()
    assert body["search_mode"] == "semantic+rerank"
    assert body["results"]
    assert body["results"][0]["reason"] == "hot chickpea curry"


def test_hallucinated_ids_from_the_reranker_are_dropped(
    client, db_session, live_ai, monkeypatch
):
    _seed_embeddings(db_session)

    def fake_generate_json(prompt, temperature=0.1):
        if "max_price" in prompt:
            return {}
        # id 4242 does not exist; id 1 does.
        return {
            "ranking": [
                {"id": 4242, "score": 0.99, "reason": "invented dish"},
                {"id": 1, "score": 0.8, "reason": "real dish"},
            ]
        }

    monkeypatch.setattr(gemini, "generate_json", fake_generate_json)

    body = client.get("/api/search", params={"q": "anything"}).json()
    returned_ids = {r["item"]["id"] for r in body["results"]}
    assert 4242 not in returned_ids
    assert body["results"]


def test_reranker_failure_degrades_to_retrieval_order(
    client, db_session, live_ai, monkeypatch
):
    _seed_embeddings(db_session)
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: None)

    body = client.get("/api/search", params={"q": "vegetarian"}).json()
    assert body["search_mode"] == "semantic"
    assert body["degraded"] is True
    assert body["results"]
    assert any("rerank" in note.lower() for note in body["notes"])


def test_embedding_failure_degrades_to_lexical(client, live_ai, monkeypatch):
    monkeypatch.setattr(gemini, "embed_query", lambda text: None)
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: None)

    body = client.get("/api/search", params={"q": "vegetarian"}).json()
    assert body["search_mode"] == "lexical"
    assert body["results"], "fallback must still return results"


def test_llm_cannot_widen_a_price_constraint_the_rules_set(
    client, db_session, live_ai, monkeypatch
):
    _seed_embeddings(db_session)

    def fake_generate_json(prompt, temperature=0.1):
        if "max_price" in prompt:
            return {"max_price": 5000}  # model tries to relax the budget
        return {"ranking": []}

    monkeypatch.setattr(gemini, "generate_json", fake_generate_json)

    body = client.get("/api/search", params={"q": "anything under 190 rupees"}).json()
    assert body["constraints"]["max_price"] == 190
    assert all(r["item"]["price"] <= 190 for r in body["results"])


def test_embeddings_are_cached_and_invalidated_by_content(db_session, live_ai):
    from sqlalchemy import select

    from app.models import MenuItem

    written = ai_search.refresh_embeddings(db_session)
    assert written > 0
    # Second pass is a no-op: fingerprints match, so no API calls.
    assert ai_search.refresh_embeddings(db_session) == 0

    item = db_session.scalar(select(MenuItem).where(MenuItem.name == "Dal Tadka"))
    before = json.loads(item.embedding_json)
    item.description = "Now described completely differently, with new flavour notes."
    db_session.commit()

    assert ai_search.refresh_embeddings(db_session, [item]) == 1
    db_session.refresh(item)
    assert json.loads(item.embedding_json) != before


def test_cosine_is_bounded_and_handles_degenerate_input():
    assert ai_search.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert ai_search.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert ai_search.cosine([], [1, 2]) == 0.0
    assert ai_search.cosine([0, 0], [1, 1]) == 0.0


# --------------------------------------------------------------------------
# Provider dispatch — the local (offline) embedding path
# --------------------------------------------------------------------------
def test_provider_resolution_prefers_gemini_then_local(monkeypatch):
    """auto: hosted if a key exists, else local if installed, else none."""
    from app.services import embeddings, local_embeddings

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "auto")

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    assert embeddings.active_provider() == "gemini"

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(local_embeddings, "is_available", lambda: True)
    assert embeddings.active_provider() == "local"

    monkeypatch.setattr(local_embeddings, "is_available", lambda: False)
    assert embeddings.active_provider() == "none"


def test_explicit_provider_is_honoured(monkeypatch):
    from app.services import embeddings, local_embeddings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(local_embeddings, "is_available", lambda: True)

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    assert embeddings.active_provider() == "local"

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "none")
    assert embeddings.active_provider() == "none"

    # 'gemini' with no key degrades to none rather than silently going local
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    assert embeddings.active_provider() == "none"


@pytest.fixture
def local_ai(monkeypatch):
    """Offline mode: no LLM at all, local embeddings stubbed deterministically."""
    from app.services import local_embeddings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "none")
    monkeypatch.setattr(local_embeddings, "is_available", lambda: True)

    def fake_embed_texts(texts, task_type="RETRIEVAL_DOCUMENT"):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([b / 255 for b in digest[:16]])
        return vectors

    monkeypatch.setattr(local_embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(
        local_embeddings, "embed_query", lambda t: fake_embed_texts([t])[0]
    )
    return monkeypatch


def test_local_provider_serves_semantic_search_without_any_llm(
    client, db_session, local_ai
):
    """The headline guarantee: semantic search with no API key at all."""
    assert ai_search.refresh_embeddings(db_session) > 0

    body = client.get("/api/search", params={"q": "spicy chickpeas"}).json()
    assert body["search_mode"] == "semantic"          # not 'lexical'
    assert body["results"]
    assert any("local" in note for note in body["notes"])


def test_hard_constraints_still_hold_on_the_local_path(client, db_session, local_ai):
    ai_search.refresh_embeddings(db_session)
    body = client.get("/api/search", params={"q": "vegetarian under 190 rupees"}).json()
    assert body["results"]
    assert all(r["item"]["price"] <= 190 for r in body["results"])
    assert all("vegetarian" in r["item"]["tags"] for r in body["results"])


def test_switching_provider_invalidates_cached_vectors(db_session, local_ai):
    """Embedding spaces are not comparable across models, so a provider
    change must not reuse the previous provider's vectors."""
    from sqlalchemy import select

    from app.models import MenuItem

    assert ai_search.refresh_embeddings(db_session) > 0
    item = db_session.scalar(select(MenuItem).where(MenuItem.name == "Dal Tadka"))
    assert ai_search._load_vector(item, "local") is not None
    # Same row, different provider -> cache miss, not a dimension mismatch.
    assert ai_search._load_vector(item, "gemini") is None


# --------------------------------------------------------------------------
# LLM provider dispatch — Groq
# --------------------------------------------------------------------------
def test_llm_provider_prefers_groq_then_gemini(monkeypatch):
    """auto: Groq first (lower rerank latency), then Gemini, then none."""
    from app.services import llm

    monkeypatch.setattr(settings, "LLM_PROVIDER", "auto")

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    assert llm.active_provider() == "groq"

    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    assert llm.active_provider() == "gemini"

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    assert llm.active_provider() == "none"
    assert llm.is_available() is False


def test_groq_client_parses_openai_shaped_responses(monkeypatch):
    """The Groq client speaks the OpenAI schema and never raises."""
    import httpx

    from app.services import groq_llm

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"ranking": []}'}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())
    assert groq_llm.generate_json("x") == {"ranking": []}

    # A markdown-fenced body still parses.
    class FencedResponse(FakeResponse):
        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FencedResponse())
    assert groq_llm.generate_json("x") == {"ok": True}

    # An HTTP error returns None rather than raising into the request.
    class ErrorResponse:
        status_code = 429
        text = "rate limited"

    monkeypatch.setattr(httpx, "post", lambda *a, **k: ErrorResponse())
    assert groq_llm.generate_json("x") is None

    # A transport failure does too.
    def boom(*a, **k):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", boom)
    assert groq_llm.generate_json("x") is None


def test_local_embeddings_plus_groq_rerank_is_the_full_pipeline(
    client, db_session, local_ai, monkeypatch
):
    """The production configuration: offline recall, hosted reranking, and
    no single vendor in both halves of the pipeline."""
    from app.services import groq_llm

    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")

    def fake_generate_json(prompt, temperature=0.1):
        if "max_price" in prompt:
            return {"max_price": None, "require_tags": [], "exclude_tags": []}
        return {"ranking": [{"id": 1, "score": 0.95, "reason": "tangy and hot"}]}

    monkeypatch.setattr(groq_llm, "generate_json", fake_generate_json)

    ai_search.refresh_embeddings(db_session)
    body = client.get("/api/search", params={"q": "spicy chickpeas"}).json()

    assert body["search_mode"] == "semantic+rerank"
    assert body["results"][0]["reason"] == "tangy and hot"


def test_groq_failure_keeps_semantic_recall(client, db_session, local_ai, monkeypatch):
    """Losing the hosted reranker must not lose offline semantic recall —
    the whole point of splitting the providers."""
    from app.services import groq_llm

    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(groq_llm, "generate_json", lambda *a, **k: None)

    ai_search.refresh_embeddings(db_session)
    body = client.get("/api/search", params={"q": "spicy chickpeas"}).json()

    assert body["search_mode"] == "semantic"   # not 'lexical'
    assert body["results"]


def test_model_cache_is_pinned_inside_the_project(tmp_path, monkeypatch):
    """The library's default cache is %TEMP%, which the OS may delete. The
    cache must resolve to a stable project path and be created on demand."""
    from pathlib import Path

    monkeypatch.setattr(settings, "EMBEDDING_CACHE_DIR", "")
    default = settings.embedding_cache_path
    assert default.is_absolute()
    assert default.name == ".model_cache"
    assert default.parent.name == "backend"
    assert default.is_dir()          # created on access

    override = tmp_path / "nested" / "cache"
    monkeypatch.setattr(settings, "EMBEDDING_CACHE_DIR", str(override))
    assert settings.embedding_cache_path == override.resolve()
    assert override.is_dir()         # parents created too
