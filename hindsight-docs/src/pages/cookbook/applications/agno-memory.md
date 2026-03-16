---
sidebar_position: 16
---

# Agno + Hindsight Memory

:::info Complete Application
This is a complete, runnable application demonstrating Hindsight integration.
[**View source on GitHub →**](https://github.com/vectorize-io/hindsight/tree/main/hindsight-integrations/agno)
:::

Give your Agno agents persistent long-term memory. Build agents that remember users across conversations, learn preferences over time, and synthesize insights from past interactions.

## What This Demonstrates

- **Native Toolkit pattern** — retain, recall, and reflect registered as Agno tools via `HindsightTools`
- **Auto-injected context** — pre-recalled memories in the system prompt via `memory_instructions()`
- **Per-user memory banks** — automatic bank isolation using `RunContext.user_id`
- **Progressive learning** — the agent gets smarter with each interaction

## Architecture

```
Run 1 (user: alice):
    Alice: "I'm a vegetarian and I prefer window seats on flights"
    │
    ├─ memory_instructions() ──► recalls prior context (empty on first run)
    ├─ Agent calls retain_memory ──► stores preferences
    └─ Agent responds with acknowledgement

Run 2 (user: alice):
    Alice: "Help me plan a trip to Tokyo"
    │
    ├─ memory_instructions() ──► injects "User is vegetarian, prefers window seats..."
    ├─ Agent calls recall_memory ──► finds dietary + travel preferences
    └─ Agent recommends vegetarian restaurants, books window seats

Run 3 (user: bob):
    Bob: "What do you know about me?"
    │
    ├─ memory_instructions() ──► recalls Bob's context (empty — separate bank)
    └─ Agent responds that it doesn't have any info about Bob yet
```

Each user gets their own memory bank, so Alice's preferences never leak into Bob's conversations.

## Prerequisites

1. **Hindsight running**

   ```bash
   export OPENAI_API_KEY=your-key

   docker run --rm -it --pull always -p 8888:8888 -p 9999:9999 \
     -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \
     -e HINDSIGHT_API_LLM_MODEL=o3-mini \
     -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \
     ghcr.io/vectorize-io/hindsight:latest
   ```

2. **OpenAI API key** (for Agno's LLM)

   ```bash
   export OPENAI_API_KEY=your-key
   ```

3. **Install dependencies**

   ```bash
   pip install hindsight-agno agno openai
   ```

## Quick Start

### Minimal Example

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from hindsight_agno import HindsightTools

agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    tools=[HindsightTools(
        bank_id="my-assistant",
        hindsight_api_url="http://localhost:8888",
    )],
    markdown=True,
)

# Store something
agent.print_response("Remember that I prefer dark mode and use vim")

# Recall it
agent.print_response("What are my preferences?")
```

Run it twice — the agent still remembers on the second run.

### Travel Planner with Per-User Memory

A more realistic example: a travel planning agent that learns each user's preferences.

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from hindsight_agno import HindsightTools, memory_instructions

HINDSIGHT_URL = "http://localhost:8888"
USER_ID = "alice"

# Pre-recall relevant memories for the system prompt
memories = memory_instructions(
    bank_id=USER_ID,
    hindsight_api_url=HINDSIGHT_URL,
    query="travel preferences, dietary restrictions, and past trips",
    max_results=10,
)

agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    tools=[HindsightTools(
        bank_id=USER_ID,
        hindsight_api_url=HINDSIGHT_URL,
    )],
    instructions=[
        "You are a travel planning assistant with long-term memory.",
        "Remember user preferences (diet, seating, budget, interests) for future trips.",
        "When planning trips, check memory first for relevant preferences.",
        memories,
    ],
    markdown=True,
)

# First run: share preferences
agent.print_response(
    "I'm vegetarian, I prefer window seats, and my budget is mid-range. "
    "I love museums and street food."
)

# Second run: the agent uses stored preferences
agent.print_response("Plan a 3-day trip to Tokyo for me")
```

### Dynamic Per-User Banks

When building a multi-user application, use `user_id` on the Agent to automatically isolate memory per user:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from hindsight_agno import HindsightTools

def create_agent(user_id: str) -> Agent:
    """Create an agent with per-user memory."""
    return Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        tools=[HindsightTools(
            hindsight_api_url="http://localhost:8888",
            # No bank_id — HindsightTools reads it from RunContext.user_id
        )],
        user_id=user_id,
        markdown=True,
    )

# Each user gets isolated memory
alice_agent = create_agent("alice")
bob_agent = create_agent("bob")

alice_agent.print_response("I'm allergic to peanuts")
bob_agent.print_response("What am I allergic to?")
# Bob gets "No relevant memories found" — Alice's data is isolated
```

### Custom Bank Resolution

For more control over bank naming, use a `bank_resolver`:

```python
from agno.run.base import RunContext
from hindsight_agno import HindsightTools

def resolve_bank(ctx: RunContext) -> str:
    """Route to team-specific banks."""
    return f"team-{ctx.user_id}"

tools = [HindsightTools(
    bank_resolver=resolve_bank,
    hindsight_api_url="http://localhost:8888",
)]
```

### Reflect — Disposition-Aware Reasoning

The `reflect_on_memory` tool goes beyond simple retrieval. It synthesizes a reasoned answer using the bank's disposition traits (skepticism, literalism, empathy):

```python
agent.print_response(
    "Based on everything you know about me, what kind of vacation "
    "would I enjoy most and why?"
)
# The agent calls reflect_on_memory, which synthesizes an answer
# from all stored facts using the bank's configured personality
```

## How It Works

### 1. Create the Toolkit

`HindsightTools` extends Agno's `Toolkit` base class — the same pattern used by `Mem0Tools`:

```python
from hindsight_agno import HindsightTools

toolkit = HindsightTools(
    bank_id="my-bank",
    hindsight_api_url="http://localhost:8888",
    budget="mid",          # Recall/reflect thoroughness: low/mid/high
    tags=["source:chat"],  # Tags applied to stored memories
)
# Registers: retain_memory, recall_memory, reflect_on_memory
```

### 2. Pre-Recall with memory_instructions()

For injecting context into the system prompt at agent construction time:

```python
from hindsight_agno import memory_instructions

context = memory_instructions(
    bank_id="my-bank",
    hindsight_api_url="http://localhost:8888",
    query="user preferences and context",
    budget="low",       # Keep it fast
    max_results=5,      # Limit injected memories
)
# Returns a string like:
# "Relevant memories:\n\n1. User is vegetarian\n2. Prefers window seats"
```

### 3. Select Specific Tools

Include only the tools you need:

```python
toolkit = HindsightTools(
    bank_id="my-bank",
    hindsight_api_url="http://localhost:8888",
    enable_retain=True,
    enable_recall=True,
    enable_reflect=False,  # Omit reflect
)
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HINDSIGHT_API_KEY` | API key for Hindsight Cloud or authenticated self-hosted |
| `OPENAI_API_KEY` | OpenAI API key for Agno's LLM |

### Global Configuration

Instead of passing connection details to every toolkit:

```python
from hindsight_agno import configure, HindsightTools

configure(
    hindsight_api_url="http://localhost:8888",
    api_key="your-api-key",
    budget="mid",
    tags=["env:prod"],
)

# Now create toolkits without repeating connection details
toolkit = HindsightTools(bank_id="my-bank")
```

### HindsightTools Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bank_id` | `None` | Static memory bank ID |
| `bank_resolver` | `None` | `(RunContext) -> str` for dynamic bank IDs |
| `client` | `None` | Pre-configured Hindsight client |
| `hindsight_api_url` | `None` | Hindsight API URL |
| `api_key` | `None` | API key |
| `budget` | `"mid"` | Recall/reflect budget (low/mid/high) |
| `max_tokens` | `4096` | Max tokens for recall results |
| `tags` | `None` | Tags for stored memories |
| `recall_tags` | `None` | Tags to filter recall |
| `recall_tags_match` | `"any"` | Tag match mode (any/all/any_strict/all_strict) |
| `enable_retain` | `True` | Include retain tool |
| `enable_recall` | `True` | Include recall tool |
| `enable_reflect` | `True` | Include reflect tool |

## Common Issues

**"Connection refused"**
- Make sure Hindsight is running on `localhost:8888`

**"OPENAI_API_KEY not set"**
```bash
export OPENAI_API_KEY=your-key
```

**"No Hindsight API URL configured"**
- Pass `hindsight_api_url=` to `HindsightTools`, or call `configure()` first

**"No bank_id available"**
- Provide `bank_id=`, `bank_resolver=`, or set `user_id=` on the Agent

---

**Built with:**
- [Agno](https://github.com/agno-agi/agno) - Full-stack agent framework
- [hindsight-agno](https://github.com/vectorize-io/hindsight/tree/main/hindsight-integrations/agno) - Hindsight memory toolkit for Agno
- [Hindsight](https://github.com/vectorize-io/hindsight) - Long-term memory for AI agents
