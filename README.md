# Hindsight

**Long-term memory for AI agents.**

AI assistants forget everything between sessions. Hindsight fixes that with a memory system that handles temporal reasoning, entity connections, and personality-aware responses.

## Why Hindsight?

- **Temporal queries** — "What did Alice do last spring?" requires more than vector search
- **Entity connections** — Knowing "Alice works at Google" + "Google is in Mountain View" = "Alice works in Mountain View"
- **Agent opinions** — Agents form and recall beliefs with confidence scores
- **Personality** — Big Five traits influence how agents process and respond to information

## 5-Minute Setup

### 1. Start the server

```bash
# Clone and start with Docker
git clone https://github.com/vectorize-io/hindsight.git
cd hindsight/docker
./start.sh
```

Server runs at `http://localhost:8888`

### 2. Install the Python client

```bash
pip install hindsight-client
```

### 3. Use it

```python
from hindsight_client import Hindsight

client = Hindsight(base_url="http://localhost:8888")

# Store memories
client.store(agent_id="my-agent", content="Alice works at Google")
client.store(agent_id="my-agent", content="Bob prefers Python over JavaScript")

# Search memories
results = client.search(agent_id="my-agent", query="What does Alice do?")
for r in results:
    print(f"{r['text']} ({r['weight']:.2f})")

# Generate personality-aware responses
answer = client.think(agent_id="my-agent", query="Tell me about Alice")
print(answer["text"])
```

## Documentation

Full documentation: [hindsight-docs](./hindsight-docs)

- [Architecture](./hindsight-docs/docs/developer/architecture.md) — How ingestion, storage, and retrieval work
- [Python Client](./hindsight-docs/docs/sdks/python.md) — Full API reference
- [API Reference](./hindsight-docs/docs/api-reference/index.md) — REST API endpoints
- [Personality](./hindsight-docs/docs/developer/personality.md) — Big Five traits and opinion formation

## License

MIT
