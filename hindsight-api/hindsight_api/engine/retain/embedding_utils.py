"""
Embedding generation utilities for memory units.
"""

import asyncio
import logging
import threading

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


# Per-backend threading locks: keyed by id(backend).
# Local embedding models (sentence-transformers / MPS) are NOT thread-safe — calling
# encode() from multiple threads simultaneously causes a segfault on macOS MPS.
# We serialise calls at the threading level (inside run_in_executor) so only one
# encode() runs at a time. threading.Lock is used instead of asyncio.Lock to avoid
# event-loop binding issues when the same backend is used across multiple test loops
# or coroutine lifetimes (a stuck asyncio.Lock from a cancelled coroutine would block
# all subsequent callers forever).
_BACKEND_LOCKS: dict[int, threading.Lock] = {}


def _get_backend_lock(backend) -> threading.Lock | None:
    """Return the threading lock for a local (non-thread-safe) embedding backend, or None."""
    # Only local backends need serialisation; remote backends use HTTP and are safe.
    if not getattr(backend, "provider_name", None) == "local":
        return None
    key = id(backend)
    if key not in _BACKEND_LOCKS:
        _BACKEND_LOCKS[key] = threading.Lock()
    return _BACKEND_LOCKS[key]


async def generate_embeddings_batch(embeddings_backend, texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts using the provided embeddings backend.

    Runs the embedding generation in a thread pool to avoid blocking the event loop
    for CPU-bound operations.

    Local (sentence-transformers) backends are serialised via a per-backend threading
    lock acquired inside the executor to prevent concurrent MPS/GPU access from multiple
    threads (segfault risk). The lock is a threading.Lock held only during encode(),
    so it cannot become stuck across event loop boundaries.

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

            def _encode_locked() -> list[list[float]]:
                with lock:
                    return embeddings_backend.encode(texts)

            embeddings = await loop.run_in_executor(None, _encode_locked)
        else:
            embeddings = await loop.run_in_executor(None, embeddings_backend.encode, texts)
        return embeddings
    except Exception as e:
        raise Exception(f"Failed to generate batch embeddings: {str(e)}")
