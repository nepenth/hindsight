"""
Embedding generation utilities for memory units.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def generate_embedding(embeddings_backend, text: str) -> list[float]:
    """
    Generate embedding for text using the provided embeddings backend.

    Args:
        embeddings_backend: Embeddings instance to use for encoding
        text: Text to embed

    Returns:
        Embedding vector (dimension depends on embeddings backend)
    """
    try:
        embeddings = embeddings_backend.encode([text])
        return embeddings[0]
    except Exception as e:
        raise Exception(f"Failed to generate embedding: {str(e)}")


# Per-backend asyncio locks: keyed by id(backend).
# Local embedding models (sentence-transformers / MPS) are NOT thread-safe — calling
# encode() from multiple threads simultaneously causes a segfault on macOS MPS.
# We serialise calls at the asyncio level so only one encode() runs at a time.
_BACKEND_LOCKS: dict[int, asyncio.Lock] = {}


def _get_backend_lock(backend) -> asyncio.Lock | None:
    """Return the asyncio lock for a local (non-thread-safe) embedding backend, or None."""
    # Only local backends need serialisation; remote backends use HTTP and are safe.
    if not getattr(backend, "provider_name", None) == "local":
        return None
    key = id(backend)
    if key not in _BACKEND_LOCKS:
        _BACKEND_LOCKS[key] = asyncio.Lock()
    return _BACKEND_LOCKS[key]


async def generate_embeddings_batch(embeddings_backend, texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts using the provided embeddings backend.

    Runs the embedding generation in a thread pool to avoid blocking the event loop
    for CPU-bound operations.

    Local (sentence-transformers) backends are serialised via a per-backend asyncio
    lock to prevent concurrent MPS/GPU access from multiple threads (segfault risk).

    Args:
        embeddings_backend: Embeddings instance to use for encoding
        texts: List of texts to embed

    Returns:
        List of embeddings in same order as input texts
    """
    try:
        loop = asyncio.get_event_loop()
        lock = _get_backend_lock(embeddings_backend)
        if lock is not None:
            async with lock:
                embeddings = await loop.run_in_executor(None, embeddings_backend.encode, texts)
        else:
            embeddings = await loop.run_in_executor(None, embeddings_backend.encode, texts)
        return embeddings
    except Exception as e:
        raise Exception(f"Failed to generate batch embeddings: {str(e)}")
