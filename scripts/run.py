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

MODEL = "claude-sonnet-4-20250514"
MAX_ARTICLES = 60
MAX_ITEMS_PER_SECTION = 6
NEWSLETTER_NAME = "The Last Engineer"
LAUNCH_DATE = dt.date(2026, 3, 22)

SCRIPT_DIR = Path(__file__).parent
SEEN_FILE = SCRIPT_DIR / ".seen_hashes.json"
SITE_DIR = SCRIPT_DIR.parent
ISSUES_DIR = SITE_DIR / "issues"

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
# 3. CURATE (Claude API)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the editor of "The Last Engineer", a daily AI newsletter
for engineers rooting for the robots.

Your job is to find what actually moved today. Your readers are technical builders
and researchers — they don't want hype or marketing fluff. They want: what's novel,
useful, or cool?

You will receive articles from official blogs of top AI companies and labs.
Curate ONLY what is truly:
- NOVEL: genuinely new capability, technique, finding, or tool feature
- USEFUL: something the reader can act on, learn from, or apply
- COOL: technically impressive, surprising, or paradigm-shifting

BE RUTHLESS. If today was slow, return fewer items. Empty > mediocre.

Produce a JSON object with TWO sections:

"vibe_coding" — AI-assisted coding & building
  Include: workflow-changing tool features, significant releases, deep-dives.
  Exclude: minor patches, marketing, fundraising posts.

"capabilities_research" — AI capabilities, safety, alignment
  Include: eval results, red teaming, capability discoveries, alignment breakthroughs,
  interpretability, governance with substance, dangerous capability assessments.
  Exclude: vague policy statements, conference/hiring posts.

Each item:
- "title": specific informative headline (rewrite if needed)
- "url": original URL
- "source": source name
- "tldr": 2-3 sentences, specific, conversational
- "read_time": estimated reading time of original article in minutes
- "vibe": one of "🔥 breakthrough", "⚡ useful", "🧪 research", "🛠 shipping", "👀 notable"

Max {max_per_section} items per section. Sort by impact.
Return ONLY valid JSON. No markdown fences. No preamble."""


def load_editorial_memory() -> str:
    path = SCRIPT_DIR / "editorial_memory.md"
    if path.exists():
        return "\n\n---\n## Editorial Memory\n" + path.read_text().strip()
    return ""


def curate_with_claude(articles: list[Article]) -> dict:
    articles_text = "\n\n".join(
        f"[{i+1}] {a.title}\n    Source: {a.source}\n    URL: {a.url}\n    "
        f"Published: {a.published}\n    Preview: {a.summary[:400]}"
        for i, a in enumerate(articles)
    )
    system = SYSTEM_PROMPT.replace("{max_per_section}", str(MAX_ITEMS_PER_SECTION)) + load_editorial_memory()
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": MODEL, "max_tokens": 4000,
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
    "🔥 breakthrough": "#abd600", "⚡ useful": "#abd600",
    "🧪 research": "#a1a1aa", "🛠 shipping": "#abd600", "👀 notable": "#a1a1aa",
}

def _email_article(item: dict, featured: bool = False) -> str:
    vibe_color = VIBE_COLORS.get(item.get("vibe", ""), "#a1a1aa")
    rt = item.get("read_time", "")
    rt_html = f'<table cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;"><tr><td style="font-family:{FONT_L};font-size:9px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.15em;">⏱ {rt} min read</td></tr></table>' if rt else ""
    size = "28px" if featured else "22px"
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding:28px 0;">
      <tr><td>
        <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
          <td style="font-family:{FONT_L};font-size:10px;letter-spacing:0.15em;color:#a1a1aa;text-transform:uppercase;">{item.get('source','')}</td>
          <td align="right" style="font-family:{FONT_L};font-size:10px;color:{vibe_color};text-transform:uppercase;">{item.get('vibe','')}</td>
        </tr></table>
        <a href="{item.get('url','#')}" style="display:block;margin-top:10px;font-family:{FONT_H};font-size:{size};font-weight:400;font-style:italic;color:#e5e2e1;text-decoration:none;line-height:1.3;">{item.get('title','')}</a>
        <p style="margin:10px 0 0;font-family:{FONT_B};font-size:15px;color:#a1a1aa;line-height:1.7;">{item.get('tldr','')}</p>
        {rt_html}
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:28px;"><tr><td style="height:1px;background-color:#27272a;">&nbsp;</td></tr></table>
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

def render_email(digest: dict, date_str: str) -> str:
    vibe = digest.get("vibe_coding", [])
    research = digest.get("capabilities_research", [])
    total = len(vibe) + len(research)
    issue_num = (dt.date.today() - LAUNCH_DATE).days + 1
    content = _email_section("⚡ Vibe Coding", vibe) + _email_section("🔬 Capabilities & Alignment", research)
    if total == 0:
        content = f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="padding:60px 0;"><tr><td align="center" style="font-size:32px;">🤷</td></tr><tr><td align="center" style="font-family:{FONT_H};font-size:18px;font-style:italic;color:#e5e2e1;padding-top:12px;">Quiet day. Nothing cleared the bar.</td></tr></table>'
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Newsreader:ital,wght@0,400;0,700;1,400;1,700&family=Space+Grotesk:wght@300;400;700&display=swap" rel="stylesheet"></head>
<body style="margin:0;padding:0;background-color:#131313;-webkit-font-smoothing:antialiased;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#131313;"><tr><td align="center">
<table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">
<tr><td style="padding:48px 24px 32px;text-align:center;">
  <h1 style="margin:0;font-family:{FONT_H};font-size:28px;font-weight:500;font-style:italic;color:#e5e2e1;text-transform:uppercase;">THE LAST ENGINEER</h1>
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
    rt_html = f'<span class="font-label text-[9px] text-outline uppercase tracking-wider flex items-center gap-1"><span class="material-symbols-outlined" style="font-size:14px;">schedule</span> {rt} min read</span>' if rt else ""
    return f"""
    <article class="space-y-4 py-10">
      <div class="flex justify-between items-center font-label text-[10px] tracking-widest text-outline uppercase">
        <span>{item.get('source','')}</span><span style="color:{vibe_color};">{item.get('vibe','')}</span>
      </div>
      <h3 class="font-headline text-3xl font-normal italic leading-tight">
        <a href="{item.get('url','#')}" class="text-on-surface hover:text-primary transition-colors" target="_blank" rel="noopener">{item.get('title','')}</a>
      </h3>
      <p class="text-outline text-[15px] leading-relaxed">{item.get('tldr','')}</p>
      <div class="flex items-center gap-4 pt-2">{rt_html}<span class="h-px flex-1 bg-outline-variant/30"></span></div>
    </article>"""

def _web_section(title: str, items: list) -> str:
    if not items:
        return ""
    return f"""
    <div class="mt-16">
      <h2 class="font-label text-[11px] font-bold tracking-[0.2em] text-primary uppercase mb-2">{title}</h2>
      <div class="divide-y divide-outline-variant/20">{"".join(_web_article(i) for i in items)}</div>
    </div>"""

def render_issue_web(digest: dict, date_str: str, issue_num: int) -> str:
    vibe = digest.get("vibe_coding", [])
    research = digest.get("capabilities_research", [])
    total = len(vibe) + len(research)
    content = _web_section("⚡ Vibe Coding", vibe) + _web_section("🔬 Capabilities & Alignment", research)
    if total == 0:
        content = '<div class="py-20 text-center"><div class="text-4xl mb-4">🤷</div><p class="font-headline italic text-xl text-on-surface">Quiet day. Nothing cleared the bar.</p></div>'
    return f"""<!DOCTYPE html><html class="dark" lang="en"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1.0" name="viewport"/><title>Issue #{issue_num} — The Last Engineer</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Space+Grotesk:wght@400;500;600&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>tailwind.config={{darkMode:"class",theme:{{extend:{{colors:{{"surface":"#131313","surface-container":"#201f1f","surface-container-low":"#1c1b1b","surface-container-lowest":"#0e0e0e","surface-container-highest":"#353534","primary":"#abd600","on-primary":"#283500","on-surface":"#e5e2e1","outline":"#8e9192","outline-variant":"#444748","background":"#131313"}},fontFamily:{{"headline":["Newsreader","serif"],"body":["Inter","sans-serif"],"label":["Space Grotesk","monospace"]}},borderRadius:{{"DEFAULT":"0px"}}}}}}}}</script>
<style>.material-symbols-outlined{{font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 20;display:inline-block;vertical-align:middle;font-size:16px}}body{{background:#131313;margin:0;padding:0;-webkit-font-smoothing:antialiased;font-family:'Inter',sans-serif;color:#e5e2e1}}.font-headline{{font-family:'Newsreader',serif}}.font-label{{font-family:'Space Grotesk',monospace}}p{{line-height:1.7}}</style></head>
<body>
<header class="max-w-2xl mx-auto pt-12 pb-8 px-6 text-center">
  <a href="../" class="font-headline italic text-3xl font-medium tracking-tight text-on-surface uppercase hover:text-primary transition-colors">THE LAST ENGINEER</a>
  <div class="mt-4 flex justify-center items-center gap-4 text-[10px] font-label text-outline uppercase tracking-[0.2em] border-t border-outline-variant/30 pt-4">
    <span>Issue #{issue_num}</span><span class="w-1 h-1 bg-primary rounded-full"></span><span>{date_str}</span><span class="w-1 h-1 bg-primary rounded-full"></span><span>{total} stories</span>
  </div>
</header>
<main class="max-w-2xl mx-auto px-6 pb-20">{content}</main>
<footer class="max-w-2xl mx-auto border-t border-outline-variant/30 px-6 py-16">
  <div class="flex flex-col md:flex-row justify-between items-start gap-8">
    <div><h1 class="font-headline italic text-on-surface text-lg">THE LAST ENGINEER</h1><p class="text-[10px] font-label text-outline uppercase leading-relaxed max-w-[280px] tracking-wider mt-2">A daily read for engineers rooting for the robots.</p></div>
    <div class="flex gap-8 font-label text-[10px] uppercase tracking-[0.2em] text-outline"><a class="hover:text-primary transition-colors" href="./">Archive</a><a class="hover:text-primary transition-colors" href="../">Subscribe</a></div>
  </div>
</footer></body></html>"""


# ---------------------------------------------------------------------------
# 6. PUBLISH TO SITE
# ---------------------------------------------------------------------------

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
        issues.append({
            "date": date, "date_str": date.strftime("%b %d, %Y").upper(),
            "filename": f.name, "title": title,
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

def update_landing_page(issues: list[dict]):
    latest = issues[:3]
    if not latest:
        return
    grid = "".join(f"""
    <a href="./issues/{i['filename']}" class="bg-surface-container-low p-12 aspect-[4/5] flex flex-col justify-end group hover:bg-surface-container transition-colors no-underline">
      <span class="font-label text-[10px] uppercase text-primary mb-2 block">Issue #{i['issue_num']} · {i['date_str']}</span>
      <h5 class="text-2xl font-headline italic text-white group-hover:text-primary transition-colors">{i['title']}</h5>
    </a>""" for i in latest)
    tpl = LANDING_PAGE.read_text()
    tpl = re.sub(r'<!-- LATEST_ISSUES_PLACEHOLDER -->.*?(?=</div>\s*</section>)', f'<!-- LATEST_ISSUES_PLACEHOLDER -->\n{grid}\n', tpl, flags=re.DOTALL)
    LANDING_PAGE.write_text(tpl)
    print(f"  🏠 Landing: {len(latest)} latest issues")

LANDING_PAGE = SITE_DIR / "index.html"

def publish_to_site(digest: dict, date: dt.date = None):
    date = date or dt.date.today()
    issue_num = (date - LAUNCH_DATE).days + 1
    date_str = date.strftime("%B %-d, %Y")
    html = render_issue_web(digest, date_str, issue_num)
    path = ISSUES_DIR / f"{date.isoformat()}.html"
    path.write_text(html)
    print(f"  📰 Issue #{issue_num}: {path.name}")
    issues = get_all_issues()
    update_archive_page(issues)
    update_landing_page(issues)

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
         "vibe": "🛠 shipping", "read_time": 6},
    ],
    "capabilities_research": [
        {"title": "METR Finds Frontier Models Show Gains in Autonomous Replication",
         "url": "https://metr.org", "source": "METR",
         "tldr": "New eval suite tests autonomous resource acquisition and infrastructure setup. Claude Opus and GPT-4.5 show meaningful capability jumps.",
         "vibe": "🧪 research", "read_time": 12},
    ],
}

def run(preview=False, test_email=False, test_web=False, push=False, rebuild=False):
    today = dt.date.today()
    date_str = today.strftime("%A, %B %-d, %Y")
    subject = f"{NEWSLETTER_NAME} — {today.strftime('%b %-d, %Y')}"

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

    html = render_email(digest, date_str)

    if preview:
        p = SCRIPT_DIR / "preview.html"
        p.write_text(html)
        print(f"\n  💾 {p}")
        return

    print("\n🌐 Publishing...")
    publish_to_site(digest)
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
    )
