# The Last Engineer

**A daily read for engineers rooting for the robots.**

One Python script scans 35+ official AI blogs, Claude curates what's novel/useful/cool, publishes to GitHub Pages, and emails you via Gmail. Runs daily via GitHub Actions — no server needed.

## How it works

```
GitHub Actions (7 AM daily) → run.py
  ├── Fetch 35+ RSS feeds (official AI blogs)
  ├── Deduplicate
  ├── Claude curates (novel / useful / cool)
  ├── Generate email (dark editorial HTML)
  ├── Generate web issue → site/issues/YYYY-MM-DD.html
  ├── Update archive + landing page
  ├── Git push → GitHub Pages rebuilds
  └── Send email via Gmail
```

## Setup

**1. Fork or clone this repo**

**2. Add secrets** — Go to repo Settings → Secrets and Variables → Actions → New Repository Secret:
- `ANTHROPIC_API_KEY` — your Claude API key
- `GMAIL_ADDRESS` — your Gmail address
- `GMAIL_APP_PASSWORD` — generate at https://myaccount.google.com/apppasswords
- `RECIPIENT_EMAILS` — comma-separated list (e.g. `you@gmail.com,friend@email.com`)

**3. Enable GitHub Pages** — Settings → Pages → Source: Deploy from branch `main`, folder `/site`

**4. Done.** The GitHub Action runs daily at 7 AM UTC. You can also trigger it manually from the Actions tab.

## Files

```
the-last-engineer/
├── .github/workflows/newsletter.yml  ← GitHub Actions (daily trigger)
├── scripts/
│   └── run.py                         ← THE one script that does everything
├── site/                              ← GitHub Pages root
│   ├── index.html                     ← Landing page
│   └── issues/
│       ├── index.html                 ← Archive page
│       └── 2026-03-23.html            ← Daily issues (auto-generated)
└── requirements.txt
```

## Local dev

```bash
pip install -r requirements.txt
cp .env.example .env                   # fill in keys
cd scripts
python run.py --preview                # preview email
python run.py --test-email             # send test
python run.py --test-web               # publish test issue to site
python run.py                          # full run (no push)
python run.py --push                   # full run + git push
python run.py --rebuild-archive        # rebuild archive from existing issues
```

## Cost

- GitHub Actions: free (2,000 min/month)
- GitHub Pages: free
- Gmail: free
- Claude API: ~$1/month

Total: **~$1/month**
