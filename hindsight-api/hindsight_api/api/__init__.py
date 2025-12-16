"""
Unified API module for Hindsight.

Provides both HTTP REST API and MCP (Model Context Protocol) server.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from hindsight_api import MemoryEngine

logger = logging.getLogger(__name__)


def create_app(
    memory: MemoryEngine,
    http_api_enabled: bool = True,
    mcp_api_enabled: bool = False,
    mcp_mount_path: str = "/mcp",
    initialize_memory: bool = True,
) -> FastAPI:
    """
    Create and configure the unified Hindsight API application.

    Args:
        memory: MemoryEngine instance (already initialized with required parameters).
                Migrations are controlled by the MemoryEngine's run_migrations parameter.
        http_api_enabled: Whether to enable HTTP REST API endpoints (default: True)
        mcp_api_enabled: Whether to enable MCP server (default: False)
        mcp_mount_path: Path to mount MCP server (default: /mcp)
        initialize_memory: Whether to initialize memory system on startup (default: True)

    Returns:
        Configured FastAPI application with enabled APIs

    Example:
        # HTTP only
        app = create_app(memory)

        # MCP only
        app = create_app(memory, http_api_enabled=False, mcp_api_enabled=True)

        # Both HTTP and MCP
        app = create_app(memory, mcp_api_enabled=True)
    """
    mcp_app = None
    mcp_lifespan = None

    # Create MCP app if enabled
    if mcp_api_enabled:
        try:
            from .mcp import create_mcp_app

            # Create MCP app with dynamic bank_id support
            # Returns (app, lifespan) - lifespan must be passed to parent FastAPI
            # because Starlette's Mount doesn't forward lifespan events
            mcp_app, mcp_lifespan = create_mcp_app(memory=memory)
        except ImportError as e:
            logger.error(f"MCP server requested but dependencies not available: {e}")
            logger.error("Install with: pip install hindsight-api[mcp]")
            raise

    # Import and create HTTP API if enabled
    if http_api_enabled:
        from .http import create_app as create_http_app

        app = create_http_app(
            memory=memory,
            initialize_memory=initialize_memory,
            mcp_lifespan=mcp_lifespan,
        )
        logger.info("HTTP REST API enabled")
    else:
        # Create minimal FastAPI app with MCP lifespan if needed
        if mcp_lifespan:
            app = FastAPI(title="Hindsight API", version="0.0.7", lifespan=mcp_lifespan)
        else:
            app = FastAPI(title="Hindsight API", version="0.0.7")
        logger.info("HTTP REST API disabled")

    # Mount MCP server if enabled
    if mcp_app:
        app.mount(mcp_mount_path, mcp_app)
        logger.info(f"MCP server enabled at {mcp_mount_path}/{{bank_id}}/mcp")

    return app


# Re-export commonly used items for backwards compatibility
from .http import (
    CreateBankRequest,
    DispositionTraits,
    MemoryItem,
    RecallRequest,
    RecallResponse,
    RecallResult,
    ReflectRequest,
    ReflectResponse,
    RetainRequest,
)

__all__ = [
    "create_app",
    "RecallRequest",
    "RecallResult",
    "RecallResponse",
    "MemoryItem",
    "RetainRequest",
    "ReflectRequest",
    "ReflectResponse",
    "CreateBankRequest",
    "DispositionTraits",
]
