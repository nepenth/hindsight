---
name: marketing-post-writer
description: Use this skill whenever the user asks for LinkedIn posts, X posts, blog teasers, newsletters, announcements, or similar marketing copy. Fetches live guidance from Hindsight and evolves with feedback.
---

# Marketing Post Writer

Use this skill whenever the user asks for marketing copy across LinkedIn, X, blog teasers, newsletters, announcements, launch copy, or similar promotional writing.
Before drafting anything, you MUST fetch the latest guidance from Hindsight.

## Workflow

1. Fetch live guidance from the bound mental model:

   ```bash
   curl -s http://localhost:9177/v1/default/banks/marketing-writing/mental-models/marketing-post-writer
   ```

2. Read the `content` field in the JSON response. That is your current style guide.

3. If `content` is empty, missing, null, or contains a no-information message such as "I do not have any information" or "no relevant memories", stop and ask the user for the missing direction before writing. Ask for the specific marketing details you need, such as audience, tone, length, channel, CTA, and constraints.

4. If the guidance is populated, follow it strictly when drafting. Apply the rules explicitly and do not fall back to generic defaults unless the guidance allows it.

5. If the user asks for a revision or rewrite, fetch the mental model again first. The guidance may have updated since the previous draft.

## Learning loop

This skill improves automatically as the user gives feedback. Hindsight captures the conversation, extracts durable writing rules into the `marketing-writing` bank, consolidates them, and refreshes the mental model after consolidation. You do not need to manually update this file for normal feedback-driven evolution.
