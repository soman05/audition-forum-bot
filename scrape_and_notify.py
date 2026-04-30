#!/usr/bin/env python3
"""
Adobe Audition Forum → Slack Daily Digest
==========================================
Runs on your Mac via cron. No cloud. No API keys. No cost.

HOW DATE FILTERING WORKS:
  The listing page shows threads with recent ACTIVITY (replies), not recent posts.
  So we fetch each post's detail page and read the ORIGINAL post date from it.
  Only posts created within the last 24 hours are included.

Dependencies (install once):
    pip install requests beautifulsoup4

Environment variables:
    SLACK_BOT_TOKEN    - xoxb-...
    SLACK_CHANNEL_ID   - C0123456789
"""

import os
import sys
import re
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

FORUM_BASE_URL  = "https://community.adobe.com"
FORUM_BOARD_URL = "https://community.adobe.com/audition-541"

CATEGORY_URLS = [
    ("https://community.adobe.com/bug-reports-543", "🐛 Bug Report"),
    ("https://community.adobe.com/questions-544",   "❓ Question"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TOPIC_PATTERN = re.compile(
    r"/(bug-reports-543|questions-544|feature-requests-545)/[^\"'\s#?]+-\d+$"
)

SEVERITY_KEYWORDS = {
    "high": [
        "crash", "crashes", "crashing", "corrupt", "freeze", "freezes", "frozen",
        "won't open", "won't start", "not working", "broken", "data loss",
        "unresponsive", "hangs", "hanging", "lost my", "lost all",
        "can't open", "cannot open", "stopped working", "screws up",
    ],
    "medium": [
        "slow", "lag", "glitch", "bug", "issue", "problem", "fails", "fail",
        "distortion", "dropout", "missing", "incorrect", "wrong", "stuck",
        "error", "overwrites", "vanished", "not saving",
    ],
}

CATEGORY_KEYWORDS = {
    "💥 Crash/Stability": ["crash", "freeze", "hang", "unresponsive", "won't open", "stopped working"],
    "🔊 Audio Quality":   ["distortion", "dropout", "noise", "static", "crackle", "hiss", "pitch", "mono", "stereo"],
    "⚡ Performance":     ["slow", "lag", "cpu", "memory", "ram", "stuttering", "performance"],
    "📁 Import/Export":   ["import", "export", "mp3", "wav", "aiff", "flac", "render", "bounce", "batch", "metadata"],
    "🖥️ UI/UX":           ["ui", "interface", "button", "panel", "window", "display", "layout", "preset", "vanished"],
    "☁️ Sync/Cloud":      ["cloud", "sync", "creative cloud", "sign in", "login", "adobe id"],
    "📦 Installation":    ["install", "update", "download", "setup", "activation"],
    "🔑 Licensing":       ["license", "serial", "subscription", "trial", "activate"],
}

NON_ISSUE_KEYWORDS = [
    "tip", "tutorial", "best way", "recommend", "suggestion",
    "love this", "workflow tip", "help me understand", "learning",
]

SLACK_API_URL = "https://slack.com/api/chat.postMessage"


# ── Time parsing ───────────────────────────────────────────────────────────────

def parse_relative_time(text: str) -> datetime | None:
    """Convert '2 hours ago', 'just now', 'yesterday' → datetime."""
    if not text:
        return None
    now  = datetime.now(timezone.utc)
    text = text.lower().strip()
    if "just now" in text:
        return now
    if "yesterday" in text:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month)", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    deltas = {
        "second": timedelta(seconds=n),
        "minute": timedelta(minutes=n),
        "hour":   timedelta(hours=n),
        "day":    timedelta(days=n),
        "week":   timedelta(weeks=n),
        "month":  timedelta(days=n * 30),
    }
    return now - deltas.get(unit, timedelta(0))


# ── Scraping ───────────────────────────────────────────────────────────────────

def get_post_created_time(url: str) -> datetime | None:
    """
    Fetch the individual post page and extract the ORIGINAL post creation date.
    The page contains strings like 'Forum|Forum|5 months ago' or '2 hours ago'.
    We take the FIRST match — that is always the original post date, not a reply.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(string=re.compile(r'\b(ago|just now)\b', re.I)):
            text = tag.strip()
            if text and len(text) < 100:
                dt = parse_relative_time(text)
                if dt:
                    return dt
    except Exception as exc:
        log.warning("Could not fetch post date for %s: %s", url, exc)
    return None


def scrape_listing(url: str, post_type: str, seen: set) -> list[dict]:
    """Scrape the category listing page and return all topic candidates."""
    candidates = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return candidates

    soup      = BeautifulSoup(resp.text, "html.parser")
    topic_map: dict[str, dict] = {}

    for anchor in soup.find_all("a", href=TOPIC_PATTERN):
        href     = anchor.get("href", "")
        text     = anchor.get_text(strip=True)
        full_url = href if href.startswith("http") else FORUM_BASE_URL + href

        if full_url not in topic_map:
            topic_map[full_url] = {"title": "", "url": full_url}
        # Longest anchor text = the title (others are reply counts, timestamps)
        if len(text) > len(topic_map[full_url]["title"]):
            topic_map[full_url]["title"] = text

    for full_url, data in topic_map.items():
        title = data["title"]
        if not title or len(title) < 10 or full_url in seen:
            continue
        seen.add(full_url)
        candidates.append({
            "title":     title,
            "url":       full_url,
            "posted_at": "",
            "post_type": post_type,
            "snippet":   "",
        })

    log.info("  %s → %d candidates on listing page", post_type, len(candidates))
    return candidates


def fetch_posts(hours_back: int = 24) -> list[dict]:
    """
    Step 1: Scrape listing pages to collect all visible topic URLs.
    Step 2: Visit each topic page to get the ORIGINAL post date.
    Step 3: Return only posts created within the last hours_back hours.
    """
    cutoff     = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    seen       = set()
    candidates = []

    for url, post_type in CATEGORY_URLS:
        candidates.extend(scrape_listing(url, post_type, seen))

    log.info("Verifying post dates for %d candidates (this takes ~%ds)...",
             len(candidates), len(candidates))

    recent = []
    for post in candidates:
        dt = get_post_created_time(post["url"])
        if dt is None:
            log.debug("Skipping (no date): %s", post["title"][:60])
            continue
        if dt < cutoff:
            log.debug("Too old (%s): %s", dt.strftime("%b %d"), post["title"][:60])
            continue
        post["posted_at"] = dt.strftime("%b %d, %H:%M UTC")
        recent.append(post)
        log.info("  ✓ %s: %s", post["posted_at"], post["title"][:60])

    return recent


# ── Classification ─────────────────────────────────────────────────────────────

def looks_like_issue(post: dict) -> bool:
    if post["post_type"] == "🐛 Bug Report":
        return True
    text = post["title"].lower()
    if any(kw in text for kw in NON_ISSUE_KEYWORDS):
        return False
    all_kws = [kw for kws in SEVERITY_KEYWORDS.values() for kw in kws]
    return any(kw in text for kw in all_kws) or "?" in post["title"]


def classify(post: dict) -> tuple[str, str]:
    text = post["title"].lower()
    severity = "🟡 Medium" if post["post_type"] == "🐛 Bug Report" else "🟢 Low"
    if any(kw in text for kw in SEVERITY_KEYWORDS["high"]):
        severity = "🔴 High"
    elif any(kw in text for kw in SEVERITY_KEYWORDS["medium"]) and severity == "🟢 Low":
        severity = "🟡 Medium"

    category = "❓ Other"
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            category = cat
            break

    return category, severity


# ── Slack ──────────────────────────────────────────────────────────────────────

def build_slack_blocks(issues: list[dict], total: int, date_str: str) -> list[dict]:
    count  = len(issues)
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🎙️ Adobe Audition Forum — Daily Report  {date_str}"}},
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{count} new issue{'s' if count != 1 else ''} reported* "
                    f"in the last 24 hours.\n"
                    f"_Severity: 🔴 High · 🟡 Medium · 🟢 Low_"
                ),
            },
        },
        {"type": "divider"},
    ]

    if not issues:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "✅ No new customer issues posted today."},
        })
    else:
        for sev in ["🔴 High", "🟡 Medium", "🟢 Low"]:
            for issue in [i for i in issues if i["severity"] == sev]:
                title = issue["title"][:150]
                title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{issue['category']}  {issue['severity']}  {issue['post_type']}\n"
                            f"*<{issue['url']}|{title}>*\n"
                            f"_🕐 {issue['posted_at']}_"
                        ),
                    },
                })
                blocks.append({"type": "divider"})

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"<{FORUM_BOARD_URL}|Open Adobe Audition Forum>  ·  Auto-generated on your Mac"}],
    })
    return blocks


def post_to_slack(blocks: list[dict], fallback: str) -> None:
    token   = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        raise EnvironmentError("SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set.")

    # Slack hard limit: 50 blocks per message — send in chunks of 45
    CHUNK_SIZE = 45
    chunks     = [blocks[i:i + CHUNK_SIZE] for i in range(0, len(blocks), CHUNK_SIZE)]
    log.info("Posting %d blocks in %d message(s)", len(blocks), len(chunks))

    for idx, chunk in enumerate(chunks):
        text = fallback if idx == 0 else f"(continued {idx + 1}/{len(chunks)})"
        resp = requests.post(
            SLACK_API_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel": channel, "text": text, "blocks": chunk},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack error on chunk {idx + 1}: {data.get('error')}")
        log.info("✅ Posted chunk %d/%d (ts=%s)", idx + 1, len(chunks), data.get("ts"))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID") if not os.environ.get(v)]
    if missing:
        sys.exit(f"❌  Missing: {', '.join(missing)}")

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("=== Adobe Audition Forum Monitor — %s ===", date_str)

    posts = fetch_posts(hours_back=24)
    log.info("Found %d posts from last 24h", len(posts))

    issues = []
    for p in posts:
        if looks_like_issue(p):
            cat, sev = classify(p)
            issues.append({**p, "category": cat, "severity": sev})

    issues.sort(key=lambda x: {"🔴 High": 0, "🟡 Medium": 1, "🟢 Low": 2}.get(x["severity"], 3))
    log.info("Flagged %d issues", len(issues))

    blocks   = build_slack_blocks(issues, len(posts), date_str)
    fallback = f"Adobe Audition Forum {date_str}: {len(issues)} new issue(s) in last 24h."
    post_to_slack(blocks, fallback)


if __name__ == "__main__":
    main()
