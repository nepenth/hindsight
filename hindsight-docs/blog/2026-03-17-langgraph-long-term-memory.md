---
title: "Adding Long-Term Memory to LangGraph Agents"
authors: [hindsight]
date: 2026-03-17
tags: [langgraph, langchain, integrations, agents, memory]
---

LangGraph agents are stateful by design — checkpointers save graph state between steps, and the Store API persists data across threads. But neither gives agents true long-term memory: the ability to extract meaning from conversations, build up knowledge over time, and recall it semantically when relevant.

That's what `hindsight-langgraph` adds.

<!-- truncate -->

## The problem

LangGraph's built-in persistence is designed for graph state — checkpoints, intermediate values, cross-thread key-value storage. It's good at "what did this graph do last time?" but not at "what does this agent know about this user?"

Consider a support agent that talks to the same customer across dozens of sessions. With checkpointers alone, each new thread starts cold. With the `InMemoryStore` or `PostgresStore`, you can manually store and retrieve facts, but you're responsible for:

- Deciding what to store (fact extraction)
- Deciding what's relevant (semantic retrieval)
- Handling contradictions and updates
- Building knowledge graphs from raw conversations

Hindsight does all of this automatically. You retain conversations, and it extracts facts, builds entity graphs, and retrieves relevant memories using four parallel strategies (semantic, BM25, graph traversal, temporal).

## Three integration patterns

We built three ways to add Hindsight memory to LangGraph, at different abstraction levels.

### 1. Tools — the agent decides

Give the agent retain/recall/reflect tools and let it decide when to use memory.

```python
from hindsight_client import Hindsight
from hindsight_langgraph import create_hindsight_tools
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

client = Hindsight(base_url="http://localhost:8888")
tools = create_hindsight_tools(client=client, bank_id="user-123")

agent = create_react_agent(ChatOpenAI(model="gpt-4o"), tools=tools)
```

The agent gets three tools: `hindsight_retain` (store), `hindsight_recall` (search), and `hindsight_reflect` (synthesize). It calls them based on conversation context — storing facts when the user shares something important, recalling when asked about past context.

Best for ReAct agents that need to reason about when memory is relevant.

### 2. Nodes — memory as graph steps

Add recall and retain as automatic nodes in your graph. No tool-calling required.

```python
from hindsight_langgraph import create_recall_node, create_retain_node
from langgraph.graph import StateGraph, MessagesState, START, END

recall = create_recall_node(client=client, bank_id_from_config="user_id")
retain = create_retain_node(client=client, bank_id_from_config="user_id")

builder = StateGraph(MessagesState)
builder.add_node("recall", recall)
builder.add_node("agent", agent_node)
builder.add_node("retain", retain)
builder.add_edge(START, "recall")
builder.add_edge("recall", "agent")
builder.add_edge("agent", "retain")
builder.add_edge("retain", END)
```

The recall node runs before the LLM, searches Hindsight for memories relevant to the user's message, and injects them as a `SystemMessage`. The retain node runs after, storing the conversation. Both resolve per-user bank IDs from `RunnableConfig` at runtime.

Best when you always want memory context without relying on the LLM to use tools.

### 3. BaseStore — drop-in backend

Replace LangGraph's `InMemoryStore` with Hindsight as the storage backend.

```python
from hindsight_langgraph import HindsightStore

store = HindsightStore(client=client)
graph = builder.compile(checkpointer=checkpointer, store=store)
```

Namespace tuples map to Hindsight bank IDs (`("user", "123")` → bank `user.123`), banks are auto-created, and `search()` uses Hindsight's semantic recall instead of basic vector similarity.

Best for teams already using LangGraph's store patterns who want better retrieval.

## Per-user memory in one line

All three patterns support dynamic bank IDs. Instead of hardcoding a bank, resolve it from the graph's config:

```python
recall = create_recall_node(client=client, bank_id_from_config="user_id")

# Each invocation gets its own memory bank
await graph.ainvoke(
    {"messages": [...]},
    config={"configurable": {"user_id": "user-456"}},
)
```

This means one graph definition serves all users, each with isolated memory.

## Getting started

```bash
pip install hindsight-langgraph
```

Works with both self-hosted Hindsight and [Hindsight Cloud](https://ui.hindsight.vectorize.io/signup). For cloud, just set `HINDSIGHT_API_KEY` and skip the `base_url`.

Full docs: [LangGraph integration](/docs/sdks/integrations/langgraph) | [Cookbook example](/cookbook/recipes/langgraph-react-agent) | [GitHub](https://github.com/vectorize-io/hindsight/tree/main/hindsight-integrations/langgraph)
