# Hermes Marketing-Writer Demo — V2 (via meta-skill)

Same end-to-end demo as `../hermes-marketing/`, but setup happens **entirely
through the `hindsight-skill-builder` meta-skill** — no manual API calls, no
hand-written SKILL.md, no direct bank configuration. The "user" says "install a
marketing skill" and the agent handles everything with explicit approval
checkpoints.

## What's different from V1

V1 setup (yesterday): I manually PUT the bank config with tuned missions, POST'd the
mental model, and separately prompted Hermes to author the SKILL.md via file tools.
Four manual steps, one of them with hand-crafted prompts.

V2 setup (this run): one sentence — *"I'm a marketing manager. Install a new
Hindsight-backed skill that helps me write marketing posts (LinkedIn, X, blog
teasers, newsletters, announcements). Walk me through the setup."* Then four
approvals ("yes that URL", "yes that bank", "yes that mental model", "yes
proceed") and the whole pipeline is configured.

The meta-skill itself is at `skills/hindsight-skill-builder/SKILL.md` in the
main repo.

## Setup conversation (5 turns)

| Turn | Who | What |
|------|------|------|
| A1 | User | "Install a marketing skill. Walk me through setup." |
| A1 | Agent | Loaded meta-skill. Probed `env`, `~/.hindsight/config`, well-known ports. Found `http://localhost:9177` healthy. **Paused for approval.** |
| A2 | User | "Yes, use that URL." |
| A2 | Agent | Listed existing banks (`hermes`). Reasoned: "marketing feedback will pollute the hermes bank, create a new one." Proposed `marketing-writing` with three tuned missions. **Paused for approval.** |
| A3 | User | "Yes, create the bank." |
| A3 | Agent | PUT the bank config, verified via `/config`. Proposed mental model spec (id, name, source_query covering all channels, refresh_after_consolidation=true, no tags — followed the gotcha warning). **Paused for approval.** |
| A4 | User | "Yes, create the mental model." |
| A4 | Agent | POST'd the mental model, wrote `~/.hermes/skills/marketing/marketing-post-writer/SKILL.md`, confirmed with a summary. |

Five turns of dialogue total. At each decision the agent proposed, explained
the reasoning, and waited for a thumbs-up. No silent execution.

## The configuration the agent chose

Without any hand-holding beyond the user's one-sentence request, the agent
designed:

**Bank name:** `marketing-writing`

**Retain mission** *(agent-authored)*:
> Extract concrete, durable writing rules the user gives about marketing content. Capture: tone, voice, audience, position/benefit framing, length, structure, formatting, hook style, CTA style, emoji/hashtag usage, channel-specific differences (LinkedIn, X, blog teaser, newsletter, announcement), taboo phrases, brand terms to use/avoid, and explicit corrections to prior drafts. Each fact must be a single actionable rule. Ignore the post topic or campaign details unless they change the writing approach.

**Observations mission** *(agent-authored)*:
> Synthesize extracted rules into a coherent, deduplicated marketing writing playbook. Group rules by channel and by theme (tone, structure, hook, CTA, formatting, voice, taboo, audience). When a new rule contradicts an older one, the newer rule wins and the older rule should be marked stale.

**Reflect mission** *(agent-authored)*:
> When asked for current marketing writing guidance, return a clear, structured style guide that the writer can follow immediately for drafting marketing posts across the supported channels.

**Mental model:** `marketing-post-writer`
**Source query** *(agent-authored)*:
> "What are the current writing style, tone, structure, voice, and do/don't rules I should follow when drafting LinkedIn posts, X posts, blog teasers, newsletters, and announcements on behalf of this user?"

**Skill description** *(agent-authored)*:
> "Use this skill whenever the user asks for LinkedIn posts, X posts, blog teasers, newsletters, announcements, or similar marketing copy. Fetches live guidance from Hindsight and evolves with feedback."

Compare that to the hand-crafted V1 missions in `../hermes-marketing/bank-config.json`
— the agent-authored versions are **noticeably more complete**. The V1 retain mission
didn't enumerate channels; V2 does. The V1 observations mission didn't mention
grouping by channel; V2 does. This isn't magic — it's the worked example
+ mission-writing principles in the meta-skill instructions doing their job.

## Marketing conversation (turns 1–9)

Same prompts as yesterday's V1 demo (`../hermes-marketing/transcript.md`),
resumed in a single Hermes session `20260410_112606_aa95ff`.

| Turn | Type | Verdict |
|------|------|---------|
| T1 | Request: Maya Lin VP Eng post | Skill curled empty MM, **fell back to asking user** for tone/CTA/length. ✓ |
| T2 | Feedback: 9 foundational rules + redo | Applied rules; "the team" placed awkwardly (same as yesterday). |
| T4 | Feedback: 3 corrections (signature, order, metric) + redo | Applied corrections cleanly. |
| T5 | Request: 1000 GitHub stars milestone | Curled populated MM, applied T2+T4 rules. |
| T6 | Feedback: 3 more rules (no "just", milestone pattern, no thanks) + redo | Applied all three. |
| T7 | Request: Tuesday webinar teaser | Applied all accumulated rules; speaker names not yet known. |
| T8 | Feedback: 4 more rules + redo with speaker names | Ran `date -v+4d` to get real Tuesday date, applied all rules. |
| T9 | Stress test: 250 customers, "apply everything you know" | **All rules satisfied** without in-message guidance. |

### T9 output

```
Agent memory is no longer a side project.

Hindsight reached 250 paying customers in its first year. The mix is 60%
startups and 40% mid-market teams, which says the need is real across the
stack.

Persistent memory is moving from nice-to-have to core infrastructure.

— the team

What's the biggest gap you still see in agent memory?
```

Rules satisfied: provocative claim first → metric in sentence 2 (milestone
rule), no "just" (stripped from the user prompt which said "we just hit"),
digits (250, 60%, 40%), no buzzwords/emojis/hashtags, no I/we,
"— the team" on own line at end, closing question on own line after
signature, within length budget, technical-audience framing. Same verdict as
yesterday's V1 T9.

## Final stats

| Metric | V1 (manual) | V2 (meta-skill) |
|---|---|---|
| Bank name | `marketing-manager` | `marketing-writing` |
| Mental model id | `marketing-writing-guidelines` | `marketing-post-writer` |
| Observations at end | 19 | 13 |
| World facts at end | 26 | 20 |
| MM content length | ~5000 chars | 5351 chars |
| SKILL.md changed during run? | No (MD5 verified) | No (MD5 verified) |
| Setup steps for the user | 4 manual API calls + authoring prompt | 1 prompt + 4 approvals |

V2 has slightly fewer observations because I ran 7 feedback/request turns
vs 9 in V1 (I skipped T3 and T7-as-retry), but the mental model content is
comparably rich and covers all the same rule categories.

## What this run proves

The meta-skill reproduces the V1 setup quality without any manual API calls,
and matches the V1 runtime behavior end-to-end. A customer who installs the
meta-skill from the `skills/` directory can now build their own
self-improving skills conversationally:

```
User: "Install a Hindsight-backed skill for customer support responses."
Agent: [meta-skill activates, proposes, asks for approval at each decision]
User: [approves]
Agent: [skill is live, feedback loop begins on next interaction]
```

The meta-skill is the only thing the user has to install manually. Every
subsequent skill is built through a conversation.

## Files

- `README.md` — this file
- `SKILL.md` — the `marketing-post-writer` skill the meta-skill wrote (MD5: `f67e7cfccf46a1595e79dca9efb6006d`, unchanged across the run)
- `bank-config.json` — the bank config with agent-authored missions (as persisted in Hindsight)
- `mm-T0-empty.json` — mental model when empty
- `mm-T8-partial.json` / `mm-final.json` — mental model after T8 feedback batch
- `mm-final.md` — clean markdown extract of the final MM content
- `observations-final.json` — all 13 consolidated observations
- `stats-final.json` — bank stats at end of run

## Bug status from V1

The same three Hindsight bugs I hit yesterday are still latent here. The
meta-skill **worked around** them all:

1. **`find_dotenv` cwd contamination** — meta-skill runs the daemon bootstrap via the existing process; I had to remember to run hermes from `/tmp`. The meta-skill itself doesn't address this (it's a Hindsight-side bug).
2. **Tag-gated auto-refresh** — meta-skill's Step 3 explicitly instructs the agent to create mental models **with no tags** and includes a warning explaining why. Worked as designed: refresh fired on every consolidation cycle.
3. **Dead `bank_mission`/`bank_retain_mission` in hermes plugin config** — meta-skill bypasses these entirely by PUTing the bank config directly, which is what it should do anyway.

Fix priority remains: #1 is the worst because it silently breaks daemon
startup in any developer environment with a sibling `.env`.
