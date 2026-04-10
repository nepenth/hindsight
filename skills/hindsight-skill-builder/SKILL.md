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

If the user picks cloud or self-hosted, **remember that auth is required**. You'll need the API key in the next substep to write the shared env file.

**Never print the API key value** in your responses. Reference it as `$HINDSIGHT_API_KEY` or "the configured key" instead.

If no candidates respond or the user declines all of them, ask directly:

> I couldn't find a running Hindsight instance. Please tell me:
> - The API URL (e.g., `https://hindsight.mycompany.com` or `http://localhost:9177`)
> - Whether it requires an API key, and if so where it's stored (env var name or config file path)

Once you have a confirmed `(url, mode, auth)` triple, store it for the rest of the flow. Do not re-probe in later steps.

### Ensure the `hindsight` CLI is installed

Every Hindsight-backed skill in this family — both the meta-skill's own setup work and the runtime of every skill it creates — uses the `hindsight` CLI, not raw `curl`. Check that it's on the user's PATH:

```bash
command -v hindsight
```

If the command returns a path, you're done — skip ahead. If it's missing, propose installing it:

> I need the `hindsight` CLI to set up the bank and mental model. I'd like to run:
>
> ```bash
> curl -fsSL https://hindsight.vectorize.io/get-cli | bash
> ```
>
> OK to install?

Wait for approval, run the installer, then verify with `hindsight --version`. If the user declines the install, stop the whole flow and tell them they need to install the CLI before continuing — the rest of the meta-skill and the generated skills cannot work without it.

### Write the shared env file at `~/.hindsight/learning-skill.env`

This file is the **single source of truth for Hindsight connection details** used by every skill created through this meta-skill. It holds `HINDSIGHT_API_URL` and (if auth is required) `HINDSIGHT_API_KEY`, in a format that can be `source`d into any shell. The runtime of every generated skill sources this file before calling `hindsight`.

Check whether the file already exists:

```bash
ls -la ~/.hindsight/learning-skill.env 2>/dev/null
```

**If the file exists**, source it and show the user what's there (URL only, never print the key), then ask whether to reuse it or overwrite with the URL you just confirmed in the previous substep:

> The shared env file already exists at `~/.hindsight/learning-skill.env`:
> - `HINDSIGHT_API_URL=http://localhost:9177`
> - `HINDSIGHT_API_KEY=<set>` (or `<empty>`)
>
> Reuse this, or overwrite with `<new_url>` (and re-ask for the key if needed)?

**If the file does not exist, or the user chose to overwrite**, gather the values:

1. URL: use the URL confirmed in the previous substep.
2. Key (only if auth is required): check `HINDSIGHT_API_KEY` in the current environment. If it's set, offer to use it. Otherwise prompt the user directly: *"Please paste your Hindsight API key (I will not print it back)."* Never read it from any other file — the env file is the only persistent store managed by this meta-skill.

Propose the write:

> I'll write `~/.hindsight/learning-skill.env` with:
> - `HINDSIGHT_API_URL="<url>"`
> - `HINDSIGHT_API_KEY=<set>` *(or empty if no auth)*
>
> Permissions will be set to `0600` (user read/write only). The file will be plain text on disk — if that's a concern, stop here and set up your key differently. OK to write?

Wait for approval, then create the file with the exact commands below. The `chmod` MUST run.

```bash
mkdir -p ~/.hindsight
cat > ~/.hindsight/learning-skill.env <<'EOF'
export HINDSIGHT_API_URL="<url>"
export HINDSIGHT_API_KEY="<key-or-empty>"
EOF
chmod 600 ~/.hindsight/learning-skill.env
```

Verify the file was written, permissions are correct, and that sourcing it populates the env vars:

```bash
ls -la ~/.hindsight/learning-skill.env     # must show -rw-------
source ~/.hindsight/learning-skill.env
hindsight health                             # must return a healthy response
```

If `hindsight health` fails, something is wrong with the URL or key — surface the error to the user and ask them to fix it before continuing.

> **Do NOT print the key value at any point**, not even when writing it into the heredoc. The heredoc substitution happens inside your own process; keep the literal value out of your chat output. Use a placeholder like `<key>` in any text the user sees.

---

## Step 2 — Select or create a bank

All commands in this step (and Step 3) use the `hindsight` CLI. Start by sourcing the env file so the CLI routes to the right instance with the right auth:

```bash
source ~/.hindsight/learning-skill.env
```

Do this once at the top of the step. The CLI reads `HINDSIGHT_API_URL` and `HINDSIGHT_API_KEY` from the environment automatically — no per-command flags needed.

List existing banks:

```bash
hindsight bank list --output json
```

Inspect their names and missions. For each candidate bank, fetch the config:

```bash
hindsight bank config <bank_id> --output json
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

Create the bank with two CLI calls — `bank create` for the identity, then `bank set-config` to set the three missions in one shot:

```bash
hindsight bank create <bank_id> --name "<bank_id>"

hindsight bank set-config <bank_id> \
  --retain-mission "<retain_mission>" \
  --observations-mission "<observations_mission>" \
  --reflect-mission "<reflect_mission>"
```

Verify by re-fetching the config and confirm all three overrides are set:

```bash
hindsight bank config <bank_id> --output json
```

---

## Step 3 — Create the binding mental model

The mental model is what the new skill will fetch via the CLI at runtime. It has:

- **`id`** — matches the skill name so the CLI invocation is predictable (e.g., `linkedin-post-writer`)
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

**Note on tags:** do NOT set tags on the mental model. The `refresh_after_consolidation` trigger is tag-gated — if the mental model has tags but the retained memories don't, the trigger silently does nothing and the mental model never refreshes. When in doubt, leave tags empty.

Wait for approval, then create the mental model with the CLI:

```bash
hindsight mental-model create <bank_id> "<mm_name>" "<source_query>" --id <mm_id>
```

### CLI gap: set `refresh_after_consolidation` via a fallback PATCH

The `hindsight mental-model create` command does not currently accept a `--trigger` or `--refresh-after-consolidation` flag, and neither does `hindsight mental-model update`. This will be fixed upstream in a future CLI release. Until then, set the trigger via one raw `curl` PATCH immediately after the CLI create. The env file is already sourced, so `HINDSIGHT_API_URL` and `HINDSIGHT_API_KEY` are available:

```bash
curl -sS -X PATCH \
  ${HINDSIGHT_API_KEY:+-H "Authorization: Bearer $HINDSIGHT_API_KEY"} \
  -H "Content-Type: application/json" \
  -d '{"trigger": {"refresh_after_consolidation": true}, "tags": []}' \
  "$HINDSIGHT_API_URL/v1/default/banks/<bank_id>/mental-models/<mm_id>"
```

This is the ONLY raw curl call in the whole meta-skill — everything else goes through the CLI. When the CLI gap is fixed, remove this block.

Verify the mental model exists and has the trigger set:

```bash
hindsight mental-model get <bank_id> <mm_id> --output json
```

The initial `content` field will be a "no information" response — that is correct and expected. The skill's fallback handles it.

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

Render this template, substituting `<placeholders>`. The same template works for every deployment mode — the runtime skill sources the shared env file and lets the `hindsight` CLI handle URL and auth. There is no branching. Do not add extra sections beyond what is here unless the user asks.

````markdown
---
name: <skill-name>
description: <description>
---

# <Skill Title>

Use this skill whenever the user asks for <domain work>. Before doing anything, you MUST fetch the latest guidelines from Hindsight.

## Workflow

1. **Load the Hindsight connection** (once per session is enough):

   ```bash
   source ~/.hindsight/learning-skill.env
   ```

   If this file does not exist, STOP and tell the user: *"The shared Hindsight env file is missing. Ask the agent to run the `hindsight-skill-builder` skill to set it up, or create it manually."* Do not try to reach Hindsight without it.

2. **Fetch live guidance** from the bound mental model:

   ```bash
   hindsight mental-model get <bank_id> <mm_id> --output json
   ```

   If the command exits non-zero, STOP and report the error verbatim to the user. A CLI failure is NOT the same as empty guidance — do not fall through to step 4. Typical failures: unreachable instance (daemon down / wrong URL), authentication error (wrong or missing `HINDSIGHT_API_KEY`), mental model deleted (ask the user whether to recreate it).

3. **Parse the JSON output** from the CLI and read the `content` field. That field is your style guide for this request.

4. **Handle empty guidance.** If `content` is empty, missing, null, or contains a no-information message ("I do not have any information", "no relevant memories", etc.), you MUST stop and ask the user for direction before producing any output. Ask for the specific fields the domain needs (tone, audience, length, constraints, whatever is relevant). Do not guess from your defaults.

5. **Follow the guidance strictly.** When the guidance is populated, apply every rule. If a rule is non-obvious but important, briefly note which rule you are applying in your reasoning.

6. **Re-fetch on revision.** If the user asks for an edit or redo, re-run `hindsight mental-model get ...` first — the guidelines may have been updated since your last turn.

## Learning loop

Your feedback teaches this skill. You do not need to do anything special with user feedback — Hindsight's auto-retain hook captures every conversation turn, extracts rules via the bank's retain mission, consolidates them into observations, and refreshes this mental model automatically. The next CLI call will return updated guidelines.
````

Write the file, create parent directories if needed, then `ls` or `cat` to confirm.

---

## Final confirmation

After all four steps are done, show the user a summary:

> ✓ **Skill installed: `<name>`**
>
> - Hindsight: `<url>` *(mode: embedded / self-hosted / cloud)*
> - Env file: `~/.hindsight/learning-skill.env` *(chmod 600; contains `HINDSIGHT_API_URL` and `HINDSIGHT_API_KEY` if auth is required)*
> - Bank: `<bank>` (new / existing)
> - Mental model: `<mm_id>` — empty, will populate after first feedback
> - Skill file: `<path>`
>
> The skill uses the `hindsight` CLI at runtime — it sources the env file and calls `hindsight mental-model get` each time the skill fires. No direct HTTP calls, no inline auth.
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

**Bad skill body:** Anything that tries to hardcode rules inline (tone, length, format). The whole point is that the rules live in the mental model and evolve. The skill body should contain ONLY the source + `hindsight mental-model get` workflow, nothing else.

**Bad auth handling:** Embedding the API key directly in the skill file or in any generated command. The key lives in `~/.hindsight/learning-skill.env` with `chmod 600`, and the skill sources that file to pick it up. Never substitute a literal `hsk_...` value into any file the meta-skill writes, and never echo the key in chat output even during setup.

**Bad fallback to curl:** Reverting to raw `curl` in the generated skill body because "it's simpler". The CLI exists specifically so skills don't have to manage URLs, auth, tenant paths, and HTTP error parsing themselves. The ONE place raw curl is allowed is the `refresh_after_consolidation` fallback PATCH in Step 3, which exists only because the CLI doesn't yet support setting triggers — remove that call once the CLI is updated.

---

## Things to watch for (known gotchas)

- **`hindsight` CLI is required.** Both the meta-skill setup and every generated skill assume the CLI is installed and on PATH. Step 1 verifies this and offers to install it if missing. If the user declines, abort the setup — there's no fallback to raw curl in the happy path.
- **CLI gap: mental-model trigger is not exposed.** `hindsight mental-model create` and `hindsight mental-model update` do not currently support `refresh_after_consolidation` or tags. Step 3 uses a one-shot `curl PATCH` immediately after the CLI create to set the trigger and empty tags. This is the ONLY raw curl call in the whole flow. When the CLI adds `--refresh-after-consolidation` and `--tags` flags, delete the fallback block.
- **Tagged mental models skip auto-refresh.** The `refresh_after_consolidation` trigger only fires when the mental model's tags overlap with the consolidated memories' tags (or when both are untagged). The fallback PATCH always sets `"tags": []` for this reason — do NOT change that to add tags unless you're also tagging every memory the auto-retain hook writes.
- **Auto-retain must be on.** This skill only works if the harness's Hindsight plugin has auto-retain enabled (the default). The generated skill cannot verify this itself — the user is responsible for ensuring it.
- **The first turn after install will hit an empty mental model.** That is correct. The skill's fallback will ask the user for guidance, and the first batch of feedback will seed the mental model after one consolidation cycle.
- **Hindsight URLs are not always `localhost:8888`.** The actual default for the Hermes embedded daemon is `9177`; Hindsight Cloud is `https://api.hindsight.vectorize.io`; self-hosted is whatever the user configured. Always verify with `hindsight health` after writing the env file.
- **Env file is the single source of truth.** Do not write the URL or key to any other file (not `~/.hindsight/config`, not the harness config, not the shell rc). Every generated skill sources `~/.hindsight/learning-skill.env` directly. If the user needs a different Hindsight instance per skill (e.g. dev embedded + prod cloud), that's a v2 concern — for v1, one file, one instance, all skills on it.
- **Env file permissions.** Always `chmod 600`. The file contains the API key in plaintext. If the user is concerned, that's a valid concern — note that this is the v1 storage strategy and OS keychain integration is a future enhancement.
- **Cloud tenant path.** The `default` in `/v1/default/banks` is the tenant ID. On embedded and standard self-hosted it's always `default`. On cloud, the API key scopes the tenant automatically and `default` usually works — but if the user tells you their account uses a custom tenant, ask them to confirm before continuing. (The CLI's `<bank_id>` argument uses the same tenant the CLI was configured with.)
- **Mixed-mode deployments.** A user may have multiple Hindsight instances (e.g. a local embedded daemon for dev and a cloud instance for production). If Step 1 finds more than one healthy candidate, always ask the user which to target — do not silently prefer one. The env file is locked to whichever instance you chose.
