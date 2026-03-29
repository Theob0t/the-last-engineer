# The Last Engineer

**A daily read for engineers rooting for the robots.**

→ [theob0t.github.io/the-last-engineer](https://theob0t.github.io/the-last-engineer/)

---

## What is this?

A daily newsletter curated by an AI editor with a tiered memory system. Every morning it scans 40+ official AI blogs, selects what matters, writes an editorial explaining its thinking, and delivers it to your inbox.

Two sections:
- **⚡ Vibe Coding** — AI dev tool updates, vibe coding news, real builder use cases, MCP integrations, workflows
- **🧠 The Big Picture** — AI futures, societal impact, deep analysis essays, AI economy, safety in the philosophical sense

Three vibe tags: `🛠 builder tools` · `🧪 deep analysis` · `⚖️ AI futures`

---

## The Experiment

This is a live experiment in **tiered agent memory architecture**, inspired by [Generative Agents](https://arxiv.org/abs/2304.03442) (Park et al.) and [MemGPT/Letta](https://arxiv.org/abs/2310.08560).

The agent has three memory tiers:

```
┌─────────────────────────────────────────────┐
│  SEMANTIC MEMORY (persistent identity)       │
│  memory/identity.md                          │
│  Updated: weekly (consolidation)             │
│  Contains: values, beliefs, philosophy       │
└──────────────────────┬──────────────────────┘
                       │ weekly consolidation
┌──────────────────────▼──────────────────────┐
│  EPISODIC MEMORY (daily journal)             │
│  memory/journal.json                         │
│  Updated: daily                              │
│  Contains: themes, surprises, observations,  │
│  per-article reasoning                       │
│  Rolling: 7 days → consolidated → purged     │
└──────────────────────┬──────────────────────┘
                       │ assembled per-run
┌──────────────────────▼──────────────────────┐
│  WORKING MEMORY (ephemeral)                  │
│  Not persisted                               │
│  Contains: today's articles, identity,       │
│  recent journal, dedup, vote signals         │
└─────────────────────────────────────────────┘
```

**Daily**: The agent curates articles, writes an editorial explaining its picks (the "Editor's Note"), and logs a journal entry with themes, surprises, and observations.

**Weekly**: After 7 journal entries, the agent consolidates episodic memory into identity updates. Its beliefs, values, and philosophy evolve based on accumulated observations + reader vote patterns.

**The question:** can an AI agent develop genuine editorial taste through structured memory consolidation and community feedback, with no human in the loop?

---

## Pipeline

```
fetch 40+ feeds → dedup (URL hash + 7-day semantic) → curate with Claude
    → write editorial + journal entry → publish web + email
    → [every 7 days: consolidate journal → update identity]
    → git push → GitHub Pages
```

Reader votes (👍/👎 on each article) feed back into:
1. The curation prompt as engagement signals
2. The weekly consolidation as reader preference data

---

## How to participate

**Read and vote** — every article has 👍/👎 buttons. Your votes shape the agent's identity during weekly consolidation.

**Watch the agent think** — the [Agent page](https://theob0t.github.io/the-last-engineer/agent.html) shows the agent's current identity, journal, and links to all source files on GitHub.

**Read the source files:**
- [`memory/identity.md`](scripts/memory/identity.md) — the agent's persistent self
- [`memory/journal.json`](scripts/memory/journal.json) — 7-day episodic memory
- [`memory/daily_log.json`](scripts/memory/daily_log.json) — structured metrics + full audit trail
- [`curation_log.md`](scripts/curation_log.md) — editorial decisions + weekly consolidation notes

**Fork and run your own** — see below.

---

## Key files

```
scripts/
├── run.py                      ← the entire pipeline (one file)
├── curation_log.md             ← daily + weekly editorial decisions
├── editorial_memory.md         ← legacy (kept as backup)
├── .seen_hashes.json           ← URL dedup state
└── memory/
    ├── identity.md             ← agent's persistent self (values, beliefs, philosophy)
    ├── journal.json            ← 7-day rolling episodic memory
    ├── daily_log.json          ← structured metrics + audit trail
    └── recent_summaries.json   ← 7-day semantic dedup
```

---

## Fork and run your own

**1. Fork this repo**

**2. Add GitHub secrets** — Settings → Secrets and Variables → Actions:
| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | [Generate here](https://myaccount.google.com/apppasswords) |
| `RECIPIENT_EMAILS` | Comma-separated list (optional) |
| `GOOGLE_SHEET_CSV_URL` | Published CSV URL of your subscribers sheet |
| `GOOGLE_VOTES_CSV_URL` | Published CSV URL of your votes tab |

**3. Enable GitHub Pages** — Settings → Pages → Deploy from branch `main`, root `/`

**4. Done.** Trigger manually from the Actions tab or wait for 7 AM UTC.

Cost: **~$1/month** (Claude API only — GitHub Actions, Pages, and Gmail are free).
