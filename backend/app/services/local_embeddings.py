"""Local, offline embedding provider.

Why this exists: the hosted embedding API is a third party that can rate-limit,
deprecate a model, or block a project — all of which happened during
development. A local model removes that dependency entirely: semantic search
keeps working with no key, no network, and no per-call cost.

Uses fastembed (ONNX runtime) rather than sentence-transformers because it
avoids a PyTorch install — roughly 130MB of model instead of ~2GB of
framework, and it runs fine on CPU.

The model is loaded lazily and cached in a module-level singleton: the first
call pays the load cost, every later call is a tensor op. Import errors and
load failures return None, exactly like the Gemini client, so the caller
takes the same fallback path.
"""
import logging
import threading

from app.core.config import settings

logger = logging.getLogger("savora.local_embeddings")

# BAAI/bge-small-en-v1.5 — 384 dimensions, ~130MB, strong quality per byte.
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None
_load_failed = False
_lock = threading.Lock()


def is_available() -> bool:
    """True if fastembed is installed. Does not load the model."""
    try:
        import fastembed  # noqa: F401

        return True
    except ImportError:
        return False


def _get_model():
    """Load the model once, on first use. Thread-safe."""
    global _model, _load_failed
    if _model is not None:
        return _model
    if _load_failed:
        return None

    with _lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextEmbedding

            cache_dir = str(settings.embedding_cache_path)
            logger.info(
                "Loading local embedding model %s (cache: %s). "
                "The first run downloads ~130MB; later runs load from disk.",
                MODEL_NAME,
                cache_dir,
            )
            _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=cache_dir)
            logger.info("Local embedding model ready.")
            return _model
        except Exception as exc:  # ImportError, download failure, ONNX error
            logger.warning("Local embedding model unavailable: %s", exc)
            _load_failed = True
            return None


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
    """Embed a batch. Returns None if the model can't be loaded.

    `task_type` is accepted for interface parity with the Gemini client and
    ignored — this model uses one symmetric embedding space.
    """
    if not texts:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        return [vector.tolist() for vector in model.embed(texts)]
    except Exception as exc:
        logger.warning("Local embedding failed: %s", exc)
        return None


def embed_query(text: str) -> list[float] | None:
    vectors = embed_texts([text], task_type="RETRIEVAL_QUERY")
    return vectors[0] if vectors else None


def health() -> dict:
    if not is_available():
        return {"available": False, "reason": "fastembed not installed"}
    vector = embed_query("health check")
    return {
        "available": vector is not None,
        "model": MODEL_NAME,
        "dimensions": len(vector) if vector else 0,
        "cache_dir": str(settings.embedding_cache_path),
    }
