# Hermes Marketing-Writer Demo

A demonstration that the "self-improving skill" concept can be implemented today
on top of stock Hindsight, with no schema changes and no Git integration.

## The idea

A skill file lives in the agent harness. It is **thin** and **never changes** —
it just contains a single `curl` to fetch the *real* writing instructions from
a Hindsight mental model. The mental model is what evolves. As the user gives
feedback during normal conversation, Hindsight extracts writing rules,
consolidates them into observations, and the mental model auto-refreshes after
each consolidation cycle. The next `curl` from the skill returns updated
guidance.

So the loop is:

```
user request → skill → curl http://.../mental-models/marketing-writing-guidelines
            → parse content field
            → if empty, ask user
            → otherwise, write following the returned guide
            → user gives feedback in next turn
            → auto-retain (Hindsight Hermes plugin) ingests the conversation
            → fact extraction (steered by retain_mission)
            → consolidation (steered by observations_mission)
            → mental model auto-refresh (refresh_after_consolidation: true)
            → loop
```

The agent's *behavior contract* (the SKILL.md) is static. The agent's
*runtime instructions* (the mental model content) evolve.

## Setup

Hermes 0.8.0 with the bundled hindsight plugin in `local_embedded` mode,
gemini-2.5-flash for memory ops, dedicated bank `marketing-manager`.

`~/.hermes/hindsight/config.json` (only the demo-relevant fields):

```json
{
  "mode": "local_embedded",
  "bank_id": "marketing-manager",
  "retain_async": false,
  "llm_provider": "gemini",
  "llm_model": "gemini-2.5-flash"
}
```

The bank was created with three tuned missions (full text in
`bank-config.json`):

- **`retain_mission`** — extract concrete writing rules from human feedback
  (tone, structure, voice, taboo, audience, CTA, formatting). Ignore the post
  content; only extract durable style guidance.
- **`observations_mission`** — synthesize extracted rules into a coherent,
  deduplicated style guide. Newer rule wins on conflict.
- **`reflect_mission`** — return a structured style guide a writer can follow.

The mental model `marketing-writing-guidelines` was created **empty** with
`refresh_after_consolidation: true` and **no tags** (important — see Gotchas).

## The skill

`SKILL.md` was authored by Hermes itself (I prompted Hermes as the builder; it
wrote the file via its `file` toolset). Full file in `SKILL.md`. The
load-bearing line:

```
curl -s http://localhost:9177/v1/default/banks/marketing-manager/mental-models/marketing-writing-guidelines
```

Skill instructs Hermes to parse the JSON `content` field, fall back to asking
the user when empty, and otherwise write strictly to the returned guide. It
**never changes** across the entire demo.

## The conversation

A single Hermes session resumed across 9 turns with `--continue`.
4 turns deliver style feedback; 4 turns request posts; 1 final
no-guidance stress test.

| Turn | Type | What happened |
|------|------|---------------|
| T0 | baseline | Mental model returns *"I do not have any information..."* |
| T1 | request | "LinkedIn post: Maya Lin joining as VP Eng" → skill curls empty MM, **asks user for guidance** (correct fallback) |
| T2 | feedback | I deliver 9 foundational rules (tone, audience, length, signature, banned words, no emojis/hashtags, closing question, etc.) + redo |
| T3 | request | "Lumen launch post" → skill curls **populated** MM, applies the rules |
| T4 | feedback | 3 corrections (signature placement, element order, concrete metric for product posts) + redo |
| T5 | request | "Hindsight 1000 GitHub stars" → curls updated MM, applies T2+T4 rules |
| T6 | feedback | 3 more rules (no "just", milestone-post structure, no thanks → name community actions) + redo |
| T7 | request | "Tuesday cloud-cost webinar teaser" |
| T8 | feedback | 4 more rules (date on own line, speaker names+titles, digits not words, banned: "tighten"/"spot") + redo |
| T9 | stress test | "250 paying customers post — apply everything you know, don't ask me anything" |

## What the mental model looked like at each stage

Snapshots are in `mm-T0-empty.json`, `mm-T2.md`, `mm-T4.md`, `mm-T8.md`,
`mm-T9-final.json` (with the original JSON also kept for the curl
verification).

**T0** — empty:
> *I do not have any information about the current writing style, tone,
> structure, voice, or do/don't rules for drafting marketing posts.*

**T2** — after first feedback batch (~10 rules synthesized into a structured
style guide).

**T4** — adds signature/order/metric rules.

**T8** — final consolidated guide with all 19 observation-derived rules
organized into Tone, Style, Structure (with sub-sections for Milestone /
Product / Webinar posts), and a clean Do / Don't list.

The same `curl` command, called 5 different times across the conversation,
returned 5 different responses — each strictly richer than the last.

## The T9 stress test

Final post produced with no in-message guidance, just the curl response. It
satisfied every accumulated rule:

```
Agent memory is moving into production, not staying in experiments.

Hindsight reached 250 paying customers in its first year. The mix is 60%
startups and 40% mid-market teams, which says builders want memory that
survives real work, not notebook demos.

The community broke it, improved it, opened PRs, and filed issues.

— the team

What would you want an agent memory platform to remember first?
```

Rules satisfied (non-exhaustive): provocative claim → metric in 2nd sentence
(milestone rule), no "just", no buzzwords, no emojis/hashtags, no I/we,
"— the team" on own line at end, closing question on own line after
signature, names community actions instead of explicit thanks, digits not
words, target audience = technical leaders.

The skill text never changed once between T0 and T9.

## Final stats

```
total observations: 19
total world facts: 26
total documents:    9
mental model content length: ~5000 chars (vs 130 chars at T0)
mental model refreshed after each post-feedback consolidation cycle
```

## What this demo proves

1. **The "self-improving skill" pattern works on stock Hindsight today.** No
   schema changes, no new entity types, no Git integration. Skill = curl +
   fallback. Mental model = the actual evolving content.

2. **The whole thing is 1 SKILL.md (52 lines, written by Hermes itself), 1
   bank with 3 tuned missions, 1 mental model with `refresh_after_consolidation:
   true`, and `retain_async: false` so the demo isn't waiting on background
   jobs.** No code outside Hindsight.

3. **The retain → consolidate → refresh chain runs unattended.** I never called
   `/retain`, `/consolidate`, or `/refresh` directly during the conversation
   (one manual refresh after fixing the tag issue, see Gotchas). All updates
   happened via Hermes's standard auto-retain hook.

4. **The skill file is portable.** It survives a model upgrade, a harness
   swap, an env wipe — anything that touches the agent runtime but leaves
   Hindsight's bank intact. The "learning" lives in the bank, not in the
   skill prompt, and the bank can be exported / migrated with the standard
   `/export` endpoint.

5. **Hindsight is doing the work that a `feedback.md` + cron job could not
   reasonably replicate at this point:** entity-aware fact dedup across
   turns, observation consolidation that contradicts older rules (newer
   wins), automatic refresh trigger after consolidation, structured retrieval
   for the reflect call that builds the guide. The whole pipeline is
   transactional, observable, and didn't require us to write any glue code.

## Gotchas hit during the demo (worth fixing in product)

### 1. `find_dotenv(usecwd=True, override=True)` in `hindsight_api/config.py:18`

The hindsight-api process walks UPWARDS from the daemon's cwd looking for a
`.env` file, and `override=True` makes it beat any explicit env vars set by
the daemon manager. If you launch the daemon from a worktree that has its own
`.env` with `HINDSIGHT_API_LLM_PROVIDER=...` (e.g. for benchmarks), that
**silently overrides** what was carefully set in `~/.hindsight/profiles/<name>.env`.

**Symptom we hit:** The hermes profile env said gemini, but the daemon
crashed during startup trying to verify `openai/gpt-5-mini` against the OpenAI
API. The bad model was set in `hindsight-wt2/.env` (a dev worktree) which
`find_dotenv` picked up via cwd traversal.

**Workaround for this demo:** start the daemon from `/tmp` so there's no
parent `.env`. Subsequent `hindsight-embed` commands also need to be run from
a clean cwd.

**Fix idea:** either use `override=False` (so explicit env vars win), or
restrict `find_dotenv` to a fixed location like `~/.hindsight/.env` or the
profile dir. The current behavior makes the profile system unreliable
whenever a developer has dev worktrees nearby.

### 2. `refresh_after_consolidation` is gated by tag overlap

`consolidator.py:_trigger_mental_model_refreshes` only refreshes mental
models whose tags overlap with the consolidated memories' tags. If the
mental model has tags `["skill", "marketing"]` but auto-retain stores
memories with NO tags (which is what hermes-plugin does by default), the
trigger silently does nothing — the mental model just sits stale forever.

**Symptom we hit:** First consolidation completed but the MM never
refreshed. Discovered by reading the code — there were no log lines about
"Triggered refresh" because the SQL query returned 0 rows.

**Workaround for this demo:** removed the tags from the mental model with a
`PATCH /mental-models/...`. Then auto-refresh worked on every cycle.

**Fix idea:** either log a warning when an "auto-refresh" model is skipped
due to tag mismatch, or document the requirement clearly in the mental
model creation API. Right now this is a silent footgun for anyone trying to
build the skill-via-mental-model pattern with tags.

### 3. `bank_mission` / `bank_retain_mission` in hermes config are dead

The hindsight hermes plugin reads `bank_mission` and `bank_retain_mission`
from `~/.hermes/hindsight/config.json` into `self._bank_mission` /
`self._bank_retain_mission`, but **never sends them to Hindsight**. The bank
is created via auto-retain with no missions. To get tuned missions you have
to PUT to `/v1/default/banks/{bank_id}` directly with the API, which is
what this demo does.

**Fix idea:** the plugin should call `update_bank_config` with the configured
missions on initialization (or on bank creation).

### 4. The hermes integration docs say port 9077; the actual default is 9177

`hindsight-docs/docs-integrations/hermes.md:107` documents `apiPort: 9077`
as the default. The actual code in
`/Users/nicoloboschi/.hermes/hermes-agent/plugins/memory/hindsight/__init__.py:37`
defaults to `8888`, and the hermes profile registers as `:9177` in
`~/.hindsight/profiles/metadata.json`. Three different numbers in three
different places.

**Fix idea:** pick one and document it. The skill in this demo has `9177`
hardcoded because that's what the running daemon listens on; if the port
changes the SKILL.md breaks silently.

## Reproducing this run

Prerequisites: hermes 0.8.0+ with hindsight plugin installed, a Gemini API key
in `~/.hermes/.env` as `HINDSIGHT_LLM_API_KEY`, daemon at `:9177`.

```bash
# 1) configure hermes for marketing bank
cp ~/.hermes/hindsight/config.json ~/.hermes/hindsight/config.json.bak
cat > ~/.hermes/hindsight/config.json <<EOF
{
  "mode": "local_embedded",
  "bank_id": "marketing-manager",
  "retain_async": false,
  "llm_provider": "gemini",
  "llm_model": "gemini-2.5-flash"
}
EOF

# 2) start daemon FROM A CLEAN CWD (see Gotcha #1)
cd /tmp && hindsight-embed -p hermes daemon start

# 3) create bank with tuned missions
curl -X PUT http://localhost:9177/v1/default/banks/marketing-manager \
  -H "Content-Type: application/json" \
  -d @bank-config.json

# 4) create empty mental model — NO TAGS (see Gotcha #2)
curl -X POST http://localhost:9177/v1/default/banks/marketing-manager/mental-models \
  -H "Content-Type: application/json" \
  -d '{
    "id": "marketing-writing-guidelines",
    "name": "Marketing Writing Guidelines",
    "source_query": "What are the current writing style, tone, structure, voice, and do/dont rules I should follow when drafting marketing posts on behalf of this human?",
    "max_tokens": 2048,
    "trigger": {"refresh_after_consolidation": true}
  }'

# 5) ask hermes to author the skill
cd /tmp && hermes chat -Q --yolo -q "$(cat author-skill-prompt.txt)"

# 6) run the conversation
cd /tmp && hermes chat -Q --yolo --skills marketing-writer -q "$(cat turn-1.txt)"
cd /tmp && hermes chat -Q --yolo -c -q "$(cat turn-2.txt)"
# ... continue with --continue
```

## Files in this directory

- `README.md` — this file
- `SKILL.md` — the skill Hermes wrote (52 lines, never modified)
- `bank-config.json` — the three tuned missions
- `mm-T0-empty.json` — mental model when empty
- `mm-T2.md`, `mm-T4.md`, `mm-T8.md` — mental model content snapshots
- `mm-T9-final.json` — final state after stress test
- `observations-final.json` — all 19 consolidated observations
- `stats-final.json` — bank stats at end of run
- `transcript.md` — full turn-by-turn conversation with all hermes responses
