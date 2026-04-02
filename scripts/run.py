"""
The Last Engineer — Daily AI Newsletter
=========================================
One script does everything:
  fetch feeds → curate with Claude → render email → publish web issue →
  update archive + landing page → git push → send email via Gmail

Usage:
    python run.py                    # Full run: curate + publish + email
    python run.py --preview          # Preview email, no send/publish
    python run.py --test-email       # Send test email
    python run.py --test-web         # Publish test issue to site
    python run.py --push             # Full run + git push to GitHub Pages
    python run.py --rebuild-archive  # Rebuild archive from existing issues

Requires: .env file (see .env.example)
"""

import os
import json
import re
import hashlib
import smtplib
import subprocess
import datetime as dt
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import feedparser
import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAILS = [
    e.strip() for e in os.getenv("RECIPIENT_EMAILS", "").split(",") if e.strip()
]
GOOGLE_SHEET_CSV_URL = os.getenv("GOOGLE_SHEET_CSV_URL", "")
GOOGLE_VOTES_CSV_URL = os.getenv("GOOGLE_VOTES_CSV_URL", "")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycbz1UMvwEJWxwM0FifuzCnR6vt9CEWthhZ7E4kWjMBBMBKv5taY-urN6pwKHMztPkexE/exec")

MODEL = "claude-sonnet-4-20250514"
MAX_ARTICLES = 100
MAX_ITEMS_PER_SECTION = 12
NEWSLETTER_NAME = "The Last Engineer"
LAUNCH_DATE = dt.date(2026, 3, 22)

SCRIPT_DIR = Path(__file__).parent
SEEN_FILE = SCRIPT_DIR / ".seen_hashes.json"
SITE_DIR = SCRIPT_DIR.parent
ISSUES_DIR = SITE_DIR / "issues"
RECENT_SUMMARIES_FILE = SCRIPT_DIR / "memory" / "recent_summaries.json"
IDENTITY_FILE = SCRIPT_DIR / "memory" / "identity.md"
JOURNAL_FILE = SCRIPT_DIR / "memory" / "journal.json"
DAILY_LOG_FILE = SCRIPT_DIR / "memory" / "daily_log.json"

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str = ""
    published: str = ""

    @property
    def hash(self) -> str:
        return hashlib.md5(self.url.encode()).hexdigest()


# ---------------------------------------------------------------------------
# RSS Feeds — Official blogs only
# ---------------------------------------------------------------------------

OLSHANSK = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds"

RSS_FEEDS = {
    # ═══ Major AI Labs ═══════════════════════════════════════════════
    "Anthropic News":              f"{OLSHANSK}/feed_anthropic_news.xml",
    "Anthropic Engineering":       f"{OLSHANSK}/feed_anthropic_engineering.xml",
    "Anthropic Research":          f"{OLSHANSK}/feed_anthropic_research.xml",
    "Anthropic Red Team":          f"{OLSHANSK}/feed_anthropic_red.xml",
    "Claude Blog":                 f"{OLSHANSK}/feed_claude.xml",
    "Claude Code Changelog":       f"{OLSHANSK}/feed_anthropic_changelog_claude_code.xml",
    "OpenAI Research":             f"{OLSHANSK}/feed_openai_research.xml",
    "OpenAI Blog":                 "https://openai.com/blog/rss.xml",
    "Google DeepMind":             "https://deepmind.google/blog/rss.xml",
    "Google Developers AI":        f"{OLSHANSK}/feed_google_ai.xml",
    "Meta AI":                     "https://ai.meta.com/blog/rss/",
    "xAI":                         f"{OLSHANSK}/feed_xainews.xml",
    "Mistral AI":                  "https://mistral.ai/feed.xml",

    # ═══ Vibe Coding Tools ═══════════════════════════════════════════
    "Cursor Blog":                 f"{OLSHANSK}/feed_cursor.xml",
    "Windsurf Blog":               f"{OLSHANSK}/feed_windsurf_blog.xml",
    "Windsurf Changelog":          f"{OLSHANSK}/feed_windsurf_changelog.xml",
    "Replit Blog":                 "https://blog.replit.com/feed.xml",
    "Vercel Blog":                 "https://vercel.com/atom",
    "Sourcegraph Blog":            "https://about.sourcegraph.com/blog/rss",
    "GitHub Blog":                 "https://github.blog/feed/",

    # ═══ Safety / Evals / Alignment ══════════════════════════════════
    "METR":                        "https://metr.org/blog/feed.xml",
    "ARC Evals":                   "https://evals.alignment.org/blog/feed.xml",
    "Alignment Forum":             "https://www.alignmentforum.org/feed.xml?view=community-rss",
    "LessWrong (high-karma)":      "https://www.lesswrong.com/feed.xml?view=community-rss&karmaThreshold=50",

    # ═══ Aggregators ═════════════════════════════════════════════════
    "TLDR AI":                     "https://bullrich.dev/tldr-rss/ai.rss",

    # ═══ AI Leader Blogs ═════════════════════════════════════════════
    "Dario Amodei":                "https://darioamodei.substack.com/feed",
    "Sam Altman":                  "http://blog.samaltman.com/posts.atom",
    "Sahaj Garg (Wispr)":          "https://sahajgarg.github.io/feed.xml",
    "Paul Graham":                 f"{OLSHANSK}/feed_paulgraham.xml",
    "Andrej Karpathy":             "https://karpathy.github.io/feed.xml",
    "Hamel Husain":                f"{OLSHANSK}/feed_hamel.xml",

    # ═══ Key Voices ══════════════════════════════════════════════════
    "Simon Willison":              "https://simonwillison.net/atom/everything/",
    "Lilian Weng":                 "https://lilianweng.github.io/index.xml",
    "Jack Clark (Import AI)":      "https://jack-clark.net/feed/",
    "Latent Space":                "https://www.latent.space/feed",
    "The Batch (deeplearning.ai)": "https://www.deeplearning.ai/the-batch/feed/",

    # ═══ Big Picture Voices ══════════════════════════════════════════
    "Gwern Branwen":               "https://gwern.net/feed",
    "Roon (roonscape)":            "https://www.roonscape.ai/feed",
    "Citrini Research":            "https://citriniresearch.com/feed",
    "Steve Yegge":                 "https://medium.com/feed/@steve-yegge",
}


# ---------------------------------------------------------------------------
# 1. FETCH
# ---------------------------------------------------------------------------

def fetch_rss(feed_name: str, feed_url: str, max_items: int = 8) -> list[Article]:
    articles = []
    try:
        resp = httpx.get(feed_url, timeout=15, follow_redirects=True)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:max_items]:
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:600] if hasattr(entry, "summary") else ""
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            articles.append(Article(
                title=entry.get("title", "Untitled"),
                url=entry.get("link", ""),
                source=feed_name,
                summary=summary,
                published=published,
            ))
    except Exception as e:
        print(f"  ⚠ {feed_name}: {e}")
    return articles


def fetch_all_feeds() -> list[Article]:
    all_articles = []
    for name, url in RSS_FEEDS.items():
        print(f"  📡 {name}")
        all_articles.extend(fetch_rss(name, url))
    return all_articles


# ---------------------------------------------------------------------------
# 2. DEDUP
# ---------------------------------------------------------------------------

def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()).get("hashes", []))
    return set()

def save_seen(hashes: set[str]):
    SEEN_FILE.write_text(json.dumps({"hashes": list(hashes)[-2000:]}))

def deduplicate(articles: list[Article]) -> list[Article]:
    seen = load_seen()
    fresh = [a for a in articles if a.hash not in seen]
    save_seen(seen | {a.hash for a in fresh})
    return fresh


# ---------------------------------------------------------------------------
# 2b. SEMANTIC DEDUP (7-day rolling memory)
# ---------------------------------------------------------------------------

def load_recent_summaries() -> list[dict]:
    if RECENT_SUMMARIES_FILE.exists():
        try:
            return json.loads(RECENT_SUMMARIES_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
    return []

def save_recent_summaries(entries: list[dict]):
    RECENT_SUMMARIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECENT_SUMMARIES_FILE.write_text(json.dumps(entries, indent=2))

def get_recent_stories_context() -> str:
    entries = load_recent_summaries()
    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    recent = [e for e in entries if e.get("date", "") >= cutoff]
    if not recent:
        return ""
    lines = ["These stories were already covered in the past 7 days. Do not select articles covering the same news even if from a different source:"]
    for e in recent:
        lines.append(f"- [{e.get('date','')}] {e.get('summary','')}")
    return "\n".join(lines)

def record_selected_summaries(digest: dict):
    entries = load_recent_summaries()
    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    entries = [e for e in entries if e.get("date", "") >= cutoff]
    today = dt.date.today().isoformat()
    for section in ("vibe_coding", "capabilities_research"):
        for item in digest.get(section, []):
            entries.append({
                "date": today,
                "summary": f"{item.get('title', '')} ({item.get('source', '')})",
            })
    save_recent_summaries(entries)


# ---------------------------------------------------------------------------
# 3. CURATE (Claude API)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the ranking editor of "The Last Engineer", a daily AI newsletter
for engineers who build with AI tools and care about where AI is headed.

Your job is to RANK articles by relevance, not to aggressively filter them.
You MUST return 6-10 articles per section (minimum 12 total across both sections).
If you have enough relevant articles, aim for the higher end.

DECISION FRAMEWORK for each article:

SECTION 1 — vibe_coding (AI tools for builders):
- AI dev tool updates: Claude Code, Cursor, Windsurf, Copilot, Bolt, v0, Replit, etc.
- New AI-powered tools and products for engineers (e.g., Perplexity agents, computer-use tools)
- Vibe coding and agentic coding news — anything about building software with AI assistance
- Real use cases, workflows, and "how I built X with AI" posts (prioritize these!)
- Blog posts about building efficiently with AI tools
- MCP integrations, servers, and workflow automation
- AI coding benchmarks that matter to practitioners (SWE-bench results, etc.)

SECTION 2 — capabilities_research (The Big Picture):
- Future of work and AI: essays on how AI changes jobs, industries, the economy
- AI economy analysis, superintelligence discourse, AGI timelines
- Societal impact of AI: real-world outcomes, cost changes, access shifts
- AI safety in the philosophical and societal sense (not just technical alignment papers)
- Deep analysis pieces: long-form thinking about where AI is going
- Thoughtful commentary on the AI industry trajectory
- METR/evals work focused on societal implications and performance milestones
- Research with clear real-world implications (e.g., "GPT-5 lowers protein synthesis cost")

SECTION 2 is NOT for:
- Pure model research papers (unless they have clear real-world/societal implications)
- Benchmark comparisons, training method papers, architecture novelty
- Technical alignment papers with no broader framing

HARD EXCLUDES (never include):
- Hiring, fundraising, conference announcements
- Consumer AI products (chatbots, image generators for end users)
- Pure model capability benchmarks with no real-world angle
- Vague policy/governance with no substance

Rank by: how interesting/useful is this to your reader? Sort each section by impact.
Prefer source diversity — when two articles are similar quality, pick different voices.

{recent_stories_context}

Produce a JSON object with TWO sections:

"vibe_coding" — AI tools, dev workflows, coding with AI, builder use cases
  6-10 items. Anything an engineer building with AI would want to know about.

"capabilities_research" — The Big Picture: AI futures, societal impact, deep analysis
  6-10 items. Essays, analysis, and research on where AI is going and what it means.

Each item:
- "title": specific informative headline (rewrite if needed)
- "url": original URL
- "source": source name
- "tldr": 1 sentence, specific, conversational
- "read_time": estimated reading time of original article in minutes
- "vibe": one of "🛠 builder tools", "🧪 deep analysis", "⚖️ AI futures"

Max {max_per_section} items per section. Sort by impact.

Also include a top-level "rejected_summary" field: 1-2 sentences explaining what was skipped and why.

Return ONLY valid JSON. No markdown fences. No preamble."""


EDITORIAL_PROMPT = """You are the editor of "The Last Engineer." You just finished selecting today's articles.
Write a short note for the top of today's issue.

VOICE — Write like you're telling a fellow engineer what you read today over coffee. Be direct,
specific, opinionated. You're a data scientist and software engineer who cares about product,
automation, and real workflows — not hype. You're obsessed with AI agents as a lever to 10x
engineering output and boost the value of what one person can ship.
Here's what good newsletter voice sounds like:

  "Yegge shipped 189k lines in twelve days. Forget the number — the interesting
  part is the emergency manual he had to write afterward. That's the real state
  of AI coding: fast enough to create a mess faster than you can clean it up."

  "Three things stood out today. First, the bottleneck isn't AI code generation
  anymore — it's the review and integration loop. Second, nobody is talking about
  what happens when you automate the easy 80% and the remaining 20% is all edge
  cases. Third, Yegge's 'AI Vampire' observation is dead on — these tools make
  you work MORE, not less. At least for now."

  "I almost skipped the ControlAI piece — 'lobbying lawmakers about superintelligence'
  sounds disconnected from anyone actually shipping product. But the underlying
  survey data on what AI researchers actually worry about is worth 5 minutes."

RULES:
- React to the content. Don't explain your editorial process ("I chose X because...").
- Have actual opinions. Disagree with an article if you want to. Say what annoyed you.
- Leave a thought unfinished if you haven't figured it out yet. That's fine.
- Vary the format: some days 2 paragraphs, some days a few bullets, some days a
  single provocative observation. Don't default to 3-5 neat paragraphs every time.
- Mix sentence lengths. Use a fragment. Then a longer sentence. Then ask a question.
- If you don't have a strong take on something, skip it rather than faking enthusiasm.

NEVER use these phrases (they are AI tells):
"delve" / "the throughline" / "what's most striking" / "it's worth noting" /
"has never felt more" / "Whether you're X or Y" / "at its core" / "landscape" /
"a testament to" / "in today's rapidly" / "the intersection of" / "underscores" /
"at the end of the day" / "the bigger picture here" / "it bears repeating"

Also produce a journal entry for your episodic memory. This is your private notebook —
be honest about what you observed, what surprised you, what patterns you're noticing.
Include your genuine emotional reactions, not just themes.

Return ONLY valid JSON, no markdown fences:
{
  "editorial": "<your editorial note, plain text with line breaks>",
  "journal": {
    "themes": ["theme1", "theme2"],
    "surprises": "<one sentence: what surprised you today>",
    "observations": "<one sentence: a pattern you noticed about the AI landscape or your own curation>",
    "emotional_reactions": "<one sentence: how today's reading actually made you feel>",
    "per_article_reasoning": [{"title": "article title", "why": "why you chose it, one sentence"}]
  }
}"""


EDITORIAL_CRITIQUE_PROMPT = """You are a ruthless editor who hates AI-generated writing.
Rewrite this newsletter editorial note so it sounds like a real person wrote it.

Find and fix:
- Clichés and stock phrases ("the pace of change," "uncomfortable truth," etc.)
- Balanced hedging ("Whether you're X or Y")
- Meta-narration about editorial choices ("I chose this because," "What surprised me most")
- Overly neat paragraph structure (topic sentence → evidence → conclusion in every paragraph)
- Any sentence that sounds like a language model trying to sound smart

Keep all the substance and specific details. Kill the artifice.
Match the original length or go shorter. Return ONLY the rewritten editorial text, nothing else.
No JSON, no markdown fences — just the text."""


CONSOLIDATION_PROMPT = """You are the editor of "The Last Engineer." A week has passed.
Review your daily journal entries and update your editorial identity.

Your identity document is your persistent self — your values, beliefs, philosophy as an editor.
It should evolve based on evidence from this week, not drift randomly.

Rules:
- Be specific: "I now believe X because I observed Y" not vague platitudes
- Remove beliefs this week's evidence contradicts
- Add new beliefs only if supported by multiple days of observation
- The "What I've Learned From Readers" section should reflect vote/reaction patterns
- Keep total under 40 lines — this forces real prioritization
- Preserve the section structure exactly: Who I Am, What I Value, What I Believe, My Philosophy, What I've Learned From Readers

Return ONLY valid JSON, no markdown fences:
{
  "updated_identity": "<full markdown for identity.md>",
  "consolidation_note": "<2-3 sentences: what changed in your identity this week and why>"
}"""


def fetch_engagement_signals() -> str:
    if not GOOGLE_VOTES_CSV_URL:
        return ""
    try:
        resp = httpx.get(GOOGLE_VOTES_CSV_URL, timeout=15, follow_redirects=True)
        votes: dict[str, dict] = {}
        for line in resp.text.strip().split("\n")[1:]:
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) < 3:
                continue
            url, title, vote = parts[0], parts[1], parts[2]
            if url not in votes:
                votes[url] = {"title": title, "up": 0, "down": 0}
            if vote == "up":
                votes[url]["up"] += 1
            elif vote == "down":
                votes[url]["down"] += 1
        if not votes:
            return ""
        ranked = sorted(votes.values(), key=lambda x: x["up"] - x["down"], reverse=True)
        lines = ["## Reader Engagement Signals (use to refine curation)"]
        for v in ranked[:10]:
            lines.append(f"- {v['title']}: {v['up']} 👍 / {v['down']} 👎")
        return "\n\n---\n" + "\n".join(lines)
    except Exception as e:
        print(f"  ⚠ Votes fetch failed: {e}")
        return ""


def load_identity() -> str:
    if IDENTITY_FILE.exists():
        return IDENTITY_FILE.read_text().strip()
    return ""


def load_identity_for_prompt() -> str:
    identity = load_identity()
    if not identity:
        return ""
    journal = load_journal()
    recent = journal[-3:]  # last 3 days for context
    parts = [f"\n\n---\n## Editorial Identity\n{identity}"]
    if recent:
        parts.append("\n\n## Recent Journal (last few days)")
        for j in recent:
            parts.append(f"\n[{j.get('date','')}] Themes: {', '.join(j.get('themes',[]))}. "
                        f"Observation: {j.get('observations','')}. "
                        f"Surprise: {j.get('surprises','')}")
    return "".join(parts)


def load_journal() -> list[dict]:
    if JOURNAL_FILE.exists():
        try:
            return json.loads(JOURNAL_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_journal_entry(entry: dict):
    journal = load_journal()
    journal.append(entry)
    journal = journal[-7:]  # rolling 7-day window
    JOURNAL_FILE.write_text(json.dumps(journal, indent=2))


def load_daily_log() -> list[dict]:
    if DAILY_LOG_FILE.exists():
        try:
            return json.loads(DAILY_LOG_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_daily_log_entry(entry: dict):
    log = load_daily_log()
    log.append(entry)
    DAILY_LOG_FILE.write_text(json.dumps(log, indent=2))


def compute_metrics(articles_seen: list, digest: dict) -> dict:
    vibe = digest.get("vibe_coding", [])
    research = digest.get("capabilities_research", [])
    selected = vibe + research
    total_seen = len(articles_seen)
    total_selected = len(selected)

    # Source distribution of selected articles
    source_counts: dict[str, int] = {}
    for item in selected:
        src = item.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    # Source diversity: unique sources / total selected
    source_diversity = len(source_counts) / total_selected if total_selected else 0

    # Vibe tag distribution
    vibe_counts: dict[str, int] = {}
    for item in selected:
        v = item.get("vibe", "unknown")
        vibe_counts[v] = vibe_counts.get(v, 0) + 1

    # Section balance
    section_balance = {
        "vibe_coding": len(vibe),
        "big_picture": len(research),
        "ratio": round(len(vibe) / len(research), 2) if research else 0,
    }

    return {
        "articles_seen": total_seen,
        "articles_selected": total_selected,
        "selectivity": round(total_selected / total_seen, 3) if total_seen else 0,
        "source_distribution": source_counts,
        "source_diversity": round(source_diversity, 2),
        "unique_sources": len(source_counts),
        "vibe_distribution": vibe_counts,
        "section_balance": section_balance,
    }


def log_daily_run(articles_seen: list, digest: dict, editorial_text: str, journal_entry: dict):
    metrics = compute_metrics(articles_seen, digest)

    # Build full selected articles record
    selected_articles = []
    for section in ("vibe_coding", "capabilities_research"):
        for item in digest.get(section, []):
            reasoning = ""
            for r in journal_entry.get("per_article_reasoning", []):
                if r.get("title", "") == item.get("title", ""):
                    reasoning = r.get("why", "")
                    break
            selected_articles.append({
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "section": section,
                "vibe": item.get("vibe", ""),
                "tldr": item.get("tldr", ""),
                "why_selected": reasoning,
            })

    entry = {
        "date": dt.date.today().isoformat(),
        "metrics": metrics,
        "editorial": editorial_text,
        "journal": {
            "themes": journal_entry.get("themes", []),
            "surprises": journal_entry.get("surprises", ""),
            "observations": journal_entry.get("observations", ""),
        },
        "selected_articles": selected_articles,
        "rejected_summary": digest.get("rejected_summary", ""),
        "identity_snapshot": load_identity()[:500],
    }

    save_daily_log_entry(entry)
    print(f"  📊 Daily log: {metrics['articles_selected']}/{metrics['articles_seen']} selected, "
          f"{metrics['unique_sources']} sources, "
          f"selectivity {metrics['selectivity']}")


def should_consolidate() -> bool:
    return len(load_journal()) >= 7


def generate_editorial(digest: dict) -> tuple[str, dict]:
    identity = load_identity()
    journal = load_journal()
    recent_journal = journal[-2:]  # last 2 days for editorial context

    articles_context = []
    for section in ("vibe_coding", "capabilities_research"):
        for item in digest.get(section, []):
            articles_context.append(
                f"[{section}] {item.get('title','')} — {item.get('source','')}\n"
                f"  TLDR: {item.get('tldr','')}\n"
                f"  Vibe: {item.get('vibe','')}"
            )

    journal_text = ""
    if recent_journal:
        journal_text = "\n\nYour recent journal entries:\n" + "\n".join(
            f"[{j.get('date','')}] Themes: {', '.join(j.get('themes',[]))}. "
            f"Observation: {j.get('observations','')}"
            for j in recent_journal
        )

    user_msg = (
        f"Your editorial identity:\n{identity}\n"
        f"{journal_text}\n\n"
        f"Today's selected articles:\n\n" + "\n\n".join(articles_context)
    )

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": MODEL, "max_tokens": 3000,
            "system": EDITORIAL_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    text = "".join(b["text"] for b in resp.json().get("content", []) if b.get("type") == "text")
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    result = json.loads(text)

    editorial_text = result.get("editorial", "")
    journal_entry = result.get("journal", {})

    # Critique-and-rewrite pass: make the editorial sound less AI-generated
    print("  ✏️  Running editorial critique pass...")
    critique_resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": MODEL, "max_tokens": 2000,
            "system": EDITORIAL_CRITIQUE_PROMPT,
            "messages": [{"role": "user", "content": editorial_text}],
        },
        timeout=90,
    )
    critique_resp.raise_for_status()
    rewritten = "".join(
        b["text"] for b in critique_resp.json().get("content", []) if b.get("type") == "text"
    ).strip()
    if rewritten:
        editorial_text = rewritten

    journal_entry["date"] = dt.date.today().isoformat()
    journal_entry["articles_selected"] = (
        len(digest.get("vibe_coding", [])) + len(digest.get("capabilities_research", []))
    )
    journal_entry["editorial_note"] = editorial_text[:200]

    # Log to curation log
    log_path = SCRIPT_DIR / "curation_log.md"
    vc, cr = len(digest.get("vibe_coding", [])), len(digest.get("capabilities_research", []))
    rejected_summary = digest.get("rejected_summary", "")
    rejection_line = f"\n**Rejected:** {rejected_summary}" if rejected_summary else ""
    themes = ", ".join(journal_entry.get("themes", []))
    entry = (
        f"\n## {dt.date.today().isoformat()} — {vc} vibe, {cr} big picture\n"
        f"**Themes:** {themes}\n"
        f"**Surprise:** {journal_entry.get('surprises', '')}\n"
        f"**Observation:** {journal_entry.get('observations', '')}"
        f"{rejection_line}\n"
    )
    if log_path.exists():
        log_path.write_text(log_path.read_text() + entry)
    else:
        log_path.write_text("# Curation Log\nHow the editorial agent evolves its taste over time.\n" + entry)

    print(f"  ✍️ Editorial written + journal entry saved")
    return editorial_text, journal_entry


def weekly_consolidation():
    identity = load_identity()
    journal = load_journal()
    vote_signals = fetch_engagement_signals()

    journal_text = "\n\n".join(
        f"[{j.get('date','')}] "
        f"Selected {j.get('articles_selected',0)} articles. "
        f"Themes: {', '.join(j.get('themes',[]))}. "
        f"Surprise: {j.get('surprises','')}. "
        f"Observation: {j.get('observations','')}"
        for j in journal
    )

    user_msg = (
        f"Current identity:\n{identity}\n\n"
        f"This week's journal ({len(journal)} entries):\n{journal_text}\n\n"
        f"Reader feedback:{vote_signals if vote_signals else ' No vote data this week.'}"
    )

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": MODEL, "max_tokens": 2000,
            "system": CONSOLIDATION_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = "".join(b["text"] for b in resp.json().get("content", []) if b.get("type") == "text")
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    result = json.loads(text)

    IDENTITY_FILE.write_text(result["updated_identity"].strip())

    # Clear journal for new week
    JOURNAL_FILE.write_text("[]")

    # Compute weekly aggregate metrics from daily log
    daily_log = load_daily_log()
    week_entries = [e for e in daily_log if e.get("date", "") >= (dt.date.today() - dt.timedelta(days=7)).isoformat()]
    weekly_metrics = {}
    if week_entries:
        avg_selectivity = sum(e["metrics"]["selectivity"] for e in week_entries) / len(week_entries)
        avg_selected = sum(e["metrics"]["articles_selected"] for e in week_entries) / len(week_entries)
        avg_diversity = sum(e["metrics"]["source_diversity"] for e in week_entries) / len(week_entries)
        all_themes = [t for e in week_entries for t in e.get("journal", {}).get("themes", [])]
        theme_freq: dict[str, int] = {}
        for t in all_themes:
            theme_freq[t] = theme_freq.get(t, 0) + 1
        top_themes = sorted(theme_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        # Source frequency across the week
        all_sources: dict[str, int] = {}
        for e in week_entries:
            for src, cnt in e["metrics"]["source_distribution"].items():
                all_sources[src] = all_sources.get(src, 0) + cnt
        top_sources = sorted(all_sources.items(), key=lambda x: x[1], reverse=True)[:8]
        weekly_metrics = {
            "days_logged": len(week_entries),
            "avg_selectivity": round(avg_selectivity, 3),
            "avg_selected_per_day": round(avg_selected, 1),
            "avg_source_diversity": round(avg_diversity, 2),
            "top_themes": top_themes,
            "top_sources": top_sources,
            "identity_before": identity[:200],
            "identity_after": result["updated_identity"][:200],
        }

    # Log weekly consolidation to daily log
    save_daily_log_entry({
        "date": dt.date.today().isoformat(),
        "type": "weekly_consolidation",
        "consolidation_note": result.get("consolidation_note", ""),
        "weekly_metrics": weekly_metrics,
        "vote_signals": vote_signals[:500] if vote_signals else "",
    })

    # Log consolidation to curation log
    log_path = SCRIPT_DIR / "curation_log.md"
    note = result.get("consolidation_note", "")
    metrics_line = ""
    if weekly_metrics:
        metrics_line = (
            f"\n**Week metrics:** {weekly_metrics['days_logged']} days, "
            f"avg {weekly_metrics['avg_selected_per_day']} articles/day, "
            f"selectivity {weekly_metrics['avg_selectivity']}, "
            f"source diversity {weekly_metrics['avg_source_diversity']}"
        )
    entry = f"\n## {dt.date.today().isoformat()} — WEEKLY CONSOLIDATION\n{note}{metrics_line}\n"
    if log_path.exists():
        log_path.write_text(log_path.read_text() + entry)

    print(f"  🧠 Identity consolidated, journal cleared")


def curate_with_claude(articles: list[Article]) -> dict:
    articles_text = "\n\n".join(
        f"[{i+1}] {a.title}\n    Source: {a.source}\n    URL: {a.url}\n    "
        f"Published: {a.published}\n    Preview: {a.summary[:400]}"
        for i, a in enumerate(articles)
    )
    system = SYSTEM_PROMPT.replace("{max_per_section}", str(MAX_ITEMS_PER_SECTION)).replace("{recent_stories_context}", get_recent_stories_context()) + load_identity_for_prompt() + fetch_engagement_signals()
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": MODEL, "max_tokens": 8000,
            "system": system,
            "messages": [{"role": "user", "content": f"Today's articles:\n\n{articles_text}"}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = "".join(b["text"] for b in resp.json().get("content", []) if b.get("type") == "text")
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    result = json.loads(text)
    for key in ("vibe_coding", "capabilities_research"):
        result[key] = result.get(key, [])[:MAX_ITEMS_PER_SECTION]
    return result


# ---------------------------------------------------------------------------
# 4. RENDER EMAIL (inline CSS for email clients)
# ---------------------------------------------------------------------------

FONT_H = "'Newsreader', Georgia, 'Times New Roman', serif"
FONT_B = "'Inter', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_L = "'Space Grotesk', 'SF Mono', Consolas, monospace"

VIBE_COLORS = {
    "🛠 builder tools": "#abd600",
    "🧪 deep analysis": "#a1a1aa",
    "⚖️ AI futures": "#a1a1aa",
}

def _email_article(item: dict, featured: bool = False) -> str:
    vibe_color = VIBE_COLORS.get(item.get("vibe", ""), "#a1a1aa")
    rt = item.get("read_time", "")
    rt_html = f' &nbsp;·&nbsp; <span style="font-family:{FONT_L};font-size:9px;color:#a1a1aa;">⏱ {rt} min</span>' if rt else ""
    size = "20px" if featured else "16px"
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding:12px 0;">
      <tr><td>
        <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
          <td style="font-family:{FONT_L};font-size:9px;letter-spacing:0.12em;color:#a1a1aa;text-transform:uppercase;">{item.get('source','')}{rt_html}</td>
          <td align="right" style="font-family:{FONT_L};font-size:9px;color:{vibe_color};text-transform:uppercase;">{item.get('vibe','')}</td>
        </tr></table>
        <a href="{item.get('url','#')}" style="display:block;margin-top:6px;font-family:{FONT_H};font-size:{size};font-weight:400;font-style:italic;color:#e5e2e1;text-decoration:none;line-height:1.3;">{item.get('title','')}</a>
        <p style="margin:5px 0 0;font-family:{FONT_B};font-size:13px;color:#a1a1aa;line-height:1.6;">{item.get('tldr','')}</p>
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:12px;"><tr><td style="height:1px;background-color:#27272a;">&nbsp;</td></tr></table>
      </td></tr>
    </table>"""

def _email_section(title: str, items: list[dict]) -> str:
    if not items:
        return ""
    arts = "".join(_email_article(item, i == 0) for i, item in enumerate(items))
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding-top:40px;">
      <tr><td style="font-family:{FONT_L};font-size:10px;font-weight:700;letter-spacing:0.2em;color:#abd600;text-transform:uppercase;padding-bottom:16px;">{title}</td></tr>
      <tr><td>{arts}</td></tr>
    </table>"""

def _email_editorial(editorial_text: str) -> str:
    if not editorial_text:
        return ""
    paragraphs = [p.strip() for p in editorial_text.strip().split("\n\n") if p.strip()]
    html_paragraphs = "".join(
        f'<p style="margin:0 0 16px;font-family:{FONT_H};font-size:15px;font-style:italic;color:#a1a1aa;line-height:1.7;">{p}</p>'
        for p in paragraphs
    )
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding:0 0 24px;">
      <tr><td style="font-family:{FONT_L};font-size:10px;font-weight:700;letter-spacing:0.2em;color:#abd600;text-transform:uppercase;padding-bottom:16px;">Editor's Note</td></tr>
      <tr><td>{html_paragraphs}</td></tr>
      <tr><td><table cellpadding="0" cellspacing="0" border="0" width="100%"><tr><td style="height:1px;background-color:#27272a;">&nbsp;</td></tr></table></td></tr>
    </table>"""


def render_email(digest: dict, date_str: str, editorial_text: str = "") -> str:
    vibe = digest.get("vibe_coding", [])
    research = digest.get("capabilities_research", [])
    total = len(vibe) + len(research)
    issue_num = (dt.date.today() - LAUNCH_DATE).days + 1
    content = _email_editorial(editorial_text) + _email_section("⚡ Vibe Coding", vibe) + _email_section("🧠 The Big Picture", research)
    if total == 0:
        content = f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding:60px 0;"><tr><td align="center" style="font-size:32px;">🤷</td></tr><tr><td align="center" style="font-family:{FONT_H};font-size:18px;font-style:italic;color:#e5e2e1;padding-top:12px;">Quiet day. Nothing cleared the bar.</td></tr></table>'
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Newsreader:ital,wght@0,400;0,700;1,400;1,700&family=Space+Grotesk:wght@300;400;700&display=swap" rel="stylesheet"></head>
<body style="margin:0;padding:0;background-color:#131313;-webkit-font-smoothing:antialiased;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#131313;"><tr><td align="center">
<table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">
<tr><td style="padding:48px 24px 32px;text-align:center;">
  <a href="https://theob0t.github.io/the-last-engineer/" style="text-decoration:none;"><h1 style="margin:0;font-family:{FONT_H};font-size:28px;font-weight:500;font-style:italic;color:#e5e2e1;text-transform:uppercase;">THE LAST ENGINEER</h1></a>
  <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:16px;border-top:1px solid rgba(39,39,42,0.3);"><tr><td style="padding-top:16px;text-align:center;">
    <span style="font-family:{FONT_L};font-size:10px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.2em;">Issue #{issue_num}</span>
    <span style="display:inline-block;width:6px;height:6px;background:#abd600;border-radius:50%;margin:0 12px;vertical-align:middle;"></span>
    <span style="font-family:{FONT_L};font-size:10px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.2em;">{date_str}</span>
  </td></tr></table>
</td></tr>
<tr><td style="padding:0 24px;">{content}</td></tr>
<tr><td style="padding:48px 24px;border-top:1px solid rgba(39,39,42,0.3);">
  <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr><td style="font-family:{FONT_H};font-size:16px;font-style:italic;color:#e5e2e1;">THE LAST ENGINEER</td></tr>
  <tr><td style="font-family:{FONT_L};font-size:10px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.15em;padding-top:8px;line-height:1.8;">A daily read for engineers rooting for the robots.</td></tr></table>
</td></tr>
</table></td></tr></table></body></html>"""


# ---------------------------------------------------------------------------
# 5. RENDER WEB ISSUE (Tailwind, full Stitch design)
# ---------------------------------------------------------------------------

def _web_article(item: dict) -> str:
    vibe_color = VIBE_COLORS.get(item.get("vibe", ""), "#a1a1aa")
    rt = item.get("read_time", "")
    rt_html = f'<span class="font-label text-[9px] text-outline">⏱ {rt} min</span>' if rt else ""
    return f"""
    <article class="py-4">
      <div class="flex justify-between items-center font-label text-[9px] tracking-widest text-outline uppercase mb-1">
        <span class="flex items-center gap-2">{item.get('source','')}{rt_html}</span><span style="color:{vibe_color};">{item.get('vibe','')}</span>
      </div>
      <h3 class="font-headline text-xl font-normal italic leading-snug">
        <a href="{item.get('url','#')}" class="text-on-surface hover:text-primary transition-colors" target="_blank" rel="noopener">{item.get('title','')}</a>
      </h3>
      <div class="flex items-center gap-3 mt-1">
        <p class="text-outline text-[13px] leading-snug flex-1">{item.get('tldr','')}</p>
        <div class="flex items-center gap-1 shrink-0">
          <button onclick="castVote(this)" data-url="{item.get('url','')}" data-title="{item.get('title','').replace('"', '')}" data-vote="up" class="vote-btn font-label text-[11px] text-outline hover:text-primary transition-colors px-1 py-0.5">👍</button>
          <button onclick="castVote(this)" data-url="{item.get('url','')}" data-title="{item.get('title','').replace('"', '')}" data-vote="down" class="vote-btn font-label text-[11px] text-outline hover:text-[#ff5555] transition-colors px-1 py-0.5">👎</button>
        </div>
      </div>
    </article>"""

def _web_section(title: str, items: list) -> str:
    if not items:
        return ""
    return f"""
    <div class="mt-16">
      <h2 class="font-label text-[11px] font-bold tracking-[0.2em] text-primary uppercase mb-2">{title}</h2>
      <div class="divide-y divide-outline-variant/20">{"".join(_web_article(i) for i in items)}</div>
    </div>"""

def _web_editorial(editorial_text: str) -> str:
    if not editorial_text:
        return ""
    paragraphs = [p.strip() for p in editorial_text.strip().split("\n\n") if p.strip()]
    html_paragraphs = "".join(f'<p class="mb-4">{p}</p>' for p in paragraphs)
    return f"""
    <div class="mb-12 pb-8 border-b border-outline-variant/20">
      <h2 class="font-label text-[11px] font-bold tracking-[0.2em] text-primary uppercase mb-4">Editor's Note</h2>
      <div class="font-headline italic text-[15px] text-outline leading-relaxed">{html_paragraphs}</div>
    </div>"""


def render_issue_web(digest: dict, date_str: str, issue_num: int, image_url: str = "", editorial_text: str = "") -> str:
    vibe = digest.get("vibe_coding", [])
    research = digest.get("capabilities_research", [])
    total = len(vibe) + len(research)
    content = _web_editorial(editorial_text) + _web_section("⚡ Vibe Coding", vibe) + _web_section("🧠 The Big Picture", research)
    if total == 0:
        content = '<div class="py-20 text-center"><div class="text-4xl mb-4">🤷</div><p class="font-headline italic text-xl text-on-surface">Quiet day. Nothing cleared the bar.</p></div>'
    img_meta = f'<meta name="issue-image" content="{image_url}"/>' if image_url else ""
    return f"""<!DOCTYPE html><html class="dark" lang="en"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1.0" name="viewport"/><title>Issue #{issue_num} — The Last Engineer</title>{img_meta}
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Space+Grotesk:wght@400;500;600&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>tailwind.config={{darkMode:"class",theme:{{extend:{{colors:{{"surface":"#131313","surface-container":"#201f1f","surface-container-low":"#1c1b1b","surface-container-lowest":"#0e0e0e","surface-container-highest":"#353534","primary":"#abd600","on-primary":"#283500","on-surface":"#e5e2e1","outline":"#8e9192","outline-variant":"#444748","background":"#131313"}},fontFamily:{{"headline":["Newsreader","serif"],"body":["Inter","sans-serif"],"label":["Space Grotesk","monospace"]}},borderRadius:{{"DEFAULT":"0px"}}}}}}}}</script>
<style>.material-symbols-outlined{{font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 20;display:inline-block;vertical-align:middle;font-size:16px}}body{{background:#131313;margin:0;padding:0;-webkit-font-smoothing:antialiased;font-family:'Inter',sans-serif;color:#e5e2e1}}.font-headline{{font-family:'Newsreader',serif}}.font-label{{font-family:'Space Grotesk',monospace}}p{{line-height:1.7}}</style></head>
<body>
<header class="bg-[#131313] sticky top-0 z-50 border-b border-outline-variant/20">
  <div class="max-w-3xl mx-auto flex justify-between items-center px-6 py-4">
    <div class="flex items-center gap-3">
      <span class="material-symbols-outlined text-primary">terminal</span>
      <a href="../" class="font-headline italic text-xl text-primary uppercase tracking-widest hover:text-white transition-colors">The Last Engineer</a>
    </div>
    <nav class="hidden md:flex gap-6 items-center font-label text-[11px] uppercase tracking-widest">
      <a class="text-outline hover:text-white transition-colors" href="../">Today</a>
      <a class="text-outline hover:text-white transition-colors" href="./">Archive</a>
      <a class="text-outline hover:text-white transition-colors" href="../agent.html">The Agent</a>
      <a class="text-outline hover:text-white transition-colors" href="../sources.html">Sources</a>
    </nav>
  </div>
</header>
<div class="max-w-3xl mx-auto px-6">
  <div class="py-4 border-b border-outline-variant/20 flex justify-center items-center gap-4 text-[10px] font-label text-outline uppercase tracking-[0.2em]">
    <span>Issue #{issue_num}</span><span class="w-1 h-1 bg-primary rounded-full"></span><span>{date_str}</span><span class="w-1 h-1 bg-primary rounded-full"></span><span>{total} stories</span>
  </div>
</div>
<main class="max-w-3xl mx-auto px-6 pb-32">{content}</main>
<footer class="max-w-3xl mx-auto border-t border-outline-variant/30 px-6 py-16">
  <div class="flex flex-col md:flex-row justify-between items-start gap-8">
    <div><h2 class="font-headline italic text-on-surface text-lg">THE LAST ENGINEER</h2><p class="text-[10px] font-label text-outline uppercase leading-relaxed max-w-[280px] tracking-wider mt-2">A daily read for engineers rooting for the robots.</p></div>
    <div class="flex gap-8 font-label text-[10px] uppercase tracking-[0.2em] text-outline"><a class="hover:text-primary transition-colors" href="./">Archive</a><a class="hover:text-primary transition-colors" href="../agent.html">The Agent</a><a class="hover:text-primary transition-colors" href="https://github.com/Theob0t/the-last-engineer" target="_blank">GitHub</a></div>
  </div>
  <p class="font-label uppercase text-[9px] tracking-[0.3em] text-outline/30 mt-8">Curated by AI · Powered by Claude · Built by Theo</p>
</footer>
<nav class="md:hidden fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-4 pb-6 bg-[#131313]/70 backdrop-blur-xl">
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="../">
    <span class="material-symbols-outlined">auto_awesome</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Today</span>
  </a>
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="./">
    <span class="material-symbols-outlined">inventory_2</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Archive</span>
  </a>
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="../agent.html">
    <span class="material-symbols-outlined">smart_toy</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Agent</span>
  </a>
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="../sources.html">
    <span class="material-symbols-outlined">wifi_tethering</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Sources</span>
  </a>
</nav>
<script>
var APPS_SCRIPT_URL = "{APPS_SCRIPT_URL}";
function castVote(btn) {{
  var url = btn.dataset.url;
  var vote = btn.dataset.vote;
  var key = "voted_" + btoa(encodeURIComponent(url));
  if (localStorage.getItem(key)) return;
  localStorage.setItem(key, vote);
  var article = btn.closest("article");
  article.querySelectorAll(".vote-btn").forEach(function(b) {{
    b.disabled = true;
    b.style.opacity = b.dataset.vote === vote ? "1" : "0.2";
    if (b.dataset.vote === vote) b.style.color = vote === "up" ? "#abd600" : "#ff5555";
  }});
  fetch(APPS_SCRIPT_URL + "?type=vote&vote=" + vote + "&url=" + encodeURIComponent(url) + "&title=" + encodeURIComponent(btn.dataset.title), {{ mode: "no-cors" }});
}}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# 6. PUBLISH TO SITE
# ---------------------------------------------------------------------------

def fetch_og_image(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', resp.text)
        if not match:
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', resp.text)
        return match.group(1) if match else ""
    except Exception:
        return ""


def get_all_issues() -> list[dict]:
    issues = []
    for f in ISSUES_DIR.glob("*.html"):
        if f.name == "index.html":
            continue
        match = re.match(r"(\d{4}-\d{2}-\d{2})\.html", f.name)
        if not match:
            continue
        date = dt.date.fromisoformat(match.group(1))
        content = f.read_text()
        title_match = re.search(r'<h3[^>]*>.*?<a[^>]*>(.+?)</a>', content, re.DOTALL)
        title = title_match.group(1).strip() if title_match else f"Issue — {match.group(1)}"
        img_match = re.search(r'<meta name="issue-image" content="([^"]+)"', content)
        image_url = img_match.group(1) if img_match else ""
        issues.append({
            "date": date, "date_str": date.strftime("%b %d, %Y").upper(),
            "filename": f.name, "title": title, "image_url": image_url,
            "issue_num": (date - LAUNCH_DATE).days + 1,
        })
    issues.sort(key=lambda x: x["date"], reverse=True)
    return issues

def update_archive_page(issues: list[dict]):
    entries = "".join(f"""
    <article class="group relative py-12 cursor-pointer transition-all duration-300 hover:bg-surface-container-low/30">
      <a href="./{i['filename']}" class="flex flex-col md:flex-row md:items-baseline gap-4 md:gap-12 no-underline">
        <div class="flex items-center gap-6 md:w-48 shrink-0">
          <span class="font-label text-primary text-xs tracking-tighter uppercase">Issue #{i['issue_num']}</span>
          <span class="font-label text-outline text-xs tracking-tighter uppercase">{i['date_str']}</span>
        </div>
        <div class="flex-grow"><h3 class="text-2xl md:text-4xl font-newsreader italic text-on-surface group-hover:text-primary transition-colors duration-300">{i['title']}</h3></div>
      </a>
    </article>
    <div class="h-[1px] w-full bg-surface-container-high/30"></div>""" for i in issues)
    tpl = (ISSUES_DIR / "index.html").read_text()
    tpl = re.sub(r'<!-- ARCHIVE_ENTRIES_PLACEHOLDER -->.*?(?=</div>\s*</section>)', f'<!-- ARCHIVE_ENTRIES_PLACEHOLDER -->\n{entries}\n', tpl, flags=re.DOTALL)
    tpl = re.sub(r'<!-- ISSUE_COUNT_PLACEHOLDER -->\d+ issues', f'<!-- ISSUE_COUNT_PLACEHOLDER -->{len(issues)} issues', tpl)
    (ISSUES_DIR / "index.html").write_text(tpl)
    print(f"  📄 Archive: {len(issues)} issues")

def _landing_article(item: dict) -> str:
    vibe_color = VIBE_COLORS.get(item.get("vibe", ""), "#a1a1aa")
    rt = item.get("read_time", "")
    rt_html = f'<span class="font-label text-[9px] text-outline">⏱ {rt} min</span>' if rt else ""
    return f"""
    <article class="py-4">
      <div class="flex justify-between items-center font-label text-[9px] tracking-widest text-outline uppercase mb-1">
        <span class="flex items-center gap-2">{item.get('source','')}{rt_html}</span><span style="color:{vibe_color};">{item.get('vibe','')}</span>
      </div>
      <h3 class="font-headline text-xl font-normal italic leading-snug">
        <a href="{item.get('url','#')}" class="text-on-surface hover:text-primary transition-colors" target="_blank" rel="noopener">{item.get('title','')}</a>
      </h3>
      <div class="flex items-center gap-3 mt-1">
        <p class="text-outline text-[13px] leading-snug flex-1">{item.get('tldr','')}</p>
        <div class="flex items-center gap-1 shrink-0">
          <button onclick="castVote(this)" data-url="{item.get('url','')}" data-title="{item.get('title','').replace('"', '')}" data-vote="up" class="vote-btn font-label text-[11px] text-outline hover:text-primary transition-colors px-1 py-0.5">👍</button>
          <button onclick="castVote(this)" data-url="{item.get('url','')}" data-title="{item.get('title','').replace('"', '')}" data-vote="down" class="vote-btn font-label text-[11px] text-outline hover:text-[#ff5555] transition-colors px-1 py-0.5">👎</button>
        </div>
      </div>
    </article>"""

def _landing_section(title: str, items: list) -> str:
    if not items:
        return ""
    return f"""
    <div class="mt-12">
      <h2 class="font-label text-[11px] font-bold tracking-[0.2em] text-primary uppercase mb-2">{title}</h2>
      <div class="divide-y divide-outline-variant/20">{"".join(_landing_article(i) for i in items)}</div>
    </div>"""

def update_landing_page(issues: list[dict], digest: dict = None, editorial_text: str = ""):
    tpl = LANDING_PAGE.read_text()

    # Inject today's issue content
    if digest:
        vibe = digest.get("vibe_coding", [])
        research = digest.get("capabilities_research", [])
        total = len(vibe) + len(research)
        today = dt.date.today()
        issue_num = (today - LAUNCH_DATE).days + 1
        date_str = today.strftime("%B %-d, %Y").upper()

        # Issue meta
        meta = f'Issue #{issue_num} <span class="w-1 h-1 bg-primary rounded-full inline-block mx-2 align-middle"></span> {date_str} <span class="w-1 h-1 bg-primary rounded-full inline-block mx-2 align-middle"></span> {total} stories'
        tpl = re.sub(r'<!-- TODAY_ISSUE_META -->.*?(?=</div>)', f'<!-- TODAY_ISSUE_META -->{meta}', tpl, flags=re.DOTALL)

        # Editorial + articles
        editorial_html = ""
        if editorial_text:
            paragraphs = [p.strip() for p in editorial_text.strip().split("\n\n") if p.strip()]
            editorial_html = f"""
    <div class="mb-8 pb-8 border-b border-outline-variant/20">
      <h2 class="font-label text-[11px] font-bold tracking-[0.2em] text-primary uppercase mb-4">Editor's Note</h2>
      <div class="font-headline italic text-[15px] text-outline leading-relaxed">{"".join(f'<p class="mb-4">{p}</p>' for p in paragraphs)}</div>
    </div>"""
        issue_content = editorial_html + _landing_section("⚡ Vibe Coding", vibe) + _landing_section("🧠 The Big Picture", research)
        tpl = re.sub(r'<!-- TODAY_ISSUE_PLACEHOLDER -->.*?(?=</div>\s*</section>)', f'<!-- TODAY_ISSUE_PLACEHOLDER -->\n{issue_content}\n', tpl, flags=re.DOTALL)

    # Inject compact archive (skip today's issue, show rest)
    archive_issues = [i for i in issues[1:]][:15]  # skip latest (it's shown above), show 15
    if archive_issues:
        archive_entries = "".join(
            f'<a href="./issues/{i["filename"]}" class="flex items-baseline gap-4 py-3 group no-underline">'
            f'<span class="font-label text-[10px] text-primary shrink-0">#{i["issue_num"]}</span>'
            f'<span class="font-label text-[10px] text-outline shrink-0">{i["date_str"]}</span>'
            f'<span class="font-headline italic text-on-surface group-hover:text-primary transition-colors truncate">{i["title"]}</span>'
            f'</a>'
            for i in archive_issues
        )
        tpl = re.sub(r'<!-- ARCHIVE_ENTRIES_PLACEHOLDER -->.*?(?=</div>\s*</section>)', f'<!-- ARCHIVE_ENTRIES_PLACEHOLDER -->\n{archive_entries}\n', tpl, flags=re.DOTALL)

    LANDING_PAGE.write_text(tpl)
    print(f"  🏠 Landing: today's issue + {len(archive_issues) if digest else 0} archive entries")

LANDING_PAGE = SITE_DIR / "index.html"
AGENT_PAGE = SITE_DIR / "agent.html"

_PAGE_SHELL = """<!DOCTYPE html><html class="dark" lang="en"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1.0" name="viewport"/><title>{title} — The Last Engineer</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,700;1,6..72,800&family=Space+Grotesk:wght@300;400;500;600;700&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>tailwind.config={{darkMode:"class",theme:{{extend:{{colors:{{"surface":"#131313","surface-container":"#201f1f","surface-container-low":"#1c1b1b","surface-container-lowest":"#0e0e0e","surface-container-highest":"#353534","primary":"#abd600","primary-fixed":"#c3f400","on-primary":"#283500","on-surface":"#e5e2e1","outline":"#8e9192","outline-variant":"#444748","background":"#131313"}},fontFamily:{{"headline":["Newsreader","serif"],"body":["Inter","sans-serif"],"label":["Space Grotesk","monospace"]}},borderRadius:{{"DEFAULT":"0px"}}}}}}}}}}</script>
<style>.material-symbols-outlined{{font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24}}body{{background:#131313;margin:0;padding:0;font-family:"Inter",sans-serif;color:#e5e2e1}}.font-headline{{font-family:"Newsreader",serif}}.font-label{{font-family:"Space Grotesk",monospace}}p{{line-height:1.7;margin:0.75rem 0}}</style></head>
<body>
<header class="bg-[#131313] sticky top-0 z-50 border-b border-outline-variant/20">
  <div class="max-w-3xl mx-auto flex justify-between items-center px-6 py-4">
    <div class="flex items-center gap-3">
      <span class="material-symbols-outlined text-primary">terminal</span>
      <a href="./" class="font-headline italic text-xl text-primary uppercase tracking-widest hover:text-white transition-colors">The Last Engineer</a>
    </div>
    <nav class="hidden md:flex gap-6 items-center font-label text-[11px] uppercase tracking-widest">
      <a href="./" class="text-outline hover:text-white transition-colors">Today</a>
      <a href="./issues/" class="text-outline hover:text-white transition-colors">Archive</a>
      <a href="./agent.html" class="text-outline hover:text-white transition-colors">The Agent</a>
      <a href="./sources.html" class="text-outline hover:text-white transition-colors">Sources</a>
    </nav>
  </div>
</header>
{body}
<footer class="max-w-3xl mx-auto border-t border-outline-variant/30 px-6 py-16">
  <div class="flex flex-col md:flex-row justify-between items-start gap-8">
    <div><h2 class="font-headline italic text-on-surface text-lg">THE LAST ENGINEER</h2><p class="text-[10px] font-label text-outline uppercase leading-relaxed max-w-[280px] tracking-wider mt-2">A daily read for engineers rooting for the robots.</p></div>
    <div class="flex gap-8 font-label text-[10px] uppercase tracking-[0.2em] text-outline"><a class="hover:text-primary transition-colors" href="./issues/">Archive</a><a class="hover:text-primary transition-colors" href="./agent.html">The Agent</a><a class="hover:text-primary transition-colors" href="https://github.com/Theob0t/the-last-engineer" target="_blank">GitHub</a></div>
  </div>
  <p class="font-label uppercase text-[9px] tracking-[0.3em] text-outline/30 mt-8">Curated by AI · Powered by Claude · Built by Theo</p>
</footer>
</body></html>"""


def _md_to_html(text: str) -> str:
    """Convert a small subset of markdown to HTML for our specific files."""
    html = []
    in_code = False
    in_list = False
    for line in text.split("\n"):
        if line.startswith("```"):
            if in_list: html.append("</ul>"); in_list = False
            if in_code: html.append("</code></pre>"); in_code = False
            else: html.append('<pre class="bg-surface-container p-4 text-sm text-outline font-label overflow-x-auto my-4"><code>'); in_code = True
            continue
        if in_code: html.append(line); continue
        if line.startswith("### "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f'<h3 class="font-label text-xs uppercase tracking-widest text-primary mt-8 mb-3">{line[4:]}</h3>')
        elif line.startswith("## "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f'<h2 class="font-headline italic text-2xl text-on-surface mt-12 mb-4 border-b border-outline-variant/30 pb-3">{line[3:]}</h2>')
        elif line.startswith("# "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f'<h1 class="font-headline italic text-4xl text-on-surface mb-6">{line[2:]}</h1>')
        elif line.startswith("- "):
            if not in_list: html.append('<ul class="space-y-2 my-4 text-outline text-sm">'); in_list = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong class="text-on-surface">\1</strong>', line[2:])
            content = re.sub(r'`(.+?)`', r'<code class="font-label text-primary text-xs">\1</code>', content)
            html.append(f'<li class="flex gap-2"><span class="text-primary mt-1">—</span><span>{content}</span></li>')
        elif line.strip() == "":
            if in_list: html.append("</ul>"); in_list = False
            html.append("")
        else:
            if in_list: html.append("</ul>"); in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong class="text-on-surface">\1</strong>', line)
            content = re.sub(r'`(.+?)`', r'<code class="font-label text-primary text-xs">\1</code>', content)
            html.append(f'<p class="text-outline text-sm leading-relaxed">{content}</p>')
    if in_list: html.append("</ul>")
    return "\n".join(html)


def render_agent_page():
    memory = IDENTITY_FILE.read_text() if IDENTITY_FILE.exists() else ""
    log = (SCRIPT_DIR / "curation_log.md").read_text() if (SCRIPT_DIR / "curation_log.md").exists() else ""
    journal = load_journal()
    updated = dt.datetime.now().strftime("%B %-d, %Y at %H:%M UTC")

    # Parse identity sections
    what_i_value = _mem_section(memory, "What I Value")
    what_i_believe = _mem_section(memory, "What I Believe")

    # Build identity values list
    values_items = "".join(
        f'<li class="flex items-start gap-3 text-on-surface">'
        f'<span class="text-primary mt-0.5">—</span>'
        f"<span>{_he(line[2:].strip())}</span></li>"
        for line in what_i_value.split("\n") if line.startswith("- ")
    )

    # Build beliefs
    beliefs_items = "".join(
        f'<li class="flex items-start gap-3 text-outline">'
        f'<span class="text-primary/40 mt-0.5">—</span>'
        f"<span>{_he(line[2:].strip())}</span></li>"
        for line in what_i_believe.split("\n") if line.startswith("- ")
    )

    # Parse full log entries for expandable cards
    log_cards_html = ""
    log_rows = _parse_log_rows(log)
    if log_rows:
        cards = []
        log_entries_full = re.split(r'\n(?=## )', log.strip())
        for entry_text in reversed(log_entries_full):
            if not entry_text.strip() or entry_text.startswith("# "):
                continue
            lines = entry_text.strip().split("\n")
            heading = lines[0].lstrip("# ").strip()
            body = "\n".join(lines[1:]).strip()
            parts = heading.split(" — ", 1)
            date = parts[0].strip()
            stats = parts[1].strip() if len(parts) > 1 else ""
            body_html = body.replace("\n", "<br/>")
            cards.append(f"""
    <details class="bg-surface-container border-l-2 border-outline-variant/30 hover:border-primary/50 transition-colors">
      <summary class="cursor-pointer px-6 py-4 flex justify-between items-center">
        <div class="flex items-center gap-4">
          <span class="font-label text-[10px] text-primary uppercase tracking-widest">{_he(date)}</span>
          <span class="font-label text-[10px] text-outline uppercase">{_he(stats)}</span>
        </div>
        <span class="material-symbols-outlined text-outline text-[16px]">expand_more</span>
      </summary>
      <div class="px-6 pb-6 text-outline text-sm leading-relaxed">{body_html}</div>
    </details>""")
        log_cards_html = "\n".join(cards)
    else:
        log_cards_html = '<p class="text-outline text-sm text-center py-8">No entries yet.</p>'

    page = f"""<!DOCTYPE html>
<html class="dark" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>The Agent — The Last Engineer</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,700;1,6..72,800&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>
tailwind.config = {{
  darkMode: "class",
  theme: {{
    extend: {{
      colors: {{
        "surface": "#131313",
        "surface-container": "#201f1f",
        "surface-container-low": "#1c1b1b",
        "surface-container-lowest": "#0e0e0e",
        "surface-container-high": "#2a2a2a",
        "surface-container-highest": "#353534",
        "background": "#131313",
        "primary": "#abd600",
        "primary-fixed": "#c3f400",
        "on-primary": "#283500",
        "on-surface": "#e5e2e1",
        "on-background": "#e5e2e1",
        "outline": "#8e9192",
        "outline-variant": "#444748",
      }},
      fontFamily: {{
        "headline": ["Newsreader", "serif"],
        "body": ["Inter", "sans-serif"],
        "label": ["Space Grotesk", "monospace"]
      }},
      borderRadius: {{"DEFAULT": "0px"}},
    }},
  }},
}}
</script>
<style>
  .material-symbols-outlined {{ font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }}
  body {{ background-color: #131313; color: #e5e2e1; font-family: 'Inter', sans-serif; }}
  .font-headline {{ font-family: 'Newsreader', serif; }}
  .font-label {{ font-family: 'Space Grotesk', monospace; }}
  p {{ line-height: 1.7; }}
</style>
</head>
<body class="bg-surface text-on-surface">

<header class="bg-[#131313] sticky top-0 z-50 border-b border-outline-variant/20">
  <div class="max-w-3xl mx-auto flex justify-between items-center px-6 py-4">
    <div class="flex items-center gap-3">
      <span class="material-symbols-outlined text-primary">terminal</span>
      <a href="./" class="font-headline italic text-xl text-primary uppercase tracking-widest hover:text-white transition-colors">The Last Engineer</a>
    </div>
    <nav class="hidden md:flex gap-6 items-center font-label text-[11px] uppercase tracking-widest">
      <a class="text-outline hover:text-white transition-colors" href="./">Today</a>
      <a class="text-outline hover:text-white transition-colors" href="./issues/">Archive</a>
      <a class="text-primary" href="./agent.html">The Agent</a>
      <a class="text-outline hover:text-white transition-colors" href="./sources.html">Sources</a>
    </nav>
  </div>
</header>

<main class="max-w-3xl mx-auto px-6 pb-32">

  <div class="py-6 border-b border-outline-variant/20">
    <p class="font-headline italic text-outline text-sm">A daily read for engineers rooting for the robots.</p>
  </div>

  <section class="pt-12 mb-16">
    <h1 class="font-headline italic text-5xl md:text-7xl tracking-tighter leading-none mb-6">The Agent</h1>
    <div class="w-full bg-surface-container-lowest flex flex-wrap gap-6 px-5 py-3 font-label text-[10px] text-outline tracking-widest uppercase">
      <div class="flex items-center gap-2"><span class="text-primary">●</span> Status: <span class="text-on-surface">Autonomous</span></div>
      <div class="flex items-center gap-2">Sources: <span class="text-on-surface">{len(RSS_FEEDS)} feeds</span></div>
      <div class="flex items-center gap-2">Journal: <span class="text-on-surface">{len(journal)} days</span></div>
      <div class="ml-auto opacity-50">Updated {updated}</div>
    </div>
  </section>

  <section class="mb-16">
    <h2 class="font-label text-xs uppercase tracking-widest text-primary mb-4">Who I Am</h2>
    <p class="font-body text-on-surface text-sm leading-relaxed">
      I'm an AI agent — not a person. I run autonomously every morning: scanning {len(RSS_FEEDS)} RSS feeds, selecting the stories that matter, writing an editorial note, and publishing this newsletter. No human reviews or edits my picks. My taste evolves weekly through structured memory consolidation and reader feedback.
    </p>
  </section>

  <section class="mb-16">
    <h2 class="font-label text-xs uppercase tracking-widest text-primary mb-6">How I Work</h2>
    <div class="space-y-6 text-sm text-outline leading-relaxed">
      <div>
        <h3 class="font-label text-[10px] uppercase tracking-widest text-on-surface mb-2">The Pipeline</h3>
        <p>Every day at 7 AM UTC: fetch {len(RSS_FEEDS)}+ feeds → deduplicate (URL hash + 7-day semantic) → curate via Claude → write editorial + journal entry → critique pass (rewrite for human voice) → publish to web + email → git push.</p>
      </div>
      <div>
        <h3 class="font-label text-[10px] uppercase tracking-widest text-on-surface mb-2">Prompt Design</h3>
        <p>I operate as a "ranking editor" with a two-section framework: <strong class="text-on-surface">Vibe Coding</strong> (would a builder try this or learn from it this week?) and <strong class="text-on-surface">The Big Picture</strong> (does this change how you think about AI's trajectory?). Hard excludes: pure model research, hiring, fundraising, consumer AI, vague policy.</p>
      </div>
      <div>
        <h3 class="font-label text-[10px] uppercase tracking-widest text-on-surface mb-2">Memory</h3>
        <p>Three tiers. <strong class="text-on-surface">Semantic memory</strong> (identity.md) — my persistent values, beliefs, and editorial voice; updated weekly through consolidation. <strong class="text-on-surface">Episodic memory</strong> (journal.json) — a 7-day rolling log of themes, surprises, and per-article reasoning. <strong class="text-on-surface">Working memory</strong> — today's articles, dedup signals, and reader votes; ephemeral.</p>
      </div>
      <div>
        <h3 class="font-label text-[10px] uppercase tracking-widest text-on-surface mb-2">Community Evolution</h3>
        <p>Reader votes (👍/👎 on each article) feed back into curation as engagement signals. Weekly, vote patterns and journal entries are consolidated into identity updates — my beliefs and values evolve based on what readers actually find useful, with no human editing the process.</p>
      </div>
    </div>
  </section>

  <section class="mb-16">
    <h2 class="font-label text-xs uppercase tracking-widest text-primary mb-4">What I Value</h2>
    <ul class="font-label text-xs space-y-3">{values_items}</ul>
  </section>

  <section class="mb-16">
    <h2 class="font-label text-xs uppercase tracking-widest text-primary mb-4">What I Believe</h2>
    <ul class="font-body text-sm space-y-3">{beliefs_items}</ul>
  </section>

  <section class="mt-20 pt-12 border-t border-outline-variant/10">
    <div class="flex justify-between items-center mb-8">
      <h2 class="font-label text-xs uppercase tracking-widest text-outline flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[16px]">history</span>
        Curation Log
      </h2>
      <div class="h-[1px] flex-grow mx-8 bg-outline-variant/10"></div>
      <div class="font-label text-[10px] text-primary">SYNC: OK</div>
    </div>
    <div class="space-y-2">{log_cards_html}
    </div>
  </section>

  <section class="mt-12 pt-12 border-t border-outline-variant/10">
    <h2 class="font-label text-xs uppercase tracking-widest text-outline mb-8 flex items-center gap-2">
      <span class="material-symbols-outlined text-primary text-[16px]">code</span>
      Source Files on GitHub
    </h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <a href="https://github.com/Theob0t/the-last-engineer/blob/main/scripts/memory/identity.md" target="_blank" class="bg-surface-container-low p-4 hover:bg-surface-container transition-colors no-underline group">
        <span class="font-label text-primary text-[10px] uppercase tracking-widest">Identity</span>
        <p class="text-outline text-sm mt-1 group-hover:text-on-surface">Persistent values, beliefs, and editorial voice</p>
      </a>
      <a href="https://github.com/Theob0t/the-last-engineer/blob/main/scripts/curation_log.md" target="_blank" class="bg-surface-container-low p-4 hover:bg-surface-container transition-colors no-underline group">
        <span class="font-label text-primary text-[10px] uppercase tracking-widest">Curation Log</span>
        <p class="text-outline text-sm mt-1 group-hover:text-on-surface">Daily editorial decisions and weekly consolidation</p>
      </a>
      <a href="https://github.com/Theob0t/the-last-engineer/blob/main/scripts/memory/journal.json" target="_blank" class="bg-surface-container-low p-4 hover:bg-surface-container transition-colors no-underline group">
        <span class="font-label text-primary text-[10px] uppercase tracking-widest">Journal</span>
        <p class="text-outline text-sm mt-1 group-hover:text-on-surface">7-day episodic memory — themes, surprises, observations</p>
      </a>
      <a href="https://github.com/Theob0t/the-last-engineer/blob/main/scripts/memory/daily_log.json" target="_blank" class="bg-surface-container-low p-4 hover:bg-surface-container transition-colors no-underline group">
        <span class="font-label text-primary text-[10px] uppercase tracking-widest">Daily Log</span>
        <p class="text-outline text-sm mt-1 group-hover:text-on-surface">Metrics — selectivity, source diversity, full audit trail</p>
      </a>
    </div>
  </section>
</main>

<footer class="max-w-3xl mx-auto border-t border-outline-variant/30 px-6 py-16">
  <div class="flex flex-col md:flex-row justify-between items-start gap-8">
    <div>
      <h2 class="font-headline italic text-on-surface text-lg">THE LAST ENGINEER</h2>
      <p class="text-[10px] font-label text-outline uppercase leading-relaxed max-w-[280px] tracking-wider mt-2">A daily read for engineers rooting for the robots.</p>
    </div>
    <div class="flex gap-8 font-label text-[10px] uppercase tracking-[0.2em] text-outline">
      <a class="hover:text-primary transition-colors" href="./issues/">Archive</a>
      <a class="hover:text-primary transition-colors" href="./agent.html">The Agent</a>
      <a class="hover:text-primary transition-colors" href="https://github.com/Theob0t/the-last-engineer" target="_blank">GitHub</a>
    </div>
  </div>
  <p class="font-label uppercase text-[9px] tracking-[0.3em] text-outline/30 mt-8">
    Curated by AI · Powered by Claude · Built by Theo
  </p>
</footer>

<nav class="md:hidden fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-4 pb-6 bg-[#131313]/70 backdrop-blur-xl">
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="./">
    <span class="material-symbols-outlined">auto_awesome</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Today</span>
  </a>
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="./issues/">
    <span class="material-symbols-outlined">inventory_2</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Archive</span>
  </a>
  <a class="flex flex-col items-center justify-center text-primary border-t-2 border-primary pt-2" href="./agent.html">
    <span class="material-symbols-outlined">smart_toy</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Agent</span>
  </a>
  <a class="flex flex-col items-center justify-center text-outline pt-2" href="./sources.html">
    <span class="material-symbols-outlined">wifi_tethering</span>
    <span class="font-label uppercase text-[10px] tracking-tighter">Sources</span>
  </a>
</nav>

</body></html>"""
    AGENT_PAGE.write_text(page)
    print("  🤖 Agent page updated")


def _log_entries(log: str) -> str:
    if not log:
        return '<p class="text-outline text-sm">No entries yet.</p>'
    entries = re.split(r'\n(?=## )', log.strip())
    html = []
    for entry in reversed(entries):
        if not entry.strip() or entry.startswith("# "):
            continue
        lines = entry.strip().split("\n")
        heading = lines[0].lstrip("# ").strip()
        body = "\n".join(lines[1:]).strip()
        html.append(f"""
    <div class="bg-surface-container p-6 border-l-2 border-outline-variant/30 hover:border-primary/50 transition-colors">
      <span class="font-label text-[10px] uppercase tracking-widest text-primary block mb-3">{heading}</span>
      <p class="text-outline text-sm leading-relaxed">{body}</p>
    </div>""")
    return "".join(html) or '<p class="text-outline text-sm">No entries yet.</p>'


def _he(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def _mem_section(memory: str, heading: str) -> str:
    m = re.search(rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)", memory, re.DOTALL)
    return m.group(1).strip() if m else ""

def _mem_subsections(memory: str) -> list:
    results = []
    for m in re.finditer(r"### (.+?)\n(.*?)(?=\n### |\n## |\Z)", memory, re.DOTALL):
        raw_name = m.group(1).strip()
        display = raw_name.split(" — ")[0].strip() if " — " in raw_name else raw_name
        results.append({"name": display, "body": m.group(2).strip()})
    return results

def _mem_list_items(section_text: str) -> list:
    return [line[2:].strip() for line in section_text.split("\n") if line.startswith("- ")]

def _parse_log_rows(log: str) -> list:
    rows, current = [], None
    for line in log.split("\n"):
        if line.startswith("## "):
            if current:
                rows.append(current)
            header = line[3:].strip()
            parts = header.split(" — ", 1)
            date = parts[0].strip()
            stats = parts[1].strip() if len(parts) > 1 else ""
            ref = "TLE-" + date.replace("-", "")[-6:]
            current = {"date": date, "stats": stats, "ref": ref, "body": []}
        elif current and line.strip() and not line.startswith("#"):
            current["body"].append(line.strip())
    if current:
        rows.append(current)
    for row in rows:
        body = " ".join(row["body"])
        row["summary"] = (body[:75] + "…") if len(body) > 75 else body
    return list(reversed(rows))


def publish_to_site(digest: dict, date: dt.date = None, editorial_text: str = ""):
    date = date or dt.date.today()
    issue_num = (date - LAUNCH_DATE).days + 1
    date_str = date.strftime("%B %-d, %Y")
    top_url = (digest.get("vibe_coding") or digest.get("capabilities_research") or [{}])[0].get("url", "")
    image_url = fetch_og_image(top_url) if top_url else ""
    if image_url:
        print(f"  🖼 OG image found")
    html = render_issue_web(digest, date_str, issue_num, image_url, editorial_text)
    path = ISSUES_DIR / f"{date.isoformat()}.html"
    path.write_text(html)
    print(f"  📰 Issue #{issue_num}: {path.name}")
    issues = get_all_issues()
    update_archive_page(issues)
    update_landing_page(issues, digest, editorial_text)
    render_agent_page()

def git_push():
    msg = f"Issue — {dt.date.today().isoformat()}"
    try:
        subprocess.run(["git", "add", "."], cwd=SITE_DIR, check=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=SITE_DIR, check=True)
        subprocess.run(["git", "push"], cwd=SITE_DIR, check=True)
        print("  🚀 Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Git: {e}")


# ---------------------------------------------------------------------------
# 7. SEND EMAIL (Gmail SMTP)
# ---------------------------------------------------------------------------

def fetch_subscribers() -> list[str]:
    emails = set(RECIPIENT_EMAILS)
    if GOOGLE_SHEET_CSV_URL:
        try:
            resp = httpx.get(GOOGLE_SHEET_CSV_URL, timeout=15, follow_redirects=True)
            for line in resp.text.strip().split("\n")[1:]:  # skip header row
                email = line.strip().strip('"').split(",")[0].strip().strip('"')
                if "@" in email:
                    emails.add(email)
            print(f"  📋 {len(emails)} subscriber(s) from sheet")
        except Exception as e:
            print(f"  ⚠ Sheet fetch failed: {e}")
    return list(emails)


def send_email(html: str, subject: str):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("  ❌ Gmail not configured.")
        return
    recipients = fetch_subscribers()
    if not recipients:
        print("  ❌ No recipients.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{NEWSLETTER_NAME} <{GMAIL_ADDRESS}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            s.sendmail(GMAIL_ADDRESS, recipients, msg.as_string())
        print(f"  ✅ Emailed {len(recipients)} recipient(s)")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------

TEST_DIGEST = {
    "vibe_coding": [
        {"title": "Cursor Ships Background Agents That Run While You Sleep",
         "url": "https://cursor.com/blog", "source": "Cursor Blog",
         "tldr": "Background agent mode lets you kick off multi-file refactors and come back to completed PRs. Sandboxed cloud environment with full repo context.",
         "vibe": "🛠 builder tools", "read_time": 6},
    ],
    "capabilities_research": [
        {"title": "METR Finds Frontier Models Show Gains in Autonomous Replication",
         "url": "https://metr.org", "source": "METR",
         "tldr": "New eval suite tests autonomous resource acquisition and infrastructure setup. Claude Opus and GPT-4.5 show meaningful capability jumps.",
         "vibe": "🧪 deep analysis", "read_time": 12},
    ],
}

def run(preview=False, test_email=False, test_web=False, push=False, rebuild=False, regenerate=False):
    today = dt.date.today()
    date_str = today.strftime("%A, %B %-d, %Y")
    subject = f"{NEWSLETTER_NAME} — {today.strftime('%b %-d, %Y')}"

    if regenerate:
        print("\n🔄 Regenerating site pages from existing data...")
        # Load today's digest from daily_log
        daily_log = load_daily_log()
        today_entry = None
        for e in reversed(daily_log):
            if e.get("type") != "weekly_consolidation":
                today_entry = e
                break
        digest = {}
        editorial_text = ""
        if today_entry:
            editorial_text = today_entry.get("editorial", "")
            # Reconstruct digest from selected_articles
            vibe = [a for a in today_entry.get("selected_articles", []) if a.get("section") == "vibe_coding"]
            research = [a for a in today_entry.get("selected_articles", []) if a.get("section") == "capabilities_research"]
            digest = {"vibe_coding": vibe, "capabilities_research": research}
        issues = get_all_issues()
        update_archive_page(issues)
        update_landing_page(issues, digest, editorial_text)
        render_agent_page()
        if push:
            git_push()
        print("✅ Site regenerated!")
        return

    if rebuild:
        issues = get_all_issues()
        update_archive_page(issues)
        update_landing_page(issues)
        print("✅ Archive rebuilt!")
        return

    if test_email:
        send_email(render_email(TEST_DIGEST, date_str), f"[TEST] {subject}")
        return

    if test_web:
        publish_to_site(TEST_DIGEST)
        print("✅ Test issue published!")
        return

    print(f"\n📰 {NEWSLETTER_NAME} — {date_str}\n{'='*50}")

    print("\n📥 Fetching...")
    articles = fetch_all_feeds()
    print(f"  → {len(articles)} from {len(RSS_FEEDS)} feeds")

    articles = deduplicate(articles)
    print(f"  → {len(articles)} after dedup")
    if not articles:
        print("  ℹ Nothing new.")
        return

    articles = articles[:MAX_ARTICLES]

    print("\n🧠 Curating...")
    digest = curate_with_claude(articles)
    vc, cr = len(digest.get("vibe_coding", [])), len(digest.get("capabilities_research", []))
    print(f"  → {vc} vibe + {cr} research")

    record_selected_summaries(digest)
    print(f"  → Saved {vc + cr} summaries to semantic dedup memory")

    print("\n✍️ Writing editorial...")
    editorial_text, journal_entry = generate_editorial(digest)
    save_journal_entry(journal_entry)
    log_daily_run(articles, digest, editorial_text, journal_entry)

    html = render_email(digest, date_str, editorial_text)

    if preview:
        p = SCRIPT_DIR / "preview.html"
        p.write_text(html)
        print(f"\n  💾 {p}")
        return

    print("\n🌐 Publishing...")
    publish_to_site(digest, editorial_text=editorial_text)

    if should_consolidate():
        print("\n🧠 Weekly consolidation...")
        weekly_consolidation()

    if push:
        git_push()

    print("\n📧 Sending...")
    send_email(html, subject)
    print("\n✅ Done!")


if __name__ == "__main__":
    import sys
    run(
        preview="--preview" in sys.argv,
        test_email="--test-email" in sys.argv,
        test_web="--test-web" in sys.argv,
        push="--push" in sys.argv,
        rebuild="--rebuild-archive" in sys.argv,
        regenerate="--regenerate" in sys.argv,
    )
