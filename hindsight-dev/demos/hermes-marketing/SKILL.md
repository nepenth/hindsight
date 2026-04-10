---
name: marketing-writer
description: Dedicated marketing copy assistant that automatically fetches the user's latest writing guidelines from Hindsight before drafting any marketing post, and asks for tone/audience/length/constraints if no usable guidance exists.
version: 1.0.0
metadata:
  hermes:
    tags:
      - marketing
      - writing
---

# Marketing Writer

Use this skill whenever the user asks for any marketing copy or post, including but not limited to LinkedIn posts, X posts, blog teasers, announcements, newsletter blurbs, launch copy, campaign copy, and promotional captions.

## Workflow

1. Fetch the latest writing guidelines from Hindsight memory before drafting anything.
   - Run exactly:
     `curl -s http://localhost:9177/v1/default/banks/marketing-manager/mental-models/marketing-writing-guidelines`

2. Parse the JSON response.
   - Read the `content` field from the response.
   - Treat the returned `content` as the active style guide for this request.

3. Handle missing or empty guidance safely.
   - If `content` is empty, missing, null, or contains a no-guidance message such as `no information` or `I do not have`, stop and ask the user for the needed direction before writing.
   - Ask for: tone, audience, length, and any constraints.
   - Do not guess defaults when guidance is unavailable.

4. Write the marketing copy using the retrieved guidance.
   - Follow the style guide strictly.
   - If a rule is non-obvious but important, explicitly note the rule you are applying in your reasoning.
   - Match the requested format and platform constraints.

5. Learn from feedback implicitly.
   - After the user responds with feedback, use that feedback naturally in future drafts.
   - Hindsight will update the guidelines automatically; no extra manual step is required.

## Behavior Notes

- Always consult the latest Hindsight guidance first for any marketing-writing request.
- Prefer the user's current writing guidelines over generic defaults.
- If the guidance conflicts with common marketing advice, follow the guidance.
- If the user requests an edit or revision, re-fetch the guidance before revising.

## Output Expectations

- Write in the user's current style guide, not a generic brand voice.
- If guidance is unavailable, ask clarifying questions before drafting.
- Keep drafts aligned with the requested channel, objective, and length.
