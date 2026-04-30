# Adobe Audition Forum Daily Bot

Scrapes the Adobe Audition community forum daily and posts new customer-reported issues to a Slack channel.

## How it works
- Scrapes `community.adobe.com/bug-reports-543` and `community.adobe.com/questions-544`
- Visits each post to verify it was created in the last 24 hours (not just recently replied to)
- Posts a formatted digest to Slack grouped by severity 🔴🟡🟢

## Setup on a new Mac

### 1 — Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/audition-forum-bot.git
cd audition-forum-bot
```

### 2 — Create virtual environment and install dependencies
```bash
python3 -m venv ~/audition-bot-env
source ~/audition-bot-env/bin/activate
pip install requests beautifulsoup4
```

### 3 — Create run_bot.sh from template
```bash
cp run_bot.template.sh run_bot.sh
```
Edit `run_bot.sh` and fill in:
- `SLACK_BOT_TOKEN` — get from Slack app admin or your team
- `SLACK_CHANNEL_ID` — right-click channel in Slack → View details
- Update the username in the paths (replace `YOUR_MAC_USERNAME`)

```bash
chmod +x run_bot.sh
```

### 4 — Test it manually
```bash
source ~/audition-bot-env/bin/activate
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_CHANNEL_ID="C..."
python3 scrape_and_notify.py
```

### 5 — Schedule it (runs at 9am, catches up if Mac was asleep)
```bash
# Edit com.auditionbot.plist — update the path to match your username
# Then load it:
launchctl load ~/Library/LaunchAgents/com.auditionbot.plist
```

### Run manually anytime
```bash
launchctl start com.auditionbot
# or directly:
bash run_bot.sh
```

### Check logs
```bash
cat ~/repos/audition-forum-bot-main/bot.log
```

## Files
| File | Purpose |
|---|---|
| `scrape_and_notify.py` | Main script |
| `run_bot.template.sh` | Template for run_bot.sh (copy and fill in tokens) |
| `com.auditionbot.plist` | macOS launchd scheduler config |
| `run_bot.sh` | Your local config with tokens — gitignored, never committed |
| `bot.log` | Log output — gitignored |
