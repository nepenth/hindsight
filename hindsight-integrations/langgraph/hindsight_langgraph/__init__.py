"""Hindsight-LangGraph: Persistent memory for LangGraph agents.

Provides Hindsight-backed tools, nodes, and a BaseStore adapter for
LangGraph, giving agents long-term memory across conversations.

Basic usage with tools::

    from hindsight_client import Hindsight
    from hindsight_langgraph import create_hindsight_tools

    client = Hindsight(base_url="http://localhost:8888")
    tools = create_hindsight_tools(client=client, bank_id="user-123")

    # Bind tools to your model
    model = ChatOpenAI(model="gpt-4o").bind_tools(tools)

Usage with memory nodes::

    from hindsight_langgraph import create_recall_node, create_retain_node

    recall = create_recall_node(client=client, bank_id="user-123")
    retain = create_retain_node(client=client, bank_id="user-123")

    builder.add_node("recall", recall)
    builder.add_node("agent", agent_node)
    builder.add_node("retain", retain)
    builder.add_edge("recall", "agent")
    builder.add_edge("agent", "retain")

Usage with BaseStore::

    from hindsight_langgraph import HindsightStore

    store = HindsightStore(client=client)
    graph = builder.compile(checkpointer=checkpointer, store=store)
"""

from .config import (
    HindsightLangGraphConfig,
    configure,
    get_config,
    reset_config,
)
from .errors import HindsightError
from .nodes import create_recall_node, create_retain_node
from .store import HindsightStore
from .tools import create_hindsight_tools

__version__ = "0.1.0"

__all__ = [
    "configure",
    "get_config",
    "reset_config",
    "HindsightLangGraphConfig",
    "HindsightError",
    "create_hindsight_tools",
    "create_recall_node",
    "create_retain_node",
    "HindsightStore",
]
