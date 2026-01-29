---
sidebar_position: 4
---

# Embedded SDK (hindsight-embed)

Zero-configuration local memory system with automatic daemon management. Perfect for development, prototyping, and single-user applications.

## Overview

`hindsight-embed` wraps the Hindsight API in a local daemon that:
- **Starts automatically** on first command
- **No setup required** — uses embedded PostgreSQL (pg0)
- **Auto-exits when idle** — configurable timeout
- **Localhost only** — binds to `127.0.0.1:8889`

Think of it as SQLite for long-term memory — perfect for getting started or building local-first applications.

## Installation

Install via `uvx` (recommended - always latest version):

```bash
# Run directly without installation
uvx hindsight-embed@latest configure

# Or use pipx for persistent installation
pipx install hindsight-embed
```

## Quick Start

### 1. Configure

```bash
# Interactive configuration
hindsight-embed configure

# Or non-interactive via environment variables
export HINDSIGHT_EMBED_LLM_PROVIDER=openai
export HINDSIGHT_EMBED_LLM_API_KEY=sk-xxxxxxxxxxxx
export HINDSIGHT_EMBED_LLM_MODEL=gpt-4o-mini
hindsight-embed configure
```

Configuration is saved to `~/.hindsight/embed`:

```bash
HINDSIGHT_EMBED_LLM_PROVIDER=openai
HINDSIGHT_EMBED_LLM_MODEL=gpt-4o-mini
HINDSIGHT_EMBED_BANK_ID=default
HINDSIGHT_EMBED_LLM_API_KEY=sk-xxxxxxxxxxxx

# Daemon settings (macOS: force CPU to avoid MPS/XPC issues)
HINDSIGHT_API_EMBEDDINGS_LOCAL_FORCE_CPU=1
HINDSIGHT_API_RERANKER_LOCAL_FORCE_CPU=1
```

### 2. Use Memory Operations

```bash
# Store a memory
hindsight-embed memory retain default "User prefers dark mode"

# Query memories
hindsight-embed memory recall default "user preferences"

# Reasoning with memory
hindsight-embed memory reflect default "What color scheme should I use?"
```

The daemon starts automatically on first use!

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HINDSIGHT_EMBED_LLM_API_KEY` | **Required**. API key for LLM provider | - |
| `HINDSIGHT_EMBED_LLM_PROVIDER` | LLM provider: `openai`, `anthropic`, `gemini`, `groq`, `ollama` | `openai` |
| `HINDSIGHT_EMBED_LLM_MODEL` | Model name | `gpt-4o-mini` |
| `HINDSIGHT_EMBED_BANK_ID` | Default memory bank ID | `default` |
| `HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT` | Seconds before daemon auto-exits when idle (0 = never) | `300` |

**Provider Examples:**

```bash
# OpenAI
export HINDSIGHT_EMBED_LLM_PROVIDER=openai
export HINDSIGHT_EMBED_LLM_API_KEY=sk-xxxxxxxxxxxx
export HINDSIGHT_EMBED_LLM_MODEL=gpt-4o

# Groq (fast inference)
export HINDSIGHT_EMBED_LLM_PROVIDER=groq
export HINDSIGHT_EMBED_LLM_API_KEY=gsk_xxxxxxxxxxxx
export HINDSIGHT_EMBED_LLM_MODEL=llama-3.3-70b-versatile

# Anthropic
export HINDSIGHT_EMBED_LLM_PROVIDER=anthropic
export HINDSIGHT_EMBED_LLM_API_KEY=sk-ant-xxxxxxxxxxxx
export HINDSIGHT_EMBED_LLM_MODEL=claude-sonnet-4-20250514
```

## Daemon Management

### Idle Timeout

Customize how long the daemon stays alive when idle:

```bash
# Never timeout (daemon runs until manually stopped)
export HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT=0

# Shorter timeout: 1 minute
export HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT=60

# Longer timeout: 30 minutes
export HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT=1800
```

### Daemon Commands

```bash
# Check daemon status
hindsight-embed daemon status

# View daemon logs in real-time
hindsight-embed daemon logs -f

# Stop daemon manually
hindsight-embed daemon stop
```

## Commands

All memory operations follow the same interface as the CLI:

### Retain (Store Memory)

```bash
hindsight-embed memory retain <bank_id> "content"

# With context
hindsight-embed memory retain <bank_id> "content" --context "source information"

# Background processing
hindsight-embed memory retain <bank_id> "content" --async
```

### Recall (Search)

```bash
hindsight-embed memory recall <bank_id> "query"

# With budget control
hindsight-embed memory recall <bank_id> "query" --budget high

# Show trace
hindsight-embed memory recall <bank_id> "query" --trace
```

### Reflect (Generate Response)

```bash
hindsight-embed memory reflect <bank_id> "prompt"

# With additional context
hindsight-embed memory reflect <bank_id> "prompt" --context "additional info"
```

### Bank Management

```bash
# List all banks
hindsight-embed bank list

# View bank stats
hindsight-embed bank stats <bank_id>

# Set bank name
hindsight-embed bank name <bank_id> "My Assistant"

# Set bank mission
hindsight-embed bank mission <bank_id> "I am a helpful AI assistant"
```

## Platform-Specific Behavior

### macOS

Automatically forces CPU-only inference for embeddings and reranking to avoid MPS (Metal Performance Shaders) stability issues in background daemon processes. This is transparent and configured automatically during `hindsight-embed configure`.

### Linux

Can use GPU acceleration (CUDA) if available. The CPU-only restrictions are macOS-specific.

## Use Cases

### Development & Prototyping

Perfect for trying out Hindsight without infrastructure:

```bash
# Quick experiment
uvx hindsight-embed@latest configure
uvx hindsight-embed@latest memory retain demo "Test memory"
uvx hindsight-embed@latest memory recall demo "test"
```

### Local-First Applications

Build applications that store memory locally:

```python
import subprocess

# Store memory from your app
subprocess.run([
    "hindsight-embed", "memory", "retain", "myapp",
    "User completed tutorial"
])

# Query memories
result = subprocess.run([
    "hindsight-embed", "memory", "recall", "myapp",
    "what has the user done?",
    "-o", "json"
], capture_output=True, text=True)
```

### Personal AI Assistant

Use as a memory layer for your personal assistant:

```bash
# Configure once with your preferred LLM
hindsight-embed configure

# Your assistant can now remember context
hindsight-embed memory retain assistant "User's favorite color is blue"
hindsight-embed memory reflect assistant "What should I paint my room?"
```

## Comparison with Regular CLI

| Feature | hindsight-embed | hindsight (CLI) |
|---------|----------------|-----------------|
| **Setup** | Zero-config | Requires API server |
| **Database** | Embedded (pg0) | External PostgreSQL |
| **Daemon** | Auto-managed | Manual setup |
| **Deployment** | Local only | Any network |
| **Use Case** | Development, single-user | Production, multi-user |
| **Installation** | `uvx hindsight-embed` | `curl -fsSL ...` |

## Troubleshooting

### Daemon Won't Start

Check the daemon logs:

```bash
hindsight-embed daemon logs
# Or watch in real-time
hindsight-embed daemon logs -f
```

Common issues:
- **Missing API key**: Set `HINDSIGHT_EMBED_LLM_API_KEY`
- **Port conflict**: Another service using port 8889
- **Permissions**: Check `~/.hindsight/` directory permissions

### Daemon Exits Immediately

Check if you have the idle timeout set too low:

```bash
# Disable idle timeout for debugging
export HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT=0
hindsight-embed daemon status
```

### Reset Configuration

```bash
# Remove config file and reconfigure
rm ~/.hindsight/embed
hindsight-embed configure
```

## Advanced Configuration

While `hindsight-embed` aims to be zero-config, you can customize the underlying API behavior by setting `HINDSIGHT_API_*` variables in `~/.hindsight/embed`:

```bash
# Example: Custom embedding model
HINDSIGHT_API_EMBEDDINGS_PROVIDER=openai
HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL=text-embedding-3-large

# Example: Verbose extraction
HINDSIGHT_API_RETAIN_EXTRACTION_MODE=verbose
```

See [Configuration](/developer/configuration) for all available `HINDSIGHT_API_*` options.

## Limitations

- **Single user**: No authentication/multi-tenancy
- **Local only**: Not accessible from network
- **Development database**: pg0 is not production-grade
- **Auto-exit**: Daemon stops after idle timeout (configurable)

For production deployments with multiple users, use the [API Service](/developer/services) directly with external PostgreSQL.
