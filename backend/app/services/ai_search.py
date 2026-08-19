"""The AI menu search pipeline.

    query
      │
      ├─ 1. constraint extraction ──── rules (regex)  ─┐
      │                                LLM (optional) ─┴─► hard filters
      │
      ├─ 2. candidate set  ─────────── SQL: available items matching filters
      │
      ├─ 3. recall ─────────────────── cosine over cached embeddings
      │                                 (local ONNX model or a hosted API)
      │                                 └─ fallback: BM25 + synonym expansion
      │
      ├─ 4. rerank ─────────────────── an LLM scores the top-N with a reason
      │                                 (Groq or Gemini)
      │                                 └─ fallback: keep retrieval order
      │
      └─ 5. response ───────────────── ranked items + score + why + the mode
                                        that actually served the request

Design decisions worth defending in the demo:

* Hard constraints are never delegated to the model. Price and diet are
  enforced in SQL, so "under 200" cannot return a 240-rupee dish no matter
  what the model thinks.
* Availability is a filter, not a signal. The brief says "from what is
  currently available", so unavailable items never enter the candidate set.
* Embeddings are cached on the row with a content fingerprint. A search
  costs one embedding call (the query); item vectors are computed on write.
* Every stage degrades independently. Losing the reranker does not lose
  semantic recall; losing embeddings does not lose search. Recall and
  reranking use different providers on purpose, so no single vendor outage
  takes out both.
* The response tells the caller which path ran (`search_mode`, `degraded`,
  `notes`) rather than silently pretending. The UI surfaces this.
"""
import hashlib
import json
import logging
import math
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MenuItem
from app.schemas import (
    MenuItemOut,
    ParsedConstraints,
    SearchResponse,
    SearchResult,
)
from app.services import embeddings, llm
from app.services.constraints import merge_constraints, parse_constraints
from app.services.lexical import BM25, normalise

logger = logging.getLogger("savora.search")


# --------------------------------------------------------------------------
# Embedding cache
# --------------------------------------------------------------------------
def fingerprint(text: str, provider: str | None = None) -> str:
    """Content hash of the searchable text, scoped to the provider that
    produced the vector.

    The provider is part of the hash because embedding spaces are not
    comparable across models — a 384-dim local vector and a 3072-dim hosted
    one describe different geometries. Including it means switching
    providers invalidates every cached vector automatically, instead of
    silently comparing incompatible ones.
    """
    return hashlib.sha256(f"{provider or 'none'}|{text}".encode("utf-8")).hexdigest()[:32]


def refresh_embeddings(db: Session, items: list[MenuItem] | None = None) -> int:
    """Compute and store embeddings for items whose text has changed.

    Called on item create/update and by the seeder. Returns the number of
    vectors written (0 when no provider is available — not an error).
    """
    provider = embeddings.active_provider()
    if provider == "none":
        return 0
    if items is None:
        items = list(db.scalars(select(MenuItem)))

    stale = [
        i for i in items
        if i.embedding_fingerprint != fingerprint(i.search_text, provider)
    ]
    if not stale:
        return 0

    written = 0
    # Batch in chunks so one oversized request cannot fail the whole refresh.
    for start in range(0, len(stale), 25):
        chunk = stale[start : start + 25]
        vectors = embeddings.embed_texts([i.search_text for i in chunk])
        if vectors is None:
            logger.warning("embedding refresh unavailable; keeping lexical mode")
            break
        for item, vector in zip(chunk, vectors):
            item.embedding_json = json.dumps(vector)
            item.embedding_fingerprint = fingerprint(item.search_text, provider)
            written += 1
    if written:
        db.commit()
    return written


def _load_vector(item: MenuItem, provider: str) -> list[float] | None:
    if not item.embedding_json:
        return None
    if item.embedding_fingerprint != fingerprint(item.search_text, provider):
        return None  # stale or produced by another provider — treat as missing
    try:
        return json.loads(item.embedding_json)
    except json.JSONDecodeError:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------
# Stage 1 — constraints
# --------------------------------------------------------------------------
_EXTRACTION_PROMPT = """You extract structured filters from a restaurant \
customer's search query. Return ONLY a JSON object with these keys:

{{
  "max_price": number or null,
  "min_price": number or null,
  "require_tags": array of any of ["vegetarian","non-vegetarian","spicy","vegan"],
  "exclude_tags": array of the same values,
  "exclude_terms": array of lowercase ingredient/preparation words to avoid,
  "categories": array of any of ["Starters","Main Course","Breads","Rice & Biryani","Desserts","Beverages"]
}}

Rules:
- Prices are in Indian rupees. Only set them when the user stated a budget.
- "not spicy" means exclude_tags ["spicy"], never require_tags.
- Use exclude_terms for preparation styles the user rejects, e.g. "not fried" -> ["fried"].
- Leave arrays empty and numbers null when the query does not mention them.
- Do not invent constraints the user did not express.

Query: "{query}"
"""


def _llm_constraints(query: str) -> ParsedConstraints | None:
    data = llm.generate_json(_EXTRACTION_PROMPT.format(query=query))
    if not isinstance(data, dict):
        return None
    allowed_tags = {"vegetarian", "non-vegetarian", "spicy", "vegan"}

    def _tags(key: str) -> list[str]:
        raw = data.get(key) or []
        if not isinstance(raw, list):
            return []
        return [str(t).lower() for t in raw if str(t).lower() in allowed_tags]

    def _number(key: str) -> float | None:
        value = data.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    def _strings(key: str) -> list[str]:
        raw = data.get(key) or []
        if not isinstance(raw, list):
            return []
        return [str(v).lower().strip() for v in raw if str(v).strip()][:8]

    return ParsedConstraints(
        max_price=_number("max_price"),
        min_price=_number("min_price"),
        require_tags=_tags("require_tags"),
        exclude_tags=_tags("exclude_tags"),
        exclude_terms=_strings("exclude_terms"),
        categories=_strings("categories"),
        source="llm",
    )


# --------------------------------------------------------------------------
# Stage 2 — candidate set
# --------------------------------------------------------------------------
def _candidates(db: Session, c: ParsedConstraints) -> list[MenuItem]:
    stmt = select(MenuItem).where(MenuItem.is_available.is_(True))
    if c.max_price is not None:
        stmt = stmt.where(MenuItem.price <= c.max_price)
    if c.min_price is not None:
        stmt = stmt.where(MenuItem.price >= c.min_price)

    items = list(db.scalars(stmt))

    # Tag predicates run in Python: tags are a packed string, and the
    # catalogue is small enough that a scan is cheaper than a join table.
    if c.require_tags:
        items = [i for i in items if all(t in i.tags for t in c.require_tags)]
    if c.exclude_tags:
        items = [i for i in items if not any(t in i.tags for t in c.exclude_tags)]
    if c.categories:
        wanted = {cat.lower() for cat in c.categories}
        narrowed = [i for i in items if i.category.lower() in wanted]
        # A category guess that empties the result set is worse than no
        # category guess, so only apply it when something survives.
        if narrowed:
            items = narrowed
    return items


def _apply_soft_exclusions(
    items: list[MenuItem], terms: list[str]
) -> tuple[list[MenuItem], bool]:
    """Drop items mentioning an excluded preparation, but only if some
    items survive. Returns (items, applied)."""
    if not terms:
        return items, False
    kept = [
        i
        for i in items
        if not any(term in f"{i.name} {i.description}".lower() for term in terms)
    ]
    if kept and len(kept) != len(items):
        return kept, True
    return items, False


# --------------------------------------------------------------------------
# Stage 4 — rerank
# --------------------------------------------------------------------------
_RERANK_PROMPT = """You are the search ranking engine for a restaurant menu.

Customer query: "{query}"

Candidate dishes (already filtered to available items that satisfy any \
stated price and dietary constraints):
{candidates}

Rank the candidates by how well they satisfy the query's intent, including \
soft preferences such as "light", "comforting" or "not fried". Return ONLY \
JSON:

{{"ranking": [{{"id": <int>, "score": <0-1 float>, "reason": "<max 12 words>"}}]}}

Include only genuinely relevant dishes — returning 3 good matches is better \
than 10 padded ones. Never invent an id that is not in the candidate list.
"""


def _rerank(
    query: str, items: list[MenuItem]
) -> dict[int, tuple[float, str]] | None:
    if not items:
        return None
    lines = [
        f"- id={i.id} | {i.name} | {i.category} | Rs {i.price:.0f} | "
        f"tags: {', '.join(i.tags) or 'none'} | {i.description}"
        for i in items
    ]
    data = llm.generate_json(
        _RERANK_PROMPT.format(query=query, candidates="\n".join(lines))
    )
    if not isinstance(data, dict):
        return None
    ranking = data.get("ranking")
    if not isinstance(ranking, list):
        return None

    valid_ids = {i.id for i in items}
    out: dict[int, tuple[float, str]] = {}
    for entry in ranking:
        if not isinstance(entry, dict):
            continue
        try:
            item_id = int(entry["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if item_id not in valid_ids:
            continue  # guard against hallucinated ids
        score = entry.get("score", 0.0)
        score = float(score) if isinstance(score, (int, float)) else 0.0
        reason = str(entry.get("reason", ""))[:120]
        out[item_id] = (max(0.0, min(1.0, score)), reason)
    return out or None


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def search_menu(db: Session, query: str, limit: int = 8) -> SearchResponse:
    started = time.perf_counter()
    notes: list[str] = []

    # -- 1. constraints ---------------------------------------------------
    constraints = parse_constraints(query)
    if llm.is_available():
        llm_side = _llm_constraints(query)
        if llm_side:
            constraints = merge_constraints(constraints, llm_side)
        else:
            notes.append("LLM constraint extraction unavailable; used rules only.")
    else:
        notes.append("No LLM provider configured; rules-only constraints, no reranking.")

    # -- 2. candidates ----------------------------------------------------
    items = _candidates(db, constraints)
    if not items:
        return SearchResponse(
            query=query,
            results=[],
            constraints=constraints,
            search_mode="lexical",
            degraded=True,
            notes=notes + ["No available items satisfy the stated constraints."],
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    items, soft_applied = _apply_soft_exclusions(items, constraints.exclude_terms)
    if soft_applied:
        notes.append(f"Excluded items matching: {', '.join(constraints.exclude_terms)}.")

    # -- 3. recall --------------------------------------------------------
    provider = embeddings.active_provider()
    vectors = {i.id: _load_vector(i, provider) for i in items} if provider != "none" else {}
    have_vectors = [i for i in items if vectors.get(i.id)]
    query_vector = embeddings.embed_query(query) if provider != "none" else None

    # Require vectors for at least half the candidates: ranking 3 embedded
    # items against 37 unembedded ones is worse than running BM25 on all 40.
    semantic = query_vector is not None and len(have_vectors) >= max(
        1, len(items) // 2
    )

    if semantic:
        scored = [
            (i, cosine(query_vector, vectors[i.id]))
            for i in items
            if vectors.get(i.id)
        ]
        # Cosine similarity from these models lives roughly in 0.3-0.9;
        # rescale so the percentage shown in the UI spans the range a human
        # expects. Monotonic, so it changes the label and not the order.
        scored = [(i, max(0.0, (s - 0.3) / 0.6)) for i, s in scored]
        mode_base = "semantic"
        notes.append(f"Semantic recall via the {provider} embedding provider.")
    else:
        if provider != "none" and query_vector is None:
            notes.append("Embedding provider unavailable; fell back to lexical BM25.")
        elif provider != "none" and not have_vectors:
            notes.append(
                "No cached item embeddings for this provider; fell back to lexical BM25. "
                "Re-run the seeder to build them."
            )
        bm25 = BM25([i.search_text for i in items])
        raw = normalise(bm25.score(query))
        scored = list(zip(items, raw))
        mode_base = "lexical"

    scored.sort(key=lambda pair: pair[1], reverse=True)
    pool = scored[: settings.AI_CANDIDATE_POOL]

    # -- 4. rerank --------------------------------------------------------
    reranked = _rerank(query, [i for i, _ in pool]) if llm.is_available() else None
    if reranked:
        mode = f"{mode_base}+rerank"
        merged: list[tuple[MenuItem, float, str]] = []
        for item, retrieval_score in pool:
            if item.id in reranked:
                llm_score, reason = reranked[item.id]
                # Blend: the reranker sees the query intent, retrieval sees
                # the whole corpus. 70/30 keeps the model in charge without
                # letting one odd judgement bury an obviously good match.
                blended = 0.7 * llm_score + 0.3 * retrieval_score
                merged.append((item, blended, reason))
        if not merged:  # model rejected everything — show retrieval order
            merged = [(i, s, "") for i, s in pool]
            notes.append("Reranker returned no matches; showing retrieval order.")
        merged.sort(key=lambda t: t[1], reverse=True)
    else:
        if llm.is_available():
            notes.append(
                f"Reranker ({llm.active_provider()}) unavailable; showing retrieval order."
            )
        mode = mode_base
        merged = [(i, s, "") for i, s in pool]

    # Drop zero-relevance tail, but never return an empty list when the
    # constraint filter found legitimate candidates — a customer who asked
    # for "desserts under 200" should see desserts even if no word matched.
    ranked = merged[:limit]
    meaningful = [t for t in ranked if t[1] > 0.05]
    if len(meaningful) >= 3 or (meaningful and len(ranked) <= 3):
        ranked = meaningful

    results = [
        SearchResult(
            item=MenuItemOut.model_validate(item),
            score=round(min(1.0, max(0.0, score)), 3),
            reason=reason,
        )
        for item, score, reason in ranked
    ]

    return SearchResponse(
        query=query,
        results=results,
        constraints=constraints,
        search_mode=mode,
        degraded=not mode.startswith("semantic") or "rerank" not in mode,
        notes=notes,
        took_ms=int((time.perf_counter() - started) * 1000),
    )
