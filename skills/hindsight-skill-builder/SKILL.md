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

Hindsight can be deployed in three ways. The meta-skill and the skill it creates must work with all of them:

| Mode | URL pattern | Auth | Typical config location |
|---|---|---|---|
| **Embedded** (local daemon) | `http://localhost:<port>` | none | `hindsight-embed -p <profile> daemon status`, ports `9177` / `9077` / `8888` |
| **Self-hosted** | user-configured HTTP(S) URL | optional API key | `HINDSIGHT_API_URL` env var, `~/.hindsight/config` |
| **Cloud** | `https://api.hindsight.vectorize.io` | required API key (`hsk_...`) | `HINDSIGHT_API_KEY` env var, `~/.hindsight/config`, `~/.hermes/hindsight/config.json` |

### Probe candidates

Try these sources in order and collect every candidate `(url, api_key)` pair. Do NOT stop at the first one — probe all of them, then propose the best match to the user.

1. **Environment variables** — `HINDSIGHT_API_URL` (url), `HINDSIGHT_API_KEY` (key). If both are set, that's the preferred candidate.
2. **`~/.hindsight/config`** — TOML file with `api_url = "..."` and optionally `api_key = "..."`.
3. **`~/.hermes/hindsight/config.json`** — JSON with `api_url`, `api_key`, and `mode` fields. If `mode` is `local_embedded`, derive the URL from the hermes profile (default port is `9177` for the `hermes` profile).
4. **`~/.claude/hindsight.json`, `~/.hindsight/claude-code.json`, `~/.hindsight/codex.json`** — any JSON with `api_url` / `api_key` / `hindsightApiUrl`.
5. **Well-known local ports** — `http://localhost:9177`, `http://localhost:9077`, `http://localhost:8888` (no auth; embedded mode).
6. **Cloud default** — `https://api.hindsight.vectorize.io` (only include this candidate if `HINDSIGHT_API_KEY` is set somewhere; otherwise the user has no way to authenticate).

### Verify with an authenticated health check

For each candidate, run:

```bash
# Without auth (embedded / self-hosted without key)
curl -sf <url>/health

# With auth (cloud / self-hosted with key)
curl -sf -H "Authorization: Bearer <api_key>" <url>/health
```

A healthy response looks like `{"status":"healthy","database":"connected"}`. Treat a `401` or `403` as "auth wrong or missing" — do NOT treat it as unhealthy. Retry the same URL without auth; if that also fails, the instance requires a key you don't have.

### Classify the mode

From the URL and auth result, classify the instance:

- Hostname matches `api.hindsight.vectorize.io` → **cloud**
- Hostname is `localhost` / `127.0.0.1` / private IP → **embedded** (if no key) or **self-hosted** (if key)
- Any other hostname → **self-hosted**

### Propose to the user

Show the user every candidate you probed and recommend one. Example:

> I probed for a Hindsight instance and found these options:
>
> 1. **Embedded** — `http://localhost:9177` (healthy, no auth) ← from `~/.hermes/hindsight/config.json`
> 2. **Cloud** — `https://api.hindsight.vectorize.io` (healthy, auth via `HINDSIGHT_API_KEY`) ← key found in `~/.hermes/.env`
>
> I'd recommend the **embedded** instance for local development. Use the embedded one, or switch to cloud?

If the user picks cloud or self-hosted, **remember that auth is required**. Every subsequent API call in Steps 2–4 must include the `Authorization: Bearer <api_key>` header, and the generated SKILL.md must include it too (Step 4 covers this).

**Never print the API key value** in your responses. Reference it as `$HINDSIGHT_API_KEY` or "the configured key" instead.

If no candidates respond or the user declines all of them, ask directly:

> I couldn't find a running Hindsight instance. Please tell me:
> - The API URL (e.g., `https://hindsight.mycompany.com` or `http://localhost:9177`)
> - Whether it requires an API key, and if so where it's stored (env var name or config file path)

Once you have a confirmed `(url, mode, auth)` triple, store it for the rest of the flow. Do not re-probe in later steps.

---

## Step 2 — Select or create a bank

All API calls in this step must include the `Authorization` header if Step 1 classified the instance as `cloud` or `self-hosted` with auth. Use this helper form throughout:

```bash
# Define once at the top of the step
AUTH=""   # for embedded mode, leave empty
# AUTH="-H 'Authorization: Bearer $HINDSIGHT_API_KEY'"   # for cloud / self-hosted with key
```

List existing banks:

```bash
curl -s $AUTH <url>/v1/default/banks
```

Inspect their names and missions. For each, optionally fetch the config:

```bash
curl -s $AUTH <url>/v1/default/banks/<bank_id>/config
```

> **Note on the tenant path segment.** The `default` in `/v1/default/banks` is the tenant ID. On embedded and standard self-hosted deployments it's always `default`. On cloud, the API key typically scopes the tenant automatically and `/v1/default/` still works — but if the user's cloud account uses a custom tenant, ask them to confirm the tenant id before proceeding and substitute it throughout.

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

Create the bank with (add `-H "Authorization: Bearer $HINDSIGHT_API_KEY"` if the instance requires auth):

```bash
curl -X PUT $AUTH <url>/v1/default/banks/<bank_id> \
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

Wait for approval, then create (add auth header if required):

```bash
curl -X POST $AUTH <url>/v1/default/banks/<bank>/mental-models \
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

Render **one of two templates** depending on whether the instance requires auth (decided in Step 1). Do not add extra sections beyond what is here unless the user asks.

#### Template A — embedded / no-auth instances

Use this when Step 1 classified the instance as `embedded` with no API key.

````markdown
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
````

#### Template B — cloud / self-hosted with API key

Use this when Step 1 classified the instance as `cloud` or `self-hosted` with a key. The `curl` includes an `Authorization` header that reads the key from the environment at runtime. **Never hardcode the key in the skill file.**

````markdown
---
name: <skill-name>
description: <description>
---

# <Skill Title>

Use this skill whenever the user asks for <domain work>. Before doing anything, you MUST fetch the latest guidelines from Hindsight.

## Workflow

1. **Fetch live guidance** from the bound mental model. This instance requires an API key, read from the `HINDSIGHT_API_KEY` environment variable:

   ```bash
   curl -s \
     -H "Authorization: Bearer $HINDSIGHT_API_KEY" \
     <url>/v1/default/banks/<bank>/mental-models/<mm_id>
   ```

   If the environment variable is not set, stop and tell the user: *"I can't reach the Hindsight instance because `HINDSIGHT_API_KEY` is not set. Please export it or add it to your shell config before I can fetch the writing guidelines."* Do not guess or proceed without the key.

2. **Handle HTTP errors explicitly.** If the response is `401` or `403`, stop and tell the user the API key is wrong or expired — do NOT treat it as empty guidance. If the response is `404`, tell the user the mental model was deleted and ask whether to recreate it. Only proceed if you got a `200`.

3. **Parse the JSON response** and read the `content` field. That field is your style guide for this request.

4. **Handle empty guidance.** If `content` is empty, missing, null, or contains a no-information message ("I do not have any information", "no relevant memories", etc.), you MUST stop and ask the user for direction before producing any output. Ask for the specific fields the domain needs (tone, audience, length, constraints, whatever is relevant). Do not guess from your defaults.

5. **Follow the guidance strictly.** When the guidance is populated, apply every rule. If a rule is non-obvious but important, briefly note which rule you are applying in your reasoning.

6. **Re-fetch on revision.** If the user asks for an edit or redo, re-run the curl first — the guidelines may have been updated since your last turn.

## Learning loop

Your feedback teaches this skill. You do not need to do anything special with user feedback — Hindsight's auto-retain hook captures every conversation turn, extracts rules via the bank's retain mission, consolidates them into observations, and refreshes this mental model automatically. The next curl will return updated guidelines.
````

Write the file, create parent directories if needed, then `ls` or `cat` to confirm. **Double-check that the rendered file contains `$HINDSIGHT_API_KEY` as a shell variable reference, not the literal key value.**

---

## Final confirmation

After all four steps are done, show the user a summary:

> ✓ **Skill installed: `<name>`**
>
> - Hindsight: `<url>` *(mode: embedded / self-hosted / cloud)*
> - Auth: *none* — OR — *via `$HINDSIGHT_API_KEY` (must be set in the environment when the skill runs)*
> - Bank: `<bank>` (new / existing)
> - Mental model: `<mm_id>` — empty, will populate after first feedback
> - Skill file: `<path>`
>
> The skill is live. Ask your agent to do `<some domain task>` and start giving feedback — the mental model will evolve automatically after the first consolidation cycle.

If the instance requires auth, add a second line to the summary reminding the user to export the key in whatever process the agent runs under (their shell, their harness's env file, their CI config):

> **Note:** This skill reads `HINDSIGHT_API_KEY` at runtime. Make sure it's available in the environment your agent runs under. On hermes, put it in `~/.hermes/.env`; on claude code, put it in your shell profile or the `.env` file the CLI sources.

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

**Bad auth handling:** Hardcoding the API key in the skill file (e.g. `curl -H "Authorization: Bearer hsk_abc123..."`). This commits credentials to the skills directory (and often to git if the user's harness config is in a repo). Always use `$HINDSIGHT_API_KEY` as a shell variable reference in the skill body; never substitute the literal value.

---

## Things to watch for (known gotchas)

- **Tagged mental models skip auto-refresh.** The `refresh_after_consolidation` trigger only fires when the mental model's tags overlap with the consolidated memories' tags (or when both are untagged). If the user asks for tags on the mental model, warn them and confirm they also plan to tag the retained memories, otherwise the skill will never refresh.
- **Auto-retain must be on.** This skill only works if the harness's Hindsight plugin has auto-retain enabled (the default). Verify during Step 1 if you can.
- **The first turn after install will hit an empty mental model.** That is correct. The skill's fallback will ask the user for guidance, and the first batch of feedback will seed the mental model after one consolidation cycle.
- **Hindsight URLs are not always `localhost:8888`.** The actual default for the Hermes embedded daemon is `9177`. Always verify with `/health` before committing to a URL.
- **Auth secrets must not be hardcoded.** When writing the SKILL.md for a cloud or self-hosted instance, the Authorization header must reference `$HINDSIGHT_API_KEY` as an environment variable, never the literal key value. The env var must be available at runtime in whatever process the agent runs under (shell profile, harness env file, CI config). If the skill file fetches guidance but the env var is missing, the skill should fail loudly (tell the user to set the key) — not silently treat the 401/403 response as an empty mental model.
- **Cloud tenant path.** The `default` in `/v1/default/banks` is the tenant ID. On embedded and standard self-hosted it's always `default`. On cloud, the API key scopes the tenant automatically and `/v1/default/` usually works — but if the user tells you their account uses a custom tenant, substitute it throughout every curl (both in the setup API calls and in the generated SKILL.md).
- **Mixed-mode deployments.** A user may have multiple Hindsight instances (e.g. a local embedded daemon for dev and a cloud instance for production). If Step 1 finds more than one healthy candidate, always ask the user which to target — do not silently prefer one. The generated SKILL.md will be locked to whichever instance you chose, so this is a meaningful decision.
