"""Application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, dashboard, menu, orders, search
from app.core.config import settings
from app.db.session import Base, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("savora")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # create_all is adequate for a single-file SQLite demo. A production
    # deployment would use Alembic migrations; noted in the README.
    Base.metadata.create_all(bind=engine)
    # Imported here rather than at module scope: the dispatchers read the
    # settings singleton, and keeping the import local makes the startup
    # order explicit.
    from app.services import embeddings, llm

    logger.info(
        "Savora API up. Reasoning: %s | Recall: %s",
        llm.active_provider(),
        embeddings.active_provider(),
    )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Food ordering backend with AI-powered natural language menu search. "
        "Two roles: admin (menu + order management) and customer (browse, "
        "search, order, track)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten pydantic's nested error payload into something a frontend can
    render directly, while keeping the 422 semantics."""
    messages = [
        f"{'.'.join(str(p) for p in err['loc'][1:]) or 'body'}: {err['msg']}"
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(messages) or "Invalid request."},
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus which AI providers are actually wired up.

    Recall and reasoning are reported separately because they fail
    independently — a local embedding provider serves semantic search with
    no LLM available at all.
    """
    from app.services import embeddings, llm

    recall = embeddings.active_provider()
    reasoning = llm.active_provider()
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "recall_provider": recall,
        "reasoning_provider": reasoning,
        "ai_configured": recall != "none" or reasoning != "none",
    }


for router in (auth.router, menu.router, search.router, orders.router, dashboard.router):
    app.include_router(router, prefix=settings.API_V1_PREFIX)
