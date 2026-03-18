---
sidebar_position: 12
---

# LangGraph ReAct Agent with Long-Term Memory

A ReAct agent built with LangGraph that remembers user preferences and past interactions across conversations using Hindsight memory.

## What This Demonstrates

- A LangGraph ReAct agent with retain/recall/reflect tools
- Per-user memory banks resolved dynamically from config
- Memory persisting across separate graph invocations
- Tags for scoping memories by conversation

## Prerequisites

- Python 3.10+
- Hindsight running locally (Docker or pip)
- An OpenAI API key (or any LangChain-supported model)

## Start Hindsight Locally

```bash
export OPENAI_API_KEY="your-openai-api-key"

docker run --rm -it --pull always -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \
  -e HINDSIGHT_API_LLM_MODEL=gpt-4o-mini \
  -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

## 1. Install Dependencies

```bash
pip install hindsight-langgraph langchain-openai
```

## 2. Create the Agent

```python
import asyncio
import os
from hindsight_client import Hindsight
from hindsight_langgraph import create_hindsight_tools
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

client = Hindsight(base_url="http://localhost:8888")


async def chat(user_id: str, message: str) -> str:
    """Send a message to the agent with per-user memory."""
    # Each user gets their own memory bank
    tools = create_hindsight_tools(
        client=client,
        bank_id=f"user-{user_id}",
        tags=["source:chat"],
        budget="mid",
    )

    agent = create_react_agent(
        ChatOpenAI(model="gpt-4o-mini"),
        tools=tools,
        prompt="You are a helpful assistant with long-term memory. "
               "Use hindsight_retain to store important facts about the user. "
               "Use hindsight_recall to search your memory before answering. "
               "Use hindsight_reflect for thoughtful summaries of what you know.",
    )

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": message}]}
    )
    return result["messages"][-1].content
```

## 3. Run Multi-Turn Conversations

```python
async def main():
    # Create user's memory bank
    await client.acreate_bank("user-alice", name="Alice's Memory")

    # Conversation 1: Store preferences
    print("--- Conversation 1 ---")
    response = await chat("alice",
        "Hi! I'm Alice. I'm a data scientist who works with Python and SQL. "
        "I prefer dark mode and use VS Code. Please remember all of this.")
    print(f"Agent: {response}\n")

    # Wait for memory processing
    await asyncio.sleep(2)

    # Conversation 2: Recall preferences (new invocation, memory persists)
    print("--- Conversation 2 ---")
    response = await chat("alice",
        "What IDE do I use? And what's my job?")
    print(f"Agent: {response}\n")

    # Conversation 3: Reflect on accumulated knowledge
    print("--- Conversation 3 ---")
    response = await chat("alice",
        "Based on everything you know about me, what tools and setup "
        "would you recommend for a new machine learning project?")
    print(f"Agent: {response}\n")

    # Cleanup
    await client.adelete_bank("user-alice")

asyncio.run(main())
```

## 4. Alternative: Automatic Memory with Graph Nodes

Instead of relying on the agent to call tools, you can add memory as automatic graph steps:

```python
from hindsight_langgraph import create_recall_node, create_retain_node
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END


async def llm_node(state: MessagesState):
    """Your LLM call — memories are already injected as a SystemMessage."""
    model = ChatOpenAI(model="gpt-4o-mini")
    response = await model.ainvoke(state["messages"])
    return {"messages": [response]}


def build_graph(client: Hindsight, user_id: str):
    recall = create_recall_node(
        client=client,
        bank_id_from_config="user_id",
        budget="low",
        max_results=5,
    )
    retain = create_retain_node(
        client=client,
        bank_id_from_config="user_id",
        tags=["source:auto"],
    )

    builder = StateGraph(MessagesState)
    builder.add_node("recall", recall)
    builder.add_node("llm", llm_node)
    builder.add_node("retain", retain)

    builder.add_edge(START, "recall")
    builder.add_edge("recall", "llm")
    builder.add_edge("llm", "retain")
    builder.add_edge("retain", END)

    return builder.compile()


async def main():
    client = Hindsight(base_url="http://localhost:8888")
    graph = build_graph(client, "bob")

    await client.acreate_bank("user-bob", name="Bob's Memory")

    # First message — retained automatically
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="I'm training for a marathon next month")]},
        config={"configurable": {"user_id": "user-bob"}},
    )
    print(result["messages"][-1].content)

    await asyncio.sleep(2)

    # Second message — recalls the marathon context automatically
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="What exercise should I do today?")]},
        config={"configurable": {"user_id": "user-bob"}},
    )
    print(result["messages"][-1].content)

    await client.adelete_bank("user-bob")

asyncio.run(main())
```

## Key Takeaways

- **Tools pattern**: The agent decides when to store/retrieve. Best for complex reasoning flows.
- **Nodes pattern**: Memory happens automatically. Best when you always want context injection.
- **Dynamic banks**: Use `bank_id_from_config` or parameterized `bank_id` for per-user isolation.
- **Tags**: Scope memories by source, conversation, or topic for precise recall.
