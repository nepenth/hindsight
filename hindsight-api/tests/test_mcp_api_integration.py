"""
Integration test for the MCP (Model Context Protocol) server.

Tests MCP endpoints by starting a real FastAPI server with MCP enabled and using the MCP client.
Uses Streamable HTTP transport, which is the recommended MCP transport that provides:
- Single HTTP endpoint for all communication
- Streaming responses via Server-Sent Events
- Proper session management
- Better performance than legacy SSE transport

These tests verify the full integration flow including:
- Server startup with proper lifespan management
- MCP client connection and session initialization
- Tool listing and execution
- Multi-tenant bank_id routing
- Concurrent request handling
"""
import asyncio
import socket
import pytest
import pytest_asyncio
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from hindsight_api.api import create_app


def get_free_port():
    """Get a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


class UvicornServer:
    """Helper class to run uvicorn in background."""

    def __init__(self, app, host: str, port: int):
        self.config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self._task = None

    async def start(self):
        """Start the server in background."""
        self._task = asyncio.create_task(self.server.serve())
        # Wait for server to be ready
        while not self.server.started:
            await asyncio.sleep(0.01)

    async def stop(self):
        """Stop the server."""
        self.server.should_exit = True
        if self._task:
            await self._task


@pytest_asyncio.fixture
async def mcp_server(memory):
    """Start a real FastAPI server with MCP enabled and return the MCP URL."""
    import uuid

    # Memory is already initialized by the conftest fixture (with migrations)
    app = create_app(
        memory,
        initialize_memory=False,
        mcp_api_enabled=True,
        mcp_mount_path="/mcp"
    )

    port = get_free_port()
    server = UvicornServer(app, "127.0.0.1", port)
    await server.start()

    # Use a unique bank_id for tests - bank will be auto-created on first retain
    bank_id = f"mcp-test-{uuid.uuid4().hex[:8]}"

    # Return the Streamable HTTP URL: /mcp/{bank_id}/mcp
    mcp_url = f"http://127.0.0.1:{port}/mcp/{bank_id}/mcp"

    yield mcp_url

    # Cleanup
    await server.stop()
    # Delete test bank data
    await memory.delete_bank(bank_id)


@pytest.mark.asyncio
async def test_mcp_list_tools(mcp_server):
    """Test that MCP server exposes the expected tools."""
    mcp_url = mcp_server

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_list = await session.list_tools()
            tool_names = [t.name for t in tools_list.tools]

            assert "retain" in tool_names
            assert "recall" in tool_names


@pytest.mark.asyncio
async def test_mcp_retain_and_recall(mcp_server):
    """Test retain and recall flow via MCP."""
    mcp_url = mcp_server

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Store a memory via retain
            put_result = await session.call_tool(
                "retain",
                arguments={
                    "content": "User loves Python programming and prefers functional style",
                    "context": "programming_preferences",
                }
            )
            assert put_result is not None

            # Wait for indexing
            await asyncio.sleep(1)

            # Search for it via recall
            search_result = await session.call_tool(
                "recall",
                arguments={
                    "query": "What programming languages does the user like?",
                }
            )
            assert search_result is not None


@pytest.mark.asyncio
async def test_mcp_multiple_concurrent_requests(mcp_server):
    """Test multiple concurrent requests from a single session."""
    mcp_url = mcp_server

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Fire off concurrent recall requests
            async def make_search(idx):
                try:
                    result = await session.call_tool(
                        "recall",
                        arguments={
                            "query": f"test query {idx}",
                        }
                    )
                    return idx, "success", result
                except Exception as e:
                    return idx, "error", str(e)

            tasks = [make_search(i) for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes
            successes = sum(
                1 for r in results
                if not isinstance(r, Exception) and r[1] == "success"
            )

            # Most requests should succeed
            assert successes >= 3, f"Too many failures: only {successes}/5 succeeded"


@pytest.mark.asyncio
async def test_mcp_rapid_sessions(mcp_server):
    """Test rapid-fire requests with multiple sessions."""
    mcp_url = mcp_server

    async def rapid_session_search(idx):
        """Create a new session and immediately make a request."""
        try:
            async with streamablehttp_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "recall",
                        arguments={
                            "query": f"rapid query {idx}",
                        }
                    )
                    return idx, "success", result
        except Exception as e:
            return idx, "error", str(e)

    # Fire requests with their own sessions
    tasks = [rapid_session_search(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # Count errors
    errors = [(idx, data) for idx, status, data in results if status == "error"]

    # Most requests should succeed
    assert len(errors) < 5, f"Too many errors: {len(errors)}/10"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
