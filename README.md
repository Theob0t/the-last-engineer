# The Last Engineer

**A daily read for engineers rooting for the robots.**

→ [thelastengineer.com](https://theob0t.github.io/the-last-engineer/)

---

## What is this?

A daily AI newsletter — and an experiment in agentic self-improvement.

Every morning, an autonomous agent scans 35+ official AI blogs (Anthropic, OpenAI, DeepMind, Cursor, METR, and more), decides what's worth reading, and delivers it to your inbox. No human editor. No curation team. Just an AI making editorial decisions at 7 AM UTC.

Two tracks, zero noise:
- **⚡ Vibe Coding** — workflow-changing releases, tool deep-dives, agentic dev tools
- **🔬 Capabilities & Alignment** — evals, interpretability, safety research, autonomous capability benchmarks

---

## The Experiment

This isn't just a newsletter. It's a live experiment in **agentic editorial intelligence**.

The agent doesn't just curate — it learns. After each issue, it reflects on its own picks, updates its editorial memory, and refines its selection criteria. Over time, reader feedback (👍/👎 on each article) is aggregated into engagement signals that feed back into the next curation cycle.

The loop:

```
fetch → deduplicate → curate → publish → reflect → update memory → commit
                                            ↑
                              reader engagement signals
```

This is an early attempt at **RLHF-style feedback** applied to editorial curation:
- The agent has a persistent `editorial_memory.md` that evolves with each run
- Reader votes are aggregated and injected into the system prompt as preference signals
- A `curation_log.md` tracks every editorial decision the agent makes, building an interpretable trace of how its taste develops
- The full history is version-controlled in git — every change to the agent's editorial guidelines is auditable

**The question we're trying to answer:** can an AI agent develop a genuinely good editorial taste through self-reflection and human feedback — with no human in the loop after setup?

---

## How it works

```
GitHub Actions (7 AM UTC daily) → scripts/run.py
  ├── Fetch 35+ RSS feeds
  ├── Deduplicate (URL hashing, persistent across runs)
  ├── Curate with Claude (system prompt + editorial memory + engagement signals)
  ├── Render email (inline CSS) + web issue (Tailwind)
  ├── Publish issue → issues/YYYY-MM-DD.html
  ├── Update archive + landing page
  ├── Reflect → update editorial_memory.md + append to curation_log.md
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

## Setup

**1. Fork this repo**

**2. Add GitHub secrets** — Settings → Secrets and Variables → Actions:
| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | [Generate here](https://myaccount.google.com/apppasswords) |
| `RECIPIENT_EMAILS` | Comma-separated list (optional, or use Google Sheet) |
| `GOOGLE_SHEET_CSV_URL` | Published CSV URL of your subscribers sheet |
| `GOOGLE_VOTES_CSV_URL` | Published CSV URL of your votes tab |

**3. Enable GitHub Pages** — Settings → Pages → Deploy from branch `main`, root `/`

**4. Done.** Trigger manually from the Actions tab or wait for 7 AM UTC.

---

## Local dev

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in keys
cd scripts
python run.py --preview     # preview email in browser
python run.py --test-email  # send test email
python run.py --test-web    # publish test issue to site
python run.py --push        # full run + git push
python run.py --rebuild-archive  # rebuild archive from existing issues
```

---

## Cost

| Service | Cost |
|---|---|
| GitHub Actions | Free (2,000 min/month) |
| GitHub Pages | Free |
| Gmail SMTP | Free |
| Claude API | ~$1/month |

**Total: ~$1/month**
