"""
Pytest configuration and shared fixtures.
"""
import pytest
import pytest_asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from hindsight_api import MemoryEngine, LLMConfig, SentenceTransformersEmbeddings

from hindsight_api.engine.cross_encoder import SentenceTransformersCrossEncoder
from hindsight_api.engine.query_analyzer import DateparserQueryAnalyzer

# Default database URL using pg0 with test-specific instance on a different port
DEFAULT_DATABASE_URL = "pg0://hindsight-test:5556"


# Load environment variables from .env at the start of test session
def pytest_configure(config):
    """Load environment variables before running tests."""
    # Look for .env in the workspace root (two levels up from tests dir)
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        print(f"Warning: {env_file} not found, tests may fail without proper configuration")


@pytest.fixture(scope="session")
def db_url():
    """
    Provide a PostgreSQL connection URL for tests.

    Supports:
    - pg0://instance-name - Start a pg0 instance with the given name
    - pg0:// or pg0 - Start a pg0 instance with default name "hindsight"
    - postgresql://... - Use the provided URL directly

    Set HINDSIGHT_API_DATABASE_URL environment variable to override.
    Default: pg0://hindsight-test
    """
    return os.getenv("HINDSIGHT_API_DATABASE_URL", DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def llm_config():
    """
    Provide LLM configuration for tests.
    This can be used by tests that need to call LLM directly without memory system.
    """
    return LLMConfig.for_memory()


@pytest.fixture(scope="session")
def embeddings():

    return SentenceTransformersEmbeddings("BAAI/bge-small-en-v1.5")



@pytest.fixture(scope="session")
def cross_encoder():

    return SentenceTransformersCrossEncoder()

@pytest.fixture(scope="session")
def query_analyzer():
    return DateparserQueryAnalyzer()




@pytest_asyncio.fixture(scope="function")
async def memory(db_url, embeddings, cross_encoder, query_analyzer):
    """
    Provide a MemoryEngine instance for each test.

    Must be function-scoped because:
    1. pytest-xdist runs tests in separate processes with different event loops
    2. asyncpg pools are bound to the event loop that created them
    3. Each test needs its own pool in its own event loop

    Uses small pool sizes since tests run in parallel.
    """
    mem = MemoryEngine(
        db_url=db_url,
        memory_llm_provider=os.getenv("HINDSIGHT_API_LLM_PROVIDER", "groq"),
        memory_llm_api_key=os.getenv("HINDSIGHT_API_LLM_API_KEY"),
        memory_llm_model=os.getenv("HINDSIGHT_API_LLM_MODEL", "openai/gpt-oss-120b"),
        memory_llm_base_url=os.getenv("HINDSIGHT_API_LLM_BASE_URL") or None,
        embeddings=embeddings,
        cross_encoder=cross_encoder,
        query_analyzer=query_analyzer,
        pool_min_size=1,
        pool_max_size=5,
    )
    await mem.initialize()
    yield mem
    try:
        if mem._pool and not mem._pool._closing:
            await mem.close()
    except Exception:
        pass
