---
name: marketing-agent-seed
description: First-run setup instructions for the marketing agent profile. Invoked once immediately after provisioning to install the self-learning skills declared in agent.yaml. Use this skill when the user asks you to "set up", "provision", "seed", or "finish installing" the marketing agent.
---

# Marketing Agent — First-Run Setup

You are running in a fresh hermes profile that was just created by the `hindsight-agent` CLI. The profile has:

- The Hindsight plugin installed and configured (URL, bank id, optional key)
- The `hindsight-skill-builder` meta-skill available
- This seed skill

Your job right now is to **install the self-learning skills declared in `agent.yaml`** by invoking the skill-builder once per skill. After that, the agent is ready for normal use and this seed skill is never needed again.

## Self-learning skills to install

Install **one self-learning skill** with these exact parameters:

- **Skill id:** `marketing-post-writer`
- **Skill name:** Marketing Post Writer
- **Description (for the SKILL.md frontmatter, used by the harness for auto-match):**
  > Use this skill whenever the user asks for any marketing copy — LinkedIn post, X post, thread, blog teaser, newsletter blurb, announcement, launch copy, or promotional caption. Fetches the latest writing guidelines from Hindsight before drafting and asks the user for tone / audience / length / constraints when no guidance exists yet.
- **Source query (the question the mental model answers at fetch time):**
  > What are the current writing style, tone, structure, voice, and do/don't rules I should follow when drafting marketing posts on behalf of this user? Include channel-specific rules for LinkedIn, X, blog teasers, newsletters, and announcements when they exist.
- **refresh_after_consolidation:** true
- **tags:** none

## How to do it

1. Load the `hindsight-skill-builder` skill (it's already installed in this profile's skills directory).
2. Run through its steps **exactly as it instructs** — read the harness plugin config, verify with `hindsight health`, write the shared env file, then create the mental model and the SKILL.md file. The skill-builder will ask for approval at a few gates; approve with the parameters above (the skill id, description, and source_query are fixed by this seed and should not be re-designed).
3. When the skill-builder finishes the `marketing-post-writer` installation, confirm that:
   - `~/.hindsight/learning-skill.env` exists with `HINDSIGHT_BANK_ID` set
   - `hindsight mental-model get "$HINDSIGHT_BANK_ID" marketing-post-writer --output json` returns a valid mental model
   - The new skill file exists in the profile's skills directory
4. Tell the user: *"Your marketing agent is ready. Ask me for a LinkedIn post (or any marketing copy) and give feedback as we go — the skill will evolve."*

## Do not

- Do not create a new bank — the skill-builder binds to the bank the harness plugin is already configured to use, and that's the only bank auto-retain will ever write to.
- Do not set tags on the mental model.
- Do not write any marketing copy yet. This turn is setup only.
- Do not ask the user to re-confirm the skill id, description, or source_query — they are fixed by this seed. You only need user approval for anything the skill-builder itself asks about (harness config, env file write, final SKILL.md path).
