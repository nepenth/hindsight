"""
Test for datetime serialization in async task backend.

This test reproduces the bug where datetime objects in task payloads
cause JSON serialization errors when submitting async retain operations.
"""
import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from hindsight_api import MemoryEngine, RequestContext
from hindsight_api.engine.task_backend import BrokerTaskBackend


@pytest_asyncio.fixture
async def memory_engine_with_broker(pg0_db_url, embeddings, cross_encoder, query_analyzer):
    """
    Create a MemoryEngine instance with BrokerTaskBackend.

    This uses the actual BrokerTaskBackend (not SyncTaskBackend) which performs
    JSON serialization and would trigger the datetime bug if not handled properly.
    """
    # Create a memory engine instance with BrokerTaskBackend
    # We'll create the backend after initialize() so we can get the pool
    engine = MemoryEngine(
        db_url=pg0_db_url,
        memory_llm_provider=os.getenv("HINDSIGHT_API_LLM_PROVIDER", "groq"),
        memory_llm_api_key=os.getenv("HINDSIGHT_API_LLM_API_KEY"),
        memory_llm_model=os.getenv("HINDSIGHT_API_LLM_MODEL", "openai/gpt-oss-120b"),
        memory_llm_base_url=os.getenv("HINDSIGHT_API_LLM_BASE_URL") or None,
        embeddings=embeddings,
        cross_encoder=cross_encoder,
        query_analyzer=query_analyzer,
        pool_min_size=1,
        pool_max_size=5,
        run_migrations=False,  # Migrations already run at session scope
        task_backend=None,  # Will be set after initialization
    )
    await engine.initialize()

    # Now create and set the BrokerTaskBackend with pool access
    broker_backend = BrokerTaskBackend(
        pool_getter=lambda: engine._pool,
        schema=None,
    )
    await broker_backend.initialize()
    engine._task_backend = broker_backend

    # Use a unique bank ID for testing
    bank_id = f"test-datetime-{datetime.now(timezone.utc).timestamp()}"

    yield engine, bank_id

    # Cleanup
    try:
        await engine.close()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_async_retain_with_datetime_event_date(memory_engine_with_broker):
    """
    Test that async retain operations handle datetime objects in event_date field.

    This reproduces the bug:
    TypeError: Object of type datetime is not JSON serializable

    When content includes an event_date as a datetime object, the task backend
    must properly serialize it to JSON.
    """
    engine, bank_id = memory_engine_with_broker

    # Create content with a datetime event_date (as would come from MCP tools)
    contents = [
        {
            "content": "User attended a conference in San Francisco",
            "context": "professional event",
            "event_date": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }
    ]

    # This should not raise a JSON serialization error
    result = await engine.submit_async_retain(
        bank_id=bank_id,
        contents=contents,
        request_context=RequestContext(tenant_id="default"),
    )

    # Verify the operation was queued successfully (no JSON serialization error!)
    assert "operation_id" in result
    assert result.get("items_count") == 1
    # If we got here, the datetime was successfully serialized to JSON


@pytest.mark.asyncio
async def test_async_retain_with_multiple_datetime_fields(memory_engine_with_broker):
    """
    Test async retain with multiple datetime fields in the content.

    Ensures comprehensive datetime handling across all fields.
    """
    engine, bank_id = memory_engine_with_broker

    now = datetime.now(timezone.utc)
    past_event = datetime(2023, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

    contents = [
        {
            "content": "First memory with event date",
            "context": "test",
            "event_date": past_event,
        },
        {
            "content": "Second memory with current timestamp",
            "context": "test",
            "event_date": now,
        },
        {
            "content": "Third memory without event date",
            "context": "test",
        }
    ]

    # Should handle all variations without errors (no JSON serialization error!)
    result = await engine.submit_async_retain(
        bank_id=bank_id,
        contents=contents,
        request_context=RequestContext(tenant_id="default"),
    )

    assert "operation_id" in result
    assert result.get("items_count") == 3
    # If we got here, all datetimes were successfully serialized to JSON


@pytest.mark.asyncio
async def test_async_retain_with_naive_datetime(memory_engine_with_broker):
    """
    Test async retain with naive datetime (no timezone).

    Ensures the system can handle both timezone-aware and naive datetimes.
    """
    engine, bank_id = memory_engine_with_broker

    # Create content with a naive datetime (no timezone info)
    contents = [
        {
            "content": "Event with naive datetime",
            "context": "test",
            "event_date": datetime(2024, 1, 15, 10, 30, 0),  # No tzinfo
        }
    ]

    # Should handle naive datetime without errors (no JSON serialization error!)
    result = await engine.submit_async_retain(
        bank_id=bank_id,
        contents=contents,
        request_context=RequestContext(tenant_id="default"),
    )

    assert "operation_id" in result
    assert result.get("items_count") == 1
    # If we got here, the naive datetime was successfully serialized to JSON
