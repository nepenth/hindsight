# Hindsight Memory Skill

You have access to a long-term memory system called Hindsight. Use it to recall context from prior tasks and store important learnings after each task.

## Environment Variables

The following environment variables are available (injected via Paperclip secrets):

- `HINDSIGHT_API_URL` — Hindsight server URL (e.g. `https://api.hindsight.vectorize.io`)
- `HINDSIGHT_API_TOKEN` — API token for authentication
- `HINDSIGHT_BANK_ID` — Your memory bank ID (e.g. `paperclip::company-id::agent-id`)

## Recalling Memories

Before starting a task, recall relevant context from prior sessions:

```bash
curl -s -X POST "$HINDSIGHT_API_URL/v1/default/banks/$HINDSIGHT_BANK_ID/memories/recall" \
  -H "Authorization: Bearer $HINDSIGHT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "'"$TASK_DESCRIPTION"'",
    "budget": "mid",
    "max_tokens": 1024
  }' | jq -r '.results[] | "- \(.text)"'
```

If memories are returned, incorporate them into your approach for the current task.

## Storing Memories

After completing a task, store what you did and any important learnings:

```bash
curl -s -X POST "$HINDSIGHT_API_URL/v1/default/banks/$HINDSIGHT_BANK_ID/memories" \
  -H "Authorization: Bearer $HINDSIGHT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{
      "content": "'"$TASK_SUMMARY"'",
      "document_id": "'"$PAPERCLIP_RUN_ID"'",
      "context": "paperclip",
      "metadata": {
        "taskId": "'"$TASK_ID"'"
      }
    }],
    "async": true
  }'
```

## When to Use Memory

**Recall** at the start of a task when:
- Starting work on a codebase or system you may have worked on before
- Investigating a recurring issue or bug
- Working with a user or company you've interacted with previously
- Beginning a task that may be a continuation of prior work

**Store** at the end of a task when:
- You discovered something non-obvious about the codebase or system
- You made a decision that future tasks should know about
- You encountered an error and found the solution
- You completed a significant piece of work worth remembering

## Tips

- Keep stored summaries factual and specific — future-you needs actionable context, not vague notes
- Include file paths, function names, and key decisions in your stored memories
- If recall returns many results, focus on the most recent and most relevant ones
