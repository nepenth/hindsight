"""Hindsight MCP Server implementation using FastMCP."""

import json
import logging
import os
from contextvars import ContextVar

from fastmcp import FastMCP

from hindsight_api import MemoryEngine
from hindsight_api.engine.response_models import VALID_RECALL_FACT_TYPES

# Configure logging from HINDSIGHT_API_LOG_LEVEL environment variable
_log_level_str = os.environ.get("HINDSIGHT_API_LOG_LEVEL", "info").lower()
_log_level_map = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": logging.DEBUG,
}
logging.basicConfig(
    level=_log_level_map.get(_log_level_str, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Context variable to hold the current bank_id from the URL path
_current_bank_id: ContextVar[str | None] = ContextVar("current_bank_id", default=None)


def get_current_bank_id() -> str | None:
    """Get the current bank_id from context (set from URL path)."""
    return _current_bank_id.get()


def create_mcp_server(memory: MemoryEngine) -> FastMCP:
    """
    Create and configure the Hindsight MCP server.

    Args:
        memory: MemoryEngine instance (required)

    Returns:
        Configured FastMCP server instance
    """
    mcp = FastMCP("hindsight-mcp-server")

    @mcp.tool()
    async def retain(content: str, context: str = "general") -> str:
        """
        Store important information to long-term memory.

        Use this tool PROACTIVELY whenever the user shares:
        - Personal facts, preferences, or interests
        - Important events or milestones
        - User history, experiences, or background
        - Decisions, opinions, or stated preferences
        - Goals, plans, or future intentions
        - Relationships or people mentioned
        - Work context, projects, or responsibilities

        Args:
            content: The fact/memory to store (be specific and include relevant details)
            context: Category for the memory (e.g., 'preferences', 'work', 'hobbies', 'family'). Default: 'general'
        """
        try:
            bank_id = get_current_bank_id()
            await memory.retain_batch_async(bank_id=bank_id, contents=[{"content": content, "context": context}])
            return "Memory stored successfully"
        except Exception as e:
            logger.error(f"Error storing memory: {e}", exc_info=True)
            return f"Error: {str(e)}"

    @mcp.tool()
    async def recall(query: str, max_results: int = 10) -> str:
        """
        Search memories to provide personalized, context-aware responses.

        Use this tool PROACTIVELY to:
        - Check user's preferences before making suggestions
        - Recall user's history to provide continuity
        - Remember user's goals and context
        - Personalize responses based on past interactions

        Args:
            query: Natural language search query (e.g., "user's food preferences", "what projects is user working on")
            max_results: Maximum number of results to return (default: 10)
        """
        try:
            bank_id = get_current_bank_id()
            from hindsight_api.engine.memory_engine import Budget

            search_result = await memory.recall_async(
                bank_id=bank_id, query=query, fact_type=list(VALID_RECALL_FACT_TYPES), budget=Budget.LOW
            )

            results = [
                {
                    "id": fact.id,
                    "text": fact.text,
                    "type": fact.fact_type,
                    "context": fact.context,
                    "event_date": fact.event_date,
                }
                for fact in search_result.results[:max_results]
            ]

            return json.dumps({"results": results}, indent=2)
        except Exception as e:
            logger.error(f"Error searching: {e}", exc_info=True)
            return json.dumps({"error": str(e), "results": []})

    return mcp


class MCPRouterMiddleware:
    """ASGI middleware that extracts bank_id from path and routes to MCP server.

    This middleware wraps the FastMCP http_app and:
    1. Extracts bank_id from the URL path (pattern: /{bank_id}/mcp)
    2. Sets the bank_id in a context variable for tools to access
    3. Forwards requests to the underlying MCP app with the correct path (/mcp)

    The middleware also handles lifespan events to ensure the MCP server's
    session manager is properly initialized.
    """

    def __init__(self, mcp_http_app):
        self.mcp_http_app = mcp_http_app
        self._lifespan_started = False

    async def __call__(self, scope, receive, send):
        logger.debug(f"MCPRouterMiddleware: type={scope['type']}, path={scope.get('path', 'N/A')}")

        # Handle lifespan events - forward to MCP app
        if scope["type"] == "lifespan":
            logger.debug("MCPRouterMiddleware: handling lifespan")
            await self.mcp_http_app(scope, receive, send)
            return

        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.mcp_http_app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Strip any mount prefix (root_path) from the path
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path):] or "/"

        # Path should now be like /{bank_id}/mcp or /{bank_id}
        # Extract bank_id from first path segment
        if not path.startswith("/") or len(path) <= 1:
            await self._send_error(send, 400, "bank_id required in path: /{bank_id}/mcp")
            return

        parts = path[1:].split("/", 1)
        if not parts[0]:
            await self._send_error(send, 400, "bank_id required in path: /{bank_id}/mcp")
            return

        bank_id = parts[0]
        # The remainder of the path after bank_id, or /mcp if nothing follows
        remaining_path = "/" + parts[1] if len(parts) > 1 else "/mcp"

        logger.debug(f"MCPRouterMiddleware: bank_id={bank_id}, remaining_path={remaining_path}")

        # Set bank_id context for this request
        token = _current_bank_id.set(bank_id)
        try:
            # Create new scope with the path that FastMCP expects (/mcp)
            new_scope = scope.copy()
            new_scope["path"] = remaining_path
            new_scope["raw_path"] = remaining_path.encode()
            # Clear root_path since we've already handled the routing
            new_scope["root_path"] = ""

            logger.debug(f"MCPRouterMiddleware: forwarding to MCP app with path={remaining_path}")
            await self.mcp_http_app(new_scope, receive, send)
        finally:
            _current_bank_id.reset(token)

    async def _send_error(self, send, status: int, message: str):
        """Send an error response."""
        body = json.dumps({"error": message}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )


def create_mcp_app(memory: MemoryEngine):
    """
    Create an ASGI app that handles MCP requests using Streamable HTTP transport.

    URL pattern: {mount_path}/{bank_id}/mcp

    The bank_id is extracted from the URL path and made available to tools.
    Uses Streamable HTTP transport (recommended by MCP spec).

    Args:
        memory: MemoryEngine instance

    Returns:
        Tuple of (ASGI application, lifespan context manager).
        The lifespan MUST be passed to the parent FastAPI app for Streamable HTTP to work.
        This is required because Starlette's Mount doesn't forward lifespan events.
    """
    mcp_server = create_mcp_server(memory)
    # Use Streamable HTTP transport (recommended)
    mcp_http_app = mcp_server.http_app(transport="streamable-http")

    # Wrap with router middleware for bank_id extraction
    router_app = MCPRouterMiddleware(mcp_http_app)

    # Return both the app and the lifespan
    # The lifespan must be passed to the parent FastAPI app because
    # Starlette's Mount doesn't forward lifespan events to mounted apps
    return router_app, mcp_http_app.lifespan
