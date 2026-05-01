#!/usr/bin/env python3
"""
Automation Monitoring Duty Rotation Bot
========================================
Posts daily (Mon–Fri) to a Slack channel with:
- A compact main message tagging Primary and Secondary on duty
- The checklist posted as a thread reply 

Rotation logic:
- Team members sorted alphabetically by name
- Every Monday the rotation advances by 1 — new primary/secondary pair
- Week number since ROTATION_START determines the offset

Environment variables:
    SLACK_BOT_TOKEN         - xoxb-...
    DUTY_SLACK_CHANNEL_ID   - C... (your duty/monitoring channel)

"""

import os
import sys
import logging
from datetime import datetime, timezone, date, timedelta

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────

TEAM_MEMBERS = [
    {"name": "Yashwant Kumar",  "slack_id": "U03QJGRA9B2"},
    {"name": "Swati Soman",  "slack_id": "W4WBTAYGJ"},
    {"name": "Sathvik T S",  "slack_id": "U039ZDRSQ90"},
    {"name": "Pulkit Gera",  "slack_id": "W4X2FVDJA"},
    {"name": "Nikhil Khurana",  "slack_id": "U040TJVLKPF"},
    {"name": "Harshvardhan Bobbili",  "slack_id": "U071KGE1KS8"},
    {"name": "Abhishek Sharma",  "slack_id": "W4WBU0NLA"},
    {"name": "Abhishek Kapoor",  "slack_id": "W4W9Y4867"},
    {"name": "Anil Berry",  "slack_id": "W4W9WCMKM"},
    {"name": "Sankar Dey Sarkar",  "slack_id": "W4W9X4KHR"},
]

CHECKLIST = [
    ("Au Monitoring Dashboard", "<https://auditiondva.ci.corp.adobe.com/view/au-monitoring/|AU Monitoring Dashboard> — Check that all jobs are green (ignore Mac IBS that's diabled). Note: These are the Audition IBS and codex build validation jobs responsible for posting beta builds to CCD"),
    ("Node Status", "<https://auditiondva.ci.corp.adobe.com/computer/|Node Status> — Check the node status page — report any offline nodes"),
    ("Daily Beta Build Tests", "<https://auditiondva.ci.corp.adobe.com/job/Audition/view/%20test-main/|Daily Beta Build Testss> — Check status of all the jobs, job runs should be finished by morning — report any stuck, failing jobs"),
]

# Fixed reference Monday — rotation is calculated from this point.
ROTATION_START = date(2026, 5, 4)

SLACK_API_URL = "https://slack.com/api/chat.postMessage"


# ── Rotation logic ─────────────────────────────────────────────────────────────

def get_duty_pair() -> tuple[dict, dict]:
    """Returns (primary, secondary) dicts for the current week."""
    members       = TEAM_MEMBERS
    n             = len(members)
    today         = date.today()
    monday        = today - timedelta(days=today.weekday())
    weeks_elapsed = (monday - ROTATION_START).days // 7
    primary       = members[weeks_elapsed % n]
    secondary     = members[(weeks_elapsed + 1) % n]
    return primary, secondary


def mention(member: dict) -> str:
    """Returns a Slack mention string e.g. <@U0123456789>."""
    return f"<@{member['slack_id']}>"


# ── Slack blocks ───────────────────────────────────────────────────────────────

def build_main_blocks(primary: dict, secondary: dict, date_str: str) -> list[dict]:
    """Compact parent message — tags who's on duty."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🔧 Automation Monitoring Duty — {date_str}*\n"
                    f"*Primary:* {mention(primary)}   |   *Secondary:* {mention(secondary)}\n"
                    f"_Checklist in thread 👇_"
                ),
            },
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"_Rotation resets every Monday · {len(TEAM_MEMBERS)} team members_",
            }],
        },
    ]


def build_checklist_blocks():
    checklist_lines = "\n".join(
        f"  ☐ {desc}" for _, desc in CHECKLIST
    )
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Today's checklist:*\n{checklist_lines}",
            },
        },
    ]


# ── Slack posting ──────────────────────────────────────────────────────────────

def post_to_slack(primary: dict, secondary: dict, date_str: str) -> None:
    token   = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("DUTY_SLACK_CHANNEL_ID", "")
    if not token or not channel:
        raise EnvironmentError("SLACK_BOT_TOKEN and DUTY_SLACK_CHANNEL_ID must be set.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    # Step 1 — Post compact main message (tags both assignees)
    resp = requests.post(
        SLACK_API_URL,
        headers=headers,
        json={
            "channel": channel,
            "text":    f"Monitoring duty {date_str}: Primary={primary['name']}, Secondary={secondary['name']}",
            "blocks":  build_main_blocks(primary, secondary, date_str),
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error (main): {data.get('error')}")
    thread_ts = data["ts"]
    log.info("✅ Posted main message (ts=%s)", thread_ts)

    # Step 2 — Post checklist as thread reply
    resp = requests.post(
        SLACK_API_URL,
        headers=headers,
        json={
            "channel":   channel,
            "text":      "Today's monitoring checklist",
            "blocks":    build_checklist_blocks(),
            "thread_ts": thread_ts,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error (thread): {data.get('error')}")
    log.info("✅ Posted checklist to thread (ts=%s)", data.get("ts"))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ("SLACK_BOT_TOKEN", "DUTY_SLACK_CHANNEL_ID") if not os.environ.get(v)]
    if missing:
        sys.exit(f"❌  Missing: {', '.join(missing)}")

    date_str           = datetime.now(timezone.utc).strftime("%a %b %d, %Y")
    primary, secondary = get_duty_pair()

    log.info("=== Duty Rotation — %s ===", date_str)
    log.info("Primary: %s | Secondary: %s", primary["name"], secondary["name"])

    post_to_slack(primary, secondary, date_str)


if __name__ == "__main__":
    main()
