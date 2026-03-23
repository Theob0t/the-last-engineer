# The Last Engineer

**A daily read for engineers rooting for the robots.**

→ [theob0t.github.io/the-last-engineer](https://theob0t.github.io/the-last-engineer/)

---

## What is this?

A daily newsletter about autonomous AI agents — and a live experiment in agentic self-improvement.

Every morning, an autonomous agent scans 35+ official AI blogs (Anthropic, OpenAI, DeepMind, METR, Cursor, and more), decides what's worth reading, and delivers it to your inbox. No human editor. No curation team. Just an AI making editorial decisions at 7 AM UTC.

Three types of content, nothing else:
- **🛠 agentic tools** — frameworks, products, MCP integrations, coding agents you can use this week
- **🧪 agent research** — benchmarks, architectures, capabilities, long-horizon task research
- **⚖️ alignment research** — safety, red-teaming, oversight, corrigibility — agents only

---

## The Experiment

This isn't just a newsletter. It's a live experiment in **agentic editorial intelligence**.

The agent doesn't just curate — it learns. After each issue, it reflects on its own picks, updates its editorial memory, and refines its selection criteria. Reader feedback (👍/👎 on each article) is aggregated into engagement signals that feed back into the next curation cycle.

```
fetch → deduplicate → curate → publish → reflect → update memory → commit
                                            ↑
                              reader engagement signals (👍/👎)
```

This is an early attempt at **RLHF-style feedback** applied to editorial curation:
- `editorial_memory.md` — the agent's evolving editorial guidelines, updated daily
- `curation_log.md` — an interpretable trace of every editorial decision the agent makes
- Reader votes are aggregated and injected into Claude's system prompt as preference signals
- Everything is version-controlled — the agent's taste evolution is fully auditable in git history

**The question:** can an AI agent develop genuinely good editorial taste through self-reflection and human feedback, with no human in the loop?

---

## How to participate

**Read and vote** — every article on the web issues has a 👍/👎. Your votes directly influence what the agent picks tomorrow.

**Watch the agent learn** — `editorial_memory.md` and `curation_log.md` are updated daily and committed to this repo. You can read the agent's reasoning and see how its editorial guidelines change over time.

**Fork and run your own** — this is fully open source. Fork the repo, point it at different feeds, change the editorial mandate, and run your own agentic newsletter for ~$1/month.

**Open issues** — if you think the agent made a bad call (wrong pick, missed something important), open a GitHub issue. We may use community feedback to manually correct the editorial memory.

---

## How it works

```
GitHub Actions (7 AM UTC daily) → scripts/run.py
  ├── Fetch 35+ RSS feeds
  ├── Deduplicate (URL hashing, persistent across runs)
  ├── Curate with Claude (system prompt + editorial memory + engagement signals)
  ├── Render email + web issue
  ├── Publish → issues/YYYY-MM-DD.html + update landing page
  ├── Reflect → update editorial_memory.md + curation_log.md
  ├── Git push → GitHub Pages rebuilds
  └── Send email via Gmail SMTP
```

**Key files:**
```
scripts/
├── run.py                  ← the entire pipeline (one file)
├── editorial_memory.md     ← agent's evolving editorial guidelines
├── curation_log.md         ← daily trace of editorial decisions
└── .seen_hashes.json       ← dedup state (persisted in git)
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
