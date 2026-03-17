"""Pre-built LangGraph nodes for Hindsight memory operations.

Provides node functions that can be added directly to a StateGraph to
inject memories at conversation start and store new memories after responses.
"""

from __future__ import annotations

import logging
from typing import Any

from hindsight_client import Hindsight
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState

from .config import get_config
from .errors import HindsightError
from .tools import _resolve_client

logger = logging.getLogger(__name__)


def create_recall_node(
    *,
    bank_id: str | None = None,
    client: Hindsight | None = None,
    hindsight_api_url: str | None = None,
    api_key: str | None = None,
    budget: str = "low",
    max_tokens: int = 4096,
    max_results: int = 10,
    tags: list[str] | None = None,
    tags_match: str = "any",
    bank_id_from_config: str = "user_id",
):
    """Create a node that injects relevant memories into the conversation.

    This node extracts the latest user message, recalls relevant memories
    from Hindsight, and prepends them as a system message. It should be
    placed before the LLM call node in your graph.

    The bank_id can be provided directly or resolved dynamically from
    the graph's RunnableConfig via the ``bank_id_from_config`` key.

    Args:
        bank_id: Static Hindsight memory bank ID.
        client: Pre-configured Hindsight client.
        hindsight_api_url: API URL (used if no client provided).
        api_key: API key (used if no client provided).
        budget: Recall budget level (low/mid/high).
        max_tokens: Maximum tokens for recall results.
        max_results: Maximum number of memories to inject.
        tags: Tags to filter recall results.
        tags_match: Tag matching mode.
        bank_id_from_config: Config key to read bank_id from at runtime.
            Looked up in ``config["configurable"][bank_id_from_config]``.
            Only used when ``bank_id`` is not provided.

    Returns:
        An async node function compatible with LangGraph StateGraph.
    """
    resolved_client = _resolve_client(client, hindsight_api_url, api_key)

    async def recall_node(state: MessagesState, config: RunnableConfig | None = None) -> dict[str, Any]:
        resolved_bank_id = bank_id
        if resolved_bank_id is None and config:
            configurable = config.get("configurable", {})
            resolved_bank_id = configurable.get(bank_id_from_config)

        if not resolved_bank_id:
            logger.warning("No bank_id available for recall node, skipping memory injection.")
            return {"messages": []}

        # Extract query from the latest human message
        query = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                query = msg.content
                break

        if not query:
            return {"messages": []}

        try:
            recall_kwargs: dict[str, Any] = {
                "bank_id": resolved_bank_id,
                "query": query,
                "budget": budget,
                "max_tokens": max_tokens,
            }
            if tags:
                recall_kwargs["tags"] = tags
                recall_kwargs["tags_match"] = tags_match

            response = await resolved_client.arecall(**recall_kwargs)
            results = response.results[:max_results] if response.results else []

            if not results:
                return {"messages": []}

            lines = ["Relevant memories about this user:"]
            for i, result in enumerate(results, 1):
                lines.append(f"{i}. {result.text}")
            memory_text = "\n".join(lines)

            return {"messages": [SystemMessage(content=memory_text)]}
        except Exception as e:
            logger.error(f"Recall node failed: {e}")
            return {"messages": []}

    return recall_node


def create_retain_node(
    *,
    bank_id: str | None = None,
    client: Hindsight | None = None,
    hindsight_api_url: str | None = None,
    api_key: str | None = None,
    tags: list[str] | None = None,
    bank_id_from_config: str = "user_id",
    retain_human: bool = True,
    retain_ai: bool = False,
):
    """Create a node that stores conversation messages as memories.

    This node extracts messages from the conversation and stores them
    via Hindsight retain. It should be placed after the LLM response
    node in your graph.

    Args:
        bank_id: Static Hindsight memory bank ID.
        client: Pre-configured Hindsight client.
        hindsight_api_url: API URL (used if no client provided).
        api_key: API key (used if no client provided).
        tags: Tags to apply to stored memories.
        bank_id_from_config: Config key to read bank_id from at runtime.
        retain_human: Store human messages as memories.
        retain_ai: Store AI responses as memories.

    Returns:
        An async node function compatible with LangGraph StateGraph.
    """
    resolved_client = _resolve_client(client, hindsight_api_url, api_key)

    async def retain_node(state: MessagesState, config: RunnableConfig | None = None) -> dict[str, Any]:
        resolved_bank_id = bank_id
        if resolved_bank_id is None and config:
            configurable = config.get("configurable", {})
            resolved_bank_id = configurable.get(bank_id_from_config)

        if not resolved_bank_id:
            logger.warning("No bank_id available for retain node, skipping memory storage.")
            return {"messages": []}

        messages_to_retain = []
        for msg in state["messages"]:
            if retain_human and isinstance(msg, HumanMessage):
                messages_to_retain.append(msg.content)
            elif retain_ai and isinstance(msg, AIMessage):
                messages_to_retain.append(msg.content)

        if not messages_to_retain:
            return {"messages": []}

        content = "\n\n".join(messages_to_retain)

        try:
            retain_kwargs: dict[str, Any] = {
                "bank_id": resolved_bank_id,
                "content": content,
            }
            if tags:
                retain_kwargs["tags"] = tags
            await resolved_client.aretain(**retain_kwargs)
        except Exception as e:
            logger.error(f"Retain node failed: {e}")

        return {"messages": []}

    return retain_node
