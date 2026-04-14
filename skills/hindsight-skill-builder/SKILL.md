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

At every decision point below, you follow this pattern:

1. **Explore** — run whatever read-only checks you need (read the harness plugin config file, run `hindsight health`)
2. **Propose** — show the user your proposed values in a clearly labeled block
3. **Ask for approval** — end with a direct question like *"Proceed with this, or do you want to edit?"*
4. **Wait for explicit confirmation** before making any API call or writing any file

Never chain decision points. If the user gives partial feedback ("change the source_query"), regenerate the affected field and ask again.

Decision points that require approval:

- **Step 1 — Detected harness config:** the URL, bank id, and key (status only, never the value) you read from the harness plugin's config file
- **Step 1 — Env file write:** the final contents of `~/.hindsight/learning-skill.env`
- **Step 2 — Mental model spec:** ONE approval covering the mental model id, name, and source_query. The bank id is fixed (it comes from the env file / harness plugin). After approval, the CLI create + trigger PATCH + verify run without further pauses.
- **Step 3 — Skill file:** the final description and rendered SKILL.md content before writing

The meta-skill is intentionally minimal: it never creates banks, never sets missions, never asks the user to design a memory pipeline. It binds new mental models to the bank the harness plugin already uses, and writes a skill file that fetches them at runtime.

---

## Step 1 — Read Hindsight connection details from an installed harness plugin

The architecture of this feature relies on **the user's harness plugin being the source of truth** for Hindsight connection details. The flow the user sets up is:

1. User installs a Hindsight plugin for their harness (hermes, OpenClaw, Claude Code, Codex, etc.)
2. User configures the plugin with an API URL, optional API key, and a bank id — either via the plugin's setup wizard or by editing its config file
3. User installs this meta-skill
4. The meta-skill **reads the plugin config** to figure out which Hindsight instance to talk to and which bank to bind new mental models to
5. All generated skills use the same `(url, key, bank_id)` the harness plugin uses

This matters because the harness's **auto-retain hook writes every conversation turn to the plugin's configured bank**. If the meta-skill created a different bank, no auto-retain data would ever reach it and the mental model would stay empty forever. Binding to the plugin's bank is not optional — it's the only way the learning loop works.

### Detect an installed harness plugin

Check the known config locations **in this order**, stopping at the first one that exists. Do NOT probe multiple at once — take the first match and confirm it with the user.

**hermes** — `$HERMES_HOME/hindsight/config.json` (falls back to `~/.hermes/hindsight/config.json` when no profile is active)

Hermes sets `HERMES_HOME` to the active profile's root when you're running under `hermes --profile <name>`. Resolve the config path **from that env var**, not from a hardcoded `~/.hermes/` path, otherwise a named profile's config is missed and the meta-skill binds skills to the wrong bank.

```bash
HERMES_CFG="${HERMES_HOME:-$HOME/.hermes}/hindsight/config.json"
test -f "$HERMES_CFG" && echo "found: $HERMES_CFG"
```

Keys to extract (JSON):
- `bank_id` — the bank auto-retain writes to
- `mode` — one of `cloud`, `local_embedded`, `local_external`
- `api_url` — explicit URL when `mode` is `cloud` or `local_external`
- `api_key` — optional; falls back to the `HINDSIGHT_API_KEY` env var for cloud mode

For `mode == "local_embedded"`: the URL is `http://localhost:<port>` where `<port>` is the hermes profile's allocated port. Read it via:

```bash
hindsight-embed -p hermes profile show --output json
```

Take the `port` field. If `hindsight-embed` is not available, fall back to `http://localhost:9177` (the hermes default profile port).

**claude-code** — `~/.hindsight/claude-code.json` OR `~/.claude/hindsight.json`

```bash
test -f ~/.hindsight/claude-code.json && echo found
```

Keys (JSON, camelCase):
- `hindsightApiUrl` — full URL (e.g. `http://localhost:4445/api/hindsight`)
- `bankId` — bank id
- `apiKey` — optional

**codex** — `~/.hindsight/codex/settings.json`

```bash
test -f ~/.hindsight/codex/settings.json && echo found
```

Keys (JSON, camelCase):
- `hindsightApiUrl` — full URL (may be empty; if empty, fall back to `HINDSIGHT_API_URL` env var or ask the user)
- `bankId` — bank id
- `apiKey` — optional

**openclaw** — `~/.openclaw/extensions/hindsight-openclaw/` (schema present, secrets in the OpenClaw vault)

OpenClaw stores the plugin secrets inside its encrypted vault, not as a plain JSON file. The meta-skill **cannot read them directly**. Instead, check for the plugin directory and ask the user to provide the values manually:

```bash
test -d ~/.openclaw/extensions/hindsight-openclaw && echo found
```

If the directory exists, tell the user:

> I see OpenClaw's Hindsight plugin is installed, but OpenClaw keeps plugin secrets in its vault and I can't read them directly. Please paste the Hindsight API URL, bank id, and API key (if any) that you configured for this plugin. I will not print any of them back.

**Unknown harness** — if none of the files above exist:

> I couldn't find a Hindsight plugin configuration for hermes, claude-code, codex, or OpenClaw. This meta-skill assumes you've already installed and configured a Hindsight plugin for your agent harness. The plugin's auto-retain hook is what feeds the mental model with conversation data — without it, any skill I create would never learn from your feedback.
>
> Please install a Hindsight plugin for your harness first. See:
> - hermes: https://github.com/vectorize-io/hindsight/tree/main/skills/hindsight-local
> - Hindsight Cloud: https://ui.hindsight.vectorize.io
>
> Once the plugin is installed and configured, re-run me.

Stop the flow. Do not continue without a plugin to bind to.

### Propose the extracted config to the user

Once you've read a plugin's config, show the user what you found and ask for confirmation. Do not print the API key value — reference it as `<set>` or `<empty>`.

> I detected a **<harness>** Hindsight plugin. Here's what I read from `<config_path>`:
>
> - API URL: `<url>`
> - Bank id: `<bank_id>`
> - API key: `<set>` *(or `<empty>`)*
> - Mode: `<mode>` *(if applicable)*
>
> Any new skill I create will bind to the `<bank_id>` bank on this instance, so the skill learns from the same conversations your harness's auto-retain hook captures.
>
> Use this config, or tell me to re-read a different plugin config file?

Wait for approval. If the user wants to use a different plugin, repeat the detection with the location they specify.

### Verify the config works

Before touching anything, run a one-shot `hindsight health` to make sure the extracted values actually reach a live instance:

```bash
HINDSIGHT_API_URL="<url>" ${api_key:+HINDSIGHT_API_KEY="<key>"} hindsight health
```

If this fails:
- For hermes `local_embedded`: the daemon isn't running. Tell the user to start hermes (which auto-starts the daemon) or run `hindsight-embed -p hermes daemon start` manually, then retry.
- For cloud: the URL or key is wrong. Tell the user to verify their plugin config.
- For self-hosted / other: surface the error and ask.

Do not proceed until `hindsight health` returns healthy.

### Install (or upgrade) the `hindsight` CLI

The generated skill invokes `hindsight mental-model get` at runtime, and this meta-skill itself uses the CLI to create banks and mental models. We **always** run the upstream installer so the user ends up on the latest release — older builds won't have the flags this skill relies on (`--trigger-refresh-after-consolidation`, `--tags`).

The installer is idempotent — it'll upgrade in place if `hindsight` is already on PATH.

Propose the install and wait for approval:

> To set up the bank and the runtime CLI the new skill will use, I want to install or upgrade the `hindsight` CLI to the latest release:
>
> ```bash
> curl -fsSL https://hindsight.vectorize.io/get-cli | bash
> ```
>
> The script writes the binary to `~/.local/bin/hindsight` and is safe to re-run. OK to install?

Once approved, run it. Then verify and report the version:

```bash
curl -fsSL https://hindsight.vectorize.io/get-cli | bash
PATH="$HOME/.local/bin:$PATH" hindsight --version
```

If the install fails (the upstream installer hits the unauthenticated GitHub releases API and gets rate-limited at 60 requests/hour per IP), check whether `hindsight` is already on PATH and meets the minimum version. If yes, proceed and warn the user. If no, stop and tell the user to retry in a few minutes or install manually from <https://github.com/vectorize-io/hindsight/releases>.

If the user declines the install entirely, stop the whole flow.

### Write the shared env file at `~/.hindsight/learning-skill.env`

Write the verified `(url, key, bank_id)` triple to a sourceable file that every generated skill will read at runtime. This is how the generated SKILL.md bodies stay short — they source one file and call the CLI.

Propose the write:

> I'll write `~/.hindsight/learning-skill.env` (chmod 600) with:
> - `HINDSIGHT_API_URL="<url>"`
> - `HINDSIGHT_API_KEY=<set>` *(or empty)*
> - `HINDSIGHT_BANK_ID="<bank_id>"`
>
> OK to write?

Once approved:

```bash
mkdir -p ~/.hindsight
cat > ~/.hindsight/learning-skill.env <<'EOF'
export HINDSIGHT_API_URL="<url>"
export HINDSIGHT_API_KEY="<key-or-empty>"
export HINDSIGHT_BANK_ID="<bank_id>"
EOF
chmod 600 ~/.hindsight/learning-skill.env
```

Verify:

```bash
ls -la ~/.hindsight/learning-skill.env     # must show -rw-------
source ~/.hindsight/learning-skill.env
hindsight health                             # must return healthy
```

> **Do NOT print the key value at any point**, not even inside the heredoc. Substitution happens inside your own process; keep the literal value out of chat output.

### What if the user re-runs the meta-skill later

If `~/.hindsight/learning-skill.env` already exists when the meta-skill starts, source it, compare what's in there to what's in the detected plugin config, and ask the user:

> The shared env file already exists and points at `<old_url>` / bank `<old_bank_id>`. The detected plugin now reports `<new_url>` / bank `<new_bank_id>`.
>
> Keep the existing file (the plugin config must have changed; any previously-created skills still point at `<old_bank_id>`), or overwrite it with the new values (new skills bind to `<new_bank_id>`; old skills may stop learning)?

Let the user decide. Never silently overwrite.

---

## Step 2 — Create the mental model on the harness's bank

Step 2 is deliberately minimal. The meta-skill does NOT create a new bank, does NOT set retain / observations / reflect missions, and does NOT manage bank configuration at all. The bank the new skill learns from is **whatever the harness plugin is already configured to use** (captured in `HINDSIGHT_BANK_ID` from the env file written in Step 1). Every self-improving skill on this machine shares that bank and is scoped by its own mental model's `source_query`.

Why this matters: the harness's auto-retain hook writes to exactly one bank per session. If the meta-skill created a dedicated bank per skill, auto-retain data would never reach it and the mental model would stay empty forever. Binding to the harness's bank is the only way the learning loop works end-to-end without modifying the harness plugin.

### The single approval

Source the env file so `HINDSIGHT_API_URL`, `HINDSIGHT_API_KEY`, and `HINDSIGHT_BANK_ID` are available:

```bash
source ~/.hindsight/learning-skill.env
```

Then propose the full mental model spec in one block and ask for ONE approval.

> I'll create this mental model on the **`<HINDSIGHT_BANK_ID>`** bank (the one your harness plugin is already configured to use for auto-retain):
>
> - **id:** `linkedin-post-writer`
> - **name:** LinkedIn Post Writer Guidelines
> - **source_query:** *"What are the current writing style, tone, structure, voice, and do/dont rules I should follow when drafting LinkedIn posts on behalf of this user?"*
> - **refresh_after_consolidation:** true
> - **tags:** none
>
> Approve?

Wait for approval. If the user wants to tweak the id, name, or source_query, regenerate and ask again. Do not change the bank id — that comes from the env file and is tied to the harness plugin.

### Execute after approval

Once approved, run the commands below without pausing:

```bash
# 1. Ensure the bank identity exists. The bank name comes from the harness
#    plugin's config, but the bank itself may not have been created on the
#    daemon yet (e.g. brand-new profile where no retain has happened). Always
#    run `bank create` first — it is a no-op if the bank already exists.
#    Do NOT bind the skill to a different bank if the target is missing;
#    create the missing bank and proceed.
hindsight bank create "$HINDSIGHT_BANK_ID" --name "$HINDSIGHT_BANK_ID" 2>/dev/null || true

# 2. Create the mental model on that bank
hindsight mental-model create "$HINDSIGHT_BANK_ID" "<mm_name>" "<source_query>" --id <mm_id>

# 3. Set the refresh trigger and empty tags (CLI gap — see below)
curl -sS -X PATCH \
  ${HINDSIGHT_API_KEY:+-H "Authorization: Bearer $HINDSIGHT_API_KEY"} \
  -H "Content-Type: application/json" \
  -d '{"trigger": {"refresh_after_consolidation": true}, "tags": []}' \
  "$HINDSIGHT_API_URL/v1/default/banks/$HINDSIGHT_BANK_ID/mental-models/<mm_id>"

# 4. Verify
hindsight mental-model get "$HINDSIGHT_BANK_ID" <mm_id> --output json
```

**Hard rule:** if `hindsight mental-model create` fails because the bank does not exist, create the bank (identity only, no missions — the harness plugin will own whatever extraction behavior it wants) and retry. Never silently fall back to a different bank id. The bank id in the env file is authoritative because it's the bank the harness plugin's auto-retain hook writes to. Binding a skill to a different bank would break the learning loop.

The initial `content` field will be a "no information" response. That's correct — the skill's fallback at runtime asks the user for guidance on first use and the mental model populates after the first consolidation cycle.

### Design guidance for the mental model

- **`id`** — matches the skill name so the CLI invocation is predictable (e.g., `linkedin-post-writer`)
- **`name`** — human-readable (e.g., "LinkedIn Post Writer Guidelines")
- **`source_query`** — the most important field. It is the **question the mental model answers whenever the skill fetches it**, and it is the ONLY thing scoping this skill's output to its domain since the bank is shared. A good `source_query`:
  - Mirrors the skill's purpose: *"What are the current X rules I should follow when Y?"*
  - Is specific enough that reflect pulls only observations relevant to this skill's domain, even though the bank contains feedback from all skills
  - Is stable — it does not need to be rewritten as the skill learns
  - Asks for guidance the user *would* give you, not facts about the user
- **`refresh_after_consolidation`** — always `true` for self-improving skills
- **`tags`** — leave empty. Do NOT set tags on the mental model. The trigger is tag-gated — if the mental model has tags but the retained memories don't, the trigger silently does nothing and the mental model never refreshes.

### CLI gap: `refresh_after_consolidation` is set via a fallback PATCH

The `hindsight mental-model create` command does not currently accept a `--trigger` or `--refresh-after-consolidation` flag, and neither does `hindsight mental-model update`. Until the CLI is fixed upstream, set the trigger via the raw `curl` PATCH in command 2 above — immediately after `mental-model create`, before verification. This is the ONLY raw curl call in the whole meta-skill. When the CLI gap is fixed, replace command 2 with the equivalent CLI flag.

### Why the meta-skill doesn't create or tune banks anymore

A previous version of this meta-skill created a dedicated bank per skill with hand-designed `retain_mission` and `observations_mission` values. That version was wrong: harness auto-retain only writes to ONE bank per session (read from the plugin's config), so any dedicated bank the meta-skill created would never receive user feedback.

The current version accepts a constraint: **one bank per harness, many skills, many mental models, all scoped by source_query**. The bank's retain and observations missions are whatever the harness plugin set up (often empty, sometimes default). Mental model `source_query` does all the per-skill filtering at reflect time.

Downside: observations in a shared bank are noisier because the retain mission isn't domain-specific. Upside: the learning loop actually closes, and multiple skills can learn from the same conversation when it touches multiple domains. We could revisit per-skill bank tuning later via multi-bank harness plugin support, but that's a v2 story.

---

## Step 3 — Write the SKILL.md file

### Where to write it

Figure out the skills directory for the CURRENT harness session. This is **profile-aware** — named profiles have their own skills directories and you must NOT write to the default profile's directory when running under a named profile.

Preferred resolution order:

1. **`$HERMES_HOME/skills/`** — hermes sets `HERMES_HOME` to the active profile's root (e.g. `~/.hermes/profiles/smoke-marketing/` for a named profile, `~/.hermes/` for the default profile). Use this whenever the env var is set. Example:
   ```bash
   SKILLS_DIR="${HERMES_HOME:-$HOME/.hermes}/skills"
   ```
2. If `HERMES_HOME` is not set, check for Claude Code: `~/.claude/skills/`.
3. If neither, check Codex: `~/.codex/skills/`.
4. If none are found, ask the user where the harness loads skills from.

**Never** default to `~/.hermes/skills/` when `HERMES_HOME` is set to a different path — that's the default profile's directory and writing there pollutes it. If `HERMES_HOME=/Users/foo/.hermes/profiles/marketing-agent`, the new skill MUST go to `/Users/foo/.hermes/profiles/marketing-agent/skills/<skill-name>/SKILL.md`.

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

2. **Fetch live guidance** from the bound mental model. The bank id comes from the sourced env file; the mental model id is fixed to this skill:

   ```bash
   hindsight mental-model get "$HINDSIGHT_BANK_ID" <mm_id> --output json
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

After all three steps are done, show the user a summary:

> ✓ **Skill installed: `<name>`**
>
> - Harness plugin: `<harness>` *(hermes / claude-code / codex / openclaw)*
> - Hindsight: `<url>`
> - Env file: `~/.hindsight/learning-skill.env` *(chmod 600; holds `HINDSIGHT_API_URL`, `HINDSIGHT_API_KEY`, `HINDSIGHT_BANK_ID`)*
> - Bank: `<HINDSIGHT_BANK_ID>` *(shared with your harness's auto-retain stream)*
> - Mental model: `<mm_id>` — empty, will populate after first feedback
> - Skill file: `<path>`
>
> The skill is live. Give your agent work and feedback as usual. Your harness's auto-retain writes every conversation turn to `<bank_id>`; consolidation produces observations; this mental model refreshes automatically and the skill's next call picks up the updated guidance.
>
> Because this skill shares a bank with everything else on `<bank_id>`, the mental model's `source_query` is the only thing filtering its output. If you ever notice guidance drift — e.g. it starts picking up rules meant for a different domain — that's a signal to narrow the source_query.

---

## Worked example — `marketing-writer`

This is a known-good shape. The bank is whatever the harness plugin is configured to use (e.g. `hermes`, `claude-code`, `codex`) — this meta-skill never creates banks.

**Bank:** read from `HINDSIGHT_BANK_ID` (the harness plugin's bank)

**Mental model:**

- **id:** `marketing-writer`
- **name:** Marketing Writing Guidelines
- **source_query:** *"What are the current writing style, tone, structure, voice, and do/dont rules I should follow when drafting marketing posts on behalf of this human?"*
- **refresh_after_consolidation:** true, no tags

**Skill description:**

> *"Use this skill whenever the user asks for any marketing copy, LinkedIn post, X post, blog teaser, newsletter blurb, announcement, launch copy, or promotional caption. Fetches the latest writing guidelines from Hindsight before drafting and asks the user for tone/audience/length/constraints when no guidance exists yet."*

In an earlier prototype that pre-tuned the bank with a domain-specific retain mission, this configuration started empty and evolved into a ~5000-character structured style guide after four rounds of user feedback. The current version gives up the per-skill retain mission in exchange for the bank actually being the one auto-retain writes to, so the loop closes without manual config edits.

---

## Counter-examples — what NOT to write

Bad configs produce skills that sort-of-work but never auto-activate well and never close the learning loop. Avoid these:

**Bad source_query:** *"What do I need to know?"*
Too broad — reflect will pull everything in the bank, which includes feedback meant for OTHER skills (since we share one bank across all skills). Good source_queries are scoped to the skill's domain and phrased as the question whose answer *is* the skill's runtime instructions: *"What are the current rules I should follow when drafting marketing posts?"*. The source_query is your only domain filter; make it count.

**Bad description:** *"Marketing helper."*
Ten characters, zero keywords. The harness will never match user requests to it. Good descriptions enumerate every phrase the user might say ("LinkedIn post, X post, blog teaser, newsletter, announcement, launch copy, promotional caption").

**Bad skill body:** Anything that tries to hardcode rules inline (tone, length, format). The whole point is that the rules live in the mental model and evolve. The skill body should contain ONLY the source + `hindsight mental-model get` workflow, nothing else.

**Bad auth handling:** Embedding the API key directly in the skill file or in any generated command. The key lives in `~/.hindsight/learning-skill.env` with `chmod 600`, and the skill sources that file to pick it up. Never substitute a literal `hsk_...` value into any file the meta-skill writes, and never echo the key in chat output even during setup.

**Bad bank creation:** Creating a NEW bank for each skill. This was the original (broken) design — the harness's auto-retain hook only writes to ONE bank per session, so any dedicated bank the meta-skill creates would never receive user feedback. The current architecture binds every new skill to the harness plugin's existing bank, which is the only bank auto-retain actually writes to.

**Bad fallback to curl:** Reverting to raw `curl` in the generated skill body because "it's simpler". The CLI exists specifically so skills don't have to manage URLs, auth, tenant paths, and HTTP error parsing themselves. The ONE place raw curl is allowed is the `refresh_after_consolidation` fallback PATCH in Step 2, which exists only because the CLI doesn't yet support setting triggers — remove that call once the CLI is updated.

---

## Things to watch for (known gotchas)

- **`hindsight` CLI is required.** Both the meta-skill setup and every generated skill assume the CLI is installed and on PATH. Step 1 verifies this and offers to install it if missing. If the user declines, abort the setup — there's no fallback to raw curl in the happy path.
- **CLI gap: mental-model trigger is not exposed.** `hindsight mental-model create` and `hindsight mental-model update` do not currently support `refresh_after_consolidation` or tags. Step 2 uses a one-shot `curl PATCH` immediately after the CLI create to set the trigger and empty tags. This is the ONLY raw curl call in the whole flow. When the CLI adds `--refresh-after-consolidation` and `--tags` flags, delete the fallback block.
- **Harness plugin must be installed FIRST.** The meta-skill cannot work in isolation — it reads the URL, key, and bank id from an installed harness Hindsight plugin (hermes / claude-code / codex / openclaw). If no plugin is detected, Step 1 stops and tells the user to install one. The plugin's auto-retain hook is the only source of conversation data; without it, the mental model never learns anything.
- **One bank per harness, shared across skills.** Every skill the meta-skill creates binds to the same bank — the one the harness plugin is configured to write to. Multiple skills can coexist on that bank, each scoped by its own mental model `source_query`. There is no per-skill bank, no per-skill retain mission, no per-skill consolidation tuning. If the user wants per-skill tuning, that requires multi-bank harness support, which is a v2 story.
- **Tagged mental models skip auto-refresh.** The `refresh_after_consolidation` trigger only fires when the mental model's tags overlap with the consolidated memories' tags (or when both are untagged). The fallback PATCH always sets `"tags": []` for this reason — do NOT change that to add tags unless you're also tagging every memory the auto-retain hook writes.
- **Auto-retain must be on.** This pattern only works if the harness's Hindsight plugin has auto-retain enabled (the default for hermes / claude-code / codex). The generated skill cannot verify this itself — the user is responsible.
- **The first turn after install will hit an empty mental model.** That is correct. The skill's fallback asks the user for guidance, and the first batch of feedback seeds the mental model after one consolidation cycle.
- **OpenClaw secrets are vault-encrypted.** OpenClaw stores plugin secrets inside its own vault, not as plain JSON. The meta-skill cannot read them — for OpenClaw users, fall back to asking them to paste the URL / key / bank id manually after detecting the plugin directory exists.
- **Env file is the single source of truth.** Do not write the URL, key, or bank id to any other file (not `~/.hindsight/config`, not the harness config, not the shell rc). Every generated skill sources `~/.hindsight/learning-skill.env` directly. If the harness plugin's config later changes (URL, key, or bank), the meta-skill must be re-run so the env file resyncs.
- **Env file permissions.** Always `chmod 600`. The file contains the API key in plaintext. OS keychain integration is a future enhancement.
- **Cloud tenant path.** The `default` in `/v1/default/banks` is the tenant ID. On embedded and standard self-hosted it's always `default`. On cloud, the API key scopes the tenant automatically and `default` usually works — but if the user tells you their account uses a custom tenant, ask them to confirm before continuing.
