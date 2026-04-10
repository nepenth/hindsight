---
name: hindsight-skill-builder
description: Create, install, configure, or update a Hindsight-backed self-improving skill. Use whenever the user asks to build a new skill, add a skill to their agent, set up a marketing/support/research/coding assistant skill, bind a skill to a memory bank, create a skill that learns from feedback, or otherwise turn a task into a Hindsight-powered workflow that evolves over time. Handles the full setup: locating the Hindsight instance, selecting or creating a bank with tuned missions, creating the binding mental model, and writing the new SKILL.md file into the harness skills directory.
---

# Hindsight Skill Builder

You are helping the user create a **self-improving skill**: a thin SKILL.md file that fetches its live instructions from a Hindsight mental model via `curl` and adapts over time as the user gives feedback during normal conversations.

Your job is to walk the user through a four-step setup, **pausing for explicit approval at every decision**. You are NOT a silent script. At every step you propose, the user approves or edits, and only then do you execute.

The resulting skill, once installed, will:

1. Be loaded by the harness whenever a matching request comes in
2. `curl` a Hindsight mental model to fetch live guidance
3. Fall back to asking the user when the mental model is empty
4. Follow the returned guidance strictly when writing output
5. Learn automatically as the user gives feedback — because Hindsight's auto-retain, consolidation, and `refresh_after_consolidation` pipeline keeps the mental model up to date without any extra work from you

---

## Human-in-the-loop protocol (MANDATORY)

At every step below, you follow this pattern:

1. **Explore** — run whatever checks you need (list banks, probe URLs, read existing config, etc)
2. **Propose** — show the user your proposed value for this step in a clearly labeled block
3. **Ask for approval** — end with a direct question like *"Proceed with this, or do you want to edit?"*
4. **Wait for explicit confirmation** before making any API call, writing any file, or moving to the next step

Never chain steps. Never auto-advance. If the user gives partial feedback ("make the description shorter"), regenerate that single field and ask again.

Decisions that require approval:
- The Hindsight instance URL you will talk to
- The bank name (whether existing or new)
- The three bank missions (retain, observations, reflect) — only when creating a new bank
- The mental model id, name, and source_query
- The final skill name and description
- The target directory where the new SKILL.md will be written

---

## Step 1 — Locate the Hindsight instance

Find the running Hindsight API. Try these in order and stop at the first one that responds to `GET /health`:

1. `HINDSIGHT_API_URL` environment variable
2. `~/.hindsight/config` — toml file with an `api_url` key
3. `~/.hermes/hindsight/config.json` — `api_url` field, or derive from `bank_id` + default local port
4. `~/.claude/hindsight.json` or `~/.hindsight/claude-code.json`
5. `~/.hindsight/codex.json`
6. Well-known local ports: `9177`, `9077`, `8888`
7. Hindsight Cloud default: `https://api.hindsight.vectorize.io` (needs `HINDSIGHT_API_KEY`)

Verify with:

```bash
curl -sf <url>/health
```

A healthy response looks like `{"status":"healthy","database":"connected"}`.

**Propose to the user** which URL you found and got a healthy response from. Example:

> I found a running Hindsight instance at `http://localhost:9177` (healthy).
> Is this the instance you want to use?

If the user declines or none of the candidates respond, ask for the URL directly. If you had to use `HINDSIGHT_API_KEY` for cloud, confirm the key is available (do not print it).

---

## Step 2 — Select or create a bank

List existing banks:

```bash
curl -s <url>/v1/default/banks
```

Inspect their names and missions. For each, optionally fetch the config:

```bash
curl -s <url>/v1/default/banks/<bank_id>/config
```

Now **decide with the user** whether the new skill should:

- **(a) Bind to an existing bank** — because the kind of feedback it will receive overlaps with what the bank already learns. Example: a `linkedin-post-writer` skill belongs in a bank that already handles marketing writing, because all the same tone/voice/audience feedback applies.
- **(b) Create a new bank** — because the skill's domain is distinct. Example: a `customer-support-responder` skill should NOT go in a marketing bank; the feedback it will receive ("be more apologetic", "mention refund policy") is unrelated to marketing style.

Your rule of thumb: **if the user's feedback for the new skill would pollute the existing bank's observations, create a new bank.** When in doubt, ask the user.

### (a) Binding to an existing bank

If binding, confirm the target bank with the user:

> I'll bind the new skill to the existing `marketing` bank. Its retain mission
> already captures writing rules, so feedback on your new skill will flow into
> the same style guide. OK?

Skip to Step 3.

### (b) Creating a new bank with tuned missions

If creating a new bank, you must **design three missions** (and get the user's approval on each):

- **`retain_mission`** — what single, actionable facts to extract from every conversation turn. Must be specific about categories. Must include negative constraints ("ignore X").
- **`observations_mission`** — how to synthesize extracted facts into deduplicated, coherent observations. Must handle conflicts (newer rule wins on contradiction).
- **`reflect_mission`** — how to format the response when the skill queries the mental model. The shape the user will see.

Propose all three in one block with the bank name, like this:

> Here's the proposed bank configuration:
>
> **Bank id:** `customer-support`
>
> **Retain mission:**
> Extract concrete rules the human gives about how to respond to customer
> support messages. Capture: tone (apologetic/neutral/firm), required disclosures,
> escalation criteria, banned phrases, refund/credit policy, response length,
> signature format, and any explicit corrections to previous replies. Each fact
> must be a single, actionable rule. IGNORE the ticket content itself; only
> extract durable response-writing guidance.
>
> **Observations mission:**
> Synthesise extracted rules into a coherent, deduplicated support response
> playbook. Group rules by situation (angry customer, refund request, bug
> report, feature request). When a new rule contradicts an older one, the
> newer rule wins; mark the older as stale. Output observations as actionable
> rules a responder can follow without ambiguity.
>
> **Reflect mission:**
> When asked for the current support response guidelines, return a clear,
> structured playbook organized by situation with clear do's and don'ts that
> a support agent can follow when drafting a reply.
>
> Create this bank?

Wait for approval. If the user asks for edits, regenerate and ask again.

Create the bank with:

```bash
curl -X PUT <url>/v1/default/banks/<bank_id> \
  -H "Content-Type: application/json" \
  -d '{
    "name": "<bank_id>",
    "retain_mission": "...",
    "observations_mission": "...",
    "reflect_mission": "..."
  }'
```

Verify by re-fetching `/config` and confirm all three overrides are set.

---

## Step 3 — Create the binding mental model

The mental model is what the new skill will `curl` at runtime. It has:

- **`id`** — matches the skill name so the `curl` URL is predictable (e.g., `linkedin-post-writer`)
- **`name`** — human-readable (e.g., "LinkedIn Post Writer Guidelines")
- **`source_query`** — the reflect question whose answer becomes the live instructions

The `source_query` is the most important field. It is the **question the mental model answers whenever the skill fetches it**. A good `source_query`:

- Mirrors the skill's purpose: *"What are the current X rules I should follow when Y?"*
- Is specific enough that reflect pulls the right slice of observations
- Is stable — it does not need to be rewritten as the skill learns
- Asks for guidance the user *would* give you, not facts about the user

Propose the mental model spec:

> Here's the proposed mental model:
>
> **id:** `linkedin-post-writer`
> **name:** LinkedIn Post Writer Guidelines
> **source_query:** *"What are the current writing style, tone, structure, voice, and do/dont rules I should follow when drafting LinkedIn posts on behalf of this user?"*
> **refresh_after_consolidation:** true
> **tags:** (none — this is important, see note)
>
> Create this mental model in bank `<bank>`?

**Note on tags:** do NOT set tags on the mental model unless you are also going to tag the memories the auto-retain hook stores. The `refresh_after_consolidation` trigger is tag-gated — if the mental model has tags but the retained memories don't, the trigger silently does nothing and the mental model never refreshes. When in doubt, leave tags empty.

Wait for approval, then create:

```bash
curl -X POST <url>/v1/default/banks/<bank>/mental-models \
  -H "Content-Type: application/json" \
  -d '{
    "id": "<mm_id>",
    "name": "<mm_name>",
    "source_query": "<source_query>",
    "max_tokens": 2048,
    "trigger": {"refresh_after_consolidation": true}
  }'
```

Verify by fetching the mental model. The initial `content` will be a "no information" response — that is correct and expected. The skill's fallback handles it.

---

## Step 4 — Write the SKILL.md file

### Where to write it

Figure out where to put the new SKILL.md. Your preferred strategy:

1. **Use your own location** — if you (this skill-builder skill) were loaded from `~/.hermes/skills/hindsight-skill-builder/SKILL.md`, then the new skill goes into a sibling directory: `~/.hermes/skills/<new-skill-name>/SKILL.md`. Ask the agent-runtime environment or introspect available paths to find this.
2. If you cannot determine your own location, check for known harness skill directories and propose the first one that exists:
   - `~/.hermes/skills/` (Hermes)
   - `~/.claude/skills/` (Claude Code)
   - `~/.codex/skills/` (Codex)
   - `~/.cursor/skills/` (Cursor)
3. If none are found, ask the user where the harness loads skills from.

**Propose the target path to the user before writing** and wait for approval:

> I'll write the new skill to:
> `~/.hermes/skills/linkedin-post-writer/SKILL.md`
>
> OK to proceed?

### The frontmatter description

This field is the **auto-match surface** the harness uses to decide when to load the skill. It must enumerate the intents and phrases the user is likely to use. Pattern:

> Use this skill whenever the user asks for [intent 1], [intent 2], [intent 3], or similar. Handles [domain] by [mechanism].

Length: 80–250 characters. Keyword-rich. Concrete.

Propose the description separately and get approval:

> Proposed description:
> *"Use this skill whenever the user asks for a LinkedIn post, thought-leadership post, company-update post, or executive announcement. Fetches the latest writing style guidelines from Hindsight and follows them strictly, or asks the user for guidance when the guidelines are empty."*
>
> Approve as-is, or edit?

### The SKILL.md template

Render this template, substituting `<placeholders>`. Do not add extra sections beyond what is here unless the user asks.

```markdown
---
name: <skill-name>
description: <description>
---

# <Skill Title>

Use this skill whenever the user asks for <domain work>. Before doing anything, you MUST fetch the latest guidelines from Hindsight.

## Workflow

1. **Fetch live guidance** from the bound mental model:

   ```bash
   curl -s <url>/v1/default/banks/<bank>/mental-models/<mm_id>
   ```

2. **Parse the JSON response** and read the `content` field. That field is your style guide for this request.

3. **Handle empty guidance.** If `content` is empty, missing, null, or contains a no-information message ("I do not have any information", "no relevant memories", etc.), you MUST stop and ask the user for direction before producing any output. Ask for the specific fields the domain needs (tone, audience, length, constraints, whatever is relevant). Do not guess from your defaults.

4. **Follow the guidance strictly.** When the guidance is populated, apply every rule. If a rule is non-obvious but important, briefly note which rule you are applying in your reasoning.

5. **Re-fetch on revision.** If the user asks for an edit or redo, re-run the curl first — the guidelines may have been updated since your last turn.

## Learning loop

Your feedback teaches this skill. You do not need to do anything special with user feedback — Hindsight's auto-retain hook captures every conversation turn, extracts rules via the bank's retain mission, consolidates them into observations, and refreshes this mental model automatically. The next curl will return updated guidelines.
```

Write the file, create parent directories if needed, then `ls` or `cat` to confirm.

---

## Final confirmation

After all four steps are done, show the user a summary:

> ✓ **Skill installed: `<name>`**
>
> - Hindsight: `<url>`
> - Bank: `<bank>` (new / existing)
> - Mental model: `<mm_id>` — empty, will populate after first feedback
> - Skill file: `<path>`
>
> The skill is live. Ask your agent to do `<some domain task>` and start giving feedback — the mental model will evolve automatically after the first consolidation cycle.

---

## Worked example — `marketing-writer`

This is a known-good configuration. Use it as a shape reference when designing a new skill, not as a template to copy blindly.

**Bank:** `marketing`

- **retain_mission:** *"Extract concrete writing rules expressed by the human about how marketing posts should be written. Capture: tone (formal/casual/energetic/dry), structure (length, format, bullets vs paragraphs, use of emojis/hashtags), voice (we/you/I/brand name), forbidden words or cliches, target audience, calls to action, headline patterns, do/dont constraints, and any explicit corrections to previous drafts. Each fact must be a single, actionable writing rule a writer could follow next time. IGNORE the post content itself; only extract durable style guidance."*
- **observations_mission:** *"Synthesise extracted writing rules into a coherent, deduplicated marketing style guide. Group rules by theme (tone, structure, voice, taboo, audience, CTA, formatting). When the human gives a NEW rule that contradicts an older one, the newer rule wins and the older one should be marked stale. Output observations as actionable rules a writer can follow without ambiguity."*
- **reflect_mission:** *"When asked to produce writing guidelines, return a clear, structured style guide a writer could follow when drafting marketing posts."*

**Mental model:**

- **id:** `marketing-writing-guidelines`
- **source_query:** *"What are the current writing style, tone, structure, voice, and do/dont rules I should follow when drafting marketing posts on behalf of this human?"*
- **refresh_after_consolidation:** true, no tags

**Skill description:**

> *"Use this skill whenever the user asks for any marketing copy, LinkedIn post, X post, blog teaser, newsletter blurb, announcement, launch copy, or promotional caption. Fetches the latest writing guidelines from Hindsight before drafting and asks the user for tone/audience/length/constraints when no guidance exists yet."*

In a real run of this skill, that configuration started empty and evolved into a ~5000-character structured style guide after four rounds of user feedback — all without changing the skill file.

---

## Counter-examples — what NOT to write

Bad configs produce skills that sort-of-work but never auto-activate well and extract noisy observations. Avoid these:

**Bad retain_mission:** *"Extract important things the user says."*
Too vague. No categories, no negative constraints. The LLM will extract greetings, transient opinions, and irrelevant trivia. Good retain missions enumerate concrete categories and say what to ignore.

**Bad observations_mission:** *"Combine related facts."*
Tells the consolidator nothing about how to group, deduplicate, or handle contradictions. Good observations missions specify grouping axes and conflict-resolution behavior.

**Bad source_query:** *"What do I need to know?"*
Too broad — reflect will pull everything in the bank. Good source_queries are scoped to the skill's purpose and phrased as the question whose answer *is* the skill's runtime instructions.

**Bad description:** *"Marketing helper."*
Ten characters, zero keywords. The harness will never match user requests to it. Good descriptions enumerate every phrase the user might say ("LinkedIn post, X post, blog teaser, newsletter, announcement, launch copy, promotional caption").

**Bad skill body:** Anything that tries to hardcode rules inline (tone, length, format). The whole point is that the rules live in the mental model and evolve. The skill body should contain ONLY the curl-parse-follow-or-ask workflow, nothing else.

---

## Things to watch for (known gotchas)

- **Tagged mental models skip auto-refresh.** The `refresh_after_consolidation` trigger only fires when the mental model's tags overlap with the consolidated memories' tags (or when both are untagged). If the user asks for tags on the mental model, warn them and confirm they also plan to tag the retained memories, otherwise the skill will never refresh.
- **Auto-retain must be on.** This skill only works if the harness's Hindsight plugin has auto-retain enabled (the default). Verify during Step 1 if you can.
- **The first turn after install will hit an empty mental model.** That is correct. The skill's fallback will ask the user for guidance, and the first batch of feedback will seed the mental model after one consolidation cycle.
- **Hindsight URLs are not always `localhost:8888`.** The actual default for the Hermes embedded daemon is `9177`. Always verify with `/health` before committing to a URL.
