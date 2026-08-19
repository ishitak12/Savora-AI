"""AI-powered natural language menu search."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import SearchResponse
from app.services import embeddings, llm
from app.services.ai_search import search_menu

router = APIRouter(prefix="/search", tags=["ai-search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=300, description="Natural language query"),
    limit: int = Query(default=8, ge=1, le=25),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Search the menu in natural language.

    Open to anonymous callers on purpose: browsing and searching should not
    require an account. Ordering does.
    """
    return search_menu(db, q, limit)


@router.get("/health")
def ai_health() -> dict:
    """Reports whether the AI path is live. The admin UI polls this so the
    operator knows before a customer does that search has degraded.

    Recall and reranking are reported separately because they fail
    independently: a local embedding provider can serve semantic search with
    no LLM available at all.
    """
    embedding = embeddings.health()
    rerank = llm.health()
    return {
        # kept for the existing admin badge
        "configured": embedding.get("available") or rerank.get("configured", False),
        "reachable": bool(embedding.get("available")),
        "embeddings": embedding,
        "reranker": rerank,
    }
