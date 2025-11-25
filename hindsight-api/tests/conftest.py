"""
Pytest configuration and shared fixtures.
"""
import pytest
import pytest_asyncio
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from hindsight_api import MemoryEngine, LLMConfig
import asyncpg
from testcontainers.postgres import PostgresContainer


# Global testcontainer instance
_postgres_container = None
_db_url = None


# Load environment variables from .env at the start of test session
def pytest_configure(config):
    """Load environment variables and start testcontainer before running tests."""
    # Look for .env in the workspace root (two levels up from tests dir)
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        print(f"Warning: {env_file} not found, tests may fail without proper configuration")


@pytest.fixture(scope="session")
def postgres_container():
    """
    Start a postgres container for all tests.
    This is a session-scoped fixture that starts once and is shared by all tests.
    """
    global _postgres_container, _db_url

    if _postgres_container is None:
        # Start postgres container with pgvector extension
        _postgres_container = PostgresContainer("pgvector/pgvector:pg16")
        _postgres_container.start()

        # Get connection URL and convert to postgresql:// (asyncpg doesn't support postgresql+psycopg2://)
        _db_url = _postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")

        # Override environment variable for all tests
        os.environ["HINDSIGHT_API_DATABASE_URL"] = _db_url

        print(f"\nStarted PostgreSQL testcontainer at: {_db_url}")

        # Run migrations to create schema
        from hindsight_api.migrations import run_migrations
        run_migrations(_db_url)
        print("Ran database migrations")

    yield _db_url

    # Cleanup happens in pytest_sessionfinish


def pytest_sessionfinish(session, exitstatus):
    """Stop the testcontainer after all tests complete."""
    global _postgres_container
    if _postgres_container is not None:
        print("\nStopping PostgreSQL testcontainer...")
        _postgres_container.stop()
        _postgres_container = None


@pytest.fixture(scope="session")
def llm_config():
    """
    Provide LLM configuration for tests.
    This can be used by tests that need to call LLM directly without memory system.
    """
    return LLMConfig.for_memory()


@pytest_asyncio.fixture(scope="function")
async def memory(postgres_container):
    """
    Provide a memory system instance for each test function.
    Uses the testcontainer database URL.

    Note: Using function scope to avoid event loop issues, but this means
    the embedding model will be loaded for each test (adds ~3 seconds per test).

    Tests should handle their own cleanup by calling memory.delete_agent(agent_id)
    in their finally blocks. The fixture will attempt cleanup as a safeguard.
    """
    mem = MemoryEngine(
        db_url=postgres_container,
        memory_llm_provider=os.getenv("HINDSIGHT_API_LLM_PROVIDER", "groq"),
        memory_llm_api_key=os.getenv("HINDSIGHT_API_LLM_API_KEY"),
        memory_llm_model=os.getenv("HINDSIGHT_API_LLM_MODEL", "openai/gpt-oss-120b"),
        memory_llm_base_url=os.getenv("HINDSIGHT_API_LLM_BASE_URL") or None,  # Use None to get provider defaults
    )
    await mem.initialize()
    yield mem
    # Attempt cleanup (tests should already have called close, but this is a safeguard)
    try:
        if mem._pool and not mem._pool._closing:
            await mem.close()
    except Exception as e:
        # Ignore errors during fixture cleanup since test may have already closed
        pass


@pytest_asyncio.fixture(scope="function")
async def clean_agent(memory):
    """
    Provide a clean agent ID and clean up data after test.
    Uses agent_id='test' for all tests (multi-tenant isolation).
    """
    agent_id = "test"

    # Clean up before test
    await memory.delete_agent(agent_id)

    yield agent_id

    # Clean up after test
    try:
        await memory.delete_agent(agent_id)
    except Exception as e:
        print(f"Warning: Error during agent cleanup: {e}")


@pytest_asyncio.fixture
async def db_connection(postgres_container):
    """
    Provide a database connection for direct DB queries in tests.
    Uses the testcontainer database URL.
    """
    conn = await asyncpg.connect(postgres_container, statement_cache_size=0)
    yield conn
    try:
        await conn.close()
    except Exception as e:
        print(f"Warning: Error closing connection: {e}")
