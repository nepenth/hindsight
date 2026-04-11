"""
Tests for RAG mode config flags: temporal extraction and graph retrieval.

Verifies that:
1. Config flags default to True (full retrieval pipeline).
2. Disabling temporal extraction skips dateparser and temporal DB queries.
3. Disabling graph retrieval skips entity/link traversal.
4. Recall still returns relevant results with both disabled (2-way: semantic + BM25).
"""

import os
import time
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from hindsight_api import LocalSTEmbeddings, MemoryEngine, RequestContext
from hindsight_api.engine.cross_encoder import LocalSTCrossEncoder
from hindsight_api.engine.memory_engine import Budget
from hindsight_api.engine.query_analyzer import DateparserQueryAnalyzer
from hindsight_api.engine.task_backend import SyncTaskBackend
from hindsight_api.config import (
    ENV_ENABLE_TEMPORAL_EXTRACTION,
    DEFAULT_ENABLE_TEMPORAL_EXTRACTION,
    ENV_ENABLE_GRAPH_RETRIEVAL,
    DEFAULT_ENABLE_GRAPH_RETRIEVAL,
    clear_config_cache,
    HindsightConfig,
)

# Env vars managed by the clean_env fixture
_MANAGED_ENV_VARS = [ENV_ENABLE_TEMPORAL_EXTRACTION, ENV_ENABLE_GRAPH_RETRIEVAL]


@pytest.fixture(autouse=True)
def clean_env():
    """Save and restore RAG mode env vars around each test."""
    originals = {k: os.environ.get(k) for k in _MANAGED_ENV_VARS}
    clear_config_cache()
    yield
    for k, v in originals.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    clear_config_cache()


@pytest_asyncio.fixture(scope="function")
async def none_memory(pg0_db_url, embeddings, cross_encoder, query_analyzer):
    """MemoryEngine with provider=none (chunks mode — no LLM needed for retain)."""
    mem = MemoryEngine(
        db_url=pg0_db_url,
        memory_llm_provider="none",
        memory_llm_api_key=None,
        memory_llm_model="none",
        embeddings=embeddings,
        cross_encoder=cross_encoder,
        query_analyzer=query_analyzer,
        pool_min_size=1,
        pool_max_size=5,
        run_migrations=False,
        task_backend=SyncTaskBackend(),
    )
    await mem.initialize()
    yield mem
    try:
        if mem._pool and not mem._pool._closing:
            await mem.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Config-level tests
# ---------------------------------------------------------------------------

def test_temporal_extraction_defaults_to_true():
    """Default value should be True (temporal extraction on)."""
    assert DEFAULT_ENABLE_TEMPORAL_EXTRACTION is True


def test_config_enables_temporal_extraction_by_default():
    """HindsightConfig.from_env() should set enable_temporal_extraction=True when env var is unset."""
    os.environ.pop(ENV_ENABLE_TEMPORAL_EXTRACTION, None)
    os.environ.setdefault("HINDSIGHT_API_LLM_PROVIDER", "mock")
    config = HindsightConfig.from_env()
    assert config.enable_temporal_extraction is True


def test_config_disables_temporal_extraction_when_false():
    """Setting the env var to 'false' should disable temporal extraction."""
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    os.environ.setdefault("HINDSIGHT_API_LLM_PROVIDER", "mock")
    config = HindsightConfig.from_env()
    assert config.enable_temporal_extraction is False


def test_config_enables_temporal_extraction_when_true():
    """Setting the env var to 'true' explicitly should enable it."""
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "true"
    os.environ.setdefault("HINDSIGHT_API_LLM_PROVIDER", "mock")
    config = HindsightConfig.from_env()
    assert config.enable_temporal_extraction is True


# ---------------------------------------------------------------------------
# Integration tests — full retain + recall with temporal extraction on/off
# Uses provider=none so retain works in chunks mode (no LLM needed).
# Recall finds chunks via semantic search (embeddings only).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_returns_results_with_temporal_extraction_enabled(none_memory, request_context):
    """
    With temporal extraction enabled (default), recall should return results
    for a query that contains temporal language.
    """
    os.environ.pop(ENV_ENABLE_TEMPORAL_EXTRACTION, None)
    clear_config_cache()

    bank_id = f"test_temporal_enabled_{datetime.now(timezone.utc).timestamp()}"

    await none_memory.retain_async(
        bank_id=bank_id,
        content="In March 2024, the team shipped the new authentication system. It replaced the legacy OAuth flow.",
        context="engineering update",
        request_context=request_context,
    )

    result = await none_memory.recall_async(
        bank_id=bank_id,
        query="What happened with authentication in March 2024?",
        budget=Budget.LOW,
        include_chunks=True,
        request_context=request_context,
    )

    has_results = len(result.results) > 0 or (result.chunks is not None and len(result.chunks) > 0)
    assert has_results, "Should find results with temporal extraction enabled"


@pytest.mark.asyncio
async def test_recall_returns_results_with_temporal_extraction_disabled(none_memory, request_context):
    """
    With temporal extraction disabled, recall should still return results
    via semantic + BM25 + graph retrieval (3-way).
    """
    bank_id = f"test_temporal_disabled_{datetime.now(timezone.utc).timestamp()}"

    await none_memory.retain_async(
        bank_id=bank_id,
        content="In March 2024, the team shipped the new authentication system. It replaced the legacy OAuth flow.",
        context="engineering update",
        request_context=request_context,
    )

    # Now disable temporal extraction for recall
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    clear_config_cache()

    result = await none_memory.recall_async(
        bank_id=bank_id,
        query="What happened with authentication in March 2024?",
        budget=Budget.LOW,
        include_chunks=True,
        request_context=request_context,
    )

    has_results = len(result.results) > 0 or (result.chunks is not None and len(result.chunks) > 0)
    assert has_results, "Should find results even with temporal extraction disabled (3-way retrieval)"


@pytest.mark.asyncio
async def test_recall_non_temporal_query_works_with_extraction_disabled(none_memory, request_context):
    """
    A non-temporal query should work with temporal extraction disabled.
    """
    bank_id = f"test_non_temporal_{datetime.now(timezone.utc).timestamp()}"

    await none_memory.retain_async(
        bank_id=bank_id,
        content="Alice is a software engineer who specializes in distributed systems and Kubernetes.",
        context="team info",
        request_context=request_context,
    )

    # Disable temporal extraction
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    clear_config_cache()

    result = await none_memory.recall_async(
        bank_id=bank_id,
        query="Who is Alice?",
        budget=Budget.LOW,
        include_chunks=True,
        request_context=request_context,
    )

    has_results = len(result.results) > 0 or (result.chunks is not None and len(result.chunks) > 0)
    assert has_results, "Should find results for non-temporal query"


@pytest.mark.asyncio
async def test_recall_latency_lower_with_temporal_extraction_disabled(none_memory, request_context):
    """
    Recall with temporal extraction disabled should be measurably faster
    than with it enabled, since we skip the dateparser overhead.
    """
    bank_id = f"test_latency_{datetime.now(timezone.utc).timestamp()}"

    await none_memory.retain_async(
        bank_id=bank_id,
        content="The quarterly revenue report showed strong growth in Q3 2024.",
        context="business update",
        request_context=request_context,
    )

    query = "What was the revenue in Q3 2024?"

    # Measure with temporal extraction enabled
    os.environ.pop(ENV_ENABLE_TEMPORAL_EXTRACTION, None)
    clear_config_cache()

    enabled_times = []
    for _ in range(3):
        start = time.perf_counter()
        await none_memory.recall_async(
            bank_id=bank_id,
            query=query,
            budget=Budget.LOW,
            request_context=request_context,
        )
        enabled_times.append((time.perf_counter() - start) * 1000)

    # Measure with temporal extraction disabled
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    clear_config_cache()

    disabled_times = []
    for _ in range(3):
        start = time.perf_counter()
        await none_memory.recall_async(
            bank_id=bank_id,
            query=query,
            budget=Budget.LOW,
            request_context=request_context,
        )
        disabled_times.append((time.perf_counter() - start) * 1000)

    enabled_avg = sum(enabled_times) / len(enabled_times)
    disabled_avg = sum(disabled_times) / len(disabled_times)

    print(f"\n  Enabled avg:  {enabled_avg:.1f}ms")
    print(f"  Disabled avg: {disabled_avg:.1f}ms")
    print(f"  Savings:      {enabled_avg - disabled_avg:.1f}ms")

    # Disabled should be faster
    assert disabled_avg < enabled_avg, (
        f"Expected disabled ({disabled_avg:.1f}ms) to be faster than enabled ({enabled_avg:.1f}ms)"
    )


# ---------------------------------------------------------------------------
# Integration tests with real LLM — retains extract facts, recall searches them.
# These require HINDSIGHT_API_LLM_API_KEY in the environment (available in CI).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_recall_with_temporal_extraction_enabled(memory, request_context):
    """
    With a real LLM: retain extracts facts, recall finds them with temporal
    extraction enabled (4-way retrieval).
    """
    os.environ.pop(ENV_ENABLE_TEMPORAL_EXTRACTION, None)
    clear_config_cache()

    bank_id = f"test_llm_temporal_on_{datetime.now(timezone.utc).timestamp()}"

    await memory.retain_async(
        bank_id=bank_id,
        content="In March 2024, the team shipped the new authentication system. It replaced the legacy OAuth flow with OIDC.",
        context="engineering update",
        request_context=request_context,
    )

    result = await memory.recall_async(
        bank_id=bank_id,
        query="What happened with authentication in March 2024?",
        budget=Budget.LOW,
        request_context=request_context,
    )

    assert len(result.results) > 0, "Should find facts with temporal extraction enabled"


@pytest.mark.asyncio
async def test_llm_recall_with_temporal_extraction_disabled(memory, request_context):
    """
    With a real LLM: retain extracts facts, recall finds them with temporal
    extraction disabled (3-way retrieval — semantic + BM25 + graph).
    """
    bank_id = f"test_llm_temporal_off_{datetime.now(timezone.utc).timestamp()}"

    await memory.retain_async(
        bank_id=bank_id,
        content="In March 2024, the team shipped the new authentication system. It replaced the legacy OAuth flow with OIDC.",
        context="engineering update",
        request_context=request_context,
    )

    # Disable temporal extraction for recall
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    clear_config_cache()

    result = await memory.recall_async(
        bank_id=bank_id,
        query="What happened with authentication in March 2024?",
        budget=Budget.LOW,
        request_context=request_context,
    )

    assert len(result.results) > 0, "Should find facts even with temporal extraction disabled (3-way retrieval)"


@pytest.mark.asyncio
async def test_llm_recall_latency_comparison(memory, request_context):
    """
    With a real LLM: measure recall latency with temporal extraction on vs off.
    """
    bank_id = f"test_llm_latency_{datetime.now(timezone.utc).timestamp()}"

    await memory.retain_async(
        bank_id=bank_id,
        content="The quarterly revenue report showed strong growth in Q3 2024. Revenue increased 15% year over year.",
        context="business update",
        request_context=request_context,
    )

    query = "What was the revenue in Q3 2024?"

    # Measure with temporal extraction enabled
    os.environ.pop(ENV_ENABLE_TEMPORAL_EXTRACTION, None)
    clear_config_cache()

    enabled_times = []
    for _ in range(3):
        start = time.perf_counter()
        await memory.recall_async(
            bank_id=bank_id,
            query=query,
            budget=Budget.LOW,
            request_context=request_context,
        )
        enabled_times.append((time.perf_counter() - start) * 1000)

    # Measure with temporal extraction disabled
    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    clear_config_cache()

    disabled_times = []
    for _ in range(3):
        start = time.perf_counter()
        await memory.recall_async(
            bank_id=bank_id,
            query=query,
            budget=Budget.LOW,
            request_context=request_context,
        )
        disabled_times.append((time.perf_counter() - start) * 1000)

    enabled_avg = sum(enabled_times) / len(enabled_times)
    disabled_avg = sum(disabled_times) / len(disabled_times)

    print(f"\n  LLM Enabled avg:  {enabled_avg:.1f}ms")
    print(f"  LLM Disabled avg: {disabled_avg:.1f}ms")
    print(f"  LLM Savings:      {enabled_avg - disabled_avg:.1f}ms")

    assert disabled_avg < enabled_avg, (
        f"Expected disabled ({disabled_avg:.1f}ms) to be faster than enabled ({enabled_avg:.1f}ms)"
    )


# ---------------------------------------------------------------------------
# Graph retrieval config tests
# ---------------------------------------------------------------------------

def test_graph_retrieval_defaults_to_true():
    """Default value should be True (graph retrieval on)."""
    assert DEFAULT_ENABLE_GRAPH_RETRIEVAL is True


def test_config_disables_graph_retrieval_when_false():
    """Setting the env var to 'false' should disable graph retrieval."""
    os.environ[ENV_ENABLE_GRAPH_RETRIEVAL] = "false"
    os.environ.setdefault("HINDSIGHT_API_LLM_PROVIDER", "mock")
    config = HindsightConfig.from_env()
    assert config.enable_graph_retrieval is False


# ---------------------------------------------------------------------------
# Full RAG mode integration tests — temporal OFF + graph OFF (2-way retrieval)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_with_both_temporal_and_graph_disabled(none_memory, request_context):
    """
    With both temporal extraction and graph retrieval disabled, recall should
    still return results via semantic + BM25 only (2-way retrieval).
    """
    bank_id = f"test_rag_mode_{datetime.now(timezone.utc).timestamp()}"

    await none_memory.retain_async(
        bank_id=bank_id,
        content="Alice is a software engineer who specializes in distributed systems and Kubernetes.",
        context="team info",
        request_context=request_context,
    )

    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    os.environ[ENV_ENABLE_GRAPH_RETRIEVAL] = "false"
    clear_config_cache()

    result = await none_memory.recall_async(
        bank_id=bank_id,
        query="Who is Alice?",
        budget=Budget.LOW,
        include_chunks=True,
        request_context=request_context,
    )

    has_results = len(result.results) > 0 or (result.chunks is not None and len(result.chunks) > 0)
    assert has_results, "Should find results with 2-way retrieval (semantic + BM25 only)"


@pytest.mark.asyncio
async def test_llm_recall_rag_mode(memory, request_context):
    """
    Full RAG mode with real LLM: temporal OFF + graph OFF.
    Recall should still find LLM-extracted facts via semantic + BM25.
    """
    bank_id = f"test_llm_rag_{datetime.now(timezone.utc).timestamp()}"

    await memory.retain_async(
        bank_id=bank_id,
        content="In March 2024, the team shipped the new authentication system. It replaced the legacy OAuth flow with OIDC.",
        context="engineering update",
        request_context=request_context,
    )

    os.environ[ENV_ENABLE_TEMPORAL_EXTRACTION] = "false"
    os.environ[ENV_ENABLE_GRAPH_RETRIEVAL] = "false"
    clear_config_cache()

    result = await memory.recall_async(
        bank_id=bank_id,
        query="What happened with authentication?",
        budget=Budget.LOW,
        request_context=request_context,
    )

    assert len(result.results) > 0, "Should find facts in RAG mode (2-way retrieval)"
