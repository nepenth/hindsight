---
title: "Create bank (idempotent, safe to run repeatedly)"
authors: [hindsight]
date: 2026-03-10
tags: [memory, mcp, crewai, openai, anthropic, python, tutorial, litellm, llm, vector]
image: /img/blog/run-hindsight-with-ollama.png
hide_table_of_contents: true
---

hindsight.create_bank(
    bank_id="local-agent",
    name="Local Agent Memory",
    mission="Remember user preferences and important facts.",
)

<!-- truncate -->

# Store some memories
print("Retaining memories...")
hindsight.retain(
    bank_id="local-agent",
    content="User: I'm Alice, a backend engineer at Acme Corp. I work mostly in Python and Go.",
)
hindsight.retain(
    bank_id="local-agent",
    content="User: I prefer dark mode, vim keybindings, and tabs over spaces.",
)

# Wait for background fact extraction
print("Waiting for fact extraction (local models are slower)...")
time.sleep(30)

# Recall
print("\nRecalling: 'What does Alice do for work?'")
memories = hindsight.recall(
    bank_id="local-agent",
    query="What does Alice do for work?",
    budget="low",
)

for r in memories.results:
    print(f"  → {r.text}")

print("\nDone. All processing happened locally.")
```

Run:

```bash
python local_memory.py
```

---

## Hindsight with Ollama: Pitfalls and Edge Cases

**1. First request is slow.** Ollama loads the model into memory on the first inference call. This can take 10-30 seconds. Subsequent calls are faster.

**2. Concurrent requests will queue.** Set `HINDSIGHT_API_LLM_MAX_CONCURRENT=1`. Local models can't parallelize like cloud APIs. Multiple concurrent retain calls will queue and process sequentially.

**3. Gemma doesn't support tool calling.** Reflect won't work with the default `gemma3:12b`. Use `qwen3:8b` or another tool-calling model if you need reflect.

**4. RAM matters.** A 12b parameter model needs ~8GB of RAM just for the weights. Add Hindsight's embedded Postgres and local embeddings, and you want 16GB+ total. Use a smaller model on constrained hardware.

**5. Model quality varies.** Local models produce less precise fact extraction than GPT-4o or Claude. You may see more missed facts or less accurate entity resolution. For production workloads, cloud APIs still win on quality.

**6. Fresh Linux installs may need `zstd`.** The Ollama installer requires it for extraction. If you hit an error, run `sudo apt-get install zstd` (Debian/Ubuntu) or `sudo dnf install zstd` (RHEL/Fedora) first.

---

## Local Ollama vs. Cloud LLMs for Agent Memory

| | Ollama (Local) | OpenAI / Anthropic (Cloud) |
|---|---|---|
| **Cost** | Free after hardware | Per-token pricing |
| **Privacy** | Full, nothing leaves your machine | Data transits third-party API |
| **Speed** | 15-60s per retain (CPU) | 1-3s per retain |
| **Quality** | Good for 12b+ models | Best available |
| **Tool calling** | Model-dependent | Fully supported |
| **Reflect** | Requires specific models | Works with all providers |
| **Setup** | Ollama install + model pull | API key |
| **Concurrency** | Limited by hardware | Cloud-scaled |

**Use local when:** developing, prototyping, running in air-gapped environments, handling sensitive data, or avoiding per-token costs.

**Use cloud when:** you need speed, maximum quality, tool calling reliability, or production-scale concurrency.

You can also mix both approaches: develop locally with Hindsight and Ollama, then deploy to production with OpenAI or Anthropic. Same Hindsight API, same code, just change the env vars. Many teams use this pattern to keep development costs at zero while getting the best quality in production.

---

## Override Hindsight Ollama Defaults

Hindsight picks sensible defaults when running with Ollama, but you can override everything:

```bash
export HINDSIGHT_API_LLM_PROVIDER=ollama
export HINDSIGHT_API_LLM_MODEL=qwen3:8b          # default: gemma3:12b
export HINDSIGHT_API_LLM_BASE_URL=http://192.168.1.50:11434/v1  # remote Ollama
export HINDSIGHT_API_LLM_MAX_CONCURRENT=2         # if your GPU can handle it
```

This also means you can run Ollama on a different machine (a GPU server, for example) and point Hindsight at it over the network. This is a common pattern for teams that want local privacy but better performance: run Ollama on a dedicated GPU box in your network, and run Hindsight on your application server.

---

## Recap: Running Hindsight with Ollama

Running Hindsight with Ollama takes two environment variables and about ten minutes of setup. Once connected, you get the same memory engine, the same knowledge graph, and the same retain/recall/reflect API that the cloud version provides, all running on your own hardware.

The key points to remember:

- `HINDSIGHT_API_LLM_PROVIDER=ollama` is the only switch you need
- `retain` and `recall` work reliably with local models like Gemma 3
- `reflect` needs tool-calling support, so use Qwen 3 or check [Ollama's model library](https://ollama.com/library) for compatible models
- Local inference is slower than cloud APIs, but you get full privacy and zero per-token costs
- The same code works with local or cloud providers, so you can swap by changing env vars

For teams that need data privacy, air-gapped deployments, or zero-cost development environments, Hindsight with Ollama is the fastest way to get persistent agent memory running locally.

---

## Next Steps

- **Try a bigger model** -- `gemma3:27b` or `qwen3:32b` for better fact extraction quality
- **Run Ollama on a GPU server** -- point `LLM_BASE_URL` at a remote machine for faster inference
- **Add the OpenAI chatbot loop** -- combine this with the [OpenAI memory tutorial](/blog/2026/03/05/add-memory-to-openai-application) for a fully local chatbot
- **Try MCP integration** -- connect Hindsight to [Claude, Cursor, or VS Code via MCP](/blog/2026/03/04/mcp-agent-memory)
- **Scale with LiteLLM** -- use [100+ model providers](/blog/2026/03/03/litellm) through a single interface
- **Inspect memories in the web UI** -- run the control plane at `localhost:9999` to browse extracted facts
- **Go to production with cloud** -- switch to `HINDSIGHT_API_LLM_PROVIDER=openai` when ready

Local memory is real memory. It just runs on your hardware.
