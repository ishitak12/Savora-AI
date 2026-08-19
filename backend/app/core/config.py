"""Application configuration.

Every knob is environment-driven so the same image runs locally and in CI.
Defaults are chosen so `uvicorn app.main:app` works with zero setup.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "Savora Food Ordering API"
    API_V1_PREFIX: str = "/api"

    # --- Persistence -------------------------------------------------------
    # SQLite keeps the demo hermetic: one file, no daemon, no docker-compose.
    DATABASE_URL: str = "sqlite:///./savora.db"

    # --- Auth --------------------------------------------------------------
    SECRET_KEY: str = "dev-secret-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # --- CORS --------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- AI ----------------------------------------------------------------
    # Absent keys are a supported configuration, not an error: the search
    # pipeline degrades to the lexical engine and reports that it did so.
    #
    # Two independent axes:
    #   LLM_PROVIDER       - who extracts constraints and reranks
    #   EMBEDDING_PROVIDER - who produces vectors for semantic recall
    # They fail separately on purpose, so losing one does not lose the other.
    LLM_PROVIDER: str = "auto"  # auto | groq | gemini | none

    # Groq: OpenAI-compatible, no embedding models, very low latency.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    GEMINI_API_KEY: str = ""
    GEMINI_EMBED_MODEL: str = "text-embedding-004"
    GEMINI_CHAT_MODEL: str = "gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    AI_TIMEOUT_SECONDS: float = 8.0
    AI_CANDIDATE_POOL: int = 12  # items handed to the reranker
    AI_ENABLED: bool = True

    # Where the local ONNX model is cached on disk.
    #
    # Left empty this resolves to <backend>/.model_cache. The library's own
    # default is %TEMP%/fastembed_cache, which Windows Disk Cleanup and
    # Storage Sense are free to delete — a 130MB re-download triggered by an
    # OS housekeeping job is not a dependency worth having. Pinning it inside
    # the project makes the cache survive reboots and makes its location
    # obvious to the next person who clones this.
    EMBEDDING_CACHE_DIR: str = ""

    # Which embedding backend produces vectors:
    #   auto   - Gemini if a key is configured, else the local model
    #   gemini - hosted only
    #   local  - offline ONNX model only (no key, no network)
    #   none   - skip embeddings; search runs on BM25
    # Recall and reranking are independent: 'local' still uses Gemini for the
    # rerank stage when a key is available.
    EMBEDDING_PROVIDER: str = "auto"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def has_gemini(self) -> bool:
        return self.AI_ENABLED and bool(self.GEMINI_API_KEY.strip())

    @property
    def embedding_cache_path(self) -> Path:
        """Absolute path to the local model cache, created if missing.

        Anchored to the backend package rather than the working directory,
        so `python -m app.db.seed` and `uvicorn` find the same cache no
        matter where they were launched from.
        """
        if self.EMBEDDING_CACHE_DIR.strip():
            path = Path(self.EMBEDDING_CACHE_DIR).expanduser()
        else:
            # config.py -> core -> app -> backend
            path = Path(__file__).resolve().parents[2] / ".model_cache"
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
