"""LangGraph tool definitions for Hindsight memory operations.

Provides factory functions that create LangGraph-compatible tool functions
backed by Hindsight's retain/recall/reflect APIs. These tools can be bound
to a ChatModel via `model.bind_tools()` or used in a ToolNode.
"""

from __future__ import annotations

import logging
from typing import Any

from hindsight_client import Hindsight
from langchain_core.tools import tool

from .config import get_config
from .errors import HindsightError

logger = logging.getLogger(__name__)


def _resolve_client(
    client: Hindsight | None,
    hindsight_api_url: str | None,
    api_key: str | None,
) -> Hindsight:
    """Resolve a Hindsight client from explicit args or global config."""
    if client is not None:
        return client

    config = get_config()
    url = hindsight_api_url or (config.hindsight_api_url if config else None)
    key = api_key or (config.api_key if config else None)

    if url is None:
        raise HindsightError(
            "No Hindsight API URL configured. "
            "Pass client= or hindsight_api_url=, or call configure() first."
        )

    kwargs: dict[str, Any] = {"base_url": url, "timeout": 30.0}
    if key:
        kwargs["api_key"] = key
    return Hindsight(**kwargs)


def create_hindsight_tools(
    *,
    bank_id: str,
    client: Hindsight | None = None,
    hindsight_api_url: str | None = None,
    api_key: str | None = None,
    budget: str = "mid",
    max_tokens: int = 4096,
    tags: list[str] | None = None,
    recall_tags: list[str] | None = None,
    recall_tags_match: str = "any",
    # Retain options
    retain_metadata: dict[str, str] | None = None,
    retain_document_id: str | None = None,
    # Recall options
    recall_types: list[str] | None = None,
    recall_include_entities: bool = False,
    # Reflect options
    reflect_context: str | None = None,
    reflect_max_tokens: int | None = None,
    reflect_response_schema: dict[str, Any] | None = None,
    reflect_tags: list[str] | None = None,
    reflect_tags_match: str | None = None,
    include_retain: bool = True,
    include_recall: bool = True,
    include_reflect: bool = True,
) -> list:
    """Create Hindsight memory tools for a LangGraph agent.

    Returns a list of LangChain tool instances compatible with LangGraph's
    ToolNode and ChatModel.bind_tools().

    Args:
        bank_id: The Hindsight memory bank to operate on.
        client: Pre-configured Hindsight client (preferred).
        hindsight_api_url: API URL (used if no client provided).
        api_key: API key (used if no client provided).
        budget: Recall/reflect budget level (low/mid/high).
        max_tokens: Maximum tokens for recall results.
        tags: Tags applied when storing memories via retain.
        recall_tags: Tags to filter when searching memories.
        recall_tags_match: Tag matching mode (any/all/any_strict/all_strict).
        retain_metadata: Default metadata dict for retain operations.
        retain_document_id: Default document_id for retain (groups/upserts memories).
        recall_types: Fact types to filter (world, experience, opinion, observation).
        recall_include_entities: Include entity information in recall results.
        reflect_context: Additional context for reflect operations.
        reflect_max_tokens: Max tokens for reflect results (defaults to max_tokens).
        reflect_response_schema: JSON schema to constrain reflect output format.
        reflect_tags: Tags to filter memories used in reflect (defaults to recall_tags).
        reflect_tags_match: Tag matching for reflect (defaults to recall_tags_match).
        include_retain: Include the retain (store) tool.
        include_recall: Include the recall (search) tool.
        include_reflect: Include the reflect (synthesize) tool.

    Returns:
        List of LangChain tool instances.

    Raises:
        HindsightError: If no client or API URL can be resolved.
    """
    resolved_client = _resolve_client(client, hindsight_api_url, api_key)

    config = get_config()
    effective_tags = tags if tags is not None else (config.tags if config else None)
    effective_recall_tags = recall_tags if recall_tags is not None else (config.recall_tags if config else None)
    effective_recall_tags_match = recall_tags_match or (config.recall_tags_match if config else "any")
    effective_budget = budget or (config.budget if config else "mid")
    effective_max_tokens = max_tokens or (config.max_tokens if config else 4096)

    tools: list = []

    if include_retain:

        @tool
        async def hindsight_retain(content: str) -> str:
            """Store information to long-term memory for later retrieval.

            Use this to save important facts, user preferences, decisions,
            or any information that should be remembered across conversations.

            Args:
                content: The information to store in memory.
            """
            try:
                retain_kwargs: dict[str, Any] = {"bank_id": bank_id, "content": content}
                if effective_tags:
                    retain_kwargs["tags"] = effective_tags
                if retain_metadata:
                    retain_kwargs["metadata"] = retain_metadata
                if retain_document_id:
                    retain_kwargs["document_id"] = retain_document_id
                await resolved_client.aretain(**retain_kwargs)
                return "Memory stored successfully."
            except Exception as e:
                logger.error(f"Retain failed: {e}")
                raise HindsightError(f"Retain failed: {e}") from e

        tools.append(hindsight_retain)

    if include_recall:

        @tool
        async def hindsight_recall(query: str) -> str:
            """Search long-term memory for relevant information.

            Use this to find previously stored facts, preferences, or context.
            Returns a numbered list of matching memories.

            Args:
                query: What to search for in memory.
            """
            try:
                recall_kwargs: dict[str, Any] = {
                    "bank_id": bank_id,
                    "query": query,
                    "budget": effective_budget,
                    "max_tokens": effective_max_tokens,
                }
                if effective_recall_tags:
                    recall_kwargs["tags"] = effective_recall_tags
                    recall_kwargs["tags_match"] = effective_recall_tags_match
                if recall_types:
                    recall_kwargs["types"] = recall_types
                if recall_include_entities:
                    recall_kwargs["include_entities"] = True
                response = await resolved_client.arecall(**recall_kwargs)
                if not response.results:
                    return "No relevant memories found."
                lines = []
                for i, result in enumerate(response.results, 1):
                    lines.append(f"{i}. {result.text}")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Recall failed: {e}")
                raise HindsightError(f"Recall failed: {e}") from e

        tools.append(hindsight_recall)

    if include_reflect:

        @tool
        async def hindsight_reflect(query: str) -> str:
            """Synthesize a thoughtful answer from long-term memories.

            Use this when you need a coherent summary or reasoned response
            about what you know, rather than raw memory facts.

            Args:
                query: The question to reflect on using stored memories.
            """
            try:
                reflect_kwargs: dict[str, Any] = {
                    "bank_id": bank_id,
                    "query": query,
                    "budget": effective_budget,
                }
                if reflect_context:
                    reflect_kwargs["context"] = reflect_context
                effective_reflect_max = reflect_max_tokens or effective_max_tokens
                if effective_reflect_max:
                    reflect_kwargs["max_tokens"] = effective_reflect_max
                if reflect_response_schema:
                    reflect_kwargs["response_schema"] = reflect_response_schema
                # Reflect tags: use reflect-specific or fall back to recall tags
                effective_reflect_tags = reflect_tags if reflect_tags is not None else effective_recall_tags
                effective_reflect_tags_match = reflect_tags_match or effective_recall_tags_match
                if effective_reflect_tags:
                    reflect_kwargs["tags"] = effective_reflect_tags
                    reflect_kwargs["tags_match"] = effective_reflect_tags_match
                response = await resolved_client.areflect(**reflect_kwargs)
                return response.text or "No relevant memories found."
            except Exception as e:
                logger.error(f"Reflect failed: {e}")
                raise HindsightError(f"Reflect failed: {e}") from e

        tools.append(hindsight_reflect)

    return tools
